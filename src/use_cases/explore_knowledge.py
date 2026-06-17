"""ExploreKnowledgeUseCase — Read-only browsing of the Neo4j knowledge graph.

Extracted from backend/app/services/knowledge_service.py.
Uses only IGraphRepository port — no direct Neo4j driver imports.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_SUMMARY_MAX_LEN = 120
_FIELD_SEPARATORS = re.compile(r"[;\n]+")


def _split_field(value: str | None) -> list[str]:
    if not value:
        return []
    return [p.strip() for p in _FIELD_SEPARATORS.split(value) if p.strip()]


def _truncate(text: str | None, max_len: int) -> str | None:
    if not text:
        return None
    text = text.strip()
    return text[:max_len] + "…" if len(text) > max_len else text


@dataclass
class DiseaseListResult:
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


class ExploreKnowledgeUseCase:
    """Read-only knowledge graph exploration.

    Args:
        graph: IGraphRepository
    """

    def __init__(self, *, graph) -> None:
        self._graph = graph

    async def list_diseases(
        self,
        *,
        q: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> DiseaseListResult:
        """Paginated disease list, optionally filtered by name."""
        try:
            if q:
                count_query = """
                    MATCH (d:Disease)
                    WHERE toLower(d.disease_name) CONTAINS toLower($q)
                    RETURN count(d) AS total
                """
                list_query = """
                    MATCH (d:Disease)
                    WHERE toLower(d.disease_name) CONTAINS toLower($q)
                    RETURN d.disease_name AS disease_name,
                           d.disease_category AS disease_category,
                           d.disease_description AS disease_description
                    ORDER BY d.disease_name
                    SKIP $offset LIMIT $limit
                """
                params: dict[str, Any] = {"q": q, "offset": offset, "limit": limit}
            else:
                count_query = "MATCH (d:Disease) RETURN count(d) AS total"
                list_query = """
                    MATCH (d:Disease)
                    RETURN d.disease_name AS disease_name,
                           d.disease_category AS disease_category,
                           d.disease_description AS disease_description
                    ORDER BY d.disease_name
                    SKIP $offset LIMIT $limit
                """
                params = {"offset": offset, "limit": limit}

            count_rows = await self._graph.execute_cypher(count_query, params)
            total = count_rows[0]["total"] if count_rows else 0
            rows = await self._graph.execute_cypher(list_query, params)

        except Exception as exc:
            logger.error("ExploreKnowledgeUseCase.list_diseases failed: %s", exc)
            raise RuntimeError("KNOWLEDGE_GRAPH_UNAVAILABLE") from exc

        items = [
            {
                "id": row["disease_name"],
                "disease_name": row["disease_name"],
                "disease_category": row.get("disease_category"),
                "summary": _truncate(row.get("disease_description"), _SUMMARY_MAX_LEN),
            }
            for row in rows
        ]
        return DiseaseListResult(items=items, total=total, limit=limit, offset=offset)

    async def get_disease(self, *, disease_id: str) -> dict[str, Any] | None:
        """Return full disease detail or None if not found."""
        try:
            query = """
                MATCH (d:Disease {disease_name: $disease_name})
                OPTIONAL MATCH (d)-[:HAS_SYMPTOM]->(s:Symptom)
                OPTIONAL MATCH (d)-[:HAS_TREATMENT]->(t:Treatment)
                OPTIONAL MATCH (d)-[:IS_PRESCRIBED]->(m:Medicine)
                OPTIONAL MATCH (d)-[:HAS_ADVICE]->(a:Advice)
                RETURN
                    d.disease_name        AS disease_name,
                    d.disease_description AS disease_description,
                    d.disease_category    AS disease_category,
                    d.disease_cause       AS disease_cause,
                    s.disease_symptom     AS disease_symptom,
                    s.check_method        AS check_method,
                    s.people_easy_get     AS people_easy_get,
                    t.cure_method         AS cure_method,
                    t.cure_department     AS cure_department,
                    t.cure_probability    AS cure_probability,
                    m.drug_common         AS drug_common,
                    m.drug_recommend      AS drug_recommend,
                    m.drug_detail         AS drug_detail,
                    a.nutrition_do_eat    AS nutrition_do_eat,
                    a.nutrition_not_eat   AS nutrition_not_eat,
                    a.nutrition_recommend_meal AS nutrition_recommend_meal,
                    a.disease_prevention  AS disease_prevention
            """
            rows = await self._graph.execute_cypher(query, {"disease_name": disease_id})
        except Exception as exc:
            logger.error("ExploreKnowledgeUseCase.get_disease(%r) failed: %s", disease_id, exc)
            raise RuntimeError("KNOWLEDGE_GRAPH_UNAVAILABLE") from exc

        if not rows:
            return None

        row = rows[0]
        symptoms = _split_field(row.get("disease_symptom"))
        treatments = _split_field(row.get("cure_method"))
        if row.get("cure_department"):
            for dept in _split_field(row.get("cure_department")):
                entry = f"Khoa {dept}"
                if entry not in treatments:
                    treatments.insert(0, entry)

        medicines: list[str] = []
        for field in ("drug_common", "drug_recommend", "drug_detail"):
            medicines.extend(_split_field(row.get(field)))
        seen: set[str] = set()
        unique_medicines = [m for m in medicines if not (m in seen or seen.add(m))]

        advice: list[str] = []
        for field in ("nutrition_do_eat", "nutrition_recommend_meal", "nutrition_not_eat", "disease_prevention"):
            advice.extend(_split_field(row.get(field)))

        metadata: dict[str, Any] = {"source": "Neo4j VietMedKG"}
        for key in ("disease_category", "disease_cause", "people_easy_get", "check_method", "cure_probability", "cure_department"):
            if row.get(key):
                metadata[key] = row[key]

        return {
            "id": row["disease_name"],
            "disease_name": row["disease_name"],
            "description": row.get("disease_description"),
            "symptoms": symptoms,
            "treatments": treatments,
            "medicines": unique_medicines,
            "advice": advice,
            "metadata": metadata,
        }
