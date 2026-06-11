"""Health service — S3-ARCH-03.

Lightweight, dependency-free health checks for each infrastructure component.

Design rules
------------
- Each check returns a ``ServiceCheckResult`` — never raises.
- Checks are intentionally fast: no LLM calls, no heavy queries.
- No credential values (DB URL, password, tokens) appear in ``detail`` strings.
- The AI engine check only validates that the module is importable and config
  is present; it does NOT call the LLM or embedding server.
- Individual checks have a per-check timeout of 5 seconds.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Per-check timeout (seconds) — lightweight ops should complete well under this.
_CHECK_TIMEOUT = 5.0


@dataclass
class ServiceCheckResult:
    """Result of a single service health check."""

    name: str
    status: str   # "connected" | "ready" | "running" | "degraded" | "unavailable" | "unknown"
    detail: str   # Human-readable detail — MUST NOT contain secrets


def _ok(name: str, status: str = "connected", detail: str = "") -> ServiceCheckResult:
    return ServiceCheckResult(name=name, status=status, detail=detail)


def _fail(name: str, detail: str) -> ServiceCheckResult:
    """Return a degraded result with a safe, secret-free detail string."""
    return ServiceCheckResult(name=name, status="unavailable", detail=detail)


# ── Individual checks ─────────────────────────────────────────────────────────


async def check_postgres() -> ServiceCheckResult:
    """Check Supabase Postgres connectivity with a lightweight SELECT 1.

    Uses the SupabaseDatabase helper from app.database; does NOT use the
    service-role key (only the SUPABASE_DB_URL connection string).
    The DB URL is never included in the returned detail string.
    """
    from app.config import SUPABASE_DB_URL

    if not SUPABASE_DB_URL:
        return _fail("supabase_postgres", "SUPABASE_DB_URL not configured")

    try:
        # Run the blocking psycopg call in a thread to avoid blocking event loop.
        def _ping() -> None:
            import psycopg  # noqa: PLC0415

            with psycopg.connect(SUPABASE_DB_URL, connect_timeout=4) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")

        await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, _ping),
            timeout=_CHECK_TIMEOUT,
        )
        return _ok("supabase_postgres", "connected")

    except asyncio.TimeoutError:
        logger.warning("health_service: postgres check timed out")
        return _fail("supabase_postgres", "connection timeout")
    except ImportError:
        return _fail("supabase_postgres", "psycopg not installed (pip install psycopg[binary])")
    except Exception as exc:
        # Log the real error internally but expose only a safe summary.
        logger.warning("health_service: postgres check failed: %s", type(exc).__name__)
        return _fail("supabase_postgres", f"connection error ({type(exc).__name__})")


async def check_neo4j() -> ServiceCheckResult:
    """Check Neo4j connectivity using the existing graph_service driver.

    Calls ``driver.verify_connectivity()`` — no Cypher query is run.
    """
    try:
        from app.services.graph_service import check_connectivity  # noqa: PLC0415

        connected = await asyncio.wait_for(check_connectivity(), timeout=_CHECK_TIMEOUT)
        if connected:
            return _ok("neo4j", "connected")
        return _fail("neo4j", "verify_connectivity returned false")

    except asyncio.TimeoutError:
        logger.warning("health_service: neo4j check timed out")
        return _fail("neo4j", "connection timeout")
    except Exception as exc:
        logger.warning("health_service: neo4j check failed: %s", type(exc).__name__)
        return _fail("neo4j", f"connection error ({type(exc).__name__})")


async def check_ai_engine() -> ServiceCheckResult:
    """Check whether the AI engine module is importable and config is present.

    Intentionally does NOT call the LLM or embedding server — that check is
    already provided by the LightRAG health_check() function used separately.

    Returns "ready" if the module is importable and at least one LLM config
    value is set, "degraded" otherwise.
    """
    try:
        from ai_engine.config import validate_config  # noqa: PLC0415

        warnings = validate_config()
        if warnings:
            detail = f"{len(warnings)} config warning(s)"
            logger.info("health_service: ai_engine config warnings: %s", warnings)
            return ServiceCheckResult(name="ai_engine", status="degraded", detail=detail)
        return _ok("ai_engine", "ready")

    except ImportError as exc:
        logger.warning("health_service: ai_engine not importable: %s", exc)
        return _fail("ai_engine", "ai_engine module not importable")
    except Exception as exc:
        logger.warning("health_service: ai_engine check failed: %s", type(exc).__name__)
        return _fail("ai_engine", f"config check error ({type(exc).__name__})")


async def run_all_checks() -> dict[str, ServiceCheckResult]:
    """Run all health checks concurrently and return a name → result mapping."""
    results = await asyncio.gather(
        check_postgres(),
        check_neo4j(),
        check_ai_engine(),
        return_exceptions=False,
    )
    return {r.name: r for r in results}
