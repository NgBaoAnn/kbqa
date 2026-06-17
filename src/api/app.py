"""FastAPI Application Factory — AegisHealth KBQA.

Usage (uvicorn entry point)::

    uvicorn api.app:app --reload --app-dir src

Or with the legacy entry point (backend/app/main.py) still working, import
the new app explicitly::

    uvicorn api.app:app --reload --app-dir src --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.config import settings
from api.middleware.cors import add_cors_middleware
from api.middleware.rate_limit import RateLimitMiddleware

logger = logging.getLogger(__name__)


# ── Lifespan ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup / shutdown lifecycle manager."""
    logger.info("🚀 AegisHealth KBQA Backend starting…")
    logger.info("   Rate limit: %d req/min on /api/v1/query", settings.rate_limit_per_minute)

    # Build DI container (wires all adapters and use cases)
    from api.dependencies import AppContainer
    container = await AppContainer.create(settings)
    app.state.container = container

    logger.info("🟢 Backend ready.")
    yield

    # Graceful shutdown
    logger.info("🔴 Shutting down…")
    await container.close()
    logger.info("👋 Goodbye.")


# ── App factory ────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="AegisHealth KBQA API",
        description=(
            "Hệ thống Hỏi đáp Y tế (Medical QA) sử dụng LightRAG + Neo4j Knowledge Graph. "
            "Hỗ trợ truy vấn bằng tiếng Việt và tiếng Anh."
        ),
        version=settings.pipeline_version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── Middleware ─────────────────────────────────────────────────────────
    add_cors_middleware(app, origins=settings.api_cors_origins)
    app.add_middleware(
        RateLimitMiddleware,
        limit=settings.rate_limit_per_minute,
        window_seconds=60.0,
        paths=["/api/v1/query", "/api/v1/conversations"],
    )

    # ── Routers ────────────────────────────────────────────────────────────
    from api.routers import (
        admin_router,
        conversations_router,
        feedback_router,
        health_router,
        knowledge_router,
        me_router,
        query_router,
        schema_router,
    )

    app.include_router(health_router)
    app.include_router(me_router)
    app.include_router(conversations_router)
    app.include_router(feedback_router)
    app.include_router(knowledge_router)
    app.include_router(admin_router)
    app.include_router(query_router)
    app.include_router(schema_router)

    # ── Root ───────────────────────────────────────────────────────────────
    @app.get("/", tags=["root"])
    async def root():
        return {
            "name": "AegisHealth KBQA API",
            "version": settings.pipeline_version,
            "engine": "LightRAG + Neo4j",
            "docs": "/docs",
        }

    return app


# ── Module-level app instance (for uvicorn) ────────────────────────────────
app = create_app()
