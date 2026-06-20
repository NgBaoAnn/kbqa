"""Pure QA pipeline types and routing policy.

The domain layer owns the language of QA routing but performs no I/O.  Use
cases execute the returned route through graph/vector/LLM ports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.qa.intent_classifier import FIND_BY_TYPES

# ── Engine constants ──────────────────────────────────────────────────────
ENGINE_CYPHER = "cypher_direct"
ENGINE_LIGHTRAG = "lightrag"

# ── User-facing error messages ────────────────────────────────────────────
MSG_INVALID_QUESTION = "Vui lòng nhập câu hỏi hợp lệ."
MSG_MODEL_UNAVAILABLE = "Dịch vụ AI tạm thời không khả dụng. Vui lòng thử lại sau."
MSG_INVALID_MODE = "Chế độ truy vấn không hợp lệ."
MSG_GENERATION_FAILED = "Xin lỗi, tôi chưa hiểu câu hỏi. Bạn có thể diễn đạt lại được không?"
MSG_SYSTEM_ERROR = "Hệ thống đang gặp sự cố. Vui lòng thử lại sau."
MSG_TIMEOUT = "Xử lý mất quá lâu. Vui lòng thử câu hỏi ngắn hơn."
MSG_NO_DATA = "Không tìm thấy thông tin về chủ đề này trong cơ sở dữ liệu."
MSG_EMPTY_ANSWER = "Không tìm thấy thông tin về chủ đề này trong cơ sở dữ liệu y tế."


@dataclass
class PipelineResult:
    """Structured result from the application QA pipeline."""

    status: str                                  # "success" | "error"
    answer: str
    response_type: str                           # "text" | "disambiguation" | "warning"
    data: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None

    @property
    def is_success(self) -> bool:
        return self.status == "success"


@dataclass(frozen=True)
class PipelineRouteDecision:
    """Pure route decision shared by normal and streaming QA use cases."""

    path: str
    mode: str | None = None
    query_type: str | None = None
    entity: str | None = None
    exact: bool = False
    variants: list[str] = field(default_factory=list)


class QAPipeline:
    """Pure QA routing policy.

    The application layer supplies extracted intent and KG disambiguation facts.
    This module only decides which path should be executed next.
    """

    def __init__(
        self,
        *,
        disable_cypher_path: bool = False,
        default_lightrag_mode: str = "naive",
    ) -> None:
        self._disable_cypher = disable_cypher_path
        self._default_mode = default_lightrag_mode

    def route_question(
        self,
        *,
        mode: str | None,
        query_type: str | None,
        entity: str | None,
        canonical_entity: str | None = None,
        variants: list[str] | None = None,
    ) -> PipelineRouteDecision:
        """Return the route once use cases have gathered all external facts."""
        if self._disable_cypher or mode:
            return PipelineRouteDecision(path="lightrag", mode=mode or self._default_mode)

        if query_type in FIND_BY_TYPES:
            if not entity:
                return PipelineRouteDecision(path="lightrag", mode=self._default_mode)
            return PipelineRouteDecision(
                path="cypher",
                query_type=query_type,
                entity=entity,
                exact=False,
            )

        if not entity:
            return PipelineRouteDecision(path="lightrag", mode=self._default_mode)

        variants = variants or []
        if not variants:
            return PipelineRouteDecision(path="lightrag", mode=self._default_mode)

        if canonical_entity is None:
            return PipelineRouteDecision(
                path="disambiguation",
                entity=entity,
                variants=variants,
            )

        return PipelineRouteDecision(
            path="cypher",
            query_type=query_type,
            entity=canonical_entity,
            exact=True,
        )
