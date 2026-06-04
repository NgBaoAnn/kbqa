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


def _tmpl_linked_with_info(entity: str | None, _extra, exact: bool = False) -> tuple[str, dict]:
    if not entity:
        return (
            "MATCH (d1:Disease)-[:IS_LINKED_WITH]->(d2:Disease) "
            "RETURN d1.disease_name AS source_disease, d2.disease_name AS linked_disease "
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


# ── Deterministic text formatter ───────────────────────────────────────────

def format_cypher_result_as_text(
    query_type: str,
    entity: str | None,
    records: list[dict],
) -> str:
    """Chuyển kết quả Cypher thành văn bản tiếng Việt (không dùng LLM)."""
    if not records:
        return f"Không tìm thấy thông tin về '{entity}' trong cơ sở dữ liệu."

    formatters = {
        "symptoms":              _fmt_symptoms,
        "medicine":              _fmt_medicine,
        "treatment":             _fmt_treatment,
        "advice":                _fmt_advice,
        "prevention":            _fmt_prevention,
        "department":            _fmt_department,
        "profile":               _fmt_profile,
        "linked_diseases":       _fmt_linked_diseases,
        "count":                 _fmt_count,
        "count_by_type":         _fmt_count_by_type,
        "find_by_symptom":       _fmt_find_by_symptom,
        "find_by_medicine":      _fmt_find_by_medicine,
        "find_by_nutrition_avoid": _fmt_find_by_nutrition_avoid,
        "find_by_nutrition_eat": _fmt_find_by_nutrition_eat,
        "find_by_prevention":    _fmt_find_by_prevention,
        "linked_with_info":      _fmt_linked_with_info,
    }

    formatter = formatters.get(query_type, _fmt_generic)
    return formatter(entity, records)


def _safe(value: object) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    return "" if s in ("None", "null", "nan") else s


def _fmt_symptoms(entity: str | None, records: list[dict]) -> str:
    label = entity or records[0].get("disease", "")
    lines = [f"Triệu chứng bệnh {label}:"]
    for r in records:
        disease = _safe(r.get("disease"))
        if disease and len(records) > 1:
            lines.append(f"\n{disease}:")
        symptoms = _safe(r.get("symptoms"))
        if symptoms:
            lines.append(f"\n  Triệu chứng: {symptoms}")
        check = _safe(r.get("check_method"))
        if check:
            lines.append(f"\n  Phương pháp kiểm tra: {check}")
        risk = _safe(r.get("risk_group"))
        if risk:
            lines.append(f"\n  Đối tượng dễ mắc: {risk}")
    return "".join(lines)


def _fmt_medicine(entity: str | None, records: list[dict]) -> str:
    label = entity or records[0].get("disease", "")
    lines = [f"Thuốc điều trị bệnh {label}:"]
    for r in records:
        disease = _safe(r.get("disease"))
        if disease and len(records) > 1:
            lines.append(f"\n{disease}:")
        rec = _safe(r.get("recommended_drugs"))
        if rec:
            lines.append(f"\n  Thuốc đề xuất: {rec}")
        common = _safe(r.get("common_drugs"))
        if common:
            lines.append(f"\n  Thuốc phổ biến: {common}")
        detail = _safe(r.get("drug_detail"))
        if detail:
            lines.append(f"\n  Chi tiết: {detail[:200]}")
    return "".join(lines)


def _fmt_treatment(entity: str | None, records: list[dict]) -> str:
    label = entity or records[0].get("disease", "")
    lines = [f"Phương pháp điều trị bệnh {label}:"]
    for r in records:
        disease = _safe(r.get("disease"))
        if disease and len(records) > 1:
            lines.append(f"\n{disease}:")
        method = _safe(r.get("treatment_method"))
        if method:
            lines.append(f"\n  Phương pháp: {method}")
        dept = _safe(r.get("department"))
        if dept:
            lines.append(f"\n  Khoa điều trị: {dept}")
        rate = _safe(r.get("cure_rate"))
        if rate:
            lines.append(f"\n  Tỉ lệ khỏi bệnh: {rate}")
    return "".join(lines)


def _fmt_advice(entity: str | None, records: list[dict]) -> str:
    label = entity or records[0].get("disease", "")
    lines = [f"Lời khuyên cho bệnh {label}:"]
    for r in records:
        eat = _safe(r.get("should_eat"))
        if eat:
            lines.append(f"\n  Nên ăn: {eat}")
        avoid = _safe(r.get("should_avoid"))
        if avoid:
            lines.append(f"\n  Không nên ăn: {avoid}")
        meal = _safe(r.get("recommended_meals"))
        if meal:
            lines.append(f"\n  Thực đơn gợi ý: {meal}")
        prev = _safe(r.get("prevention"))
        if prev:
            lines.append(f"\n  Phòng tránh: {prev}")
    return "".join(lines)


def _fmt_prevention(entity: str | None, records: list[dict]) -> str:
    label = entity or records[0].get("disease", "")
    lines = [f"Cách phòng tránh bệnh {label}:"]
    for r in records:
        prev = _safe(r.get("prevention"))
        if prev:
            lines.append(f"\n{prev}")
    if len(lines) == 1:
        return f"Không có thông tin phòng tránh cho bệnh {label}."
    return "".join(lines)


def _fmt_department(entity: str | None, records: list[dict]) -> str:
    depts = sorted({_safe(r.get("department")) for r in records if r.get("department")})
    if depts:
        return f"Bệnh {entity} được điều trị tại: {', '.join(depts)}."
    return f"Không tìm thấy khoa điều trị cho bệnh {entity}."


def _fmt_profile(entity: str | None, records: list[dict]) -> str:
    lines = []
    for r in records:
        disease = _safe(r.get("disease")) or entity or "N/A"
        lines.append(f"Thông tin bệnh: {disease}")
        for field, label in [
            ("description",      "Mô tả"),
            ("category",         "Chuyên khoa"),
            ("cause",            "Nguyên nhân"),
            ("symptoms",         "Triệu chứng"),
            ("check_method",     "Phương pháp kiểm tra"),
            ("risk_group",       "Đối tượng dễ mắc"),
            ("treatment_method", "Phương pháp điều trị"),
            ("department",       "Khoa điều trị"),
            ("cure_rate",        "Tỉ lệ khỏi bệnh"),
            ("recommended_drugs","Thuốc đề xuất"),
            ("common_drugs",     "Thuốc phổ biến"),
            ("should_eat",       "Nên ăn"),
            ("should_avoid",     "Không nên ăn"),
            ("prevention",       "Phòng tránh"),
        ]:
            val = _safe(r.get(field))
            if val:
                lines.append(f"- {label}: {val}")
        lines.append("")
    return "\n".join(lines).strip()


def _fmt_linked_diseases(entity: str | None, records: list[dict]) -> str:
    diseases = [_safe(r.get("linked_disease")) for r in records if r.get("linked_disease")]
    if not diseases:
        return f"Không tìm thấy bệnh liên quan đến {entity}."
    items = "\n  - ".join(diseases)
    return f"Bệnh liên quan đến {entity}:\n  - {items}"


def _fmt_count(_entity, records: list[dict]) -> str:
    if not records:
        return "Không có thông tin thống kê."
    r = records[0]
    return (
        f"Thống kê VietMedKG:\n"
        f"  Bệnh (Disease): {r.get('disease_count', 'N/A')}\n"
        f"  Triệu chứng (Symptom): {r.get('symptom_count', 'N/A')}\n"
        f"  Thuốc (Medicine): {r.get('medicine_count', 'N/A')}\n"
        f"  Điều trị (Treatment): {r.get('treatment_count', 'N/A')}\n"
        f"  Lời khuyên (Advice): {r.get('advice_count', 'N/A')}"
    )


def _fmt_count_by_type(_entity, records: list[dict]) -> str:
    if not records:
        return "Không có thông tin thống kê."
    r = records[0]
    return f"Tổng số {r.get('node_type', '')}: {r.get('total', 'N/A')}"


def _fmt_find_by_symptom(entity: str | None, records: list[dict]) -> str:
    diseases = [_safe(r.get("disease")) for r in records if r.get("disease")]
    if not diseases:
        return f"Không tìm thấy bệnh nào có triệu chứng '{entity}'."
    items = "\n  - ".join(diseases)
    return f"Bệnh có triệu chứng '{entity}':\n  - {items}"


def _fmt_find_by_medicine(entity: str | None, records: list[dict]) -> str:
    if not records:
        return f"Không tìm thấy bệnh nào dùng thuốc '{entity}'."
    lines = [f"Bệnh dùng thuốc '{entity}':"]
    for r in records:
        disease = _safe(r.get("disease"))
        if not disease:
            continue
        drug = _safe(r.get("matched_common")) or _safe(r.get("matched_recommend"))
        if drug:
            lines.append(f"\n  - {disease}: {drug[:120]}")
        else:
            lines.append(f"\n  - {disease}")
    return "".join(lines) if len(lines) > 1 else f"Không tìm thấy bệnh nào dùng thuốc '{entity}'."


def _fmt_find_by_nutrition_avoid(entity: str | None, records: list[dict]) -> str:
    if not records:
        return f"Không tìm thấy bệnh nào cần kiêng '{entity}'."
    diseases = [_safe(r.get("disease")) for r in records if r.get("disease")]
    if not diseases:
        return f"Không tìm thấy bệnh nào cần kiêng '{entity}'."
    items = "\n  - ".join(diseases)
    return f"Bệnh cần kiêng '{entity}':\n  - {items}"


def _fmt_find_by_nutrition_eat(entity: str | None, records: list[dict]) -> str:
    if not records:
        return f"Không tìm thấy bệnh nào nên ăn '{entity}'."
    diseases = [_safe(r.get("disease")) for r in records if r.get("disease")]
    if not diseases:
        return f"Không tìm thấy bệnh nào nên ăn '{entity}'."
    items = "\n  - ".join(diseases)
    return f"Bệnh nên ăn '{entity}':\n  - {items}"


def _fmt_find_by_prevention(entity: str | None, records: list[dict]) -> str:
    if not records:
        return f"Không tìm thấy bệnh nào phòng ngừa bằng '{entity}'."
    diseases = [_safe(r.get("disease")) for r in records if r.get("disease")]
    if not diseases:
        return f"Không tìm thấy bệnh nào phòng ngừa bằng '{entity}'."
    items = "\n  - ".join(diseases)
    return f"Bệnh phòng ngừa bằng '{entity}':\n  - {items}"


def _fmt_linked_with_info(entity: str | None, records: list[dict]) -> str:
    lines = [f"Bệnh liên quan đến {entity} và thông tin của chúng:"]
    for r in records:
        linked = _safe(r.get("linked_disease"))
        if not linked:
            continue
        lines.append(f"\n\n{linked}:")
        symptoms = _safe(r.get("linked_symptoms"))
        if symptoms:
            lines.append(f"\n  Triệu chứng: {symptoms[:150]}")
        treatment = _safe(r.get("linked_treatment"))
        if treatment:
            lines.append(f"\n  Điều trị: {treatment}")
    return "".join(lines)


def _fmt_generic(entity: str | None, records: list[dict]) -> str:
    lines = [f"Kết quả tìm kiếm cho '{entity}':"]
    for i, r in enumerate(records[:10], 1):
        lines.append(f"\n[{i}]")
        for k, v in r.items():
            val = _safe(v)
            if val:
                lines.append(f"  {k}: {val[:200]}")
    return "".join(lines)
