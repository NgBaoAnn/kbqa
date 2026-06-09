"""LLM transport — lazy singleton clients for OpenAI-compatible APIs."""

import logging

from openai import AsyncOpenAI

from ai_engine.config import (
    EMBEDDING_BASE_URL,
    LLM_BASE_URL,
    LLM_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

_llm_client: AsyncOpenAI | None = None
_embedding_client: AsyncOpenAI | None = None


def get_chat_client() -> AsyncOpenAI:
    """Return the shared LLM chat client, creating it on first call."""
    global _llm_client
    if _llm_client is None:
        _llm_client = AsyncOpenAI(
            base_url=LLM_BASE_URL,
            api_key="ollama",
            timeout=LLM_TIMEOUT_SECONDS,
        )
    return _llm_client


def get_embedding_client() -> AsyncOpenAI:
    """Return the shared embedding client, creating it on first call."""
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = AsyncOpenAI(
            base_url=EMBEDDING_BASE_URL,
            api_key="ollama",
            timeout=LLM_TIMEOUT_SECONDS,
        )
    return _embedding_client
