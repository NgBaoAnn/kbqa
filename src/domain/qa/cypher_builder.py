"""Pure Cypher template builder for VietMedKG question intents."""

from __future__ import annotations

from collections.abc import Callable

DEFAULT_LIMIT = 5
LINKED_LIMIT = 10
REVERSE_QUERY_LIMIT = 10

CypherTemplate = Callable[[str | None, str | None, bool], tuple[str | None, dict | None]]


SCHEMA_PROMPT = """You are a Cypher expert. Convert the user's medical question into a read-only Cypher query for VietMedKG.
Use only these labels: Disease, Symptom, Treatment, Medicine, Advice.
Use only these relationships: HAS_SYMPTOM, HAS_TREATMENT, IS_PRESCRIBED, HAS_ADVICE, IS_LINKED_WITH.
Always use MATCH/OPTIONAL MATCH/WHERE/WITH/RETURN and add a LIMIT. Never generate writes or destructive clauses."""


def _tiered_where(alias: str, exact: bool, carry: tuple[str, ...] = ()) -> str:
    carry_str = "".join(f", {v}" for v in carry)
    if exact:
        return f"WHERE {alias}.disease_name = $name\n        WITH {alias}{carry_str}\n        "
    return (
        f"WHERE toLower({alias}.disease_name) CONTAINS toLower($name)\n"
        f"        WITH {alias}{carry_str},\n"
        f"             CASE\n"
        f"               WHEN toLower({alias}.disease_name) = toLower($name) THEN 0\n"
        f"               WHEN toLower({alias}.disease_name) = 'bệnh ' + toLower($name) THEN 1\n"
        f"               WHEN toLower({alias}.disease_name) STARTS WITH toLower($name) THEN 2\n"
        f"               ELSE 3\n"
        f"             END AS match_score\n"
        f"        ORDER BY match_score, {alias}.disease_name\n"
        f"        "
    )


def _token_relevance(field: str, keyword_param: str = "$keyword") -> str:
    kw = f"toLower({keyword_param})"
    f_lo = f"toLower({field})"
    return (
        "CASE\n"
        f"               WHEN {f_lo} STARTS WITH {kw} THEN 0\n"
        f"               WHEN {f_lo} CONTAINS (', ' + {kw}) THEN 0\n"
        f"               WHEN {f_lo} CONTAINS (',' + {kw}) THEN 0\n"
        "               ELSE 1\n"
        "             END"
    )


def build_cypher_query(
    query_type: str | None,
    entity: str | None = None,
    extra: str | None = None,
    exact: bool = False,
) -> tuple[str | None, dict | None]:
    """Return ``(cypher, params)`` for known query types, otherwise ``(None, None)``."""
    builder = _BUILDERS.get(query_type or "")
    if builder is None:
        return None, None
    return builder(entity, extra, exact)


def _tmpl_symptoms(entity: str | None, _extra: str | None, exact: bool = False):
    if not entity:
        return (
            "MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom) "
            "RETURN d.disease_name AS disease, s.disease_symptom AS symptoms, "
            "s.check_method AS check_method, s.people_easy_get AS risk_group "
            f"LIMIT {DEFAULT_LIMIT}",
            {},
        )
    wf = _tiered_where("d", exact, ("s",))
    return (
        f"""MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom)
        {wf}LIMIT $limit
        RETURN d.disease_name AS disease, s.disease_symptom AS symptoms,
               s.check_method AS check_method, s.people_easy_get AS risk_group""",
        {"name": entity, "limit": DEFAULT_LIMIT},
    )


def _tmpl_medicine(entity: str | None, _extra: str | None, exact: bool = False):
    rel = "IS_PRESCRIBED"
    if not entity:
        return (
            f"MATCH (d:Disease)-[:{rel}]->(m:Medicine) "
            "RETURN d.disease_name AS disease, m.drug_common AS common_drugs, "
            f"m.drug_recommend AS recommended_drugs, m.drug_detail AS drug_detail LIMIT {DEFAULT_LIMIT}",
            {},
        )
    wf = _tiered_where("d", exact, ("m",))
    return (
        f"""MATCH (d:Disease)-[:{rel}]->(m:Medicine)
        {wf}LIMIT $limit
        RETURN d.disease_name AS disease, m.drug_recommend AS recommended_drugs,
               m.drug_common AS common_drugs, m.drug_detail AS drug_detail""",
        {"name": entity, "limit": DEFAULT_LIMIT},
    )


def _tmpl_treatment(entity: str | None, _extra: str | None, exact: bool = False):
    if not entity:
        return (
            "MATCH (d:Disease)-[:HAS_TREATMENT]->(t:Treatment) "
            "RETURN d.disease_name AS disease, t.cure_method AS treatment_method, "
            f"t.cure_department AS department, t.cure_probability AS cure_rate LIMIT {DEFAULT_LIMIT}",
            {},
        )
    wf = _tiered_where("d", exact, ("t",))
    return (
        f"""MATCH (d:Disease)-[:HAS_TREATMENT]->(t:Treatment)
        {wf}LIMIT $limit
        RETURN d.disease_name AS disease, t.cure_method AS treatment_method,
               t.cure_department AS department, t.cure_probability AS cure_rate""",
        {"name": entity, "limit": DEFAULT_LIMIT},
    )


def _tmpl_advice(entity: str | None, _extra: str | None, exact: bool = False):
    if not entity:
        return (
            "MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice) RETURN d.disease_name AS disease, "
            "a.nutrition_do_eat AS should_eat, a.nutrition_not_eat AS should_avoid, "
            f"a.nutrition_recommend_meal AS recommended_meals, a.disease_prevention AS prevention LIMIT {DEFAULT_LIMIT}",
            {},
        )
    wf = _tiered_where("d", exact, ("a",))
    return (
        f"""MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice)
        {wf}LIMIT $limit
        RETURN d.disease_name AS disease, a.nutrition_do_eat AS should_eat,
               a.nutrition_not_eat AS should_avoid,
               a.nutrition_recommend_meal AS recommended_meals,
               a.disease_prevention AS prevention""",
        {"name": entity, "limit": DEFAULT_LIMIT},
    )


def _tmpl_prevention(entity: str | None, _extra: str | None, exact: bool = False):
    if not entity:
        return (
            f"MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice) RETURN d.disease_name AS disease, a.disease_prevention AS prevention LIMIT {DEFAULT_LIMIT}",
            {},
        )
    wf = _tiered_where("d", exact, ("a",))
    return (
        f"""MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice)
        {wf}LIMIT $limit
        RETURN d.disease_name AS disease, a.disease_prevention AS prevention""",
        {"name": entity, "limit": DEFAULT_LIMIT},
    )


def _tmpl_department(entity: str | None, _extra: str | None, exact: bool = False):
    if not entity:
        return (
            f"MATCH (d:Disease)-[:HAS_TREATMENT]->(t:Treatment) RETURN d.disease_name AS disease, t.cure_department AS department LIMIT {DEFAULT_LIMIT}",
            {},
        )
    wf = _tiered_where("d", exact, ("t",))
    return (
        f"""MATCH (d:Disease)-[:HAS_TREATMENT]->(t:Treatment)
        {wf}LIMIT $limit
        RETURN d.disease_name AS disease, t.cure_department AS department""",
        {"name": entity, "limit": DEFAULT_LIMIT},
    )


def _tmpl_profile(entity: str | None, _extra: str | None, exact: bool = False):
    if not entity:
        return (
            f"MATCH (d:Disease) RETURN d.disease_name AS disease, d.disease_description AS description LIMIT {DEFAULT_LIMIT}",
            {},
        )
    wf = _tiered_where("d", exact)
    return (
        f"""MATCH (d:Disease)
        {wf}LIMIT $limit
        OPTIONAL MATCH (d)-[:HAS_SYMPTOM]->(s:Symptom)
        OPTIONAL MATCH (d)-[:HAS_TREATMENT]->(t:Treatment)
        OPTIONAL MATCH (d)-[:IS_PRESCRIBED]->(m:Medicine)
        OPTIONAL MATCH (d)-[:HAS_ADVICE]->(a:Advice)
        RETURN d.disease_name AS disease, d.disease_description AS description,
               d.disease_category AS category, d.disease_cause AS cause,
               s.disease_symptom AS symptoms, s.check_method AS check_method,
               s.people_easy_get AS risk_group, t.cure_method AS treatment_method,
               t.cure_department AS department, t.cure_probability AS cure_rate,
               m.drug_recommend AS recommended_drugs, m.drug_common AS common_drugs,
               a.nutrition_do_eat AS should_eat, a.nutrition_not_eat AS should_avoid,
               a.nutrition_recommend_meal AS recommended_meals, a.disease_prevention AS prevention""",
        {"name": entity, "limit": DEFAULT_LIMIT},
    )


def _tmpl_cause(entity: str | None, _extra: str | None, exact: bool = False):
    if not entity:
        return (
            f"MATCH (d:Disease) WHERE d.disease_cause IS NOT NULL RETURN d.disease_name AS disease, d.disease_cause AS cause LIMIT {DEFAULT_LIMIT}",
            {},
        )
    wf = _tiered_where("d", exact)
    return (
        f"""MATCH (d:Disease)
        {wf}LIMIT $limit
        RETURN d.disease_name AS disease, d.disease_cause AS cause""",
        {"name": entity, "limit": DEFAULT_LIMIT},
    )


def _tmpl_check_method(entity: str | None, _extra: str | None, exact: bool = False):
    if not entity:
        return (
            f"MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom) WHERE s.check_method IS NOT NULL RETURN d.disease_name AS disease, s.check_method AS check_method LIMIT {DEFAULT_LIMIT}",
            {},
        )
    wf = _tiered_where("d", exact, ("s",))
    return (
        f"""MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom)
        {wf}LIMIT $limit
        RETURN d.disease_name AS disease, s.check_method AS check_method""",
        {"name": entity, "limit": DEFAULT_LIMIT},
    )


def _tmpl_susceptible_population(entity: str | None, _extra: str | None, exact: bool = False):
    if not entity:
        return (
            f"MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom) WHERE s.people_easy_get IS NOT NULL RETURN d.disease_name AS disease, s.people_easy_get AS risk_group LIMIT {DEFAULT_LIMIT}",
            {},
        )
    wf = _tiered_where("d", exact, ("s",))
    return (
        f"""MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom)
        {wf}LIMIT $limit
        RETURN d.disease_name AS disease, s.people_easy_get AS risk_group""",
        {"name": entity, "limit": DEFAULT_LIMIT},
    )


def _tmpl_linked_diseases(entity: str | None, _extra: str | None, exact: bool = False):
    if not entity:
        return (
            f"MATCH (d1:Disease)-[:IS_LINKED_WITH]-(d2:Disease) RETURN d1.disease_name AS disease, d2.disease_name AS linked_disease LIMIT {LINKED_LIMIT}",
            {},
        )
    wf = _tiered_where("d1", exact, ("d2",))
    return (
        f"""MATCH (d1:Disease)-[:IS_LINKED_WITH]-(d2:Disease)
        {wf}LIMIT $limit
        RETURN d1.disease_name AS disease, d2.disease_name AS linked_disease,
               d2.disease_category AS linked_category""",
        {"name": entity, "limit": LINKED_LIMIT},
    )


def _reverse_template(
    *,
    entity: str | None,
    match: str,
    null_filter: str,
    relevance_field: str,
    returns: str,
):
    if not entity:
        return (
            f"{match} WHERE {null_filter} RETURN {returns} LIMIT {REVERSE_QUERY_LIMIT}",
            {},
        )
    relevance = _token_relevance(relevance_field)
    return (
        f"""{match}
        WHERE toLower({relevance_field}) CONTAINS toLower($keyword)
        WITH d, {relevance_field.split('.')[0]},
             {relevance} AS relevance
        ORDER BY relevance, d.disease_name
        LIMIT $limit
        RETURN {returns}""",
        {"keyword": entity, "limit": REVERSE_QUERY_LIMIT},
    )


def _tmpl_find_by_symptom(entity: str | None, _extra: str | None, _exact: bool = False):
    return _reverse_template(
        entity=entity,
        match="MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom)",
        null_filter="s.disease_symptom IS NOT NULL",
        relevance_field="s.disease_symptom",
        returns="d.disease_name AS disease, s.disease_symptom AS symptoms, s.check_method AS check_method",
    )


def _tmpl_find_by_medicine(entity: str | None, _extra: str | None, _exact: bool = False):
    if not entity:
        return (
            f"MATCH (d:Disease)-[:IS_PRESCRIBED]->(m:Medicine) RETURN d.disease_name AS disease, m.drug_common AS matched_common LIMIT {REVERSE_QUERY_LIMIT}",
            {},
        )
    return (
        """MATCH (d:Disease)-[:IS_PRESCRIBED]->(m:Medicine)
        WHERE toLower(m.drug_common) CONTAINS toLower($keyword)
           OR toLower(m.drug_recommend) CONTAINS toLower($keyword)
        WITH d, m,
             CASE
               WHEN toLower(m.drug_common) STARTS WITH toLower($keyword)
                 OR toLower(m.drug_recommend) STARTS WITH toLower($keyword) THEN 0
               ELSE 1
             END AS relevance
        ORDER BY relevance, d.disease_name
        LIMIT $limit
        RETURN d.disease_name AS disease, m.drug_common AS matched_common,
               m.drug_recommend AS matched_recommend""",
        {"keyword": entity, "limit": REVERSE_QUERY_LIMIT},
    )


def _tmpl_find_by_nutrition_avoid(entity: str | None, extra: str | None, exact: bool = False):
    return _reverse_template(
        entity=entity,
        match="MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice)",
        null_filter="a.nutrition_not_eat IS NOT NULL",
        relevance_field="a.nutrition_not_eat",
        returns="d.disease_name AS disease, a.nutrition_not_eat AS matched_advice",
    )


def _tmpl_find_by_nutrition_eat(entity: str | None, _extra: str | None, _exact: bool = False):
    if not entity:
        return (
            f"MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice) WHERE a.nutrition_do_eat IS NOT NULL RETURN d.disease_name AS disease, a.nutrition_do_eat AS matched_do_eat LIMIT {REVERSE_QUERY_LIMIT}",
            {},
        )
    return (
        """MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice)
        WHERE toLower(a.nutrition_do_eat) CONTAINS toLower($keyword)
           OR toLower(a.nutrition_recommend_meal) CONTAINS toLower($keyword)
        WITH d, a
        LIMIT $limit
        RETURN d.disease_name AS disease, a.nutrition_do_eat AS matched_do_eat,
               a.nutrition_recommend_meal AS matched_recommend""",
        {"keyword": entity, "limit": REVERSE_QUERY_LIMIT},
    )


def _tmpl_find_by_prevention(entity: str | None, extra: str | None, exact: bool = False):
    return _reverse_template(
        entity=entity,
        match="MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice)",
        null_filter="a.disease_prevention IS NOT NULL",
        relevance_field="a.disease_prevention",
        returns="d.disease_name AS disease, a.disease_prevention AS matched_prevention",
    )


def _tmpl_find_by_check_method(entity: str | None, extra: str | None, exact: bool = False):
    return _reverse_template(
        entity=entity,
        match="MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom)",
        null_filter="s.check_method IS NOT NULL",
        relevance_field="s.check_method",
        returns="d.disease_name AS disease, s.check_method AS matched_check_method",
    )


def _tmpl_chain_linked_avoid(entity: str | None, _extra: str | None, _exact: bool = False):
    if not entity:
        return None, None
    return (
        """MATCH (d1:Disease)-[:IS_LINKED_WITH]-(d2:Disease)
        WHERE toLower(d1.disease_name) CONTAINS toLower($keyword)
           OR toLower(d2.disease_name) CONTAINS toLower($keyword)
        WITH CASE WHEN toLower(d1.disease_name) CONTAINS toLower($keyword) THEN d2 ELSE d1 END AS target
        MATCH (target)-[:HAS_ADVICE]->(a:Advice)
        WHERE a.nutrition_not_eat IS NOT NULL AND a.nutrition_not_eat <> ''
        RETURN target.disease_name AS linked_disease, a.nutrition_not_eat AS should_avoid
        LIMIT $limit""",
        {"keyword": entity, "limit": REVERSE_QUERY_LIMIT},
    )


def _tmpl_chain_linked_eat(entity: str | None, _extra: str | None, _exact: bool = False):
    if not entity:
        return None, None
    return (
        """MATCH (d1:Disease)-[:IS_LINKED_WITH]-(d2:Disease)
        WHERE toLower(d1.disease_name) CONTAINS toLower($keyword)
           OR toLower(d2.disease_name) CONTAINS toLower($keyword)
        WITH CASE WHEN toLower(d1.disease_name) CONTAINS toLower($keyword) THEN d2 ELSE d1 END AS target
        MATCH (target)-[:HAS_ADVICE]->(a:Advice)
        WHERE a.nutrition_do_eat IS NOT NULL AND a.nutrition_do_eat <> ''
        RETURN target.disease_name AS linked_disease, a.nutrition_do_eat AS should_eat
        LIMIT $limit""",
        {"keyword": entity, "limit": REVERSE_QUERY_LIMIT},
    )


_BUILDERS: dict[str, CypherTemplate] = {
    "symptoms": _tmpl_symptoms,
    "medicine": _tmpl_medicine,
    "treatment": _tmpl_treatment,
    "advice": _tmpl_advice,
    "prevention": _tmpl_prevention,
    "department": _tmpl_department,
    "profile": _tmpl_profile,
    "cause": _tmpl_cause,
    "check_method": _tmpl_check_method,
    "susceptible_population": _tmpl_susceptible_population,
    "linked_diseases": _tmpl_linked_diseases,
    "find_by_symptom": _tmpl_find_by_symptom,
    "find_by_medicine": _tmpl_find_by_medicine,
    "find_by_nutrition_avoid": _tmpl_find_by_nutrition_avoid,
    "find_by_nutrition_eat": _tmpl_find_by_nutrition_eat,
    "find_by_prevention": _tmpl_find_by_prevention,
    "find_by_check_method": _tmpl_find_by_check_method,
    "chain_linked_avoid": _tmpl_chain_linked_avoid,
    "chain_linked_eat": _tmpl_chain_linked_eat,
}
