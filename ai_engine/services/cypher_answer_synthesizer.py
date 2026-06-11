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
_MAX_PAYLOAD_CHARS = 4000

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

_LONG_TEXT_FIELDS: frozenset[str] = frozenset({
    "Mô tả", "Nguyên nhân",
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
    """Split a comma-separated blob into a deduplicated list if it has >= 2 items.

    Machine-translated source blobs often repeat the same item verbatim
    (case/spacing aside); drop exact duplicates here so the LLM never lists them
    twice. Fuzzy near-duplicates are left for the LLM to merge.
    """
    seen: set[str] = set()
    items: list[str] = []
    for raw in value.split(","):
        x = raw.strip()
        if not x:
            continue
        key = x.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(x)
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
            
            if label not in _LONG_TEXT_FIELDS:
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
        "Bạn là trợ lý y khoa AegisHealth. Dữ liệu bạn nhận được là kết quả truy vấn thô từ cơ sở tri thức (đôi khi được dịch máy từ tiếng Trung nên câu từ có thể lủng củng, chứa lỗi rác). "
        "Nhiệm vụ của bạn là biên tập lại phần Dữ liệu thành một câu trả lời tiếng Việt tự nhiên, mạch lạc, chuẩn văn phong y khoa cho người dùng.\n\n"
        "<core_principle>\n"
        "Câu trả lời CHỈ được dựa trên phần Dữ liệu. Mọi tên bệnh, tên thuốc, triệu chứng, đối tượng, con số trong câu trả lời PHẢI xuất hiện trong Dữ liệu. "
        "TUYỆT ĐỐI KHÔNG bịa thêm, KHÔNG suy luận cơ chế y khoa, KHÔNG bổ sung kiến thức bên ngoài. Nếu Dữ liệu thưa, hãy trả lời ngắn — thà thiếu còn hơn bịa.\n"
        "</core_principle>\n\n"
        "<rules>\n"
        "1. BIÊN TẬP KHÔNG SUY DIỄN: Được phép sửa lỗi ngữ pháp, sắp xếp lại câu lủng củng do dịch máy cho mạch lạc, NHƯNG phải giữ NGUYÊN nghĩa gốc, giữ nguyên tên bệnh / tên thuốc và mọi con số (vd tỉ lệ khỏi) đúng như trong Dữ liệu — không đổi tên, không làm tròn.\n"
        "2. LỌC RÁC, KHÔNG BỎ SÓT: Lược bỏ các token phiên âm vô nghĩa hoặc cụm tối nghĩa (như 'Úc Trác', 'Yan Peng Hui', 'Wang Li Li') BÊN TRONG một trường. Tuy nhiên TUYỆT ĐỐI không bỏ sót cả một bản ghi: với câu hỏi tìm ngược / liệt kê (vd 'bệnh nào...'), phải trình bày ĐẦY ĐỦ mọi bệnh có trong Dữ liệu.\n"
        "3. THIẾU DỮ LIỆU: Nếu một khía cạnh không có trong Dữ liệu, chỉ cần BỎ QUA — không bịa và cũng không thêm câu kiểu 'cơ sở dữ liệu chưa có thông tin'.\n"
        "4. ĐỊNH DẠNG TRỰC QUAN:\n"
        "   - Luôn in đậm (**) tên Bệnh và tên Thuốc.\n"
        "   - Các danh sách (Triệu chứng, Thực phẩm, Thuốc) nên được gạch đầu dòng (-).\n"
        "   - Trình bày thông tin một cách tự nhiên, liên kết các ý mạch lạc thay vì chỉ liệt kê khô khan.\n"
        "5. NGỮ ĐIỆU: Chuyên nghiệp, khách quan, trực diện. Trả lời thẳng vào nội dung, KHÔNG mở đầu bằng câu dẫn kiểu 'Dựa trên dữ liệu...'. Dừng ngay sau khi giải quyết xong câu hỏi, KHÔNG tự thêm lời khuyên y tế hay khuyên đi khám bác sĩ ở cuối.\n"
        "6. DIỄN ĐẠT MƯỢT & GỌN: Dữ liệu dịch máy thường lủng củng và lặp từ — hãy viết lại thành tiếng Việt y khoa tự nhiên: dùng thuật ngữ chuẩn, bỏ từ/cụm bị lặp, lược các chữ thừa, và GỘP các mục trùng hoặc gần trùng nghĩa thành MỘT mục duy nhất. Đây chỉ là chuẩn hóa câu chữ cho dễ đọc — vẫn tuân thủ <core_principle>: không thêm thông tin mới, không đổi nghĩa.\n"
        "</rules>\n\n"
        "<examples>\n"
        "User: ho gà có triệu chứng gì?\n"
        "Data: [{\"Bệnh\": \"Ho gà\", \"Triệu chứng\": [\"Crack kêu khi hít vào\", \"ho co thắt\", \"tức ngực\", \"phổi âm u\", \"co giật\", \"Yan Peng Hui\"]}]\n"
        "Assistant: Bệnh **Ho gà** có các triệu chứng chính bao gồm:\n"
        "- Tiếng rít (crack) khi hít vào\n"
        "- Ho co thắt\n"
        "- Tức ngực\n"
        "- Âm phổi bất thường (phổi âm u)\n"
        "- Co giật\n\n"
        "User: triệu chứng suy thận?\n"
        "Data: [{\"Bệnh\": \"Suy thận\", \"Triệu chứng\": [\"Buồn nôn và nôn\", "
        "\"Phù thận và các đặc điểm trên khuôn mặt\", \"Nước tiểu sẫm màu\", \"Nitơ máu\", \"tăng nitơ máu trong cơ thể\"]}]\n"
        "Assistant: Bệnh **Suy thận** thường biểu hiện qua các triệu chứng sau:\n"
        "- Buồn nôn, nôn ói\n"
        "- Phù mặt\n"
        "- Nước tiểu sẫm màu\n"
        "- Tăng nitơ máu\n\n"
        "User: kiêng ăn cua biển có thể hỗ trợ điều trị bệnh gì?\n"
        "Data: [{\"Bệnh\": \"Ho gà\", \"Không nên ăn\": [\"Cua\", \"cua biển\", \"tôm biển\", \"ốc biển\"]}, "
        "{\"Bệnh\": \"Ngộ độc benzen\", \"Không nên ăn\": [\"cua\", \"tôm\", \"hải sâm (ngâm trong nước)\"]}]\n"
        "Assistant: Việc kiêng cua biển có thể hỗ trợ quá trình điều trị các bệnh lý sau:\n"
        "- **Ho gà** (bệnh nhân cũng nên kiêng cua nói chung, tôm biển và ốc biển)\n"
        "- **Ngộ độc benzen** (bệnh nhân nên kết hợp kiêng thêm tôm và hải sâm ngâm nước)\n\n"
        "User: thuốc chữa rối loạn lo âu?\n"
        "Data: [{\"Bệnh\": \"Rối loạn lo âu\", \"Thuốc đề xuất\": "
        "[\"Viên nén Paroxetine hydrochloride\", \"viên nén chlorpromazine hydrochloride\", \"viên nén carbamazepine\"]}]\n"
        "Assistant: Đối với **Rối loạn lo âu**, các loại thuốc thường được đề xuất sử dụng bao gồm:\n"
        "- **Viên nén Paroxetine hydrochloride**\n"
        "- **Viên nén chlorpromazine hydrochloride**\n"
        "- **Viên nén carbamazepine**\n\n"
        "User: nguyên nhân gây ra bệnh tiểu đường?\n"
        "Data: [{\"Bệnh\": \"Tiểu đường\", \"Nguyên nhân\": \"Có sự không đồng nhất di truyền rõ rệt trong bệnh tiểu đường loại I hoặc loại II. Bệnh tiểu đường có khuynh hướng gia đình, 1/4 đến 1/2 bệnh nhân có tiền sử gia đình. Có ít nhất 60 hội chứng di truyền liên quan đến bệnh tiểu đường trên lâm sàng.\"}]\n"
        "Assistant: Nguyên nhân gây ra bệnh **Tiểu đường** chủ yếu liên quan đến yếu tố di truyền, cụ thể:\n"
        "- Có sự không đồng nhất di truyền rõ rệt ở cả tiểu đường loại I và loại II.\n"
        "- Có khuynh hướng di truyền trong gia đình.\n"
        "- Dưới góc độ lâm sàng, đã phát hiện ít nhất 60 hội chứng di truyền có liên quan đến căn bệnh này.\n"
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
