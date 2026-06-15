"""In-Memory Database Repository — Test double for IDatabaseRepository.

Stores rows in plain Python dicts, keyed by table name.
Supports transactions (no-op commit/rollback for simplicity).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator, Iterable
import re

from ports.database import IDatabaseRepository


class InMemoryDatabaseRepository(IDatabaseRepository):
    """In-memory implementation of IDatabaseRepository for testing.

    This is a simplified mock that stores rows in dicts.
    For complex SQL testing, use a real test database.
    """

    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {}
        self._query_results: list[dict[str, Any] | None] = []
        self._query_results_all: list[list[dict[str, Any]]] = []

    # ── Seeding helpers ───────────────────────────────────────────────────

    def seed_table(self, table: str, rows: list[dict[str, Any]]) -> None:
        """Pre-populate a table with rows."""
        self._tables[table] = list(rows)

    def set_fetch_one_result(self, result: dict[str, Any] | None) -> None:
        """Queue a result for the next ``fetch_one`` call."""
        self._query_results.append(result)

    def set_fetch_all_result(self, results: list[dict[str, Any]]) -> None:
        """Queue results for the next ``fetch_all`` call."""
        self._query_results_all.append(results)

    # ── IDatabaseRepository implementation ────────────────────────────────

    def fetch_one(
        self, query: str, params: Iterable[Any] = ()
    ) -> dict[str, Any] | None:
        if self._query_results:
            return self._query_results.pop(0)
        # Try to find in tables by parsing a simple SELECT
        return None

    def fetch_all(
        self, query: str, params: Iterable[Any] = ()
    ) -> list[dict[str, Any]]:
        if self._query_results_all:
            return self._query_results_all.pop(0)
        return []

    def execute(
        self, query: str, params: Iterable[Any] = ()
    ) -> None:
        # No-op for in-memory
        pass

    @contextmanager
    def transaction(self) -> Generator[Any, None, None]:
        """Yield a dummy connection object (self)."""
        yield self

    def fetch_one_in_tx(
        self, conn: Any, query: str, params: Iterable[Any] = ()
    ) -> dict[str, Any] | None:
        return self.fetch_one(query, params)

    def execute_in_tx(
        self, conn: Any, query: str, params: Iterable[Any] = ()
    ) -> None:
        self.execute(query, params)

    def execute_many_in_tx(
        self, conn: Any, query: str, params_seq: Iterable[Iterable[Any]]
    ) -> None:
        for params in params_seq:
            self.execute(query, params)
