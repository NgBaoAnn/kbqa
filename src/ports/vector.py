"""Port: Vector Repository.

Abstracts semantic vector search (LightRAG / Qdrant).
Adapters: LightragVectorRepository, InMemoryVectorRepository.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any


class IVectorRepository(ABC):
    """Port for semantic vector search operations."""

    @abstractmethod
    async def query(
        self,
        question: str,
        *,
        mode: str = "naive",
        only_need_context: bool = False,
    ) -> dict[str, Any]:
        """Query the vector store with a natural language question.

        Args:
            question: The user's question.
            mode: Query mode (naive, local, global, hybrid).
            only_need_context: If True, return raw context without LLM synthesis.

        Returns:
            Dict with keys: answer, mode, success, [error].

        Raises:
            InfrastructureError: If the vector store is unavailable.
        """
        ...

    @abstractmethod
    async def query_stream(
        self,
        question: str,
        *,
        mode: str = "naive",
    ) -> tuple[str, AsyncIterator[str]]:
        """Stream a query response token by token.

        Args:
            question: The user's question.
            mode: Query mode.

        Returns:
            Tuple of (effective_mode, async iterator of answer chunks).

        Raises:
            InfrastructureError: If the vector store is unavailable.
        """
        ...

    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """Check the health of the vector store and its dependencies.

        Returns:
            Dict with status information for each component.
        """
        ...
