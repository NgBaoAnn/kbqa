"""Sprint 2 — Người 1: Unit tests for ai_service adapter, source_policy, and safety_policy.

Coverage targets
----------------
source_policy:
  - normalize_cypher_source — baseline, stripped cypher, safe metadata
  - normalize_lightrag_sources — entities, relationships, chunks, mixed, empty
  - build_fallback_source — always returns a valid ChatSource
  - normalize_sources_from_pipeline — cypher path, lightrag path, fallback path,
    malformed input

safety_policy:
  - classify_safety — normal question, caution medical question, emergency symptoms
  - safety_from_response_type — warning response_type → emergency, others → classify

ai_service:
  - answer_question — success (cypher path), success (lightrag path),
    pipeline error response, empty answer, adapter timeout, engine exception
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.models.contracts import AIServiceResult, ChatSource, SafetyPayload


# ════════════════════════════════════════════════════════════════════════════
# source_policy tests
# ════════════════════════════════════════════════════════════════════════════


class TestNormalizeCypherSource:
    def test_basic_cypher_source(self):
        from app.services.source_policy import normalize_cypher_source

        src = normalize_cypher_source(
            cypher="MATCH (d:Disease) RETURN d",
            engine="cypher_direct",
            query_mode="cypher:template:symptoms",
        )
        assert isinstance(src, ChatSource)
        assert src.source_type == "cypher"
        assert src.title == "Neo4j VietMedKG"
        assert "MATCH" in (src.snippet or "")
        assert src.rank == 1
        assert src.metadata["engine"] == "cypher_direct"
        assert src.metadata["query_mode"] == "cypher:template:symptoms"

    def test_cypher_snippet_truncated_at_500(self):
        from app.services.source_policy import normalize_cypher_source

        long_cypher = "MATCH " + "x" * 600
        src = normalize_cypher_source(cypher=long_cypher)
        assert len(src.snippet or "") <= 500

    def test_empty_cypher_does_not_crash(self):
        from app.services.source_policy import normalize_cypher_source

        src = normalize_cypher_source(cypher="")
        assert src.source_type == "cypher"
        assert src.snippet == ""

    def test_secret_keys_stripped_from_extra_metadata(self):
        from app.services.source_policy import normalize_cypher_source

        src = normalize_cypher_source(
            cypher="MATCH (n) RETURN n",
            extra_metadata={
                "password": "hunter2",
                "token": "abc123",
                "engine": "cypher_direct",
            },
        )
        assert "password" not in src.metadata
        assert "token" not in src.metadata
        assert src.metadata["engine"] == "cypher_direct"

    def test_source_id_is_uuid_string(self):
        from app.services.source_policy import normalize_cypher_source
        import re

        src = normalize_cypher_source(cypher="MATCH (n) RETURN n")
        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        )
        assert uuid_pattern.match(src.id), f"id is not a UUID: {src.id}"


class TestNormalizeLightragSources:
    def test_entities_only(self):
        from app.services.source_policy import normalize_lightrag_sources

        entities = [
            {"entity_name": "Bệnh tiểu đường", "description": "Rối loạn chuyển hóa glucose.", "type": "Disease"},
            {"entity_name": "Insulin", "description": "Hormone điều hòa đường huyết.", "type": "Medicine"},
        ]
        sources = normalize_lightrag_sources(entities=entities)
        assert len(sources) == 2
        assert sources[0].source_type == "lightrag_entity"
        assert sources[0].title == "Bệnh tiểu đường"
        assert sources[1].rank == 2

    def test_relationships_only(self):
        from app.services.source_policy import normalize_lightrag_sources

        rels = [
            {"src_id": "Bệnh tiểu đường", "tgt_id": "Insulin", "keywords": "TREATS", "description": "Insulin điều trị tiểu đường."},
        ]
        sources = normalize_lightrag_sources(relationships=rels)
        assert len(sources) == 1
        assert sources[0].source_type == "lightrag_relationship"
        assert "Bệnh tiểu đường" in sources[0].title

    def test_chunks_only(self):
        from app.services.source_policy import normalize_lightrag_sources

        chunks = [
            {"id": "chunk-001", "content": "Bệnh tiểu đường type 2 rất phổ biến."},
        ]
        sources = normalize_lightrag_sources(chunks=chunks)
        assert len(sources) == 1
        assert sources[0].source_type == "lightrag_chunk"
        assert "chunk-001" in sources[0].title

    def test_mixed_sources_have_sequential_ranks(self):
        from app.services.source_policy import normalize_lightrag_sources

        sources = normalize_lightrag_sources(
            entities=[{"entity_name": "E1", "description": ""}],
            relationships=[{"src_id": "A", "tgt_id": "B", "keywords": "REL", "description": ""}],
            chunks=[{"id": "c1", "content": "text"}],
        )
        assert len(sources) == 3
        assert [s.rank for s in sources] == [1, 2, 3]

    def test_empty_lists_returns_empty(self):
        from app.services.source_policy import normalize_lightrag_sources

        sources = normalize_lightrag_sources(entities=[], relationships=[], chunks=[])
        assert sources == []

    def test_none_inputs_returns_empty(self):
        from app.services.source_policy import normalize_lightrag_sources

        sources = normalize_lightrag_sources()
        assert sources == []

    def test_snippet_truncated_at_500(self):
        from app.services.source_policy import normalize_lightrag_sources

        entities = [{"entity_name": "E", "description": "x" * 600}]
        sources = normalize_lightrag_sources(entities=entities)
        assert len(sources[0].snippet or "") <= 500

    def test_secret_keys_stripped(self):
        from app.services.source_policy import normalize_lightrag_sources

        entities = [{"entity_name": "E", "description": "ok"}]
        # Extra metadata would come through engine/query_mode only; ensure no bleed
        sources = normalize_lightrag_sources(entities=entities, engine="lightrag", query_mode="mix")
        assert "password" not in sources[0].metadata
        assert sources[0].metadata["engine"] == "lightrag"


class TestBuildFallbackSource:
    def test_always_returns_valid_source(self):
        from app.services.source_policy import build_fallback_source

        src = build_fallback_source(engine="lightrag", query_mode="mix")
        assert isinstance(src, ChatSource)
        assert src.source_type == "other"
        assert src.rank == 1
        assert src.id

    def test_metadata_has_engine_and_mode(self):
        from app.services.source_policy import build_fallback_source

        src = build_fallback_source(engine="cypher_direct", query_mode="cypher:template:symptoms")
        assert src.metadata["engine"] == "cypher_direct"
        assert src.metadata["query_mode"] == "cypher:template:symptoms"


class TestNormalizeSourcesFromPipeline:
    def test_cypher_engine_with_cypher_query(self):
        from app.services.source_policy import normalize_sources_from_pipeline

        meta = {
            "engine": "cypher_direct",
            "query_mode": "cypher:template:symptoms",
            "cypher": "MATCH (d:Disease)-[:HAS_SYMPTOM]->(s:Symptom) RETURN s",
        }
        sources = normalize_sources_from_pipeline(meta)
        assert len(sources) == 1
        assert sources[0].source_type == "cypher"
        assert "MATCH" in (sources[0].snippet or "")

    def test_cypher_engine_without_cypher_falls_back(self):
        from app.services.source_policy import normalize_sources_from_pipeline

        meta = {"engine": "cypher_direct", "query_mode": "cypher:template:symptoms"}
        sources = normalize_sources_from_pipeline(meta)
        assert len(sources) == 1
        assert sources[0].source_type == "other"  # fallback

    def test_lightrag_engine_with_entities(self):
        from app.services.source_policy import normalize_sources_from_pipeline

        meta = {"engine": "lightrag", "query_mode": "mix"}
        pipeline_result = {
            "entities": [{"entity_name": "Tiểu đường", "description": "desc"}],
        }
        sources = normalize_sources_from_pipeline(meta, pipeline_result)
        assert sources[0].source_type == "lightrag_entity"

    def test_lightrag_engine_without_context_falls_back(self):
        from app.services.source_policy import normalize_sources_from_pipeline

        meta = {"engine": "lightrag", "query_mode": "naive"}
        sources = normalize_sources_from_pipeline(meta, pipeline_result={"status": "success"})
        assert len(sources) == 1
        assert sources[0].source_type == "other"

    def test_malformed_metadata_does_not_crash(self):
        from app.services.source_policy import normalize_sources_from_pipeline

        # Non-dict metadata should be handled gracefully
        sources = normalize_sources_from_pipeline(None)  # type: ignore
        assert len(sources) == 1
        assert sources[0].source_type == "other"

    def test_missing_engine_falls_back(self):
        from app.services.source_policy import normalize_sources_from_pipeline

        sources = normalize_sources_from_pipeline({})
        assert len(sources) >= 1

    def test_sources_never_empty(self):
        """Regardless of input, normalize_sources_from_pipeline must return ≥1 source."""
        from app.services.source_policy import normalize_sources_from_pipeline

        for meta in [{}, {"engine": "lightrag"}, {"engine": "cypher_direct"}]:
            sources = normalize_sources_from_pipeline(meta)
            assert len(sources) >= 1, f"got empty sources for meta={meta}"

    def test_no_secret_keys_in_output(self):
        from app.services.source_policy import normalize_sources_from_pipeline

        meta = {
            "engine": "cypher_direct",
            "cypher": "MATCH (n) RETURN n",
            "password": "secret",
            "token": "tok123",
        }
        sources = normalize_sources_from_pipeline(meta)
        for src in sources:
            for key in src.metadata:
                assert key not in ("password", "token", "secret", "api_key")


# ════════════════════════════════════════════════════════════════════════════
# safety_policy tests
# ════════════════════════════════════════════════════════════════════════════


class TestClassifySafety:
    def test_normal_question_returns_normal(self):
        from app.services.safety_policy import classify_safety

        result = classify_safety("Bệnh tiểu đường là gì?")
        assert isinstance(result, SafetyPayload)
        assert result.level == "normal"
        assert result.requires_emergency_notice is False
        assert result.disclaimer

    def test_normal_english_question(self):
        from app.services.safety_policy import classify_safety

        result = classify_safety("What are the symptoms of diabetes?")
        assert result.level == "normal"

    def test_caution_medication_question(self):
        from app.services.safety_policy import classify_safety

        result = classify_safety("Thuốc này có thể uống khi đang dùng thuốc huyết áp không?")
        assert result.level == "caution"
        assert result.requires_emergency_notice is False
        assert result.disclaimer  # disclaimer always present

    def test_caution_side_effects_question(self):
        from app.services.safety_policy import classify_safety

        result = classify_safety("Thuốc này có tác dụng phụ gì không?")
        assert result.level == "caution"

    def test_caution_pregnant_medication_question(self):
        from app.services.safety_policy import classify_safety

        result = classify_safety("Phụ nữ có thai có dùng thuốc này được không?")
        assert result.level == "caution"

    def test_emergency_chest_pain(self):
        from app.services.safety_policy import classify_safety

        result = classify_safety("Tôi đang bị đau ngực dữ dội và khó thở")
        assert result.level == "emergency"
        assert result.requires_emergency_notice is True

    def test_emergency_co_giat(self):
        from app.services.safety_policy import classify_safety

        result = classify_safety("Người nhà đang bị co giật không dừng lại")
        assert result.level == "emergency"
        assert result.requires_emergency_notice is True

    def test_emergency_bat_tinh(self):
        from app.services.safety_policy import classify_safety

        result = classify_safety("Bạn tôi vừa bị bất tỉnh ở ngoài đường")
        assert result.level == "emergency"
        assert result.requires_emergency_notice is True

    def test_emergency_chay_mau(self):
        from app.services.safety_policy import classify_safety

        result = classify_safety("Vết thương đang chảy máu không cầm được")
        assert result.level == "emergency"

    def test_disclaimer_always_present(self):
        from app.services.safety_policy import classify_safety

        for question in [
            "Bệnh cảm cúm là gì?",
            "Thuốc này có tác dụng phụ gì?",
            "Tôi đang bị bất tỉnh",
        ]:
            result = classify_safety(question)
            assert result.disclaimer, f"disclaimer empty for: {question}"
            assert len(result.disclaimer) > 5


class TestSafetyFromResponseType:
    def test_warning_response_type_returns_emergency(self):
        from app.services.safety_policy import safety_from_response_type

        result = safety_from_response_type("warning", "Đau ngực dữ dội")
        assert result.level == "emergency"
        assert result.requires_emergency_notice is True

    def test_text_response_type_delegates_to_classify(self):
        from app.services.safety_policy import safety_from_response_type

        result = safety_from_response_type("text", "Bệnh tiểu đường là gì?")
        assert result.level == "normal"

    def test_table_response_type_delegates_to_classify(self):
        from app.services.safety_policy import safety_from_response_type

        result = safety_from_response_type("table", "Liệt kê triệu chứng bệnh tim")
        assert result.level in ("normal", "caution", "emergency")

    def test_warning_always_sets_requires_emergency_notice(self):
        from app.services.safety_policy import safety_from_response_type

        result = safety_from_response_type("warning", "any question")
        assert result.requires_emergency_notice is True


# ════════════════════════════════════════════════════════════════════════════
# ai_service adapter tests
# ════════════════════════════════════════════════════════════════════════════


def _make_success_pipeline_response(
    answer: str = "Câu trả lời test.",
    engine: str = "lightrag",
    query_mode: str = "mix",
    response_type: str = "text",
) -> dict[str, Any]:
    return {
        "status": "success",
        "response_type": response_type,
        "answer": answer,
        "data": None,
        "metadata": {
            "engine": engine,
            "query_mode": query_mode,
            "execution_time_ms": 120.5,
            "source_count": 1,
        },
    }


def _make_cypher_pipeline_response() -> dict[str, Any]:
    return {
        "status": "success",
        "response_type": "table",
        "answer": "Bệnh tiểu đường có các triệu chứng: khát nước, đi tiểu nhiều.",
        "data": [{"item": "Khát nước"}, {"item": "Đi tiểu nhiều"}],
        "metadata": {
            "engine": "cypher_direct",
            "query_mode": "cypher:template:symptoms",
            "execution_time_ms": 85.0,
            "source_count": 1,
            "cypher": "MATCH (d:Disease {disease_name: $name})-[:HAS_SYMPTOM]->(s:Symptom) RETURN s.name",
        },
    }


def _make_error_pipeline_response(error_code: str = "SYSTEM_ERROR") -> dict[str, Any]:
    return {
        "status": "error",
        "response_type": "text",
        "answer": "Xin lỗi, hệ thống đang gặp sự cố.",
        "data": None,
        "metadata": {
            "engine": "unknown",
            "query_mode": "unknown",
            "error_code": error_code,
            "error_detail": "Some internal error detail",
            "execution_time_ms": 10.0,
        },
    }


class TestAIServiceAnswerQuestion:
    @pytest.mark.asyncio
    async def test_success_lightrag_returns_ai_result(self):
        from app.services import ai_service

        mock_response = _make_success_pipeline_response()
        with patch(
            "app.services.pipeline.run_pipeline",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await ai_service.answer_question(
                question="Bệnh tiểu đường là gì?",
                mode="mix",
            )

        assert isinstance(result, AIServiceResult)
        assert result.answer == "Câu trả lời test."
        assert result.response_type == "text"
        assert result.metadata.engine == "lightrag"
        assert result.metadata.query_mode == "mix"
        assert result.metadata.execution_time_ms > 0
        assert isinstance(result.sources, list)
        assert len(result.sources) >= 1  # always at least 1 source
        assert isinstance(result.safety, SafetyPayload)

    @pytest.mark.asyncio
    async def test_success_cypher_path_builds_cypher_source(self):
        from app.services import ai_service

        mock_response = _make_cypher_pipeline_response()
        with patch(
            "app.services.pipeline.run_pipeline",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await ai_service.answer_question(question="Triệu chứng bệnh tiểu đường?")

        assert result.metadata.engine == "cypher_direct"
        assert result.metadata.cypher is not None
        assert any(s.source_type == "cypher" for s in result.sources)
        cypher_src = next(s for s in result.sources if s.source_type == "cypher")
        assert "MATCH" in (cypher_src.snippet or "")

    @pytest.mark.asyncio
    async def test_pipeline_error_response_returns_result_not_exception(self):
        from app.services import ai_service

        mock_response = _make_error_pipeline_response("LIGHTRAG_QUERY_FAILED")
        with patch(
            "app.services.pipeline.run_pipeline",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await ai_service.answer_question(question="Câu hỏi lỗi")

        assert isinstance(result, AIServiceResult)
        assert result.metadata.engine == "unknown"
        assert len(result.sources) >= 1  # fallback source present

    @pytest.mark.asyncio
    async def test_empty_answer_gets_fallback_message(self):
        from app.services import ai_service

        mock_response = {
            "status": "success",
            "response_type": "text",
            "answer": "",
            "data": None,
            "metadata": {
                "engine": "lightrag",
                "query_mode": "naive",
                "execution_time_ms": 50.0,
            },
        }
        with patch(
            "app.services.pipeline.run_pipeline",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await ai_service.answer_question(question="Câu hỏi rỗng?")

        assert result.answer  # not empty
        assert len(result.answer) > 5

    @pytest.mark.asyncio
    async def test_engine_exception_returns_result_not_exception(self):
        from app.services import ai_service

        with patch(
            "app.services.pipeline.run_pipeline",
            new_callable=AsyncMock,
            side_effect=Exception("DB connection refused at 10.0.0.1:7687"),
        ):
            result = await ai_service.answer_question(question="Câu hỏi gây lỗi")

        assert isinstance(result, AIServiceResult)
        # Error detail must NOT leak into the answer
        assert "10.0.0.1" not in result.answer
        assert "7687" not in result.answer
        assert "DB connection" not in result.answer
        assert result.answer  # non-empty user-friendly message

    @pytest.mark.asyncio
    async def test_adapter_timeout_returns_result_not_exception(self):
        from app.services import ai_service

        async def _slow(*args, **kwargs):
            await asyncio.sleep(999)

        with patch("app.services.pipeline.run_pipeline", side_effect=_slow):
            with patch.object(ai_service, "_ADAPTER_TIMEOUT_SECONDS", 0.01):
                result = await ai_service.answer_question(question="Câu hỏi timeout")

        assert isinstance(result, AIServiceResult)
        assert result.answer  # user-friendly timeout message
        assert len(result.sources) >= 1

    @pytest.mark.asyncio
    async def test_sources_never_empty(self):
        """sources[] must always have at least one element."""
        from app.services import ai_service

        for mock_response in [
            _make_success_pipeline_response(),
            _make_cypher_pipeline_response(),
            _make_error_pipeline_response(),
            {"status": "success", "answer": "ok", "metadata": {}, "response_type": "text"},
        ]:
            with patch(
                "app.services.pipeline.run_pipeline",
                new_callable=AsyncMock,
                return_value=mock_response,
            ):
                result = await ai_service.answer_question(question="Q")
            assert len(result.sources) >= 1, f"got empty sources for {mock_response}"

    @pytest.mark.asyncio
    async def test_safety_set_for_emergency_question(self):
        from app.services import ai_service

        mock_response = _make_success_pipeline_response(response_type="warning")
        with patch(
            "app.services.pipeline.run_pipeline",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await ai_service.answer_question(
                question="Tôi đang bị bất tỉnh và không thở được"
            )

        assert result.safety.level == "emergency"
        assert result.safety.requires_emergency_notice is True

    @pytest.mark.asyncio
    async def test_metadata_never_contains_secrets(self):
        from app.services import ai_service

        mock_response = _make_success_pipeline_response()
        # Inject a secret key into pipeline metadata to ensure it gets stripped
        mock_response["metadata"]["password"] = "hunter2"
        mock_response["metadata"]["token"] = "abc123"
        with patch(
            "app.services.pipeline.run_pipeline",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await ai_service.answer_question(question="Q")

        for src in result.sources:
            for key in src.metadata:
                assert key not in ("password", "token", "secret")

    @pytest.mark.asyncio
    async def test_mode_passed_through_to_pipeline(self):
        from app.services import ai_service

        mock_response = _make_success_pipeline_response(engine="lightrag", query_mode="local")
        with patch(
            "app.services.pipeline.run_pipeline",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_pipeline:
            await ai_service.answer_question(question="Q", mode="local")

        mock_pipeline.assert_awaited_once_with(question="Q", mode="local")

    @pytest.mark.asyncio
    async def test_follow_up_questions_are_limited_to_three(self):
        from app.services import ai_service

        mock_response = _make_success_pipeline_response()
        mock_response["suggested_questions"] = ["Q1?", "Q2?", "Q3?", "Q4?"]
        with patch(
            "app.services.pipeline.run_pipeline",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await ai_service.answer_question(question="Bệnh tiểu đường là gì?")

        assert result.suggested_questions == ["Q1?", "Q2?", "Q3?"]

    @pytest.mark.asyncio
    async def test_emergency_response_has_no_suggested_questions(self):
        from app.services import ai_service

        mock_response = _make_success_pipeline_response(response_type="warning")
        with patch(
            "app.services.pipeline.run_pipeline",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await ai_service.answer_question(question="Tôi đang bị đau ngực dữ dội")

        assert result.suggested_questions == []

    @pytest.mark.asyncio
    async def test_error_response_has_no_suggested_questions(self):
        from app.services import ai_service

        with patch(
            "app.services.pipeline.run_pipeline",
            new_callable=AsyncMock,
            return_value=_make_error_pipeline_response("LIGHTRAG_QUERY_FAILED"),
        ):
            result = await ai_service.answer_question(question="Q")

        assert result.suggested_questions == []

    @pytest.mark.asyncio
    async def test_disambiguation_structured_data_passes_through(self):
        from app.services import ai_service

        options = [
            {
                "id": "disease-cum-a",
                "label": "Bệnh cúm A",
                "description": "Bệnh trong cơ sở tri thức VietMedKG.",
                "entity_type": "Disease",
                "confidence": 0.95,
            }
        ]
        mock_response = _make_success_pipeline_response(response_type="disambiguation")
        mock_response["answer"] = "Vui lòng chọn bệnh bạn muốn hỏi."
        mock_response["data"] = options
        with patch(
            "app.services.pipeline.run_pipeline",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await ai_service.answer_question(question="Cúm có triệu chứng gì?")

        assert result.response_type == "disambiguation"
        assert result.data == options
        assert result.suggested_questions == []

    @pytest.mark.asyncio
    async def test_preferences_passed_to_pipeline_and_metadata(self):
        from app.services import ai_service

        prefs = {
            "language": "vi",
            "explanation_level": "expert",
            "answer_style": "detailed",
        }
        mock_response = _make_success_pipeline_response()
        with patch(
            "app.services.pipeline.run_pipeline",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_pipeline:
            result = await ai_service.answer_question(question="Q", preferences=prefs)

        mock_pipeline.assert_awaited_once_with(question="Q", mode=None, preferences=prefs)
        assert result.metadata.language == "vi"
        assert result.metadata.explanation_level == "expert"
        assert result.metadata.answer_style == "detailed"
        assert result.raw_engine_metadata["preferences"] == prefs

    @pytest.mark.asyncio
    async def test_raw_engine_metadata_available_for_query_log(self):
        """chat_service (Người 2) needs raw_engine_metadata to write query_logs."""
        from app.services import ai_service

        mock_response = _make_cypher_pipeline_response()
        with patch(
            "app.services.pipeline.run_pipeline",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await ai_service.answer_question(question="Q")

        assert isinstance(result.raw_engine_metadata, dict)
        assert "engine" in result.raw_engine_metadata
