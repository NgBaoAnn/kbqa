"""QA Domain — Entities.

Entities are the core business objects of the QA domain.  Unlike value
objects they carry identity (or at least represent a meaningful aggregate).

These objects have NO dependency on infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.qa.value_objects import (
    IntentClassification,
    SafetyClassification,
    SourceRecord,
)


@dataclass
class QueryResult:
    """The final output of the QA pipeline.

    This is the domain's canonical result.  The use-case layer maps it
    into API-specific response schemas (ChatResponse, AIServiceResult).

    Attributes:
        answer:               The synthesised answer text.
        response_type:        One of 'text', 'table', 'warning'.
        data:                 Structured data for table rendering (may be None).
        sources:              Normalised provenance records.
        safety:               Safety classification for the answer.
        suggested_questions:  Follow-up questions (may be empty).
        intent:               The classified intent that produced this result.
        engine:               Which engine produced the answer ('cypher_direct', 'lightrag').
        query_mode:           Detailed query mode (e.g. 'cypher:template:symptoms').
        execution_time_ms:    Wall-clock time for the pipeline.
        cypher:               The Cypher query used (if CypherPath).
        raw_metadata:         Unprocessed metadata dict from the engine for logging.
    """

    answer: str
    response_type: str = "text"
    data: list[dict[str, Any]] | dict[str, Any] | None = None
    sources: list[SourceRecord] = field(default_factory=list)
    safety: SafetyClassification = field(default_factory=SafetyClassification)
    suggested_questions: list[str] = field(default_factory=list)
    intent: IntentClassification | None = None
    engine: str = "unknown"
    query_mode: str = "unknown"
    execution_time_ms: float = 0.0
    cypher: str | None = None
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_successful(self) -> bool:
        """Whether the pipeline produced a usable answer."""
        return bool(self.answer and self.answer.strip())

    @property
    def source_count(self) -> int:
        return len(self.sources)


@dataclass
class PipelineContext:
    """Mutable context passed through the pipeline stages.

    Collects intermediate results so that each stage can contribute
    without knowing about other stages.  The pipeline transforms this
    context into a final ``QueryResult``.
    """

    question: str
    language: str = "vi"
    explanation_level: str = "general"
    answer_style: str = "concise"
    mode_override: str | None = None

    # Populated by intent classification
    intent: IntentClassification | None = None

    # Populated by entity disambiguation
    disambiguated_entity: str | None = None

    # Populated by Cypher path
    cypher_result: dict[str, Any] | None = None

    # Populated by LightRAG path
    lightrag_result: dict[str, Any] | None = None

    # Timing
    start_time_ns: int = 0

    @property
    def entity_name(self) -> str | None:
        """Convenience: the entity string from intent classification."""
        if self.intent and self.intent.entity:
            return self.intent.entity.value
        return None
