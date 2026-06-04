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

# ── Emergency QUESTION patterns — only match first-person urgent phrasing ──
# IMPORTANT: Do NOT scan the ANSWER for these keywords.
# Medical answers naturally mention "đau ngực", "khó thở" etc. when describing
# disease symptoms — scanning answers causes massive false positives.
# Only the QUESTION is scanned, and only when it reads as a real emergency
# (first-person, present-tense, urgent) rather than an informational query.
EMERGENCY_QUESTION_KEYWORDS = [
    # First-person urgent: "tôi đang bị...", "tôi bị..."
    "tôi đang bị",
    "tôi bị ngất",
    "tôi bị co giật",
    "tôi bị ngộ độc",
    "tôi muốn tự tử",
    "tôi uống nhầm",
    "tôi uống quá liều",
    "giúp tôi với",
    "cứu tôi",
    # Third-person emergency
    "bị đột quỵ",
    "ngừng thở",
    "ngừng tim",
    "bất tỉnh",
    "hôn mê",
    "chảy máu không cầm",
    # English
    "help me",
    "i'm having a heart attack",
    "call ambulance",
    "overdose",
    "unconscious",
]


def classify_response_type(question: str, answer: str) -> str:
    """Classify the response type based on question intent.

    Emergency detection uses TWO layers, both on the QUESTION only:
      1. intent_classifier.detect_emergency_intent() — strong regex patterns
      2. EMERGENCY_QUESTION_KEYWORDS — first-person/urgent phrasing fallback

    The ANSWER is intentionally NOT scanned for emergency keywords because
    medical answers naturally describe dangerous symptoms (e.g. "đau ngực"
    appears in any cardiac disease answer) causing massive false positives.

    Args:
        question: The original user question.
        answer: The LightRAG synthesized answer.

    Returns:
        One of: 'warning', 'table', 'text'.
    """
    q_lower = question.lower()

    # 1. Priority: Detect emergency from QUESTION via intent_classifier (regex-based)
    if detect_emergency_intent(question):
        logger.info("Emergency intent detected via intent_classifier: '%s'", question[:60])
        return "warning"

    # 2. Fallback: scan QUESTION only for urgent first-person phrasing
    for keyword in EMERGENCY_QUESTION_KEYWORDS:
        if keyword in q_lower:
            logger.info("Emergency keyword in question: '%s'", keyword)
            return "warning"

    # 3. Detect list intent from question + verify answer has list structure
    if detect_list_intent(question):
        list_items = re.findall(r"^[\s]*[-•\d.]+\s+\S", answer, re.MULTILINE)
        if len(list_items) >= 2:
            return "table"

    # 4. Unconditionally check for list-like content in answer → table
    # (Block 3 only triggers when detect_list_intent matches; this catches all other cases.)
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


# ── Query types that require a medical disclaimer ─────────────────────────
# Disclaimer appears ONLY for queries where medical advice is actionable.
# Navigational/factual queries (department, linked_diseases, find_by_*,
# count) do NOT get a disclaimer.
_DISCLAIMER_MODES = {
    # Direct medical advice — user may act on this info
    "symptoms", "medicine", "treatment", "advice", "prevention", "profile",
}
_NO_DISCLAIMER_MODES = {
    # Purely informational / navigational — no disclaimer needed
    "count", "count_by_type", "disambiguation",
    "department",                           # just which clinic to go to
    "linked_diseases",                       # factual disease relationships
    "find_by_symptom", "find_by_medicine",  # reverse lookup, not advice
    "find_by_nutrition_avoid", "find_by_nutrition_eat",
    "find_by_prevention",
}

# Keywords in the QUESTION that signal medical-advice intent for LightRAG path.
# Only checked when query_mode is a LightRAG semantic mode (mix/naive/...).
_ADVICE_QUESTION_KEYWORDS = (
    "triệu chứng", "chẩn đoán", "điều trị", "thuốc", "chữa",
    "phòng ngừa", "phòng tránh", "nên ăn", "không nên ăn", "kiêng",
    "lời khuyên", "tư vấn", "nguy hiểm", "biến chứng",
    "symptoms", "diagnos", "treat", "medicine", "drug",
)


def _is_medical_advice_question(question: str) -> bool:
    """Return True if the question asks for medical advice / diagnosis / treatment.

    Used to conditionally suppress the disclaimer on LightRAG semantic paths
    when the question is clearly navigational (e.g. 'bệnh nào phổ biến ở trẻ em').
    """
    q_lower = question.lower()
    return any(kw in q_lower for kw in _ADVICE_QUESTION_KEYWORDS)


def _needs_disclaimer(query_mode: str, question: str = "") -> bool:
    """Return True when the response needs a MEDICAL_DISCLAIMER appended.

    Rules:
    - LightRAG / mix / naive / local / global paths  → only when question has
      medical-advice keywords (symptoms, treatment, drugs, diet advice...)
    - Cypher template with medical query type         → show
    - Cypher navigational types (department, find_by_*, linked_*)  → suppress
    - Cypher count / disambiguation                   → suppress
    - LLM-generated Cypher (type=None)                → check question

    Args:
        query_mode: The query_mode string from metadata
                    (e.g. 'cypher:template:symptoms', 'mix', 'naive').
        question:   The original user question (used for LightRAG path).
    Returns:
        True if disclaimer should be appended.
    """
    # LightRAG semantic paths — only show when medical-advice question
    if query_mode in ("mix", "naive", "local", "global", "hybrid"):
        return _is_medical_advice_question(question)
    # cypher:template:<type>  or  cypher:llm:<type>  or  cypher:disambiguation
    parts = query_mode.split(":")
    if len(parts) >= 3:
        query_type = parts[2]
        if query_type in _NO_DISCLAIMER_MODES:
            return False
        if query_type in _DISCLAIMER_MODES:
            return True
        # LLM-generated Cypher (type=None or unknown) → check question
        return _is_medical_advice_question(question)
    # cypher:disambiguation  (2-part)
    if "disambiguation" in query_mode:
        return False
    # Fallback: check question
    return _is_medical_advice_question(question)


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
            "answer": "Không tìm thấy thông tin về chủ đề này trong cơ sở dữ liệu.",
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
    show_disclaimer = _needs_disclaimer(query_mode, question)

    # Build answer based on type
    answer = raw_answer.strip()
    data = None

    if response_type == "warning":
        # Warning already includes emergency CTA — no additional disclaimer needed
        answer = format_warning_answer(answer)
    elif response_type == "table":
        data = extract_table_data(answer)
        if show_disclaimer and MEDICAL_DISCLAIMER.strip() not in answer:
            answer += MEDICAL_DISCLAIMER
    else:
        # text
        if show_disclaimer and MEDICAL_DISCLAIMER.strip() not in answer:
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
