"""Cypher Query Builder — Template library cho VietMedKG.

Cung cấp pre-validated Cypher templates cho các query type phổ biến.
Được gọi TRƯỚC khi dùng LLM Text2Cypher.

Ghi chú schema (đã kiểm tra trực tiếp trên Neo4j):
- Mỗi Disease có đúng 1 Symptom node (UNIQUE constraint trên Symptom.disease_name).
  Triệu chứng lưu dạng blob string trong disease_symptom, không phải individual nodes.
  Pattern shared-symptom (d1)-[:HAS_SYMPTOM]->(s)<-[:HAS_SYMPTOM]-(d2) không hoạt động.
- 38% Advice nodes chỉ có disease_prevention, không có nutrition fields.
- Matching ưu tiên exact → prefixed-exact → starts-with → contains (tiered matching).
"""

import logging

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 5
_LINKED_LIMIT = 10
_FIND_BY_SYMPTOM_LIMIT = 10

# Tiered CASE expression for fuzzy entity matching.
# Score 0 = exact, 1 = "bệnh " + exact, 2 = starts-with, 3 = general contains.
_TIER = """\
CASE
  WHEN toLower(d.disease_name) = toLower($name)               THEN 0
  WHEN toLower(d.disease_name) = 'bệnh ' + toLower($name)    THEN 1
  WHEN toLower(d.disease_name) STARTS WITH toLower($name)     THEN 2
  ELSE 3
END"""


def build_cypher_query(
    query_type: str,
    entity: str | None = None,
    extra: str | None = None,
    exact: bool = False,
) -> tuple[str, dict] | tuple[None, None]:
    """Trả về (cypher_string, params) cho query_type đã biết, hoặc (None, None) nếu không khớp.

    Args:
        exact: When True, use equality match (d.disease_name = $name) instead of CONTAINS.
               Set to True when entity is a canonical name returned by disambiguation.
    """
    builders = {
        "symptoms":              _tmpl_symptoms,
        "medicine":              _tmpl_medicine,
        "treatment":             _tmpl_treatment,
        "advice":                _tmpl_advice,
        "prevention":            _tmpl_prevention,
        "department":            _tmpl_department,
        "profile":               _tmpl_profile,
        "linked_diseases":       _tmpl_linked_diseases,
        "count":                 _tmpl_count,
        "count_by_type":         _tmpl_count_by_type,
        "find_by_symptom":       _tmpl_find_by_symptom,
        "find_by_medicine":      _tmpl_find_by_medicine,
        "find_by_nutrition_avoid": _tmpl_find_by_nutrition_avoid,
        "find_by_nutrition_eat": _tmpl_find_by_nutrition_eat,
        "find_by_prevention":    _tmpl_find_by_prevention,
    }

    builder = builders.get(query_type)
    if not builder:
        logger.warning("Unknown query_type '%s' — no template available", query_type)
        return None, None

    cypher, params = builder(entity, extra, exact)
    logger.info(
        "Template selected: type=%s entity='%s' cypher='%s'",
        query_type, entity, cypher.strip()[:100],
    )
    return cypher, params


# ── Templates ──────────────────────────────────────────────────────────────

def _where_filter(alias: str, exact: bool) -> str:
    """Return the WHERE + optional tiered-sort clause for an entity-based template."""
    if exact:
        return f"WHERE {alias}.disease_name = $name\n        "
    return (
        f"WHERE toLower({alias}.disease_name) CONTAINS toLower($name)\n"
        f"        WITH {alias}, s,\n"
        f"             CASE\n"
        f"               WHEN toLower({alias}.disease_name) = toLower($name)               THEN 0\n"
        f"               WHEN toLower({alias}.disease_name) = 'bệnh ' + toLower($name)    THEN 1\n"
        f"               WHEN toLower({alias}.disease_name) STARTS WITH toLower($name)     THEN 2\n"
        f"               ELSE 3\n"
        f"             END AS match_score\n"
        f"        ORDER BY match_score, {alias}.disease_name\n"
        f"        "
    )


def _where_filter_single(alias: str, exact: bool) -> str:
    """Same as _where_filter but without the s variable in WITH (for single-node MATCH)."""
    if exact:
        return f"WHERE {alias}.disease_name = $name\n        "
    return (
        f"WHERE toLower({alias}.disease_name) CONTAINS toLower($name)\n"
        f"        WITH {alias},\n"
        f"             CASE\n"
        f"               WHEN toLower({alias}.disease_name) = toLower($name)               THEN 0\n"
        f"               WHEN toLower({alias}.disease_name) = 'bệnh ' + toLower($name)    THEN 1\n"
        f"               WHEN toLower({alias}.disease_name) STARTS WITH toLower($name)     THEN 2\n"
        f"               ELSE 3\n"
        f"             END AS match_score\n"
        f"        ORDER BY match_score, {alias}.disease_name\n"
        f"        "
    )


def _where_filter_join(alias: str, join_var: str, exact: bool) -> str:
    """WHERE + tiered sort for MATCH with a join variable (not s)."""
    if exact:
        return f"WHERE {alias}.disease_name = $name\n        "
    return (
        f"WHERE toLower({alias}.disease_name) CONTAINS toLower($name)\n"
        f"        WITH {alias}, {join_var},\n"
        f"             CASE\n"
        f"               WHEN toLower({alias}.disease_name) = toLower($name)               THEN 0\n"
        f"               WHEN toLower({alias}.disease_name) = 'bệnh ' + toLower($name)    THEN 1\n"
        f"               WHEN toLower({alias}.disease_name) STARTS WITH toLower($name)     THEN 2\n"
        f"               ELSE 3\n"
        f"             END AS match_score\n"
        f"        ORDER BY match_score, {alias}.disease_name\n"
        f"        "
    )


def _tmpl_symptoms(entity: str | None, _extra, exact: bool = False) -> tuple[str, dict]:
    if not entity:
        return (
            "MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom) "
            "RETURN d.disease_name AS disease, s.disease_symptom AS symptoms "
            f"LIMIT {_DEFAULT_LIMIT}",
            {},
        )
    wf = _where_filter("d", exact)
    return (
        f"""
        MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom)
        {wf}LIMIT $limit
        RETURN d.disease_name     AS disease,
               s.disease_symptom  AS symptoms,
               s.check_method     AS check_method,
               s.people_easy_get  AS risk_group
        """,
        {"name": entity, "limit": _DEFAULT_LIMIT},
    )


def _tmpl_medicine(entity: str | None, _extra, exact: bool = False) -> tuple[str, dict]:
    if not entity:
        return (
            "MATCH (d:Disease)-[:IS_PRESCRIBED]->(m:Medicine) "
            "RETURN d.disease_name AS disease, m.drug_common AS common_drugs "
            f"LIMIT {_DEFAULT_LIMIT}",
            {},
        )
    wf = _where_filter_join("d", "m", exact)
    return (
        f"""
        MATCH (d:Disease)-[:IS_PRESCRIBED]->(m:Medicine)
        {wf}LIMIT $limit
        RETURN d.disease_name    AS disease,
               m.drug_recommend  AS recommended_drugs,
               m.drug_common     AS common_drugs,
               m.drug_detail     AS drug_detail
        """,
        {"name": entity, "limit": _DEFAULT_LIMIT},
    )


def _tmpl_treatment(entity: str | None, _extra, exact: bool = False) -> tuple[str, dict]:
    if not entity:
        return (
            "MATCH (d:Disease)-[:HAS_TREATMENT]->(t:Treatment) "
            "RETURN d.disease_name AS disease, t.cure_method AS treatment_method "
            f"LIMIT {_DEFAULT_LIMIT}",
            {},
        )
    wf = _where_filter_join("d", "t", exact)
    return (
        f"""
        MATCH (d:Disease)-[:HAS_TREATMENT]->(t:Treatment)
        {wf}LIMIT $limit
        RETURN d.disease_name      AS disease,
               t.cure_method       AS treatment_method,
               t.cure_department   AS department,
               t.cure_probability  AS cure_rate
        """,
        {"name": entity, "limit": _DEFAULT_LIMIT},
    )


def _tmpl_advice(entity: str | None, _extra, exact: bool = False) -> tuple[str, dict]:
    # 38% Advice nodes chỉ có disease_prevention — OPTIONAL MATCH không cần thiết vì
    # đây là 1:1 relationship; NULL fields được lọc bởi formatter.
    if not entity:
        return (
            "MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice) "
            "RETURN d.disease_name AS disease, "
            "a.nutrition_do_eat AS should_eat, a.disease_prevention AS prevention "
            f"LIMIT {_DEFAULT_LIMIT}",
            {},
        )
    wf = _where_filter_join("d", "a", exact)
    return (
        f"""
        MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice)
        {wf}LIMIT $limit
        RETURN d.disease_name              AS disease,
               a.nutrition_do_eat          AS should_eat,
               a.nutrition_not_eat         AS should_avoid,
               a.nutrition_recommend_meal  AS recommended_meals,
               a.disease_prevention        AS prevention
        """,
        {"name": entity, "limit": _DEFAULT_LIMIT},
    )


def _tmpl_prevention(entity: str | None, _extra, exact: bool = False) -> tuple[str, dict]:
    if not entity:
        return (
            "MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice) "
            "RETURN d.disease_name AS disease, a.disease_prevention AS prevention "
            f"LIMIT {_DEFAULT_LIMIT}",
            {},
        )
    wf = _where_filter_join("d", "a", exact)
    return (
        f"""
        MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice)
        {wf}LIMIT $limit
        RETURN d.disease_name        AS disease,
               a.disease_prevention  AS prevention
        """,
        {"name": entity, "limit": _DEFAULT_LIMIT},
    )


def _tmpl_department(entity: str | None, _extra, exact: bool = False) -> tuple[str, dict]:
    if not entity:
        return (
            "MATCH (d:Disease)-[:HAS_TREATMENT]->(t:Treatment) "
            "RETURN d.disease_name AS disease, t.cure_department AS department "
            f"LIMIT {_DEFAULT_LIMIT}",
            {},
        )
    wf = _where_filter_join("d", "t", exact)
    return (
        f"""
        MATCH (d:Disease)-[:HAS_TREATMENT]->(t:Treatment)
        {wf}LIMIT $limit
        RETURN d.disease_name     AS disease,
               t.cure_department  AS department
        """,
        {"name": entity, "limit": _DEFAULT_LIMIT},
    )


def _tmpl_profile(entity: str | None, _extra, exact: bool = False) -> tuple[str, dict]:
    if not entity:
        return (
            "MATCH (d:Disease) "
            "RETURN d.disease_name AS disease, d.disease_description AS description "
            f"LIMIT {_DEFAULT_LIMIT}",
            {},
        )
    wf = _where_filter_single("d", exact)
    return (
        f"""
        MATCH (d:Disease)
        {wf}LIMIT $limit
        OPTIONAL MATCH (d)-[:HAS_SYMPTOM]->(s:Symptom)
        OPTIONAL MATCH (d)-[:HAS_TREATMENT]->(t:Treatment)
        OPTIONAL MATCH (d)-[:IS_PRESCRIBED]->(m:Medicine)
        OPTIONAL MATCH (d)-[:HAS_ADVICE]->(a:Advice)
        RETURN d.disease_name              AS disease,
               d.disease_description       AS description,
               d.disease_category          AS category,
               d.disease_cause             AS cause,
               s.disease_symptom           AS symptoms,
               s.check_method              AS check_method,
               s.people_easy_get           AS risk_group,
               t.cure_method               AS treatment_method,
               t.cure_department           AS department,
               t.cure_probability          AS cure_rate,
               m.drug_recommend            AS recommended_drugs,
               m.drug_common               AS common_drugs,
               a.nutrition_do_eat          AS should_eat,
               a.nutrition_not_eat         AS should_avoid,
               a.nutrition_recommend_meal  AS recommended_meals,
               a.disease_prevention        AS prevention
        """,
        {"name": entity, "limit": _DEFAULT_LIMIT},
    )


def _tmpl_linked_diseases(entity: str | None, _extra, exact: bool = False) -> tuple[str, dict]:
    if not entity:
        return (
            "MATCH (d1:Disease)-[:IS_LINKED_WITH]->(d2:Disease) "
            "RETURN d1.disease_name AS disease, d2.disease_name AS linked_disease "
            f"LIMIT {_LINKED_LIMIT}",
            {},
        )
    if exact:
        where_sort = "WHERE d1.disease_name = $name\n        "
    else:
        where_sort = (
            "WHERE toLower(d1.disease_name) CONTAINS toLower($name)\n"
            "        WITH d1, d2,\n"
            "             CASE\n"
            "               WHEN toLower(d1.disease_name) = toLower($name)               THEN 0\n"
            "               WHEN toLower(d1.disease_name) = 'bệnh ' + toLower($name)    THEN 1\n"
            "               WHEN toLower(d1.disease_name) STARTS WITH toLower($name)     THEN 2\n"
            "               ELSE 3\n"
            "             END AS match_score\n"
            "        ORDER BY match_score, d1.disease_name\n"
            "        "
        )
    return (
        f"""
        MATCH (d1:Disease)-[:IS_LINKED_WITH]->(d2:Disease)
        {where_sort}LIMIT $limit
        RETURN d1.disease_name      AS disease,
               d2.disease_name      AS linked_disease,
               d2.disease_category  AS linked_category
        """,
        {"name": entity, "limit": _LINKED_LIMIT},
    )


def _tmpl_count(_entity, _extra, _exact=False) -> tuple[str, dict]:
    return (
        """
        MATCH (d:Disease)
        WITH count(d) AS disease_count
        MATCH (s:Symptom)
        WITH disease_count, count(s) AS symptom_count
        MATCH (m:Medicine)
        WITH disease_count, symptom_count, count(m) AS medicine_count
        MATCH (t:Treatment)
        WITH disease_count, symptom_count, medicine_count, count(t) AS treatment_count
        MATCH (a:Advice)
        RETURN disease_count, symptom_count, medicine_count,
               treatment_count, count(a) AS advice_count
        """,
        {},
    )


def _tmpl_count_by_type(entity: str | None, _extra, _exact=False) -> tuple[str, dict]:
    label_map = {
        "benh": "Disease", "bệnh": "Disease", "disease": "Disease",
        "trieu chung": "Symptom", "triệu chứng": "Symptom", "symptom": "Symptom",
        "thuoc": "Medicine", "thuốc": "Medicine", "drug": "Medicine", "medicine": "Medicine",
        "dieu tri": "Treatment", "điều trị": "Treatment", "treatment": "Treatment",
        "loi khuyen": "Advice", "lời khuyên": "Advice", "advice": "Advice",
    }
    label = label_map.get((entity or "").lower().strip(), "Disease")
    return (
        f"MATCH (n:{label}) RETURN count(n) AS total, '{label}' AS node_type",
        {},
    )


def _tmpl_find_by_symptom(entity: str | None, _extra, _exact=False) -> tuple[str, dict]:
    # disease_symptom là blob string — dùng CONTAINS để tìm kiếm ngược.
    if not entity:
        return (
            "MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom) "
            "RETURN d.disease_name AS disease, s.disease_symptom AS symptoms "
            f"LIMIT {_FIND_BY_SYMPTOM_LIMIT}",
            {},
        )
    return (
        """
        MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom)
        WHERE toLower(s.disease_symptom) CONTAINS toLower($keyword)
        RETURN d.disease_name     AS disease,
               s.disease_symptom  AS symptoms,
               s.check_method     AS check_method
        ORDER BY d.disease_name
        LIMIT $limit
        """,
        {"keyword": entity, "limit": _FIND_BY_SYMPTOM_LIMIT},
    )


def _tmpl_find_by_medicine(entity: str | None, _extra, _exact=False) -> tuple[str, dict]:
    """Reverse: find diseases whose drug_common or drug_recommend contains keyword."""
    if not entity:
        return (
            "MATCH (d:Disease)-[:IS_PRESCRIBED]->(m:Medicine) "
            "RETURN d.disease_name AS disease, m.drug_common AS matched_common "
            f"LIMIT {_FIND_BY_SYMPTOM_LIMIT}",
            {},
        )
    return (
        """
        MATCH (d:Disease)-[:IS_PRESCRIBED]->(m:Medicine)
        WHERE toLower(m.drug_common) CONTAINS toLower($keyword)
           OR toLower(m.drug_recommend) CONTAINS toLower($keyword)
        RETURN d.disease_name    AS disease,
               m.drug_common     AS matched_common,
               m.drug_recommend  AS matched_recommend
        ORDER BY d.disease_name
        LIMIT $limit
        """,
        {"keyword": entity, "limit": _FIND_BY_SYMPTOM_LIMIT},
    )


def _tmpl_find_by_nutrition_avoid(entity: str | None, _extra, _exact=False) -> tuple[str, dict]:
    """Reverse: find diseases whose nutrition_not_eat contains keyword."""
    if not entity:
        return (
            "MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice) "
            "WHERE a.nutrition_not_eat IS NOT NULL "
            "RETURN d.disease_name AS disease, a.nutrition_not_eat AS matched_advice "
            f"LIMIT {_FIND_BY_SYMPTOM_LIMIT}",
            {},
        )
    return (
        """
        MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice)
        WHERE toLower(a.nutrition_not_eat) CONTAINS toLower($keyword)
        RETURN d.disease_name       AS disease,
               a.nutrition_not_eat  AS matched_advice
        ORDER BY d.disease_name
        LIMIT $limit
        """,
        {"keyword": entity, "limit": _FIND_BY_SYMPTOM_LIMIT},
    )


def _tmpl_find_by_nutrition_eat(entity: str | None, _extra, _exact=False) -> tuple[str, dict]:
    """Reverse: find diseases whose nutrition_do_eat or nutrition_recommend_meal contains keyword."""
    if not entity:
        return (
            "MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice) "
            "WHERE a.nutrition_do_eat IS NOT NULL "
            "RETURN d.disease_name AS disease, a.nutrition_do_eat AS matched_do_eat "
            f"LIMIT {_FIND_BY_SYMPTOM_LIMIT}",
            {},
        )
    return (
        """
        MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice)
        WHERE toLower(a.nutrition_do_eat) CONTAINS toLower($keyword)
           OR toLower(a.nutrition_recommend_meal) CONTAINS toLower($keyword)
        RETURN d.disease_name              AS disease,
               a.nutrition_do_eat          AS matched_do_eat,
               a.nutrition_recommend_meal  AS matched_recommend
        ORDER BY d.disease_name
        LIMIT $limit
        """,
        {"keyword": entity, "limit": _FIND_BY_SYMPTOM_LIMIT},
    )


def _tmpl_find_by_prevention(entity: str | None, _extra, _exact=False) -> tuple[str, dict]:
    """Reverse: find diseases whose disease_prevention contains keyword."""
    if not entity:
        return (
            "MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice) "
            "WHERE a.disease_prevention IS NOT NULL "
            "RETURN d.disease_name AS disease, a.disease_prevention AS matched_prevention "
            f"LIMIT {_FIND_BY_SYMPTOM_LIMIT}",
            {},
        )
    return (
        """
        MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice)
        WHERE toLower(a.disease_prevention) CONTAINS toLower($keyword)
        RETURN d.disease_name        AS disease,
               a.disease_prevention  AS matched_prevention
        ORDER BY d.disease_name
        LIMIT $limit
        """,
        {"keyword": entity, "limit": _FIND_BY_SYMPTOM_LIMIT},
    )




