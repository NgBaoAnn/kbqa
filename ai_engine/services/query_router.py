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
  │ (Neo4j │ │ (semantic   │
  │  trực  │ │  retrieval) │
  │  tiếp) │ │             │
  └────┬───┘ └─┬──────────┘
       │       │
    ┌──▼───────▼──┐
    │  Response    │
    │  Formatter   │
    └─────────────┘

Thuật toán xác định (query_type, entity):

  BƯỚC 1 — regex fast path (classify_cypher_intent):
    count patterns → ("count", None)
    FORWARD patterns → (type, _clean_entity(group))
      type ∈ {symptoms, medicine, treatment, advice,
               prevention, department, profile}
      entity = Vietnamese disease name
    REVERSE patterns → (type, _clean_entity(group))
      type ∈ {find_by_symptom, find_by_medicine,
               find_by_nutrition_avoid, find_by_nutrition_eat,
               find_by_prevention}
      entity = constraint keyword (symptom phrase, drug name, food, etc.)
    No match → (None, None)

  BƯỚC 2 — LLM fallback (extract_intent_with_llm):
    Called only when entity is None and type != "count".
    Returns JSON {query_type, entity}; errors return (None, None).
    routing_method updated to "llm" whenever LLM is invoked.

  BƯỚC 3 — Pipeline routing (pipeline.py):
    type == "count"         → CYPHER (no entity needed)
    type ∈ _FIND_BY_TYPES   → CYPHER (entity = keyword, CONTAINS, no disambiguation)
    entity is None          → LIGHTRAG
    entity found in KG      → CYPHER (exact=True, after disambiguation)
    entity not in KG        → LIGHTRAG (data-driven fallback)
"""

import json
import logging
import os
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


_QUESTION_WORDS: frozenset[str] = frozenset({
    "gì", "nào", "sao", "thế nào", "như thế nào",
    "bao nhiêu", "khi nào", "ở đâu",
    "what", "which", "how", "when", "where",
})

_VALID_QUERY_TYPES: frozenset[str] = frozenset({
    # Forward (entity = disease name)
    "symptoms", "medicine", "treatment", "advice",
    "prevention", "department", "profile", "count",
    # Reverse (entity = constraint keyword, not a disease name)
    "find_by_symptom", "find_by_medicine",
    "find_by_nutrition_avoid", "find_by_nutrition_eat",
    "find_by_prevention",
    # Sentinel
    "unknown",
})

_FIND_BY_TYPES: frozenset[str] = frozenset({
    "find_by_symptom", "find_by_medicine",
    "find_by_nutrition_avoid", "find_by_nutrition_eat",
    "find_by_prevention",
})


def _clean_entity(raw: str) -> str | None:
    """Normalize an extracted entity name; returns None for question words."""
    if not raw:
        return None
    name = raw.strip().rstrip("?.!")
    name = re.sub(r"^(?:bệnh|bị)\s+", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+không$", "", name, flags=re.IGNORECASE)
    # Strip trailing question phrases before checking length (R3)
    name = re.sub(
        r"\s+(?:như\s+thế\s+nào|thế\s+nào|là\s+gì|gồm\s+gì|thì\s+sao)\s*$",
        "", name, flags=re.IGNORECASE,
    )
    name = name.strip("[]").strip()
    if not name or len(name) < 2:
        return None
    # Reject bare question words (R2)
    if name.lower() in _QUESTION_WORDS:
        return None
    return name


def classify_cypher_intent(question: str) -> tuple[str | None, str | None]:
    """Extract (query_type, entity) from a question.

    Returns (query_type, entity) or (None, None) when no pattern matches.
    (query_type, None) means type detected but entity invalid → LLM fallback.
    """
    q = question.strip()

    # Multi-constraint bracket list → too complex for regex; let LLM classify.
    # "[A, B, C, ...]" with ≥2 commas inside brackets = user-provided list.
    if re.search(r"\[[^\]]+,[^\]]+,[^\]]+", q):
        return None, None

    # Count — entity not needed
    for pattern in COUNT_PATTERNS:
        if re.search(pattern, q.lower()):
            return "count", None

    # Reverse: find_by_symptom — checked BEFORE forward symptom patterns to prevent
    # "bệnh nào có triệu chứng X" from being captured by the forward "triệu chứng..." pattern.
    for pattern in [
        r"bệnh\s+(?:lý\s+)?(?:nào|gì)\s+(?:có|gây|biểu\s+hiện\s+bằng)\s+(?:triệu\s*chứng|biểu\s+hiện|dấu\s+hiệu)\s+(.+?)(?:\?|$)",
        r"(?:triệu\s*chứng|biểu\s+hiện|dấu\s+hiệu)\s+(.+?)\s+(?:là|thuộc)\s+bệnh\s+(?:gì|nào)",
        r"which\s+diseases?\s+(?:has|have|cause[sd]?)\s+(.+?)\s+(?:as\s+)?(?:symptom|sign)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "find_by_symptom", _clean_entity(m.group(1))

    # Symptoms — "entity có triệu chứng" patterns must precede "triệu chứng của entity"
    # to avoid lazy capture grabbing question words like "gì" (R1 fix)
    for pattern in [
        r"(.+?)\s+có\s+(?:những\s+)?triệu\s*chứng\s+(?:gì|nào)",
        r"triệu chứng\s+(?:của\s+)?(?:bệnh\s+)?(.+?)(?:\s+là|\s+gồm|\?|$)",
        r"biểu hiện\s+(?:của\s+)?(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"dấu hiệu\s+(?:của\s+)?(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"symptoms?\s+of\s+(.+?)(?:\?|$)",
        r"signs?\s+of\s+(.+?)(?:\?|$)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "symptoms", _clean_entity(m.group(1))

    # Medicine
    for pattern in [
        r"thuốc\s+(?:điều\s*trị|chữa|trị)\s+(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"(.+?)\s+(?:dùng|uống|điều\s*trị\s+bằng)\s+thuốc\s+(?:gì|nào)",
        r"(?:what|which)\s+(?:drugs?|medicines?)\s+(?:treat|cure|for)\s+(.+?)(?:\?|$)",
        r"(?:medication|drugs?)\s+for\s+(.+?)(?:\?|$)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "medicine", _clean_entity(m.group(1))

    # Treatment
    for pattern in [
        r"(?:bệnh\s+)?(.+?)\s+điều\s*trị\s+(?:bằng\s+cách\s+)?(?:nào|như\s+thế\s+nào)",
        r"cách\s+(?:điều\s*trị|chữa)\s+(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"phương\s*pháp\s+(?:điều\s*trị|chữa)\s+(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"(?:how|what)\s+(?:to\s+)?treat\s+(.+?)(?:\?|$)",
        r"(?:treatment|cure)\s+for\s+(.+?)(?:\?|$)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "treatment", _clean_entity(m.group(1))

    # Department
    for pattern in [
        r"khoa\s+(?:điều\s*trị|khám)\s+(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"(?:bệnh\s+)?(.+?)\s+(?:khám|điều\s*trị)\s+(?:ở\s+)?khoa\s+(?:gì|nào)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "department", _clean_entity(m.group(1))

    # Advice / nutrition
    for pattern in [
        r"(?:bị\s+)?(.+?)\s+(?:nên|không\s+nên)\s+ăn\s+(?:gì|những\s+gì)",
        r"chế\s+độ\s+ăn\s+(?:cho\s+)?(?:bị\s+)?(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"dinh\s*dưỡng\s+(?:cho\s+)?(?:bị\s+)?(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"(?:bệnh\s+)?(.+?)\s+ăn\s+(?:gì|những\s+gì)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "advice", _clean_entity(m.group(1))

    # Prevention
    for pattern in [
        r"(?:cách\s+)?phòng\s+(?:tránh|ngừa)\s+(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"(?:bệnh\s+)?(.+?)\s+phòng\s+(?:tránh|ngừa)\s+(?:như\s+thế\s+nào|thế\s+nào)",
        r"(?:làm\s+thế\s+nào\s+)?để\s+phòng\s+(?:bệnh\s+)?(.+?)(?:\?|$)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "prevention", _clean_entity(m.group(1))

    # Reverse: find_by_medicine — "thuốc X chữa bệnh nào"
    for pattern in [
        r"thuốc\s+(.+?)\s+(?:chữa|điều\s*trị|dùng cho|trị)\s+bệnh\s+(?:gì|nào)",
        r"(.+?)\s+(?:chữa|điều\s*trị|trị)\s+(?:được\s+)?bệnh\s+(?:gì|nào)\s*(?:\?|$)",
        r"(.+?)\s+dùng\s+cho\s+bệnh\s+(?:gì|nào)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "find_by_medicine", _clean_entity(m.group(1))

    # Reverse: find_by_nutrition_avoid — "kiêng X tốt cho bệnh nào"
    for pattern in [
        r"(?:không\s+(?:nên\s+)?ăn|kiêng|tránh\s+ăn)\s+(.+?)\s+(?:tốt\s+cho|là|giúp|chữa|hỗ\s*trợ)\s+bệnh\s+(?:gì|nào)",
        r"bệnh\s+(?:lý\s+)?(?:nào|gì)\s+(?:nên\s+)?(?:kiêng|tránh|không\s+nên\s+ăn)\s+(.+?)(?:\?|$)",
        r"(.+?)\s+(?:là thực phẩm|không nên ăn khi)\s+bị\s+bệnh\s+(?:gì|nào)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "find_by_nutrition_avoid", _clean_entity(m.group(1))

    # Reverse: find_by_nutrition_eat — "ăn X tốt cho bệnh nào"
    for pattern in [
        r"(?:nên\s+)?ăn\s+(.+?)\s+(?:tốt\s+cho|giúp|có\s+tác\s+dụng\s+(?:với|cho)|hỗ\s*trợ)\s+bệnh\s+(?:gì|nào)",
        r"bệnh\s+(?:lý\s+)?(?:nào|gì)\s+(?:nên|cần)\s+ăn\s+(.+?)(?:\?|$)",
        r"(.+?)\s+có\s+tác\s+dụng\s+(?:với|cho|hỗ trợ)\s+bệnh\s+(?:gì|nào)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "find_by_nutrition_eat", _clean_entity(m.group(1))

    # Reverse: find_by_prevention — "X phòng được bệnh nào"
    for pattern in [
        r"(.+?)\s+(?:phòng|giúp\s+phòng|ngăn\s+ngừa)\s+(?:được\s+)?bệnh\s+(?:gì|nào)",
        r"bệnh\s+(?:lý\s+)?(?:nào|gì)\s+(?:được\s+)?phòng\s+bằng\s+(.+?)(?:\?|$)",
        r"(.+?)\s+(?:phòng ngừa|ngừa)\s+bệnh\s+(?:gì|nào)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "find_by_prevention", _clean_entity(m.group(1))

    # Profile / general info
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
            return "profile", _clean_entity(m.group(1))

    return None, None


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
            logger.info("Route → CYPHER (count): %s", question[:80])
            return {
                "path": QueryPath.CYPHER,
                "disease_name": None,
                "query_type": "count",
                "reason": "Câu hỏi thống kê/đếm → Cypher",
            }

    # ── Priority 2: Structured entity lookup → Cypher ────────────────────
    all_cypher_patterns = EXACT_LOOKUP_PATTERNS_VI + EXACT_LOOKUP_PATTERNS_EN + PROFILE_PATTERNS
    for pattern in all_cypher_patterns:
        if re.search(pattern, question, re.IGNORECASE):
            query_type, entity = classify_cypher_intent(question)
            logger.info(
                "Route → CYPHER (type=%s, entity=%s): %s",
                query_type, entity, question[:80],
            )
            return {
                "path": QueryPath.CYPHER,
                "disease_name": entity,
                "query_type": query_type,
                "reason": f"Pattern match → Cypher template (type={query_type})",
            }

    # ── Priority 3: Everything else → LightRAG ───────────────────────────
    logger.info("Route → LIGHTRAG (semantic/thematic): %s", question[:80])
    return {
        "path": QueryPath.LIGHTRAG,
        "disease_name": None,
        "query_type": None,
        "reason": "Câu hỏi mơ hồ/thematic/suy luận → LightRAG retrieval",
    }


# ── LLM Structured Intent Extraction (fallback) ───────────────────────────

_INTENT_SYSTEM_PROMPT = """\
You classify a Vietnamese (or English) medical question about the VietMedKG
knowledge graph and return EXACTLY one JSON object: {"query_type": "...", "entity": "..."}.

# Knowledge graph fields (VietMedKG)
- Disease: disease_name, disease_description, disease_category, disease_cause
- Symptom: disease_symptom (comma-separated blob: "Ho khan, Sốt cao, Đau ngực")
- Treatment: cure_method, cure_department
- Medicine: drug_common, drug_recommend (comma-separated blob, mostly
  Vietnamese-prefixed Latin names e.g. "Viên nén Azithromycin, Viên nang Levofloxacin")
- Advice: nutrition_do_eat, nutrition_not_eat, nutrition_recommend_meal,
  disease_prevention (all comma-separated blobs; nutrition_not_eat samples:
  "Rượu trắng, Bia, Trứng vịt muối, Dưa chua khô"; nutrition_do_eat samples:
  "Trứng, vừng, bắp cải, rau muống, hạt sen")

# Two query directions
FORWARD  — user names a disease, asks about its fields. entity = disease name.
REVERSE  — user names a constraint (symptom / drug / food / prevention method),
           asks WHICH disease matches. entity = the constraint keyword.

# Valid query_type values

Forward (entity = Vietnamese disease name; null if irrelevant):
  symptoms        — user wants Symptom of disease X
  medicine        — user wants Medicine for disease X
  treatment       — user wants Treatment / cure_method of disease X
  advice          — user wants nutrition advice for disease X
  prevention      — user wants how to prevent disease X
  department      — user wants which medical department treats disease X
  profile         — user wants overview / "what is" disease X
  count           — counting/statistics (entity = null)

Reverse (entity = constraint keyword, NOT a disease name):
  find_by_symptom         — "which disease has symptom X" (Symptom.disease_symptom)
  find_by_medicine        — "which disease is drug X for" (Medicine.drug_common/recommend)
  find_by_nutrition_avoid — "which disease should avoid food X" (Advice.nutrition_not_eat)
  find_by_nutrition_eat   — "which disease should eat food X" (Advice.nutrition_do_eat)
  find_by_prevention      — "X helps prevent which disease" (Advice.disease_prevention)

Sentinel:
  unknown — use when (a) question mixes multiple unrelated constraints (long
            bracketed list of foods/drugs/symptoms), (b) general advice without
            identifiable entity, or (c) intent doesn't match any type above.
            Set entity = null. The pipeline routes to semantic search.

# Rules
- Forward: entity = Vietnamese disease name. Strip "bệnh ", "bị ".
  Never include question words: gì, nào, như thế nào, what, which, how.
- Reverse: entity = ONE short keyword (1–4 words). If user gives a list like
  "[A, B, C, D]", pick the most specific ONE. If picking one would lose key
  meaning → query_type="unknown", entity=null.
- count, unknown: entity = null.

# Output
ONLY a JSON object, no markdown, no explanation:
{"query_type": "...", "entity": "..."}

# Examples

Q: "tiểu đường có triệu chứng gì"
A: {"query_type": "symptoms", "entity": "tiểu đường"}

Q: "bệnh nào có triệu chứng sốt cao"
A: {"query_type": "find_by_symptom", "entity": "sốt cao"}

Q: "bệnh nào gây ho khan kéo dài"
A: {"query_type": "find_by_symptom", "entity": "ho khan"}

Q: "thuốc chữa viêm phổi"
A: {"query_type": "medicine", "entity": "viêm phổi"}

Q: "thuốc Azithromycin chữa bệnh nào"
A: {"query_type": "find_by_medicine", "entity": "Azithromycin"}

Q: "Levofloxacin dùng cho bệnh gì"
A: {"query_type": "find_by_medicine", "entity": "Levofloxacin"}

Q: "cách điều trị viêm khớp như thế nào"
A: {"query_type": "treatment", "entity": "viêm khớp"}

Q: "khoa nào điều trị viêm phổi"
A: {"query_type": "department", "entity": "viêm phổi"}

Q: "tăng huyết áp là bệnh gì"
A: {"query_type": "profile", "entity": "tăng huyết áp"}

Q: "tiểu đường nên ăn gì"
A: {"query_type": "advice", "entity": "tiểu đường"}

Q: "viêm dạ dày kiêng gì"
A: {"query_type": "advice", "entity": "viêm dạ dày"}

Q: "kiêng rượu bia tốt cho bệnh nào"
A: {"query_type": "find_by_nutrition_avoid", "entity": "rượu bia"}

Q: "không nên ăn dưa chua khô là bệnh gì"
A: {"query_type": "find_by_nutrition_avoid", "entity": "dưa chua khô"}

Q: "ăn rau muống tốt cho bệnh nào"
A: {"query_type": "find_by_nutrition_eat", "entity": "rau muống"}

Q: "hạt sen có tác dụng với bệnh nào"
A: {"query_type": "find_by_nutrition_eat", "entity": "hạt sen"}

Q: "phòng tránh viêm phổi như thế nào"
A: {"query_type": "prevention", "entity": "viêm phổi"}

Q: "rửa tay phòng được bệnh nào"
A: {"query_type": "find_by_prevention", "entity": "rửa tay"}

Q: "tiêm vắc-xin BCG phòng bệnh gì"
A: {"query_type": "find_by_prevention", "entity": "vắc-xin BCG"}

Q: "bao nhiêu bệnh trong cơ sở dữ liệu"
A: {"query_type": "count", "entity": null}

Q: "Việc tránh ăn [Dưa chua khô, Bia, Rượu trắng, Trứng cút] có thể hỗ trợ điều trị bệnh lý nào?"
A: {"query_type": "unknown", "entity": null}

Q: "Tôi nên làm gì khi bị stress công việc"
A: {"query_type": "unknown", "entity": null}

Q: "symptoms of diabetes"
A: {"query_type": "symptoms", "entity": "tiểu đường"}

Q: "which disease has fever as symptom"
A: {"query_type": "find_by_symptom", "entity": "sốt"}\
"""


async def extract_intent_with_llm(question: str) -> tuple[str | None, str | None]:
    """LLM fallback for intent extraction when regex returns no valid entity.

    Returns (query_type, entity). Either or both may be None on failure.
    Never raises — logs warning and returns (None, None) on any error.
    """
    from ai_engine.services.text2cypher import client as _llm_client

    try:
        resp = await _llm_client.chat.completions.create(
            model=os.environ.get("LLM_MODEL_NAME", "qwen2.5:7b"),
            messages=[
                {"role": "system", "content": _INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            temperature=0.0,
            max_tokens=160,
        )
        raw = resp.choices[0].message.content.strip()
        # Strip markdown fences if model ignores instructions
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1]) if len(lines) >= 3 else raw

        parsed = json.loads(raw)
        q_type = parsed.get("query_type") or "unknown"
        entity_raw = parsed.get("entity") or None

        if q_type not in _VALID_QUERY_TYPES:
            q_type = None
        entity = _clean_entity(str(entity_raw)) if entity_raw else None

        logger.info("LLM intent: type=%s entity=%r for: %s", q_type, entity, question[:60])
        return q_type, entity

    except Exception as exc:
        logger.warning("LLM intent extraction failed: %s", exc)
        return None, None
