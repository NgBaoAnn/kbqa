"""Tests for query routing and Cypher query building (AI Engine pipeline components)."""

import pytest


class TestQueryRouter:
    """Tests for ai_engine/services/query_router.py."""

    def test_symptom_question_routes_cypher(self):
        """Question about symptoms should route to Cypher path."""
        from ai_engine.services.query_router import route_query, QueryPath
        result = route_query("Bệnh tiểu đường có triệu chứng gì?")
        assert result["path"] == QueryPath.CYPHER
        assert result["query_type"] == "symptoms"

    def test_vague_question_routes_lightrag(self):
        """Vague/thematic questions should route to LightRAG."""
        from ai_engine.services.query_router import route_query, QueryPath
        result = route_query("Sức khỏe quan trọng như thế nào trong cuộc sống?")
        assert result["path"] == QueryPath.LIGHTRAG

    def test_count_question_routes_cypher(self):
        """Count questions should route to Cypher path."""
        from ai_engine.services.query_router import route_query, QueryPath
        result = route_query("Có bao nhiêu bệnh trong hệ thống?")
        assert result["path"] == QueryPath.CYPHER
        assert result["query_type"] == "count"

    def test_english_question_routing(self):
        """English questions should also be routed correctly."""
        from ai_engine.services.query_router import route_query, QueryPath
        result = route_query("What are the symptoms of diabetes?")
        assert result["path"] == QueryPath.CYPHER

    def test_route_returns_required_keys(self):
        """Route result should contain path, disease_name, query_type, reason."""
        from ai_engine.services.query_router import route_query
        result = route_query("Bệnh tiểu đường có triệu chứng gì?")
        assert "path" in result
        assert "disease_name" in result
        assert "query_type" in result
        assert "reason" in result


class TestCypherQueryBuilder:
    """Tests for ai_engine/services/cypher_query_builder.py."""

    def test_build_symptoms_query(self):
        """Should build valid symptoms Cypher query."""
        from ai_engine.services.cypher_query_builder import build_cypher_query
        cypher, params = build_cypher_query("symptoms", "Tiểu Đường")
        assert "MATCH" in cypher
        assert "RETURN" in cypher
        assert params.get("name") == "Tiểu Đường"

    def test_build_medicine_query(self):
        """Should build valid medicine Cypher query."""
        from ai_engine.services.cypher_query_builder import build_cypher_query
        cypher, params = build_cypher_query("medicine", "Tiểu Đường")
        assert "MATCH" in cypher
        assert "Medicine" in cypher or "IS_PRESCRIBED" in cypher

    def test_build_count_query(self):
        """Should build valid count Cypher query."""
        from ai_engine.services.cypher_query_builder import build_cypher_query
        cypher, params = build_cypher_query("count", None)
        assert "count" in cypher.lower() or "COUNT" in cypher

    def test_format_cypher_result_as_text(self):
        """Should format Cypher results into Vietnamese text."""
        from ai_engine.services.cypher_query_builder import format_cypher_result_as_text
        records = [{"symptom": "Đau đầu"}, {"symptom": "Sốt"}]
        text = format_cypher_result_as_text("symptoms", "Cảm cúm", records)
        assert isinstance(text, str)
        assert len(text) > 0
