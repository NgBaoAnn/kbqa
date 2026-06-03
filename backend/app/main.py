"""FastAPI entry point — AegisHealth KBQA Backend.

Powered by LightRAG for graph-enhanced medical QA.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import API_CORS_ORIGINS, API_VERSION, LOG_LEVEL, RATE_LIMIT_PER_MINUTE

# ── Logging setup ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ── Rate Limiting (in-memory, per-IP) ─────────────────────────────────────
# Simple in-memory rate limiter — no external dependency needed.
import time
from collections import defaultdict

_rate_limit_store: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(client_ip: str) -> bool:
    """Check if the client has exceeded the rate limit.

    Returns True if the request is allowed, False if rate-limited.
    """
    now = time.time()
    window = 60.0  # 1-minute sliding window

    # Clean expired entries
    _rate_limit_store[client_ip] = [
        ts for ts in _rate_limit_store[client_ip] if now - ts < window
    ]

    if len(_rate_limit_store[client_ip]) >= RATE_LIMIT_PER_MINUTE:
        return False

    _rate_limit_store[client_ip].append(now)
    return True


# ── Lifespan (startup/shutdown) ───────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — handles startup and shutdown tasks."""
    # Startup
    logger.info("🚀 AegisHealth KBQA Backend starting (v%s)...", API_VERSION)
    logger.info("   Engine: Hybrid (LightRAG + Cypher)")
    logger.info("   Rate Limit: %d req/min/IP", RATE_LIMIT_PER_MINUTE)

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


# ── Rate Limiting Middleware ──────────────────────────────────────────────
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply per-IP rate limiting to POST /api/v1/query endpoint."""
    # Only rate-limit the query endpoint (most resource-intensive)
    if request.url.path == "/api/v1/query" and request.method == "POST":
        client_ip = request.client.host if request.client else "unknown"
        if not _check_rate_limit(client_ip):
            logger.warning("Rate limit exceeded for IP: %s", client_ip)
            return JSONResponse(
                status_code=429,
                content={
                    "status": "error",
                    "response_type": "text",
                    "answer": "Bạn đã gửi quá nhiều yêu cầu. Vui lòng đợi một phút rồi thử lại.",
                    "data": None,
                    "metadata": {
                        "error_code": "RATE_LIMITED",
                        "error_detail": f"Rate limit: {RATE_LIMIT_PER_MINUTE} requests/minute exceeded.",
                    },
                },
            )

    response = await call_next(request)
    return response


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
