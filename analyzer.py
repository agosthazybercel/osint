from __future__ import annotations

import re
from collections import Counter, defaultdict

from .models import Evidence, UsernameProfile
from .utils import normalize_text, root_domain, unique_keep_order
from .identity import build_query_profile, confidence_from_identity, norm as identity_norm, rootish_domain


def query_terms(query: str) -> list[str]:
    cleaned = identity_norm(query or "")
    return unique_keep_order([t for t in cleaned.split() if len(t) >= 3])


def relevance(query: str, title: str, snippet: str, text: str, url: str = "", context: str = "") -> tuple[float, list[str]]:
    profile = build_query_profile(query, "person" if len(query.split()) >= 2 else "general", context)
    terms = profile.target_tokens or query_terms(query)
    title_l = identity_norm(title or "")
    snippet_l = identity_norm(snippet or "")
    text_l = identity_norm(text or "")
    url_l = identity_norm(url or "")
    score = 0.0
    matched: list[str] = []

    full_query = identity_norm(profile.target_text.strip())
    if full_query and full_query in title_l:
        score += 8; matched.append("exact_title")
    if full_query and full_query in snippet_l:
        score += 6; matched.append("exact_snippet")
    if full_query and full_query in text_l[:6000]:
        score += 7; matched.append("exact_text")
    if full_query and full_query in url_l.replace("-", " ").replace("_", " "):
        score += 6; matched.append("exact_url")

    for term in terms:
        s = 0.0
        if re.search(rf"\b{re.escape(term)}\b", url_l):
            s += 2.0
        if re.search(rf"\b{re.escape(term)}\b", title_l):
            s += 4.0
        if re.search(rf"\b{re.escape(term)}\b", snippet_l):
            s += 3.0
        count = len(re.findall(rf"\b{re.escape(term)}\b", text_l[:12000]))
        if count:
            s += min(count * 0.5, 5.0)
        if s > 0:
            matched.append(term)
            score += s

    for cterm in profile.context_tokens:
        if cterm in title_l or cterm in snippet_l or cterm in url_l or cterm in text_l[:10000]:
            score += 1.5
            matched.append("ctx:" + cterm)

    if len(text or "") > 600:
        score += 0.6
    if len(text or "") > 3000:
        score += 0.8

    return round(score, 2), unique_keep_order(matched)


def confidence_from_score(score: float, matched_terms: list[str], mode: str = "general") -> str:
    # Kept for compatibility; identity.py does stricter scoring.
    return confidence_from_identity(score, matched_terms, mode)


def overall_confidence(evidence: list[Evidence]) -> str:
    if not evidence:
        return "none"
    high = sum(1 for e in evidence if e.confidence == "high")
    med = sum(1 for e in evidence if e.confidence == "medium")
    if high >= 2 or (high >= 1 and med >= 2):
        return "high"
    if high >= 1 or med >= 2:
        return "medium"
    if med >= 1 or len(evidence) >= 3:
        return "low"
    return "very_low"


def cluster_by_domain(evidence: list[Evidence]) -> dict[str, list[int]]:
    clusters: dict[str, list[int]] = defaultdict(list)
    for ev in evidence:
        clusters[root_domain(ev.source)].append(ev.id)
    return dict(sorted(clusters.items(), key=lambda kv: len(kv[1]), reverse=True))


def _top_unique(items: list[str], limit: int) -> list[str]:
    cleaned = [normalize_text(x).strip() for x in items if normalize_text(x).strip()]
    # prefer shorter profile-like canonical values over repeated tracking URLs
    cleaned = sorted(unique_keep_order(cleaned), key=lambda x: (len(x) > 160, len(x)))
    return cleaned[:limit]


def aggregate_findings(evidence: list[Evidence], username_profiles: list[UsernameProfile] | None = None) -> dict:
    emails: list[str] = []
    phones: list[str] = []
    socials: list[str] = []
    usernames: list[str] = []
    images: list[str] = []
    videos: list[str] = []
    locations: list[str] = []
    related_names: list[str] = []
    orgs: list[str] = []
    records: list[str] = []
    dates: list[str] = []
    top_domains = Counter()
    sources_by_confidence = Counter()

    # only high/medium evidence contributes to sensitive-looking findings by default
    trusted = [e for e in evidence if e.confidence in {"high", "medium"}] or evidence[:3]

    for ev in trusted:
        emails.extend(ev.emails)
        phones.extend(ev.phones)
        socials.extend(ev.social_profiles)
        usernames.extend(ev.usernames)
        locations.extend(ev.locations)
        related_names.extend(ev.related_names)
        orgs.extend(ev.organizations)
        records.extend(ev.public_record_hints)
        dates.extend(getattr(ev, "dates", []))
        for m in ev.media:
            if m.type == "image":
                images.append(m.url)
            elif m.type == "video":
                videos.append(m.url)

    for ev in evidence:
        sources_by_confidence[ev.confidence] += 1
        if ev.source:
            top_domains[rootish_domain(ev.source)] += 1

    profiles = username_profiles or []
    confirmed_profiles = [p.url for p in profiles if p.status == "confirmed"]
    possible_profiles = [p.url for p in profiles if p.status == "possible"]

    social_list = _top_unique([*socials, *confirmed_profiles, *possible_profiles], 40)
    return {
        "contacts": {
            "emails": _top_unique(emails, 15),
            "phones": _top_unique(phones, 15),
        },
        "social_profiles": social_list,
        "direct_username_profiles": {
            "confirmed": _top_unique(confirmed_profiles, 25),
            "possible": _top_unique(possible_profiles, 25),
            "unavailable_count": sum(1 for p in profiles if p.status == "unavailable"),
            "error_count": sum(1 for p in profiles if p.status == "error"),
        },
        "usernames": _top_unique(usernames, 25),
        "media": {
            "images": _top_unique(images, 18),
            "videos": _top_unique(videos, 12),
        },
        "mentions": {
            "top_domains": dict(top_domains.most_common(16)),
            "domain_clusters": cluster_by_domain(evidence),
            "evidence_by_confidence": dict(sources_by_confidence),
        },
        "locations": _top_unique(locations, 16),
        "organizations": _top_unique(orgs, 18),
        "related_names": _top_unique(related_names, 18),
        "public_record_hints": _top_unique(records, 16),
        "dates": _top_unique(dates, 30),
        "visual_profile": {
            "entity_counts": {
                "emails": len(unique_keep_order(emails)),
                "phones": len(unique_keep_order(phones)),
                "social_profiles": len(social_list),
                "usernames": len(unique_keep_order(usernames)),
                "images": len(unique_keep_order(images)),
                "videos": len(unique_keep_order(videos)),
                "locations": len(unique_keep_order(locations)),
                "organizations": len(unique_keep_order(orgs)),
                "related_names": len(unique_keep_order(related_names)),
                "record_hints": len(unique_keep_order(records)),
                "dates": len(unique_keep_order(dates)),
            }
        },
    }


def executive_summary_from_findings(query: str, findings: dict, evidence: list[Evidence], confidence: str) -> str:
    contacts = findings.get("contacts", {})
    media = findings.get("media", {})
    social_count = len(findings.get("social_profiles", []))
    email_count = len(contacts.get("emails", []))
    phone_count = len(contacts.get("phones", []))
    img_count = len(media.get("images", []))
    video_count = len(media.get("videos", []))
    evidence_count = len(evidence)
    top_sources = list(findings.get("mentions", {}).get("top_domains", {}).keys())[:4]
    if evidence_count == 0:
        return "No strong public evidence was accepted. Add disambiguation context such as city, school/company, username or domain."
    return (
        f"Accepted {evidence_count} public evidence item(s) after strict identity filtering. "
        f"Overall confidence: {confidence}. Curated findings: {social_count} social/profile URL(s), "
        f"{email_count} email(s), {phone_count} phone number(s), {img_count} image URL(s), "
        f"{video_count} video URL(s). Main domains: {', '.join(top_sources) if top_sources else 'none'}."
    )
