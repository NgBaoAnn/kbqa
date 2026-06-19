"""Shared type aliases used across domain modules.

These are simple type aliases — not Pydantic models, not dataclasses.
They provide semantic meaning to primitive types without introducing
runtime overhead.
"""

from __future__ import annotations

from typing import Any, Literal

# ── Identifiers ───────────────────────────────────────────────────────────

UserId = str
"""Supabase user UUID."""

ConversationId = str
"""Conversation UUID."""

MessageId = str
"""Message UUID."""

FeedbackId = str
"""Feedback UUID."""

ReviewItemId = str
"""Review item UUID."""

# ── Enums as Literals ─────────────────────────────────────────────────────
# Using Literal types instead of Enum classes for Pydantic compatibility
# and zero-overhead serialization.

UserRole = Literal["user", "reviewer", "admin"]

MessageRole = Literal["user", "assistant", "system"]

SafetyLevel = Literal["normal", "caution", "emergency"]

FeedbackRating = Literal["up", "down"]

FeedbackReason = Literal[
    "helpful", "incorrect", "unsafe", "unclear", "incomplete", "other"
]

Language = Literal["vi", "en"]

ExplanationLevel = Literal["general", "detailed", "expert"]

AnswerStyle = Literal["concise", "detailed"]

ResponseType = Literal["text", "table", "warning"]

ReviewStatus = Literal["pending", "resolved", "dismissed"]

# ── Source Types ──────────────────────────────────────────────────────────

SourceType = Literal[
    "cypher",
    "neo4j",
    "lightrag_entity",
    "lightrag_relationship",
    "lightrag_chunk",
    "document",
    "other",
]

# ── Generic ───────────────────────────────────────────────────────────────

JsonDict = dict[str, Any]
"""A JSON-serializable dictionary."""
