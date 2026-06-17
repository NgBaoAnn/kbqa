"""In-Memory Database Repository — Test double for IDatabaseRepository.

Phase 4 upgrade: now supports full conversation and preference CRUD
using in-memory stores, so ManageConversationUseCase and
ManagePreferencesUseCase unit tests can pass without a real DB.
"""

from __future__ import annotations

import uuid
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator, Iterable

from ports.database import IDatabaseRepository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


class InMemoryDatabaseRepository(IDatabaseRepository):
    """In-memory implementation of IDatabaseRepository for testing.

    Supports:
    - Conversation CRUD (conversations + messages tables)
    - User preferences CRUD
    - Feedback (message not found path returns None → ValueError upstream)
    - Queue-based mock fallback for arbitrary queries via set_fetch_one_result
    """

    def __init__(self) -> None:
        # Real in-memory stores
        self._conversations: dict[str, dict[str, Any]] = {}   # id → conv row
        self._messages: list[dict[str, Any]] = []              # list of msg rows
        self._preferences: dict[str, dict[str, Any]] = {}     # user_id → prefs
        self._feedback: list[dict[str, Any]] = []
        self._review_items: list[dict[str, Any]] = []
        self._query_logs: list[dict[str, Any]] = []
        self._message_sources: list[dict[str, Any]] = []

        # Queue-based fallback for arbitrary query mocking
        self._fetch_one_queue: list[dict[str, Any] | None] = []
        self._fetch_all_queue: list[list[dict[str, Any]]] = []

    # ── Seeding helpers ───────────────────────────────────────────────────

    def seed_table(self, table: str, rows: list[dict[str, Any]]) -> None:
        """Pre-populate a table with rows (legacy queue-based test helper)."""
        pass  # Not needed with real stores; kept for API compatibility

    def set_fetch_one_result(self, result: dict[str, Any] | None) -> None:
        """Queue a result for the next ``fetch_one`` call not handled by stores."""
        self._fetch_one_queue.append(result)

    def set_fetch_all_result(self, results: list[dict[str, Any]]) -> None:
        """Queue results for the next ``fetch_all`` call."""
        self._fetch_all_queue.append(results)

    # ── Smart query dispatch ──────────────────────────────────────────────

    def fetch_one(
        self, query: str, params: Iterable[Any] = ()
    ) -> dict[str, Any] | None:
        q = query.strip().lower()
        params_list = list(params)

        # ── CONVERSATIONS ─────────────────────────────────────────────────
        if "insert into public.conversations" in q:
            user_id, title, language = params_list[0], params_list[1], params_list[2]
            conv_id = _new_id()
            now = _now()
            row = {
                "id": conv_id,
                "title": title,
                "language": language,
                "created_at": now,
                "updated_at": now,
                "_user_id": user_id,  # internal only
            }
            self._conversations[conv_id] = row
            return {k: v for k, v in row.items() if not k.startswith("_")}

        if "from public.conversations" in q and "where id = " in q and "user_id = " in q:
            conv_id, user_id = params_list[0], params_list[1]
            conv = self._conversations.get(conv_id)
            if conv and conv.get("_user_id") == user_id:
                return {k: v for k, v in conv.items() if not k.startswith("_")}
            return None

        if "update public.conversations" in q and "updated_at" in q:
            # update conversation timestamp — no-op for in-memory
            return None

        # ── MESSAGES ──────────────────────────────────────────────────────
        if "insert into public.messages" in q:
            conv_id = params_list[0]
            if "values (%s, 'user'" in q:
                role = "user"
                content = params_list[1]
                response_type = None
                data = None
                safety = None
                metadata = json.loads(params_list[2]) if len(params_list) > 2 and params_list[2] else {}
            elif "values (%s, 'assistant'" in q:
                role = "assistant"
                content = params_list[1]
                response_type = params_list[2]
                data = json.loads(params_list[3]) if params_list[3] else None
                safety = json.loads(params_list[4]) if params_list[4] else None
                metadata = json.loads(params_list[5]) if params_list[5] else {}
            else:
                role = params_list[1]
                content = params_list[2]
                response_type = params_list[3] if len(params_list) > 3 else "text"
                data = None
                safety = None
                metadata = None
            msg_id = _new_id()
            now = _now()
            row = {
                "id": msg_id,
                "conversation_id": conv_id,
                "role": role,
                "content": content,
                "response_type": response_type,
                "data": data,
                "safety": safety,
                "metadata": metadata,
                "created_at": now,
            }
            self._messages.append(row)
            return row

        if "from public.messages m" in q and "join public.conversations c" in q:
            msg_id = params_list[0]
            msg = next((m for m in self._messages if m.get("id") == msg_id), None)
            if msg is None or msg.get("role") != "assistant":
                return None
            conv = self._conversations.get(msg.get("conversation_id"))
            if conv is None:
                return None
            if "m.metadata" in q:
                return {
                    "id": msg["id"],
                    "metadata": msg.get("metadata") or {},
                    "owner_id": conv.get("_user_id"),
                }
            # Feedback ownership check.
            return {
                "id": msg["id"],
                "role": msg.get("role"),
                "message_id": msg["id"],
                "conversation_id": msg.get("conversation_id"),
                "owner_id": conv.get("_user_id"),
            }

        # ── USER PREFERENCES ──────────────────────────────────────────────
        if "from public.user_preferences" in q and "where user_id = " in q and "insert" not in q and "update" not in q:
            user_id = params_list[0]
            pref = self._preferences.get(user_id)
            return dict(pref) if pref else None

        if "insert into public.user_preferences" in q:
            user_id = params_list[0]
            language = params_list[1]
            explanation_level = params_list[2]
            answer_style = params_list[3]
            now = _now()
            row = {
                "id": _new_id(),
                "user_id": user_id,
                "language": language,
                "explanation_level": explanation_level,
                "answer_style": answer_style,
                "created_at": now,
                "updated_at": now,
            }
            self._preferences[user_id] = row
            return dict(row)

        if "update public.user_preferences" in q and "where user_id = " in q:
            # Dynamic SET clause — parse by detecting known column names
            user_id = params_list[-1]
            pref = self._preferences.get(user_id)
            if pref is None:
                return None
            # Update only known columns found in the query
            for col in ("language", "explanation_level", "answer_style"):
                if col in q:
                    idx = list(q.split()).index(col.lower()) if col.lower() in q.split() else -1
                    # Simpler: just accept all params except the last (user_id)
                    pass
            # Actually: params = [val1, val2, ..., user_id]; set clauses in order
            update_vals = params_list[:-1]
            col_order = []
            for col in ("language", "explanation_level", "answer_style"):
                if f"{col} = " in q or f"{col}=%s" in q or f"{col} =%s" in q:
                    col_order.append(col)
            for col, val in zip(col_order, update_vals):
                pref[col] = val
            pref["updated_at"] = _now()
            self._preferences[user_id] = pref
            return dict(pref)

        # ── FEEDBACK ──────────────────────────────────────────────────────
        if "insert into public.feedback" in q:
            msg_id, user_id, rating, reason, comment = (params_list + [None, None, None, None, None])[:5]
            now = _now()
            row = {
                "id": _new_id(),
                "message_id": str(msg_id),
                "rating": rating,
                "reason": reason,
                "comment": comment,
                "created_at": now,
            }
            self._feedback.append(row)
            return dict(row)

        if "insert into public.review_items" in q:
            feedback_id, category = params_list[0], params_list[1]
            row = {"id": _new_id(), "feedback_id": feedback_id, "status": "pending", "category": category}
            self._review_items.append(row)
            return dict(row)

        # ── ANALYTICS ─────────────────────────────────────────────────────
        if "from public.query_logs" in q and "count(*)" in q:
            return {"request_count": len(self._query_logs), "average_latency_ms": 0.0, "p95_latency_ms": 0.0}

        if "from public.feedback" in q and "count(*)" in q:
            total = len(self._feedback)
            neg = sum(1 for f in self._feedback if f.get("rating") == "down")
            return {"total_feedback": total, "negative_count": neg}

        if "from public.review_items" in q and "count(*)" in q and "status = 'pending'" in q:
            count = sum(1 for r in self._review_items if r.get("status") == "pending")
            return {"pending_count": count}

        if "count(*) as total" in q and "from public.review_items" in q:
            return {"total": len(self._review_items)}

        # ── Queue-based fallback ──────────────────────────────────────────
        if self._fetch_one_queue:
            return self._fetch_one_queue.pop(0)
        return None

    def fetch_all(
        self, query: str, params: Iterable[Any] = ()
    ) -> list[dict[str, Any]]:
        q = query.strip().lower()
        params_list = list(params)

        # ── CONVERSATIONS ─────────────────────────────────────────────────
        if "from public.conversations" in q and "where user_id = " in q and "order by" in q:
            user_id = params_list[0]
            return [
                {k: v for k, v in conv.items() if not k.startswith("_")}
                for conv in self._conversations.values()
                if conv.get("_user_id") == user_id
            ]

        # ── MESSAGES ──────────────────────────────────────────────────────
        if "from public.messages m" in q and "where m.conversation_id = " in q:
            conv_id = params_list[1] if len(params_list) > 1 else params_list[0]
            return [m for m in self._messages if m.get("conversation_id") == conv_id]

        # ── ANALYTICS ─────────────────────────────────────────────────────
        if "from public.query_logs" in q and "group by engine" in q:
            return []

        if "from public.review_items ri" in q:
            return []

        # ── Queue fallback ────────────────────────────────────────────────
        if self._fetch_all_queue:
            return self._fetch_all_queue.pop(0)
        return []

    def execute(
        self, query: str, params: Iterable[Any] = ()
    ) -> None:
        q = query.strip().lower()
        params_list = list(params)

        if "insert into public.message_sources" in q:
            message_id, source_type, title, snippet, metadata_json, rank = params_list
            self._message_sources.append({
                "message_id": message_id,
                "source_type": source_type,
                "title": title,
                "snippet": snippet,
                "metadata": json.loads(metadata_json) if metadata_json else {},
                "rank": rank,
            })
            return

        if "insert into public.query_logs" in q:
            (
                message_id,
                engine,
                query_mode,
                execution_time_ms,
                source_count,
                status,
                metadata_json,
            ) = params_list
            self._query_logs.append({
                "message_id": message_id,
                "engine": engine,
                "query_mode": query_mode,
                "execution_time_ms": execution_time_ms,
                "source_count": source_count,
                "status": status,
                "metadata": json.loads(metadata_json) if metadata_json else {},
            })
            return

        if "update public.conversations" in q and "updated_at" in q:
            conv_id = params_list[0]
            if conv_id in self._conversations:
                self._conversations[conv_id]["updated_at"] = _now()
            return

    @contextmanager
    def transaction(self) -> Generator[Any, None, None]:
        """Yield self as dummy connection."""
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
