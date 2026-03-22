"""
AegisHealth KBQA — FastAPI Entry Point

Tham chiếu:
  - docs/02_SYSTEM_ARCHITECTURE.md (Section 3.2 — Backend Middleware)
  - docs/05_API_SYSTEM_DESIGN.md   (Section 1 — Nguyên tắc thiết kế)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

# ---------------------------------------------------------------------------
# FastAPI Application Instance
# ---------------------------------------------------------------------------
app = FastAPI(
    title="AegisHealth KBQA API",
    description=(
        "Knowledge Base Question Answering cho Y tế — Hybrid GraphRAG. "
        "Generate → Retrieve → Synthesize pipeline."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# CORS Middleware
# ---------------------------------------------------------------------------
origins = [origin.strip() for origin in settings.API_CORS_ORIGINS.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Root Endpoint
# ---------------------------------------------------------------------------
@app.get("/", tags=["Root"])
async def root():
    """Root endpoint — thông tin cơ bản của API."""
    return {
        "service": "AegisHealth KBQA API",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


# ---------------------------------------------------------------------------
# Health Check (placeholder — sẽ hoàn thiện ở task M4-BE-06)
# ---------------------------------------------------------------------------
@app.get("/api/v1/health", tags=["Health"])
async def health_check():
    """Health check endpoint — kiểm tra trạng thái các service."""
    return {
        "status": "healthy",
        "services": {
            "api": "running",
            "database": "not_configured",
            "llm_server": "not_configured",
        },
        "version": "0.1.0",
    }
