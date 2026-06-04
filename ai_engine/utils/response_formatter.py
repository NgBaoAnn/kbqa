"""Response Formatter — Convert LightRAG output to AegisHealth API response format.

Transforms raw LightRAG query results into the standardized QueryResponse
JSON structure defined in docs/05_API_SYSTEM_DESIGN.md.
"""

import logging
import re
from typing import Any

from ai_engine.services.intent_classifier import (
    detect_emergency_intent,
    detect_list_intent,
)

logger = logging.getLogger(__name__)

from ai_engine.utils.ui_constants import MEDICAL_DISCLAIMER

# ── Dangerous symptom keywords for warning detection ──────────────────────
DANGER_KEYWORDS = [
    "đau ngực",
    "khó thở",
    "co giật",
    "bất tỉnh",
    "chảy máu",
    "ngừng tim",
    "đột quỵ",
    "sốt cao",
    "ngộ độc",
    "tự tử",
    "chest pain",
    "difficulty breathing",
    "seizure",
    "unconscious",
    "bleeding",
    "cardiac arrest",
    "stroke",
    "high fever",
    "poisoning",
    "suicide",
]


def classify_response_type(question: str, answer: str) -> str:
    """Classify the response type based on question and answer content.

    Uses intent_classifier for strong regex-based emergency detection on
    the question, then falls back to keyword matching on the answer for
    additional coverage. Combines both approaches for best accuracy.

    Args:
        question: The original user question.
        answer: The LightRAG synthesized answer.

    Returns:
        One of: 'warning', 'table', 'text'.
    """
    # 1. Priority: Detect emergency from QUESTION (intent_classifier — stronger regex patterns)
    if detect_emergency_intent(question):
        logger.info("Emergency intent detected via intent_classifier (question)")
        return "warning"

    # 2. Fallback: Detect emergency from ANSWER (keyword matching)
    combined = (question + " " + answer).lower()
    for keyword in DANGER_KEYWORDS:
        if keyword in combined:
            logger.info("Emergency keyword detected: '%s'", keyword)
            return "warning"

    # 3. Detect list intent from question + verify answer has list structure
    if detect_list_intent(question):
        list_items = re.findall(r"^[\s]*[-•\d.]+\s+\S", answer, re.MULTILINE)
        if len(list_items) >= 2:
            return "table"

    # 4. Check for list-like content in answer → table
    answer_lower = answer.lower()

    # Count items that look like a list (lines starting with - or • or numbers)
    list_items = re.findall(r"^[\s]*[-•\d.]+\s+\S", answer, re.MULTILINE)
    if len(list_items) >= 2:
        return "table"

    # Count comma-separated items after a colon
    colon_lists = re.findall(r":\s*(.+?)(?:\.|$)", answer)
    for item_str in colon_lists:
        items = [x.strip() for x in item_str.split(",") if x.strip()]
        if len(items) >= 3:
            return "table"

    return "text"


def extract_table_data(answer: str) -> list[dict[str, str]] | None:
    """Try to extract structured table data from a text answer.

    Looks for list-like patterns in the answer and converts them
    into a list of dicts suitable for table rendering.

    Args:
        answer: The raw text answer.

    Returns:
        List of dicts if table data is found, None otherwise.
    """
    # Try to find bullet-point or numbered lists
    list_items = re.findall(r"^[\s]*[-•]\s*(.+)$", answer, re.MULTILINE)
    if len(list_items) >= 2:
        return [{"item": item.strip()} for item in list_items]

    numbered_items = re.findall(r"^[\s]*\d+[.)]\s*(.+)$", answer, re.MULTILINE)
    if len(numbered_items) >= 2:
        return [{"item": item.strip()} for item in numbered_items]

    return None


def format_warning_answer(answer: str) -> str:
    """Enhance answer with warning formatting.

    Args:
        answer: The original answer text.

    Returns:
        Answer with warning prefix and emergency CTA.
    """
    warning_prefix = "⚠️ CẢNH BÁO Y TẾ: "
    emergency_cta = (
        "\n\n🏥 Nếu bạn đang gặp triệu chứng nguy hiểm, "
        "VUI LÒNG LIÊN HỆ BÁC SĨ HOẶC GỌI CẤP CỨU NGAY LẬP TỨC."
        "\n\nHệ thống này KHÔNG thay thế chẩn đoán y tế chuyên nghiệp."
    )

    if not answer.startswith("⚠️"):
        answer = warning_prefix + answer

    return answer + emergency_cta


def format_lightrag_response(
    raw_answer: str,
    question: str,
    query_mode: str,
    execution_time_ms: float,
) -> dict[str, Any]:
    """Format a LightRAG query result into the standard API response.

    Follows the QueryResponse schema from docs/05_API_SYSTEM_DESIGN.md:
    {status, response_type, answer, data, metadata}

    Args:
        raw_answer: Raw text answer from LightRAG.
        question: The original user question.
        query_mode: The LightRAG query mode used.
        execution_time_ms: Total execution time in milliseconds.

    Returns:
        Dict conforming to the QueryResponse schema.
    """
    if not raw_answer or not raw_answer.strip():
        return {
            "status": "success",
            "response_type": "text",
            "answer": (
                "Không tìm thấy thông tin về chủ đề này trong cơ sở dữ liệu."
                + MEDICAL_DISCLAIMER
            ),
            "data": None,
            "metadata": {
                "query_mode": query_mode,
                "execution_time_ms": round(execution_time_ms, 1),
                "source_count": 0,
                "engine": "lightrag",
            },
        }

    # Classify response type
    response_type = classify_response_type(question, raw_answer)

    # Build answer based on type
    answer = raw_answer.strip()
    data = None

    if response_type == "warning":
        answer = format_warning_answer(answer)
    elif response_type == "table":
        data = extract_table_data(answer)
    else:
        # Ensure disclaimer is appended for text responses
        if MEDICAL_DISCLAIMER.strip() not in answer:
            answer += MEDICAL_DISCLAIMER

    # For table type, also ensure disclaimer in the answer text
    if response_type == "table" and MEDICAL_DISCLAIMER.strip() not in answer:
        answer += MEDICAL_DISCLAIMER

    return {
        "status": "success",
        "response_type": response_type,
        "answer": answer,
        "data": data,
        "metadata": {
            "query_mode": query_mode,
            "execution_time_ms": round(execution_time_ms, 1),
            "source_count": len(data) if data else 1,
            "engine": "lightrag",
        },
    }


def format_error_response(
    error_code: str,
    error_message: str,
    user_message: str,
    execution_time_ms: float = 0,
) -> dict[str, Any]:
    """Format an error into the standard API error response.

    Args:
        error_code: Internal error code (e.g., 'MODEL_UNAVAILABLE').
        error_message: Technical error detail.
        user_message: User-friendly error message.
        execution_time_ms: Execution time before error.

    Returns:
        Dict conforming to the ErrorResponse schema.
    """
    return {
        "status": "error",
        "response_type": "text",
        "answer": user_message,
        "data": None,
        "metadata": {
            "error_code": error_code,
            "error_detail": error_message,
            "execution_time_ms": round(execution_time_ms, 1),
            "engine": "lightrag",
        },
    }
