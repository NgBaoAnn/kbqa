"""Analytics / admin metrics service — S3-BE-03 & S3-BE-04.

Reads from Supabase Postgres app data only.
Never calls Neo4j. Never returns secrets.

Metrics computed
----------------
- request_count          : Total rows in query_logs (one per AI response)
- average_latency_ms     : Mean execution_time_ms across all query_logs
- p95_latency_ms         : 95th-percentile latency using Postgres PERCENTILE_CONT
- negative_feedback_rate : (count of 'down' ratings) / (total feedback); 0.0 if no feedback
- engine_usage           : GROUP BY engine count from query_logs
- pending_review_count   : COUNT(*) from review_items WHERE status = 'pending'
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, status

from app.database import get_database
from app.models.contracts import (
    AdminMetricsResponse,
    ReviewItemRecord,
    ReviewQueueResponse,
)

logger = logging.getLogger(__name__)


def _db_error(exc: Exception, context: str) -> HTTPException:
    """Log the real error and return a safe 503 to the caller."""
    logger.error("analytics_service: %s failed: %s", context, exc)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "error_code": "ANALYTICS_UNAVAILABLE",
            "message": "Analytics data is temporarily unavailable.",
        },
    )


# ── Public API ─────────────────────────────────────────────────────────────


async def get_admin_metrics() -> AdminMetricsResponse:
    """Compute and return admin operational metrics from Supabase Postgres.

    All queries are read-only against ``query_logs``, ``feedback``, and
    ``review_items``. No secrets are included in any returned value.
    """
    db = get_database()
    try:
        # ── Request count + latency statistics ───────────────────────────
        latency_row = db.fetch_one(
            """
            SELECT
                COUNT(*)                                                          AS request_count,
                COALESCE(AVG(execution_time_ms), 0.0)                             AS average_latency_ms,
                COALESCE(
                    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY execution_time_ms),
                    0.0
                )                                                                 AS p95_latency_ms
            FROM public.query_logs
            """
        )
        request_count: int = int(latency_row["request_count"]) if latency_row else 0
        average_latency_ms: float = float(latency_row["average_latency_ms"]) if latency_row else 0.0
        p95_latency_ms: float = float(latency_row["p95_latency_ms"]) if latency_row else 0.0

        # ── Negative feedback rate ────────────────────────────────────────
        feedback_row = db.fetch_one(
            """
            SELECT
                COUNT(*)                                      AS total_feedback,
                COUNT(*) FILTER (WHERE rating = 'down')       AS negative_count
            FROM public.feedback
            """
        )
        total_feedback: int = int(feedback_row["total_feedback"]) if feedback_row else 0
        negative_count: int = int(feedback_row["negative_count"]) if feedback_row else 0
        negative_feedback_rate: float = (
            round(negative_count / total_feedback, 4) if total_feedback > 0 else 0.0
        )

        # ── Engine usage breakdown ────────────────────────────────────────
        engine_rows = db.fetch_all(
            """
            SELECT engine, COUNT(*) AS cnt
            FROM public.query_logs
            GROUP BY engine
            ORDER BY cnt DESC
            """
        )
        engine_usage: dict[str, int] = {
            row["engine"]: int(row["cnt"]) for row in engine_rows
        }

        # ── Pending review items ──────────────────────────────────────────
        review_row = db.fetch_one(
            """
            SELECT COUNT(*) AS pending_count
            FROM public.review_items
            WHERE status = 'pending'
            """
        )
        pending_review_count: int = int(review_row["pending_count"]) if review_row else 0

    except HTTPException:
        raise
    except Exception as exc:
        raise _db_error(exc, "get_admin_metrics") from exc

    return AdminMetricsResponse(
        request_count=request_count,
        average_latency_ms=round(average_latency_ms, 2),
        p95_latency_ms=round(p95_latency_ms, 2),
        negative_feedback_rate=negative_feedback_rate,
        engine_usage=engine_usage,
        pending_review_count=pending_review_count,
    )


async def get_review_queue(*, limit: int, offset: int) -> ReviewQueueResponse:
    """Return a paginated list of review items for the admin review queue.

    Joins ``review_items`` → ``feedback`` → ``messages`` to surface enough
    context for an admin to identify which message triggered the review.

    Args:
        limit: Page size (1–100).
        offset: Pagination offset.

    Returns:
        A ``ReviewQueueResponse`` with items ordered newest first.
    """
    db = get_database()
    try:
        # Total count for pagination
        count_row = db.fetch_one("SELECT COUNT(*) AS total FROM public.review_items")
        total: int = int(count_row["total"]) if count_row else 0

        # Full join: review_items → feedback → assistant message → preceding user message
        rows: list[dict[str, Any]] = db.fetch_all(
            """
            SELECT
                ri.id               AS review_item_id,
                ri.status           AS status,
                ri.category         AS category,
                ri.created_at       AS created_at,
                f.id                AS feedback_id,
                f.message_id        AS message_id,
                f.rating            AS rating,
                f.reason            AS reason,
                f.comment           AS comment,
                m.conversation_id   AS conversation_id,
                m.content           AS answer_content,
                prev_m.content      AS question_content
            FROM public.review_items ri
            JOIN public.feedback     f      ON f.id  = ri.feedback_id
            JOIN public.messages     m      ON m.id  = f.message_id
            LEFT JOIN public.messages prev_m ON (
                prev_m.conversation_id = m.conversation_id
                AND prev_m.role = 'user'
                AND prev_m.created_at = (
                    SELECT MAX(u.created_at)
                    FROM public.messages u
                    WHERE u.conversation_id = m.conversation_id
                      AND u.role = 'user'
                      AND u.created_at < m.created_at
                )
            )
            ORDER BY ri.created_at DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise _db_error(exc, "get_review_queue") from exc

    items = [
        ReviewItemRecord(
            id=str(row["review_item_id"]),
            status=row["status"],
            category=row["category"],
            feedback_id=str(row["feedback_id"]),
            message_id=str(row["message_id"]),
            conversation_id=str(row["conversation_id"]),
            rating=row["rating"],
            reason=row.get("reason"),
            comment=row.get("comment"),
            created_at=str(row["created_at"]),
            question_content=row.get("question_content"),
            answer_content=row.get("answer_content"),
        )
        for row in rows
    ]

    return ReviewQueueResponse(items=items, total=total, limit=limit, offset=offset)
