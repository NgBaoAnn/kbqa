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

        # If explicit cypher_results are pre-set, use those
        if self.cypher_results:
            return list(self.cypher_results)

        params = params or {}
        q_lower = query.strip().lower()

        # ── count(d) ──────────────────────────────────────────────────────
        if "return count(d) as total" in q_lower or "return count(d)" in q_lower:
            if "contains" in q_lower and "q" in params:
                search = params.get("q", "").lower()
                count = sum(1 for d in self.diseases if search in d.lower())
            else:
                count = len(self.diseases)
            return [{"total": count}]

        # ── MATCH (d:Disease) — list / detail queries ─────────────────────
        if "match (d:disease" in q_lower:
            disease_name_param = params.get("disease_name")

            # Detail query for specific disease
            if disease_name_param is not None:
                disease = self.diseases.get(disease_name_param)
                if disease is None:
                    return []
                return [{
                    "disease_name": disease.get("disease_name", disease_name_param),
                    "disease_description": disease.get("disease_description") or disease.get("description"),
                    "disease_category": disease.get("disease_category"),
                    "disease_cause": disease.get("disease_cause"),
                    "disease_symptom": None,
                    "check_method": None,
                    "people_easy_get": None,
                    "cure_method": None,
                    "cure_department": None,
                    "cure_probability": None,
                    "drug_common": None,
                    "drug_recommend": None,
                    "drug_detail": None,
                    "nutrition_do_eat": None,
                    "nutrition_not_eat": None,
                    "nutrition_recommend_meal": None,
                    "disease_prevention": None,
                }]

            # List query with optional filter + pagination
            search = params.get("q", "").lower() if params.get("q") else None
            skip = int(params.get("offset", 0))
            limit = int(params.get("limit", 20))

            results = list(self.diseases.values())
            if search:
                results = [d for d in results if search in d.get("disease_name", "").lower()]
            results = sorted(results, key=lambda d: d.get("disease_name", ""))
            page = results[skip: skip + limit]

            return [
                {
                    "disease_name": d.get("disease_name"),
                    "disease_category": d.get("disease_category"),
                    "disease_description": d.get("disease_description") or d.get("description"),
                }
                for d in page
            ]

        # ── Fallback ──────────────────────────────────────────────────────
        return []

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
