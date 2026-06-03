"""LLM Service — Ollama/vLLM interaction via OpenAI-compatible API.

Provides wrapper functions that conform to LightRAG's expected signatures
for LLM inference and embedding generation.
"""

import asyncio
import logging
from typing import Any

import numpy as np
from openai import AsyncOpenAI

from ai_engine.config import (
    EMBEDDING_BASE_URL,
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    LLM_BASE_URL,
    LLM_MODEL_NAME,
    LLM_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

# ── Singleton clients ─────────────────────────────────────────────────────
_llm_client: AsyncOpenAI | None = None
_embedding_client: AsyncOpenAI | None = None


def _get_llm_client() -> AsyncOpenAI:
    """Get or create the LLM client (lazy singleton)."""
    global _llm_client
    if _llm_client is None:
        _llm_client = AsyncOpenAI(
            base_url=LLM_BASE_URL,
            api_key="ollama",  # Ollama doesn't require a real API key
            timeout=LLM_TIMEOUT_SECONDS,
        )
    return _llm_client


def _get_embedding_client() -> AsyncOpenAI:
    """Get or create the Embedding client (lazy singleton)."""
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = AsyncOpenAI(
            base_url=EMBEDDING_BASE_URL,
            api_key="ollama",
            timeout=LLM_TIMEOUT_SECONDS,
        )
    return _embedding_client


# ── LLM Function (for LightRAG) ──────────────────────────────────────────


async def llm_model_func(
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list[dict[str, str]] | None = None,
    keyword_extraction: bool = False,
    **kwargs: Any,
) -> str:
    """Call the LLM via OpenAI-compatible API.

    This function conforms to LightRAG's expected LLM function signature.

    Args:
        prompt: The user message / query.
        system_prompt: Optional system prompt to set context.
        history_messages: Optional conversation history.
        keyword_extraction: If True, request concise keyword-style output.
        **kwargs: Additional arguments (ignored for compatibility).

    Returns:
        The LLM's text response.
    """
    client = _get_llm_client()

    messages: list[dict[str, str]] = []

    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    if history_messages:
        messages.extend(history_messages)

    messages.append({"role": "user", "content": prompt})

    try:
        response = await client.chat.completions.create(
            model=LLM_MODEL_NAME,
            messages=messages,
            temperature=0.1 if keyword_extraction else 0.3,
            max_tokens=2048,
        )
        result = response.choices[0].message.content or ""
        logger.debug(
            "LLM response received (model=%s, tokens=%s)",
            LLM_MODEL_NAME,
            response.usage.total_tokens if response.usage else "unknown",
        )
        return result

    except Exception as e:
        logger.error("LLM call failed: %s", e)
        raise


# ── Embedding Function (for LightRAG) ────────────────────────────────────


async def embedding_func(texts: list[str]) -> np.ndarray:
    """Generate embeddings for a list of texts.

    This function conforms to LightRAG's expected embedding function signature.

    Args:
        texts: List of text strings to embed.

    Returns:
        numpy array of shape (len(texts), EMBEDDING_DIM).
    """
    client = _get_embedding_client()

    try:
        response = await client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=texts,
        )
        embeddings = [item.embedding for item in response.data]
        result = np.array(embeddings, dtype=np.float32)

        # Validate dimensions
        if result.shape[1] != EMBEDDING_DIM:
            logger.warning(
                "Embedding dimension mismatch: expected %d, got %d. "
                "Update EMBEDDING_DIM in your .env file.",
                EMBEDDING_DIM,
                result.shape[1],
            )

        logger.debug(
            "Embeddings generated: %d texts → shape %s",
            len(texts),
            result.shape,
        )
        return result

    except Exception as e:
        logger.error("Embedding call failed: %s", e)
        raise


# ── Health Check ──────────────────────────────────────────────────────────


async def check_llm_availability() -> bool:
    """Check if the LLM server is reachable and responsive."""
    try:
        response = await llm_model_func("Say 'ok'.", system_prompt="Reply with only 'ok'.")
        return bool(response.strip())
    except Exception:
        return False


async def check_embedding_availability() -> bool:
    """Check if the embedding model is reachable and responsive."""
    try:
        result = await embedding_func(["test"])
        return result.shape == (1, EMBEDDING_DIM)
    except Exception:
        return False
