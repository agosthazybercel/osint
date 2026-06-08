from __future__ import annotations

import hashlib
import re
from html import escape
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse, urlunparse


def normalize_text(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def domain_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def root_domain(domain: str) -> str:
    parts = domain.lower().split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else domain.lower()


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    parsed = urlparse(url)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc.lower().replace("www.", "")
    path = parsed.path.rstrip("/") or "/"
    query_pairs = parse_qs(parsed.query)
    for noisy in ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"]:
        query_pairs.pop(noisy, None)
    clean_query = "&".join(f"{quote_plus(k)}={quote_plus(v[0])}" for k, v in sorted(query_pairs.items()) if v)
    return urlunparse((scheme, netloc, path, "", clean_query, ""))


def absolute_url(base_url: str, maybe_url: str) -> str:
    try:
        return urljoin(base_url, maybe_url)
    except Exception:
        return maybe_url


def stable_id(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()[:14]


def content_hash(text: str) -> str:
    normalized = normalize_text((text or "")[:5000]).lower()
    return hashlib.sha256(normalized.encode("utf-8", errors="ignore")).hexdigest()[:16]


def html_escape(text: str | None) -> str:
    return escape(text or "")


def unique_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        item = normalize_text(str(item))
        if not item:
            continue
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def maybe_unwrap_search_url(url: str) -> str:
    """Unwrap common redirect URLs used by search engines."""
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        for key in ["url", "u", "q"]:
            if key in qs and qs[key]:
                candidate = unquote(qs[key][0])
                if candidate.startswith("http"):
                    return candidate
    except Exception:
        pass
    return url


def looks_like_email(value: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value or ""))


def looks_like_phone(value: str) -> bool:
    digits = re.sub(r"\D", "", value or "")
    return 7 <= len(digits) <= 16


def safe_filename(text: str, fallback: str = "report") -> str:
    clean = re.sub(r"[^\w\-.]+", "_", text, flags=re.UNICODE).strip("_")
    return clean[:80] or fallback
