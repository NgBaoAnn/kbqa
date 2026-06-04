"""Intent Classifier — Phân loại response_type (table/text/warning).

This module provides post-processing classification for LightRAG responses. 
The primary classification logic is in response_formatter.py. This module 
adds additional domain-specific intent detection for the medical QA context.
"""

import logging
import re

logger = logging.getLogger(__name__)

# ── Emergency symptom patterns ────────────────────────────────────────────
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

# ── Question intent patterns ─────────────────────────────────────────────
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
    """Detect if a question describes an emergency medical situation.

    Args:
        question: The user's question.

    Returns:
        True if emergency symptoms are detected.
    """
    question_lower = question.lower()

    for pattern in EMERGENCY_PATTERNS_VI + EMERGENCY_PATTERNS_EN:
        if re.search(pattern, question_lower):
            logger.info("Emergency intent detected: pattern='%s'", pattern)
            return True

    return False


def detect_list_intent(question: str) -> bool:
    """Detect if a question expects a list/table response.

    Args:
        question: The user's question.

    Returns:
        True if the question likely expects a list response.
    """
    question_lower = question.lower()

    for pattern in LIST_INTENT_PATTERNS:
        if re.search(pattern, question_lower):
            return True

    return False
