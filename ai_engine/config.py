"""AI Engine configuration — LightRAG, LLM, Embedding, and Neo4j settings.

Uses find_dotenv() to locate .env regardless of working directory.
Validates required variables at import time (fail-fast).
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# ── Load .env files ──────────────────────────────────────────────────────
# Keep legacy ai_engine imports aligned with the refactored src config.
# Priority, lowest → highest: root .env, backend/.env, src/.env.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_ENV_FILES = [
    _PROJECT_ROOT / ".env",
    _PROJECT_ROOT / "backend" / ".env",
    _PROJECT_ROOT / "src" / ".env",
]

_loaded_env_files: list[str] = []
for _env_file in _ENV_FILES:
    if _env_file.exists():
        load_dotenv(_env_file, override=True)
        _loaded_env_files.append(str(_env_file))

if _loaded_env_files:
    logger.info("Loaded env files: %s", ", ".join(_loaded_env_files))
else:
    logger.warning(
        "No .env file found in root, backend/, or src/ — using environment variables / defaults"
    )

# ── LLM Server (Ollama/vLLM — OpenAI-compatible API) ──────────────────────
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "qwen2.5:14b")
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))

# ── Embedding Model ───────────────────────────────────────────────────────
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", LLM_BASE_URL)

# ── Reranker (optional, recommended for mix mode) ─────────────────────────
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
RERANKER_ENABLED = os.getenv("RERANKER_ENABLED", "false").lower() == "true"

# ── LightRAG Framework ───────────────────────────────────────────────────
LIGHTRAG_WORKING_DIR = os.getenv("LIGHTRAG_WORKING_DIR", "./lightrag_data")
LIGHTRAG_KG_STORAGE = os.getenv("LIGHTRAG_KG_STORAGE", "Neo4JStorage")
LIGHTRAG_VECTOR_STORAGE = os.getenv("LIGHTRAG_VECTOR_STORAGE", "NanoVectorDBStorage")
LIGHTRAG_DOC_STORAGE = os.getenv("LIGHTRAG_DOC_STORAGE", "JsonKVStorage")

# Query mode for the LightRAG semantic path.
# «naive» = pure Qdrant vector search only (no LightRAG-internal graph).
# The VietMedKG graph is served exclusively via the Cypher path.
DEFAULT_QUERY_MODE = os.getenv("DEFAULT_QUERY_MODE", "naive")

# Enforce naive mode regardless of caller override.
# Change to False only if LightRAG's own internal graph is populated.
FORCE_LIGHTRAG_NAIVE_MODE = os.getenv("FORCE_LIGHTRAG_NAIVE_MODE", "true").lower() == "true"

# ── Neo4j AuraDB ──────────────────────────────────────────────────────────
NEO4J_URI = os.getenv("NEO4J_URI", "")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

# ── Benchmark models (for evaluation) ────────────────────────────────────
BENCHMARK_MODELS = [
    "qwen2.5:14b",
    "qwen2.5:7b",
]


# ── Validation ────────────────────────────────────────────────────────────
def validate_config() -> list[str]:
    """Validate critical config values. Returns list of warnings (empty = OK)."""
    warnings = []

    if not NEO4J_URI:
        warnings.append("NEO4J_URI is empty — Cypher path and LightRAG KG storage will fail")
    if not NEO4J_PASSWORD:
        warnings.append("NEO4J_PASSWORD is empty — Neo4j connection will fail")
    if DEFAULT_QUERY_MODE not in {"naive", "local", "global", "hybrid", "mix"}:
        warnings.append(f"DEFAULT_QUERY_MODE '{DEFAULT_QUERY_MODE}' is invalid")

    # Ensure LightRAG working dir exists
    wd = Path(LIGHTRAG_WORKING_DIR)
    if not wd.exists():
        wd.mkdir(parents=True, exist_ok=True)
        logger.info("Created LightRAG working dir: %s", wd.resolve())

    return warnings
