"""Unit tests for the production LightRAG vector adapter contract."""

from __future__ import annotations

import sys
import types

import pytest


class _QueryParam:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeRag:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def aquery(self, question, *, param):
        self.calls.append({"question": question, "param": param})
        return self.result


def _install_fake_lightrag(monkeypatch):
    fake_lightrag = types.ModuleType("lightrag")
    fake_lightrag.QueryParam = _QueryParam
    fake_prompt = types.ModuleType("lightrag.prompt")
    fake_prompt.PROMPTS = {}
    fake_lightrag.prompt = fake_prompt
    monkeypatch.setitem(sys.modules, "lightrag", fake_lightrag)
    monkeypatch.setitem(sys.modules, "lightrag.prompt", fake_prompt)
    return fake_prompt


def test_prompt_patch_keeps_legacy_vietnamese_medical_contract(monkeypatch):
    fake_prompt = _install_fake_lightrag(monkeypatch)
    from adapters.lightrag import vector_repository

    vector_repository._patch_lightrag_prompts()

    expected_base = vector_repository._VI_PROMPT_BASE
    assert fake_prompt.PROMPTS["rag_response"] == expected_base + "{context_data}\n"
    assert fake_prompt.PROMPTS["naive_rag_response"] == expected_base + "{content_data}\n"
    assert "Bạn là trợ lý y tế AegisHealth" in expected_base
    assert "CHỈ dựa trên thông tin được cung cấp" in expected_base
    assert "Không tạo mục \"References\"" in expected_base
    assert vector_repository._MEDICAL_USER_PROMPT == (
        "Luôn trả lời bằng tiếng Việt. Không đề xuất liều lượng thuốc."
    )


@pytest.mark.asyncio
async def test_query_builds_legacy_lightrag_query_param_contract(monkeypatch):
    _install_fake_lightrag(monkeypatch)
    from adapters.lightrag.vector_repository import LightragVectorRepository

    repo = LightragVectorRepository(force_naive_mode=True, default_query_mode="hybrid")
    fake_rag = _FakeRag("Câu trả lời")

    async def _get_instance():
        return fake_rag

    monkeypatch.setattr(repo, "_get_instance", _get_instance)

    result = await repo.query("Câu hỏi", mode="global")

    assert result["success"] is True
    assert result["mode"] == "naive"
    param = fake_rag.calls[0]["param"].kwargs
    assert param == {
        "mode": "naive",
        "only_need_context": False,
        "user_prompt": "Luôn trả lời bằng tiếng Việt. Không đề xuất liều lượng thuốc.",
        "top_k": 20,
        "chunk_top_k": 10,
        "max_entity_tokens": 2000,
        "max_relation_tokens": 2000,
        "max_total_tokens": 6000,
    }


@pytest.mark.asyncio
async def test_query_rejects_none_result(monkeypatch):
    _install_fake_lightrag(monkeypatch)
    from adapters.lightrag.vector_repository import LightragVectorRepository

    repo = LightragVectorRepository()

    async def _get_instance():
        return _FakeRag(None)

    monkeypatch.setattr(repo, "_get_instance", _get_instance)

    result = await repo.query("Tôi nên làm gì để ngủ tốt hơn?", mode="naive")

    assert result["success"] is False
    assert result["answer"] == ""
    assert "empty answer" in result["error"]


@pytest.mark.asyncio
async def test_query_rejects_string_none_result(monkeypatch):
    _install_fake_lightrag(monkeypatch)
    from adapters.lightrag.vector_repository import LightragVectorRepository

    repo = LightragVectorRepository()

    async def _get_instance():
        return _FakeRag("None")

    monkeypatch.setattr(repo, "_get_instance", _get_instance)

    result = await repo.query("Tôi nên làm gì để ngủ tốt hơn?", mode="naive")

    assert result["success"] is False
    assert result["answer"] == ""
    assert "empty answer" in result["error"]


@pytest.mark.asyncio
async def test_query_stream_rejects_none_result(monkeypatch):
    _install_fake_lightrag(monkeypatch)
    from adapters.lightrag.vector_repository import LightragVectorRepository

    repo = LightragVectorRepository()

    async def _get_instance():
        return _FakeRag(None)

    monkeypatch.setattr(repo, "_get_instance", _get_instance)

    with pytest.raises(RuntimeError, match="empty answer"):
        await repo.query_stream("Tôi nên làm gì để ngủ tốt hơn?", mode="naive")
