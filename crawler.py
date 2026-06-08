from __future__ import annotations

import mimetypes
import re
from pathlib import Path

import requests
try:
    import trafilatura  # type: ignore
except Exception:  # pragma: no cover
    trafilatura = None  # type: ignore
from bs4 import BeautifulSoup

from .config import settings
from .models import MediaItem
from .utils import absolute_url, domain_from_url, normalize_text, stable_id, unique_keep_order

try:
    from pypdf import PdfReader  # type: ignore
except Exception:  # pragma: no cover
    PdfReader = None  # type: ignore


class FetchResult:
    def __init__(self, url: str, final_url: str, status_code: int, content_type: str, text: str, raw: bytes | None = None):
        self.url = url
        self.final_url = final_url
        self.status_code = status_code
        self.content_type = content_type
        self.text = text
        self.raw = raw


SESSION = requests.Session()
SESSION.headers.update({"User-Agent": settings.user_agent})

SOCIAL_DOMAINS = {
    "linkedin.com", "facebook.com", "instagram.com", "x.com", "twitter.com", "tiktok.com",
    "github.com", "gitlab.com", "youtube.com", "medium.com", "reddit.com", "pinterest.com",
    "threads.net", "mastodon.social", "soundcloud.com", "behance.net", "dribbble.com",
    "kaggle.com", "huggingface.co", "dev.to", "npmjs.com", "stackoverflow.com", "about.me",
}

VIDEO_DOMAINS = {"youtube.com", "youtu.be", "vimeo.com", "tiktok.com", "dailymotion.com", "twitch.tv"}


def _cache_path(url: str) -> Path:
    return settings.cache_dir / f"http_{stable_id(url)}.txt"


def fetch_url(url: str) -> FetchResult | None:
    cache_path = _cache_path(url)
    if settings.enable_http_cache and cache_path.exists():
        try:
            cached = cache_path.read_text(encoding="utf-8", errors="ignore")
            header, body = cached.split("\n\n", 1)
            parts = dict(line.split(": ", 1) for line in header.splitlines() if ": " in line)
            return FetchResult(url, parts.get("final_url", url), int(parts.get("status_code", "200")), parts.get("content_type", "text/html"), body)
        except Exception:
            pass

    try:
        resp = SESSION.get(url, timeout=settings.request_timeout_seconds, allow_redirects=True, stream=True)
        status = resp.status_code
        ctype = resp.headers.get("content-type", "").lower()
        if status >= 400:
            return None

        raw = resp.raw.read(settings.max_download_bytes + 1, decode_content=True)
        if len(raw) > settings.max_download_bytes:
            return None

        text = ""
        if "application/pdf" in ctype or url.lower().endswith(".pdf"):
            text = extract_pdf_text(raw)
        elif "text/html" in ctype or "text/plain" in ctype or not ctype:
            resp.encoding = resp.encoding or "utf-8"
            text = raw.decode(resp.encoding, errors="ignore")
        else:
            return None

        result = FetchResult(url, resp.url, status, ctype, text, raw)
        if settings.enable_http_cache and text:
            try:
                cache_path.write_text(
                    f"final_url: {resp.url}\nstatus_code: {status}\ncontent_type: {ctype}\n\n{text}",
                    encoding="utf-8",
                    errors="ignore",
                )
            except Exception:
                pass
        return result
    except requests.RequestException:
        return None


def extract_pdf_text(raw: bytes) -> str:
    if PdfReader is None:
        return ""
    try:
        import io
        reader = PdfReader(io.BytesIO(raw))
        pages = []
        for page in reader.pages[:20]:
            pages.append(page.extract_text() or "")
        return normalize_text("\n".join(pages))
    except Exception:
        return ""


def extract_title(html: str) -> str:
    try:
        soup = BeautifulSoup(html, "html.parser")
        if soup.title and soup.title.text:
            return normalize_text(soup.title.text)
        h1 = soup.find("h1")
        if h1:
            return normalize_text(h1.get_text(" "))
    except Exception:
        pass
    return ""


def extract_text(html_or_text: str, url: str = "") -> str:
    if not html_or_text:
        return ""
    # PDF text has no HTML tags.
    if "<html" not in html_or_text.lower() and "</" not in html_or_text[:1000].lower():
        return normalize_text(html_or_text)[: settings.max_text_chars_per_page]
    if trafilatura is not None:
        try:
            extracted = trafilatura.extract(
                html_or_text,
                url=url,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
            )
            if extracted:
                return normalize_text(extracted)[: settings.max_text_chars_per_page]
        except Exception:
            pass
    try:
        soup = BeautifulSoup(html_or_text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
            tag.decompose()
        return normalize_text(soup.get_text(" "))[: settings.max_text_chars_per_page]
    except Exception:
        return ""


def extract_links(html: str, base_url: str) -> list[str]:
    if not html or "<" not in html:
        return []
    try:
        soup = BeautifulSoup(html, "html.parser")
        links = []
        for a in soup.find_all("a", href=True):
            href = absolute_url(base_url, a.get("href", ""))
            if href.startswith("http"):
                links.append(href)
        return unique_keep_order(links)
    except Exception:
        return []


def extract_media(html: str, base_url: str) -> list[MediaItem]:
    if not html or "<" not in html:
        return []
    media: list[MediaItem] = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or img.get("data-original")
            if not src:
                continue
            url = absolute_url(base_url, src)
            if url.startswith("http"):
                media.append(MediaItem(type="image", url=url, source_page=base_url, alt=normalize_text(img.get("alt", ""))))
        for meta in soup.find_all("meta"):
            prop = (meta.get("property") or meta.get("name") or "").lower()
            content = meta.get("content") or ""
            if not content:
                continue
            if prop in {"og:image", "twitter:image"}:
                media.append(MediaItem(type="image", url=absolute_url(base_url, content), source_page=base_url, alt=prop))
            if prop in {"og:video", "twitter:player"}:
                media.append(MediaItem(type="video", url=absolute_url(base_url, content), source_page=base_url, alt=prop))
        for video in soup.find_all(["video", "source", "iframe"]):
            src = video.get("src")
            if src:
                media.append(MediaItem(type="video", url=absolute_url(base_url, src), source_page=base_url, alt="embedded video"))
    except Exception:
        pass

    dedup = []
    seen = set()
    for item in media:
        if item.url and item.url not in seen:
            seen.add(item.url)
            dedup.append(item)
    return dedup[:60]


def find_social_urls(urls: list[str]) -> list[str]:
    found = []
    for url in urls:
        d = domain_from_url(url)
        if any(d == sd or d.endswith("." + sd) for sd in SOCIAL_DOMAINS):
            found.append(url.split("?", 1)[0].rstrip("/"))
    return unique_keep_order(found)


def find_video_urls(urls: list[str]) -> list[str]:
    found = []
    for url in urls:
        d = domain_from_url(url)
        if any(d == vd or d.endswith("." + vd) for vd in VIDEO_DOMAINS):
            found.append(url.split("?", 1)[0].rstrip("/"))
    return unique_keep_order(found)
