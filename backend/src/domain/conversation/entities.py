"""Conversation Domain — Entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Conversation:
    """A thread of messages between a user and the assistant."""

    id: str
    user_id: str
    title: str
    language: str = "vi"
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Message:
    """A single turn in a conversation."""

    id: str
    conversation_id: str
    role: str  # "user" | "assistant" | "system"
    content: str
    response_type: str | None = None
    data: list[dict[str, Any]] | dict[str, Any] | None = None
    safety: dict[str, Any] | None = None
    suggested_questions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""


@dataclass
class Feedback:
    """User's rating on an assistant message."""

    id: str
    message_id: str
    user_id: str
    rating: str  # "up" | "down"
    reason: str | None = None
    comment: str | None = None
    review_item_id: str | None = None
    created_at: str = ""
