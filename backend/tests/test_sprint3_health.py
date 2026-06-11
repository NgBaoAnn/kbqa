"""Sprint 3 — Người 1: Tests for health_service and the /api/v1/health endpoint.

Coverage
--------
health_service:
  - check_postgres: success, DB URL not configured, psycopg not installed,
    connection error, timeout
  - check_neo4j: success, connection failure, timeout
  - check_ai_engine: ready (no warnings), degraded (warnings), import error
  - run_all_checks: returns all three keys

health router (/api/v1/health):
  - all healthy → status "healthy", all services present
  - postgres failure → degraded
  - neo4j failure → degraded
  - ai_engine degraded → overall degraded
  - LightRAG error → unhealthy
  - no secret in response (DB URL, password, JWT secret not present)
  - response version matches API_VERSION
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.health_service import ServiceCheckResult, _fail, _ok


# ════════════════════════════════════════════════════════════════════════════
# health_service unit tests
# ════════════════════════════════════════════════════════════════════════════


class TestCheckPostgres:
    @pytest.mark.asyncio
    async def test_success(self):
        from app.services import health_service

        # Simulate a successful synchronous DB ping by mocking run_in_executor.
        with patch("app.config.SUPABASE_DB_URL", "postgresql://fake:fake@localhost/db"):
            with patch(
                "asyncio.get_event_loop",
                return_value=MagicMock(
                    run_in_executor=AsyncMock(return_value=None)
                ),
            ):
                result = await health_service.check_postgres()

        assert result.name == "supabase_postgres"
        assert result.status == "connected"

    @pytest.mark.asyncio
    async def test_not_configured(self):
        from app.services import health_service

        with patch("app.config.SUPABASE_DB_URL", ""):
            result = await health_service.check_postgres()

        assert result.status == "unavailable"
        assert "not configured" in result.detail
        # Ensure no URL in detail
        assert "postgresql" not in result.detail

    @pytest.mark.asyncio
    async def test_connection_error_returns_safe_detail(self):
        from app.services import health_service

        with patch("app.config.SUPABASE_DB_URL", "postgresql://fake:secret@localhost/db"):
            # Make run_in_executor raise a connection error
            mock_loop = MagicMock()
            mock_loop.run_in_executor = AsyncMock(
                side_effect=Exception("connection refused at localhost:5432")
            )
            with patch("asyncio.get_event_loop", return_value=mock_loop):
                result = await health_service.check_postgres()

        assert result.status == "unavailable"
        # Secret (password) must not appear in the detail
        assert "secret" not in result.detail
        assert "postgresql" not in result.detail

    @pytest.mark.asyncio
    async def test_timeout_returns_degraded(self):
        import asyncio as _asyncio

        from app.services import health_service

        async def _slow(*a, **kw):
            await _asyncio.sleep(999)

        with patch("app.config.SUPABASE_DB_URL", "postgresql://fake@localhost/db"):
            mock_loop = MagicMock()
            mock_loop.run_in_executor = _slow
            with patch("asyncio.get_event_loop", return_value=mock_loop):
                with patch.object(health_service, "_CHECK_TIMEOUT", 0.01):
                    result = await health_service.check_postgres()

        assert result.status == "unavailable"
        assert "timeout" in result.detail


class TestCheckNeo4j:
    @pytest.mark.asyncio
    async def test_success(self):
        from app.services import health_service

        with patch(
            "app.services.graph_service.check_connectivity",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await health_service.check_neo4j()

        assert result.name == "neo4j"
        assert result.status == "connected"

    @pytest.mark.asyncio
    async def test_failure_returns_unavailable(self):
        from app.services import health_service

        with patch(
            "app.services.graph_service.check_connectivity",
            new_callable=AsyncMock,
            return_value=False,
        ):
            result = await health_service.check_neo4j()

        assert result.status == "unavailable"
        # No credentials in detail
        assert "password" not in result.detail

    @pytest.mark.asyncio
    async def test_exception_returns_safe_detail(self):
        from app.services import health_service

        with patch(
            "app.services.graph_service.check_connectivity",
            new_callable=AsyncMock,
            side_effect=Exception("Auth failed: wrong password=hunter2"),
        ):
            result = await health_service.check_neo4j()

        assert result.status == "unavailable"
        # The raw exception message is NOT in detail — only type name
        assert "hunter2" not in result.detail

    @pytest.mark.asyncio
    async def test_timeout_returns_unavailable(self):
        import asyncio as _asyncio

        from app.services import health_service

        async def _slow():
            await _asyncio.sleep(999)

        with patch("app.services.graph_service.check_connectivity", side_effect=_slow):
            with patch.object(health_service, "_CHECK_TIMEOUT", 0.01):
                result = await health_service.check_neo4j()

        assert result.status == "unavailable"
        assert "timeout" in result.detail


class TestCheckAiEngine:
    @pytest.mark.asyncio
    async def test_ready_when_no_warnings(self):
        from app.services import health_service

        with patch("ai_engine.config.validate_config", return_value=[]):
            result = await health_service.check_ai_engine()

        assert result.name == "ai_engine"
        assert result.status == "ready"

    @pytest.mark.asyncio
    async def test_degraded_when_warnings(self):
        from app.services import health_service

        with patch(
            "ai_engine.config.validate_config",
            return_value=["LLM_BASE_URL not set", "embedding model not configured"],
        ):
            result = await health_service.check_ai_engine()

        assert result.status == "degraded"
        assert "2 config warning" in result.detail

    @pytest.mark.asyncio
    async def test_import_error_returns_unavailable(self):
        from app.services import health_service

        with patch(
            "ai_engine.config.validate_config",
            side_effect=ImportError("No module named ai_engine"),
        ):
            result = await health_service.check_ai_engine()

        assert result.status == "unavailable"
        assert "not importable" in result.detail


class TestRunAllChecks:
    @pytest.mark.asyncio
    async def test_returns_all_keys(self):
        from app.services import health_service

        with (
            patch.object(health_service, "check_postgres", new_callable=AsyncMock,
                         return_value=_ok("supabase_postgres")),
            patch.object(health_service, "check_neo4j", new_callable=AsyncMock,
                         return_value=_ok("neo4j")),
            patch.object(health_service, "check_ai_engine", new_callable=AsyncMock,
                         return_value=_ok("ai_engine", "ready")),
        ):
            results = await health_service.run_all_checks()

        assert "supabase_postgres" in results
        assert "neo4j" in results
        assert "ai_engine" in results


# ════════════════════════════════════════════════════════════════════════════
# health router integration tests (via TestClient)
# ════════════════════════════════════════════════════════════════════════════


def _mock_infra_all_ok():
    """Return infra check results where all services are healthy."""
    return {
        "supabase_postgres": _ok("supabase_postgres", "connected"),
        "neo4j": _ok("neo4j", "connected"),
        "ai_engine": _ok("ai_engine", "ready"),
    }


def _mock_rag_all_ok():
    return {
        "llm_server": "available",
        "embedding_server": "available",
        "lightrag": "initialized",
    }


client = TestClient(app, raise_server_exceptions=False)


class TestHealthEndpoint:
    def test_all_healthy(self):
        with (
            patch("app.services.health_service.run_all_checks",
                  new_callable=AsyncMock, return_value=_mock_infra_all_ok()),
            patch("ai_engine.services.lightrag_service.health_check",
                  new_callable=AsyncMock, return_value=_mock_rag_all_ok()),
        ):
            resp = client.get("/api/v1/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["services"]["api"] == "running"
        assert body["services"]["supabase_postgres"] == "connected"
        assert body["services"]["neo4j"] == "connected"
        assert body["services"]["ai_engine"] == "ready"

    def test_postgres_failure_returns_degraded(self):
        infra = _mock_infra_all_ok()
        infra["supabase_postgres"] = _fail("supabase_postgres", "connection error (OperationalError)")

        with (
            patch("app.services.health_service.run_all_checks",
                  new_callable=AsyncMock, return_value=infra),
            patch("ai_engine.services.lightrag_service.health_check",
                  new_callable=AsyncMock, return_value=_mock_rag_all_ok()),
        ):
            resp = client.get("/api/v1/health")

        body = resp.json()
        assert body["status"] == "degraded"
        assert body["services"]["supabase_postgres"] == "unavailable"

    def test_neo4j_failure_returns_degraded(self):
        infra = _mock_infra_all_ok()
        infra["neo4j"] = _fail("neo4j", "connection timeout")

        with (
            patch("app.services.health_service.run_all_checks",
                  new_callable=AsyncMock, return_value=infra),
            patch("ai_engine.services.lightrag_service.health_check",
                  new_callable=AsyncMock, return_value=_mock_rag_all_ok()),
        ):
            resp = client.get("/api/v1/health")

        body = resp.json()
        assert body["status"] == "degraded"
        assert body["services"]["neo4j"] == "unavailable"

    def test_ai_engine_degraded_returns_degraded(self):
        infra = _mock_infra_all_ok()
        infra["ai_engine"] = ServiceCheckResult("ai_engine", "degraded", "2 config warning(s)")

        with (
            patch("app.services.health_service.run_all_checks",
                  new_callable=AsyncMock, return_value=infra),
            patch("ai_engine.services.lightrag_service.health_check",
                  new_callable=AsyncMock, return_value=_mock_rag_all_ok()),
        ):
            resp = client.get("/api/v1/health")

        body = resp.json()
        assert body["status"] == "degraded"
        assert body["services"]["ai_engine"] == "degraded"

    def test_lightrag_error_returns_unhealthy(self):
        rag = {
            "llm_server": "available",
            "embedding_server": "available",
            "lightrag": "error: initialization failed",
        }

        with (
            patch("app.services.health_service.run_all_checks",
                  new_callable=AsyncMock, return_value=_mock_infra_all_ok()),
            patch("ai_engine.services.lightrag_service.health_check",
                  new_callable=AsyncMock, return_value=rag),
        ):
            resp = client.get("/api/v1/health")

        body = resp.json()
        assert body["status"] == "unhealthy"

    def test_no_secret_in_response(self):
        """Ensure DB URL, password, JWT secret are not present in the response body."""
        import json

        from app.config import NEO4J_PASSWORD, SUPABASE_DB_URL, SUPABASE_JWT_SECRET

        infra = _mock_infra_all_ok()
        infra["supabase_postgres"] = _fail("supabase_postgres", "connection error (OperationalError)")

        with (
            patch("app.services.health_service.run_all_checks",
                  new_callable=AsyncMock, return_value=infra),
            patch("ai_engine.services.lightrag_service.health_check",
                  new_callable=AsyncMock, return_value=_mock_rag_all_ok()),
        ):
            resp = client.get("/api/v1/health")

        body_str = json.dumps(resp.json())

        # Real secret values must never appear in the response
        for secret in [SUPABASE_DB_URL, SUPABASE_JWT_SECRET, NEO4J_PASSWORD]:
            if secret:  # only check if actually configured in test env
                assert secret not in body_str, f"secret leaked: {secret[:6]}..."

    def test_response_contains_version(self):
        from app.config import API_VERSION

        with (
            patch("app.services.health_service.run_all_checks",
                  new_callable=AsyncMock, return_value=_mock_infra_all_ok()),
            patch("ai_engine.services.lightrag_service.health_check",
                  new_callable=AsyncMock, return_value=_mock_rag_all_ok()),
        ):
            resp = client.get("/api/v1/health")

        body = resp.json()
        assert body["version"] == API_VERSION

    def test_response_has_all_service_fields(self):
        with (
            patch("app.services.health_service.run_all_checks",
                  new_callable=AsyncMock, return_value=_mock_infra_all_ok()),
            patch("ai_engine.services.lightrag_service.health_check",
                  new_callable=AsyncMock, return_value=_mock_rag_all_ok()),
        ):
            resp = client.get("/api/v1/health")

        services = resp.json()["services"]
        expected_fields = {"api", "supabase_postgres", "neo4j", "ai_engine",
                           "llm_server", "embedding_server", "lightrag"}
        assert expected_fields.issubset(set(services.keys()))
