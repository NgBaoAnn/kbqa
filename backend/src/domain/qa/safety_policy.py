"""QA Domain — Safety Policy.

Pure functions to classify a question's safety level and produce
safety metadata.  No infrastructure dependencies.

Classification levels:
    normal:     General informational query; standard disclaimer.
    caution:    Medical query affecting health decisions; stronger advisory.
    emergency:  Life-threatening symptoms; immediate action required.
"""

from __future__ import annotations

import re

from domain.qa.intent_classifier import detect_emergency_intent
from domain.qa.value_objects import SafetyClassification

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

MEDICAL_DISCLAIMER_MD = (
    "\n\n> [!NOTE]\n"
    "> **Lưu ý:** Thông tin mang tính chất tham khảo. "
    "Vui lòng tham khảo ý kiến bác sĩ chuyên khoa để có chẩn đoán chính xác."
)

# ── Emergency question keywords (first-person urgent phrasing) ────────────

EMERGENCY_QUESTION_KEYWORDS = [
    "tôi đang bị",
    "tôi bị ngất",
    "tôi bị co giật",
    "tôi bị ngộ độc",
    "tôi muốn tự tử",
    "tôi uống nhầm",
    "tôi uống quá liều",
    "giúp tôi với",
    "cứu tôi",
    "bị đột quỵ",
    "ngừng thở",
    "ngừng tim",
    "bất tỉnh",
    "hôn mê",
    "chảy máu không cầm",
    "help me",
    "i'm having a heart attack",
    "call ambulance",
    "overdose",
    "unconscious",
]

# ── Caution patterns ─────────────────────────────────────────────────────

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


# ── Public API ────────────────────────────────────────────────────────────

def detect_caution_intent(question: str) -> bool:
    """Return True when the question warrants caution-level safety messaging."""
    for pattern in _CAUTION_COMPILED:
        if pattern.search(question):
            return True
    return False


def classify_safety(question: str) -> SafetyClassification:
    """Classify a user question and return the appropriate safety metadata.

    Evaluation order (first match wins):
    1. Emergency: detect_emergency_intent() + keyword scan
    2. Caution: _CAUTION_COMPILED patterns
    3. Normal: everything else

    Args:
        question: The user's natural language question.

    Returns:
        A SafetyClassification value object.
    """
    q_lower = question.lower()

    # 1. Emergency: regex patterns from intent_classifier
    if detect_emergency_intent(question):
        return SafetyClassification(
            level="emergency",
            requires_emergency_notice=True,
            disclaimer=EMERGENCY_DISCLAIMER_VI,
        )

    # 2. Emergency: first-person urgent keywords (fallback)
    for keyword in EMERGENCY_QUESTION_KEYWORDS:
        if keyword in q_lower:
            return SafetyClassification(
                level="emergency",
                requires_emergency_notice=True,
                disclaimer=EMERGENCY_DISCLAIMER_VI,
            )

    # 3. Caution
    if detect_caution_intent(question):
        return SafetyClassification(
            level="caution",
            requires_emergency_notice=False,
            disclaimer=CAUTION_DISCLAIMER_VI,
        )

    # 4. Normal
    return SafetyClassification(
        level="normal",
        requires_emergency_notice=False,
        disclaimer=MEDICAL_DISCLAIMER_VI,
    )


def safety_from_response_type(response_type: str, question: str) -> SafetyClassification:
    """Derive safety from the pipeline's response_type classification.

    When response_type is 'warning', the pipeline has already detected
    emergency intent.

    Args:
        response_type: The response_type from the pipeline ('warning', 'text', 'table').
        question: The original user question.

    Returns:
        A SafetyClassification.
    """
    if response_type == "warning":
        return SafetyClassification(
            level="emergency",
            requires_emergency_notice=True,
            disclaimer=EMERGENCY_DISCLAIMER_VI,
        )
    return classify_safety(question)
