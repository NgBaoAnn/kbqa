"""Port: LLM Provider.

Abstracts all LLM interactions (chat completions, streaming).
Adapters: OllamaLlmProvider, (future) vLLMLlmProvider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class ILlmProvider(ABC):
    """Port for LLM chat completion interactions."""

    @abstractmethod
    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> str:
        """Send a chat completion request and return the full response text.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            temperature: Sampling temperature (0.0 = deterministic).
            max_tokens: Maximum tokens in the response.

        Returns:
            The assistant's response text.

        Raises:
            InfrastructureError: If the LLM service is unavailable.
        """
        ...

    @abstractmethod
    async def chat_completion_stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Stream a chat completion response token by token.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in the response.

        Yields:
            Individual tokens/chunks as strings.

        Raises:
            InfrastructureError: If the LLM service is unavailable.
        """
        ...

    @abstractmethod
    async def check_availability(self) -> bool:
        """Check if the LLM service is reachable.

        Returns:
            True if the service responds successfully.
        """
        ...


class IEmbeddingProvider(ABC):
    """Port for text embedding generation."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts.

        Args:
            texts: List of strings to embed.

        Returns:
            List of embedding vectors (each a list of floats).

        Raises:
            InfrastructureError: If the embedding service is unavailable.
        """
        ...

    @abstractmethod
    async def check_availability(self) -> bool:
        """Check if the embedding service is reachable."""
        ...
