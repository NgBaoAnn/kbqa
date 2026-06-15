"""Unit tests for the Domain layer — Phase 1.

Tests are grouped by sub-domain:
1. QA value objects
2. Intent classifier (regex)
3. Safety policy
4. Source policy
5. Response formatter
6. Other domain entities
"""

from __future__ import annotations

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# 1. QA Value Objects
# ═══════════════════════════════════════════════════════════════════════════


class TestQueryType:
    def test_from_string_valid(self):
        from domain.qa.value_objects import QueryType

        assert QueryType.from_string("symptoms") == QueryType.SYMPTOMS
        assert QueryType.from_string("TREATMENT") == QueryType.TREATMENT
        assert QueryType.from_string("  medicine ") == QueryType.MEDICINE

    def test_from_string_invalid_returns_general(self):
        from domain.qa.value_objects import QueryType

        assert QueryType.from_string("invalid") == QueryType.GENERAL
        assert QueryType.from_string(None) == QueryType.GENERAL
        assert QueryType.from_string("") == QueryType.GENERAL

    def test_has_cypher_template(self):
        from domain.qa.value_objects import QueryType

        assert QueryType.SYMPTOMS.has_cypher_template is True
        assert QueryType.TREATMENT.has_cypher_template is True
        assert QueryType.GENERAL.has_cypher_template is False
        assert QueryType.GENERAL_INFO.has_cypher_template is False


class TestEntityName:
    def test_valid_creation(self):
        from domain.qa.value_objects import EntityName

        e = EntityName("tiểu đường")
        assert e.value == "Tiểu đường"

    def test_single_char_capitalised(self):
        from domain.qa.value_objects import EntityName

        e = EntityName("a")
        assert e.value == "A"

    def test_strips_whitespace(self):
        from domain.qa.value_objects import EntityName

        e = EntityName("  viêm phổi  ")
        assert e.value == "Viêm phổi"

    def test_empty_raises(self):
        from domain.qa.value_objects import EntityName

        with pytest.raises(ValueError, match="cannot be empty"):
            EntityName("")

    def test_whitespace_only_raises(self):
        from domain.qa.value_objects import EntityName

        with pytest.raises(ValueError, match="cannot be empty"):
            EntityName("   ")


class TestCypherQuery:
    def test_valid(self):
        from domain.qa.value_objects import CypherQuery

        cq = CypherQuery(query="MATCH (n) RETURN n", params={"limit": 10})
        assert cq.query == "MATCH (n) RETURN n"
        assert cq.params == {"limit": 10}

    def test_empty_raises(self):
        from domain.qa.value_objects import CypherQuery

        with pytest.raises(ValueError, match="cannot be empty"):
            CypherQuery(query="")


class TestIntentClassification:
    def test_should_use_cypher(self):
        from domain.qa.value_objects import EntityName, IntentClassification, QueryType

        ic = IntentClassification(
            query_type=QueryType.SYMPTOMS,
            entity=EntityName("tiểu đường"),
        )
        assert ic.should_use_cypher is True
        assert ic.has_entity is True

    def test_general_no_cypher(self):
        from domain.qa.value_objects import IntentClassification, QueryType

        ic = IntentClassification(query_type=QueryType.GENERAL)
        assert ic.should_use_cypher is False
        assert ic.has_entity is False


class TestSafetyClassification:
    def test_defaults(self):
        from domain.qa.value_objects import SafetyClassification

        sc = SafetyClassification()
        assert sc.level == "normal"
        assert sc.requires_emergency_notice is False


class TestSourceRecord:
    def test_creation(self):
        from domain.qa.value_objects import SourceRecord

        sr = SourceRecord(id="1", source_type="cypher", title="Test", snippet="MATCH (n)")
        assert sr.id == "1"
        assert sr.source_type == "cypher"
        assert sr.rank == 1


# ═══════════════════════════════════════════════════════════════════════════
# 2. Intent Classifier (Regex)
# ═══════════════════════════════════════════════════════════════════════════


class TestCleanEntity:
    def test_removes_prefix_benh(self):
        from domain.qa.intent_classifier import clean_entity

        assert clean_entity("bệnh tiểu đường") == "tiểu đường"

    def test_removes_trailing_question_words(self):
        from domain.qa.intent_classifier import clean_entity

        assert clean_entity("viêm phổi là gì") == "viêm phổi"

    def test_none_for_empty(self):
        from domain.qa.intent_classifier import clean_entity

        assert clean_entity("") is None
        assert clean_entity("a") is None  # too short

    def test_none_for_question_word(self):
        from domain.qa.intent_classifier import clean_entity

        assert clean_entity("gì") is None
        assert clean_entity("nào") is None


class TestClassifyCypherIntent:
    def test_symptoms_pattern(self):
        from domain.qa.intent_classifier import classify_cypher_intent

        q_type, entity = classify_cypher_intent("triệu chứng của bệnh tiểu đường?")
        assert q_type == "symptoms"
        assert entity == "tiểu đường"

    def test_medicine_pattern(self):
        from domain.qa.intent_classifier import classify_cypher_intent

        q_type, entity = classify_cypher_intent("thuốc điều trị viêm phổi?")
        assert q_type == "medicine"
        assert entity == "viêm phổi"

    def test_treatment_pattern(self):
        from domain.qa.intent_classifier import classify_cypher_intent

        q_type, entity = classify_cypher_intent("cách điều trị bệnh gout?")
        assert q_type == "treatment"
        assert entity == "gout"

    def test_find_by_symptom_pattern(self):
        from domain.qa.intent_classifier import classify_cypher_intent

        q_type, entity = classify_cypher_intent("bệnh nào có triệu chứng ho khan?")
        assert q_type == "find_by_symptom"
        assert entity == "ho khan"

    def test_no_match_returns_none(self):
        from domain.qa.intent_classifier import classify_cypher_intent

        q_type, entity = classify_cypher_intent("xin chào bạn")
        assert q_type is None
        assert entity is None

    def test_multi_bracket_skips(self):
        from domain.qa.intent_classifier import classify_cypher_intent

        q_type, entity = classify_cypher_intent("[sốt, ho, đau đầu, mệt] là triệu chứng gì?")
        assert q_type is None


class TestClassifyIntentRegex:
    def test_returns_intent_classification(self):
        from domain.qa.intent_classifier import classify_intent_regex
        from domain.qa.value_objects import QueryType

        result = classify_intent_regex("triệu chứng của bệnh tiểu đường?")
        assert result.query_type == QueryType.SYMPTOMS
        assert result.entity is not None
        assert result.entity.value == "Tiểu đường"
        assert result.method == "regex"

    def test_no_match_returns_general(self):
        from domain.qa.intent_classifier import classify_intent_regex
        from domain.qa.value_objects import QueryType

        result = classify_intent_regex("xin chào")
        assert result.query_type == QueryType.GENERAL
        assert result.confidence == 0.0


class TestEmergencyDetection:
    def test_vi_patterns(self):
        from domain.qa.intent_classifier import detect_emergency_intent

        assert detect_emergency_intent("tôi bị co giật rất mạnh") is True
        assert detect_emergency_intent("bất tỉnh trên sàn nhà") is True

    def test_en_patterns(self):
        from domain.qa.intent_classifier import detect_emergency_intent

        assert detect_emergency_intent("severe chest pain right now") is True

    def test_normal_question(self):
        from domain.qa.intent_classifier import detect_emergency_intent

        assert detect_emergency_intent("tiểu đường là gì?") is False


class TestListIntentDetection:
    def test_list_keywords(self):
        from domain.qa.intent_classifier import detect_list_intent

        assert detect_list_intent("liệt kê tất cả bệnh") is True
        assert detect_list_intent("có bệnh nào liên quan?") is True

    def test_normal_question(self):
        from domain.qa.intent_classifier import detect_list_intent

        assert detect_list_intent("tiểu đường là gì?") is False


# ═══════════════════════════════════════════════════════════════════════════
# 3. Safety Policy
# ═══════════════════════════════════════════════════════════════════════════


class TestClassifySafety:
    def test_emergency(self):
        from domain.qa.safety_policy import classify_safety

        result = classify_safety("tôi bị co giật, giúp tôi với!")
        assert result.level == "emergency"
        assert result.requires_emergency_notice is True

    def test_caution_drug_question(self):
        from domain.qa.safety_policy import classify_safety

        result = classify_safety("liều lượng thuốc paracetamol cho trẻ?")
        assert result.level == "caution"

    def test_normal(self):
        from domain.qa.safety_policy import classify_safety

        result = classify_safety("tiểu đường type 2 là gì?")
        assert result.level == "normal"


class TestSafetyFromResponseType:
    def test_warning_response_type(self):
        from domain.qa.safety_policy import safety_from_response_type

        result = safety_from_response_type("warning", "bất kỳ câu hỏi nào")
        assert result.level == "emergency"
        assert result.requires_emergency_notice is True

    def test_text_response_type_falls_through(self):
        from domain.qa.safety_policy import safety_from_response_type

        result = safety_from_response_type("text", "tiểu đường là gì?")
        assert result.level == "normal"


# ═══════════════════════════════════════════════════════════════════════════
# 4. Source Policy
# ═══════════════════════════════════════════════════════════════════════════


class TestSourcePolicy:
    def test_cypher_source(self):
        from domain.qa.source_policy import build_cypher_source

        src = build_cypher_source("MATCH (d:Disease) RETURN d", engine="cypher_direct")
        assert src.source_type == "cypher"
        assert src.title == "Neo4j VietMedKG"
        assert "MATCH" in src.snippet

    def test_fallback_source(self):
        from domain.qa.source_policy import build_fallback_source

        src = build_fallback_source(engine="lightrag", query_mode="naive")
        assert src.source_type == "other"
        assert "lightrag" in src.snippet

    def test_normalize_cypher_path(self):
        from domain.qa.source_policy import normalize_sources_from_pipeline

        sources = normalize_sources_from_pipeline({
            "engine": "cypher_direct",
            "cypher": "MATCH (d) RETURN d",
            "query_mode": "cypher:template:symptoms",
        })
        assert len(sources) >= 1
        assert sources[0].source_type == "cypher"

    def test_normalize_fallback_on_empty(self):
        from domain.qa.source_policy import normalize_sources_from_pipeline

        sources = normalize_sources_from_pipeline({})
        assert len(sources) >= 1
        assert sources[0].source_type == "other"

    def test_normalize_non_dict_metadata(self):
        from domain.qa.source_policy import normalize_sources_from_pipeline

        sources = normalize_sources_from_pipeline(None)  # type: ignore
        assert len(sources) >= 1

    def test_secret_keys_stripped(self):
        from domain.qa.source_policy import build_cypher_source

        src = build_cypher_source(
            "MATCH (d) RETURN d",
            extra={"token": "secret123", "engine": "test"},
        )
        assert "token" not in src.metadata

    def test_lightrag_sources(self):
        from domain.qa.source_policy import build_lightrag_sources

        sources = build_lightrag_sources(
            entities=[{"entity_name": "Tiểu đường", "description": "Bệnh mãn tính"}],
            relationships=[{"src_id": "A", "tgt_id": "B", "description": "liên quan"}],
            chunks=[{"content": "Đoạn văn bản", "id": "chunk-1"}],
        )
        assert len(sources) == 3
        assert sources[0].source_type == "lightrag_entity"
        assert sources[1].source_type == "lightrag_relationship"
        assert sources[2].source_type == "lightrag_chunk"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Response Formatter
# ═══════════════════════════════════════════════════════════════════════════


class TestClassifyResponseType:
    def test_emergency_question(self):
        from domain.qa.response_formatter import classify_response_type

        assert classify_response_type("tôi bị co giật nặng", "answer") == "warning"

    def test_table_response(self):
        from domain.qa.response_formatter import classify_response_type

        answer = "- Paracetamol\n- Ibuprofen\n- Aspirin"
        assert classify_response_type("thuốc điều trị cảm cúm", answer) == "table"

    def test_text_response(self):
        from domain.qa.response_formatter import classify_response_type

        assert classify_response_type("tiểu đường là gì?", "Tiểu đường là bệnh mãn tính.") == "text"


class TestFormatWarningAnswer:
    def test_adds_prefix_and_cta(self):
        from domain.qa.response_formatter import format_warning_answer

        result = format_warning_answer("Bạn cần đến bệnh viện")
        assert result.startswith("⚠️ CẢNH BÁO Y TẾ:")
        assert "CẤP CỨU" in result

    def test_no_double_prefix(self):
        from domain.qa.response_formatter import format_warning_answer

        result = format_warning_answer("⚠️ Already prefixed")
        assert not result.startswith("⚠️ CẢNH BÁO Y TẾ: ⚠️")


class TestNeedsDisclaimer:
    def test_lightrag_medical_question(self):
        from domain.qa.response_formatter import needs_disclaimer

        assert needs_disclaimer("naive", "triệu chứng tiểu đường") is True

    def test_lightrag_navigational_question(self):
        from domain.qa.response_formatter import needs_disclaimer

        assert needs_disclaimer("naive", "bệnh nào phổ biến ở trẻ em") is False

    def test_cypher_template_symptoms(self):
        from domain.qa.response_formatter import needs_disclaimer

        assert needs_disclaimer("cypher:template:symptoms", "") is True

    def test_cypher_template_department(self):
        from domain.qa.response_formatter import needs_disclaimer

        assert needs_disclaimer("cypher:template:department", "") is False

    def test_disambiguation_no_disclaimer(self):
        from domain.qa.response_formatter import needs_disclaimer

        assert needs_disclaimer("cypher:disambiguation", "") is False


# ═══════════════════════════════════════════════════════════════════════════
# 6. Other Domain Entities
# ═══════════════════════════════════════════════════════════════════════════


class TestQueryResult:
    def test_is_successful(self):
        from domain.qa.entities import QueryResult

        qr = QueryResult(answer="Câu trả lời")
        assert qr.is_successful is True

    def test_empty_answer_not_successful(self):
        from domain.qa.entities import QueryResult

        qr = QueryResult(answer="")
        assert qr.is_successful is False


class TestUserProfile:
    def test_admin_role(self):
        from domain.user.entities import UserProfile

        user = UserProfile(id="1", role="admin")
        assert user.is_admin is True
        assert user.is_reviewer is True

    def test_user_role(self):
        from domain.user.entities import UserProfile

        user = UserProfile(id="2", role="user")
        assert user.is_admin is False
        assert user.is_reviewer is False


class TestUserPreferences:
    def test_valid(self):
        from domain.user.value_objects import UserPreferencesValue

        prefs = UserPreferencesValue(language="en", explanation_level="expert")
        assert prefs.language == "en"

    def test_invalid_language_raises(self):
        from domain.user.value_objects import UserPreferencesValue

        with pytest.raises(ValueError, match="Invalid language"):
            UserPreferencesValue(language="fr")


class TestFeedbackRatingValue:
    def test_valid(self):
        from domain.conversation.value_objects import FeedbackRatingValue

        f = FeedbackRatingValue(rating="up")
        assert f.is_negative is False

    def test_invalid_raises(self):
        from domain.conversation.value_objects import FeedbackRatingValue

        with pytest.raises(ValueError, match="Invalid feedback rating"):
            FeedbackRatingValue(rating="neutral")


class TestDiseaseName:
    def test_capitalisation(self):
        from domain.knowledge.value_objects import DiseaseName

        d = DiseaseName("viêm phổi")
        assert d.value == "Viêm phổi"

    def test_empty_raises(self):
        from domain.knowledge.value_objects import DiseaseName

        with pytest.raises(ValueError, match="cannot be empty"):
            DiseaseName("")
