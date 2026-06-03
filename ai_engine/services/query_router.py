"""Query Router — Phân loại câu hỏi và chọn đường đi xử lý (Phương án C).

Hybrid Architecture:
    ┌─────────────┐
    │  Câu hỏi NL │
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │ Query Router │ ── Phân tích câu hỏi
    └──┬───────┬──┘
       │       │
  ┌────▼───┐ ┌─▼──────────┐
  │ CYPHER │ │  LIGHTRAG   │
  │ (Neo4j │ │ (GraphRAG   │
  │  trực  │ │  semantic   │
  │  tiếp) │ │  retrieval) │
  └────┬───┘ └─┬──────────┘
       │       │
    ┌──▼───────▼──┐
    │  Response    │
    │  Formatter   │
    └─────────────┘

Cypher path dùng khi:
    - Câu hỏi dạng liệt kê chính xác ("triệu chứng của X", "thuốc trị Y")
    - Câu hỏi thống kê/đếm ("bao nhiêu bệnh", "top 5 ...")
    - Câu hỏi tra cứu profile bệnh ("toàn bộ thông tin về X")

LightRAG path dùng khi:
    - Câu hỏi mơ hồ/thematic ("bệnh nào liên quan đến phổi")
    - Câu hỏi suy luận nhiều bước
    - Câu hỏi giải thích, tư vấn
    - Câu hỏi so sánh, tổng hợp
"""

import logging
import re

logger = logging.getLogger(__name__)


# ── Query path enum ───────────────────────────────────────────────────────
class QueryPath:
    CYPHER = "cypher"       # Truy vấn Cypher trực tiếp lên Neo4j VietMedKG
    LIGHTRAG = "lightrag"   # LightRAG graph-enhanced retrieval


# ── Patterns that indicate a direct Cypher query is more precise ──────────

# Vietnamese patterns for exact lookup
EXACT_LOOKUP_PATTERNS_VI = [
    # "triệu chứng (của) X (là gì)"
    r"triệu chứng\s+(?:của\s+)?(?:bệnh\s+)?(.+?)(?:\s+là|\s+gồm|\?|$)",
    # "X có triệu chứng gì / những triệu chứng gì"
    r"(.+?)\s+có\s+(?:những\s+)?triệu chứng\s+(?:gì|nào)",
    # "thuốc (điều trị / chữa / trị) X"
    r"thuốc\s+(?:điều trị|chữa|trị)\s+(?:bệnh\s+)?(.+?)(?:\?|$)",
    # "X (dùng / uống) thuốc gì"
    r"(.+?)\s+(?:dùng|uống|điều trị bằng)\s+thuốc\s+(?:gì|nào)",
    # "X điều trị (bằng cách) nào / như thế nào"
    r"(?:bệnh\s+)?(.+?)\s+điều trị\s+(?:bằng\s+cách\s+)?(?:nào|như thế nào)",
    # "khoa điều trị X"
    r"khoa\s+(?:điều trị|khám)\s+(?:bệnh\s+)?(.+?)(?:\?|$)",
    # "X nên ăn gì / không nên ăn gì"
    r"(?:bị\s+)?(.+?)\s+(?:nên|không nên)\s+ăn\s+(?:gì|những gì)",
    # "phòng tránh X (như thế nào)"
    r"(?:cách\s+)?phòng\s+(?:tránh|ngừa)\s+(?:bệnh\s+)?(.+?)(?:\?|$)",
]

# English patterns for exact lookup
EXACT_LOOKUP_PATTERNS_EN = [
    r"symptoms?\s+of\s+(.+?)(?:\?|$)",
    r"(?:what|which)\s+(?:drugs?|medicines?)\s+(?:treat|cure|for)\s+(.+?)(?:\?|$)",
    r"(?:how|what)\s+(?:to\s+)?treat\s+(.+?)(?:\?|$)",
    r"(?:treatment|cure)\s+for\s+(.+?)(?:\?|$)",
]

# Count/statistics patterns
COUNT_PATTERNS = [
    r"bao nhiêu\s+(?:bệnh|triệu chứng|thuốc)",
    r"tổng\s+(?:số|cộng)\s+(?:bệnh|triệu chứng|thuốc)",
    r"how many\s+(?:diseases?|symptoms?|drugs?|medicines?)",
    r"(?:count|total)\s+(?:of\s+)?(?:diseases?|symptoms?|drugs?)",
    r"top\s+\d+",
    r"thống kê",
]

# Full profile patterns — "cho tôi thông tin về X", "X là bệnh gì"
PROFILE_PATTERNS = [
    r"(?:toàn bộ\s+)?thông tin\s+(?:về\s+)?(?:bệnh\s+)?(.+?)(?:\?|$)",
    r"(?:cho tôi biết|nói cho tôi)\s+(?:về\s+)?(?:bệnh\s+)?(.+?)(?:\?|$)",
    r"(.+?)\s+là\s+(?:bệnh\s+)?gì",
]


def _extract_disease_name(question: str) -> str | None:
    """Try to extract a disease name from the question.

    Args:
        question: The user question.

    Returns:
        Extracted disease name or None.
    """
    q = question.strip().rstrip("?").strip()

    all_patterns = (
        EXACT_LOOKUP_PATTERNS_VI
        + EXACT_LOOKUP_PATTERNS_EN
        + PROFILE_PATTERNS
    )

    for pattern in all_patterns:
        match = re.search(pattern, q, re.IGNORECASE)
        if match:
            name = match.group(1).strip().rstrip(".")
            # Clean up common prefixes
            name = re.sub(r"^(?:bệnh|bị)\s+", "", name, flags=re.IGNORECASE)
            # Remove trailing words like 'không' or brackets
            name = re.sub(r"\s+không$", "", name, flags=re.IGNORECASE)
            name = name.strip("[]")
            if len(name) >= 2:
                return name

    return None


def route_query(question: str) -> dict:
    """Decide which query path to use for a given question.

    This is the core decision logic of Phương án C (Hybrid).

    Args:
        question: The user's natural language question.

    Returns:
        Dict with:
            - path: QueryPath.CYPHER or QueryPath.LIGHTRAG
            - disease_name: extracted disease name (if applicable)
            - query_type: specific query type for Cypher path
            - reason: explanation of the routing decision
    """
    q_lower = question.lower().strip()

    # ── Priority 1: Count/statistics → Cypher ─────────────────────────────
    for pattern in COUNT_PATTERNS:
        if re.search(pattern, q_lower):
            logger.info("Route → CYPHER (count/statistics): %s", question[:80])
            return {
                "path": QueryPath.CYPHER,
                "disease_name": None,
                "query_type": "count",
                "reason": "Câu hỏi thống kê/đếm → Cypher chính xác hơn",
            }

    # ── Priority 2: Exact entity lookup → Cypher ─────────────────────────
    # If the question matches any lookup or profile pattern, route to CYPHER.
    all_cypher_patterns = EXACT_LOOKUP_PATTERNS_VI + EXACT_LOOKUP_PATTERNS_EN + PROFILE_PATTERNS
    
    for pattern in all_cypher_patterns:
        if re.search(pattern, question, re.IGNORECASE):
            logger.info("Route → CYPHER (exact lookup pattern matched): %s", question[:80])
            return {
                "path": QueryPath.CYPHER,
                "disease_name": None,  # Not needed for LLM Text2Cypher
                "query_type": None,    # Not needed for LLM Text2Cypher
                "reason": "Matched structured lookup pattern → Cypher (LLM generated)",
            }

    # ── Priority 3: Everything else → LightRAG ───────────────────────────
    logger.info("Route → LIGHTRAG (semantic/thematic): %s", question[:80])
    return {
        "path": QueryPath.LIGHTRAG,
        "disease_name": None,
        "query_type": None,
        "reason": "Câu hỏi mơ hồ/thematic/suy luận → LightRAG retrieval",
    }
