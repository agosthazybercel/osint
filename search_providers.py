from __future__ import annotations

import json
from typing import Iterable

import requests

from .config import settings
from .models import SearchHit
from .utils import domain_from_url, maybe_unwrap_search_url, normalize_text, normalize_url

try:
    from ddgs import DDGS  # type: ignore
except Exception:  # pragma: no cover
    try:
        from duckduckgo_search import DDGS  # type: ignore
    except Exception:  # pragma: no cover
        DDGS = None  # type: ignore


class SearchProviderError(RuntimeError):
    pass


def search_duckduckgo(query: str, max_results: int = 10) -> list[SearchHit]:
    if DDGS is None:
        raise SearchProviderError("DDGS/DuckDuckGo package is not installed. Run: pip install ddgs duckduckgo-search")

    hits: list[SearchHit] = []
    try:
        with DDGS() as ddgs:  # type: ignore
            for rank, row in enumerate(ddgs.text(query, max_results=max_results), start=1):
                url = row.get("href") or row.get("url") or ""
                url = normalize_url(maybe_unwrap_search_url(url))
                if not url:
                    continue
                hits.append(
                    SearchHit(
                        title=normalize_text(row.get("title", "")),
                        url=url,
                        snippet=normalize_text(row.get("body", "")),
                        source=domain_from_url(url),
                        provider="duckduckgo",
                        query_used=query,
                        rank=rank,
                    )
                )
    except Exception as exc:
        raise SearchProviderError(f"DuckDuckGo search failed: {exc}") from exc
    return hits


def search_brave(query: str, max_results: int = 10) -> list[SearchHit]:
    if not settings.brave_search_api_key:
        return []
    try:
        response = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": min(max_results, 20)},
            headers={"Accept": "application/json", "X-Subscription-Token": settings.brave_search_api_key},
            timeout=settings.request_timeout_seconds,
        )
        if response.status_code >= 400:
            raise SearchProviderError(f"Brave API HTTP {response.status_code}: {response.text[:200]}")
        data = response.json()
        hits = []
        for rank, row in enumerate(data.get("web", {}).get("results", [])[:max_results], start=1):
            url = normalize_url(row.get("url", ""))
            if not url:
                continue
            hits.append(
                SearchHit(
                    title=normalize_text(row.get("title", "")),
                    url=url,
                    snippet=normalize_text(row.get("description", "")),
                    source=domain_from_url(url),
                    provider="brave",
                    query_used=query,
                    rank=rank,
                )
            )
        return hits
    except SearchProviderError:
        raise
    except Exception as exc:
        raise SearchProviderError(f"Brave search failed: {exc}") from exc


def search_serpapi(query: str, max_results: int = 10) -> list[SearchHit]:
    if not settings.serpapi_key:
        return []
    try:
        response = requests.get(
            "https://serpapi.com/search.json",
            params={"q": query, "api_key": settings.serpapi_key, "num": max_results, "engine": "google"},
            timeout=settings.request_timeout_seconds,
        )
        if response.status_code >= 400:
            raise SearchProviderError(f"SerpAPI HTTP {response.status_code}: {response.text[:200]}")
        data = response.json()
        hits = []
        for rank, row in enumerate(data.get("organic_results", [])[:max_results], start=1):
            url = normalize_url(row.get("link", ""))
            if not url:
                continue
            hits.append(
                SearchHit(
                    title=normalize_text(row.get("title", "")),
                    url=url,
                    snippet=normalize_text(row.get("snippet", "")),
                    source=domain_from_url(url),
                    provider="serpapi",
                    query_used=query,
                    rank=rank,
                )
            )
        return hits
    except SearchProviderError:
        raise
    except Exception as exc:
        raise SearchProviderError(f"SerpAPI failed: {exc}") from exc


def search_all(query: str, max_results: int = 10, providers: list[str] | None = None) -> tuple[list[SearchHit], list[str]]:
    provider_order = providers or ["brave", "serpapi", "duckduckgo"]
    hits: list[SearchHit] = []
    errors: list[str] = []

    for provider in provider_order:
        try:
            if provider == "brave":
                hits.extend(search_brave(query, max_results=max_results))
            elif provider == "serpapi":
                hits.extend(search_serpapi(query, max_results=max_results))
            elif provider == "duckduckgo":
                hits.extend(search_duckduckgo(query, max_results=max_results))
        except SearchProviderError as exc:
            errors.append(str(exc))

    seen: set[str] = set()
    deduped: list[SearchHit] = []
    for hit in hits:
        key = normalize_url(hit.url)
        if key and key not in seen:
            seen.add(key)
            hit.url = key
            deduped.append(hit)
    return deduped, errors
