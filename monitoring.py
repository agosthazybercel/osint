from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .config import settings

WATCHLIST_PATH = settings.data_dir / "watchlist.json"


def load_watchlist() -> list[dict]:
    if not WATCHLIST_PATH.exists():
        return []
    try:
        return json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def add_watch(query: str, context: str = "", mode: str = "general") -> dict:
    items = load_watchlist()
    item = {"query": query, "context": context, "mode": mode, "created_at": datetime.now().isoformat(timespec="seconds")}
    items.append(item)
    WATCHLIST_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return item


def remove_watch(index: int) -> bool:
    items = load_watchlist()
    if index < 0 or index >= len(items):
        return False
    items.pop(index)
    WATCHLIST_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return True
