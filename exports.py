from __future__ import annotations

import csv
from pathlib import Path

from .config import settings
from .models import DeepSearchReport
from .utils import safe_filename, stable_id


def export_csv(report: DeepSearchReport, directory: str | Path | None = None) -> str:
    out_dir = Path(directory) if directory else settings.reports_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{safe_filename(report.query)}_{stable_id(report.query + report.created_at)}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id", "title", "url", "source", "provider", "query_used", "confidence",
                "relevance_score", "matched_terms", "emails", "phones", "social_profiles", "locations",
            ],
        )
        writer.writeheader()
        for ev in report.evidence:
            writer.writerow(
                {
                    "id": ev.id,
                    "title": ev.title,
                    "url": ev.url,
                    "source": ev.source,
                    "provider": ev.provider,
                    "query_used": ev.query_used,
                    "confidence": ev.confidence,
                    "relevance_score": ev.relevance_score,
                    "matched_terms": "; ".join(ev.matched_terms),
                    "emails": "; ".join(ev.emails),
                    "phones": "; ".join(ev.phones),
                    "social_profiles": "; ".join(ev.social_profiles),
                    "locations": "; ".join(ev.locations),
                }
            )
    return str(path)
