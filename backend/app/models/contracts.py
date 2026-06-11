"""Pydantic contracts for the end-to-end product API.

Public API contracts (consumed by router and frontend):
    CurrentUserResponse, ConversationCreateRequest, ConversationSummary,
    ConversationDetail, MessageCreateRequest, MessageRecord,
    ChatResponse, ChatSource, SafetyPayload, ChatMetadata,
    FeedbackCreateRequest, FeedbackResponse,
    DiseaseSummary, DiseaseListResponse, DiseaseDetailResponse,
    AdminMetricsResponse

Internal service contracts (not serialised to HTTP responses directly):
    AIServiceResult  — returned by ai_service, consumed by chat_service
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ── Source type literals ──────────────────────────────────────────────────
# Extending this list is a non-breaking change (additive).
ChatSourceType = Literal[
    "cypher",
    "neo4j",
    "lightrag_entity",
    "lightrag_relationship",
    "lightrag_chunk",
    "document",
    "other",
]


class CurrentUserResponse(BaseModel):
    id: str
    email: str | None = None
    role: Literal["user", "admin"] = "user"
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


class MessageRecord(BaseModel):
    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    response_type: str | None = None
    data: list[dict[str, Any]] | dict[str, Any] | None = None
    safety: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ConversationDetail(BaseModel):
    conversation: ConversationSummary
    messages: list[MessageRecord]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "conversation": ConversationSummary.model_config["json_schema_extra"]["example"],
                "messages": [
                    {
                        "id": "2d4b5b43-7074-4217-8a3b-8231f727d402",
                        "role": "user",
                        "content": "Bệnh tiểu đường có triệu chứng gì?",
                        "response_type": None,
                        "data": None,
                        "safety": None,
                        "metadata": {},
                        "created_at": "2026-06-11T09:01:00Z",
                    }
                ],
            }
        }
    )


class MessageCreateRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    mode: str | None = Field(default=None, description="Optional LightRAG query mode override")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "question": "Bệnh tiểu đường có những triệu chứng gì?",
                "mode": None,
            }
        }
    )


class ChatSource(BaseModel):
    """A single provenance / citation record attached to an assistant answer.

    ``source_type`` is constrained to known values; use ``"other"`` as a
    graceful fallback for any engine that is added later without an explicit
    type mapping.
    """

    id: str
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

    level: Literal["normal", "caution", "emergency"] = "normal"
    requires_emergency_notice: bool = False
    disclaimer: str = "Thông tin chỉ mang tính chất tham khảo."


class ChatMetadata(BaseModel):
    """Execution metadata for a chat response; persisted in query_logs."""

    engine: str
    query_mode: str
    execution_time_ms: float
    source_count: int
    cypher: str | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    status: Literal["success", "error"] = "success"
    response_type: str
    answer: str
    data: list[dict[str, Any]] | dict[str, Any] | None = None
    sources: list[ChatSource] = Field(default_factory=list)
    safety: SafetyPayload = Field(default_factory=SafetyPayload)
    suggested_questions: list[str] = Field(default_factory=list)
    metadata: ChatMetadata


# ── Internal service contract ─────────────────────────────────────────────


class AIServiceResult(BaseModel):
    """Internal result model returned by ``ai_service.answer_question()``.

    This is NOT exposed directly as an HTTP response.  ``chat_service`` maps
    this into a persisted ``ChatResponse`` after saving messages to Supabase.

    Attributes:
        answer:               The synthesized answer text.
        response_type:        One of 'text', 'table', 'warning'.
        data:                 Structured data for table rendering (may be None).
        sources:              Normalised provenance records.
        safety:               Safety classification for the answer.
        suggested_questions:  Follow-up questions (may be empty).
        metadata:             Execution metadata for query_logs.
        raw_engine_metadata:  Unprocessed dict from the pipeline (for Người 2
                              to persist in query_logs without re-computing).
    """

    answer: str
    response_type: str
    data: list[dict[str, Any]] | dict[str, Any] | None = None
    sources: list[ChatSource] = Field(default_factory=list)
    safety: SafetyPayload = Field(default_factory=SafetyPayload)
    suggested_questions: list[str] = Field(default_factory=list)
    metadata: ChatMetadata
    raw_engine_metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "conversation_id": "a8e9b1fc-9c3e-4cda-a2f5-6b98f7a6e111",
                "message_id": "c3d038c1-f6c9-4c82-9795-ecdf066e2f9d",
                "status": "success",
                "response_type": "text",
                "answer": "Bệnh tiểu đường thường có các triệu chứng như khát nước, đi tiểu nhiều và mệt mỏi.",
                "data": None,
                "sources": [
                    {
                        "id": "6e690f3e-92e1-49f8-878e-b48bb4875c3b",
                        "source_type": "cypher",
                        "title": "Neo4j VietMedKG",
                        "snippet": "MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom) ...",
                        "rank": 1,
                        "metadata": {"engine": "cypher_direct"},
                    }
                ],
                "safety": {
                    "level": "normal",
                    "requires_emergency_notice": False,
                    "disclaimer": "Thông tin chỉ mang tính chất tham khảo.",
                },
                "suggested_questions": ["Khi nào người bệnh tiểu đường nên đi khám?"],
                "metadata": {
                    "engine": "cypher_direct",
                    "query_mode": "cypher:template:symptoms",
                    "execution_time_ms": 120,
                    "source_count": 1,
                    "cypher": "MATCH ...",
                },
            }
        }
    )


class FeedbackCreateRequest(BaseModel):
    rating: Literal["up", "down"]
    reason: Literal["helpful", "incorrect", "unsafe", "unclear", "incomplete", "other"] | None = None
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
    """A single pending review item surfaced from a negative feedback signal."""

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
            }
        }
    )


class ReviewQueueResponse(BaseModel):
    """Paginated list of review items for the admin review queue."""

    items: list[ReviewItemRecord]
    total: int
    limit: int
    offset: int

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [ReviewItemRecord.model_config["json_schema_extra"]["example"]],
                "total": 1,
                "limit": 20,
                "offset": 0,
            }
        }
    )
