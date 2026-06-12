"""Backend configuration — load environment variables.

Reuses Neo4j credentials from ai_engine.config to ensure single source of truth.
"""

import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

# ── API Configuration ─────────────────────────────────────────────────────
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
API_CORS_ORIGINS = os.getenv(
    "API_CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
).split(",")

# ── Logging ───────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ── Neo4j AuraDB ──────────────────────────────────────────────────────────
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j+s://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

# ── Supabase ──────────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL", "")

# ── Rate Limiting ─────────────────────────────────────────────────────────
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))

# ── Testing / Debug ───────────────────────────────────────────────────────
# Khi true, MỌI câu hỏi bỏ qua Cypher path, đi thẳng LightRAG.
# Dùng để cô lập và đánh giá chất lượng retrieval của LightRAG.
DISABLE_CYPHER_PATH = os.getenv("DISABLE_CYPHER_PATH", "false").lower() == "true"

# ── API Version ───────────────────────────────────────────────────────────
API_VERSION = "1.0.0"

# ── Pipeline / Model Version Tracking (Sprint 1) ─────────────────────────
# These values are persisted into assistant message metadata and query_logs
# so every response can be traced to the exact prompt/model/KG/pipeline used.
PROMPT_VERSION = os.getenv("PROMPT_VERSION", "v1.0.0")
MODEL_NAME = os.getenv("MODEL_NAME", os.getenv("LLM_MODEL_NAME", "unknown"))
KG_VERSION = os.getenv("KG_VERSION", "v1.0.0")
PIPELINE_VERSION = os.getenv("PIPELINE_VERSION", "v1.0.0")
