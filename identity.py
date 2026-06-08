from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .models import MediaItem
from .utils import domain_from_url, normalize_text, unique_keep_order

STOP_PERSON_TOKENS = {
    "dr", "mr", "mrs", "ms", "prof", "ifj", "id", "junior", "senior", "jr", "sr",
}

ORG_CONTEXT_WORDS = {
    "gimnazium", "gimn", "school", "iskola", "egyetem", "university", "college", "academy",
    "kft", "zrt", "bt", "ltd", "llc", "inc", "company", "foundation", "association",
    "budapest", "hungary", "magyarorszag", "piarista", "factpress", "nova", "press",
}

NOISE_DOMAINS = {
    "gstatic.com", "googleusercontent.com", "ggpht.com", "doubleclick.net", "googlesyndication.com",
    "google-analytics.com", "gravatar.com", "cloudfront.net", "akamaihd.net", "appspot.com",
    "apple.com", "apps.apple.com", "play.google.com", "pinterest.com", "pinimg.com", "ytimg.com",
}

LOW_SIGNAL_DOMAINS = {
    "facebook.com", "instagram.com", "x.com", "twitter.com", "tiktok.com", "linkedin.com",
    "youtube.com", "youtu.be", "reddit.com", "pinterest.com",
}

PROFILE_DOMAINS = {
    "github.com", "gitlab.com", "linkedin.com", "medium.com", "about.me", "dev.to", "kaggle.com",
    "huggingface.co", "stackoverflow.com", "behance.net", "dribbble.com", "youtube.com",
    "instagram.com", "facebook.com", "x.com", "twitter.com", "threads.net",
}

NOISE_IMAGE_PATTERNS = (
    "logo", "icon", "sprite", "avatar_default", "placeholder", "blank", "transparent", "tracking", "pixel",
    "favicon", "apple-touch-icon", "android-chrome", "app-store", "google-play", "badge", "button",
    "ads", "adservice", "doubleclick", "analytics", "share", "social", "loader", "spinner", "lazy",
)

SOCIAL_PLATFORM_PATH_BLOCKLIST = {
    "home", "about", "contact", "contacts", "login", "logout", "share", "watch", "posts", "post", "reel", "reels",
    "status", "explore", "search", "hashtag", "privacy", "terms", "help", "support", "company", "jobs",
}


@dataclass
class QueryProfile:
    raw_query: str
    mode: str
    target_text: str
    context_text: str = ""
    target_tokens: list[str] = field(default_factory=list)
    context_tokens: list[str] = field(default_factory=list)
    quoted_phrases: list[str] = field(default_factory=list)
    username: str = ""
    email: str = ""
    phone_digits: str = ""

    @property
    def display_query(self) -> str:
        if self.context_text and self.context_text.lower() not in self.target_text.lower():
            return f"{self.target_text} — {self.context_text}"
        return self.target_text or self.raw_query


def strip_accents(text: str) -> str:
    text = text or ""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def norm(text: str) -> str:
    text = strip_accents(text or "").lower()
    text = re.sub(r"[^a-z0-9@.+_\-\s]", " ", text)
    return normalize_text(text)


def query_tokens(query: str) -> list[str]:
    q = norm(query)
    toks = [t for t in q.split() if len(t) >= 3 and t not in STOP_PERSON_TOKENS]
    return unique_keep_order(toks)


def looks_like_person_name(query: str) -> bool:
    raw = query.strip().strip('"')
    if "@" in raw or re.search(r"https?://|www\.|\d", raw, re.I):
        return False
    parts = [p for p in re.split(r"\s+", raw) if p]
    if not (2 <= len(parts) <= 4):
        return False
    if any(norm(p) in ORG_CONTEXT_WORDS for p in parts):
        return False
    return all(re.match(r"^[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű\-']{2,}$", p) for p in parts)


def _quoted_phrases(query: str) -> list[str]:
    return [normalize_text(x) for x in re.findall(r'"([^"]+)"', query or "") if normalize_text(x)]


def _split_name_context(query: str, mode: str, explicit_context: str = "") -> tuple[str, str, list[str]]:
    raw = normalize_text(query.strip())
    quotes = _quoted_phrases(raw)
    if quotes and mode in {"person", "general"}:
        target = quotes[0]
        rest = raw
        for q in quotes:
            rest = rest.replace(f'"{q}"', " ")
        context = normalize_text(" ".join([rest, explicit_context]))
        return target, context, quotes

    if mode not in {"person", "general"}:
        return raw, explicit_context.strip(), quotes

    parts = [p for p in raw.split() if p]
    if len(parts) <= 2:
        return raw, explicit_context.strip(), quotes

    norm_parts = [norm(p) for p in parts]
    # If the query contains an obvious organization/city/context word after the first two tokens,
    # treat the first two tokens as the identity and the rest as disambiguation context.
    context_start = None
    for i, p in enumerate(norm_parts[2:], start=2):
        if p in ORG_CONTEXT_WORDS or any(w in p for w in ORG_CONTEXT_WORDS):
            context_start = i
            break
    if context_start is not None:
        target = " ".join(parts[:context_start])
        context = normalize_text(" ".join(parts[context_start:] + ([explicit_context] if explicit_context else [])))
        return target, context, quotes

    # Hungarian/international names are most often two tokens in this use case. If there are 3+ capitalized
    # tokens and no explicit context, keep up to 3 name-like tokens, then make the rest context.
    if 3 <= len(parts) <= 5:
        name_len = 3 if len(parts) == 3 and looks_like_person_name(raw) else 2
        target = " ".join(parts[:name_len])
        context = normalize_text(" ".join(parts[name_len:] + ([explicit_context] if explicit_context else [])))
        return target, context, quotes

    return raw, explicit_context.strip(), quotes


def build_query_profile(query: str, mode: str, context: str = "") -> QueryProfile:
    raw = normalize_text(query.strip())
    target, ctx, quotes = _split_name_context(raw, mode, explicit_context=context)
    n_target = norm(target)
    email = raw if "@" in raw and "." in raw else ""
    phone_digits = re.sub(r"\D", "", raw) if re.search(r"\d", raw) else ""
    username = ""
    if mode == "username" or re.fullmatch(r"@?[A-Za-z0-9_.\-]{3,32}", raw):
        username = raw.lstrip("@")
    return QueryProfile(
        raw_query=raw,
        mode=mode,
        target_text=target,
        context_text=ctx,
        target_tokens=query_tokens(target),
        context_tokens=[t for t in query_tokens(ctx) if t not in query_tokens(target)][:12],
        quoted_phrases=quotes,
        username=username,
        email=email,
        phone_digits=phone_digits,
    )


def contains_exact_phrase(query: str, text: str) -> bool:
    return bool(norm(query)) and norm(query) in norm(text)


def token_coverage(tokens_or_query, text: str) -> float:
    tokens = tokens_or_query if isinstance(tokens_or_query, list) else query_tokens(str(tokens_or_query))
    if not tokens:
        return 0.0
    h = norm(text)
    matched = sum(1 for t in tokens if re.search(rf"\b{re.escape(t)}\b", h))
    return matched / len(tokens)


def proximity_bonus(tokens_or_query, text: str, max_gap_words: int = 8) -> float:
    tokens = tokens_or_query if isinstance(tokens_or_query, list) else query_tokens(str(tokens_or_query))
    if len(tokens) < 2:
        return 0.0
    words = norm(text).split()
    positions: dict[str, list[int]] = {t: [] for t in tokens}
    for i, w in enumerate(words[:3500]):
        if w in positions:
            positions[w].append(i)
    if not all(positions.values()):
        return 0.0
    best = None
    # scan around first token positions; this keeps it fast and favors real phrase occurrences
    for pos in positions[tokens[0]][:80]:
        span_positions = [pos]
        for t in tokens[1:]:
            nearest = min(positions[t], key=lambda p: abs(p - pos))
            span_positions.append(nearest)
        span = max(span_positions) - min(span_positions)
        if best is None or span < best:
            best = span
    if best is None:
        return 0.0
    if best <= max_gap_words:
        return 10.0
    if best <= 20:
        return 5.0
    if best <= 40:
        return 2.0
    return 0.0


def rootish_domain(url_or_domain: str) -> str:
    d = domain_from_url(url_or_domain) or url_or_domain.lower().replace("www.", "")
    parts = d.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return d


def source_quality(url: str) -> tuple[float, list[str]]:
    d = domain_from_url(url)
    rd = rootish_domain(d)
    score = 0.0
    reasons: list[str] = []
    if rd in PROFILE_DOMAINS:
        score += 2.0; reasons.append("profile_domain")
    if d.endswith((".edu", ".gov", ".org", ".hu")):
        score += 1.0; reasons.append("institutional_or_local_domain")
    if rd in NOISE_DOMAINS or any(d == nd or d.endswith("." + nd) for nd in NOISE_DOMAINS):
        score -= 10.0; reasons.append("noise_domain")
    if any(x in url.lower() for x in ("/search?", "?q=", "/tag/", "/tags/", "/hashtag/", "/category/")):
        score -= 3.0; reasons.append("search_or_listing_page")
    return score, reasons


def identity_score(query: str, title: str, snippet: str, text: str, url: str, mode: str, context: str = "") -> tuple[float, list[str]]:
    profile = build_query_profile(query, mode, context)
    return identity_score_profile(profile, title, snippet, text, url)


def identity_score_profile(profile: QueryProfile, title: str, snippet: str, text: str, url: str) -> tuple[float, list[str]]:
    full_text = " ".join([title or "", snippet or "", text[:16000] or "", url or ""])
    short_text = " ".join([title or "", snippet or "", text[:5000] or "", url or ""])
    n_target = norm(profile.target_text)
    n_title, n_snip, n_text, n_url = norm(title), norm(snippet), norm(text[:12000]), norm(url)
    score = 0.0
    reasons: list[str] = []

    if profile.mode == "email" and profile.email:
        if norm(profile.email) in norm(full_text):
            score += 24; reasons.append("exact_email")
        return round(score, 2), reasons

    if profile.mode == "phone" and profile.phone_digits:
        all_digits = re.sub(r"\D", "", full_text)
        if profile.phone_digits and profile.phone_digits in all_digits:
            score += 24; reasons.append("exact_phone")
        return round(score, 2), reasons

    if profile.mode == "username" and profile.username:
        u = norm(profile.username)
        path = norm(urlparse(url).path.replace("/", " ").replace("_", " ").replace("-", " "))
        if re.search(rf"\b{re.escape(u)}\b", path):
            score += 16; reasons.append("username_in_profile_url")
        if re.search(rf"\b{re.escape(u)}\b", norm(title + " " + snippet)):
            score += 8; reasons.append("username_in_title_or_snippet")
        if re.search(rf"\b{re.escape(u)}\b", norm(text[:5000])):
            score += 5; reasons.append("username_in_text")

    # exact target/name phrase
    if n_target and n_target in n_title:
        score += 18; reasons.append("exact_title")
    if n_target and n_target in n_snip:
        score += 14; reasons.append("exact_snippet")
    if n_target and n_target in n_url.replace("-", " ").replace("_", " "):
        score += 14; reasons.append("exact_url")
    if n_target and n_target in n_text[:5000]:
        score += 12; reasons.append("exact_text")
    elif n_target and n_target in n_text:
        score += 7; reasons.append("exact_text_late")

    if profile.target_tokens:
        cov_title = token_coverage(profile.target_tokens, title)
        cov_snip = token_coverage(profile.target_tokens, snippet)
        cov_url = token_coverage(profile.target_tokens, url.replace("-", " ").replace("_", " "))
        cov_text = token_coverage(profile.target_tokens, text[:10000])
        if cov_title == 1:
            score += 12; reasons.append("all_name_tokens_title")
        if cov_snip == 1:
            score += 10; reasons.append("all_name_tokens_snippet")
        if cov_url == 1:
            score += 9; reasons.append("all_name_tokens_url")
        if cov_text == 1:
            score += 7; reasons.append("all_name_tokens_text")
        score += max(cov_title, cov_snip, cov_url, cov_text) * 3

        prox = proximity_bonus(profile.target_tokens, short_text)
        if prox:
            score += prox; reasons.append("name_tokens_close")

    if profile.context_tokens:
        ctx_cov_title = token_coverage(profile.context_tokens, title)
        ctx_cov_snip = token_coverage(profile.context_tokens, snippet)
        ctx_cov_text = token_coverage(profile.context_tokens, text[:10000])
        ctx_score = max(ctx_cov_title * 6, ctx_cov_snip * 5, ctx_cov_text * 4)
        if ctx_score >= 2:
            score += ctx_score; reasons.append("context_match")

    qscore, qreasons = source_quality(url)
    score += qscore
    reasons.extend(qreasons)
    return round(score, 2), unique_keep_order(reasons)


def identity_pass(query: str, title: str, snippet: str, text: str, url: str, mode: str, context: str = "") -> tuple[bool, float, list[str]]:
    profile = build_query_profile(query, mode, context)
    return identity_pass_profile(profile, title, snippet, text, url)


def identity_pass_profile(profile: QueryProfile, title: str, snippet: str, text: str, url: str) -> tuple[bool, float, list[str]]:
    score, reasons = identity_score_profile(profile, title, snippet, text, url)
    person_like = profile.mode == "person" or (profile.mode == "general" and looks_like_person_name(profile.target_text))
    if "noise_domain" in reasons and not any(r.startswith("exact_") or r == "username_in_profile_url" for r in reasons):
        return False, score, reasons
    if profile.mode in {"email", "phone"}:
        return score >= 20, score, reasons
    if profile.mode == "username":
        return score >= 10 or "username_in_profile_url" in reasons, score, reasons
    if not person_like:
        return score >= 6 or any(r.startswith("exact_") for r in reasons), score, reasons

    strong_identity = any(r in reasons for r in (
        "exact_title", "exact_snippet", "exact_url", "all_name_tokens_title", "all_name_tokens_snippet",
        "all_name_tokens_url", "name_tokens_close"
    ))
    text_only_identity = any(r in reasons for r in ("exact_text", "all_name_tokens_text"))
    context_needed = bool(profile.context_tokens)
    context_ok = not context_needed or "context_match" in reasons or "exact_url" in reasons or "all_name_tokens_url" in reasons

    if strong_identity and score >= 14 and context_ok:
        return True, score, reasons
    if strong_identity and score >= 18:
        return True, score, reasons
    if text_only_identity and score >= 20 and context_ok:
        return True, score, reasons
    return False, score, reasons


def confidence_from_identity(score: float, reasons: list[str], mode: str) -> str:
    if not reasons:
        return "very_low"
    if score >= 32 and any(r in reasons for r in ("exact_title", "exact_snippet", "exact_url", "username_in_profile_url", "exact_email", "exact_phone")):
        return "high"
    if score >= 22:
        return "high"
    if score >= 14:
        return "medium"
    if score >= 8:
        return "low"
    return "very_low"


def evidence_window(profile: QueryProfile, title: str, snippet: str, text: str, radius: int = 900) -> str:
    """Return only text around the target tokens. This prevents unrelated page-wide names/images/emails
    from being treated as target-related findings."""
    source = normalize_text(" ".join([title or "", snippet or "", text or ""]))
    if not profile.target_tokens:
        return source[:4000]
    n_source = norm(source)
    # map normalized index to rough original index by searching exact/accentless target variants
    candidates = [profile.target_text, strip_accents(profile.target_text)] + profile.target_tokens
    windows: list[str] = []
    for cand in candidates:
        if not cand:
            continue
        c = norm(cand)
        for m in re.finditer(re.escape(c), n_source):
            # normalized and original are not perfectly aligned; this approximation is good enough for windowing.
            start = max(0, m.start() - radius)
            end = min(len(source), m.end() + radius)
            windows.append(source[start:end])
            if len(windows) >= 6:
                break
        if len(windows) >= 6:
            break
    if not windows:
        return " ".join([title, snippet])[:2500]
    return normalize_text(" ... ".join(windows))[:8000]


def is_social_profile_url_for_target(profile: QueryProfile, url: str) -> bool:
    d = rootish_domain(url)
    path = urlparse(url).path.strip("/")
    path_parts = [p for p in re.split(r"[/?#]", path) if p]
    if not path_parts:
        return False
    last = path_parts[-1].lstrip("@")
    if norm(last) in SOCIAL_PLATFORM_PATH_BLOCKLIST:
        return False
    path_norm = norm(path.replace("/", " ").replace("-", " ").replace("_", " "))
    if profile.username and norm(profile.username) in path_norm:
        return True
    if profile.target_tokens and any(t in path_norm for t in profile.target_tokens):
        return True
    return False


def filter_social_urls_for_identity(query: str, urls: list[str], mode: str, context: str = "") -> list[str]:
    profile = build_query_profile(query, mode, context)
    out = []
    for u in urls:
        d = rootish_domain(u)
        if d not in PROFILE_DOMAINS:
            continue
        if profile.mode == "person" or (profile.mode == "general" and looks_like_person_name(profile.target_text)) or profile.mode == "username":
            if not is_social_profile_url_for_target(profile, u):
                continue
        out.append(u.split("?", 1)[0].rstrip("/"))
    return unique_keep_order(out)[:30]


def is_noise_media(item: MediaItem) -> bool:
    url = (item.url or "").lower()
    alt = norm(item.alt or "")
    d = domain_from_url(url)
    rd = rootish_domain(d)
    if not url.startswith("http") or url.startswith("data:"):
        return True
    if ".svg" in url or url.endswith(".svg"):
        return True
    if any(pat in url or pat in alt for pat in NOISE_IMAGE_PATTERNS):
        return True
    if rd in NOISE_DOMAINS or any(d == bad or d.endswith("." + bad) for bad in NOISE_DOMAINS):
        return True
    return False


def media_relevance(query: str, item: MediaItem, source_title: str = "", source_text: str = "", context: str = "") -> float:
    profile = build_query_profile(query, "person" if looks_like_person_name(query) else "general", context)
    url_alt = " ".join([item.url or "", item.alt or ""])
    score = 0.0
    if contains_exact_phrase(profile.target_text, url_alt):
        score += 10
    score += token_coverage(profile.target_tokens, url_alt) * 8
    if (item.alt or "").lower() in {"og:image", "twitter:image"}:
        score += 3
    if token_coverage(profile.target_tokens, source_title) == 1:
        score += 3
    return score


def filter_media_for_identity(query: str, media: list[MediaItem], source_title: str, source_text: str, source_confidence: str, mode: str, context: str = "") -> list[MediaItem]:
    profile = build_query_profile(query, mode, context)
    person_like = profile.mode == "person" or (profile.mode == "general" and looks_like_person_name(profile.target_text))
    out: list[MediaItem] = []
    seen = set()
    for m in media:
        rel = media_relevance(profile.target_text, m, source_title, source_text, context)
        if is_noise_media(m) and rel < 9:
            continue
        if person_like:
            # For people, only keep media from high/medium pages, and prefer OG/article images or explicitly target-linked media.
            if source_confidence not in {"high", "medium"}:
                continue
            if rel < 3 and (m.alt or "").lower() not in {"og:image", "twitter:image"}:
                continue
        key = m.url.split("?", 1)[0]
        if key not in seen:
            seen.add(key)
            out.append(m)
    return out[:10]
