"""Tests for backend/app/routers/query.py — POST /api/v1/query endpoint."""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import app

# Patch target: where run_pipeline is LOOKED UP (in the router module),
# not where it's DEFINED (in pipeline module).
_PATCH_TARGET = "app.routers.query.run_pipeline"


@pytest.fixture
def client():
    """Create a test client."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


class TestQueryEndpoint:
    """Tests for POST /api/v1/query."""

    def test_valid_query_returns_200(self, client):
        """Valid question should return 200 with success status."""
        mock_result = {
            "status": "success",
            "response_type": "text",
            "answer": "Test answer",
            "data": None,
            "metadata": {"query_mode": "hybrid", "execution_time_ms": 100, "source_count": 1, "engine": "lightrag"},
        }
        with patch(_PATCH_TARGET, new_callable=AsyncMock, return_value=mock_result):
            response = client.post("/api/v1/query", json={"question": "Bệnh tiểu đường là gì?"})
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["response_type"] == "text"

    def test_empty_question_returns_422(self, client):
        """Empty question should return 422 (Pydantic min_length=1 validation)."""
        response = client.post("/api/v1/query", json={"question": ""})
        assert response.status_code == 422

    def test_missing_question_returns_422(self, client):
        """Missing question field should return 422 validation error."""
        response = client.post("/api/v1/query", json={})
        assert response.status_code == 422



    def test_model_unavailable_returns_503(self, client):
        """MODEL_UNAVAILABLE error should return 503."""
        mock_result = {
            "status": "error",
            "response_type": "text",
            "answer": "Dịch vụ AI tạm thời không khả dụng.",
            "data": None,
            "metadata": {"error_code": "MODEL_UNAVAILABLE", "error_detail": "LLM down", "execution_time_ms": 0, "engine": "lightrag"},
        }
        with patch(_PATCH_TARGET, new_callable=AsyncMock, return_value=mock_result):
            response = client.post("/api/v1/query", json={"question": "test"})
            assert response.status_code == 503

    def test_database_error_returns_500(self, client):
        """DATABASE_ERROR should return 500."""
        mock_result = {
            "status": "error",
            "response_type": "text",
            "answer": "Hệ thống đang gặp sự cố.",
            "data": None,
            "metadata": {"error_code": "DATABASE_ERROR", "error_detail": "Connection refused", "execution_time_ms": 0, "engine": "lightrag"},
        }
        with patch(_PATCH_TARGET, new_callable=AsyncMock, return_value=mock_result):
            response = client.post("/api/v1/query", json={"question": "test"})
            assert response.status_code == 500

    def test_query_with_mode_override(self, client):
        """Query with mode should pass mode to pipeline."""
        mock_result = {
            "status": "success",
            "response_type": "text",
            "answer": "Test",
            "data": None,
            "metadata": {"query_mode": "hybrid", "execution_time_ms": 100, "source_count": 1, "engine": "lightrag"},
        }
        with patch(_PATCH_TARGET, new_callable=AsyncMock, return_value=mock_result) as mock_pipeline:
            response = client.post("/api/v1/query", json={"question": "test", "mode": "hybrid"})
            assert response.status_code == 200
            mock_pipeline.assert_called_once()

    def test_response_contains_required_fields(self, client):
        """Response should contain all required fields."""
        mock_result = {
            "status": "success",
            "response_type": "table",
            "answer": "Test answer",
            "data": [{"item": "test"}],
            "metadata": {"query_mode": "cypher:symptoms", "execution_time_ms": 50, "source_count": 1, "engine": "cypher_direct"},
        }
        with patch(_PATCH_TARGET, new_callable=AsyncMock, return_value=mock_result):
            response = client.post("/api/v1/query", json={"question": "Triệu chứng bệnh tiểu đường?"})
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert "response_type" in data
            assert "answer" in data
            assert "data" in data
            assert "metadata" in data

    def test_timeout_returns_504(self, client):
        """TIMEOUT error should return 504."""
        mock_result = {
            "status": "error",
            "response_type": "text",
            "answer": "Xử lý mất quá lâu.",
            "data": None,
            "metadata": {"error_code": "TIMEOUT", "error_detail": "Pipeline timeout", "execution_time_ms": 60000, "engine": "lightrag"},
        }
        with patch(_PATCH_TARGET, new_callable=AsyncMock, return_value=mock_result):
            response = client.post("/api/v1/query", json={"question": "test"})
            assert response.status_code == 504
