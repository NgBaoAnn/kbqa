"""Cypher Query Builder — Template library cho VietMedKG.

Cung cấp pre-validated Cypher templates cho các query type phổ biến.
Được gọi TRƯỚC khi dùng LLM Text2Cypher.

Ghi chú schema (đã kiểm tra trực tiếp trên Neo4j):
- Mỗi Disease có đúng 1 Symptom node (UNIQUE constraint trên Symptom.disease_name).
  Triệu chứng lưu dạng blob string trong disease_symptom, không phải individual nodes.
  Pattern shared-symptom (d1)-[:HAS_SYMPTOM]->(s)<-[:HAS_SYMPTOM]-(d2) không hoạt động.
- 38% Advice nodes chỉ có disease_prevention, không có nutrition fields.
- IS_LINKED_WITH được import một chiều từ ETL; query dùng undirected để bắt cả hai hướng.
- Matching ưu tiên exact → prefixed-exact → starts-with → contains (tiered matching).
"""

import logging

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 5
_LINKED_LIMIT = 10
_REVERSE_QUERY_LIMIT = 10


def _tiered_where(alias: str, exact: bool, carry: tuple[str, ...] = ()) -> str:
    """Return WHERE + optional tiered-sort block for entity-name matching.

    Args:
        alias:  Main node variable (e.g. 'd', 'd1').
        exact:  When True, use equality match only — no scoring/sorting needed.
        carry:  Additional variables to carry through the WITH clause besides alias.
    """
    if exact:
        return f"WHERE {alias}.disease_name = $name\n        "
    carry_str = "".join(f", {v}" for v in carry)
    return (
        f"WHERE toLower({alias}.disease_name) CONTAINS toLower($name)\n"
        f"        WITH {alias}{carry_str},\n"
        f"             CASE\n"
        f"               WHEN toLower({alias}.disease_name) = toLower($name)               THEN 0\n"
        f"               WHEN toLower({alias}.disease_name) = 'bệnh ' + toLower($name)    THEN 1\n"
        f"               WHEN toLower({alias}.disease_name) STARTS WITH toLower($name)     THEN 2\n"
        f"               ELSE 3\n"
        f"             END AS match_score\n"
        f"        ORDER BY match_score, {alias}.disease_name\n"
        f"        "
    )


def _token_relevance(field: str, keyword_param: str = "$keyword") -> str:
    """Return a CASE expression scoring how precisely `field` contains the keyword.

    Score 0 = keyword is a distinct token (preceded by comma or at field start).
    Score 1 = keyword appears as a substring only.

    Both ', keyword' and ',keyword' patterns are tested to handle inconsistent
    spacing in the source data (some entries use comma+space, others just comma).
    """
    kw = f"toLower({keyword_param})"
    f_lo = f"toLower({field})"
    return (
        f"CASE\n"
        f"               WHEN {f_lo} STARTS WITH {kw} THEN 0\n"
        f"               WHEN {f_lo} CONTAINS (', ' + {kw}) THEN 0\n"
        f"               WHEN {f_lo} CONTAINS (',' + {kw}) THEN 0\n"
        f"               ELSE 1\n"
        f"             END"
    )


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
        "linked_with_info":      _tmpl_linked_with_info,
        "compare_diseases":      _tmpl_compare_diseases,
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


# ── Templates ──────────────────────────────────────────────────────────────────

def _tmpl_symptoms(entity: str | None, _extra, exact: bool = False) -> tuple[str, dict]:
    if not entity:
        return (
            "MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom) "
            "RETURN d.disease_name AS disease, s.disease_symptom AS symptoms, "
            f"s.check_method AS check_method, s.people_easy_get AS risk_group "
            f"LIMIT {_DEFAULT_LIMIT}",
            {},
        )
    wf = _tiered_where("d", exact, ("s",))
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
            "RETURN d.disease_name AS disease, m.drug_common AS common_drugs, "
            "m.drug_recommend AS recommended_drugs, m.drug_detail AS drug_detail "
            f"LIMIT {_DEFAULT_LIMIT}",
            {},
        )
    wf = _tiered_where("d", exact, ("m",))
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
            "RETURN d.disease_name AS disease, t.cure_method AS treatment_method, "
            "t.cure_department AS department, t.cure_probability AS cure_rate "
            f"LIMIT {_DEFAULT_LIMIT}",
            {},
        )
    wf = _tiered_where("d", exact, ("t",))
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
            "a.nutrition_do_eat AS should_eat, a.nutrition_not_eat AS should_avoid, "
            "a.nutrition_recommend_meal AS recommended_meals, "
            "a.disease_prevention AS prevention "
            f"LIMIT {_DEFAULT_LIMIT}",
            {},
        )
    wf = _tiered_where("d", exact, ("a",))
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
    wf = _tiered_where("d", exact, ("a",))
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
    wf = _tiered_where("d", exact, ("t",))
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
    wf = _tiered_where("d", exact)
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
    # Undirected match để bắt cả hai chiều của IS_LINKED_WITH.
    # ETL chỉ import một chiều nên dùng hướng có hướng sẽ bỏ sót bệnh link ngược.
    if not entity:
        return (
            "MATCH (d1:Disease)-[:IS_LINKED_WITH]-(d2:Disease) "
            "RETURN d1.disease_name AS disease, d2.disease_name AS linked_disease "
            f"LIMIT {_LINKED_LIMIT}",
            {},
        )
    wf = _tiered_where("d1", exact, ("d2",))
    return (
        f"""
        MATCH (d1:Disease)-[:IS_LINKED_WITH]-(d2:Disease)
        {wf}LIMIT $limit
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
        WITH disease_count, symptom_count, medicine_count, treatment_count, count(a) AS advice_count
        MATCH ()-[r:IS_LINKED_WITH]->()
        RETURN disease_count, symptom_count, medicine_count,
               treatment_count, advice_count, count(r) AS linked_count
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
            f"LIMIT {_REVERSE_QUERY_LIMIT}",
            {},
        )
    relevance = _token_relevance("s.disease_symptom")
    return (
        f"""
        MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom)
        WHERE toLower(s.disease_symptom) CONTAINS toLower($keyword)
        WITH d, s,
             {relevance} AS relevance
        ORDER BY relevance, d.disease_name
        LIMIT $limit
        RETURN d.disease_name     AS disease,
               s.disease_symptom  AS symptoms,
               s.check_method     AS check_method
        """,
        {"keyword": entity, "limit": _REVERSE_QUERY_LIMIT},
    )


def _tmpl_find_by_medicine(entity: str | None, _extra, _exact=False) -> tuple[str, dict]:
    """Reverse: find diseases whose drug_common or drug_recommend contains keyword."""
    if not entity:
        return (
            "MATCH (d:Disease)-[:IS_PRESCRIBED]->(m:Medicine) "
            "RETURN d.disease_name AS disease, m.drug_common AS matched_common "
            f"LIMIT {_REVERSE_QUERY_LIMIT}",
            {},
        )
    rel_common = _token_relevance("m.drug_common")
    rel_recommend = _token_relevance("m.drug_recommend")
    return (
        f"""
        MATCH (d:Disease)-[:IS_PRESCRIBED]->(m:Medicine)
        WHERE toLower(m.drug_common) CONTAINS toLower($keyword)
           OR toLower(m.drug_recommend) CONTAINS toLower($keyword)
        WITH d, m,
             CASE
               WHEN ({rel_common}) = 0 OR ({rel_recommend}) = 0 THEN 0
               ELSE 1
             END AS relevance
        ORDER BY relevance, d.disease_name
        LIMIT $limit
        RETURN d.disease_name    AS disease,
               m.drug_common     AS matched_common,
               m.drug_recommend  AS matched_recommend
        """,
        {"keyword": entity, "limit": _REVERSE_QUERY_LIMIT},
    )


def _tmpl_find_by_nutrition_avoid(entity: str | None, _extra, _exact=False) -> tuple[str, dict]:
    """Reverse: find diseases whose nutrition_not_eat contains keyword."""
    if not entity:
        return (
            "MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice) "
            "WHERE a.nutrition_not_eat IS NOT NULL "
            "RETURN d.disease_name AS disease, a.nutrition_not_eat AS matched_advice "
            f"LIMIT {_REVERSE_QUERY_LIMIT}",
            {},
        )
    relevance = _token_relevance("a.nutrition_not_eat")
    return (
        f"""
        MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice)
        WHERE toLower(a.nutrition_not_eat) CONTAINS toLower($keyword)
        WITH d, a,
             {relevance} AS relevance
        ORDER BY relevance, d.disease_name
        LIMIT $limit
        RETURN d.disease_name       AS disease,
               a.nutrition_not_eat  AS matched_advice
        """,
        {"keyword": entity, "limit": _REVERSE_QUERY_LIMIT},
    )


def _tmpl_find_by_nutrition_eat(entity: str | None, _extra, _exact=False) -> tuple[str, dict]:
    """Reverse: find diseases whose nutrition_do_eat or nutrition_recommend_meal contains keyword."""
    if not entity:
        return (
            "MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice) "
            "WHERE a.nutrition_do_eat IS NOT NULL "
            "RETURN d.disease_name AS disease, a.nutrition_do_eat AS matched_do_eat "
            f"LIMIT {_REVERSE_QUERY_LIMIT}",
            {},
        )
    rel_do = _token_relevance("a.nutrition_do_eat")
    rel_rec = _token_relevance("a.nutrition_recommend_meal")
    return (
        f"""
        MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice)
        WHERE toLower(a.nutrition_do_eat) CONTAINS toLower($keyword)
           OR toLower(a.nutrition_recommend_meal) CONTAINS toLower($keyword)
        WITH d, a,
             CASE
               WHEN ({rel_do}) = 0 OR ({rel_rec}) = 0 THEN 0
               ELSE 1
             END AS relevance
        ORDER BY relevance, d.disease_name
        LIMIT $limit
        RETURN d.disease_name              AS disease,
               a.nutrition_do_eat          AS matched_do_eat,
               a.nutrition_recommend_meal  AS matched_recommend
        """,
        {"keyword": entity, "limit": _REVERSE_QUERY_LIMIT},
    )


def _tmpl_find_by_prevention(entity: str | None, _extra, _exact=False) -> tuple[str, dict]:
    """Reverse: find diseases whose disease_prevention contains keyword."""
    if not entity:
        return (
            "MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice) "
            "WHERE a.disease_prevention IS NOT NULL "
            "RETURN d.disease_name AS disease, a.disease_prevention AS matched_prevention "
            f"LIMIT {_REVERSE_QUERY_LIMIT}",
            {},
        )
    relevance = _token_relevance("a.disease_prevention")
    return (
        f"""
        MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice)
        WHERE toLower(a.disease_prevention) CONTAINS toLower($keyword)
        WITH d, a,
             {relevance} AS relevance
        ORDER BY relevance, d.disease_name
        LIMIT $limit
        RETURN d.disease_name        AS disease,
               a.disease_prevention  AS matched_prevention
        """,
        {"keyword": entity, "limit": _REVERSE_QUERY_LIMIT},
    )


def _tmpl_linked_with_info(entity: str | None, _extra, exact: bool = False) -> tuple[str, dict]:
    # Undirected match để bắt cả hai chiều của IS_LINKED_WITH.
    if not entity:
        return (
            "MATCH (d1:Disease)-[:IS_LINKED_WITH]-(d2:Disease) "
            "RETURN d1.disease_name AS source_disease, d2.disease_name AS linked_disease "
            f"LIMIT {_LINKED_LIMIT}",
            {},
        )
    wf = _tiered_where("d1", exact, ("d2",))
    return (
        f"""
        MATCH (d1:Disease)-[:IS_LINKED_WITH]-(d2:Disease)
        {wf}LIMIT $limit
        OPTIONAL MATCH (d2)-[:HAS_SYMPTOM]->(s2:Symptom)
        OPTIONAL MATCH (d2)-[:HAS_TREATMENT]->(t2:Treatment)
        RETURN d1.disease_name     AS source_disease,
               d2.disease_name     AS linked_disease,
               s2.disease_symptom  AS linked_symptoms,
               t2.cure_method      AS linked_treatment,
               t2.cure_department  AS linked_department
        """,
        {"name": entity, "limit": _LINKED_LIMIT},
    )


def _tmpl_compare_diseases(entity: str | None, extra: str | None, _exact=False) -> tuple[str, dict]:
    # Symptoms là blob 1:1 với Disease — không thể tìm shared symptoms trong Cypher.
    # Template trả về cả hai blob để LLM synthesizer tổng hợp điểm chung/khác.
    return (
        """
        MATCH (d1:Disease)-[:HAS_SYMPTOM]->(s1:Symptom)
        WHERE toLower(d1.disease_name) CONTAINS toLower($name1)
        MATCH (d2:Disease)-[:HAS_SYMPTOM]->(s2:Symptom)
        WHERE toLower(d2.disease_name) CONTAINS toLower($name2)
        RETURN d1.disease_name     AS disease1,
               s1.disease_symptom  AS symptoms1,
               d2.disease_name     AS disease2,
               s2.disease_symptom  AS symptoms2
        LIMIT 5
        """,
        {"name1": entity or "", "name2": extra or ""},
    )
