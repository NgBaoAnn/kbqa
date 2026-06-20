"""API Request schemas — inbound Pydantic models.

All models here represent the request body / query params that the
API layer receives from the frontend.  They are validated by FastAPI
before reaching the router handler.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    language: Literal["vi", "en"] = "vi"

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Tư vấn triệu chứng đau đầu",
                "language": "vi",
            }
        }
    )


class MessageCreateRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    mode: str | None = Field(
        default=None,
        description="Optional LightRAG query mode override (naive | local | global | hybrid)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "question": "Bệnh tiểu đường có những triệu chứng gì?",
                "mode": None,
            }
        }
    )


class QueryRequest(BaseModel):
    """Standalone query (no conversation context)."""

    question: str = Field(min_length=1, max_length=1000)
    mode: str | None = Field(default=None)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "question": "Triệu chứng của bệnh cao huyết áp là gì?",
                "mode": None,
            }
        }
    )


class FeedbackCreateRequest(BaseModel):
    rating: Literal["up", "down"]
    reason: (
        Literal["helpful", "incorrect", "unsafe", "unclear", "incomplete", "other"]
        | None
    ) = None
    comment: str | None = Field(default=None, max_length=1000)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "rating": "down",
                "reason": "incorrect",
                "comment": "Nguồn trả lời không đúng với bệnh được hỏi.",
            }
        }
    )


class UserPreferencesUpdateRequest(BaseModel):
    """Partial update of user preferences (PATCH semantics)."""

    language: Literal["vi", "en"] | None = None
    explanation_level: Literal["general", "detailed", "expert"] | None = None
    answer_style: Literal["concise", "detailed"] | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "language": "en",
                "explanation_level": "detailed",
            }
        }
    )
