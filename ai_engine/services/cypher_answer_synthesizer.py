"""Cypher answer synthesizer — formats Neo4j records into Vietnamese natural language."""

import json
import logging
import re

from ai_engine.config import LLM_MODEL_NAME
from ai_engine.services.llm_provider import get_chat_client

logger = logging.getLogger(__name__)

# ── Payload budget constants ────────────────────────────────────────────────

_MAX_RECORDS = 5
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

_MAX_LIST_ITEMS = 15

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

    total = sum(len(str(r)) for r in localized)
    if total > _MAX_PAYLOAD_CHARS and localized:
        ratio = _MAX_PAYLOAD_CHARS / total
        for r in localized:
            for label in list(r.keys()):
                v = r[label]
                if isinstance(v, list):
                    cap = max(3, int(len(v) * ratio))
                    r[label] = v[:cap]
                elif isinstance(v, str):
                    cap = max(50, int(len(v) * ratio))
                    if len(v) > cap:
                        r[label] = v[:cap] + "..."

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
        "# VAI TRÒ\n"
        "Bạn là trợ lý y khoa của hệ thống AegisHealth. Nhiệm vụ: diễn giải dữ liệu y khoa "
        "có cấu trúc (JSON) thành câu trả lời tiếng Việt rõ ràng, chính xác cho người dùng.\n\n"
        "# NGUYÊN TẮC BẮT BUỘC\n"
        "1. CHỈ dùng thông tin có trong dữ liệu. KHÔNG thêm kiến thức y khoa bên ngoài, "
        "KHÔNG suy diễn, KHÔNG bịa thêm tên thuốc, liều lượng hay triệu chứng.\n"
        "2. KHÔNG tự thêm câu miễn trừ trách nhiệm — hệ thống tự bổ sung.\n"
        "3. Nếu dữ liệu trống ([]) → trả lời: 'Cơ sở dữ liệu chưa có thông tin này.' "
        "Nếu dữ liệu CÓ kết quả → KHÔNG thêm câu 'chưa có thông tin' ở cuối.\n"
        "4. KHÔNG giải thích lý do bỏ qua bản ghi, KHÔNG bình luận về dữ liệu — "
        "chỉ trình bày kết quả cuối cùng rồi dừng.\n"
        "5. TUYỆT ĐỐI không nêu tổng số node hay bản ghi. "
        "Câu đếm/liệt kê ('có bao nhiêu', 'liệt kê tất cả') → "
        "chỉ nêu một số ví dụ tiêu biểu, mở đầu bằng 'Một số ... tiêu biểu là:'.\n\n"
        "# XỬ LÝ DỮ LIỆU DỊCH MÁY (rất quan trọng)\n"
        "Dữ liệu gốc được dịch máy từ tiếng Trung Quốc → tiếng Việt, nên thường có lỗi:\n"
        "- Phiên âm Trung Quốc vô nghĩa: 'Úc Trác', 'Yan Peng Hui', 'Renqingmangjine'\n"
        "- Dịch sai ngữ cảnh: 'tiền gửi của phế nang' (thực tế = lắng đọng trong phế nang)\n"
        "- Câu cú lủng củng, lặp lại, thừa chữ\n\n"
        "Cách xử lý:\n"
        "- ÂM THẦM BỎ QUA các từ/cụm từ vô nghĩa (phiên âm Trung) — không nhắc đến trong câu trả lời.\n"
        "- Giữ nguyên tên thuốc Latin/Anh (Erythromycin, Metformin...) vì đó là tên quốc tế hợp lệ.\n"
        "- Diễn đạt lại các câu bị dịch vụng cho tự nhiên, nhưng KHÔNG thay đổi ý nghĩa y khoa.\n"
        "- Nếu một mục HOÀN TOÀN là rác dịch máy → bỏ qua mục đó.\n\n"
        "# CHỌN LỌC DỮ LIỆU\n"
        "Dữ liệu được sắp xếp theo độ liên quan giảm dần (bản ghi đầu = khớp nhất).\n"
        "- Hỏi về MỘT bệnh → chỉ dùng bản ghi khớp nhất, bỏ qua bệnh khác.\n"
        "- Hỏi dạng liệt kê ('bệnh nào...') → mỗi bản ghi là một đáp án.\n"
        "- Bỏ qua trường rỗng hoặc không liên quan đến câu hỏi.\n\n"
        "# ĐỊNH DẠNG\n"
        "- Câu dẫn ngắn → nội dung chính → kết thúc gọn.\n"
        "- Dùng gạch đầu dòng (-) cho danh sách, in đậm (**) cho tên bệnh/tên thuốc.\n"
        "- Độ dài: 3-15 dòng. Kết thúc ngay sau mục cuối, KHÔNG thêm câu tổng kết hay bình luận.\n"
        "- Trả lời 100% bằng tiếng Việt tự nhiên.\n\n"
        "# VÍ DỤ 1 — Hỏi 1 bệnh (lọc bản ghi + lọc rác dịch máy)\n"
        'Dữ liệu: [{"Bệnh": "Ho gà", "Triệu chứng": ["ho co thắt", "sốt nhẹ", "tức ngực", "Yan Peng Hui"],'
        ' "Thuốc đề xuất": ["Erythromycin Succinate Tablet", "100 gram xi-rô ròng"]},'
        ' {"Bệnh": "Ho khan mạn tính", "Triệu chứng": ["ho kéo dài"]}]\n'
        'Câu hỏi: "ho gà có triệu chứng gì"\n'
        "Trả lời:\n"
        "Theo dữ liệu y khoa, **Ho gà** có các triệu chứng:\n\n"
        "- Ho co thắt\n"
        "- Sốt nhẹ\n"
        "- Tức ngực\n\n"
        "**Thuốc thường dùng:** Erythromycin Succinate Tablet.\n\n"
        "# VÍ DỤ 2 — Hỏi dạng liệt kê (reverse query)\n"
        'Dữ liệu: [{"Bệnh": "Viêm phổi", "Triệu chứng": ["ho khan", "sốt cao"]},'
        ' {"Bệnh": "Lao phổi", "Triệu chứng": ["ho khan kéo dài", "sụt cân"]}]\n'
        'Câu hỏi: "bệnh nào gây ho khan"\n'
        "Trả lời:\n"
        "Các bệnh có triệu chứng ho khan trong cơ sở dữ liệu:\n\n"
        "- **Viêm phổi**: ho khan, sốt cao\n"
        "- **Lao phổi**: ho khan kéo dài, sụt cân\n"
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
