"""Rate-limiting middleware — in-memory sliding window per IP.

Limitations:
    - State is lost on process restart.
    - Does NOT scale across multiple Uvicorn workers / replicas.
    - Suitable for single-instance or development deployments.

For production at scale, replace this with a Redis-backed solution
(e.g., fastapi-limiter or slowapi + redis).

Usage::

    from api.middleware.rate_limit import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware, limit=20, window_seconds=60)
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP sliding-window rate limiter.

    Args:
        app:            ASGI application.
        limit:          Maximum number of requests per window.
        window_seconds: Window size in seconds (default: 60).
        paths:          Only apply the limit to these URL paths.
                        Pass ``None`` to apply globally.
    """

    def __init__(
        self,
        app,
        *,
        limit: int = 20,
        window_seconds: float = 60.0,
        paths: list[str] | None = None,
    ) -> None:
        super().__init__(app)
        self._limit = limit
        self._window = window_seconds
        self._paths = set(paths) if paths else None
        self._store: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        # Only apply to configured paths (or all paths if None)
        if self._paths is not None and request.url.path not in self._paths:
            return await call_next(request)

        client_ip = (request.client.host if request.client else "unknown")
        now = time.monotonic()

        # Evict expired timestamps
        self._store[client_ip] = [
            ts for ts in self._store[client_ip] if now - ts < self._window
        ]

        if len(self._store[client_ip]) >= self._limit:
            logger.warning(
                "Rate limit exceeded for IP %s (path=%s limit=%d/%ds)",
                client_ip,
                request.url.path,
                self._limit,
                int(self._window),
            )
            return JSONResponse(
                status_code=429,
                content={
                    "status": "error",
                    "response_type": "text",
                    "answer": (
                        "Bạn đã gửi quá nhiều yêu cầu. "
                        "Vui lòng đợi một phút rồi thử lại."
                    ),
                    "data": None,
                    "metadata": {
                        "error_code": "RATE_LIMITED",
                        "error_detail": (
                            f"Rate limit: {self._limit} requests/"
                            f"{int(self._window)}s exceeded."
                        ),
                    },
                },
            )

        self._store[client_ip].append(now)
        return await call_next(request)
