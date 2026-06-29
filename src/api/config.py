"""Unified project configuration for the new src/ layout.

This module is the single source of truth for all environment variables.
It supersedes ai_engine/config.py (legacy modules remain for reference only).

Usage:
    from api.config import settings
    neo4j_uri = settings.neo4j_uri
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from dataclasses import dataclass, field

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# ── Load .env files ─────────────────────────────────────────────────────
# Priority, lowest → highest:
#   1. root .env      (shared local defaults)
#   2. backend/.env   (backend-specific overrides)
#
# Later files override earlier files.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILES = [
    _PROJECT_ROOT / ".env",
    _PROJECT_ROOT / "backend" / ".env",
    _PROJECT_ROOT / "backend" / "src" / ".env",
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
        "No .env file found in root or backend/ — using environment variables / defaults"
    )


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
        default_factory=lambda: os.getenv("EMBEDDING_MODEL", "bge-m3")
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
    check_infra_on_startup: bool = field(
        default_factory=lambda: os.getenv("CHECK_INFRA_ON_STARTUP", "false").lower() == "true"
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
