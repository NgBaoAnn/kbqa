"""Ollama LLM Provider Adapter — implements ILlmProvider + IEmbeddingProvider.

Wraps the OpenAI-compatible Ollama/vLLM API to provide LLM
chat completion and embedding operations.

Extracted and refactored from ai_engine/services/llm_provider.py
and ai_engine/services/lightrag_llm_adapter.py.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from ports.llm import IEmbeddingProvider, ILlmProvider

logger = logging.getLogger(__name__)


class OllamaLlmProvider(ILlmProvider):
    """Production LLM adapter for Ollama/vLLM OpenAI-compatible API.

    Args:
        base_url: OpenAI-compatible API base URL (e.g. 'http://localhost:11434/v1').
        model_name: Model to use for chat completions (e.g. 'qwen2.5:14b').
        timeout_seconds: HTTP request timeout.
    """

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434/v1",
        model_name: str = "qwen2.5:14b",
        timeout_seconds: int = 60,
    ) -> None:
        self._base_url = base_url
        self._model_name = model_name
        self._timeout = timeout_seconds
        self._client = None

    def _get_client(self):
        """Lazy singleton client."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI  # type: ignore[import]
            except ImportError as exc:
                from domain.shared.errors import InfrastructureError
                raise InfrastructureError(
                    "openai package is not installed. Run: pip install openai"
                ) from exc
            self._client = AsyncOpenAI(
                base_url=self._base_url,
                api_key="ollama",  # Ollama ignores the key
                timeout=self._timeout,
            )
        return self._client

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> str:
        """Send a chat completion request and return the full response text."""
        client = self._get_client()
        try:
            response = await client.chat.completions.create(
                model=self._model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            result = response.choices[0].message.content or ""
            logger.debug(
                "OllamaLlmProvider.chat_completion: model=%s, tokens=%s",
                self._model_name,
                response.usage.total_tokens if response.usage else "unknown",
            )
            return result
        except Exception as exc:
            from domain.shared.errors import InfrastructureError
            raise InfrastructureError(f"LLM call failed: {exc}") from exc

    async def chat_completion_stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Stream a chat completion response token by token."""
        client = self._get_client()
        try:
            response = await client.chat.completions.create(
                model=self._model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
        except Exception as exc:
            from domain.shared.errors import InfrastructureError
            raise InfrastructureError(f"LLM stream failed: {exc}") from exc

        async def _stream() -> AsyncIterator[str]:
            async for chunk in response:
                if not getattr(chunk, "choices", None):
                    continue
                delta = getattr(chunk.choices[0], "delta", None)
                content = getattr(delta, "content", None) if delta else None
                if content:
                    yield content

        return _stream()

    async def check_availability(self) -> bool:
        """Check if the LLM service is reachable."""
        try:
            result = await self.chat_completion(
                [{"role": "user", "content": "Say 'ok'."}],
                max_tokens=5,
            )
            return bool(result.strip())
        except Exception:
            return False


class OllamaEmbeddingProvider(IEmbeddingProvider):
    """Production embedding adapter for Ollama/vLLM OpenAI-compatible API.

    Args:
        base_url: OpenAI-compatible API base URL.
        model_name: Embedding model (e.g. 'bge-m3').
        embedding_dim: Expected embedding dimension (used for validation).
        timeout_seconds: HTTP request timeout.
    """

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434/v1",
        model_name: str = "bge-m3",
        embedding_dim: int = 1024,
        timeout_seconds: int = 60,
    ) -> None:
        self._base_url = base_url
        self._model_name = model_name
        self._embedding_dim = embedding_dim
        self._timeout = timeout_seconds
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI  # type: ignore[import]
            except ImportError as exc:
                from domain.shared.errors import InfrastructureError
                raise InfrastructureError(
                    "openai package is not installed. Run: pip install openai"
                ) from exc
            self._client = AsyncOpenAI(
                base_url=self._base_url,
                api_key="ollama",
                timeout=self._timeout,
            )
        return self._client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts."""
        if not texts:
            return []
        client = self._get_client()
        try:
            response = await client.embeddings.create(
                model=self._model_name,
                input=texts,
            )
            embeddings = [item.embedding for item in response.data]

            # Validate dimension
            if embeddings and len(embeddings[0]) != self._embedding_dim:
                logger.warning(
                    "Embedding dimension mismatch: expected %d, got %d. "
                    "Update EMBEDDING_DIM in your .env.",
                    self._embedding_dim,
                    len(embeddings[0]),
                )
            return embeddings
        except Exception as exc:
            from domain.shared.errors import InfrastructureError
            raise InfrastructureError(f"Embedding call failed: {exc}") from exc

    async def check_availability(self) -> bool:
        """Check if the embedding service is reachable."""
        try:
            result = await self.embed(["test"])
            return len(result) == 1 and len(result[0]) == self._embedding_dim
        except Exception:
            return False
