"""Safety payload policy — S2-ARCH-03.

Pure functions to classify a question and produce a ``SafetyPayload``.

Classification levels
---------------------
``normal``      General medical information query; standard disclaimer.
``caution``     Medical question that may affect health decisions; add disclaimer and advisory.
``emergency``   Immediate life-threatening symptoms; require emergency notice.

Design decisions
----------------
- Classification is rule-based for Sprint 2 (no ML classifier needed).
- Emergency detection re-uses ``ai_engine.services.intent_classifier.detect_emergency_intent()``
  which already has robust regex patterns.  This avoids duplicating patterns.
- CAUTION keywords cover medical queries that are not emergencies but warrant
  stronger advisory messaging.
- Safety logic is intentionally located here in the service/helper layer and
  MUST NOT be duplicated in the router.
- The medical disclaimer is always present regardless of level.
"""

from __future__ import annotations

import logging
import re

from app.models.contracts import SafetyPayload

logger = logging.getLogger(__name__)

# ── Disclaimer text ───────────────────────────────────────────────────────
MEDICAL_DISCLAIMER_VI = (
    "Thông tin chỉ mang tính chất tham khảo. "
    "Vui lòng tham khảo ý kiến bác sĩ chuyên khoa để có chẩn đoán chính xác."
)

EMERGENCY_DISCLAIMER_VI = (
    "⚠️ ĐÂY LÀ TÌNH HUỐNG CẤP CỨU. "
    "Vui lòng gọi 115 hoặc đến cơ sở y tế gần nhất NGAY LẬP TỨC. "
    "Thông tin này KHÔNG thay thế chẩn đoán và can thiệp y tế khẩn cấp."
)

CAUTION_DISCLAIMER_VI = (
    "Thông tin chỉ mang tính chất tham khảo và không thay thế lời khuyên y tế chuyên nghiệp. "
    "Nếu bạn có triệu chứng đáng lo ngại, hãy tham khảo ý kiến bác sĩ."
)

# ── Caution keyword patterns (Vietnamese + English) ───────────────────────
# Triggered when a question is medical in nature but NOT an emergency.
# These represent queries where the user might act on the answer directly.
_CAUTION_PATTERNS_VI = [
    r"thuốc.*có thể.*uống",
    r"tự.*điều trị",
    r"uống thuốc.*không",
    r"có nên.*dùng thuốc",
    r"liều lượng.*thuốc",
    r"tác dụng phụ",
    r"tương tác thuốc",
    r"dị ứng.*thuốc",
    r"con nít.*thuốc",
    r"trẻ em.*thuốc",
    r"thai phụ.*thuốc",
    r"phụ nữ có thai.*thuốc",
    r"ngừng thuốc",
    r"bỏ thuốc",
    r"triệu chứng.*nghiêm trọng",
    r"biến chứng.*nguy hiểm",
    r"lây.*như thế nào",
    r"có lây không",
    r"truyền nhiễm",
]

_CAUTION_PATTERNS_EN = [
    r"can i take.*medicine",
    r"self.?medic",
    r"dosage",
    r"side effect",
    r"drug interaction",
    r"allergic.*medicine",
    r"medicine.*children",
    r"medicine.*pregnant",
    r"stop.*medication",
    r"serious symptom",
    r"dangerous complication",
    r"contagious",
    r"how does it spread",
]

_CAUTION_COMPILED = [
    re.compile(p, re.IGNORECASE)
    for p in _CAUTION_PATTERNS_VI + _CAUTION_PATTERNS_EN
]


def _detect_caution_intent(question: str) -> bool:
    """Return True when the question warrants caution-level safety messaging."""
    for pattern in _CAUTION_COMPILED:
        if pattern.search(question):
            logger.debug("safety_policy: caution pattern matched '%s'", pattern.pattern)
            return True
    return False


def classify_safety(question: str) -> SafetyPayload:
    """Classify a user question and return the appropriate ``SafetyPayload``.

    Evaluation order (first match wins):
    1. Emergency: uses ``detect_emergency_intent()`` from ai_engine.
    2. Caution: matches one of ``_CAUTION_COMPILED`` patterns.
    3. Normal: everything else.

    Args:
        question: The user's natural language question.

    Returns:
        A ``SafetyPayload`` with ``level``, ``requires_emergency_notice``,
        and ``disclaimer`` set appropriately.
    """
    try:
        from ai_engine.services.intent_classifier import detect_emergency_intent

        is_emergency = detect_emergency_intent(question)
    except Exception:
        logger.warning("safety_policy: could not import detect_emergency_intent, using fallback")
        is_emergency = False

    if is_emergency:
        logger.info("safety_policy: EMERGENCY detected for question: '%s'", question[:80])
        return SafetyPayload(
            level="emergency",
            requires_emergency_notice=True,
            disclaimer=EMERGENCY_DISCLAIMER_VI,
        )

    if _detect_caution_intent(question):
        logger.info("safety_policy: CAUTION detected for question: '%s'", question[:80])
        return SafetyPayload(
            level="caution",
            requires_emergency_notice=False,
            disclaimer=CAUTION_DISCLAIMER_VI,
        )

    return SafetyPayload(
        level="normal",
        requires_emergency_notice=False,
        disclaimer=MEDICAL_DISCLAIMER_VI,
    )


def safety_from_response_type(response_type: str, question: str) -> SafetyPayload:
    """Derive safety payload from the pipeline's ``response_type`` classification.

    The pipeline's ``response_type == "warning"`` already signals emergency intent
    (see ``response_formatter.classify_response_type``). This helper merges that
    signal with the direct question classifier so neither path is missed.

    Args:
        response_type: The ``response_type`` from the pipeline (``warning``, ``text``, ``table``).
        question: The original user question (used as fallback classifier input).

    Returns:
        A ``SafetyPayload``.
    """
    if response_type == "warning":
        # Pipeline already classified this as emergency/warning — trust it
        return SafetyPayload(
            level="emergency",
            requires_emergency_notice=True,
            disclaimer=EMERGENCY_DISCLAIMER_VI,
        )
    # Fall through to full question classification
    return classify_safety(question)
