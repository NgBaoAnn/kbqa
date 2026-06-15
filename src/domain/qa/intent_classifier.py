"""QA Domain — Intent Classifier (Regex-based).

Pure functions for classifying Vietnamese medical questions into
(query_type, entity) pairs using regex patterns.

This module contains ONLY the regex classification logic extracted from
``ai_engine/services/query_router.py``.  The LLM-based classification
lives in the adapter layer (it requires infrastructure).

All functions are pure — no I/O, no framework dependencies.
"""

from __future__ import annotations

import re

from domain.qa.value_objects import EntityName, IntentClassification, QueryType


# ── Constants ─────────────────────────────────────────────────────────────

QUESTION_WORDS: frozenset[str] = frozenset({
    "gì", "nào", "sao", "thế nào", "như thế nào",
    "bao nhiêu", "khi nào", "ở đâu",
    "what", "which", "how", "when", "where",
})

VALID_QUERY_TYPES: frozenset[str] = frozenset({
    # Forward (entity = disease name)
    "symptoms", "medicine", "treatment", "advice",
    "prevention", "department", "profile",
    "linked_diseases",
    "cause", "check_method", "susceptible_population",
    # Reverse (entity = constraint keyword, not a disease name)
    "find_by_symptom", "find_by_medicine",
    "find_by_nutrition_avoid", "find_by_nutrition_eat",
    "find_by_prevention", "find_by_check_method",
    # Chain (2-hop)
    "chain_linked_avoid", "chain_linked_eat",
    # Sentinel
    "unknown",
})

FIND_BY_TYPES: frozenset[str] = frozenset({
    "find_by_symptom", "find_by_medicine",
    "find_by_nutrition_avoid", "find_by_nutrition_eat",
    "find_by_prevention", "find_by_check_method",
})


# ── Entity cleaning ──────────────────────────────────────────────────────

def clean_entity(raw: str) -> str | None:
    """Normalize an extracted entity name; returns None for question words.

    This function strips Vietnamese question particles, prefix words
    like "bệnh"/"bị", and trailing noise.
    """
    if not raw:
        return None
    name = raw.strip().rstrip("?.!")
    name = re.sub(r"^(?:bệnh|bị)\s+", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+không$", "", name, flags=re.IGNORECASE)
    # Strip trailing question phrases
    name = re.sub(
        r"\s+(?:như\s+thế\s+nào|thế\s+nào|là\s+gì|gồm\s+gì|thì\s+sao|có|không)\s*$",
        "", name, flags=re.IGNORECASE,
    )
    name = name.strip("[]").strip()
    if not name or len(name) < 2:
        return None
    # Reject bare question words
    if name.lower() in QUESTION_WORDS:
        return None
    return name


# ── Regex classification ─────────────────────────────────────────────────

def classify_cypher_intent(question: str) -> tuple[str | None, str | None]:
    """Extract (query_type, entity) from a question using regex patterns.

    Returns (query_type, entity) or (None, None) when no pattern matches.
    (query_type, None) means type detected but entity invalid → LLM fallback.
    """
    q = question.strip()

    # Multi-constraint bracket list → too complex for regex
    if re.search(r"\[[^\]]+,[^\]]+,[^\]]+", q):
        return None, None

    # ── Reverse: find_by_symptom (checked BEFORE forward symptom patterns) ──
    for pattern in [
        r"bệnh\s+(?:lý\s+)?(?:nào|gì)\s+(?:có|gây|biểu\s+hiện\s+bằng)\s+(?:triệu\s*chứng|biểu\s+hiện|dấu\s+hiệu)\s+(.+?)(?:\?|$)",
        r"(?:triệu\s*chứng|biểu\s+hiện|dấu\s+hiệu)\s+(.+?)\s+(?:là|thuộc)\s+bệnh\s+(?:gì|nào)",
        r"which\s+diseases?\s+(?:has|have|cause[sd]?)\s+(.+?)\s+(?:as\s+)?(?:symptom|sign)",
        r"bao\s+nhiêu\s+bệnh\s+(?:lý\s+)?(?:có|gây)\s+(?:triệu\s*chứng|biểu\s+hiện|dấu\s+hiệu)\s+(.+?)(?:\?|$)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "find_by_symptom", clean_entity(m.group(1))

    # ── Symptoms ──
    for pattern in [
        r"(.+?)\s+có\s+(?:những\s+)?triệu\s*chứng\s+(?:gì|nào)",
        r"triệu chứng\s+(?:của\s+)?(?:bệnh\s+)?(.+?)(?:\s+là|\s+gồm|\?|$)",
        r"biểu hiện\s+(?:của\s+)?(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"dấu hiệu\s+(?:của\s+)?(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"symptoms?\s+of\s+(.+?)(?:\?|$)",
        r"signs?\s+of\s+(.+?)(?:\?|$)",
        r"bao\s+nhiêu\s+triệu\s*chứng\s+(?:của\s+)?(?:bệnh\s+)?(.+?)(?:\?|$)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "symptoms", clean_entity(m.group(1))

    # ── Medicine ──
    for pattern in [
        r"thuốc\s+(?:điều\s*trị|chữa|trị)\s+(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"(.+?)\s+(?:dùng|uống|điều\s*trị\s+bằng)\s+thuốc\s+(?:gì|nào)",
        r"(?:what|which)\s+(?:drugs?|medicines?)\s+(?:treat|cure|for)\s+(.+?)(?:\?|$)",
        r"(?:medication|drugs?)\s+for\s+(.+?)(?:\?|$)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "medicine", clean_entity(m.group(1))

    # ── Treatment ──
    for pattern in [
        r"(?:bệnh\s+)?(.+?)\s+điều\s*trị\s+(?:bằng\s+cách\s+)?(?:nào|như\s+thế\s+nào)",
        r"cách\s+(?:điều\s*trị|chữa)\s+(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"phương\s*pháp\s+(?:điều\s*trị|chữa)\s+(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"(?:how|what)\s+(?:to\s+)?treat\s+(.+?)(?:\?|$)",
        r"(?:treatment|cure)\s+for\s+(.+?)(?:\?|$)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "treatment", clean_entity(m.group(1))

    # ── Department ──
    for pattern in [
        r"khoa\s+(?:điều\s*trị|khám)\s+(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"(?:bệnh\s+)?(.+?)\s+(?:khám|điều\s*trị)\s+(?:ở\s+)?khoa\s+(?:gì|nào)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "department", clean_entity(m.group(1))

    # ── Advice / nutrition ──
    for pattern in [
        r"(?:bị\s+)?(.+?)\s+(?:nên|không\s+nên)\s+ăn\s+(?:gì|những\s+gì)",
        r"chế\s+độ\s+ăn\s+(?:cho\s+)?(?:bị\s+)?(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"dinh\s*dưỡng\s+(?:cho\s+)?(?:bị\s+)?(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"(?:bệnh\s+)?(.+?)\s+ăn\s+(?:gì|những\s+gì)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "advice", clean_entity(m.group(1))

    # ── Prevention ──
    for pattern in [
        r"(?:cách\s+)?phòng\s+(?:tránh|ngừa)\s+(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"(?:bệnh\s+)?(.+?)\s+phòng\s+(?:tránh|ngừa)\s+(?:như\s+thế\s+nào|thế\s+nào)",
        r"(?:làm\s+thế\s+nào\s+)?để\s+phòng\s+(?:bệnh\s+)?(.+?)(?:\?|$)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "prevention", clean_entity(m.group(1))

    # ── Cause ──
    for pattern in [
        r"nguyên\s+nhân\s+(?:gây\s+)?(?:ra\s+)?(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"(?:bệnh\s+)?(.+?)\s+(?:do\s+)?nguyên\s+nhân\s+(?:gì|nào)",
        r"(?:tại\s+sao|vì\s+sao)\s+(?:bị|mắc)\s+(?:bệnh\s+)?(.+?)(?:\?|$)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "cause", clean_entity(m.group(1))

    # ── Check method ──
    for pattern in [
        r"(?:xét\s*nghiệm|kiểm\s*tra|chẩn\s*đoán)\s+(?:bệnh\s+)?(.+?)(?:\s+bằng\s+cách\s+nào|\?|$)",
        r"(?:bệnh\s+)?(.+?)\s+(?:cần\s+)?(?:xét\s*nghiệm|kiểm\s*tra|chẩn\s*đoán)\s+(?:gì|nào|bằng\s+cách\s+nào)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "check_method", clean_entity(m.group(1))

    # ── Susceptible population ──
    for pattern in [
        r"(?:ai|đối\s+tượng\s+nào|người\s+nào)\s+(?:dễ\s+)?(?:mắc|bị)\s+(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"(?:bệnh\s+)?(.+?)\s+(?:thường\s+gặp|phổ\s+biến)\s+(?:ở|với)\s+(?:ai|đối\s+tượng\s+nào)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "susceptible_population", clean_entity(m.group(1))

    # ── Reverse: find_by_medicine ──
    for pattern in [
        r"thuốc\s+(.+?)\s+(?:chữa|điều\s*trị|dùng cho|trị)\s+bệnh\s+(?:gì|nào)",
        r"(.+?)\s+(?:chữa|điều\s*trị|trị)\s+(?:được\s+)?bệnh\s+(?:gì|nào)\s*(?:\?|$)",
        r"(.+?)\s+dùng\s+cho\s+bệnh\s+(?:gì|nào)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "find_by_medicine", clean_entity(m.group(1))

    # ── Reverse: find_by_nutrition_avoid ──
    for pattern in [
        r"(?:không\s+(?:nên\s+)?ăn|kiêng|tránh\s+ăn)\s+(.+?)\s+(?:tốt\s+cho|là|giúp|chữa|hỗ\s*trợ)\s+bệnh\s+(?:gì|nào)",
        r"bệnh\s+(?:lý\s+)?(?:nào|gì)\s+(?:nên\s+)?(?:kiêng|tránh|không\s+nên\s+ăn)\s+(.+?)(?:\?|$)",
        r"(.+?)\s+(?:là thực phẩm|không nên ăn khi)\s+bị\s+bệnh\s+(?:gì|nào)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "find_by_nutrition_avoid", clean_entity(m.group(1))

    # ── Reverse: find_by_nutrition_eat ──
    for pattern in [
        r"(?:nên\s+)?ăn\s+(.+?)\s+(?:tốt\s+cho|giúp|có\s+tác\s+dụng\s+(?:với|cho)|hỗ\s*trợ)\s+bệnh\s+(?:gì|nào)",
        r"bệnh\s+(?:lý\s+)?(?:nào|gì)\s+(?:nên|cần)\s+ăn\s+(.+?)(?:\?|$)",
        r"(.+?)\s+có\s+tác\s+dụng\s+(?:với|cho|hỗ trợ)\s+bệnh\s+(?:gì|nào)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "find_by_nutrition_eat", clean_entity(m.group(1))

    # ── Reverse: find_by_prevention ──
    for pattern in [
        r"(.+?)\s+(?:phòng|giúp\s+phòng|ngăn\s+ngừa)\s+(?:được\s+)?bệnh\s+(?:gì|nào)",
        r"bệnh\s+(?:lý\s+)?(?:nào|gì)\s+(?:được\s+)?phòng\s+bằng\s+(.+?)(?:\?|$)",
        r"(.+?)\s+(?:phòng ngừa|ngừa)\s+bệnh\s+(?:gì|nào)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "find_by_prevention", clean_entity(m.group(1))

    # ── Reverse: find_by_check_method ──
    for pattern in [
        r"(?:xét\s*nghiệm|kiểm\s*tra|chẩn\s*đoán)\s+(.+?)\s+dùng\s+để\s+(?:chẩn\s*đoán|phát\s+hiện)\s+bệnh\s+(?:gì|nào)",
        r"(.+?)\s+là\s+xét\s*nghiệm\s+của\s+bệnh\s+(?:gì|nào)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "find_by_check_method", clean_entity(m.group(1))

    # ── Chain: linked → avoid ──
    for pattern in [
        r"(?:thực\s*phẩm|đồ\s+ăn).*?(?:tránh|kiêng|không\s+nên\s+ăn).*?(?:bệnh.*?(?:liên\s+quan|đi\s+kèm|kèm\s+theo).*?)(?:\[)?(.+?)(?:\]|\?|$)",
        r"(?:tránh|kiêng).*?(?:không\s+(?:mắc|gặp)).*?(?:bệnh.*?(?:liên\s+quan|đi\s+kèm)).*?(?:\[)?(.+?)(?:\]|\?|$)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "chain_linked_avoid", clean_entity(m.group(1))

    # ── Chain: linked → eat ──
    for pattern in [
        r"(?:thực\s*phẩm|đồ\s+ăn).*?(?:nên\s+ăn|ăn\s+gì).*?(?:bệnh.*?(?:liên\s+quan|đi\s+kèm|kèm\s+theo).*?)(?:\[)?(.+?)(?:\]|\?|$)",
        r"(?:để\s+phòng\s+tránh).*?(?:bệnh.*?(?:liên\s+quan|đi\s+kèm)).*?(?:nên\s+ăn|ăn\s+gì).*?(?:\[)?(.+?)(?:\]|\?|$)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "chain_linked_eat", clean_entity(m.group(1))

    # ── Linked diseases ──
    for pattern in [
        r"(?:bệnh\s+)?(.+?)\s+có\s+liên\s+quan\s+(?:đến|với)\s+(?:bệnh|những\s+bệnh)\s+(?:gì|nào)",
        r"(?:bệnh\s+)?(.+?)\s+liên\s+quan\s+đến\s+(?:những\s+)?(?:bệnh|bệnh\s+lý)\s+(?:gì|nào)",
        r"(?:bệnh\s+)?(.+?)\s+đi\s+kèm\s+(?:với\s+)?(?:bệnh|những\s+bệnh)\s+(?:gì|nào)",
        r"bệnh\s+kèm\s+theo\s+(?:của\s+)?(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"comorbidities?\s+of\s+(.+?)(?:\?|$)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "linked_diseases", clean_entity(m.group(1))

    # ── Profile / general info ──
    for pattern in [
        r"(?:toàn\s+bộ\s+)?thông\s+tin\s+(?:về\s+)?(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"(?:cho\s+tôi\s+biết|nói\s+cho\s+tôi)\s+(?:về\s+)?(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"(.+?)\s+là\s+(?:bệnh\s+)?gì",
        r"giới\s*thiệu\s+(?:về\s+)?(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"what\s+is\s+(.+?)(?:\?|$)",
        r"tell\s+me\s+about\s+(.+?)(?:\?|$)",
        r"information\s+about\s+(.+?)(?:\?|$)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "profile", clean_entity(m.group(1))

    return None, None


# ── Emergency & list intent detection ─────────────────────────────────────

EMERGENCY_PATTERNS_VI = [
    r"đau ngực.*dữ dội",
    r"khó thở.*nghiêm trọng",
    r"co giật",
    r"bất tỉnh",
    r"chảy máu.*không.*cầm",
    r"ngừng thở",
    r"sốt cao.*trên.*39",
    r"đau đầu.*dữ dội.*đột ngột",
    r"liệt.*nửa.*người",
    r"ngộ độc",
]

EMERGENCY_PATTERNS_EN = [
    r"severe chest pain",
    r"difficulty breathing",
    r"seizure",
    r"unconscious",
    r"heavy bleeding",
    r"cardiac arrest",
    r"high fever.*above.*39",
    r"sudden severe headache",
    r"paralysis",
    r"poisoning",
]

LIST_INTENT_PATTERNS = [
    r"liệt kê",
    r"cho tôi danh sách",
    r"những.*gì",
    r"có.*nào",
    r"tất cả",
    r"bao nhiêu",
    r"list",
    r"what are",
    r"how many",
]


def detect_emergency_intent(question: str) -> bool:
    """Detect if a question describes an emergency medical situation."""
    question_lower = question.lower()
    for pattern in EMERGENCY_PATTERNS_VI + EMERGENCY_PATTERNS_EN:
        if re.search(pattern, question_lower):
            return True
    return False


def detect_list_intent(question: str) -> bool:
    """Detect if a question expects a list/table response."""
    question_lower = question.lower()
    for pattern in LIST_INTENT_PATTERNS:
        if re.search(pattern, question_lower):
            return True
    return False


# ── High-level classification function ────────────────────────────────────

def classify_intent_regex(question: str) -> IntentClassification:
    """Classify a question using regex patterns only.

    This is the pure-function entry point for intent classification.
    LLM-based classification is handled at the adapter/use-case level.

    Returns:
        An IntentClassification with method="regex".
    """
    query_type_str, entity_str = classify_cypher_intent(question)

    if query_type_str is None:
        return IntentClassification(
            query_type=QueryType.GENERAL,
            entity=None,
            method="regex",
            confidence=0.0,
        )

    query_type = QueryType.from_string(query_type_str)
    entity = EntityName(entity_str) if entity_str else None

    return IntentClassification(
        query_type=query_type,
        entity=entity,
        method="regex",
        confidence=1.0,
    )
