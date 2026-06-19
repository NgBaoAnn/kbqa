"""Shared API error-code mapping for REST and SSE responses."""

from __future__ import annotations

DEFAULT_ERROR_STATUS = 500

ERROR_HTTP_STATUS: dict[str, int] = {
    "INVALID_QUESTION": 400,
    "CYPHER_GENERATION_FAILED": 422,
    "LIGHTRAG_QUERY_FAILED": 500,
    "NO_DATA_FOUND": 404,
    "DATABASE_ERROR": 500,
    "MODEL_UNAVAILABLE": 503,
    "TIMEOUT": 504,
    "ADAPTER_ERROR": 500,
    "STREAM_ERROR": 500,
    "PERSISTENCE_FAILED": 500,
}


def http_status_for_error(error_code: str | None) -> int:
    """Return the HTTP/SSE status code associated with an application error."""
    if not error_code:
        return DEFAULT_ERROR_STATUS
    return ERROR_HTTP_STATUS.get(error_code, DEFAULT_ERROR_STATUS)
