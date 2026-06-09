"""LightRAG LLM adapter — wrapper functions conforming to LightRAG's expected signatures."""

import logging
from typing import Any

import numpy as np

from ai_engine.config import EMBEDDING_DIM, EMBEDDING_MODEL, LLM_MODEL_NAME
from ai_engine.services.llm_provider import get_chat_client, get_embedding_client

logger = logging.getLogger(__name__)


def _get_llm_client():
    return get_chat_client()


def _get_embedding_client():
    return get_embedding_client()


async def llm_model_func(
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list[dict[str, str]] | None = None,
    keyword_extraction: bool = False,
    **kwargs: Any,
) -> str:
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


async def embedding_func(texts: list[str]) -> np.ndarray:
    client = _get_embedding_client()

    try:
        response = await client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=texts,
        )
        embeddings = [item.embedding for item in response.data]
        result = np.array(embeddings, dtype=np.float32)

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
