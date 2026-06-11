"""Pydantic contracts for the end-to-end product API."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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
    id: str
    source_type: str
    title: str
    snippet: str | None = None
    rank: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)


class SafetyPayload(BaseModel):
    level: Literal["normal", "caution", "emergency"] = "normal"
    requires_emergency_notice: bool = False
    disclaimer: str = "Thông tin chỉ mang tính chất tham khảo."


class ChatMetadata(BaseModel):
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
