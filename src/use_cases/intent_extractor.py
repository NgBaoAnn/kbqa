"""LLM-backed intent extraction through the LLM port."""

from __future__ import annotations

import json
import logging

from domain.qa.intent_classifier import VALID_QUERY_TYPES, clean_entity
from ports.llm import ILlmProvider
from ports.qa import IIntentExtractor

logger = logging.getLogger(__name__)

INTENT_SYSTEM_PROMPT = """\
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


class LlmIntentExtractor(IIntentExtractor):
    """Use case service for structured intent extraction via ``ILlmProvider``."""

    def __init__(self, llm: ILlmProvider) -> None:
        self._llm = llm

    async def extract_intent(self, question: str) -> tuple[str | None, str | None]:
        """Return ``(query_type, entity)``; failures degrade to regex fallback."""
        try:
            raw = await self._llm.chat_completion(
                [
                    {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                    {"role": "user", "content": question},
                ],
                temperature=0.0,
                max_tokens=160,
            )
            raw = raw.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(lines[1:-1]) if len(lines) >= 3 else raw

            parsed = json.loads(raw)
            q_type = parsed.get("query_type") or "unknown"
            if q_type not in VALID_QUERY_TYPES:
                q_type = None

            entity_raw = parsed.get("entity") or None
            entity = clean_entity(str(entity_raw)) if entity_raw else None
            logger.info("LLM intent: type=%s entity=%r", q_type, entity)
            return q_type, entity
        except Exception as exc:
            logger.warning("LLM intent extraction failed: %s", exc)
            return None, None
