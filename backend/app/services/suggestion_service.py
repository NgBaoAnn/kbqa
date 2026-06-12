"""Follow-up question generation for chat answers.

This service is intentionally deterministic and side-effect-free. It creates a
small set of Vietnamese follow-up prompts from the current question, answer and
sources without calling the AI engine.
"""

from __future__ import annotations

import re
from typing import Iterable

from app.models.contracts import ChatSource, SafetyPayload

_MAX_SUGGESTIONS = 3
_VI_STOPWORDS = {
    "benh",
    "bệnh",
    "la",
    "là",
    "gi",
    "gì",
    "co",
    "có",
    "nhung",
    "những",
    "nao",
    "nào",
    "trieu",
    "triệu",
    "chung",
    "chứng",
    "dieu",
    "điều",
    "tri",
    "trị",
    "thuoc",
    "thuốc",
    "toi",
    "tôi",
    "hoi",
    "hỏi",
    "ve",
    "về",
}
_DANGEROUS_TERMS = (
    "cấp cứu",
    "tự tử",
    "quá liều",
    "ngộ độc",
    "đau ngực dữ dội",
    "khó thở nặng",
)


def generate_suggestions(
    *,
    question: str,
    answer: str,
    sources: Iterable[ChatSource],
    safety: SafetyPayload,
    status: str = "success",
    response_type: str = "text",
) -> list[str]:
    """Return up to three concise Vietnamese follow-up questions."""
    if status != "success" or response_type in {"warning", "disambiguation"}:
        return []
    if safety.level == "emergency" or safety.requires_emergency_notice:
        return []
    if not answer.strip():
        return []

    topic = _topic_from_sources(sources) or _topic_from_question(question)
    topic_text = f" về {topic}" if topic else ""

    candidates = [
        f"Dấu hiệu cần đi khám{topic_text} là gì?",
        f"Cách phòng ngừa{topic_text} như thế nào?",
        f"Cần lưu ý gì khi chăm sóc{topic_text}?",
        f"Khi nào nên hỏi bác sĩ{topic_text}?",
    ]
    return _dedupe_safe_questions(candidates)


def normalize_suggestions(questions: Iterable[str] | None) -> list[str]:
    """Clamp externally supplied suggestions to the public contract."""
    if not questions:
        return []
    return _dedupe_safe_questions(str(q) for q in questions)


def _topic_from_sources(sources: Iterable[ChatSource]) -> str | None:
    for source in sources:
        title = source.title.strip()
        if title and title.lower() not in {"aegishealth hybrid graphrag", "neo4j vietmedkg"}:
            return _shorten_topic(title)
    return None


def _topic_from_question(question: str) -> str | None:
    words = re.findall(r"[\wÀ-ỹ]+", question.lower(), flags=re.UNICODE)
    keywords = [w for w in words if len(w) > 2 and w not in _VI_STOPWORDS]
    if not keywords:
        return None
    return _shorten_topic(" ".join(keywords[:4]))


def _shorten_topic(topic: str) -> str:
    cleaned = re.sub(r"\s+", " ", topic).strip(" .,:;!?")
    return " ".join(cleaned.split()[:6])


def _dedupe_safe_questions(candidates: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        question = _clean_question(candidate)
        key = question.lower()
        if not question or key in seen or _contains_dangerous_term(key):
            continue
        seen.add(key)
        result.append(question)
        if len(result) >= _MAX_SUGGESTIONS:
            break
    return result


def _clean_question(question: str) -> str:
    cleaned = re.sub(r"\s+", " ", question).strip()
    if len(cleaned) > 120:
        cleaned = cleaned[:117].rstrip() + "..."
    if cleaned and not cleaned.endswith("?"):
        cleaned += "?"
    return cleaned


def _contains_dangerous_term(text: str) -> bool:
    return any(term in text for term in _DANGEROUS_TERMS)
