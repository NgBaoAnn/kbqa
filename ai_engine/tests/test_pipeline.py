"""Tests for query routing and Cypher query building (AI Engine pipeline components)."""

import pytest


class TestQueryRouter:
    """Tests for ai_engine/services/query_router.py."""

    def test_symptom_question_routes_cypher(self):
        """Question about symptoms should route to Cypher path."""
        from ai_engine.services.query_router import classify_cypher_intent
        query_type, entity = classify_cypher_intent("Bệnh tiểu đường có triệu chứng gì?")
        assert query_type == "symptoms"
        assert entity == "tiểu đường"

    def test_vague_question_routes_lightrag(self):
        """Vague/thematic questions should route to LightRAG."""
        from ai_engine.services.query_router import classify_cypher_intent
        query_type, entity = classify_cypher_intent("Sức khỏe quan trọng như thế nào trong cuộc sống?")
        assert query_type is None
        assert entity is None

    def test_count_question_no_entity_routes_lightrag(self):
        """Count questions with no disease entity route to LightRAG (no Cypher path)."""
        from ai_engine.services.query_router import classify_cypher_intent
        query_type, entity = classify_cypher_intent("Có bao nhiêu bệnh trong hệ thống?")
        assert query_type is None
        assert entity is None

    def test_count_question_with_entity_routes_representative(self):
        """Count questions with a disease entity route to representative examples."""
        from ai_engine.services.query_router import classify_cypher_intent
        query_type, entity = classify_cypher_intent("có bao nhiêu triệu chứng của viêm phổi")
        assert query_type == "symptoms"
        assert entity == "viêm phổi"

    def test_english_question_routing(self):
        """English questions should also be routed correctly."""
        from ai_engine.services.query_router import classify_cypher_intent
        query_type, entity = classify_cypher_intent("What are the symptoms of diabetes?")
        assert query_type == "symptoms"
        assert entity == "diabetes"


class TestCypherQueryBuilder:
    """Tests for ai_engine/services/cypher_query_builder.py."""

    def test_build_symptoms_query(self):
        """Should build valid symptoms Cypher query."""
        from ai_engine.services.cypher_query_builder import build_cypher_query
        cypher, params = build_cypher_query("symptoms", "Tiểu đường")
        assert "MATCH" in cypher
        assert "RETURN" in cypher
        assert params.get("name") == "Tiểu đường"

    def test_build_medicine_query(self):
        """Should build valid medicine Cypher query."""
        from ai_engine.services.cypher_query_builder import build_cypher_query
        cypher, params = build_cypher_query("medicine", "Tiểu Đường")
        assert "MATCH" in cypher
        assert "Medicine" in cypher or "IS_PRESCRIBED" in cypher

    def test_build_count_query_returns_none(self):
        """count query_type was removed — builder should return None."""
        from ai_engine.services.cypher_query_builder import build_cypher_query
        cypher, params = build_cypher_query("count", None)
        assert cypher is None
