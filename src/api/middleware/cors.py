"""CORS Middleware configuration for the new src/ API layer.

Usage::

    from api.middleware.cors import add_cors_middleware
    add_cors_middleware(app, origins=settings.api_cors_origins)
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def add_cors_middleware(app: FastAPI, origins: list[str]) -> None:
    """Add CORSMiddleware with the given allowed origins to a FastAPI app."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
