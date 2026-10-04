from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Evidence:
    source: str
    quote: str
    chunk_id: str = ""


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    source: str
    text: str
    page: int | None = None


@dataclass
class Document:
    source: str
    text: str
    content_hash: str
    chunks: list[Chunk] = field(default_factory=list)
    media_type: str = "text/plain"


@dataclass
class ActionItem:
    id: str
    title: str
    action_type: str
    priority: str
    summary: str
    suggested_action: str
    evidence_confidence: int
    facts: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    status: str = "Pending"
    response_draft: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ActionItem":
        details = dict(payload)
        details["evidence"] = [Evidence(**item) for item in details.get("evidence", [])]
        return cls(**details)


@dataclass
class AnalysisResult:
    id: str
    created_at: str
    company: str
    source_count: int
    chunk_count: int
    entities: list[str]
    items: list[ActionItem]
    summary: str
    source_names: list[str] = field(default_factory=list)
    llm_used: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "company": self.company,
            "source_count": self.source_count,
            "chunk_count": self.chunk_count,
            "entities": self.entities,
            "items": [item.to_dict() for item in self.items],
            "summary": self.summary,
            "source_names": self.source_names,
            "llm_used": self.llm_used,
            "warnings": self.warnings,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AnalysisResult":
        details = dict(payload)
        details["items"] = [ActionItem.from_dict(item) for item in details.get("items", [])]
        return cls(**details)
