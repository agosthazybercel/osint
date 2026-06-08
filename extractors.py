from __future__ import annotations

import re
from collections import Counter
from urllib.parse import urlparse

from .utils import normalize_text, unique_keep_order

EMAIL_RE = re.compile(r"(?<![\w.+-])([A-Z0-9._%+\-]+\s*(?:@|\[at\]|\(at\)| at )\s*[A-Z0-9.\-]+\s*(?:\.|\[dot\]|\(dot\)| dot )\s*[A-Z]{2,})(?![\w.+-])", re.I)
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().\-]{6,}\d)(?!\w)")
USERNAME_RE = re.compile(r"(?<![\w.])@([A-Za-z0-9_.\-]{3,32})")

COMMON_LOCATIONS = [
    "Budapest", "Debrecen", "Szeged", "Miskolc", "Pécs", "Győr", "Nyíregyháza", "Kecskemét",
    "Székesfehérvár", "Szombathely", "Hungary", "Magyarország", "Austria", "Vienna", "Wien",
    "Germany", "Berlin", "United Kingdom", "London", "France", "Paris", "Spain", "Madrid",
    "Italy", "Rome", "Poland", "Warsaw", "Prague", "Czech", "USA", "United States",
    "New York", "Los Angeles", "San Francisco", "Toronto", "Canada", "Amsterdam", "Netherlands",
]

ORG_SUFFIXES = [
    "Ltd", "Kft", "Zrt", "Bt", "Inc", "LLC", "GmbH", "AG", "University", "School", "Gimnázium",
    "Foundation", "Association", "Institute", "Group", "Company", "Corp", "Corporation",
]

PUBLIC_RECORD_TERMS = [
    "company registry", "cégjegyzék", "adószám", "tax number", "court", "bíróság", "lawsuit",
    "archive", "public records", "press release", "official gazette", "közlöny", "patent", "trademark",
]

SOCIAL_PATH_USER_RE = re.compile(r"/(?:@)?([A-Za-z0-9_.\-]{3,40})(?:/)?$")


def extract_emails(text: str) -> list[str]:
    out = []
    for raw in EMAIL_RE.findall(text or ""):
        email = raw
        email = re.sub(r"\s*(\[at\]|\(at\)| at )\s*", "@", email, flags=re.I)
        email = re.sub(r"\s*(\[dot\]|\(dot\)| dot )\s*", ".", email, flags=re.I)
        email = re.sub(r"\s+", "", email).lower().strip(".,;:)")
        if "@" in email and "." in email.split("@")[-1] and len(email) <= 120:
            out.append(email)
    return unique_keep_order(out)


def extract_phones(text: str) -> list[str]:
    phones = []
    for match in PHONE_RE.findall(text or ""):
        cleaned = normalize_text(match).strip(".,;:()[]")
        digits = re.sub(r"\D", "", cleaned)
        if 7 <= len(digits) <= 16:
            phones.append(cleaned)
    return unique_keep_order(phones)


def extract_usernames(text: str, urls: list[str] | None = None) -> list[str]:
    names = USERNAME_RE.findall(text or "")
    for url in urls or []:
        try:
            m = SOCIAL_PATH_USER_RE.search(urlparse(url).path.rstrip("/"))
            if m:
                username = m.group(1)
                if username.lower() not in {"home", "about", "contact", "login", "share", "watch", "posts", "reel"}:
                    names.append(username)
        except Exception:
            pass
    return unique_keep_order(names)[:50]


def extract_locations(text: str) -> list[str]:
    found = []
    for loc in COMMON_LOCATIONS:
        if re.search(rf"\b{re.escape(loc)}\b", text or "", flags=re.I):
            found.append(loc)
    return unique_keep_order(found)


def extract_related_names(text: str, query: str = "", max_names: int = 25) -> list[str]:
    pattern = r"\b[A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű]+(?:\s+[A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű]+){1,3}\b"
    names = re.findall(pattern, text or "")
    q = (query or "").lower()
    filtered = []
    stop = {"United States", "New York", "San Francisco", "Los Angeles", "Privacy Policy", "Terms Conditions"}
    for name in names:
        if name in stop or len(name) > 80:
            continue
        low = name.lower()
        if q and (low == q or low in q or q in low):
            continue
        # Avoid all organization-like names here; orgs extracted separately.
        if any(name.endswith(" " + suffix) for suffix in ORG_SUFFIXES):
            continue
        filtered.append(name)
    counts = Counter(filtered)
    return [name for name, _ in counts.most_common(max_names)]


def extract_organizations(text: str, max_items: int = 25) -> list[str]:
    found = []
    for suffix in ORG_SUFFIXES:
        pattern = rf"\b[A-ZÁÉÍÓÖŐÚÜŰ][\wáéíóöőúüűÁÉÍÓÖŐÚÜŰ&.,\- ]{{2,80}}\s+{re.escape(suffix)}\b"
        found.extend(re.findall(pattern, text or ""))
    cleaned = [normalize_text(x).strip(".,;:") for x in found if 3 <= len(x) <= 100]
    return unique_keep_order(cleaned)[:max_items]


def extract_public_record_hints(text: str, url: str = "") -> list[str]:
    haystack = f"{url} {text[:3000]}".lower()
    hits = []
    for term in PUBLIC_RECORD_TERMS:
        if term.lower() in haystack:
            hits.append(term)
    return unique_keep_order(hits)


DATE_RE = re.compile(
    r"\b(?:"
    r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}"
    r"|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}"
    r"|\d{1,2}\s+(?:január|február|március|április|május|június|július|augusztus|szeptember|október|november|december)\s+\d{4}"
    r")\b",
    re.I,
)


def extract_dates(text: str, max_items: int = 40) -> list[str]:
    """Extract likely explicit dates from text. This is a hint extractor, not a verified publication-date detector."""
    raw = DATE_RE.findall(text or "")
    cleaned = [normalize_text(x).strip(".,;:") for x in raw if 6 <= len(x) <= 40]
    return unique_keep_order(cleaned)[:max_items]
