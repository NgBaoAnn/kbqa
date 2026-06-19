"""Cypher QA engine implemented inside the clean backend."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from domain.qa.cypher_answer import prepare_records_for_llm, strip_trailing_commentary
from domain.qa.cypher_builder import SCHEMA_PROMPT, build_cypher_query
from domain.qa.cypher_safety import sanitize_cypher, validate_cypher
from ports.llm import ILlmProvider
from ports.qa import ICypherQaEngine

logger = logging.getLogger(__name__)

SYNTHESIS_SYSTEM_PROMPT = (
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


class CypherQaEngine(ICypherQaEngine):
    """Generate, validate, execute, and synthesize the Cypher QA path."""

    def __init__(self, llm: ILlmProvider) -> None:
        self._llm = llm

    async def query(
        self,
        *,
        question: str,
        query_type: str | None,
        entity: str | None,
        exact: bool,
        execute_fn: Callable[[str, dict[str, Any] | None], Any],
    ) -> dict[str, Any]:
        """Run the Cypher path and return the legacy-compatible result dict."""
        try:
            cypher, params, used_template = await self._to_cypher(
                query_type=query_type,
                entity=entity,
                exact=exact,
                question=question,
            )
        except Exception as exc:
            logger.error("Cypher generation failed: %s", exc)
            return {"success": False, "fallback": True, "reason": f"generation_failed: {exc}"}

        is_valid, validation_error = validate_cypher(cypher)
        if not is_valid:
            logger.warning("Cypher validation failed: %s", validation_error)
            return {"success": False, "fallback": True, "reason": f"validation_failed: {validation_error}"}

        try:
            cypher = sanitize_cypher(cypher)
        except ValueError as exc:
            logger.error("Cypher sanitization blocked: %s", exc)
            return {
                "success": False,
                "fallback": False,
                "error_code": "CYPHER_GENERATION_FAILED",
                "error_message": str(exc),
            }

        try:
            records = await execute_fn(cypher, params)
        except Exception as exc:
            logger.error("Neo4j execution failed: %s", exc)
            return {"success": False, "fallback": True, "reason": f"execution_failed: {exc}"}

        if not records:
            return {"success": False, "fallback": True, "reason": "no_records"}

        answer = await self._synthesize_answer(question, records)
        return {
            "success": True,
            "answer": answer,
            "records": records,
            "cypher": cypher,
            "used_template": used_template,
        }

    async def _to_cypher(
        self,
        *,
        query_type: str | None,
        entity: str | None,
        exact: bool,
        question: str,
    ) -> tuple[str, dict[str, Any], bool]:
        cypher, params = build_cypher_query(query_type, entity, exact=exact)
        if cypher is not None:
            return cypher, params or {}, True

        raw = await self._llm.chat_completion(
            [
                {"role": "system", "content": SCHEMA_PROMPT},
                {"role": "user", "content": f"Write a Cypher query for: {question}"},
            ],
            temperature=0.0,
            max_tokens=300,
        )
        cypher = raw.strip()
        if cypher.startswith("```"):
            lines = cypher.split("\n")
            cypher = "\n".join(lines[1:-1]) if len(lines) >= 3 else cypher
        return cypher.strip(), {}, False

    async def _synthesize_answer(self, question: str, records: list[dict[str, Any]]) -> str:
        if not records:
            return "Không tìm thấy thông tin trong cơ sở dữ liệu cấu trúc."

        data_text, note = prepare_records_for_llm(records)
        user_prompt = f"Câu hỏi: {question}\n\nDữ liệu:\n{data_text}"
        if note:
            user_prompt += (
                f"\n\nLưu ý: {note} — "
                "chỉ diễn giải dữ liệu được cung cấp, không suy đoán phần bị cắt."
            )

        try:
            answer = await self._llm.chat_completion(
                [
                    {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=800,
            )
            return strip_trailing_commentary(answer.strip())
        except Exception as exc:
            logger.error("Cypher answer synthesis failed: %s", exc)
            return "Hệ thống gặp lỗi khi tổng hợp câu trả lời. Vui lòng thử lại sau."
