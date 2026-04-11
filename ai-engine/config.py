"""AI Engine configuration — LightRAG, LLM, Embedding, and Neo4j settings."""

import os
from dotenv import load_dotenv

load_dotenv()

# ── LLM Server (Ollama/vLLM — OpenAI-compatible API) ──────────────────────
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "qwen2.5:14b")
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))

# ── Embedding Model ───────────────────────────────────────────────────────
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "http://localhost:11434/v1")

# ── Reranker (optional, recommended for mix mode) ─────────────────────────
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
RERANKER_ENABLED = os.getenv("RERANKER_ENABLED", "false").lower() == "true"

# ── LightRAG Framework ───────────────────────────────────────────────────
LIGHTRAG_WORKING_DIR = os.getenv("LIGHTRAG_WORKING_DIR", "./lightrag_data")
LIGHTRAG_KG_STORAGE = os.getenv("LIGHTRAG_KG_STORAGE", "Neo4JStorage")
LIGHTRAG_VECTOR_STORAGE = os.getenv("LIGHTRAG_VECTOR_STORAGE", "NanoVectorDBStorage")
LIGHTRAG_DOC_STORAGE = os.getenv("LIGHTRAG_DOC_STORAGE", "JsonKVStorage")

# Query mode options: naive | local | global | hybrid | mix
DEFAULT_QUERY_MODE = os.getenv("DEFAULT_QUERY_MODE", "hybrid")

# ── Neo4j AuraDB ──────────────────────────────────────────────────────────
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j+s://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

# ── Benchmark models (for evaluation) ────────────────────────────────────
BENCHMARK_MODELS = [
    "qwen2.5:14b",
    "qwen2.5:7b",
    # "llama3:8b-instruct-q4_0",  # uncomment if GPU allows
]
