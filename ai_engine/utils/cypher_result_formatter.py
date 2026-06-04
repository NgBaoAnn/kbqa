"""Cypher Result Formatter — Transforms structured Neo4j records into friendly Markdown."""

import random
from ai_engine.utils.ui_constants import (
    GREETINGS_SYMPTOMS,
    GREETINGS_MEDICINE,
    GREETINGS_TREATMENT,
    GREETINGS_ADVICE,
    GREETINGS_PREVENTION,
    GREETINGS_DEPARTMENT,
    GREETINGS_PROFILE,
    GREETINGS_LINKED,
    GREETINGS_FIND_BY_SYMPTOM,
    GREETINGS_FIND_BY_MEDICINE,
    GREETINGS_FIND_BY_NUTRITION_AVOID,
    GREETINGS_FIND_BY_NUTRITION_EAT,
    GREETINGS_FIND_BY_PREVENTION,
)

def format_cypher_result_as_text(
    query_type: str,
    entity: str | None,
    records: list[dict],
) -> str:
    """Chuyển kết quả Cypher thành văn bản tiếng Việt Markdown thân thiện."""
    if not records:
        return f"Không tìm thấy thông tin về '{entity}' trong cơ sở dữ liệu."

    formatters = {
        "symptoms":              _fmt_symptoms,
        "medicine":              _fmt_medicine,
        "treatment":             _fmt_treatment,
        "advice":                _fmt_advice,
        "prevention":            _fmt_prevention,
        "department":            _fmt_department,
        "profile":               _fmt_profile,
        "linked_diseases":       _fmt_linked_diseases,
        "count":                 _fmt_count,
        "count_by_type":         _fmt_count_by_type,
        "find_by_symptom":       _fmt_find_by_symptom,
        "find_by_medicine":      _fmt_find_by_medicine,
        "find_by_nutrition_avoid": _fmt_find_by_nutrition_avoid,
        "find_by_nutrition_eat": _fmt_find_by_nutrition_eat,
        "find_by_prevention":    _fmt_find_by_prevention,
        "linked_with_info":      _fmt_linked_with_info,
    }

    formatter = formatters.get(query_type, _fmt_generic)
    return formatter(entity, records)


def _safe(value: object) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    return "" if s in ("None", "null", "nan") else s


def _fmt_generic(entity: str | None, records: list[dict]) -> str:
    return f"Đã tìm thấy {len(records)} kết quả liên quan đến {entity}."


def _fmt_symptoms(entity: str | None, records: list[dict]) -> str:
    label = entity or records[0].get("disease", "")
    greeting = random.choice(GREETINGS_SYMPTOMS).format(label=label)
    
    lines = [f"{greeting}\n"]
    for r in records:
        disease = _safe(r.get("disease"))
        if disease and len(records) > 1:
            lines.append(f"### 🩺 {disease}")
        symptoms = _safe(r.get("symptoms"))
        if symptoms:
            lines.append(f"- **Triệu chứng chính:** {symptoms}")
        check = _safe(r.get("check_method"))
        if check:
            lines.append(f"- **Cách chẩn đoán:** {check}")
        risk = _safe(r.get("risk_group"))
        if risk:
            lines.append(f"- **Đối tượng nguy cơ:** {risk}")
        lines.append("")
    return "\n".join(lines).strip()


def _fmt_medicine(entity: str | None, records: list[dict]) -> str:
    label = entity or records[0].get("disease", "")
    greeting = random.choice(GREETINGS_MEDICINE).format(label=label)
    
    lines = [f"{greeting}\n"]
    for r in records:
        disease = _safe(r.get("disease"))
        if disease and len(records) > 1:
            lines.append(f"### 💊 {disease}")
        rec = _safe(r.get("recommended_drugs"))
        if rec:
            lines.append(f"- **Thuốc đề xuất:** {rec}")
        common = _safe(r.get("common_drugs"))
        if common:
            lines.append(f"- **Thuốc phổ biến:** {common}")
        detail = _safe(r.get("drug_detail"))
        if detail:
            lines.append(f"- **Chi tiết:** {detail[:200]}...")
        lines.append("")
    return "\n".join(lines).strip()


def _fmt_treatment(entity: str | None, records: list[dict]) -> str:
    label = entity or records[0].get("disease", "")
    greeting = random.choice(GREETINGS_TREATMENT).format(label=label)
    
    lines = [f"{greeting}\n"]
    for r in records:
        disease = _safe(r.get("disease"))
        if disease and len(records) > 1:
            lines.append(f"### 🏥 {disease}")
        method = _safe(r.get("treatment_method"))
        if method:
            lines.append(f"- **Phương pháp điều trị:** {method}")
        dept = _safe(r.get("department"))
        if dept:
            lines.append(f"- **Khoa điều trị phù hợp:** {dept}")
        rate = _safe(r.get("cure_rate"))
        if rate:
            lines.append(f"- **Tỉ lệ khỏi bệnh:** {rate}")
        lines.append("")
    return "\n".join(lines).strip()


def _fmt_advice(entity: str | None, records: list[dict]) -> str:
    label = entity or records[0].get("disease", "")
    greeting = random.choice(GREETINGS_ADVICE).format(label=label)
    
    lines = [f"{greeting}\n"]
    for r in records:
        disease = _safe(r.get("disease"))
        if disease and len(records) > 1:
            lines.append(f"### 🥗 {disease}")
        eat = _safe(r.get("should_eat"))
        if eat:
            lines.append(f"- **Nên ăn:** {eat}")
        avoid = _safe(r.get("should_avoid"))
        if avoid:
            lines.append(f"- **Cần kiêng/Hạn chế:** {avoid}")
        meal = _safe(r.get("recommended_meals"))
        if meal:
            lines.append(f"- **Thực đơn gợi ý:** {meal}")
        prev = _safe(r.get("prevention"))
        if prev:
            lines.append(f"- **Phòng tránh chung:** {prev}")
        lines.append("")
    return "\n".join(lines).strip()


def _fmt_prevention(entity: str | None, records: list[dict]) -> str:
    label = entity or records[0].get("disease", "")
    greeting = random.choice(GREETINGS_PREVENTION).format(label=label)
    
    lines = [f"{greeting}\n"]
    for r in records:
        disease = _safe(r.get("disease"))
        if disease and len(records) > 1:
            lines.append(f"### 🛡️ {disease}")
        prev = _safe(r.get("prevention"))
        if prev:
            lines.append(f"- {prev}")
        lines.append("")
    if len(lines) == 1:
        return f"Hiện chưa có thông tin phòng tránh chi tiết cho bệnh **{label}**."
    return "\n".join(lines).strip()


def _fmt_department(entity: str | None, records: list[dict]) -> str:
    label = entity or records[0].get("disease", "")
    greeting = random.choice(GREETINGS_DEPARTMENT).format(label=label)
    
    depts = sorted({_safe(r.get("department")) for r in records if r.get("department")})
    if depts:
        return f"{greeting} **{', '.join(depts)}**."
    return f"Không tìm thấy khoa điều trị cho bệnh **{label}**."


def _fmt_profile(entity: str | None, records: list[dict]) -> str:
    label = entity or records[0].get("disease", "")
    greeting = random.choice(GREETINGS_PROFILE).format(label=label)
    
    lines = [f"{greeting}\n"]
    for r in records:
        disease = _safe(r.get("disease")) or label or "N/A"
        lines.append(f"### 📋 {disease}\n")
        
        for field, label_name in [
            ("description",      "Mô tả"),
            ("category",         "Chuyên khoa"),
            ("cause",            "Nguyên nhân"),
            ("symptoms",         "Triệu chứng"),
            ("check_method",     "Phương pháp chẩn đoán"),
            ("risk_group",       "Đối tượng dễ mắc"),
            ("treatment_method", "Phương pháp điều trị"),
            ("department",       "Khoa điều trị"),
            ("cure_rate",        "Tỉ lệ khỏi bệnh"),
            ("recommended_drugs","Thuốc đề xuất"),
            ("common_drugs",     "Thuốc phổ biến"),
            ("should_eat",       "Khuyên dùng (Nên ăn)"),
            ("should_avoid",     "Chống chỉ định (Cần kiêng)"),
            ("prevention",       "Phòng tránh"),
        ]:
            val = _safe(r.get(field))
            if val:
                lines.append(f"- **{label_name}:** {val}")
        lines.append("")
    return "\n".join(lines).strip()


def _fmt_linked_diseases(entity: str | None, records: list[dict]) -> str:
    label = entity or records[0].get("disease", "")
    diseases = [_safe(r.get("linked_disease")) for r in records if r.get("linked_disease")]
    if not diseases:
        return f"Không tìm thấy dữ liệu về các bệnh liên quan đến **{label}**."
    
    greeting = random.choice(GREETINGS_LINKED).format(label=label)
    items = "\n".join(f"- {d}" for d in diseases)
    return f"{greeting}\n\n{items}"


def _fmt_count(_entity, records: list[dict]) -> str:
    if not records:
        return "Không có thông tin thống kê."
    r = records[0]
    return (
        f"📊 **Thống kê Cơ sở dữ liệu AegisHealth:**\n\n"
        f"- **Bệnh lý (Disease):** {r.get('disease_count', 'N/A')}\n"
        f"- **Triệu chứng (Symptom):** {r.get('symptom_count', 'N/A')}\n"
        f"- **Thuốc (Medicine):** {r.get('medicine_count', 'N/A')}\n"
        f"- **Phương pháp điều trị (Treatment):** {r.get('treatment_count', 'N/A')}\n"
        f"- **Lời khuyên (Advice):** {r.get('advice_count', 'N/A')}"
    )


def _fmt_count_by_type(_entity, records: list[dict]) -> str:
    if not records:
        return "Không có thông tin thống kê."
    r = records[0]
    return f"Tổng số bản ghi loại **{r.get('node_type', '')}**: {r.get('total', 'N/A')}"


def _fmt_find_by_symptom(entity: str | None, records: list[dict]) -> str:
    label = entity or records[0].get("symptoms", "")
    diseases = [_safe(r.get("disease")) for r in records if r.get("disease")]
    if not diseases:
        return f"Không tìm thấy bệnh nào có triệu chứng **'{label}'**."
        
    greeting = random.choice(GREETINGS_FIND_BY_SYMPTOM).format(label=label)
    items = "\n".join(f"- {d}" for d in diseases)
    return f"{greeting}\n\n{items}"


def _fmt_find_by_medicine(entity: str | None, records: list[dict]) -> str:
    label = entity or records[0].get("matched_common", "")
    if not records:
        return f"Không tìm thấy bệnh nào dùng thuốc **'{label}'**."
        
    greeting = random.choice(GREETINGS_FIND_BY_MEDICINE).format(label=label)
    lines = [f"{greeting}\n"]
    for r in records:
        disease = _safe(r.get("disease"))
        if not disease:
            continue
        drug = _safe(r.get("matched_common")) or _safe(r.get("matched_recommend"))
        if drug:
            lines.append(f"- **{disease}**: {drug[:120]}...")
        else:
            lines.append(f"- **{disease}**")
    return "\n".join(lines).strip() if len(lines) > 1 else f"Không tìm thấy bệnh nào dùng thuốc **'{label}'**."


def _fmt_find_by_nutrition_avoid(entity: str | None, records: list[dict]) -> str:
    label = entity or ""
    diseases = [_safe(r.get("disease")) for r in records if r.get("disease")]
    if not diseases:
        return f"Không tìm thấy bệnh nào cần kiêng **'{label}'**."
        
    greeting = random.choice(GREETINGS_FIND_BY_NUTRITION_AVOID).format(label=label)
    items = "\n".join(f"- {d}" for d in diseases)
    return f"{greeting}\n\n{items}"


def _fmt_find_by_nutrition_eat(entity: str | None, records: list[dict]) -> str:
    label = entity or ""
    diseases = [_safe(r.get("disease")) for r in records if r.get("disease")]
    if not diseases:
        return f"Không tìm thấy bệnh nào nên bổ sung **'{label}'**."
        
    greeting = random.choice(GREETINGS_FIND_BY_NUTRITION_EAT).format(label=label)
    items = "\n".join(f"- {d}" for d in diseases)
    return f"{greeting}\n\n{items}"


def _fmt_find_by_prevention(entity: str | None, records: list[dict]) -> str:
    label = entity or ""
    diseases = [_safe(r.get("disease")) for r in records if r.get("disease")]
    if not diseases:
        return f"Không tìm thấy thông tin bệnh nào được phòng ngừa bằng **'{label}'**."
        
    greeting = random.choice(GREETINGS_FIND_BY_PREVENTION).format(label=label)
    items = "\n".join(f"- {d}" for d in diseases)
    return f"{greeting}\n\n{items}"


def _fmt_linked_with_info(entity: str | None, records: list[dict]) -> str:
    label = entity or records[0].get("source_disease", "")
    lines = [f"### 🔗 Bệnh liên quan đến **{label}** và thông tin chi tiết:\n"]
    has_data = False
    for r in records:
        linked = _safe(r.get("linked_disease"))
        if not linked:
            continue
        has_data = True
        lines.append(f"**{linked}**")
        symp = _safe(r.get("linked_symptoms"))
        if symp:
            lines.append(f"  - Triệu chứng: {symp}")
        treat = _safe(r.get("linked_treatment"))
        if treat:
            lines.append(f"  - Điều trị: {treat}")
        dept = _safe(r.get("linked_department"))
        if dept:
            lines.append(f"  - Chuyên khoa: {dept}")
        lines.append("")
        
    if not has_data:
        return f"Không tìm thấy bệnh liên quan đến **{label}**."
    return "\n".join(lines).strip()
