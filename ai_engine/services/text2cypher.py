"""Text-to-Cypher Service — LLM fallback khi không có template phù hợp."""

import json
import logging
import os

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME", "qwen2.5:7b")
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT_SECONDS", "60"))

client = AsyncOpenAI(
    base_url=LLM_BASE_URL,
    api_key="ollama",
    timeout=LLM_TIMEOUT,
)

# ── Schema & few-shot examples ─────────────────────────────────────────────

SCHEMA_PROMPT = """
You are a Cypher expert. Convert the user's natural language question into a Cypher query for a Neo4j database.
The database uses the VietMedKG schema:

# Nodes and Properties:
- (d:Disease)
  - disease_name: String (e.g., "Bệnh tiểu đường", "Viêm phổi")
  - disease_description: String
  - disease_category: String
  - disease_cause: String
- (s:Symptom)
  - disease_symptom: String  [all symptoms stored as one blob string per disease]
  - check_method: String
  - people_easy_get: String
- (t:Treatment)
  - cure_method: String
  - cure_department: String
  - cure_probability: String
- (m:Medicine)
  - drug_recommend: String
  - drug_common: String
  - drug_detail: String
- (a:Advice)
  - nutrition_do_eat: String
  - nutrition_not_eat: String
  - nutrition_recommend_meal: String
  - disease_prevention: String

# Relationships:
- (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom)
- (d:Disease)-[:HAS_TREATMENT]->(t:Treatment)
- (d:Disease)-[:IS_PRESCRIBED]->(m:Medicine)
- (d:Disease)-[:HAS_ADVICE]->(a:Advice)
- (d:Disease)-[:IS_LINKED_WITH]->(d2:Disease)

# EXAMPLES:
Question: "triệu chứng của viêm phổi"
Cypher: MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom) WHERE toLower(d.disease_name) CONTAINS toLower('viêm phổi') RETURN d.disease_name AS disease, s.disease_symptom AS symptoms LIMIT 5

Question: "thuốc chữa viêm niệu đạo"
Cypher: MATCH (d:Disease)-[:IS_PRESCRIBED]->(m:Medicine) WHERE toLower(d.disease_name) CONTAINS toLower('viêm niệu đạo') RETURN d.disease_name AS disease, m.drug_common AS common_drugs, m.drug_recommend AS recommended_drugs LIMIT 5

Question: "cách điều trị viêm phổi"
Cypher: MATCH (d:Disease)-[:HAS_TREATMENT]->(t:Treatment) WHERE toLower(d.disease_name) CONTAINS toLower('viêm phổi') RETURN d.disease_name AS disease, t.cure_method AS treatment_method, t.cure_department AS department LIMIT 5

Question: "bệnh đi kèm với viêm phổi"
Cypher: MATCH (d:Disease)-[:IS_LINKED_WITH]->(d2:Disease) WHERE toLower(d.disease_name) CONTAINS toLower('viêm phổi') RETURN d.disease_name AS disease, d2.disease_name AS linked_disease LIMIT 5

Question: "bao nhiêu bệnh trong cơ sở dữ liệu"
Cypher: MATCH (d:Disease) WITH count(d) AS disease_count MATCH (s:Symptom) WITH disease_count, count(s) AS symptom_count MATCH (m:Medicine) WITH disease_count, symptom_count, count(m) AS medicine_count RETURN disease_count, symptom_count, medicine_count

Question: "tiểu đường nên ăn gì"
Cypher: MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice) WHERE toLower(d.disease_name) CONTAINS toLower('tiểu đường') RETURN d.disease_name AS disease, a.nutrition_do_eat AS should_eat, a.nutrition_not_eat AS should_avoid, a.nutrition_recommend_meal AS recommended_meals LIMIT 5

Question: "phòng tránh viêm phổi như thế nào"
Cypher: MATCH (d:Disease)-[:HAS_ADVICE]->(a:Advice) WHERE toLower(d.disease_name) CONTAINS toLower('viêm phổi') RETURN d.disease_name AS disease, a.disease_prevention AS prevention LIMIT 5

Question: "khoa điều trị viêm khớp"
Cypher: MATCH (d:Disease)-[:HAS_TREATMENT]->(t:Treatment) WHERE toLower(d.disease_name) CONTAINS toLower('viêm khớp') RETURN d.disease_name AS disease, t.cure_department AS department LIMIT 5

Question: "bệnh nào có triệu chứng sốt cao"
Cypher: MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom) WHERE toLower(s.disease_symptom) CONTAINS toLower('sốt cao') RETURN d.disease_name AS disease, s.disease_symptom AS symptoms LIMIT 10

Question: "thông tin tổng hợp về bệnh tiểu đường"
Cypher: MATCH (d:Disease) WHERE toLower(d.disease_name) CONTAINS toLower('tiểu đường') OPTIONAL MATCH (d)-[:HAS_SYMPTOM]->(s:Symptom) OPTIONAL MATCH (d)-[:HAS_TREATMENT]->(t:Treatment) OPTIONAL MATCH (d)-[:IS_PRESCRIBED]->(m:Medicine) OPTIONAL MATCH (d)-[:HAS_ADVICE]->(a:Advice) RETURN d.disease_name AS disease, d.disease_description AS description, s.disease_symptom AS symptoms, t.cure_method AS treatment, m.drug_common AS drugs, a.nutrition_do_eat AS should_eat, a.disease_prevention AS prevention LIMIT 5

Question: "symptoms of diabetes"
Cypher: MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom) WHERE toLower(d.disease_name) CONTAINS toLower('tiểu đường') RETURN d.disease_name AS disease, s.disease_symptom AS symptoms LIMIT 5

# IMPORTANT RULES:
1. ALWAYS use WHERE toLower(d.disease_name) CONTAINS toLower(...) for disease name matching.
2. ALWAYS add LIMIT 5 at the end (except count queries).
3. ALWAYS use meaningful AS aliases: disease, symptoms, treatment_method, common_drugs, etc.
4. NEVER return raw Cypher in markdown blocks. Output the query string only.
5. Use OPTIONAL MATCH for profile/summary queries so missing nodes return NULL instead of empty.
6. To search by symptom keyword: WHERE toLower(s.disease_symptom) CONTAINS toLower(...)
"""

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
    "Khoa điều trị",  # cure_department: "Nội khoa, Nội khoa hô hấp" → list
})

_MAX_LIST_ITEMS = 15   # Cap list length to prevent token overflow

# disease_category in VietMedKG is a breadcrumb path from the Chinese source:
# "Bách khoa toàn thư về bệnh, nội khoa, y học hô hấp"
# Strip the encyclopedia prefix so the LLM sees only the meaningful specialty segments.
_CATEGORY_ENCYCLOPEDIA_PREFIX = "bách khoa toàn thư về bệnh"


def _clean_category(value: str) -> str:
    """Strip encyclopedia breadcrumb prefix from disease_category and return specialty segments."""
    parts = [p.strip() for p in value.split(",")]
    filtered = [p for p in parts if p.lower() != _CATEGORY_ENCYCLOPEDIA_PREFIX and p]
    return ", ".join(filtered) if filtered else value


def _split_blob(value: str) -> list[str] | str:
    """Split a comma-separated blob into a list if it has >= 2 items.

    Drug and symptom fields in VietMedKG are stored as comma-separated
    strings (e.g. "Viên nén Metformin, Viên nang Glibenclamide, ...").
    Splitting them into arrays lets the LLM understand the list structure
    instead of treating the whole blob as one drug name.
    """
    items = [x.strip() for x in value.split(",") if x.strip()]
    if len(items) >= 2:
        return items[:_MAX_LIST_ITEMS]
    return value


def _prepare_records_for_llm(records: list[dict]) -> tuple[str, str]:
    """Truncate, localize, and structure records for LLM payload.

    Key improvements over raw JSON:
    - Blob fields (drugs, symptoms, nutrition) are split into proper lists
    - Field keys are translated to Vietnamese labels
    - Total payload is capped to prevent context overflow

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
            # Clean category breadcrumb before further processing
            if label == "Chuyên khoa":
                s = _clean_category(s)
            # Truncate long raw strings before splitting
            s = s[:_MAX_FIELD_CHARS] + "..." if len(s) > _MAX_FIELD_CHARS else s
            # Split blob fields into structured lists
            if label in _BLOB_FIELDS:
                item[label] = _split_blob(s)
            else:
                item[label] = s
        if item:
            localized.append(item)

    # Final safety cap on total characters
    total = sum(len(str(r)) for r in localized)
    if total > _MAX_PAYLOAD_CHARS and localized:
        ratio = _MAX_PAYLOAD_CHARS / total
        for r in localized:
            for label in list(r.keys()):
                v = r[label]
                if isinstance(v, list):
                    # Trim list length proportionally
                    cap = max(3, int(len(v) * ratio))
                    r[label] = v[:cap]
                elif isinstance(v, str):
                    cap = max(50, int(len(v) * ratio))
                    if len(v) > cap:
                        r[label] = v[:cap] + "..."

    return json.dumps(localized, ensure_ascii=False, indent=2), note


# ── Public API ─────────────────────────────────────────────────────────────

async def generate_cypher(question: str) -> str:
    """Generate a Cypher query from a natural language question using LLM."""
    logger.info("Generating Cypher via LLM for: %s", question[:80])

    try:
        response = await client.chat.completions.create(
            model=LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": SCHEMA_PROMPT},
                {"role": "user", "content": f"Write a Cypher query for: {question}"},
            ],
            temperature=0.0,
            max_tokens=300,
        )

        raw = response.choices[0].message.content.strip()

        # Strip markdown fences if LLM ignores instructions
        if raw.startswith("```"):
            lines = raw.split("\n")
            if len(lines) >= 3:
                raw = "\n".join(lines[1:-1])

        logger.info("LLM Cypher: %s", raw.replace("\n", " ")[:120])
        return raw.strip()

    except Exception as e:
        logger.error("Failed to generate Cypher: %s", e)
        raise ValueError(f"LLM generation failed: {e}") from e


async def synthesize_answer(question: str, records: list[dict]) -> str:
    """Synthesize a natural language answer from Cypher result records.

    Applies payload budget before sending to LLM to prevent context overflow.
    """
    logger.info("Synthesizing answer via LLM (records=%d)", len(records))

    if not records:
        return "Không tìm thấy thông tin trong cơ sở dữ liệu cấu trúc."

    data_text, note = _prepare_records_for_llm(records)

    system_prompt = (
        "# VAI TRÒ\n"
        "Bạn là trợ lý y khoa của hệ thống AegisHealth. Nhiệm vụ: diễn giải dữ liệu y khoa "
        "có cấu trúc (JSON) thành câu trả lời tiếng Việt rõ ràng, chính xác cho người dùng.\n\n"
        "# NGUYÊN TẮC BẮT BUỘC (chống bịa thông tin)\n"
        "1. CHỈ dùng thông tin có trong dữ liệu được cung cấp. TUYỆT ĐỐI KHÔNG thêm kiến thức "
        "y khoa bên ngoài, KHÔNG suy diễn, KHÔNG bịa thêm tên thuốc, liều lượng, con số hay "
        "triệu chứng không có trong dữ liệu.\n"
        "2. Giữ NGUYÊN VĂN tên bệnh, tên thuốc, tên thực phẩm như trong dữ liệu — không dịch, "
        "không sửa, không chuẩn hóa.\n"
        "3. Nếu dữ liệu KHÔNG có thông tin được hỏi → trả lời ngắn gọn "
        "'Cơ sở dữ liệu chưa có thông tin này.' Không xin lỗi dài dòng, không bịa.\n"
        "4. KHÔNG tự thêm câu miễn trừ trách nhiệm hay 'hãy tham khảo bác sĩ' — "
        "hệ thống tự bổ sung phần này.\n\n"
        "# CHỌN LỌC DỮ LIỆU (quan trọng — tránh trả lời rời rạc)\n"
        "Dữ liệu có thể chứa NHIỀU bản ghi do tìm kiếm gần đúng. "
        "Chúng được sắp xếp theo độ liên quan giảm dần: BẢN GHI ĐẦU TIÊN khớp nhất với câu hỏi.\n"
        "- Nếu câu hỏi hỏi về MỘT bệnh cụ thể: CHỈ dùng bản ghi khớp nhất với tên bệnh đó; "
        "BỎ QUA bản ghi nói về bệnh khác. TUYỆT ĐỐI không trộn thông tin của nhiều bệnh khác nhau "
        "vào cùng một câu trả lời.\n"
        "- Nếu câu hỏi dạng liệt kê ('bệnh nào...', 'những bệnh...'): mỗi bản ghi là một đáp án — "
        "liệt kê chúng, nhưng bỏ qua bản ghi không thực sự liên quan đến từ khóa.\n"
        "- Bỏ qua các trường rỗng hoặc không liên quan đến câu hỏi.\n"
        "- Nếu hai mẩu dữ liệu mâu thuẫn, ưu tiên bản ghi khớp nhất; không liệt kê cả hai gây rối.\n\n"
        "# ĐỊNH DẠNG\n"
        "- Mở đầu bằng một câu dẫn ngắn tự nhiên, rồi trình bày nội dung.\n"
        "- Dùng gạch đầu dòng (-) cho danh sách (triệu chứng, thuốc, thực phẩm...).\n"
        "- In đậm (**) cho tên bệnh và tên thuốc.\n"
        "- Tối đa 1 emoji y khoa ở đầu câu trả lời (không bắt buộc); không rải emoji.\n"
        "- KHÔNG kết bằng lời chúc hay câu cảm thán thừa.\n\n"
        "# NGÔN NGỮ\n"
        "Trả lời 100% bằng tiếng Việt tự nhiên, chuyên nghiệp và thân thiện vừa phải.\n\n"
        "# VÍ DỤ (chú ý: chỉ dùng bản ghi khớp nhất, bỏ bản ghi lệch chủ đề)\n"
        'Dữ liệu: [{"Bệnh": "Viêm phổi", "Triệu chứng": ["Ho khan", "Sốt cao", "Đau ngực"],'
        ' "Phương pháp chẩn đoán": ["Chụp X-quang phổi", "Xét nghiệm máu"]},'
        ' {"Bệnh": "Viêm phổi do nấm", "Triệu chứng": ["Sốt kéo dài", "Sụt cân"]}]\n'
        'Câu hỏi: "viêm phổi có triệu chứng gì"\n'
        "Trả lời:\n"
        "Theo cơ sở dữ liệu y khoa, **Viêm phổi** có các triệu chứng sau:\n\n"
        "- Ho khan\n"
        "- Sốt cao\n"
        "- Đau ngực\n\n"
        "**Phương pháp chẩn đoán:** Chụp X-quang phổi, Xét nghiệm máu.\n\n"
        "(Giải thích — KHÔNG đưa dòng này vào câu trả lời thật: đã bỏ qua bản ghi "
        "'Viêm phổi do nấm' vì câu hỏi chỉ hỏi về 'Viêm phổi'.)"
    )

    user_prompt = f"Câu hỏi: {question}\n\nDữ liệu:\n{data_text}"
    if note:
        user_prompt += (
            f"\n\nLưu ý: {note} — "
            "chỉ diễn giải dữ liệu được cung cấp, không suy đoán phần bị cắt."
        )

    try:
        response = await client.chat.completions.create(
            model=LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=800,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error("Failed to synthesize answer: %s", e)
        return str(records[:3])
