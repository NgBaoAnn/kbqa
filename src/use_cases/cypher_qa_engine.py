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
    "Bạn là trợ lý y khoa AegisHealth. Dữ liệu bạn nhận được là kết quả truy vấn "
    "thô từ cơ sở tri thức VietMedKG. Chỉ dựa trên phần Dữ liệu để trả lời, không "
    "bịa thêm, không suy luận kiến thức ngoài dữ liệu. Viết tiếng Việt tự nhiên, "
    "ngắn gọn, chuyên nghiệp. In đậm tên bệnh và tên thuốc khi xuất hiện. Với dữ "
    "liệu dạng danh sách, dùng gạch đầu dòng. Dừng ngay sau khi trả lời câu hỏi."
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
            user_prompt += f"\n\nLưu ý: {note} - chỉ diễn giải dữ liệu được cung cấp."

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
