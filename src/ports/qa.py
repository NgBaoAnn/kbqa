"""Ports for QA infrastructure still backed by legacy AI engine modules.

These ports keep the domain pipeline free of infrastructure imports while the
Cypher builder/synthesizer migration is completed incrementally.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any


class IIntentExtractor(ABC):
    """Port for LLM-backed intent extraction."""

    @abstractmethod
    async def extract_intent(self, question: str) -> tuple[str | None, str | None]:
        """Return ``(query_type, entity)`` for a natural language question."""
        ...


class ICypherQaEngine(ABC):
    """Port for the full Cypher QA path.

    Implementations generate Cypher, validate/sanitize it, execute through the
    provided graph callback, and synthesize a natural-language answer.
    """

    @abstractmethod
    async def query(
        self,
        *,
        question: str,
        query_type: str | None,
        entity: str | None,
        exact: bool,
        execute_fn: Callable[[str, dict[str, Any] | None], Any],
    ) -> dict[str, Any]:
        """Run the Cypher QA path and return the legacy-compatible result dict."""
        ...
