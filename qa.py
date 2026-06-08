from __future__ import annotations

import json

from .config import settings
from .models import DeepSearchReport

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore


def answer_report_question(report: DeepSearchReport, question: str) -> str:
    question = (question or "").strip()
    if not question:
        return "Adj meg egy kérdést a riportról."
    compact = {
        "query": report.query,
        "mode": report.mode,
        "confidence_overall": report.confidence_overall,
        "executive_summary": report.executive_summary,
        "findings": report.findings,
        "evidence": [
            {
                "id": e.id,
                "title": e.title,
                "url": e.url,
                "source": e.source,
                "confidence": e.confidence,
                "score": e.relevance_score,
                "matched_terms": e.matched_terms,
                "snippet": e.snippet[:600],
                "text_excerpt": e.extracted_text[:1400],
            }
            for e in report.evidence[:18]
        ],
    }
    if settings.openai_api_key and OpenAI is not None:
        client = OpenAI(api_key=settings.openai_api_key)
        resp = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.1,
            messages=[
                {"role": "system", "content": "You answer questions about a public-web research report. Use only the supplied report. Cite evidence IDs like [3]. If not supported, say so."},
                {"role": "user", "content": json.dumps({"report": compact, "question": question}, ensure_ascii=False)},
            ],
        )
        return resp.choices[0].message.content or "No answer returned."
    q = question.lower()
    if "legerősebb" in q or "strongest" in q or "best" in q:
        top = sorted(report.evidence, key=lambda e: e.relevance_score, reverse=True)[:5]
        return "\n".join([f"[{e.id}] {e.title} — {e.confidence}, score {e.relevance_score}: {e.url}" for e in top]) or "Nincs evidence."
    if "hamis" in q or "false" in q:
        fp = (report.findings.get("advanced") or {}).get("false_positive_control") or {}
        return json.dumps(fp, ensure_ascii=False, indent=2)
    if "social" in q or "profil" in q:
        return json.dumps(report.findings.get("social_profiles", []), ensure_ascii=False, indent=2)
    return "AI API-kulcs nélkül csak alap kérdésekre tudok válaszolni. Próbáld: legerősebb bizonyíték, hamis pozitív, social profilok."
