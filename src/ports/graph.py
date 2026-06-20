"""Port: Graph Repository.

Abstracts all Knowledge Graph operations (Neo4j).
Adapters: Neo4jGraphRepository, InMemoryGraphRepository.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IGraphRepository(ABC):
    """Port for Knowledge Graph operations."""

    @abstractmethod
    async def execute_cypher(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a Cypher query and return results as list of dicts.

        Args:
            query: The Cypher query string.
            params: Optional query parameters.

        Returns:
            List of record dictionaries.

        Raises:
            InfrastructureError: If the graph database is unavailable.
        """
        ...

    @abstractmethod
    async def find_diseases_by_name(
        self, name: str, *, limit: int = 30
    ) -> list[str]:
        """Find diseases whose name contains the given substring.

        Used for entity disambiguation in the Cypher path.

        Args:
            name: The search substring.
            limit: Maximum number of results.

        Returns:
            List of matching disease names.
        """
        ...

    @abstractmethod
    async def get_disease_detail(self, disease_name: str) -> dict[str, Any] | None:
        """Fetch full details for a disease by exact name.

        Returns:
            Dict with disease info, or None if not found.
        """
        ...

    @abstractmethod
    async def get_schema_info(self) -> dict[str, Any]:
        """Return the graph schema (node labels, relationship types, counts).

        Returns:
            Dict with 'nodes' and 'relationships' lists.
        """
        ...

    @abstractmethod
    async def check_connectivity(self) -> bool:
        """Check if the graph database is reachable.

        Returns:
            True if connected successfully.
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Release the database connection/driver."""
        ...
