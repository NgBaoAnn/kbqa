"""GET /api/v1/health — Health check endpoint.

Delegates all service checks to ``app.services.health_service``.
The router is intentionally thin — it assembles the final response shape
and determines the overall status from individual check results.

Overall status logic
--------------------
- ``healthy``  — all checks passed.
- ``degraded`` — at least one non-critical check failed (Postgres, Neo4j,
  AI engine config). The API is still running.
- ``unhealthy`` — a critical error that prevents normal operation.
"""

import logging

from fastapi import APIRouter

from app.config import API_VERSION
from app.models.response import HealthResponse, ServiceStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["health"])

# Services that, when unavailable, degrade the overall status to "degraded".
_DEGRADED_SERVICES = {"supabase_postgres", "neo4j", "ai_engine"}


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description=(
        "Kiểm tra trạng thái các dịch vụ: Supabase Postgres, Neo4j, AI engine, "
        "LLM server, embedding server, LightRAG. "
        "Response không chứa credentials hoặc thông tin nhạy cảm."
    ),
)
async def health_check() -> dict:
    """Check the health of all backend services.

    Returns a HealthResponse with individual service statuses and an
    overall status of ``healthy``, ``degraded``, or ``unhealthy``.
    """
    from app.services.health_service import run_all_checks  # local import — respects boundary

    # ── Run infrastructure checks (Postgres, Neo4j, AI engine) ────────────
    infra_checks = await run_all_checks()

    # ── Run LightRAG checks (LLM server, embedding, LightRAG instance) ────
    rag_health: dict = {}
    try:
        from ai_engine.services.lightrag_service import health_check as rag_health_check  # noqa: PLC0415

        rag_health = await rag_health_check()
    except Exception as exc:
        logger.warning("health: LightRAG health check error: %s", type(exc).__name__)
        rag_health = {
            "llm_server": "unavailable",
            "embedding_server": "unavailable",
            "lightrag": f"unavailable ({type(exc).__name__})",
        }

    # ── Determine overall status ──────────────────────────────────────────
    overall = "healthy"

    for name, result in infra_checks.items():
        if name in _DEGRADED_SERVICES and result.status not in ("connected", "ready", "running"):
            overall = "degraded"
            logger.info("health: %s is %s — %s", name, result.status, result.detail)

    if rag_health.get("llm_server") not in ("available", "running"):
        overall = "degraded"

    # A LightRAG error string starting with "unavailable" or "error" indicates
    # the instance itself is broken; keep as degraded (not unhealthy) because
    # Cypher path can still serve queries.
    lightrag_status = rag_health.get("lightrag", "unknown")
    if isinstance(lightrag_status, str) and lightrag_status.startswith("error"):
        overall = "unhealthy"

    # ── Build response — no secrets in any field ──────────────────────────
    services = ServiceStatus(
        api="running",
        supabase_postgres=infra_checks.get("supabase_postgres", _unknown()).status,
        neo4j=infra_checks.get("neo4j", _unknown()).status,
        ai_engine=infra_checks.get("ai_engine", _unknown()).status,
        llm_server=rag_health.get("llm_server", "unknown"),
        embedding_server=rag_health.get("embedding_server", "unknown"),
        lightrag=lightrag_status,
    )

    return {
        "status": overall,
        "services": services,
        "version": API_VERSION,
    }


def _unknown():
    """Fallback ServiceCheckResult when a check is missing from results."""
    from app.services.health_service import ServiceCheckResult  # noqa: PLC0415

    return ServiceCheckResult(name="unknown", status="unknown", detail="check not run")
