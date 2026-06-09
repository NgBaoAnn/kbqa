"""Unit tests for cypher_query_builder.to_cypher and cypher_graph_service.query."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestToCypher:
    """Tests for cypher_query_builder.to_cypher."""

    @pytest.mark.asyncio
    async def test_template_hit_returns_used_template_true(self):
        """Known query_type with entity should return a template, used_template=True."""
        from ai_engine.services.cypher_query_builder import to_cypher
        cypher, params, used_template = await to_cypher(
            "symptoms", "tiểu đường", False, "tiểu đường có triệu chứng gì"
        )
        assert used_template is True
        assert "MATCH" in cypher
        assert params.get("name") == "tiểu đường"

    @pytest.mark.asyncio
    async def test_unknown_type_falls_back_to_llm(self):
        """Unknown query_type triggers LLM fallback, used_template=False."""
        from ai_engine.services.cypher_query_builder import to_cypher
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            "MATCH (d:Disease) RETURN d.disease_name LIMIT 5"
        )
        with patch("ai_engine.services.cypher_query_builder.get_chat_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_get.return_value = mock_client
            cypher, params, used_template = await to_cypher(
                "unknown_type", None, False, "some free-form question"
            )
        assert used_template is False
        assert "MATCH" in cypher
        assert params == {}

    @pytest.mark.asyncio
    async def test_llm_failure_raises_value_error(self):
        """LLM failure should propagate as ValueError."""
        from ai_engine.services.cypher_query_builder import to_cypher
        with patch("ai_engine.services.cypher_query_builder.get_chat_client") as mock_get:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=Exception("LLM unavailable")
            )
            mock_get.return_value = mock_client
            with pytest.raises(ValueError, match="LLM generation failed"):
                await to_cypher("unknown_type", None, False, "some question")


class TestCypherGraphServiceQuery:
    """Tests for cypher_graph_service.query."""

    @pytest.mark.asyncio
    async def test_success_path_returns_answer(self):
        """Full happy path: template → execute → synthesize returns success dict."""
        from ai_engine.services.cypher_graph_service import query

        fake_records = [{"disease": "Bệnh tiểu đường", "symptoms": "khát nước, mệt mỏi"}]
        execute_fn = AsyncMock(return_value=fake_records)

        with patch("ai_engine.services.cypher_graph_service.synthesize_answer",
                   new=AsyncMock(return_value="Tiểu đường có triệu chứng khát nước.")):
            result = await query(
                question="tiểu đường có triệu chứng gì",
                query_type="symptoms",
                entity="tiểu đường",
                exact=False,
                execute_fn=execute_fn,
            )

        assert result["success"] is True
        assert result["used_template"] is True
        assert "answer" in result
        assert result["records"] == fake_records
        assert "MATCH" in result["cypher"]

    @pytest.mark.asyncio
    async def test_no_records_returns_fallback(self):
        """Empty result set should trigger fallback."""
        from ai_engine.services.cypher_graph_service import query

        execute_fn = AsyncMock(return_value=[])
        result = await query(
            question="tiểu đường có triệu chứng gì",
            query_type="symptoms",
            entity="tiểu đường",
            exact=False,
            execute_fn=execute_fn,
        )
        assert result["success"] is False
        assert result["fallback"] is True
        assert result["reason"] == "no_records"

    @pytest.mark.asyncio
    async def test_neo4j_error_returns_fallback(self):
        """Neo4j execution error should trigger fallback."""
        from ai_engine.services.cypher_graph_service import query

        execute_fn = AsyncMock(side_effect=Exception("Neo4j connection refused"))
        result = await query(
            question="tiểu đường có triệu chứng gì",
            query_type="symptoms",
            entity="tiểu đường",
            exact=False,
            execute_fn=execute_fn,
        )
        assert result["success"] is False
        assert result["fallback"] is True
        assert "execution_failed" in result["reason"]

    @pytest.mark.asyncio
    async def test_generation_failure_returns_fallback(self):
        """LLM generation failure (unknown type) should trigger fallback."""
        from ai_engine.services.cypher_graph_service import query

        execute_fn = AsyncMock()
        with patch("ai_engine.services.cypher_graph_service.to_cypher",
                   new=AsyncMock(side_effect=ValueError("LLM generation failed: timeout"))):
            result = await query(
                question="some obscure question",
                query_type=None,
                entity=None,
                exact=False,
                execute_fn=execute_fn,
            )
        assert result["success"] is False
        assert result["fallback"] is True
        assert "generation_failed" in result["reason"]

    @pytest.mark.asyncio
    async def test_sanitize_error_returns_hard_error(self):
        """Sanitizer rejection should return hard error (no fallback)."""
        from ai_engine.services.cypher_graph_service import query

        execute_fn = AsyncMock()
        with patch("ai_engine.services.cypher_graph_service.sanitize_cypher",
                   side_effect=ValueError("dangerous query blocked")):
            result = await query(
                question="tiểu đường có triệu chứng gì",
                query_type="symptoms",
                entity="tiểu đường",
                exact=False,
                execute_fn=execute_fn,
            )
        assert result["success"] is False
        assert result["fallback"] is False
        assert result["error_code"] == "CYPHER_GENERATION_FAILED"
