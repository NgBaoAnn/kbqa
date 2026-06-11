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

  BƯỚC 1 — LLM structured extraction (extract_intent_with_llm):
    Primary classifier. Returns JSON {query_type, entity}.
    Errors return (None, None).

  BƯỚC 2 — Regex fallback (classify_cypher_intent):
    Called only when LLM fails or returns no entity.
    FORWARD patterns → (type, _clean_entity(group))
    REVERSE patterns → (type, _clean_entity(group))
    No match → (None, None)

  BƯỚC 3 — Pipeline routing (pipeline.py):
    type ∈ _FIND_BY_TYPES   → CYPHER (entity = keyword, CONTAINS, no disambiguation)
    entity is None          → LIGHTRAG
    entity found in KG      → CYPHER (exact=True, after disambiguation)
    entity not in KG        → LIGHTRAG (data-driven fallback)
"""

import json
import logging
import re

logger = logging.getLogger(__name__)


# ── Query path enum ───────────────────────────────────────────────────────
class QueryPath:
    CYPHER = "cypher"       # Truy vấn Cypher trực tiếp lên Neo4j VietMedKG
    LIGHTRAG = "lightrag"   # LightRAG graph-enhanced retrieval


_QUESTION_WORDS: frozenset[str] = frozenset({
    "gì", "nào", "sao", "thế nào", "như thế nào",
    "bao nhiêu", "khi nào", "ở đâu",
    "what", "which", "how", "when", "where",
})

_VALID_QUERY_TYPES: frozenset[str] = frozenset({
    # Forward (entity = disease name)
    "symptoms", "medicine", "treatment", "advice",
    "prevention", "department", "profile",
    "linked_diseases",
    "cause", "check_method", "susceptible_population",
    # Reverse (entity = constraint keyword, not a disease name)
    "find_by_symptom", "find_by_medicine",
    "find_by_nutrition_avoid", "find_by_nutrition_eat",
    "find_by_prevention", "find_by_check_method",
    # Chain (2-hop, entity = disease/symptom name)
    "chain_linked_avoid", "chain_linked_eat",
    # Sentinel
    "unknown",
})

_FIND_BY_TYPES: frozenset[str] = frozenset({
    "find_by_symptom", "find_by_medicine",
    "find_by_nutrition_avoid", "find_by_nutrition_eat",
    "find_by_prevention", "find_by_check_method",
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
        r"\s+(?:như\s+thế\s+nào|thế\s+nào|là\s+gì|gồm\s+gì|thì\s+sao|có|không)\s*$",
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

    # Reverse: find_by_symptom — checked BEFORE forward symptom patterns to prevent
    # "bệnh nào có triệu chứng X" from being captured by the forward "triệu chứng..." pattern.
    # Also catches "bao nhiêu bệnh có triệu chứng X" — returns representative examples, not a count.
    for pattern in [
        r"bệnh\s+(?:lý\s+)?(?:nào|gì)\s+(?:có|gây|biểu\s+hiện\s+bằng)\s+(?:triệu\s*chứng|biểu\s+hiện|dấu\s+hiệu)\s+(.+?)(?:\?|$)",
        r"(?:triệu\s*chứng|biểu\s+hiện|dấu\s+hiệu)\s+(.+?)\s+(?:là|thuộc)\s+bệnh\s+(?:gì|nào)",
        r"which\s+diseases?\s+(?:has|have|cause[sd]?)\s+(.+?)\s+(?:as\s+)?(?:symptom|sign)",
        r"bao\s+nhiêu\s+bệnh\s+(?:lý\s+)?(?:có|gây)\s+(?:triệu\s*chứng|biểu\s+hiện|dấu\s+hiệu)\s+(.+?)(?:\?|$)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "find_by_symptom", _clean_entity(m.group(1))

    # Symptoms — "entity có triệu chứng" patterns must precede "triệu chứng của entity"
    # to avoid lazy capture grabbing question words like "gì" (R1 fix).
    # "bao nhiêu triệu chứng của X" → symptoms type; synthesizer lists them, does not count.
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

    # Cause
    for pattern in [
        r"nguyên\s+nhân\s+(?:gây\s+)?(?:ra\s+)?(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"(?:bệnh\s+)?(.+?)\s+(?:do\s+)?nguyên\s+nhân\s+(?:gì|nào)",
        r"(?:tại\s+sao|vì\s+sao)\s+(?:bị|mắc)\s+(?:bệnh\s+)?(.+?)(?:\?|$)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "cause", _clean_entity(m.group(1))

    # Check method
    for pattern in [
        r"(?:xét\s*nghiệm|kiểm\s*tra|chẩn\s*đoán)\s+(?:bệnh\s+)?(.+?)(?:\s+bằng\s+cách\s+nào|\?|$)",
        r"(?:bệnh\s+)?(.+?)\s+(?:cần\s+)?(?:xét\s*nghiệm|kiểm\s*tra|chẩn\s*đoán)\s+(?:gì|nào|bằng\s+cách\s+nào)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "check_method", _clean_entity(m.group(1))

    # Susceptible population
    for pattern in [
        r"(?:ai|đối\s+tượng\s+nào|người\s+nào)\s+(?:dễ\s+)?(?:mắc|bị)\s+(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"(?:bệnh\s+)?(.+?)\s+(?:thường\s+gặp|phổ\s+biến)\s+(?:ở|với)\s+(?:ai|đối\s+tượng\s+nào)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "susceptible_population", _clean_entity(m.group(1))

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

    # Reverse: find_by_check_method
    for pattern in [
        r"(?:xét\s*nghiệm|kiểm\s*tra|chẩn\s*đoán)\s+(.+?)\s+dùng\s+để\s+(?:chẩn\s*đoán|phát\s+hiện)\s+bệnh\s+(?:gì|nào)",
        r"(.+?)\s+là\s+xét\s*nghiệm\s+của\s+bệnh\s+(?:gì|nào)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "find_by_check_method", _clean_entity(m.group(1))

    # Chain: linked → avoid
    for pattern in [
        r"(?:thực\s*phẩm|đồ\s+ăn).*?(?:tránh|kiêng|không\s+nên\s+ăn).*?(?:bệnh.*?(?:liên\s+quan|đi\s+kèm|kèm\s+theo).*?)(?:\[)?(.+?)(?:\]|\?|$)",
        r"(?:tránh|kiêng).*?(?:không\s+(?:mắc|gặp)).*?(?:bệnh.*?(?:liên\s+quan|đi\s+kèm)).*?(?:\[)?(.+?)(?:\]|\?|$)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "chain_linked_avoid", _clean_entity(m.group(1))

    # Chain: linked → eat
    for pattern in [
        r"(?:thực\s*phẩm|đồ\s+ăn).*?(?:nên\s+ăn|ăn\s+gì).*?(?:bệnh.*?(?:liên\s+quan|đi\s+kèm|kèm\s+theo).*?)(?:\[)?(.+?)(?:\]|\?|$)",
        r"(?:để\s+phòng\s+tránh).*?(?:bệnh.*?(?:liên\s+quan|đi\s+kèm)).*?(?:nên\s+ăn|ăn\s+gì).*?(?:\[)?(.+?)(?:\]|\?|$)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "chain_linked_eat", _clean_entity(m.group(1))

    # Linked diseases — "bệnh X liên quan đến bệnh nào"
    # Must appear BEFORE profile patterns to prevent broad profile regex
    # from swallowing "bệnh X liên quan đến..." queries.
    # Pattern with explicit "có" MUST come first to prevent lazy (.+?) from
    # capturing "có" as part of the entity in "viêm phổi có liên quan..."
    for pattern in [
        r"(?:bệnh\s+)?(.+?)\s+có\s+liên\s+quan\s+(?:đến|với)\s+(?:bệnh|những\s+bệnh)\s+(?:gì|nào)",
        r"(?:bệnh\s+)?(.+?)\s+liên\s+quan\s+đến\s+(?:những\s+)?(?:bệnh|bệnh\s+lý)\s+(?:gì|nào)",
        r"(?:bệnh\s+)?(.+?)\s+đi\s+kèm\s+(?:với\s+)?(?:bệnh|những\s+bệnh)\s+(?:gì|nào)",
        r"bệnh\s+kèm\s+theo\s+(?:của\s+)?(?:bệnh\s+)?(.+?)(?:\?|$)",
        r"comorbidities?\s+of\s+(.+?)(?:\?|$)",
    ]:
        m = re.search(pattern, q, re.IGNORECASE)
        if m:
            return "linked_diseases", _clean_entity(m.group(1))

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





# ── LLM Structured Intent Extraction (fallback) ───────────────────────────

_INTENT_SYSTEM_PROMPT = """\
You classify a Vietnamese medical question about the VietMedKG knowledge graph.
Return EXACTLY one JSON object: {"query_type": "...", "entity": "..."}.

# Valid query_type values

Forward (entity = Vietnamese disease name):
  symptoms                — Triệu chứng của bệnh X
  cause                   — Nguyên nhân gây ra bệnh X
  check_method            — Phương pháp xét nghiệm/chẩn đoán bệnh X
  susceptible_population  — Đối tượng/Ai dễ mắc bệnh X
  medicine                — Thuốc chữa bệnh X
  treatment               — Phương pháp điều trị bệnh X
  advice                  — Lời khuyên dinh dưỡng cho bệnh X
  prevention              — Cách phòng ngừa bệnh X
  department              — Khoa khám bệnh X
  profile                 — Thông tin tổng quan về bệnh X
  linked_diseases         — Bệnh đi kèm/liên quan với bệnh X

Reverse (entity = constraint keyword, NOT a disease name):
  find_by_symptom         — Bệnh nào có triệu chứng X
  find_by_check_method    — Xét nghiệm X dùng chẩn đoán bệnh nào
  find_by_medicine        — Thuốc X dùng chữa bệnh nào
  find_by_nutrition_avoid — Ăn/Uống/Kiêng X để tránh/trị bệnh nào
  find_by_nutrition_eat   — Ăn/Uống X tốt cho bệnh nào
  find_by_prevention      — Phương pháp X phòng bệnh nào

Chain (2-hop queries, entity = disease/symptom name):
  chain_linked_avoid      — Tránh/kiêng thực phẩm nào để không mắc các bệnh liên quan đến bệnh X
  chain_linked_eat        — Nên ăn thực phẩm nào để phòng tránh bệnh liên quan/đi kèm bệnh X

Sentinel:
  unknown — Câu hỏi liệt kê quá nhiều danh sách không liên quan, hoặc không thuộc các loại trên.

# QUY TẮC TRÍCH XUẤT THỰC THỂ (Entity Extraction Rules)
1. Bỏ các từ thừa: Bỏ các từ để hỏi (gì, nào, bao nhiêu), bỏ các từ đệm (bệnh, bị, mắc, chứng). Ví dụ: "bệnh tiểu đường" -> "tiểu đường".
2. Giữ nguyên cụm từ: Entity phải ngắn gọn, súc tích (thường 1-4 từ).
3. LUẬT CHO NGOẶC VUÔNG (Dành cho hệ thống test): LƯU Ý QUAN TRỌNG: Nếu trong câu hỏi có chứa dấu ngoặc vuông (ví dụ: [sốt cao, ho khan]), phần lớn thực thể cần tìm chính là nội dung NẰM TRONG ngoặc vuông. Hãy trích xuất nội dung đó và bỏ dấu ngoặc đi. Nếu trong ngoặc có nhiều items (ví dụ: [A, B, C]), hãy lấy mục đầu tiên hoặc tiêu biểu nhất để làm entity.

# OUTPUT FORMAT (Chỉ trả về JSON)
{"query_type": "...", "entity": "..."}

# VÍ DỤ (Examples)

Q: "tiểu đường có triệu chứng gì"
A: {"query_type": "symptoms", "entity": "tiểu đường"}

Q: "bệnh nào có triệu chứng ho khan kéo dài"
A: {"query_type": "find_by_symptom", "entity": "ho khan"}

Q: "nguyên nhân nào gây ra viêm dạ dày"
A: {"query_type": "cause", "entity": "viêm dạ dày"}

Q: "cần làm xét nghiệm gì để biết bị sốt xuất huyết"
A: {"query_type": "check_method", "entity": "sốt xuất huyết"}

Q: "trẻ em có dễ mắc bệnh tay chân miệng không"
A: {"query_type": "susceptible_population", "entity": "tay chân miệng"}

Q: "viêm phổi dùng thuốc gì"
A: {"query_type": "medicine", "entity": "viêm phổi"}

Q: "thuốc Azithromycin chữa bệnh nào"
A: {"query_type": "find_by_medicine", "entity": "Azithromycin"}

Q: "không nên ăn dưa chua khô là bệnh gì"
A: {"query_type": "find_by_nutrition_avoid", "entity": "dưa chua khô"}

Q: "thực phẩm nào nên tránh để không gặp phải các bệnh liên quan đến gout"
A: {"query_type": "chain_linked_avoid", "entity": "gout"}

Q: "ăn gì để phòng tránh các bệnh đi kèm với cao huyết áp"
A: {"query_type": "chain_linked_eat", "entity": "cao huyết áp"}

Q: "Việc tránh ăn [Bia, rượu trắng, cua] có thể hỗ trợ điều trị bệnh lý nào?"
A: {"query_type": "find_by_nutrition_avoid", "entity": "Bia, rượu trắng, cua"}

Q: "Có thực phẩm nào tôi nên tránh để không gặp phải các bệnh liên quan đến [Tay và chân màu xanh] không?"
A: {"query_type": "chain_linked_avoid", "entity": "Tay và chân màu xanh"}

Q: "những bệnh nào thường gặp ở người cao tuổi"
A: {"query_type": "unknown", "entity": null}\
"""


async def extract_intent_with_llm(question: str) -> tuple[str | None, str | None]:
    """LLM fallback for intent extraction when regex returns no valid entity.

    Returns (query_type, entity). Either or both may be None on failure.
    Never raises — logs warning and returns (None, None) on any error.
    """
    from ai_engine.config import LLM_MODEL_NAME
    from ai_engine.services.llm_provider import get_chat_client

    try:
        resp = await get_chat_client().chat.completions.create(
            model=LLM_MODEL_NAME,
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
