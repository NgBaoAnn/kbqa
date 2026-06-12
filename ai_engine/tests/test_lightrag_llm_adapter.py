"""Tests for ai_engine/services/lightrag_llm_adapter.py."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestLLMClient:
    """Tests for LLM client singleton and functions."""

    def test_llm_config_loaded(self):
        """Config values should be loaded from environment."""
        from ai_engine.config import LLM_BASE_URL, LLM_MODEL_NAME
        assert LLM_BASE_URL is not None
        assert LLM_MODEL_NAME is not None

    def test_embedding_config_loaded(self):
        """Embedding config values should be loaded."""
        from ai_engine.config import EMBEDDING_MODEL, EMBEDDING_DIM
        assert EMBEDDING_MODEL is not None
        assert isinstance(EMBEDDING_DIM, int)
        assert EMBEDDING_DIM > 0

    @pytest.mark.asyncio
    async def test_check_llm_availability_connection_error(self):
        """LLM availability check should return False on connection error."""
        from ai_engine.services.lightrag_llm_adapter import check_llm_availability
        with patch("ai_engine.services.lightrag_llm_adapter._get_llm_client") as mock_client:
            mock_instance = MagicMock()
            mock_instance.models = MagicMock()
            mock_instance.models.list = AsyncMock(side_effect=Exception("Connection refused"))
            mock_client.return_value = mock_instance
            result = await check_llm_availability()
            assert result is False

    @pytest.mark.asyncio
    async def test_check_embedding_availability_connection_error(self):
        """Embedding availability check should return False on connection error."""
        from ai_engine.services.lightrag_llm_adapter import check_embedding_availability
        with patch("ai_engine.services.lightrag_llm_adapter._get_embedding_client") as mock_client:
            mock_instance = MagicMock()
            mock_instance.models = MagicMock()
            mock_instance.models.list = AsyncMock(side_effect=Exception("Connection refused"))
            mock_client.return_value = mock_instance
            result = await check_embedding_availability()
            assert result is False

    @pytest.mark.asyncio
    async def test_llm_model_func_returns_string(self):
        """LLM model function should return a string response."""
        from ai_engine.services.lightrag_llm_adapter import llm_model_func
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"

        with patch("ai_engine.services.lightrag_llm_adapter._get_llm_client") as mock_client:
            mock_instance = MagicMock()
            mock_instance.chat = MagicMock()
            mock_instance.chat.completions = MagicMock()
            mock_instance.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance
            result = await llm_model_func("test prompt")
            assert isinstance(result, str)
            assert result == "Test response"

    @pytest.mark.asyncio
    async def test_llm_model_func_streams_chunks(self):
        """Streaming LLM calls should return an async iterator of content chunks."""
        from ai_engine.services.lightrag_llm_adapter import llm_model_func

        class AsyncChunks:
            def __aiter__(self):
                self._chunks = iter(["Xin ", "chào"])
                return self

            async def __anext__(self):
                try:
                    content = next(self._chunks)
                except StopIteration as exc:
                    raise StopAsyncIteration from exc
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta.content = content
                return chunk

        with patch("ai_engine.services.lightrag_llm_adapter._get_llm_client") as mock_client:
            mock_instance = MagicMock()
            mock_instance.chat = MagicMock()
            mock_instance.chat.completions = MagicMock()
            mock_instance.chat.completions.create = AsyncMock(return_value=AsyncChunks())
            mock_client.return_value = mock_instance

            result = await llm_model_func("test prompt", stream=True)
            chunks = []
            async for chunk in result:
                chunks.append(chunk)

            assert chunks == ["Xin ", "chào"]
            mock_instance.chat.completions.create.assert_awaited_once()
            assert mock_instance.chat.completions.create.await_args.kwargs["stream"] is True

    @pytest.mark.asyncio
    async def test_embedding_func_returns_ndarray(self):
        """Embedding function should return numpy array with correct dimensions."""
        import numpy as np
        from ai_engine.services.lightrag_llm_adapter import embedding_func
        from ai_engine.config import EMBEDDING_DIM

        mock_embedding = MagicMock()
        mock_embedding.embedding = [0.1] * EMBEDDING_DIM
        mock_response = MagicMock()
        mock_response.data = [mock_embedding]

        with patch("ai_engine.services.lightrag_llm_adapter._get_embedding_client") as mock_client:
            mock_instance = MagicMock()
            mock_instance.embeddings = MagicMock()
            mock_instance.embeddings.create = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance
            result = await embedding_func(["test text"])
            assert isinstance(result, np.ndarray)
            assert result.shape[1] == EMBEDDING_DIM

    def test_timeout_config(self):
        """Timeout config should be a positive number."""
        from ai_engine.config import LLM_TIMEOUT_SECONDS
        assert isinstance(LLM_TIMEOUT_SECONDS, (int, float))
        assert LLM_TIMEOUT_SECONDS > 0
