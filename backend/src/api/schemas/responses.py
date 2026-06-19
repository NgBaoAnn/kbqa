"""API Response schemas — outbound Pydantic models.

All models here represent what the API layer serialises back to the
frontend.  They are also used to generate the OpenAPI documentation.

Hierarchy:
    ChatResponse          — the main assistant response
    ├── ChatSource        — provenance / citation
    ├── SafetyPayload     — safety classification
    └── ChatMetadata      — engine execution metadata

    ConversationSummary   — list-view row
    ConversationDetail    — full conversation + messages
    └── MessageRecord     — a single message row

    DiseaseSummary / DiseaseListResponse / DiseaseDetailResponse
    FeedbackResponse
    AdminMetricsResponse / ReviewQueueResponse / ReviewItemRecord
    CurrentUserResponse / UserPreferencesResponse / MessageTraceResponse
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ── Shared type literal ────────────────────────────────────────────────────

ChatSourceType = Literal[
    "cypher",
    "neo4j",
    "lightrag_entity",
    "lightrag_relationship",
    "lightrag_chunk",
    "document",
    "other",
]


# ── Auth / User ────────────────────────────────────────────────────────────

class CurrentUserResponse(BaseModel):
    id: str
    email: str | None = None
    role: Literal["user", "reviewer", "admin"] = "user"
    display_name: str | None = None
    is_active: bool = True
    auth_provider: Literal["supabase"] = "supabase"

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "0b3fb8c2-88b4-41b9-8a70-5bd0fb0dd6a1",
                "email": "student@example.com",
                "role": "user",
                "display_name": "student",
                "is_active": True,
                "auth_provider": "supabase",
            }
        }
    )


class UserPreferencesResponse(BaseModel):
    id: str
    user_id: str
    language: Literal["vi", "en"]
    explanation_level: Literal["general", "detailed", "expert"]
    answer_style: Literal["concise", "detailed"]
    created_at: str
    updated_at: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "f1a2b3c4-d5e6-7890-abcd-ef1234567890",
                "user_id": "0b3fb8c2-88b4-41b9-8a70-5bd0fb0dd6a1",
                "language": "vi",
                "explanation_level": "general",
                "answer_style": "concise",
                "created_at": "2026-06-12T00:00:00Z",
                "updated_at": "2026-06-12T00:00:00Z",
            }
        }
    )


# ── Chat / Conversation ────────────────────────────────────────────────────

class ChatSource(BaseModel):
    """A single provenance / citation record attached to an assistant answer."""

    id: str | None = None
    source_type: ChatSourceType
    title: str
    snippet: str | None = None
    rank: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)


class SafetyPayload(BaseModel):
    """Safety classification for a chat response.

    Levels:
        ``normal``    General informational answer; standard disclaimer.
        ``caution``   Medical query that may affect health decisions.
        ``emergency`` Life-threatening situation; requires immediate action.
    """

    level: Literal["normal", "caution", "emergency", "safe"] = "normal"
    requires_emergency_notice: bool = False
    disclaimer: str = "Thông tin chỉ mang tính chất tham khảo."


class ChatMetadata(BaseModel):
    """Execution metadata for a chat response; persisted in query_logs."""

    engine: str
    query_mode: str
    execution_time_ms: float
    source_count: int
    cypher: str | None = None
    prompt_version: str | None = None
    model_name: str | None = None
    kg_version: str | None = None
    pipeline_version: str | None = None
    language: Literal["vi", "en"] | None = None
    explanation_level: Literal["general", "detailed", "expert"] | None = None
    answer_style: Literal["concise", "detailed"] | None = None
    original_question: str | None = None
    suggested_questions: list[str] = Field(default_factory=list)
    persisted: bool = True


class ChatResponse(BaseModel):
    conversation_id: str | None
    message_id: str | None
    status: Literal["success", "error"] = "success"
    response_type: str
    answer: str
    data: list[dict[str, Any]] | dict[str, Any] | None = None
    sources: list[ChatSource] = Field(default_factory=list)
    safety: SafetyPayload = Field(default_factory=SafetyPayload)
    suggested_questions: list[str] = Field(default_factory=list)
    metadata: ChatMetadata


# ── Conversation models ────────────────────────────────────────────────────

class ConversationSummary(BaseModel):
    id: str
    title: str
    language: Literal["vi", "en"] = "vi"
    created_at: str
    updated_at: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "a8e9b1fc-9c3e-4cda-a2f5-6b98f7a6e111",
                "title": "Tư vấn triệu chứng đau đầu",
                "language": "vi",
                "created_at": "2026-06-11T09:00:00Z",
                "updated_at": "2026-06-11T09:05:00Z",
            }
        }
    )


class MessageFeedback(BaseModel):
    rating: Literal["up", "down"]
    reason: str | None = None


class MessageRecord(BaseModel):
    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    response_type: str | None = None
    data: list[dict[str, Any]] | dict[str, Any] | None = None
    safety: dict[str, Any] | None = None
    suggested_questions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    feedback: MessageFeedback | None = None
    created_at: str


class ConversationDetail(BaseModel):
    conversation: ConversationSummary
    messages: list[MessageRecord]


# ── Feedback ───────────────────────────────────────────────────────────────

class FeedbackResponse(BaseModel):
    id: str
    message_id: str
    rating: str
    reason: str | None = None
    review_item_id: str | None = None
    created_at: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "4f9820db-6fe4-41a2-b1a0-13f620f3e101",
                "message_id": "c3d038c1-f6c9-4c82-9795-ecdf066e2f9d",
                "rating": "down",
                "reason": "incorrect",
                "review_item_id": "eacb657b-2f87-448d-bdbe-1e7ce0bd5f85",
                "created_at": "2026-06-11T09:06:00Z",
            }
        }
    )


# ── Knowledge ─────────────────────────────────────────────────────────────

class DiseaseSummary(BaseModel):
    id: str
    disease_name: str
    disease_category: str | None = None
    summary: str | None = None


class DiseaseListResponse(BaseModel):
    items: list[DiseaseSummary]
    total: int
    limit: int
    offset: int

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [
                    {
                        "id": "Bệnh tiểu đường",
                        "disease_name": "Bệnh tiểu đường",
                        "disease_category": "Nội tiết",
                        "summary": "Rối loạn chuyển hóa glucose mạn tính.",
                    }
                ],
                "total": 1,
                "limit": 20,
                "offset": 0,
            }
        }
    )


class DiseaseDetailResponse(BaseModel):
    id: str
    disease_name: str
    description: str | None = None
    symptoms: list[str] = Field(default_factory=list)
    treatments: list[str] = Field(default_factory=list)
    medicines: list[str] = Field(default_factory=list)
    advice: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "Bệnh tiểu đường",
                "disease_name": "Bệnh tiểu đường",
                "description": "Rối loạn chuyển hóa glucose mạn tính.",
                "symptoms": ["Khát nước", "Đi tiểu nhiều", "Mệt mỏi"],
                "treatments": ["Theo dõi đường huyết", "Điều chỉnh chế độ ăn"],
                "medicines": ["Theo chỉ định bác sĩ"],
                "advice": ["Tập luyện đều đặn", "Hạn chế đường tinh luyện"],
                "metadata": {"source": "Neo4j VietMedKG"},
            }
        }
    )


# ── Health ────────────────────────────────────────────────────────────────

class ServiceStatus(BaseModel):
    api: str = "running"
    supabase_postgres: str = "unknown"
    neo4j: str = "unknown"
    ai_engine: str = "unknown"
    llm_server: str = "unknown"
    embedding_server: str = "unknown"
    lightrag: str = "unknown"


class HealthResponse(BaseModel):
    status: str
    services: ServiceStatus
    version: str


# ── Admin ──────────────────────────────────────────────────────────────────

class AdminMetricsResponse(BaseModel):
    request_count: int
    average_latency_ms: float
    p95_latency_ms: float
    negative_feedback_rate: float
    engine_usage: dict[str, int]
    pending_review_count: int

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "request_count": 128,
                "average_latency_ms": 842.5,
                "p95_latency_ms": 3100.0,
                "negative_feedback_rate": 0.08,
                "engine_usage": {"cypher_direct": 88, "lightrag": 40},
                "pending_review_count": 3,
            }
        }
    )


class ReviewItemRecord(BaseModel):
    id: str
    status: Literal["pending", "resolved", "dismissed"]
    category: str
    feedback_id: str
    message_id: str
    conversation_id: str
    rating: str
    reason: str | None = None
    comment: str | None = None
    created_at: str
    question_content: str | None = None
    answer_content: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa",
                "status": "pending",
                "category": "answer_quality",
                "feedback_id": "99999999-9999-4999-8999-999999999999",
                "message_id": "44444444-4444-4444-8444-444444444444",
                "conversation_id": "11111111-1111-4111-8111-111111111111",
                "rating": "down",
                "reason": "incorrect",
                "comment": "Câu trả lời thiếu thông tin.",
                "created_at": "2026-06-11T09:06:00Z",
                "question_content": "Triệu chứng bệnh tiểu đường là gì?",
                "answer_content": "Bệnh tiểu đường có các triệu chứng...",
            }
        }
    )


class ReviewQueueResponse(BaseModel):
    items: list[ReviewItemRecord]
    total: int
    limit: int
    offset: int


# ── Version / Trace ────────────────────────────────────────────────────────

class VersionMetadata(BaseModel):
    prompt_version: str
    model_name: str
    kg_version: str
    pipeline_version: str


class MessageTraceResponse(BaseModel):
    message_id: str
    version_metadata: VersionMetadata
    engine_metadata: dict[str, Any] = Field(default_factory=dict)
