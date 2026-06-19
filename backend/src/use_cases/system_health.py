"""SystemHealthUseCase — operational dependency health checks."""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SystemHealthResult:
    status: str
    services: dict[str, str]
    version: str


class SystemHealthUseCase:
    """Check runtime dependency health through injected ports."""

    def __init__(
        self,
        *,
        graph,
        vector,
        db,
        pipeline_version: str,
    ) -> None:
        self._graph = graph
        self._vector = vector
        self._db = db
        self._pipeline_version = pipeline_version

    async def execute(self) -> SystemHealthResult:
        services = {
            "api": "running",
            "ai_engine": "ready",
            "supabase_postgres": "unknown",
            "neo4j": "unknown",
            "llm_server": "unknown",
            "embedding_server": "unknown",
            "lightrag": "unknown",
        }
        overall = "healthy"

        try:
            ok = await self._graph.check_connectivity()
            services["neo4j"] = "connected" if ok else "unavailable"
            if not ok:
                overall = "degraded"
        except Exception as exc:
            logger.warning("Neo4j health check failed: %s", exc)
            services["neo4j"] = "unavailable"
            overall = "degraded"

        try:
            self._db.fetch_one("select 1 as ok")
            services["supabase_postgres"] = "connected"
        except Exception as exc:
            logger.warning("Postgres health check failed: %s", exc)
            services["supabase_postgres"] = "unavailable"
            overall = "degraded"

        try:
            vector_health = await self._vector.health_check()
            services["lightrag"] = vector_health.get("lightrag", "unknown")
            services["llm_server"] = vector_health.get("llm_server", "unknown")
            services["embedding_server"] = vector_health.get("embedding_server", "unknown")
            if services["lightrag"] in {"error", "unavailable"}:
                overall = "degraded"
        except Exception as exc:
            logger.warning("LightRAG health check failed: %s", exc)
            services["lightrag"] = "unavailable"
            overall = "degraded"

        return SystemHealthResult(
            status=overall,
            services=services,
            version=self._pipeline_version,
        )
