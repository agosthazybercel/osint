from __future__ import annotations

import re
import socket
import ssl
from collections import Counter, defaultdict
from datetime import datetime
from urllib.parse import urlparse

from .models import Evidence, UsernameProfile
from .utils import domain_from_url, root_domain, unique_keep_order, normalize_text

HIGH_TRUST_HINTS = [
    ".edu", ".gov", "gov.", "edu.", "ac.", "school", "iskola", "gimnazium", "gimnázium",
    "github.com", "linkedin.com", "company", "official", "about", "contact",
]
LOW_TRUST_HINTS = [
    "pinterest", "cdn", "static", "imgur", "gstatic", "googleusercontent", "facebook.com/plugins",
    "badge", "icon", "logo", "cdninstagram", "wikimedia.org/wikipedia/commons/thumb",
]

DATE_RE = re.compile(r"\b(20\d{2}|19\d{2})[-./ ]?(0?[1-9]|1[0-2])?[-./ ]?(0?[1-9]|[12]\d|3[01])?\b")


def source_quality(domain: str, url: str = "") -> dict:
    d = (domain or domain_from_url(url) or "").lower()
    u = (url or "").lower()
    score = 50
    reasons: list[str] = []
    if any(h in d or h in u for h in HIGH_TRUST_HINTS):
        score += 25
        reasons.append("high_signal_source")
    if d.endswith(".hu"):
        score += 5
        reasons.append("local_hu_domain")
    if any(h in d or h in u for h in LOW_TRUST_HINTS):
        score -= 30
        reasons.append("low_signal_or_media_host")
    if "http://" in u:
        score -= 5
        reasons.append("not_https")
    if len(d.split(".")) > 4:
        score -= 5
        reasons.append("deep_subdomain")
    score = max(0, min(100, score))
    band = "high" if score >= 75 else "medium" if score >= 50 else "low"
    return {"score": score, "band": band, "reasons": reasons or ["generic_web_source"]}


def build_search_plan(query: str, mode: str, context: str, search_queries: list[str]) -> dict:
    steps = []
    if mode == "person":
        steps = [
            "Exact quoted name search",
            "Name + disambiguation context",
            "High-signal platforms only",
            "Identity scoring and false-positive rejection",
            "Evidence-window entity extraction",
            "Manual verification of high-confidence sources",
        ]
    elif mode == "username":
        steps = ["Direct username scan", "Quoted handle search", "Platform-specific profile validation", "Cross-source corroboration"]
    elif mode in {"domain", "company"}:
        steps = ["Official domain discovery", "Contact and social profile extraction", "News/document search", "Basic DNS/SSL checks", "Source-quality scoring"]
    else:
        steps = ["Exact query search", "Context expansion", "Source scoring", "Entity extraction", "Report synthesis"]
    return {
        "query": query,
        "mode": mode,
        "context": context,
        "steps": steps,
        "queries": search_queries[:40],
    }


def identity_candidates(query: str, context: str, evidence: list[Evidence]) -> list[dict]:
    buckets: dict[str, list[Evidence]] = defaultdict(list)
    for ev in evidence:
        keys = [root_domain(ev.source or domain_from_url(ev.url))]
        for org in ev.organizations[:3]:
            keys.append("org:" + org.lower())
        for loc in ev.locations[:2]:
            keys.append("loc:" + loc.lower())
        key = keys[0] if keys else "unknown"
        buckets[key].append(ev)

    candidates = []
    for key, evs in buckets.items():
        high = sum(1 for e in evs if e.confidence == "high")
        med = sum(1 for e in evs if e.confidence == "medium")
        ctx_hits = sum(1 for e in evs if any(str(m).startswith("ctx:") for m in e.matched_terms))
        score = min(100, int(sum(e.relevance_score for e in evs) + high * 18 + med * 9 + ctx_hits * 12))
        candidates.append({
            "candidate": key,
            "score": score,
            "evidence_ids": [e.id for e in evs[:12]],
            "high_confidence": high,
            "medium_confidence": med,
            "context_hits": ctx_hits,
            "summary": f"{len(evs)} source(s), {high} high-confidence, {med} medium-confidence.",
        })
    return sorted(candidates, key=lambda c: c["score"], reverse=True)[:8]


def profile_completeness(findings: dict, evidence: list[Evidence], mode: str) -> dict:
    checks = {
        "name_or_query_match": bool(evidence),
        "high_confidence_evidence": any(e.confidence == "high" for e in evidence),
        "multiple_sources": len({root_domain(e.source) for e in evidence if e.source}) >= 2,
        "social_profiles": bool(findings.get("social_profiles")),
        "organization": bool(findings.get("organizations")),
        "location": bool(findings.get("locations")),
        "media": bool((findings.get("media") or {}).get("images") or (findings.get("media") or {}).get("videos")),
        "dates_or_timeline": bool(findings.get("dates")),
        "contact": bool((findings.get("contacts") or {}).get("emails") or (findings.get("contacts") or {}).get("phones")),
        "documents_or_records": bool(findings.get("public_record_hints")),
    }
    # For person searches, missing contact is not necessarily bad; keep it lower-weight by using equal weight but transparent labels.
    score = int(sum(checks.values()) / len(checks) * 100)
    return {"score": score, "checks": checks, "band": "strong" if score >= 70 else "partial" if score >= 40 else "thin"}


def build_timeline(evidence: list[Evidence]) -> list[dict]:
    events: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for ev in evidence:
        values = ev.dates or DATE_RE.findall(" ".join([ev.title, ev.snippet, ev.extracted_text[:1800]]))
        for d in values[:5]:
            if isinstance(d, tuple):
                year, month, day = d
                date = "-".join(x.zfill(2) if i else x for i, x in enumerate([year, month or "01", day or "01"]))
            else:
                date = str(d)
            key = (date[:10], ev.url)
            if key in seen:
                continue
            seen.add(key)
            events.append({"date": date[:10], "evidence_id": ev.id, "title": ev.title[:120], "source": ev.source, "url": ev.url})
    return sorted(events, key=lambda e: e["date"])[:60]


def false_positive_report(evidence: list[Evidence], raw_hits_count: int, rejected: dict | None = None) -> dict:
    low = [e for e in evidence if e.confidence in {"low", "very_low", "none"}]
    risky = []
    for ev in low[:20]:
        risky.append({
            "evidence_id": ev.id,
            "title": ev.title[:160],
            "reason": "low_identity_confidence",
            "score": ev.relevance_score,
            "url": ev.url,
        })
    return {
        "accepted": len(evidence),
        "raw_hits": raw_hits_count,
        "rejected": rejected or {},
        "potential_false_positives": risky,
        "noise_ratio": round((sum((rejected or {}).values()) / max(1, raw_hits_count)) * 100, 1),
    }


def privacy_cleanup(findings: dict, mode: str, target_type: str) -> list[str]:
    tips = []
    contacts = findings.get("contacts") or {}
    if contacts.get("emails"):
        tips.append("Email cím publikus találatban szerepel; saját keresésnél ellenőrizd, szükséges-e nyilvánosan hagyni.")
    if contacts.get("phones"):
        tips.append("Telefonszám publikus találatban szerepel; saját keresésnél fontold meg az eltávolítást vagy elrejtést.")
    if findings.get("social_profiles"):
        tips.append("Social/profil linkek azonosíthatók; ellenőrizd a profilok bio/adatvédelmi beállításait.")
    if (findings.get("media") or {}).get("images"):
        tips.append("Képek találhatók; saját digitális lábnyomnál ellenőrizd az arcot, helyszínt vagy metaadatot tartalmazó képeket.")
    if not tips:
        tips.append("Nem látszik erős publikus kontakt vagy média találat a kurált eredményekben.")
    return tips


def document_search_queries(query: str, context: str = "") -> list[str]:
    q = f'"{query.strip().strip("\"")}"'
    ctx = context.strip()
    base = f"{q} {ctx}" if ctx else q
    return [
        f"{base} filetype:pdf",
        f"{base} filetype:docx",
        f"{base} filetype:pptx",
        f"{base} site:.hu filetype:pdf",
    ]


def domain_intelligence(query: str, evidence: list[Evidence]) -> dict:
    domain = ""
    q = query.replace("https://", "").replace("http://", "").split("/")[0].strip()
    if "." in q and " " not in q:
        domain = q
    elif evidence:
        domain = root_domain(evidence[0].source or domain_from_url(evidence[0].url))
    if not domain:
        return {}
    out = {"domain": domain, "dns": {}, "ssl": {}, "errors": []}
    try:
        infos = socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)
        ips = unique_keep_order([i[4][0] for i in infos])[:8]
        out["dns"]["ips"] = ips
    except Exception as exc:
        out["errors"].append(f"DNS lookup failed: {exc}")
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=5) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
                out["ssl"] = {
                    "subject": cert.get("subject", []),
                    "issuer": cert.get("issuer", []),
                    "not_before": cert.get("notBefore"),
                    "not_after": cert.get("notAfter"),
                }
    except Exception as exc:
        out["errors"].append(f"SSL check failed: {exc}")
    return out


def source_quality_table(evidence: list[Evidence]) -> list[dict]:
    rows = []
    for ev in evidence[:80]:
        q = source_quality(ev.source, ev.url)
        rows.append({"evidence_id": ev.id, "domain": ev.source, "url": ev.url, **q})
    return rows


def monitoring_suggestions(query: str, context: str, mode: str) -> list[str]:
    q = query.strip().strip('"')
    ctx = context.strip()
    terms = [f'"{q}"']
    if ctx:
        terms.append(f'"{q}" "{ctx}"')
    if mode in {"company", "domain"}:
        terms += [f'"{q}" news', f'"{q}" contact', f'"{q}" filetype:pdf']
    else:
        terms += [f'"{q}" profile', f'"{q}" interview OR article']
    return unique_keep_order(terms)[:8]


def enrich_findings(
    query: str,
    context: str,
    mode: str,
    target_type: str,
    findings: dict,
    evidence: list[Evidence],
    username_profiles: list[UsernameProfile],
    raw_hits_count: int,
    rejected: dict | None,
    search_queries: list[str],
) -> dict:
    findings = dict(findings or {})
    advanced = {
        "search_plan": build_search_plan(query, mode, context, search_queries),
        "identity_candidates": identity_candidates(query, context, evidence),
        "profile_completeness": profile_completeness(findings, evidence, mode),
        "timeline": build_timeline(evidence),
        "false_positive_control": false_positive_report(evidence, raw_hits_count, rejected),
        "source_quality": source_quality_table(evidence),
        "privacy_cleanup": privacy_cleanup(findings, mode, target_type),
        "document_search_queries": document_search_queries(query, context),
        "monitoring_suggestions": monitoring_suggestions(query, context, mode),
        "domain_intelligence": domain_intelligence(query, evidence) if mode in {"domain", "company"} or ("." in query and " " not in query) else {},
        "username_summary": {
            "confirmed": sum(1 for p in username_profiles if p.status == "confirmed"),
            "possible": sum(1 for p in username_profiles if p.status == "possible"),
            "unavailable": sum(1 for p in username_profiles if p.status == "unavailable"),
            "error": sum(1 for p in username_profiles if p.status == "error"),
        },
    }
    findings["advanced"] = advanced
    return findings
