"""Text-to-Cypher Service — Generate Cypher queries and synthesize answers using LLM."""

import os
import logging
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Initialize OpenAI Client (OpenAI-compatible for Ollama)
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME", "qwen2.5:3b")
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT_SECONDS", "60"))

client = AsyncOpenAI(
    base_url=LLM_BASE_URL,
    api_key="ollama",  # Not required for local Ollama, but needed by the client
    timeout=LLM_TIMEOUT,
)

# VietMedKG Schema Definition
SCHEMA_PROMPT = """
You are a Cypher expert. Convert the user's natural language question into a Cypher query for a Neo4j database.
The database uses the VietMedKG schema:

# Nodes and Properties:
- (d:Disease)
  - disease_name: String (e.g., "Viêm phổi")
  - disease_description: String
  - disease_category: String
  - disease_cause: String
- (s:Symptom)
  - disease_symptom: String
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

# EXAMPLES (Learn from these):
Question: "triệu chứng của viêm phổi"
Cypher: MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom) WHERE toLower(d.disease_name) CONTAINS toLower('viêm phổi') RETURN s.disease_symptom

Question: "thuốc chữa viêm niệu đạo"
Cypher: MATCH (d:Disease)-[:IS_PRESCRIBED]->(m:Medicine) WHERE toLower(d.disease_name) CONTAINS toLower('viêm niệu đạo') RETURN m.drug_common, m.drug_recommend

Question: "cách điều trị viêm phổi"
Cypher: MATCH (d:Disease)-[:HAS_TREATMENT]->(t:Treatment) WHERE toLower(d.disease_name) CONTAINS toLower('viêm phổi') RETURN t.cure_method

Question: "bệnh đi kèm với viêm phổi"
Cypher: MATCH (d:Disease)-[:IS_LINKED_WITH]->(d2:Disease) WHERE toLower(d.disease_name) CONTAINS toLower('viêm phổi') RETURN d2.disease_name

# IMPORTANT RULES:
1. ALWAYS use `WHERE toLower(d.disease_name) CONTAINS toLower(...)` for disease names.
2. NEVER return anything other than the raw Cypher query string. Do NOT wrap it in ```cypher ... ``` markdown blocks.
3. MATCH EXACTLY the patterns in the EXAMPLES above.
"""

async def generate_cypher(question: str) -> str:
    """Generate a Cypher query from a natural language question using LLM."""
    logger.info("Generating Cypher via LLM for: %s", question)
    
    try:
        response = await client.chat.completions.create(
            model=LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": SCHEMA_PROMPT},
                {"role": "user", "content": f"Write a Cypher query for: {question}"}
            ],
            temperature=0.0,
            max_tokens=200,
        )
        
        raw_output = response.choices[0].message.content.strip()
        
        # Clean up markdown blocks if the LLM ignores instructions
        if raw_output.startswith("```"):
            lines = raw_output.split("\n")
            if len(lines) >= 3:
                raw_output = "\n".join(lines[1:-1])
        
        logger.info("LLM generated Cypher: %s", raw_output.replace("\n", " "))
        return raw_output.strip()
        
    except Exception as e:
        logger.error("Failed to generate Cypher: %s", e)
        raise ValueError(f"LLM generation failed: {e}")


async def synthesize_answer(question: str, records: list[dict], language: str = "vi") -> str:
    """Synthesize a natural language answer from Cypher result records."""
    logger.info("Synthesizing answer via LLM (records=%d)", len(records))
    
    if not records:
        if language == "en":
            return "No information found in the structured database."
        return "Không tìm thấy thông tin trong cơ sở dữ liệu cấu trúc."
        
    system_prompt = (
        "You are a helpful medical assistant. "
        "Use the provided JSON data to answer the user's question accurately. "
        "Do not invent information that is not present in the JSON. "
        f"Please write the response in {'English' if language == 'en' else 'Vietnamese'}."
    )
    
    user_prompt = f"Question: {question}\n\nData from Database:\n{records}"
    
    try:
        response = await client.chat.completions.create(
            model=LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=500,
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        logger.error("Failed to synthesize answer: %s", e)
        # Fallback to stringifying the records
        return str(records)
