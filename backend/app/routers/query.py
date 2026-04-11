"""POST /api/v1/query — Medical QA endpoint powered by LightRAG."""

import logging

from fastapi import APIRouter, HTTPException

from app.models.request import QueryRequest
from app.models.response import QueryResponse, QueryMetadata
from app.services.pipeline import run_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["query"])


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Hỏi đáp Y tế bằng Ngôn ngữ Tự nhiên",
    description=(
        "Gửi câu hỏi y tế bằng tiếng Việt hoặc tiếng Anh. "
        "Hệ thống sử dụng LightRAG với Knowledge Graph để trả lời."
    ),
    responses={
        200: {"description": "Câu trả lời thành công"},
        400: {"description": "Câu hỏi không hợp lệ"},
        503: {"description": "Dịch vụ AI không khả dụng"},
    },
)
async def query_medical(request: QueryRequest) -> dict:
    """Handle medical QA queries.

    Args:
        request: QueryRequest with question, language, and optional mode.

    Returns:
        QueryResponse with answer, response_type, data, and metadata.
    """
    logger.info(
        "Query received: question='%s', lang=%s, mode=%s",
        request.question[:80],
        request.language,
        request.mode,
    )

    result = await run_pipeline(
        question=request.question,
        language=request.language,
        mode=request.mode,
    )

    # Map error codes to HTTP status codes
    if result.get("status") == "error":
        error_code = result.get("metadata", {}).get("error_code", "")
        if error_code == "INVALID_QUESTION":
            raise HTTPException(status_code=400, detail=result)
        elif error_code == "MODEL_UNAVAILABLE":
            raise HTTPException(status_code=503, detail=result)

    return result
