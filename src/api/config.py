"""Unified project configuration for the new src/ layout.

This module is the single source of truth for all environment variables.
It supersedes ai_engine/config.py and backend/app/config.py.
Both legacy modules remain unchanged during Phase 3 to preserve backwards compatibility.

Usage:
    from api.config import settings
    neo4j_uri = settings.neo4j_uri
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from dataclasses import dataclass, field

from dotenv import find_dotenv, load_dotenv

logger = logging.getLogger(__name__)

# ── Load .env (project root takes priority over cwd) ────────────────────
_dotenv_path = find_dotenv(usecwd=True)
if _dotenv_path:
    load_dotenv(_dotenv_path)
    logger.debug("Loaded .env from: %s", _dotenv_path)
else:
    logger.warning("No .env file found — using environment variables / defaults")

# Also load from backend/.env if present (legacy location)
_backend_env = Path(__file__).resolve().parents[2] / "backend" / ".env"
if _backend_env.exists():
    load_dotenv(_backend_env, override=True)
    logger.debug("Loaded backend/.env from: %s", _backend_env)


@dataclass(frozen=True)
class Settings:
    """Immutable settings object loaded from environment variables."""

    # ── API ──────────────────────────────────────────────────────────────
    api_host: str = field(default_factory=lambda: os.getenv("API_HOST", "0.0.0.0"))
    api_port: int = field(default_factory=lambda: int(os.getenv("API_PORT", "8000")))
    api_cors_origins: list[str] = field(
        default_factory=lambda: os.getenv(
            "API_CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
        ).split(",")
    )
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    # ── Neo4j ────────────────────────────────────────────────────────────
    neo4j_uri: str = field(default_factory=lambda: os.getenv("NEO4J_URI", ""))
    neo4j_username: str = field(default_factory=lambda: os.getenv("NEO4J_USERNAME", "neo4j"))
    neo4j_password: str = field(default_factory=lambda: os.getenv("NEO4J_PASSWORD", ""))

    # ── Supabase ─────────────────────────────────────────────────────────
    supabase_url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", "").rstrip("/"))
    supabase_anon_key: str = field(default_factory=lambda: os.getenv("SUPABASE_ANON_KEY", ""))
    supabase_jwt_secret: str = field(default_factory=lambda: os.getenv("SUPABASE_JWT_SECRET", ""))
    supabase_service_role_key: str = field(
        default_factory=lambda: os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    )
    supabase_db_url: str = field(default_factory=lambda: os.getenv("SUPABASE_DB_URL", ""))

    # ── LLM / Ollama ─────────────────────────────────────────────────────
    llm_base_url: str = field(
        default_factory=lambda: os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
    )
    llm_model_name: str = field(
        default_factory=lambda: os.getenv("LLM_MODEL_NAME", "qwen2.5:14b")
    )
    llm_timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
    )

    # ── Embedding ────────────────────────────────────────────────────────
    embedding_model: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    )
    embedding_dim: int = field(
        default_factory=lambda: int(os.getenv("EMBEDDING_DIM", "1024"))
    )
    embedding_base_url: str = field(
        default_factory=lambda: os.getenv(
            "EMBEDDING_BASE_URL", os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
        )
    )

    # ── LightRAG ─────────────────────────────────────────────────────────
    lightrag_working_dir: str = field(
        default_factory=lambda: os.getenv("LIGHTRAG_WORKING_DIR", "./lightrag_data")
    )
    lightrag_kg_storage: str = field(
        default_factory=lambda: os.getenv("LIGHTRAG_KG_STORAGE", "Neo4JStorage")
    )
    lightrag_vector_storage: str = field(
        default_factory=lambda: os.getenv("LIGHTRAG_VECTOR_STORAGE", "NanoVectorDBStorage")
    )
    lightrag_doc_storage: str = field(
        default_factory=lambda: os.getenv("LIGHTRAG_DOC_STORAGE", "JsonKVStorage")
    )
    default_query_mode: str = field(
        default_factory=lambda: os.getenv("DEFAULT_QUERY_MODE", "naive")
    )
    force_lightrag_naive_mode: bool = field(
        default_factory=lambda: os.getenv("FORCE_LIGHTRAG_NAIVE_MODE", "true").lower() == "true"
    )

    # ── Pipeline feature flags ────────────────────────────────────────────
    disable_cypher_path: bool = field(
        default_factory=lambda: os.getenv("DISABLE_CYPHER_PATH", "false").lower() == "true"
    )
    rate_limit_per_minute: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
    )

    # ── Version metadata ─────────────────────────────────────────────────
    prompt_version: str = field(default_factory=lambda: os.getenv("PROMPT_VERSION", "v1.0.0"))
    model_name: str = field(
        default_factory=lambda: os.getenv(
            "MODEL_NAME", os.getenv("LLM_MODEL_NAME", "unknown")
        )
    )
    kg_version: str = field(default_factory=lambda: os.getenv("KG_VERSION", "v1.0.0"))
    pipeline_version: str = field(default_factory=lambda: os.getenv("PIPELINE_VERSION", "v1.0.0"))

    def validate(self) -> list[str]:
        """Validate critical config values. Returns list of warnings (empty = OK)."""
        warnings: list[str] = []
        if not self.neo4j_uri:
            warnings.append("NEO4J_URI is empty — Cypher path and Neo4j storage will fail")
        if not self.neo4j_password:
            warnings.append("NEO4J_PASSWORD is empty — Neo4j connection will fail")
        if not self.supabase_db_url:
            warnings.append("SUPABASE_DB_URL is empty — database operations will fail")
        if self.default_query_mode not in {"naive", "local", "global", "hybrid", "mix"}:
            warnings.append(f"DEFAULT_QUERY_MODE '{self.default_query_mode}' is invalid")
        return warnings


# Module-level singleton — import this directly in adapters.
settings = Settings()
