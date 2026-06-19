"""Pure preparation helpers for Cypher answer synthesis."""

from __future__ import annotations

import json
import re

MAX_RECORDS = 5
MAX_FIELD_CHARS = 300
MAX_PAYLOAD_CHARS = 4000
MAX_LIST_ITEMS = 5

KEY_LABELS: dict[str, str] = {
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

BLOB_FIELDS = {
    "Triệu chứng",
    "Thuốc đề xuất",
    "Thuốc phổ biến",
    "Chi tiết thuốc",
    "Nên ăn",
    "Không nên ăn",
    "Thực đơn gợi ý",
    "Phòng ngừa",
    "Phương pháp chẩn đoán",
    "Phương pháp điều trị",
    "Khoa điều trị",
}
LONG_TEXT_FIELDS = {"Mô tả", "Nguyên nhân"}
LOW_PRIORITY_FIELDS = {"Chi tiết thuốc", "Thực đơn gợi ý", "Nên ăn", "Không nên ăn", "Phòng ngừa"}
CATEGORY_ENCYCLOPEDIA_PREFIX = "bách khoa toàn thư về bệnh"

TRAILING_JUNK_START = re.compile(
    r"^(?:\*\*[^*]+\*\*\s*)?(Cơ sở dữ liệu chưa có|Hiện tại.{0,10}chưa có|"
    r"Lưu ý[:\s]|Chú ý[:\s]|Chúc bạn|Hãy tham khảo|Nên tham khảo|Bạn nên đến|"
    r"Tuy nhiên.{0,30}(cần|nên|hãy)|Ngoài ra.{0,30}không có|\(Giải thích)",
    re.IGNORECASE,
)
TRAILING_JUNK_CONTAINS = re.compile(
    r"(không được liệt kê|kết quả đầu|bản ghi đầu|không nằm trong)",
    re.IGNORECASE,
)


def prepare_records_for_llm(records: list[dict]) -> tuple[str, str]:
    """Truncate, localize, and structure graph records for LLM synthesis."""
    original_count = len(records)
    truncated = records[:MAX_RECORDS]
    localized = [_localize_record(record) for record in truncated]
    localized = [record for record in localized if record]

    while len(json.dumps(localized, ensure_ascii=False)) > MAX_PAYLOAD_CHARS:
        dropped_any = False
        for record in localized:
            for field in list(record.keys()):
                if field in LOW_PRIORITY_FIELDS:
                    del record[field]
                    dropped_any = True
        if not dropped_any and len(localized) > 1:
            localized.pop()
        elif not dropped_any:
            break

    note = (
        f"(Hiển thị {len(truncated)}/{original_count} kết quả phù hợp nhất)"
        if original_count > MAX_RECORDS
        else ""
    )
    return json.dumps(localized, ensure_ascii=False, indent=2), note


def strip_trailing_commentary(answer: str) -> str:
    """Remove common hallucinated trailing advice from synthesized answers."""
    lines = answer.rstrip().split("\n")
    while lines:
        last = lines[-1].strip()
        if not last:
            lines.pop()
            continue
        if TRAILING_JUNK_START.search(last) or TRAILING_JUNK_CONTAINS.search(last):
            lines.pop()
            continue
        break
    return "\n".join(lines).rstrip()


def _localize_record(record: dict) -> dict:
    item: dict = {}
    for key, value in record.items():
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in {"None", "null", "nan"}:
            continue
        label = KEY_LABELS.get(key, key)
        if label == "Chuyên khoa":
            text = _clean_category(text)
        if label not in LONG_TEXT_FIELDS:
            text = text[:MAX_FIELD_CHARS] + "..." if len(text) > MAX_FIELD_CHARS else text
        item[label] = _split_blob(text) if label in BLOB_FIELDS else text
    return item


def _clean_category(value: str) -> str:
    parts = [part.strip() for part in value.split(",")]
    filtered = [part for part in parts if part and part.lower() != CATEGORY_ENCYCLOPEDIA_PREFIX]
    return ", ".join(filtered) if filtered else value


def _split_blob(value: str) -> list[str] | str:
    seen: set[str] = set()
    items: list[str] = []
    for raw in value.split(","):
        item = raw.strip()
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(item)
    return items[:MAX_LIST_ITEMS] if len(items) >= 2 else value
