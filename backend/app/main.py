"""FastAPI entry point — AegisHealth KBQA Backend.

Powered by LightRAG for graph-enhanced medical QA.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import API_CORS_ORIGINS, API_VERSION, LOG_LEVEL

# ── Logging setup ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan (startup/shutdown) ───────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — handles startup and shutdown tasks."""
    # Startup
    logger.info("🚀 AegisHealth KBQA Backend starting (v%s)...", API_VERSION)
    logger.info("   Engine: Hybrid (LightRAG + Cypher)")

    # Validate config
    from ai_engine.config import validate_config

    config_warnings = validate_config()
    for w in config_warnings:
        logger.warning("   ⚠️  Config: %s", w)

    # Pre-initialize LightRAG (optional — lazy init also works)
    try:
        from ai_engine.services.lightrag_service import get_lightrag_instance

        await get_lightrag_instance()
        logger.info("   ✅ LightRAG initialized")
    except Exception as e:
        logger.warning("   ⚠️ LightRAG init deferred: %s", e)

    logger.info("🟢 Backend ready.")

    yield

    # Shutdown
    logger.info("🔴 Shutting down...")
    try:
        from app.services.graph_service import close_driver
        await close_driver()
    except Exception:
        pass
    logger.info("👋 Goodbye.")


# ── FastAPI App ───────────────────────────────────────────────────────────
app = FastAPI(
    title="AegisHealth KBQA API",
    description=(
        "Hệ thống Hỏi đáp Y tế (Medical QA) sử dụng LightRAG + Neo4j Knowledge Graph. "
        "Hỗ trợ truy vấn bằng tiếng Việt và tiếng Anh."
    ),
    version=API_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS Middleware ───────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=API_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Include Routers ───────────────────────────────────────────────────────
from app.routers import health, query, schema  # noqa: E402

app.include_router(query.router)
app.include_router(health.router)
app.include_router(schema.router)


# ── Root endpoint ─────────────────────────────────────────────────────────
@app.get("/", tags=["root"])
async def root():
    """Root endpoint — API info."""
    return {
        "name": "AegisHealth KBQA API",
        "version": API_VERSION,
        "engine": "LightRAG",
        "docs": "/docs",
    }
