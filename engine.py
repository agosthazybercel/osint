from __future__ import annotations

import time
from datetime import datetime

from .analyzer import aggregate_findings, executive_summary_from_findings, overall_confidence, relevance
from .identity import (
    QueryProfile,
    build_query_profile,
    confidence_from_identity,
    evidence_window,
    filter_media_for_identity,
    filter_social_urls_for_identity,
    identity_pass_profile,
    identity_score_profile,
    looks_like_person_name,
    normalize_text,
)
from .config import settings
from .crawler import extract_links, extract_media, extract_text, extract_title, fetch_url, find_social_urls, find_video_urls
from .extractors import (
    extract_dates,
    extract_emails,
    extract_locations,
    extract_organizations,
    extract_phones,
    extract_public_record_hints,
    extract_related_names,
    extract_usernames,
)
from .models import DeepSearchReport, Evidence, SearchHit, SearchMode, TargetType
from .query_builder import build_queries, infer_mode
from .search_providers import search_all
from .summarizer import summarize
from .enrichment import enrich_findings
from .username_scanner import looks_like_username, normalize_username, scan_username, username_profiles_to_hits
from .social_intel import analyze_social_profiles
from .utils import content_hash, domain_from_url, normalize_text as util_normalize_text, normalize_url, unique_keep_order


class LawfulUseRequired(PermissionError):
    pass


class DeepSearchError(RuntimeError):
    pass


def validate_lawful_use(target_type: TargetType, lawful_use_confirmed: bool) -> list[str]:
    warnings: list[str] = []
    if target_type == "unknown":
        warnings.append("Target type is unknown. Use only for lawful, proportionate public-information research.")
    if target_type in {"consented_person", "self", "company", "public_person", "journalism_or_research"}:
        warnings.append("This tool only aggregates public web results. Verify important findings manually before relying on them.")
    if settings.require_lawful_use and not lawful_use_confirmed:
        raise LawfulUseRequired("Lawful-use confirmation is required. CLI: add --lawful-use. Web UI: tick the lawful-use checkbox.")
    return warnings


def _hit_from_direct_url(query: str) -> SearchHit | None:
    q = query.strip()
    if q.startswith("http://") or q.startswith("https://"):
        return SearchHit(title=q, url=normalize_url(q), source=domain_from_url(q), provider="direct", query_used=q, rank=0)
    if "." in q and " " not in q and "@" not in q:
        url = "https://" + q.strip("/")
        return SearchHit(title=q, url=normalize_url(url), source=domain_from_url(url), provider="direct", query_used=q, rank=0)
    return None


def _entity_text_for_profile(profile: QueryProfile, title: str, snippet: str, text: str) -> str:
    if profile.mode == "person" or looks_like_person_name(profile.target_text):
        return evidence_window(profile, title, snippet, text)
    return util_normalize_text(" ".join([title, snippet, text[:12000]]))


def _build_evidence_from_hit(eid: int, profile: QueryProfile, hit: SearchHit) -> Evidence | None:
    fetched = fetch_url(hit.url)
    html_or_text = fetched.text if fetched else ""
    title = extract_title(html_or_text) if html_or_text else ""
    title = title or hit.title or hit.url
    text = extract_text(html_or_text, hit.url) if html_or_text else util_normalize_text(hit.snippet)

    # Keep direct username hits even if the profile page is not fetchable.
    if len(text) < 80 and hit.provider != "direct_username":
        combined = util_normalize_text(f"{hit.title}. {hit.snippet}")
        if len(combined) < 60:
            return None
        text = combined

    passed_identity, id_score, id_reasons = identity_pass_profile(profile, title, hit.snippet, text, hit.url)
    person_like = profile.mode == "person" or (profile.mode == "general" and looks_like_person_name(profile.target_text))
    if person_like and hit.provider != "direct_username" and not passed_identity:
        return None
    if profile.mode in {"email", "phone", "username"} and hit.provider != "direct_username" and not passed_identity:
        return None

    links = extract_links(html_or_text, hit.url) if html_or_text else []
    media = extract_media(html_or_text, hit.url) if html_or_text else []
    video_links = find_video_urls([hit.url, *links])
    for video_url in video_links:
        if all(m.url != video_url for m in media):
            from .models import MediaItem
            media.append(MediaItem(type="video", url=video_url, source_page=hit.url, alt="video link"))

    combined_text = " ".join([hit.title, hit.snippet, title, text])
    local_entity_text = _entity_text_for_profile(profile, title, hit.snippet, text)
    all_urls = [hit.url, *links]
    social_profiles = filter_social_urls_for_identity(profile.target_text, find_social_urls(all_urls), profile.mode, profile.context_text)

    emails = extract_emails(local_entity_text)
    phones = extract_phones(local_entity_text)
    usernames = extract_usernames(local_entity_text, urls=social_profiles)
    locations = extract_locations(local_entity_text[:9000])
    organizations = extract_organizations(local_entity_text[:9000])
    related_names = extract_related_names(local_entity_text[:9000], query=profile.target_text, max_names=12)
    public_records = extract_public_record_hints(local_entity_text, hit.url)
    dates = extract_dates(local_entity_text[:9000])

    rel_score, matched = relevance(query=profile.target_text, title=title, snippet=hit.snippet, text=text, url=hit.url, context=profile.context_text)
    score = rel_score + id_score
    matched = unique_keep_order([*matched, *id_reasons])
    if hit.provider == "direct_username":
        score += 4
        if profile.username and profile.username.lower() in hit.url.lower():
            score += 6
            matched = unique_keep_order([*matched, "direct_username"])

    confidence = confidence_from_identity(score, matched, mode=profile.mode)
    media = filter_media_for_identity(profile.target_text, media, title, local_entity_text, confidence, profile.mode, profile.context_text)

    # Sensitive-ish page-wide contact details are only retained if identity confidence is acceptable.
    if person_like and confidence not in {"high", "medium"}:
        emails, phones, media, social_profiles = [], [], [], []

    return Evidence(
        id=eid,
        title=title,
        url=hit.url,
        source=hit.source or domain_from_url(hit.url),
        provider=hit.provider,
        query_used=hit.query_used,
        snippet=hit.snippet,
        extracted_text=text[: settings.max_text_chars_per_page],
        relevance_score=round(score, 2),
        confidence=confidence,
        matched_terms=matched,
        emails=emails,
        phones=phones,
        social_profiles=social_profiles[:20],
        usernames=usernames[:12],
        media=media[:10],
        locations=locations[:12],
        organizations=organizations[:12],
        related_names=related_names[:12],
        public_record_hints=public_records[:12],
        dates=dates[:20],
        content_hash=content_hash(text),
    )


def deep_search(
    query: str,
    mode: SearchMode = "general",
    target_type: TargetType = "unknown",
    max_results_per_query: int | None = None,
    max_pages: int | None = None,
    delay_seconds: float | None = None,
    providers: list[str] | None = None,
    ai: bool = True,
    lawful_use_confirmed: bool = False,
    scan_usernames: bool = True,
    context: str = "",
) -> DeepSearchReport:
    query = query.strip()
    if not query:
        raise ValueError("Query cannot be empty.")

    mode = infer_mode(query, mode)  # type: ignore
    profile = build_query_profile(query, mode, context)
    max_results_per_query = max_results_per_query or settings.default_max_results_per_query
    max_pages = max_pages or settings.default_max_pages
    delay = settings.default_delay_seconds if delay_seconds is None else delay_seconds

    warnings = validate_lawful_use(target_type, lawful_use_confirmed)
    search_queries = build_queries(query, mode, context=context)
    if mode == "person" or (mode == "general" and looks_like_person_name(profile.target_text)):
        warnings.append("Strict identity mode is active: weak pages, generic images, app icons, listing pages and unrelated entities are filtered out.")
        if not profile.context_text:
            warnings.append("For better precision, add disambiguation context: city, school/company, username, domain, or exact quoted phrase.")

    raw_hits: list[SearchHit] = []
    provider_errors: list[str] = []
    rejected_reasons = {"identity_filter": 0, "duplicate_content": 0, "unreadable_or_thin": 0}

    direct_hit = _hit_from_direct_url(query)
    if direct_hit:
        raw_hits.append(direct_hit)

    username_profiles = []
    should_username_scan = scan_usernames and (mode == "username" or bool(profile.username) or looks_like_username(query))
    if should_username_scan:
        username = normalize_username(profile.username or query)
        username_profiles = scan_username(username, delay=min(delay, 0.4))
        raw_hits.extend(username_profiles_to_hits(username_profiles, username))

    seen_urls: set[str] = {normalize_url(h.url) for h in raw_hits}
    for sq in search_queries:
        hits, errors = search_all(sq, max_results=max_results_per_query, providers=providers)
        provider_errors.extend(errors)
        for hit in hits:
            key = normalize_url(hit.url)
            if key and key not in seen_urls:
                seen_urls.add(key)
                raw_hits.append(hit)
        time.sleep(delay)

    evidence: list[Evidence] = []
    seen_content: set[str] = set()
    processed = 0

    for hit in raw_hits:
        if processed >= max_pages:
            break
        before = len(evidence)
        ev = _build_evidence_from_hit(len(evidence) + 1, profile, hit)
        processed += 1
        if not ev:
            rejected_reasons["identity_filter"] += 1
            time.sleep(delay)
            continue
        if ev.content_hash and ev.content_hash in seen_content and ev.provider != "direct_username":
            rejected_reasons["duplicate_content"] += 1
            time.sleep(delay)
            continue
        if ev.content_hash:
            seen_content.add(ev.content_hash)
        evidence.append(ev)
        time.sleep(delay)

    evidence.sort(key=lambda e: (e.confidence == "high", e.confidence == "medium", e.relevance_score), reverse=True)
    for idx, ev in enumerate(evidence, start=1):
        ev.id = idx

    findings = aggregate_findings(evidence, username_profiles=username_profiles)
    findings = enrich_findings(
        query=profile.target_text,
        context=profile.context_text,
        mode=mode,
        target_type=target_type,
        findings=findings,
        evidence=evidence,
        username_profiles=username_profiles,
        raw_hits_count=len(raw_hits),
        rejected=rejected_reasons,
        search_queries=search_queries,
    )

    # Public social-media intelligence layer. This only analyzes reachable public profile pages
    # and metadata; it does not log in, bypass privacy settings, or scrape private content.
    try:
        findings["social_intelligence"] = analyze_social_profiles(
            evidence=evidence,
            username_profiles=username_profiles,
            query=profile.target_text,
            context=profile.context_text,
            max_profiles=30,
            delay=min(delay, 0.45),
        )
    except Exception as exc:
        provider_errors.append(f"Social intelligence failed: {exc}")
        findings["social_intelligence"] = {"profiles": [], "summary": {}, "platform_counts": {}, "confidence_counts": {}}

    confidence = overall_confidence(evidence)
    executive_summary = executive_summary_from_findings(profile.display_query, findings, evidence, confidence)

    if not evidence:
        warnings.append("No strong public evidence found. Try exact quotes, add context, or configure Brave/SerpAPI keys for better search coverage.")
    if mode == "person" and len(profile.target_tokens) <= 2 and not profile.context_text:
        warnings.append("Name-only searches can merge same-name people. Add city, school/company, username or domain context.")

    summary = "AI summary disabled."
    if ai and evidence:
        try:
            summary = summarize(query=profile.display_query, mode=mode, target_type=target_type, findings=findings, evidence=evidence[:12])
        except Exception as exc:
            provider_errors.append(f"AI summary failed: {exc}")
            summary = "AI summary failed. See provider errors."

    stats = {
        "raw_hits": len(raw_hits),
        "processed_hits": processed,
        "accepted_evidence_count": len(evidence),
        "rejected": rejected_reasons,
        "search_query_count": len(search_queries),
        "username_profiles_checked": len(username_profiles),
        "profile": {
            "target_text": profile.target_text,
            "context_text": profile.context_text,
            "target_tokens": profile.target_tokens,
            "context_tokens": profile.context_tokens,
        },
        "primary_mode": mode,
    }

    return DeepSearchReport(
        query=profile.display_query,
        mode=mode,
        target_type=target_type,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        search_queries=search_queries,
        summary=summary,
        executive_summary=executive_summary,
        confidence_overall=confidence,
        findings=findings,
        evidence=evidence,
        username_profiles=username_profiles,
        warnings=warnings,
        provider_errors=provider_errors,
        stats=stats,
    )
