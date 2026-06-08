from __future__ import annotations

import json

from .config import settings

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore


def summarize(query: str, mode: str, target_type: str, findings: dict, evidence: list) -> str:
    if not settings.openai_api_key or OpenAI is None:
        return "AI summary disabled. Add OPENAI_API_KEY to .env to enable source-grounded Deep Reports."

    compact_evidence = []
    for ev in evidence[:14]:
        compact_evidence.append(
            {
                "id": ev.id,
                "title": ev.title,
                "url": ev.url,
                "source": ev.source,
                "confidence": ev.confidence,
                "matched_terms": ev.matched_terms,
                "snippet": ev.snippet[:800],
                "text_excerpt": ev.extracted_text[:2500],
                "emails": ev.emails[:10],
                "phones": ev.phones[:10],
                "social_profiles": ev.social_profiles[:10],
                "locations": ev.locations[:10],
                "organizations": ev.organizations[:10],
            }
        )

    system = """
You are a cautious source-grounded public web research assistant.
Only use the provided evidence. Do not invent facts. Do not infer sensitive attributes.
Do not make accusations. Separate confirmed facts, likely matches, and unverified leads.
Use source IDs like [1], [2] for important claims.
If the evidence may refer to multiple people with the same name, state that clearly.
""".strip()

    user = {
        "query": query,
        "mode": mode,
        "target_type": target_type,
        "findings": findings,
        "evidence": compact_evidence,
        "required_output": [
            "Short answer / executive summary",
            "Confirmed public signals with source IDs",
            "Likely but unverified leads",
            "Social/profile findings",
            "Contact/media findings",
            "Contradictions and false-match risks",
            "Recommended manual verification steps",
        ],
    }

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=settings.openai_model,
        temperature=0.15,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ],
    )
    return response.choices[0].message.content or ""
