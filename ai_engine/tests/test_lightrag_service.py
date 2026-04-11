"""Unit tests for LightRAG Service."""

import pytest


class TestLightRAGServiceConfig:
    """Test LightRAG service configuration."""

    def test_config_imports(self):
        """Config module should import without errors."""
        from ai_engine.config import (
            DEFAULT_QUERY_MODE,
            EMBEDDING_DIM,
            EMBEDDING_MODEL,
            LIGHTRAG_KG_STORAGE,
            LIGHTRAG_VECTOR_STORAGE,
            LIGHTRAG_WORKING_DIR,
            LLM_BASE_URL,
            LLM_MODEL_NAME,
            NEO4J_URI,
        )

        assert LLM_BASE_URL is not None
        assert LLM_MODEL_NAME is not None
        assert EMBEDDING_MODEL is not None
        assert EMBEDDING_DIM > 0
        assert DEFAULT_QUERY_MODE in {"naive", "local", "global", "hybrid", "mix"}
        assert LIGHTRAG_KG_STORAGE is not None
        assert LIGHTRAG_WORKING_DIR is not None

    def test_valid_query_modes(self):
        """All expected query modes should be recognized."""
        valid_modes = {"naive", "local", "global", "hybrid", "mix"}
        from ai_engine.config import DEFAULT_QUERY_MODE

        assert DEFAULT_QUERY_MODE in valid_modes


class TestQueryValidation:
    """Test query input validation."""

    @pytest.mark.asyncio
    async def test_empty_question_returns_error(self):
        """Empty question should return error response."""
        from backend.app.services.pipeline import run_pipeline

        result = await run_pipeline(question="", language="vi")
        assert result["status"] == "error"
        assert result["metadata"]["error_code"] == "INVALID_QUESTION"

    @pytest.mark.asyncio
    async def test_whitespace_question_returns_error(self):
        """Whitespace-only question should return error response."""
        from backend.app.services.pipeline import run_pipeline

        result = await run_pipeline(question="   ", language="vi")
        assert result["status"] == "error"
