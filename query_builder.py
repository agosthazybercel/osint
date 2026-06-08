from __future__ import annotations

import re

from .models import SearchMode
from .utils import looks_like_email, looks_like_phone, unique_keep_order
from .identity import build_query_profile, looks_like_person_name, strip_accents

SOCIAL_SITES = [
    "linkedin.com", "github.com", "facebook.com", "instagram.com", "x.com", "twitter.com", "youtube.com",
    "medium.com", "reddit.com", "threads.net", "kaggle.com", "huggingface.co", "behance.net", "dribbble.com",
]

HIGH_SIGNAL_PERSON_SITES = [
    "linkedin.com", "github.com", "facebook.com", "instagram.com", "youtube.com", "medium.com", "about.me",
]


def infer_mode(query: str, requested: SearchMode = "general") -> SearchMode:
    q = query.strip()
    if requested != "general":
        return requested
    if looks_like_email(q):
        return "email"
    if looks_like_phone(q):
        return "phone"
    if re.fullmatch(r"@?[A-Za-z0-9_.\-]{3,32}", q):
        return "username"
    if "." in q and " " not in q and "@" not in q:
        return "domain"
    if looks_like_person_name(q) or len(q.split()) >= 2:
        # prefer person mode for name-like multi-token searches; the identity layer will split context safely
        return "person"
    return requested


def _ascii_variant(text: str) -> str:
    return strip_accents(text or "")


def _quoted(text: str) -> str:
    return f'"{text.strip()}"'


def build_queries(query: str, mode: SearchMode, context: str = "") -> list[str]:
    profile = build_query_profile(query, mode, context)
    q = profile.target_text.strip().strip('"')
    ctx = profile.context_text.strip()
    quoted = _quoted(q)
    ascii_q = _ascii_variant(q)
    ascii_quoted = _quoted(ascii_q)
    queries: list[str] = []

    if mode == "email":
        queries += [quoted, f'{quoted} profile', f'{quoted} contact', f'{quoted} social']

    elif mode == "phone":
        queries += [quoted, f'{quoted} contact', f'{quoted} business', f'{quoted} profile']

    elif mode == "username":
        handle = q.lstrip("@")
        queries += [
            _quoted(handle), _quoted("@" + handle), f'{_quoted(handle)} profile',
            f'{_quoted(handle)} github OR gitlab OR reddit OR medium OR youtube',
        ]
        for site in SOCIAL_SITES:
            queries.append(f'{_quoted(handle)} site:{site}')

    elif mode == "person":
        # Precision-first search set. Avoid broad "photo/public records" queries; those created most of the junk.
        if ctx:
            queries += [
                f'{quoted} {_quoted(ctx)}',
                f'{quoted} {ctx}',
                f'{ascii_quoted} {ctx}' if ascii_quoted != quoted else f'{quoted} {ctx}',
            ]
        queries += [
            quoted,
            ascii_quoted if ascii_quoted != quoted else quoted,
            f'{quoted} profile',
            f'{quoted} interview OR article OR news',
            f'{quoted} bio OR biography',
        ]
        if ctx:
            for site in HIGH_SIGNAL_PERSON_SITES:
                queries.append(f'{quoted} {ctx} site:{site}')
        for site in HIGH_SIGNAL_PERSON_SITES:
            queries.append(f'{quoted} site:{site}')

    elif mode == "company":
        queries += [
            quoted,
            f'{quoted} official website',
            f'{quoted} contact email phone',
            f'{quoted} LinkedIn Facebook Instagram YouTube',
            f'{quoted} news OR press',
            f'{quoted} company registry OR cégjegyzék OR adószám',
            f'{quoted} team OR leadership OR employees',
        ]

    elif mode == "domain":
        domain = q.replace("https://", "").replace("http://", "").strip("/")
        queries += [
            f'site:{domain}',
            _quoted(domain),
            f'{_quoted(domain)} contact email phone',
            f'{_quoted(domain)} social profiles',
            f'{_quoted(domain)} news mentions',
        ]

    else:
        if ctx:
            queries.append(f'{quoted} {_quoted(ctx)}')
        queries += [q, quoted, f'{q} overview', f'{q} sources']

    return unique_keep_order([x for x in queries if normalize_query(x)])


def normalize_query(q: str) -> str:
    return re.sub(r"\s+", " ", q or "").strip()
