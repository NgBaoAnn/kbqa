"""Query router — POST /api/v1/query (standalone, no conversation context).

Thin handler: parse → call AnswerQuestionUseCase → format response.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from api.middleware.auth import CurrentUser, get_current_user
from api.schemas.requests import QueryRequest
from api.schemas.responses import (
    ChatMetadata,
    ChatResponse,
    ChatSource,
    SafetyPayload,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["query"])

# Error code → HTTP status (spec: 05_API_SYSTEM_DESIGN.md §4.2)
_ERROR_HTTP: dict[str, int] = {
    "INVALID_QUESTION": 400,
    "CYPHER_GENERATION_FAILED": 422,
    "LIGHTRAG_QUERY_FAILED": 500,
    "NO_DATA_FOUND": 404,
    "DATABASE_ERROR": 500,
    "MODEL_UNAVAILABLE": 503,
    "TIMEOUT": 504,
}


@router.post(
    "/query",
    response_model=ChatResponse,
    summary="Hỏi đáp Y tế",
    description=(
        "Gửi câu hỏi y tế bằng tiếng Việt hoặc tiếng Anh. "
        "Hệ thống sử dụng LightRAG + Neo4j Knowledge Graph để trả lời."
    ),
    responses={
        400: {"description": "Câu hỏi không hợp lệ"},
        404: {"description": "Không tìm thấy dữ liệu"},
        422: {"description": "Không thể sinh truy vấn Cypher"},
        429: {"description": "Vượt quá giới hạn request"},
        503: {"description": "Dịch vụ AI không khả dụng"},
        504: {"description": "Timeout"},
    },
)
async def query_medical(
    payload: QueryRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> ChatResponse:
    """Execute a medical QA query without creating a conversation record."""
    container = request.app.state.container

    # Load preferences
    from use_cases.manage_preferences import ManagePreferencesUseCase
    prefs_uc = ManagePreferencesUseCase(db=container.db)
    preferences = prefs_uc.get_preferences(user_id=current_user.id)

    # Execute QA use case
    result = await container.answer_question.execute(
        question=payload.question,
        mode=payload.mode,
        preferences=preferences,
    )

    # Map error_code → HTTP status (spec: 05_API_SYSTEM_DESIGN.md §4.2)
    error_code = (result.metadata or {}).get("error_code")
    if error_code and error_code in _ERROR_HTTP:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=_ERROR_HTTP[error_code],
            detail={"error_code": error_code, "message": result.answer},
        )

    # Standalone query: conversation_id/message_id are null (not persisted)
    return _to_chat_response(
        result,
        conversation_id=None,
        message_id=None,
        version_metadata=getattr(container, "version_metadata", {}),
        original_question=payload.question,
    )


def _to_chat_response(
    result,
    *,
    conversation_id: str | None,
    message_id: str | None,
    version_metadata: dict | None = None,
    original_question: str | None = None,
) -> ChatResponse:
    """Map AIServiceResult → ChatResponse (thin mapping, no business logic)."""
    safety_raw = result.safety or {}
    safety = SafetyPayload(
        level=safety_raw.get("level", "normal"),
        requires_emergency_notice=safety_raw.get("requires_emergency_notice", False),
        disclaimer=safety_raw.get("disclaimer", "Thông tin chỉ mang tính chất tham khảo."),
    )

    sources = [
        ChatSource(
            id=s.get("id"),
            source_type=s.get("source_type", "other"),
            title=s.get("title", ""),
            snippet=s.get("snippet"),
            rank=s.get("rank", 1),
            metadata=s.get("metadata", {}),
        )
        for s in (result.sources or [])
    ]

    meta = result.metadata or {}
    vm = version_metadata or {}
    metadata = ChatMetadata(
        engine=meta.get("engine", "unknown"),
        query_mode=meta.get("query_mode", "auto"),
        execution_time_ms=meta.get("execution_time_ms", 0.0),
        source_count=meta.get("source_count", len(sources)),
        cypher=meta.get("cypher"),
        # Version fields from AppContainer.version_metadata
        prompt_version=vm.get("prompt_version"),
        model_name=vm.get("model_name"),
        kg_version=vm.get("kg_version"),
        pipeline_version=vm.get("pipeline_version"),
        language=meta.get("language"),
        explanation_level=meta.get("explanation_level"),
        answer_style=meta.get("answer_style"),
        original_question=original_question,
        suggested_questions=result.suggested_questions or [],
        persisted=False,
    )

    return ChatResponse(
        conversation_id=conversation_id,
        message_id=message_id,
        status="success",
        response_type=result.response_type,
        answer=result.answer,
        data=result.data,
        sources=sources,
        safety=safety,
        suggested_questions=result.suggested_questions or [],
        metadata=metadata,
    )
