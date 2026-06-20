"""In-Memory LLM Provider — Test double for ILlmProvider.

Returns pre-configured responses for testing without Ollama/vLLM.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from ports.llm import IEmbeddingProvider, ILlmProvider


class InMemoryLlmProvider(ILlmProvider):
    """In-memory implementation of ILlmProvider for testing.

    Pre-populate via ``set_response()`` or ``set_responses()`` to
    control what the LLM "responds" in tests.
    """

    def __init__(self) -> None:
        self._responses: list[str] = []
        self._default_response: str = "Đây là câu trả lời mặc định từ LLM."
        self._available: bool = True
        self._call_count: int = 0
        self._call_log: list[list[dict[str, str]]] = []

    # ── Seeding helpers ───────────────────────────────────────────────────

    def set_response(self, response: str) -> None:
        """Set a single response that will be returned for every call."""
        self._responses = [response]

    def set_responses(self, responses: list[str]) -> None:
        """Queue multiple responses (consumed in order, last one repeats)."""
        self._responses = list(responses)

    def set_available(self, available: bool) -> None:
        self._available = available

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def call_log(self) -> list[list[dict[str, str]]]:
        return list(self._call_log)

    # ── ILlmProvider implementation ───────────────────────────────────────

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> str:
        if not self._available:
            raise RuntimeError("InMemoryLLM: service unavailable")

        self._call_count += 1
        self._call_log.append(messages)

        if self._responses:
            # Pop first response, but keep last one for repeat calls
            if len(self._responses) > 1:
                return self._responses.pop(0)
            return self._responses[0]

        return self._default_response

    async def chat_completion_stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        full_response = await self.chat_completion(
            messages, temperature=temperature, max_tokens=max_tokens
        )

        async def _stream() -> AsyncIterator[str]:
            for word in full_response.split():
                yield word + " "

        return _stream()

    async def check_availability(self) -> bool:
        return self._available


class InMemoryEmbeddingProvider(IEmbeddingProvider):
    """In-memory embedding provider that returns fixed-dimension zero vectors."""

    def __init__(self, dim: int = 1024) -> None:
        self._dim = dim
        self._available = True

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not self._available:
            raise RuntimeError("InMemoryEmbedding: service unavailable")
        # Return zero vectors (tests shouldn't depend on actual embeddings)
        return [[0.0] * self._dim for _ in texts]

    async def check_availability(self) -> bool:
        return self._available
