"""Tests for backend/app/services/pipeline.py — Hybrid Pipeline Orchestrator."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestPipelineOrchestrator:
    """Tests for the hybrid pipeline (Phương án C)."""

    @pytest.mark.asyncio
    async def test_empty_question_returns_invalid(self):
        """Empty question should return INVALID_QUESTION error."""
        from app.services.pipeline import run_pipeline
        result = await run_pipeline(question="")
        assert result["status"] == "error"
        assert result["metadata"]["error_code"] == "INVALID_QUESTION"

    @pytest.mark.asyncio
    async def test_whitespace_question_returns_invalid(self):
        """Whitespace-only question should return INVALID_QUESTION."""
        from app.services.pipeline import run_pipeline
        result = await run_pipeline(question="   ")
        assert result["status"] == "error"
        assert result["metadata"]["error_code"] == "INVALID_QUESTION"

    @pytest.mark.asyncio
    async def test_mode_override_forces_lightrag(self):
        """Setting mode should force LightRAG path."""
        mock_result = {"success": True, "answer": "Test answer", "mode": "hybrid"}
        with patch("ai_engine.services.lightrag_service.query", new_callable=AsyncMock, return_value=mock_result):
            from app.services.pipeline import run_pipeline
            result = await run_pipeline(question="test question", mode="hybrid")
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_response_has_required_fields(self):
        """Pipeline response should have all required fields."""
        mock_result = {"success": True, "answer": "Test answer", "mode": "hybrid"}
        with patch("ai_engine.services.lightrag_service.query", new_callable=AsyncMock, return_value=mock_result):
            from app.services.pipeline import run_pipeline
            result = await run_pipeline(question="test question", mode="hybrid")
            assert "status" in result
            assert "response_type" in result
            assert "answer" in result
            assert "metadata" in result

    @pytest.mark.asyncio
    async def test_unexpected_error_returns_database_error(self):
        """Unexpected exceptions should return DATABASE_ERROR."""
        with patch("ai_engine.services.query_router.extract_intent_with_llm", side_effect=Exception("Unexpected")):
            from app.services.pipeline import run_pipeline
            result = await run_pipeline(question="test question")
            assert result["status"] == "error"
            assert result["metadata"]["error_code"] == "DATABASE_ERROR"
