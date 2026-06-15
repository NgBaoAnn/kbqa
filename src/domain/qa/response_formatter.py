"""QA Domain — Response Formatter.

Pure functions to classify response types (text/table/warning) and
format answers.  No infrastructure dependencies.

Extracted from ai_engine/utils/response_formatter.py.
"""

from __future__ import annotations

import re
from typing import Any

from domain.qa.intent_classifier import detect_emergency_intent, detect_list_intent
from domain.qa.safety_policy import EMERGENCY_QUESTION_KEYWORDS, MEDICAL_DISCLAIMER_MD

# ── Query modes that get a medical disclaimer ─────────────────────────────

_DISCLAIMER_MODES = {
    "symptoms", "medicine", "treatment", "advice", "prevention", "profile",
}

_NO_DISCLAIMER_MODES = {
    "count", "count_by_type", "disambiguation",
    "department",
    "linked_diseases",
    "find_by_symptom", "find_by_medicine",
    "find_by_nutrition_avoid", "find_by_nutrition_eat",
    "find_by_prevention",
}

_ADVICE_QUESTION_KEYWORDS = (
    "triệu chứng", "chẩn đoán", "điều trị", "thuốc", "chữa",
    "phòng ngừa", "phòng tránh", "nên ăn", "không nên ăn", "kiêng",
    "lời khuyên", "tư vấn", "nguy hiểm", "biến chứng",
    "symptoms", "diagnos", "treat", "medicine", "drug",
)


# ── Response type classification ──────────────────────────────────────────

def classify_response_type(question: str, answer: str) -> str:
    """Classify the response type based on question intent.

    Returns one of: 'warning', 'table', 'text'.
    """
    q_lower = question.lower()

    # 1. Emergency via regex patterns
    if detect_emergency_intent(question):
        return "warning"

    # 2. Emergency via first-person keyword scan
    for keyword in EMERGENCY_QUESTION_KEYWORDS:
        if keyword in q_lower:
            return "warning"

    # 3. List intent from question → verify answer has list structure
    if detect_list_intent(question):
        list_items = re.findall(r"^[\s]*[-•\d.]+\s+\S", answer, re.MULTILINE)
        if len(list_items) >= 2:
            return "table"

    # 4. Unconditional list content check in answer
    list_items = re.findall(r"^[\s]*[-•\d.]+\s+\S", answer, re.MULTILINE)
    if len(list_items) >= 2:
        return "table"

    # 5. Comma-separated items after a colon
    colon_lists = re.findall(r":\s*(.+?)(?:\.|$)", answer)
    for item_str in colon_lists:
        items = [x.strip() for x in item_str.split(",") if x.strip()]
        if len(items) >= 3:
            return "table"

    return "text"


def extract_table_data(answer: str) -> list[dict[str, str]] | None:
    """Try to extract structured table data from a text answer."""
    list_items = re.findall(r"^[\s]*[-•]\s*(.+)$", answer, re.MULTILINE)
    if len(list_items) >= 2:
        return [{"item": item.strip()} for item in list_items]

    numbered_items = re.findall(r"^[\s]*\d+[.)]\s*(.+)$", answer, re.MULTILINE)
    if len(numbered_items) >= 2:
        return [{"item": item.strip()} for item in numbered_items]

    return None


def format_warning_answer(answer: str) -> str:
    """Enhance answer with warning formatting."""
    warning_prefix = "⚠️ CẢNH BÁO Y TẾ: "
    emergency_cta = (
        "\n\n🏥 Nếu bạn đang gặp triệu chứng nguy hiểm, "
        "VUI LÒNG LIÊN HỆ BÁC SĨ HOẶC GỌI CẤP CỨU NGAY LẬP TỨC."
        "\n\nHệ thống này KHÔNG thay thế chẩn đoán y tế chuyên nghiệp."
    )
    if not answer.startswith("⚠️"):
        answer = warning_prefix + answer
    return answer + emergency_cta


# ── Disclaimer logic ─────────────────────────────────────────────────────

def is_medical_advice_question(question: str) -> bool:
    """Return True if the question asks for medical advice/diagnosis/treatment."""
    q_lower = question.lower()
    return any(kw in q_lower for kw in _ADVICE_QUESTION_KEYWORDS)


def needs_disclaimer(query_mode: str, question: str = "") -> bool:
    """Return True when the response needs a MEDICAL_DISCLAIMER appended.

    Rules:
    - LightRAG/semantic paths → only when question has medical-advice keywords
    - Cypher template with medical query type → show
    - Cypher navigational types → suppress
    - LLM-generated Cypher (type=None) → check question
    """
    if query_mode in ("mix", "naive", "local", "global", "hybrid"):
        return is_medical_advice_question(question)

    parts = query_mode.split(":")
    if len(parts) >= 3:
        query_type = parts[2]
        if query_type in _NO_DISCLAIMER_MODES:
            return False
        if query_type in _DISCLAIMER_MODES:
            return True
        return is_medical_advice_question(question)

    if "disambiguation" in query_mode:
        return False

    return is_medical_advice_question(question)


def format_lightrag_response(
    raw_answer: str,
    question: str,
    query_mode: str,
    execution_time_ms: float,
) -> dict[str, Any]:
    """Format a LightRAG query result into the standard response dict.

    Returns:
        Dict with: status, response_type, answer, data, metadata.
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

    response_type = classify_response_type(question, raw_answer)
    show_disclaimer = needs_disclaimer(query_mode, question)

    answer = raw_answer.strip()
    data = None

    if response_type == "warning":
        answer = format_warning_answer(answer)
    elif response_type == "table":
        data = extract_table_data(answer)
        if show_disclaimer and MEDICAL_DISCLAIMER_MD.strip() not in answer:
            answer += MEDICAL_DISCLAIMER_MD
    else:
        if show_disclaimer and MEDICAL_DISCLAIMER_MD.strip() not in answer:
            answer += MEDICAL_DISCLAIMER_MD

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
