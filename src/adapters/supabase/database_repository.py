"""Supabase/Postgres Database Repository Adapter — implements IDatabaseRepository.

Wraps psycopg3 (psycopg[binary]) to provide relational DB operations
against Supabase Postgres.

Extracted and refactored from backend/app/database.py (SupabaseDatabase class)
to implement the IDatabaseRepository port contract.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Generator, Iterable

from ports.database import IDatabaseRepository

logger = logging.getLogger(__name__)


class SupabaseDatabaseRepository(IDatabaseRepository):
    """Production adapter for IDatabaseRepository backed by Supabase Postgres.

    Args:
        db_url: psycopg3-compatible connection string
                (postgresql://user:pass@host/db?sslmode=require).
                If None, falls back to SUPABASE_DB_URL env var at connection time.
    """

    def __init__(self, db_url: str | None = None) -> None:
        self._db_url = db_url

    @property
    def db_url(self) -> str:
        if self._db_url:
            return self._db_url
        import os
        url = os.getenv("SUPABASE_DB_URL", "")
        if not url:
            from domain.shared.errors import InfrastructureError
            raise InfrastructureError(
                "SUPABASE_DB_URL is not configured. Set it in your .env file."
            )
        return url

    def _load_psycopg(self):
        """Import psycopg lazily to avoid hard dependency at import time."""
        try:
            import psycopg
            from psycopg.rows import dict_row
            return psycopg, dict_row
        except ImportError as exc:
            from domain.shared.errors import InfrastructureError
            raise InfrastructureError(
                "psycopg[binary] is not installed. "
                "Run: pip install 'psycopg[binary]'"
            ) from exc

    @contextmanager
    def _connect(self):
        """Open a single psycopg connection, yield it, then close."""
        psycopg, dict_row = self._load_psycopg()
        try:
            with psycopg.connect(self.db_url, row_factory=dict_row) as conn:
                yield conn
        except Exception as exc:
            from domain.shared.errors import InfrastructureError
            raise InfrastructureError(f"Database connection failed: {exc}") from exc

    # ── Transaction boundary ──────────────────────────────────────────────

    @contextmanager
    def transaction(self) -> Generator[Any, None, None]:
        """Open an atomic transaction boundary.

        Commits on clean exit, rolls back on exception.
        Yields the raw psycopg connection.
        """
        with self._connect() as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    # ── In-transaction helpers ────────────────────────────────────────────

    def fetch_one_in_tx(
        self, conn: Any, query: str, params: Iterable[Any] = ()
    ) -> dict[str, Any] | None:
        with conn.cursor() as cursor:
            cursor.execute(query, tuple(params))
            row = cursor.fetchone()
            return dict(row) if row is not None else None

    def execute_in_tx(
        self, conn: Any, query: str, params: Iterable[Any] = ()
    ) -> None:
        with conn.cursor() as cursor:
            cursor.execute(query, tuple(params))

    def execute_many_in_tx(
        self, conn: Any, query: str, params_seq: Iterable[Iterable[Any]]
    ) -> None:
        with conn.cursor() as cursor:
            for params in params_seq:
                cursor.execute(query, tuple(params))

    # ── Standalone helpers (each opens own connection) ────────────────────

    def fetch_one(
        self, query: str, params: Iterable[Any] = ()
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, tuple(params))
                row = cursor.fetchone()
                return dict(row) if row is not None else None

    def fetch_all(
        self, query: str, params: Iterable[Any] = ()
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, tuple(params))
                return [dict(row) for row in cursor.fetchall()]

    def execute(
        self, query: str, params: Iterable[Any] = ()
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, tuple(params))
            conn.commit()
