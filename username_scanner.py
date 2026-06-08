from __future__ import annotations

import re
import time

import requests

from .config import settings
from .models import SearchHit, UsernameProfile
from .utils import domain_from_url, normalize_url

PLATFORMS: dict[str, str] = {
    "GitHub": "https://github.com/{username}",
    "GitLab": "https://gitlab.com/{username}",
    "Reddit": "https://www.reddit.com/user/{username}",
    "Medium": "https://medium.com/@{username}",
    "Dev.to": "https://dev.to/{username}",
    "Kaggle": "https://www.kaggle.com/{username}",
    "HuggingFace": "https://huggingface.co/{username}",
    "npm": "https://www.npmjs.com/~{username}",
    "Pinterest": "https://www.pinterest.com/{username}/",
    "TikTok": "https://www.tiktok.com/@{username}",
    "Instagram": "https://www.instagram.com/{username}/",
    "X/Twitter": "https://x.com/{username}",
    "YouTube": "https://www.youtube.com/@{username}",
    "Threads": "https://www.threads.net/@{username}",
    "SoundCloud": "https://soundcloud.com/{username}",
    "Behance": "https://www.behance.net/{username}",
    "Dribbble": "https://dribbble.com/{username}",
    "About.me": "https://about.me/{username}",
}


def looks_like_username(query: str) -> bool:
    return bool(re.fullmatch(r"@?[A-Za-z0-9_.\-]{3,32}", query.strip()))


def normalize_username(query: str) -> str:
    return query.strip().lstrip("@")


def scan_username(username: str, timeout: int | None = None, delay: float = 0.2, max_platforms: int | None = None) -> list[UsernameProfile]:
    username = normalize_username(username)
    if not looks_like_username(username):
        return []
    timeout = timeout or settings.request_timeout_seconds
    profiles: list[UsernameProfile] = []
    session = requests.Session()
    session.headers.update({"User-Agent": settings.user_agent})

    items = list(PLATFORMS.items())[:max_platforms] if max_platforms else list(PLATFORMS.items())
    for platform, template in items:
        url = template.format(username=username)
        try:
            resp = session.get(url, timeout=timeout, allow_redirects=True)
            status = resp.status_code
            text_l = (resp.text or "")[:5000].lower()
            if status == 200:
                if "not found" in text_l or "page not found" in text_l or "user not found" in text_l:
                    status_label = "possible"
                    note = "HTTP 200 but page contains not-found wording; verify manually."
                else:
                    status_label = "confirmed"
                    note = "Public profile page responded with HTTP 200."
            elif status in {301, 302, 303, 307, 308}:
                status_label = "possible"
                note = "Redirected; verify manually."
            elif status in {401, 403, 429}:
                status_label = "possible"
                note = f"HTTP {status}; platform blocked automated check, manual verification needed."
            elif status == 404:
                status_label = "unavailable"
                note = "HTTP 404."
            else:
                status_label = "possible"
                note = f"HTTP {status}; verify manually."
            profiles.append(UsernameProfile(platform=platform, url=normalize_url(url), status=status_label, http_status=status, note=note))
        except requests.RequestException as exc:
            profiles.append(UsernameProfile(platform=platform, url=normalize_url(url), status="error", http_status=None, note=str(exc)[:160]))
        time.sleep(delay)
    return profiles


def username_profiles_to_hits(profiles: list[UsernameProfile], username: str) -> list[SearchHit]:
    hits: list[SearchHit] = []
    for i, profile in enumerate(profiles, start=1):
        if profile.status in {"confirmed", "possible"}:
            hits.append(
                SearchHit(
                    title=f"{profile.platform} profile for @{username}",
                    url=profile.url,
                    snippet=f"Direct username scan result: {profile.status}. {profile.note}",
                    source=domain_from_url(profile.url),
                    provider="direct_username",
                    query_used=f"@{username}",
                    rank=i,
                )
            )
    return hits
