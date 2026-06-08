from __future__ import annotations

import re
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .config import settings
from .models import Evidence, UsernameProfile
from .utils import domain_from_url, normalize_text, unique_keep_order

SOCIAL_DOMAINS = {
    "github.com": "GitHub",
    "gitlab.com": "GitLab",
    "linkedin.com": "LinkedIn",
    "instagram.com": "Instagram",
    "x.com": "X/Twitter",
    "twitter.com": "X/Twitter",
    "facebook.com": "Facebook",
    "tiktok.com": "TikTok",
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "threads.net": "Threads",
    "reddit.com": "Reddit",
    "medium.com": "Medium",
    "dev.to": "Dev.to",
    "kaggle.com": "Kaggle",
    "huggingface.co": "HuggingFace",
    "behance.net": "Behance",
    "dribbble.com": "Dribbble",
    "pinterest.com": "Pinterest",
    "soundcloud.com": "SoundCloud",
    "about.me": "About.me",
    "npmjs.com": "npm",
    "stackoverflow.com": "StackOverflow",
    "producthunt.com": "Product Hunt",
    "linktr.ee": "Linktree",
    "beacons.ai": "Beacons",
    "solo.to": "Solo.to",
    "carrd.co": "Carrd",
}

PLATFORM_WEIGHTS = {
    "GitHub": 90,
    "GitLab": 80,
    "LinkedIn": 88,
    "Instagram": 75,
    "X/Twitter": 72,
    "Facebook": 70,
    "TikTok": 68,
    "YouTube": 78,
    "Threads": 62,
    "Reddit": 64,
    "Medium": 72,
    "Dev.to": 75,
    "Kaggle": 74,
    "HuggingFace": 75,
    "Behance": 72,
    "Dribbble": 72,
    "Pinterest": 55,
    "SoundCloud": 55,
    "About.me": 64,
    "npm": 72,
    "StackOverflow": 72,
    "Product Hunt": 64,
    "Linktree": 58,
    "Beacons": 58,
    "Solo.to": 58,
    "Carrd": 55,
}

NOISE_PATH_PARTS = {
    "share", "intent", "sharer", "privacy", "terms", "help", "about", "explore", "search", "hashtag", "login",
    "signup", "accounts", "oauth", "plugins", "widgets", "policy", "developer", "developers"
}

TOPIC_HINTS = {
    "tech": ["python", "github", "software", "developer", "api", "code", "program", "ai", "machine learning", "app", "web"],
    "business": ["startup", "founder", "business", "marketing", "sales", "company", "ceo", "product"],
    "media": ["news", "journalism", "press", "video", "instagram", "youtube", "content", "reels", "tiktok"],
    "education": ["school", "university", "student", "gimnázium", "college", "education", "tanuló", "diák"],
    "design": ["design", "portfolio", "behance", "dribbble", "ui", "ux", "creative"],
}

@dataclass
class SocialProfileIntel:
    platform: str
    url: str
    status: str = "unknown"
    confidence: str = "low"
    score: int = 0
    title: str = ""
    bio: str = ""
    username: str = ""
    image: str = ""
    external_links: list[str] = field(default_factory=list)
    activity_hints: list[str] = field(default_factory=list)
    audience_hints: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    visibility_flags: list[str] = field(default_factory=list)
    reason: list[str] = field(default_factory=list)
    http_status: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _canonical_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    parsed = urlparse(url if url.startswith(("http://", "https://")) else "https://" + url)
    scheme = parsed.scheme or "https"
    host = parsed.netloc.lower().replace("www.", "")
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return f"{scheme}://{host}{path}"


def social_platform(url: str) -> str | None:
    d = domain_from_url(url).replace("www.", "")
    for dom, platform in SOCIAL_DOMAINS.items():
        if d == dom or d.endswith("." + dom):
            return platform
    return None


def _username_from_social_url(url: str, platform: str) -> str:
    p = urlparse(url)
    path = [x for x in p.path.split("/") if x]
    if not path:
        return ""
    if platform in {"Instagram", "TikTok", "Threads"}:
        return path[0].lstrip("@")
    if platform == "YouTube":
        if path[0].startswith("@"):
            return path[0].lstrip("@")
        if path[0].lower() in {"c", "channel", "user"} and len(path) > 1:
            return path[1]
    if platform == "Reddit" and path[0].lower() == "user" and len(path) > 1:
        return path[1]
    if platform == "Medium" and path[0].startswith("@"):
        return path[0].lstrip("@")
    if platform == "npm" and path[0] == "~" and len(path) > 1:
        return path[1]
    if path[0].lower() in NOISE_PATH_PARTS:
        return ""
    return path[0].lstrip("@")


def is_probably_profile_url(url: str) -> bool:
    platform = social_platform(url)
    if not platform:
        return False
    u = _canonical_url(url)
    p = urlparse(u)
    segments = [x.lower() for x in p.path.split("/") if x]
    if not segments:
        return False
    if any(seg in NOISE_PATH_PARTS for seg in segments[:2]):
        return False
    if platform == "YouTube":
        return segments[0].startswith("@") or segments[0] in {"c", "channel", "user"}
    if platform == "Reddit":
        return len(segments) >= 2 and segments[0] == "user"
    if platform in {"GitHub", "GitLab", "Instagram", "TikTok", "Threads", "LinkedIn", "Facebook", "X/Twitter", "Medium", "Dev.to", "Kaggle", "HuggingFace", "Behance", "Dribbble", "Pinterest", "SoundCloud", "About.me", "npm", "StackOverflow", "Product Hunt", "Linktree", "Beacons", "Solo.to", "Carrd"}:
        return bool(_username_from_social_url(u, platform))
    return False


def collect_social_urls(evidence: list[Evidence], username_profiles: list[UsernameProfile] | None = None, limit: int = 80) -> list[str]:
    urls: list[str] = []
    for p in username_profiles or []:
        if p.status in {"confirmed", "possible"} and is_probably_profile_url(p.url):
            urls.append(_canonical_url(p.url))
    for ev in evidence:
        for u in ev.social_profiles:
            if is_probably_profile_url(u):
                urls.append(_canonical_url(u))
        # Sometimes the result itself is a social profile.
        if is_probably_profile_url(ev.url):
            urls.append(_canonical_url(ev.url))
    return unique_keep_order([u for u in urls if u])[:limit]


def _fetch_profile(url: str) -> tuple[int | None, str]:
    try:
        resp = requests.get(
            url,
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": settings.user_agent, "Accept-Language": "hu,en;q=0.8"},
            allow_redirects=True,
        )
        ct = resp.headers.get("content-type", "").lower()
        if "text/html" not in ct and "text/plain" not in ct:
            return resp.status_code, ""
        return resp.status_code, resp.text[: settings.max_download_bytes]
    except requests.RequestException:
        return None, ""


def _meta(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return normalize_text(str(tag.get("content")))
    return ""


def _extract_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    links: list[str] = []
    base_host = domain_from_url(base_url)
    for a in soup.find_all("a", href=True):
        href = str(a.get("href") or "")
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        absolute = _canonical_url(urljoin(base_url, href))
        if not absolute:
            continue
        host = domain_from_url(absolute)
        if host and host != base_host and len(absolute) < 180:
            links.append(absolute)
    return unique_keep_order(links)[:20]


def _extract_activity_hints(text: str) -> list[str]:
    hints: list[str] = []
    t = text.lower()
    patterns = [
        (r"\b\d[\d,.\s]{0,8}\s*(followers?|követő|subscribers?|feliratkozó)", "audience_count_visible"),
        (r"\b\d[\d,.\s]{0,8}\s*(following|követés)", "following_count_visible"),
        (r"\b\d[\d,.\s]{0,8}\s*(posts?|bejegyzés|videos?|videó)", "content_count_visible"),
        (r"joined\s+\w+\s+\d{4}|csatlakozott", "join_date_hint"),
        (r"verified|hitelesített", "verification_hint"),
        (r"last active|utolsó aktivitás|recently", "activity_recency_hint"),
    ]
    for pat, label in patterns:
        if re.search(pat, t, re.I):
            hints.append(label)
    return unique_keep_order(hints)


def _extract_audience_hints(text: str) -> list[str]:
    found = []
    for m in re.finditer(r"\b\d[\d,.\s]{0,8}\s*(followers?|követő|subscribers?|feliratkozó|following|követés|posts?|bejegyzés|videos?|videó)\b", text, re.I):
        found.append(normalize_text(m.group(0)))
    return unique_keep_order(found)[:8]


def _extract_topics(text: str) -> list[str]:
    t = text.lower()
    scores = Counter()
    for topic, words in TOPIC_HINTS.items():
        for w in words:
            if w in t:
                scores[topic] += 1
    return [k for k, _ in scores.most_common(6)]


def _visibility_flags(platform: str, title: str, bio: str, links: list[str], activity: list[str]) -> list[str]:
    flags = []
    text = (title + " " + bio).lower()
    if any(x in text for x in ["email", "contact", "kapcsolat", "dm", "business inquiries"]):
        flags.append("contact_surface_visible")
    if len(links) >= 3:
        flags.append("many_external_links")
    if "audience_count_visible" in activity:
        flags.append("audience_size_visible")
    if platform in {"Instagram", "TikTok", "X/Twitter", "Facebook", "Threads"}:
        flags.append("consumer_social_profile")
    if platform in {"GitHub", "GitLab", "Dev.to", "Kaggle", "HuggingFace", "npm", "StackOverflow"}:
        flags.append("technical_profile")
    return unique_keep_order(flags)


def _score_social_profile(platform: str, status: int | None, username: str, title: str, bio: str, url: str, query: str, context: str) -> tuple[int, str, list[str]]:
    score = PLATFORM_WEIGHTS.get(platform, 50)
    reasons = ["known_social_platform"]
    text = f"{title} {bio} {url}".lower()
    q_terms = [x.lower() for x in re.split(r"\s+", query.strip(' \"')) if len(x) >= 3]
    ctx_terms = [x.lower() for x in re.split(r"\s+", context.strip()) if len(x) >= 3]

    if status == 200:
        score += 10; reasons.append("http_200")
    elif status in {401, 403, 429}:
        score += 4; reasons.append("platform_limited_manual_verify")
    elif status == 404:
        score -= 35; reasons.append("not_found")
    elif status is None:
        score -= 8; reasons.append("fetch_failed")

    if username and username.lower() in text:
        score += 8; reasons.append("username_visible")
    if q_terms and all(t in text for t in q_terms[:3]):
        score += 14; reasons.append("query_terms_visible")
    elif q_terms and any(t in text for t in q_terms):
        score += 5; reasons.append("partial_query_terms_visible")
    if ctx_terms and any(t in text for t in ctx_terms):
        score += 8; reasons.append("context_visible")
    if bio:
        score += 4; reasons.append("bio_or_meta_description")

    score = max(0, min(100, score))
    if score >= 80:
        conf = "high"
    elif score >= 62:
        conf = "medium"
    elif score >= 42:
        conf = "low"
    else:
        conf = "very_low"
    return score, conf, unique_keep_order(reasons)


def analyze_social_profile(url: str, query: str = "", context: str = "") -> SocialProfileIntel:
    canonical = _canonical_url(url)
    platform = social_platform(canonical) or "Unknown"
    username = _username_from_social_url(canonical, platform)
    status, html = _fetch_profile(canonical)

    title = ""
    bio = ""
    image = ""
    links: list[str] = []
    activity: list[str] = []
    audience: list[str] = []
    topics: list[str] = []

    if html:
        soup = BeautifulSoup(html, "html.parser")
        title = normalize_text((_meta(soup, "og:title", "twitter:title") or (soup.title.text if soup.title else ""))[:240])
        bio = normalize_text((_meta(soup, "og:description", "description", "twitter:description") or "")[:700])
        image = _meta(soup, "og:image", "twitter:image")
        links = _extract_links(soup, canonical)
        page_text = normalize_text(soup.get_text(" ")[:12000])
        combined = f"{title} {bio} {page_text}"
        activity = _extract_activity_hints(combined)
        audience = _extract_audience_hints(combined)
        topics = _extract_topics(combined)
    else:
        title = f"{platform} profile: @{username}" if username else canonical

    score, conf, reasons = _score_social_profile(platform, status, username, title, bio, canonical, query, context)
    return SocialProfileIntel(
        platform=platform,
        url=canonical,
        status="reachable" if status == 200 else ("limited" if status in {401, 403, 429} else "manual_verify"),
        confidence=conf,
        score=score,
        title=title,
        bio=bio,
        username=username,
        image=image,
        external_links=links[:12],
        activity_hints=activity,
        audience_hints=audience,
        topics=topics,
        visibility_flags=_visibility_flags(platform, title, bio, links, activity),
        reason=reasons,
        http_status=status,
    )


def analyze_social_profiles(evidence: list[Evidence], username_profiles: list[UsernameProfile] | None, query: str, context: str = "", max_profiles: int = 30, delay: float = 0.35) -> dict:
    urls = collect_social_urls(evidence, username_profiles, limit=max_profiles)
    profiles: list[SocialProfileIntel] = []
    for url in urls[:max_profiles]:
        if not is_probably_profile_url(url):
            continue
        profiles.append(analyze_social_profile(url, query=query, context=context))
        time.sleep(delay)

    platform_counts = Counter(p.platform for p in profiles)
    confidence_counts = Counter(p.confidence for p in profiles)
    topic_counts = Counter(t for p in profiles for t in p.topics)
    flag_counts = Counter(f for p in profiles for f in p.visibility_flags)
    top_profiles = sorted(profiles, key=lambda p: (p.score, p.platform), reverse=True)

    return {
        "profiles": [p.to_dict() for p in top_profiles],
        "platform_counts": dict(platform_counts.most_common()),
        "confidence_counts": dict(confidence_counts.most_common()),
        "topic_counts": dict(topic_counts.most_common(12)),
        "visibility_flags": dict(flag_counts.most_common(12)),
        "summary": {
            "total_profiles": len(profiles),
            "high_or_medium": sum(1 for p in profiles if p.confidence in {"high", "medium"}),
            "technical_profiles": sum(1 for p in profiles if "technical_profile" in p.visibility_flags),
            "consumer_profiles": sum(1 for p in profiles if "consumer_social_profile" in p.visibility_flags),
            "profiles_with_bio": sum(1 for p in profiles if p.bio),
            "profiles_with_external_links": sum(1 for p in profiles if p.external_links),
        },
    }
