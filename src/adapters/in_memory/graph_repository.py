"""In-Memory Graph Repository — Test double for IGraphRepository.

Stores nodes and relationships in plain Python dicts for fast,
infrastructure-free testing.
"""

from __future__ import annotations

from typing import Any

from ports.graph import IGraphRepository


class InMemoryGraphRepository(IGraphRepository):
    """In-memory implementation of IGraphRepository for testing.

    Pre-populate via ``seed_disease()`` or direct dict manipulation
    before running tests.
    """

    def __init__(self) -> None:
        self.diseases: dict[str, dict[str, Any]] = {}
        self.cypher_results: list[dict[str, Any]] = []
        self._connected: bool = True

    # ── Seeding helpers ───────────────────────────────────────────────────

    def seed_disease(
        self,
        name: str,
        *,
        description: str | None = None,
        symptoms: list[str] | None = None,
        treatments: list[str] | None = None,
        medicines: list[str] | None = None,
        advice: list[str] | None = None,
        category: str | None = None,
    ) -> None:
        """Add a disease to the in-memory graph."""
        self.diseases[name] = {
            "disease_name": name,
            "description": description or f"Mô tả {name}",
            "disease_category": category,
            "symptoms": symptoms or [],
            "treatments": treatments or [],
            "medicines": medicines or [],
            "advice": advice or [],
        }

    def set_cypher_results(self, results: list[dict[str, Any]]) -> None:
        """Pre-set results that ``execute_cypher`` will return."""
        self.cypher_results = results

    # ── IGraphRepository implementation ───────────────────────────────────

    async def execute_cypher(
        self, query: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        if not self._connected:
            raise RuntimeError("InMemoryGraph: not connected")
        return list(self.cypher_results)

    async def find_diseases_by_name(
        self, name: str, *, limit: int = 30
    ) -> list[str]:
        name_lower = name.lower()
        matches = [
            d for d in self.diseases
            if name_lower in d.lower()
        ]
        return matches[:limit]

    async def get_disease_detail(self, disease_name: str) -> dict[str, Any] | None:
        return self.diseases.get(disease_name)

    async def get_schema_info(self) -> dict[str, Any]:
        return {
            "nodes": [
                {"label": "Disease", "count": len(self.diseases), "properties": ["disease_name"]},
            ],
            "relationships": [],
        }

    async def check_connectivity(self) -> bool:
        return self._connected

    async def close(self) -> None:
        self._connected = False
