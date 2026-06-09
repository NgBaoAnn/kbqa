"""Text-to-Cypher Service — LLM fallback khi không có template phù hợp."""

import logging
import os

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME", "qwen2.5:7b")
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT_SECONDS", "60"))

client = AsyncOpenAI(
    base_url=LLM_BASE_URL,
    api_key="ollama",
    timeout=LLM_TIMEOUT,
)

# ── Schema & few-shot examples ─────────────────────────────────────────────

SCHEMA_PROMPT = """
You are a Cypher expert. Convert the user's natural language question into a Cypher query for a Neo4j database.
The database uses the VietMedKG schema:

# Nodes and Properties:
- (d:Disease)
  - disease_name: String (e.g., "Bệnh tiểu đường", "Viêm phổi")
  - disease_description: String
  - disease_category: String
  - disease_cause: String
- (s:Symptom)
  - disease_symptom: String  [all symptoms stored as one blob string per disease]
  - check_method: String
  - people_easy_get: String
- (t:Treatment)
  - cure_method: String
  - cure_department: String
  - cure_probability: String
- (m:Medicine)
  - drug_recommend: String
  - drug_common: String
  - drug_detail: String
- (a:Advice)
  - nutrition_do_eat: String
  - nutrition_not_eat: String
  - nutrition_recommend_meal: String
  - disease_prevention: String

# Relationships:
- (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom)
- (d:Disease)-[:HAS_TREATMENT]->(t:Treatment)
- (d:Disease)-[:IS_PRESCRIBED]->(m:Medicine)
- (d:Disease)-[:HAS_ADVICE]->(a:Advice)
- (d:Disease)-[:IS_LINKED_WITH]->(d2:Disease)

# EXAMPLES:
Question: "triệu chứng của viêm phổi"
Cypher: MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom) WHERE toLower(d.disease_name) CONTAINS toLower('viêm phổi') RETURN d.disease_name AS disease, s.disease_symptom AS symptoms LIMIT 5

Question: "thuốc chữa viêm niệu đạo"
Cypher: MATCH (d:Disease)-[:IS_PRESCRIBED]->(m:Medicine) WHERE toLower(d.disease_name) CONTAINS toLower('viêm niệu đạo') RETURN d.disease_name AS disease, m.drug_common AS common_drugs, m.drug_recommend AS recommended_drugs LIMIT 5

Question: "cách điều trị viêm phổi"
Cypher: MATCH (d:Disease)-[:HAS_TREATMENT]->(t:Treatment) WHERE toLower(d.disease_name) CONTAINS toLower('viêm phổi') RETURN d.disease_name AS disease, t.cure_method AS treatment_method, t.cure_department AS department LIMIT 5

Question: "bệnh đi kèm với viêm phổi"
Cypher: MATCH (d:Disease)-[:IS_LINKED_WITH]->(d2:Disease) WHERE toLower(d.disease_name) CONTAINS toLower('viêm phổi') RETURN d.disease_name AS disease, d2.disease_name AS linked_disease LIMIT 5

Question: "bao nhiêu bệnh trong cơ sở dữ liệu"
Cypher: MATCH (d:Disease) WITH count(d) AS disease_count MATCH (s:Symptom) WITH disease_count, count(s) AS symptom_count MATCH (m:Medicine) WITH disease_count, symptom_count, count(m) AS medicine_count RETURN disease_count, symptom_count, medicine_count

Question: "tiểu đường nên ăn gì"
Cypher: MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice) WHERE toLower(d.disease_name) CONTAINS toLower('tiểu đường') RETURN d.disease_name AS disease, a.nutrition_do_eat AS should_eat, a.nutrition_not_eat AS should_avoid, a.nutrition_recommend_meal AS recommended_meals LIMIT 5

Question: "phòng tránh viêm phổi như thế nào"
Cypher: MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice) WHERE toLower(d.disease_name) CONTAINS toLower('viêm phổi') RETURN d.disease_name AS disease, a.disease_prevention AS prevention LIMIT 5

Question: "khoa điều trị viêm khớp"
Cypher: MATCH (d:Disease)-[:HAS_TREATMENT]->(t:Treatment) WHERE toLower(d.disease_name) CONTAINS toLower('viêm khớp') RETURN d.disease_name AS disease, t.cure_department AS department LIMIT 5

Question: "bệnh nào có triệu chứng sốt cao"
Cypher: MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom) WHERE toLower(s.disease_symptom) CONTAINS toLower('sốt cao') RETURN d.disease_name AS disease, s.disease_symptom AS symptoms LIMIT 10

Question: "thông tin tổng hợp về bệnh tiểu đường"
Cypher: MATCH (d:Disease) WHERE toLower(d.disease_name) CONTAINS toLower('tiểu đường') OPTIONAL MATCH (d)-[:HAS_SYMPTOM]->(s:Symptom) OPTIONAL MATCH (d)-[:HAS_TREATMENT]->(t:Treatment) OPTIONAL MATCH (d)-[:IS_PRESCRIBED]->(m:Medicine) OPTIONAL MATCH (d)-[:HAS_ADVICE]->(a:Advice) RETURN d.disease_name AS disease, d.disease_description AS description, s.disease_symptom AS symptoms, t.cure_method AS treatment, m.drug_common AS drugs, a.nutrition_do_eat AS should_eat, a.disease_prevention AS prevention LIMIT 5

Question: "symptoms of diabetes"
Cypher: MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom) WHERE toLower(d.disease_name) CONTAINS toLower('tiểu đường') RETURN d.disease_name AS disease, s.disease_symptom AS symptoms LIMIT 5

# IMPORTANT RULES:
1. ALWAYS use WHERE toLower(d.disease_name) CONTAINS toLower(...) for disease name matching.
2. ALWAYS add LIMIT 5 at the end (except count queries).
3. ALWAYS use meaningful AS aliases: disease, symptoms, treatment_method, common_drugs, etc.
4. NEVER return raw Cypher in markdown blocks. Output the query string only.
5. Use OPTIONAL MATCH for profile/summary queries so missing nodes return NULL instead of empty.
6. To search by symptom keyword: WHERE toLower(s.disease_symptom) CONTAINS toLower(...)
"""

# ── Public API ─────────────────────────────────────────────────────────────

async def generate_cypher(question: str) -> str:
    """Generate a Cypher query from a natural language question using LLM."""
    logger.info("Generating Cypher via LLM for: %s", question[:80])

    try:
        response = await client.chat.completions.create(
            model=LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": SCHEMA_PROMPT},
                {"role": "user", "content": f"Write a Cypher query for: {question}"},
            ],
            temperature=0.0,
            max_tokens=300,
        )

        raw = response.choices[0].message.content.strip()

        # Strip markdown fences if LLM ignores instructions
        if raw.startswith("```"):
            lines = raw.split("\n")
            if len(lines) >= 3:
                raw = "\n".join(lines[1:-1])

        logger.info("LLM Cypher: %s", raw.replace("\n", " ")[:120])
        return raw.strip()

    except Exception as e:
        logger.error("Failed to generate Cypher: %s", e)
        raise ValueError(f"LLM generation failed: {e}") from e

