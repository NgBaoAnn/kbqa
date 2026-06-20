"""QA Domain — deterministic follow-up question suggestions."""

from __future__ import annotations

import re
from collections.abc import Iterable

_MAX_SUGGESTIONS = 3
_VI_STOPWORDS = {
    "benh", "bệnh", "la", "là", "gi", "gì", "co", "có",
    "nhung", "những", "nao", "nào", "trieu", "triệu", "chung", "chứng",
    "dieu", "điều", "tri", "trị", "thuoc", "thuốc", "toi", "tôi",
    "hoi", "hỏi", "ve", "về",
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
    sources: Iterable[dict],
    safety: dict,
    status: str = "success",
    response_type: str = "text",
) -> list[str]:
    """Return up to three concise Vietnamese follow-up questions."""
    if status != "success" or response_type in {"warning", "disambiguation"}:
        return []
    if safety.get("level") == "emergency" or safety.get("requires_emergency_notice"):
        return []
    if not answer.strip():
        return []

    topic = _topic_from_sources(sources) or _topic_from_question(question)
    topic_text = f" về {topic}" if topic else ""
    return _dedupe_safe_questions([
        f"Dấu hiệu cần đi khám{topic_text} là gì?",
        f"Cách phòng ngừa{topic_text} như thế nào?",
        f"Cần lưu ý gì khi chăm sóc{topic_text}?",
        f"Khi nào nên hỏi bác sĩ{topic_text}?",
    ])


def _topic_from_sources(sources: Iterable[dict]) -> str | None:
    for source in sources:
        title = str(source.get("title") or "").strip()
        if title and title.lower() not in {"aegishealth hybrid graphrag", "neo4j vietmedkg"}:
            return _shorten_topic(title)
    return None


def _topic_from_question(question: str) -> str | None:
    words = re.findall(r"[\wÀ-ỹ]+", question.lower(), flags=re.UNICODE)
    keywords = [word for word in words if len(word) > 2 and word not in _VI_STOPWORDS]
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
        if not question or key in seen or any(term in key for term in _DANGEROUS_TERMS):
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
