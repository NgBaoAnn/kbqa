"""Port: Database Repository.

Abstracts relational database operations (Supabase Postgres).
Adapters: SupabaseDatabaseRepository, InMemoryDatabaseRepository.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Any, Generator, Iterable


class IDatabaseRepository(ABC):
    """Port for relational database operations."""

    # ── Standalone operations (each opens its own connection) ─────────────

    @abstractmethod
    def fetch_one(
        self, query: str, params: Iterable[Any] = ()
    ) -> dict[str, Any] | None:
        """Execute a query and return the first row.

        Args:
            query: SQL query with %s placeholders.
            params: Query parameters.

        Returns:
            Dict of column→value, or None if no rows.

        Raises:
            InfrastructureError: If the database is unavailable.
        """
        ...

    @abstractmethod
    def fetch_all(
        self, query: str, params: Iterable[Any] = ()
    ) -> list[dict[str, Any]]:
        """Execute a query and return all rows.

        Args:
            query: SQL query with %s placeholders.
            params: Query parameters.

        Returns:
            List of row dicts.

        Raises:
            InfrastructureError: If the database is unavailable.
        """
        ...

    @abstractmethod
    def execute(
        self, query: str, params: Iterable[Any] = ()
    ) -> None:
        """Execute a write query (INSERT/UPDATE/DELETE).

        Args:
            query: SQL query with %s placeholders.
            params: Query parameters.

        Raises:
            InfrastructureError: If the database is unavailable.
        """
        ...

    # ── Transaction support ───────────────────────────────────────────────

    @abstractmethod
    @contextmanager
    def transaction(self) -> Generator[Any, None, None]:
        """Open an atomic transaction boundary.

        Yields a connection object. All operations via ``fetch_one_in_tx``,
        ``execute_in_tx`` within the block share a single transaction.
        Commits on clean exit, rolls back on exception.

        Usage::

            with db.transaction() as conn:
                row = db.fetch_one_in_tx(conn, SQL, params)
                db.execute_in_tx(conn, SQL, params)
        """
        ...

    @abstractmethod
    def fetch_one_in_tx(
        self, conn: Any, query: str, params: Iterable[Any] = ()
    ) -> dict[str, Any] | None:
        """Execute query within an existing transaction connection."""
        ...

    @abstractmethod
    def execute_in_tx(
        self, conn: Any, query: str, params: Iterable[Any] = ()
    ) -> None:
        """Execute write query within an existing transaction connection."""
        ...

    @abstractmethod
    def execute_many_in_tx(
        self, conn: Any, query: str, params_seq: Iterable[Iterable[Any]]
    ) -> None:
        """Execute query once per row within a transaction."""
        ...
