"""Cypher answer synthesizer — formats Neo4j records into Vietnamese natural language."""

import json
import logging
import re

from ai_engine.config import LLM_MODEL_NAME
from ai_engine.services.llm_provider import get_chat_client

logger = logging.getLogger(__name__)

# ── Payload budget constants ────────────────────────────────────────────────

_MAX_RECORDS = 3
_MAX_FIELD_CHARS = 300
_MAX_PAYLOAD_CHARS = 3000

# Map Cypher alias keys → human-readable Vietnamese labels
_KEY_LABELS: dict[str, str] = {
    "disease": "Bệnh",
    "symptoms": "Triệu chứng",
    "disease_symptom": "Triệu chứng",
    "check_method": "Phương pháp chẩn đoán",
    "risk_group": "Đối tượng dễ mắc",
    "people_easy_get": "Đối tượng dễ mắc",
    "treatment_method": "Phương pháp điều trị",
    "cure_method": "Phương pháp điều trị",
    "treatment": "Phương pháp điều trị",
    "department": "Khoa điều trị",
    "cure_department": "Khoa điều trị",
    "cure_rate": "Tỉ lệ khỏi",
    "cure_probability": "Tỉ lệ khỏi",
    "recommended_drugs": "Thuốc đề xuất",
    "drug_recommend": "Thuốc đề xuất",
    "common_drugs": "Thuốc phổ biến",
    "drug_common": "Thuốc phổ biến",
    "drugs": "Thuốc phổ biến",
    "drug_detail": "Chi tiết thuốc",
    "should_eat": "Nên ăn",
    "nutrition_do_eat": "Nên ăn",
    "should_avoid": "Không nên ăn",
    "nutrition_not_eat": "Không nên ăn",
    "recommended_meals": "Thực đơn gợi ý",
    "nutrition_recommend_meal": "Thực đơn gợi ý",
    "prevention": "Phòng ngừa",
    "disease_prevention": "Phòng ngừa",
    "description": "Mô tả",
    "disease_description": "Mô tả",
    "category": "Chuyên khoa",
    "disease_category": "Chuyên khoa",
    "cause": "Nguyên nhân",
    "disease_cause": "Nguyên nhân",
    "linked_disease": "Bệnh liên quan",
    "linked_symptoms": "Triệu chứng bệnh liên quan",
    "linked_treatment": "Điều trị bệnh liên quan",
    "linked_department": "Khoa của bệnh liên quan",
}

# Fields that store comma-separated lists in the DB and should be split
# before sending to LLM so it sees a proper array, not a raw blob string.
_BLOB_FIELDS: frozenset[str] = frozenset({
    "Triệu chứng", "Thuốc đề xuất", "Thuốc phổ biến", "Chi tiết thuốc",
    "Nên ăn", "Không nên ăn", "Thực đơn gợi ý", "Phòng ngừa",
    "Phương pháp chẩn đoán", "Phương pháp điều trị",
    "Khoa điều trị",
})

_LOW_PRIORITY_FIELDS: frozenset[str] = frozenset({
    "Chi tiết thuốc", "Thực đơn gợi ý", "Nên ăn", "Không nên ăn", "Phòng ngừa"
})

_MAX_LIST_ITEMS = 5

# disease_category in VietMedKG is a breadcrumb path from the Chinese source.
# Strip the encyclopedia prefix so the LLM sees only the meaningful specialty segments.
_CATEGORY_ENCYCLOPEDIA_PREFIX = "bách khoa toàn thư về bệnh"


def _clean_category(value: str) -> str:
    parts = [p.strip() for p in value.split(",")]
    filtered = [p for p in parts if p.lower() != _CATEGORY_ENCYCLOPEDIA_PREFIX and p]
    return ", ".join(filtered) if filtered else value


def _split_blob(value: str) -> list[str] | str:
    """Split a comma-separated blob into a list if it has >= 2 items."""
    items = [x.strip() for x in value.split(",") if x.strip()]
    if len(items) >= 2:
        return items[:_MAX_LIST_ITEMS]
    return value


def _prepare_records_for_llm(records: list[dict]) -> tuple[str, str]:
    """Truncate, localize, and structure records for LLM payload.

    Returns (json_string, note) where note is non-empty when records were cut.
    """
    original_count = len(records)
    truncated = records[:_MAX_RECORDS]
    note = (
        f"(Hiển thị {len(truncated)}/{original_count} kết quả phù hợp nhất)"
        if original_count > _MAX_RECORDS
        else ""
    )

    localized = []
    for r in truncated:
        item: dict = {}
        for k, v in r.items():
            if v is None:
                continue
            s = str(v).strip()
            if not s or s in ("None", "null", "nan"):
                continue
            label = _KEY_LABELS.get(k, k)
            if label == "Chuyên khoa":
                s = _clean_category(s)
            s = s[:_MAX_FIELD_CHARS] + "..." if len(s) > _MAX_FIELD_CHARS else s
            if label in _BLOB_FIELDS:
                item[label] = _split_blob(s)
            else:
                item[label] = s
        if item:
            localized.append(item)

    # Semantic Triage: Drop low priority fields if payload is too large
    while len(json.dumps(localized, ensure_ascii=False)) > _MAX_PAYLOAD_CHARS:
        dropped_any = False
        for r in localized:
            for field in list(r.keys()):
                if field in _LOW_PRIORITY_FIELDS:
                    del r[field]
                    dropped_any = True
        
        # If no low priority fields left to drop and still too large, drop the last record
        if not dropped_any and len(localized) > 1:
            localized.pop()
        elif not dropped_any:
            break  # Can't reduce further, keep at least 1 core record

    return json.dumps(localized, ensure_ascii=False, indent=2), note


# ── Trailing commentary stripper ───────────────────────────────────────────

_TRAILING_JUNK_START = re.compile(
    r"^(?:\*\*[^*]+\*\*\s*)?("
    r"Cơ sở dữ liệu chưa có|"
    r"Hiện tại.{0,10}chưa có|"
    r"Lưu ý[:\s]|"
    r"Chú ý[:\s]|"
    r"Chúc bạn|"
    r"Hãy tham khảo|"
    r"Nên tham khảo|"
    r"Bạn nên đến|"
    r"Tuy nhiên.{0,30}(cần|nên|hãy)|"
    r"Ngoài ra.{0,30}không có|"
    r"\(Giải thích"
    r")",
    re.IGNORECASE,
)
_TRAILING_JUNK_CONTAINS = re.compile(
    r"(không được liệt kê|kết quả đầu|bản ghi đầu|không nằm trong)",
    re.IGNORECASE,
)


def _strip_trailing_commentary(answer: str) -> str:
    lines = answer.rstrip().split("\n")
    while lines:
        last = lines[-1].strip()
        if not last:
            lines.pop()
            continue
        if _TRAILING_JUNK_START.search(last) or _TRAILING_JUNK_CONTAINS.search(last):
            lines.pop()
            continue
        break
    return "\n".join(lines).rstrip()


# ── Public API ─────────────────────────────────────────────────────────────

async def synthesize_answer(question: str, records: list[dict]) -> str:
    """Synthesize a natural language answer from Cypher result records."""
    logger.info("Synthesizing answer via LLM (records=%d)", len(records))

    if not records:
        return "Không tìm thấy thông tin trong cơ sở dữ liệu cấu trúc."

    data_text, note = _prepare_records_for_llm(records)

    system_prompt = (
        "Bạn là trợ lý y khoa AegisHealth. Nhiệm vụ: Đọc hiểu câu hỏi, chọn lọc dữ liệu phù hợp "
        "và trình bày thành câu trả lời tiếng Việt mạch lạc.\n\n"
        "<rules>\n"
        "1. LỌC DỮ LIỆU: Chỉ giữ lại các bản ghi khớp với câu hỏi. Nếu câu hỏi tìm bệnh dựa trên triệu chứng/chế độ ăn, hãy liệt kê các bệnh có chứa yếu tố đó trong dữ liệu.\n"
        "2. KHÔNG SUY DIỄN: CHỈ dùng thông tin có trong dữ liệu. TUYỆT ĐỐI KHÔNG tự giải thích cơ chế, phương pháp chẩn đoán, hay tự đưa ra nhận xét chung.\n"
        "3. ĐỊNH DẠNG NGHIÊM NGẶT: Phải in đậm (**) tên bệnh và tên thuốc. Mọi danh sách (triệu chứng, thuốc, thực phẩm) PHẢI được gạch đầu dòng (-) từng mục một. Tuyệt đối không gộp nhiều mục vào chung một câu văn xuôi.\n"
        "4. Bỏ qua các từ phiên âm vô nghĩa như 'Úc Trác', 'Yan Peng Hui'.\n"
        "5. Dừng trả lời ngay sau mục cuối cùng, KHÔNG thêm lời khuyên y tế ở cuối.\n"
        "</rules>\n\n"
        "<examples>\n"
        "User: ho gà có triệu chứng gì?\n"
        "Data: [{\"Bệnh\": \"Ho gà\", \"Triệu chứng\": [\"ho co thắt\", \"sốt nhẹ\", \"Yan Peng Hui\"]}, "
        "{\"Bệnh\": \"Ho khan mạn tính\", \"Triệu chứng\": [\"ho kéo dài\"]}]\n"
        "Assistant: Bệnh **Ho gà** có các triệu chứng:\n"
        "- Ho co thắt\n"
        "- Sốt nhẹ\n\n"
        "User: tránh ăn [bia, rượu trắng] có thể hỗ trợ điều trị bệnh gì?\n"
        "Data: [{\"Bệnh\": \"Bệnh cơ tim\", \"Không nên ăn\": [\"bia\", \"rượu trắng\", \"chân gà\"]}, "
        "{\"Bệnh\": \"Viêm phổi\", \"Nên ăn\": [\"trái cây\"]}]\n"
        "Assistant: Việc tránh ăn bia, rượu trắng có thể hỗ trợ điều trị các bệnh sau:\n"
        "- **Bệnh cơ tim** (cũng nên kiêng chân gà)\n\n"
        "User: thuốc chữa rối loạn lo âu ở trẻ em?\n"
        "Data: [{\"Bệnh\": \"Rối loạn lo âu ở trẻ em\", \"Thuốc đề xuất\": "
        "[\"Paroxetine hydrochloride\", \"Butyrone hydrochloride\", \"Carbamazepine\"]}]\n"
        "Assistant: Đối với **Rối loạn lo âu ở trẻ em**, các thuốc được đề xuất gồm:\n"
        "- **Paroxetine hydrochloride**\n"
        "- **Butyrone hydrochloride**\n"
        "- **Carbamazepine**\n"
        "</examples>"
    )

    user_prompt = f"Câu hỏi: {question}\n\nDữ liệu:\n{data_text}"
    if note:
        user_prompt += (
            f"\n\nLưu ý: {note} — "
            "chỉ diễn giải dữ liệu được cung cấp, không suy đoán phần bị cắt."
        )

    try:
        client = get_chat_client()
        response = await client.chat.completions.create(
            model=LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=800,
        )
        answer = response.choices[0].message.content.strip()
        answer = _strip_trailing_commentary(answer)
        return answer

    except Exception as e:
        logger.error("synthesize_answer failed — returning safe fallback: %s", e)
        return "Hệ thống gặp lỗi khi tổng hợp câu trả lời. Vui lòng thử lại sau."
