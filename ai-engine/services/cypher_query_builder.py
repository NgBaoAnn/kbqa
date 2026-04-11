"""Cypher Query Builder — Generate Cypher for direct Neo4j VietMedKG lookups.

Part of Phương án C (Hybrid): When the Query Router determines that a
question is a precise entity lookup, this module generates the exact
Cypher query based on the VietMedKG schema (docs/13_GRAPH_SCHEMA_DESIGN.md).

Schema Reference:
    Nodes: Disease, Symptom, Treatment, Medicine, Advice
    Relationships: HAS_SYMPTOM, HAS_TREATMENT, IS_PRESCRIBED, HAS_ADVICE, IS_LINKED_WITH
    Key: Disease.disease_name (UNIQUE, Capitalize format)
"""

import logging

logger = logging.getLogger(__name__)


def build_cypher_query(query_type: str, disease_name: str | None = None) -> tuple[str, dict]:
    """Build a Cypher query based on the query type and disease name.

    Args:
        query_type: Type of query — one of:
            symptoms, medicine, treatment, advice, prevention,
            department, profile, count, linked_diseases
        disease_name: The disease name to look up (if applicable).

    Returns:
        Tuple of (cypher_query_string, parameters_dict).
    """
    if disease_name:
        # Normalize: capitalize first letter of each word (VietMedKG convention)
        disease_name = disease_name.strip().title()

    builders = {
        "symptoms": _build_symptoms_query,
        "medicine": _build_medicine_query,
        "treatment": _build_treatment_query,
        "advice": _build_advice_query,
        "prevention": _build_prevention_query,
        "department": _build_department_query,
        "profile": _build_profile_query,
        "linked_diseases": _build_linked_diseases_query,
        "count": _build_count_query,
    }

    builder = builders.get(query_type, _build_profile_query)
    cypher, params = builder(disease_name)

    logger.info(
        "Cypher built (type=%s, disease='%s'): %s",
        query_type,
        disease_name,
        cypher[:120],
    )

    return cypher, params


def _build_symptoms_query(disease_name: str | None) -> tuple[str, dict]:
    """Query: What are the symptoms of disease X?"""
    if not disease_name:
        return "MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom) RETURN d.disease_name, s.disease_symptom LIMIT 50", {}

    return (
        """
        MATCH (d:Disease {disease_name: $name})-[:HAS_SYMPTOM]->(s:Symptom)
        RETURN d.disease_name AS disease,
               s.disease_symptom AS symptoms,
               s.check_method AS check_method,
               s.people_easy_get AS risk_group
        """,
        {"name": disease_name},
    )


def _build_medicine_query(disease_name: str | None) -> tuple[str, dict]:
    """Query: What medicine treats disease X?"""
    if not disease_name:
        return "MATCH (d:Disease)-[:IS_PRESCRIBED]->(m:Medicine) RETURN d.disease_name, m.drug_common LIMIT 50", {}

    return (
        """
        MATCH (d:Disease {disease_name: $name})-[:IS_PRESCRIBED]->(m:Medicine)
        RETURN d.disease_name AS disease,
               m.drug_recommend AS recommended_drugs,
               m.drug_common AS common_drugs,
               m.drug_detail AS drug_details
        """,
        {"name": disease_name},
    )


def _build_treatment_query(disease_name: str | None) -> tuple[str, dict]:
    """Query: How to treat disease X?"""
    if not disease_name:
        return "MATCH (d:Disease)-[:HAS_TREATMENT]->(t:Treatment) RETURN d.disease_name, t.cure_method LIMIT 50", {}

    return (
        """
        MATCH (d:Disease {disease_name: $name})-[:HAS_TREATMENT]->(t:Treatment)
        RETURN d.disease_name AS disease,
               t.cure_method AS treatment_method,
               t.cure_department AS department,
               t.cure_probability AS cure_rate
        """,
        {"name": disease_name},
    )


def _build_advice_query(disease_name: str | None) -> tuple[str, dict]:
    """Query: What dietary advice for disease X?"""
    if not disease_name:
        return "MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice) RETURN d.disease_name, a.nutrition_do_eat LIMIT 50", {}

    return (
        """
        MATCH (d:Disease {disease_name: $name})-[:HAS_ADVICE]->(a:Advice)
        RETURN d.disease_name AS disease,
               a.nutrition_do_eat AS should_eat,
               a.nutrition_recommend_meal AS recommended_meals,
               a.nutrition_not_eat AS should_avoid,
               a.disease_prevention AS prevention
        """,
        {"name": disease_name},
    )


def _build_prevention_query(disease_name: str | None) -> tuple[str, dict]:
    """Query: How to prevent disease X?"""
    if not disease_name:
        return "MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice) RETURN d.disease_name, a.disease_prevention LIMIT 50", {}

    return (
        """
        MATCH (d:Disease {disease_name: $name})-[:HAS_ADVICE]->(a:Advice)
        RETURN d.disease_name AS disease,
               a.disease_prevention AS prevention
        """,
        {"name": disease_name},
    )


def _build_department_query(disease_name: str | None) -> tuple[str, dict]:
    """Query: Which department treats disease X?"""
    if not disease_name:
        return "MATCH (d:Disease)-[:HAS_TREATMENT]->(t:Treatment) RETURN d.disease_name, t.cure_department LIMIT 50", {}

    return (
        """
        MATCH (d:Disease {disease_name: $name})-[:HAS_TREATMENT]->(t:Treatment)
        RETURN d.disease_name AS disease,
               t.cure_department AS department
        """,
        {"name": disease_name},
    )


def _build_profile_query(disease_name: str | None) -> tuple[str, dict]:
    """Query: Full profile of disease X."""
    if not disease_name:
        return "MATCH (d:Disease) RETURN d.disease_name, d.disease_description LIMIT 20", {}

    return (
        """
        MATCH (d:Disease {disease_name: $name})
        OPTIONAL MATCH (d)-[:HAS_SYMPTOM]->(s:Symptom)
        OPTIONAL MATCH (d)-[:HAS_TREATMENT]->(t:Treatment)
        OPTIONAL MATCH (d)-[:IS_PRESCRIBED]->(m:Medicine)
        OPTIONAL MATCH (d)-[:HAS_ADVICE]->(a:Advice)
        RETURN d.disease_name AS disease,
               d.disease_description AS description,
               d.disease_category AS category,
               d.disease_cause AS cause,
               s.disease_symptom AS symptoms,
               s.check_method AS check_method,
               s.people_easy_get AS risk_group,
               t.cure_method AS treatment,
               t.cure_department AS department,
               t.cure_probability AS cure_rate,
               m.drug_recommend AS recommended_drugs,
               m.drug_common AS common_drugs,
               a.nutrition_do_eat AS should_eat,
               a.nutrition_not_eat AS should_avoid,
               a.disease_prevention AS prevention
        """,
        {"name": disease_name},
    )


def _build_linked_diseases_query(disease_name: str | None) -> tuple[str, dict]:
    """Query: What diseases are linked to disease X?"""
    if not disease_name:
        return "MATCH (d1:Disease)-[:IS_LINKED_WITH]->(d2:Disease) RETURN d1.disease_name, d2.disease_name LIMIT 50", {}

    return (
        """
        MATCH (d:Disease {disease_name: $name})-[:IS_LINKED_WITH]->(linked:Disease)
        RETURN d.disease_name AS disease,
               linked.disease_name AS linked_disease,
               linked.disease_description AS linked_description
        """,
        {"name": disease_name},
    )


def _build_count_query(_disease_name: str | None) -> tuple[str, dict]:
    """Query: How many diseases, symptoms, etc."""
    return (
        """
        MATCH (d:Disease) WITH count(d) AS disease_count
        MATCH (:Disease)-[:HAS_SYMPTOM]->(s:Symptom)
        WITH disease_count, count(s) AS symptom_count
        MATCH (:Disease)-[:IS_PRESCRIBED]->(m:Medicine)
        WITH disease_count, symptom_count, count(m) AS medicine_count
        MATCH (:Disease)-[:HAS_TREATMENT]->(t:Treatment)
        RETURN disease_count,
               symptom_count,
               medicine_count,
               count(t) AS treatment_count
        """,
        {},
    )


def format_cypher_result_as_text(
    query_type: str,
    disease_name: str | None,
    records: list[dict],
) -> str:
    """Convert Cypher query results into a Vietnamese natural language text.

    This replaces the LLM Data-to-Text step for Cypher path queries,
    providing deterministic formatting.

    Args:
        query_type: The type of query that was executed.
        disease_name: The disease being queried.
        records: The raw result records from Neo4j.

    Returns:
        A formatted Vietnamese text string.
    """
    if not records:
        return f"Không tìm thấy thông tin về '{disease_name}' trong cơ sở dữ liệu."

    r = records[0]  # VietMedKG star schema: 1 disease → 1 record per relationship

    formatters = {
        "symptoms": _fmt_symptoms,
        "medicine": _fmt_medicine,
        "treatment": _fmt_treatment,
        "advice": _fmt_advice,
        "prevention": _fmt_prevention,
        "department": _fmt_department,
        "profile": _fmt_profile,
        "linked_diseases": _fmt_linked,
        "count": _fmt_count,
    }

    formatter = formatters.get(query_type, _fmt_profile)
    return formatter(disease_name, r, records)


def _safe(value: object) -> str:
    """Safe string conversion, returning empty string for None."""
    if value is None:
        return ""
    return str(value).strip()


def _fmt_symptoms(name: str | None, r: dict, _records: list) -> str:
    symptoms = _safe(r.get("symptoms"))
    check = _safe(r.get("check_method"))
    risk = _safe(r.get("risk_group"))

    parts = [f"Bệnh {name or r.get('disease', 'N/A')} có các triệu chứng sau:"]
    if symptoms:
        parts.append(f"\n📋 Triệu chứng: {symptoms}")
    if check:
        parts.append(f"\n🔍 Phương pháp kiểm tra: {check}")
    if risk:
        parts.append(f"\n⚠️ Đối tượng dễ mắc: {risk}")
    return "".join(parts)


def _fmt_medicine(name: str | None, r: dict, _records: list) -> str:
    parts = [f"Thuốc điều trị bệnh {name or r.get('disease', 'N/A')}:"]
    rec = _safe(r.get("recommended_drugs"))
    common = _safe(r.get("common_drugs"))
    detail = _safe(r.get("drug_details"))

    if rec:
        parts.append(f"\n💊 Thuốc đề xuất: {rec}")
    if common:
        parts.append(f"\n💊 Thuốc phổ biến: {common}")
    if detail:
        parts.append(f"\nℹ️ Chi tiết: {detail}")
    return "".join(parts)


def _fmt_treatment(name: str | None, r: dict, _records: list) -> str:
    parts = [f"Phương pháp điều trị bệnh {name or r.get('disease', 'N/A')}:"]
    method = _safe(r.get("treatment_method"))
    dept = _safe(r.get("department"))
    rate = _safe(r.get("cure_rate"))

    if method:
        parts.append(f"\n💉 Phương pháp: {method}")
    if dept:
        parts.append(f"\n🏥 Khoa điều trị: {dept}")
    if rate:
        parts.append(f"\n📊 Tỉ lệ chữa khỏi: {rate}")
    return "".join(parts)


def _fmt_advice(name: str | None, r: dict, _records: list) -> str:
    parts = [f"Lời khuyên dinh dưỡng cho bệnh {name or r.get('disease', 'N/A')}:"]
    eat = _safe(r.get("should_eat"))
    meal = _safe(r.get("recommended_meals"))
    avoid = _safe(r.get("should_avoid"))
    prev = _safe(r.get("prevention"))

    if eat:
        parts.append(f"\n✅ Nên ăn: {eat}")
    if meal:
        parts.append(f"\n🍽️ Món ăn đề xuất: {meal}")
    if avoid:
        parts.append(f"\n❌ Không nên ăn: {avoid}")
    if prev:
        parts.append(f"\n🛡️ Cách phòng tránh: {prev}")
    return "".join(parts)


def _fmt_prevention(name: str | None, r: dict, _records: list) -> str:
    prev = _safe(r.get("prevention"))
    if prev:
        return f"Cách phòng tránh bệnh {name or r.get('disease', 'N/A')}:\n🛡️ {prev}"
    return f"Không tìm thấy thông tin phòng tránh cho bệnh {name or 'N/A'}."


def _fmt_department(name: str | None, r: dict, _records: list) -> str:
    dept = _safe(r.get("department"))
    if dept:
        return f"Bệnh {name or r.get('disease', 'N/A')} được khám và điều trị tại: 🏥 {dept}."
    return f"Không tìm thấy thông tin khoa điều trị cho bệnh {name or 'N/A'}."


def _fmt_profile(name: str | None, r: dict, _records: list) -> str:
    dn = name or _safe(r.get("disease"))
    parts = [f"📋 THÔNG TIN BỆNH: {dn}\n"]

    desc = _safe(r.get("description"))
    if desc:
        parts.append(f"Mô tả: {desc}\n")

    cat = _safe(r.get("category"))
    if cat:
        parts.append(f"Loại bệnh: {cat}\n")

    cause = _safe(r.get("cause"))
    if cause:
        parts.append(f"Nguyên nhân: {cause}\n")

    symptoms = _safe(r.get("symptoms"))
    if symptoms:
        parts.append(f"Triệu chứng: {symptoms}\n")

    treatment = _safe(r.get("treatment"))
    if treatment:
        parts.append(f"Điều trị: {treatment}\n")

    dept = _safe(r.get("department"))
    if dept:
        parts.append(f"Khoa điều trị: {dept}\n")

    rate = _safe(r.get("cure_rate"))
    if rate:
        parts.append(f"Tỉ lệ chữa khỏi: {rate}\n")

    drugs = _safe(r.get("recommended_drugs"))
    if drugs:
        parts.append(f"Thuốc đề xuất: {drugs}\n")

    eat = _safe(r.get("should_eat"))
    if eat:
        parts.append(f"Nên ăn: {eat}\n")

    avoid = _safe(r.get("should_avoid"))
    if avoid:
        parts.append(f"Không nên ăn: {avoid}\n")

    prev = _safe(r.get("prevention"))
    if prev:
        parts.append(f"Phòng tránh: {prev}\n")

    return "".join(parts).strip()


def _fmt_linked(name: str | None, _r: dict, records: list) -> str:
    diseases = [_safe(r.get("linked_disease")) for r in records if r.get("linked_disease")]
    if diseases:
        items = ", ".join(diseases)
        return f"Bệnh {name or 'N/A'} có liên quan đến các bệnh: {items}."
    return f"Không tìm thấy bệnh đi kèm cho {name or 'N/A'}."


def _fmt_count(_name: str | None, r: dict, _records: list) -> str:
    return (
        f"📊 Thống kê cơ sở dữ liệu VietMedKG:\n"
        f"  • Số bệnh: {r.get('disease_count', 'N/A')}\n"
        f"  • Số triệu chứng: {r.get('symptom_count', 'N/A')}\n"
        f"  • Số thuốc: {r.get('medicine_count', 'N/A')}\n"
        f"  • Số phương pháp điều trị: {r.get('treatment_count', 'N/A')}"
    )
