"""Knowledge browsing service — S3-BE-01 & S3-BE-02.

Provides read-only access to the VietMedKG Neo4j knowledge graph.
Disease nodes are the hub; Symptom, Treatment, Medicine, Advice are star spokes.

Design rules
------------
- All queries are read-only Cypher executed via ``graph_service.execute_cypher()``.
- This service NEVER writes to Neo4j.
- ``disease_id`` is the disease's ``disease_name`` property (the UNIQUE key in the KG).
- Multi-value text fields stored as semicolons, newlines, or commas are split into lists.
- No user/auth data passes through this service.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import HTTPException, status

from app.models.contracts import DiseaseDetailResponse, DiseaseListResponse, DiseaseSummary
from app.services import graph_service

logger = logging.getLogger(__name__)

# Maximum summary length shown in list view.
_SUMMARY_MAX_LEN = 120

# Characters used to separate multi-value text fields in VietMedKG.
_FIELD_SEPARATORS = re.compile(r"[;\n]+")


# ── Helpers ────────────────────────────────────────────────────────────────


def _split_field(value: str | None) -> list[str]:
    """Split a semicolon/newline-delimited text field into a clean list."""
    if not value:
        return []
    parts = _FIELD_SEPARATORS.split(value)
    return [p.strip() for p in parts if p.strip()]


def _truncate(text: str | None, max_len: int) -> str | None:
    if not text:
        return None
    text = text.strip()
    return text[:max_len] + "…" if len(text) > max_len else text


def _graph_error(exc: Exception, context: str) -> HTTPException:
    """Log the real error and expose a safe 503 to the caller."""
    logger.error("knowledge_service: %s failed: %s", context, exc)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "error_code": "KNOWLEDGE_GRAPH_UNAVAILABLE",
            "message": "Knowledge graph is temporarily unavailable.",
        },
    )


# ── Public API ─────────────────────────────────────────────────────────────


async def list_diseases(
    *,
    q: str | None,
    limit: int,
    offset: int,
) -> DiseaseListResponse:
    """Return a paginated list of diseases, optionally filtered by name.

    Args:
        q: Optional search term; matched case-insensitively against ``disease_name``.
        limit: Page size (1–100).
        offset: Pagination offset.

    Returns:
        A ``DiseaseListResponse`` with ``items``, ``total``, ``limit``, ``offset``.
    """
    try:
        if q:
            # Use toLower() for case-insensitive containment search.
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

        count_rows = await graph_service.execute_cypher(count_query, params)
        total: int = count_rows[0]["total"] if count_rows else 0

        rows = await graph_service.execute_cypher(list_query, params)

    except HTTPException:
        raise
    except Exception as exc:
        raise _graph_error(exc, "list_diseases") from exc

    items = [
        DiseaseSummary(
            id=row["disease_name"],
            disease_name=row["disease_name"],
            disease_category=row.get("disease_category"),
            summary=_truncate(row.get("disease_description"), _SUMMARY_MAX_LEN),
        )
        for row in rows
    ]

    return DiseaseListResponse(items=items, total=total, limit=limit, offset=offset)


async def get_disease(*, disease_id: str) -> DiseaseDetailResponse:
    """Return full detail for a disease node and its related spokes.

    Args:
        disease_id: The disease's ``disease_name`` (UNIQUE key in VietMedKG).

    Returns:
        A ``DiseaseDetailResponse`` with symptoms, treatments, medicines, advice.

    Raises:
        HTTPException 404 if the disease is not found.
        HTTPException 503 if the graph is unavailable.
    """
    try:
        # One query: fetch Disease node + all 4 spoke types with OPTIONAL MATCH
        # so we always get the disease even if some relationships are missing.
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
        rows = await graph_service.execute_cypher(query, {"disease_name": disease_id})

    except HTTPException:
        raise
    except Exception as exc:
        raise _graph_error(exc, f"get_disease({disease_id!r})") from exc

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "DISEASE_NOT_FOUND",
                "message": f"Disease '{disease_id}' not found in the knowledge graph.",
            },
        )

    # All rows represent the same disease (star schema → at most 1:1 per spoke).
    # Take first row for all fields; multiple rows would only appear if the
    # KG has duplicate relationships (not expected in VietMedKG star schema).
    row = rows[0]

    symptoms: list[str] = _split_field(row.get("disease_symptom"))
    check_methods: list[str] = _split_field(row.get("check_method"))
    # Merge check_method into symptoms list when present (provides context)
    if check_methods and check_methods != symptoms:
        symptoms = symptoms  # keep symptoms clean; check_method is metadata

    treatments: list[str] = _split_field(row.get("cure_method"))
    if row.get("cure_department"):
        # Prepend department context when available
        for dept in _split_field(row.get("cure_department")):
            entry = f"Khoa {dept}"
            if entry not in treatments:
                treatments.insert(0, entry)

    medicines: list[str] = []
    for field in ("drug_common", "drug_recommend", "drug_detail"):
        medicines.extend(_split_field(row.get(field)))
    # De-duplicate while preserving order
    seen: set[str] = set()
    unique_medicines: list[str] = []
    for med in medicines:
        if med not in seen:
            seen.add(med)
            unique_medicines.append(med)

    advice: list[str] = []
    for field in ("nutrition_do_eat", "nutrition_recommend_meal", "nutrition_not_eat", "disease_prevention"):
        advice.extend(_split_field(row.get(field)))

    metadata: dict[str, Any] = {"source": "Neo4j VietMedKG"}
    if row.get("disease_category"):
        metadata["disease_category"] = row["disease_category"]
    if row.get("disease_cause"):
        metadata["disease_cause"] = row["disease_cause"]
    if row.get("people_easy_get"):
        metadata["people_easy_get"] = row["people_easy_get"]
    if row.get("check_method"):
        metadata["check_method"] = row["check_method"]
    if row.get("cure_probability"):
        metadata["cure_probability"] = row["cure_probability"]
    if row.get("cure_department"):
        metadata["cure_department"] = row["cure_department"]

    return DiseaseDetailResponse(
        id=row["disease_name"],
        disease_name=row["disease_name"],
        description=row.get("disease_description"),
        symptoms=symptoms,
        treatments=treatments,
        medicines=unique_medicines,
        advice=advice,
        metadata=metadata,
    )
