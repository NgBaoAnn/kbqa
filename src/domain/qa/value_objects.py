"""QA Domain — Value Objects.

Value objects are immutable, identity-less data carriers.  They enforce
business invariants at construction time and are always valid.

These objects have NO dependency on infrastructure (no I/O, no framework).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class QueryType(str, Enum):
    """Classified intent type for a medical question.

    Maps to the query_type field extracted by intent classification.
    Each value determines which Cypher template (if any) to use.
    """

    SYMPTOMS = "symptoms"
    TREATMENT = "treatment"
    MEDICINE = "medicine"
    ADVICE = "advice"
    DESCRIPTION = "description"
    GENERAL_INFO = "general_info"
    PREVENTION = "prevention"
    ASSOCIATED_DISEASE = "associated_disease"
    GENERAL = "general"

    @classmethod
    def from_string(cls, value: str | None) -> QueryType:
        """Parse a string into a QueryType, defaulting to GENERAL."""
        if not value:
            return cls.GENERAL
        try:
            return cls(value.lower().strip())
        except ValueError:
            return cls.GENERAL

    @property
    def has_cypher_template(self) -> bool:
        """Whether this query type has a dedicated Cypher template."""
        return self not in (QueryType.GENERAL, QueryType.GENERAL_INFO)


@dataclass(frozen=True)
class EntityName:
    """A normalised medical entity name extracted from a question.

    Invariants:
    - Non-empty after stripping whitespace.
    - First letter capitalised (Vietnamese convention).
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("EntityName cannot be empty.")
        # Normalise: strip + capitalise first letter
        normalised = self.value.strip()
        normalised = normalised[0].upper() + normalised[1:] if len(normalised) > 1 else normalised.upper()
        object.__setattr__(self, "value", normalised)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class CypherQuery:
    """A validated Cypher query string with optional parameters.

    This VO wraps a raw Cypher string that has already passed validation
    and sanitization.
    """

    query: str
    params: dict[str, Any] = field(default_factory=dict)
    used_template: bool = False

    def __post_init__(self) -> None:
        if not self.query or not self.query.strip():
            raise ValueError("CypherQuery cannot be empty.")


@dataclass(frozen=True)
class IntentClassification:
    """The result of classifying a user question.

    Captures both the query type and the extracted entity (if any),
    plus metadata about which method was used (regex vs LLM).
    """

    query_type: QueryType
    entity: EntityName | None = None
    exact_match: bool = False
    method: str = "regex"  # "regex" | "llm" | "fallback"
    confidence: float = 1.0

    @property
    def has_entity(self) -> bool:
        return self.entity is not None

    @property
    def should_use_cypher(self) -> bool:
        """Heuristic: use Cypher path when we have both a typed intent and an entity."""
        return self.has_entity and self.query_type.has_cypher_template


@dataclass(frozen=True)
class SafetyClassification:
    """Safety classification for a QA response.

    Levels:
        normal:    General informational answer; standard disclaimer.
        caution:   Medical query that may affect health decisions.
        emergency: Life-threatening situation; requires immediate action.
    """

    level: str = "normal"  # "normal" | "caution" | "emergency"
    requires_emergency_notice: bool = False
    disclaimer: str = "Thông tin chỉ mang tính chất tham khảo."


@dataclass(frozen=True)
class SourceRecord:
    """A single provenance/citation record attached to an answer."""

    id: str
    source_type: str  # SourceType literal
    title: str
    snippet: str | None = None
    rank: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)
