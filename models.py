from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

SearchMode = Literal["general", "person", "email", "phone", "username", "company", "domain"]
TargetType = Literal[
    "self",
    "consented_person",
    "public_person",
    "company",
    "journalism_or_research",
    "unknown",
]
ProviderName = Literal["duckduckgo", "brave", "serpapi", "direct_username"]


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str = ""
    source: str = ""
    provider: str = ""
    query_used: str = ""
    rank: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MediaItem:
    type: str  # image | video | other
    url: str
    source_page: str = ""
    alt: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class UsernameProfile:
    platform: str
    url: str
    status: str  # confirmed | possible | unavailable | error
    http_status: int | None = None
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Evidence:
    id: int
    title: str
    url: str
    source: str
    provider: str
    query_used: str
    snippet: str
    extracted_text: str
    relevance_score: float
    confidence: str
    matched_terms: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    social_profiles: list[str] = field(default_factory=list)
    usernames: list[str] = field(default_factory=list)
    media: list[MediaItem] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    organizations: list[str] = field(default_factory=list)
    related_names: list[str] = field(default_factory=list)
    public_record_hints: list[str] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)
    content_hash: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        data["media"] = [m.to_dict() if hasattr(m, "to_dict") else m for m in self.media]
        return data


@dataclass
class DeepSearchReport:
    query: str
    mode: SearchMode
    target_type: TargetType
    created_at: str
    search_queries: list[str]
    summary: str
    executive_summary: str
    confidence_overall: str
    findings: dict
    evidence: list[Evidence]
    username_profiles: list[UsernameProfile] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    provider_errors: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "mode": self.mode,
            "target_type": self.target_type,
            "created_at": self.created_at,
            "search_queries": self.search_queries,
            "summary": self.summary,
            "executive_summary": self.executive_summary,
            "confidence_overall": self.confidence_overall,
            "findings": self.findings,
            "warnings": self.warnings,
            "provider_errors": self.provider_errors,
            "stats": self.stats,
            "username_profiles": [p.to_dict() for p in self.username_profiles],
            "evidence": [e.to_dict() for e in self.evidence],
        }
