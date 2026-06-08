from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    root_dir: Path = ROOT_DIR
    data_dir: Path = ROOT_DIR / "data"
    reports_dir: Path = ROOT_DIR / "reports"
    cache_dir: Path = ROOT_DIR / ".cache"

    openai_api_key: str | None = os.getenv("OPENAI_API_KEY") or None
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5-nano")

    brave_search_api_key: str | None = os.getenv("BRAVE_SEARCH_API_KEY") or None
    serpapi_key: str | None = os.getenv("SERPAPI_KEY") or None

    require_lawful_use: bool = os.getenv("REQUIRE_LAWFUL_USE", "true").lower() in {"1", "true", "yes", "on"}
    enable_http_cache: bool = os.getenv("ENABLE_HTTP_CACHE", "true").lower() in {"1", "true", "yes", "on"}
    default_max_results_per_query: int = int(os.getenv("DEFAULT_MAX_RESULTS_PER_QUERY", "12"))
    default_max_pages: int = int(os.getenv("DEFAULT_MAX_PAGES", "60"))
    default_delay_seconds: float = float(os.getenv("DEFAULT_DELAY_SECONDS", "0.65"))
    request_timeout_seconds: int = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "18"))
    max_text_chars_per_page: int = int(os.getenv("MAX_TEXT_CHARS_PER_PAGE", "14000"))
    max_download_bytes: int = int(os.getenv("MAX_DOWNLOAD_BYTES", str(8 * 1024 * 1024)))

    user_agent: str = os.getenv(
        "USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 DeepSearchLocalPro/2.0",
    )

    sqlite_path: Path = ROOT_DIR / "data" / "deepsearch.sqlite3"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.reports_dir.mkdir(parents=True, exist_ok=True)
settings.cache_dir.mkdir(parents=True, exist_ok=True)
