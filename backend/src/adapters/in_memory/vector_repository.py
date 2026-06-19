"""In-Memory Vector Repository — Test double for IVectorRepository.

Returns pre-configured answers for testing the QA pipeline without
Qdrant or LightRAG.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from ports.vector import IVectorRepository


class _InMemoryChunkStream:
    def __init__(self, answer: str, retrieval_context: dict[str, Any]) -> None:
        self._answer = answer
        self.retrieval_context = retrieval_context

    def __aiter__(self):
        return self._iter()

    async def _iter(self) -> AsyncIterator[str]:
        for word in self._answer.split():
            yield word + " "


class InMemoryVectorRepository(IVectorRepository):
    """In-memory implementation of IVectorRepository for testing.

    Pre-populate via ``seed_answer()`` before running tests.
    Answers are returned by matching question substrings.
    """

    def __init__(self) -> None:
        self._answers: dict[str, dict[str, Any]] = {}
        self._default_answer: str = "Xin lỗi, không tìm thấy thông tin."
        self._healthy: bool = True

    # ── Seeding helpers ───────────────────────────────────────────────────

    def seed_answer(self, question_contains: str, answer: str, **extra: Any) -> None:
        """Register an answer that will be returned when the question contains the given substring."""
        self._answers[question_contains.lower()] = {
            "answer": answer,
            "mode": extra.get("mode", "naive"),
            "success": True,
            **extra,
        }

    def set_default_answer(self, answer: str) -> None:
        self._default_answer = answer

    # ── IVectorRepository implementation ──────────────────────────────────

    async def query(
        self,
        question: str,
        *,
        mode: str = "naive",
        only_need_context: bool = False,
    ) -> dict[str, Any]:
        if not self._healthy:
            return {"answer": "", "mode": mode, "success": False, "error": "unhealthy"}

        q_lower = question.lower()
        for keyword, result in self._answers.items():
            if keyword in q_lower:
                return dict(result)

        return {
            "answer": self._default_answer,
            "mode": mode,
            "success": True,
        }

    async def query_stream(
        self,
        question: str,
        *,
        mode: str = "naive",
    ) -> tuple[str, AsyncIterator[str]]:
        result = await self.query(question, mode=mode)
        answer = result.get("answer", "")
        retrieval_context = {
            key: result[key]
            for key in ("entities", "relationships", "chunks")
            if result.get(key)
        }
        return mode, _InMemoryChunkStream(answer, retrieval_context)

    async def health_check(self) -> dict[str, Any]:
        return {
            "lightrag": "initialized" if self._healthy else "error",
            "query_mode": "naive",
            "llm_server": "available" if self._healthy else "unavailable",
            "embedding_server": "available" if self._healthy else "unavailable",
        }
