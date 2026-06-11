"""Small Supabase Postgres access layer for backend-owned app data."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterable

from fastapi import HTTPException, status

from app import config


def _db_not_configured() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "error_code": "DATABASE_NOT_CONFIGURED",
            "message": "Backend is missing SUPABASE_DB_URL.",
        },
    )


def _load_psycopg():
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "DATABASE_DRIVER_NOT_INSTALLED",
                "message": "Install psycopg[binary] to connect to Supabase Postgres.",
            },
        ) from exc

    return psycopg, dict_row


class SupabaseDatabase:
    """Parameterized SQL helper backed by psycopg.

    The backend connects with `SUPABASE_DB_URL`. No service-role API key is used
    here, which keeps the service-role key out of request and response paths.
    """

    def __init__(self, db_url: str | None = None) -> None:
        self._db_url = db_url

    @property
    def db_url(self) -> str:
        return self._db_url if self._db_url is not None else config.SUPABASE_DB_URL

    @contextmanager
    def connect(self):
        if not self.db_url:
            raise _db_not_configured()

        psycopg, dict_row = _load_psycopg()
        with psycopg.connect(self.db_url, row_factory=dict_row) as connection:
            yield connection

    def fetch_one(self, query: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, tuple(params))
                row = cursor.fetchone()
                return dict(row) if row is not None else None

    def fetch_all(self, query: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, tuple(params))
                return [dict(row) for row in cursor.fetchall()]

    def execute(self, query: str, params: Iterable[Any] = ()) -> None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, tuple(params))


_database = SupabaseDatabase()


def get_database() -> SupabaseDatabase:
    return _database
