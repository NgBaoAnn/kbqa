"""Unit tests for In-Memory Adapters — Phase 2.

Verifies that each InMemory adapter correctly implements its Port contract.
Tests are grouped by adapter:
1. InMemoryGraphRepository     (IGraphRepository)
2. InMemoryVectorRepository    (IVectorRepository)
3. InMemoryDatabaseRepository  (IDatabaseRepository)
4. InMemoryLlmProvider         (ILlmProvider)
5. InMemoryEmbeddingProvider   (IEmbeddingProvider)
6. Port ABC compliance         (cannot instantiate abstract classes)
"""

from __future__ import annotations

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# 1. InMemoryGraphRepository
# ═══════════════════════════════════════════════════════════════════════════


class TestInMemoryGraphRepository:
    @pytest.fixture
    def repo(self):
        from adapters.in_memory.graph_repository import InMemoryGraphRepository
        return InMemoryGraphRepository()

    @pytest.fixture
    def seeded_repo(self):
        from adapters.in_memory.graph_repository import InMemoryGraphRepository
        r = InMemoryGraphRepository()
        r.seed_disease(
            "Tiểu đường",
            description="Bệnh rối loạn chuyển hóa",
            symptoms=["Khát nước", "Đi tiểu nhiều", "Mệt mỏi"],
            treatments=["Insulin", "Metformin"],
            medicines=["Metformin", "Insulin"],
            category="Nội tiết",
        )
        r.seed_disease("Viêm phổi", symptoms=["Ho", "Sốt"])
        return r

    @pytest.mark.asyncio
    async def test_implements_port(self, repo):
        from ports.graph import IGraphRepository
        assert isinstance(repo, IGraphRepository)

    @pytest.mark.asyncio
    async def test_check_connectivity_true_by_default(self, repo):
        assert await repo.check_connectivity() is True

    @pytest.mark.asyncio
    async def test_close_disconnects(self, repo):
        await repo.close()
        assert await repo.check_connectivity() is False

    @pytest.mark.asyncio
    async def test_execute_cypher_returns_preset(self, repo):
        preset = [{"id": 1, "name": "Test"}]
        repo.set_cypher_results(preset)
        result = await repo.execute_cypher("MATCH (n) RETURN n")
        assert result == preset

    @pytest.mark.asyncio
    async def test_execute_cypher_returns_empty_by_default(self, repo):
        result = await repo.execute_cypher("MATCH (n) RETURN n")
        assert result == []

    @pytest.mark.asyncio
    async def test_execute_cypher_with_params(self, repo):
        repo.set_cypher_results([{"disease_name": "Tiểu đường"}])
        result = await repo.execute_cypher(
            "MATCH (d:Disease {name: $name}) RETURN d",
            params={"name": "Tiểu đường"},
        )
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_find_diseases_by_name_exact(self, seeded_repo):
        results = await seeded_repo.find_diseases_by_name("Tiểu đường")
        assert "Tiểu đường" in results

    @pytest.mark.asyncio
    async def test_find_diseases_by_name_partial(self, seeded_repo):
        results = await seeded_repo.find_diseases_by_name("tiểu")  # lowercase
        assert "Tiểu đường" in results

    @pytest.mark.asyncio
    async def test_find_diseases_by_name_no_match(self, seeded_repo):
        results = await seeded_repo.find_diseases_by_name("gout")
        assert results == []

    @pytest.mark.asyncio
    async def test_find_diseases_by_name_limit(self, seeded_repo):
        # Add more diseases
        for i in range(10):
            seeded_repo.seed_disease(f"Bệnh test {i}")
        results = await seeded_repo.find_diseases_by_name("test", limit=3)
        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_get_disease_detail_found(self, seeded_repo):
        detail = await seeded_repo.get_disease_detail("Tiểu đường")
        assert detail is not None
        assert detail["disease_name"] == "Tiểu đường"
        assert "Khát nước" in detail["symptoms"]

    @pytest.mark.asyncio
    async def test_get_disease_detail_not_found(self, seeded_repo):
        detail = await seeded_repo.get_disease_detail("Bệnh lạ")
        assert detail is None

    @pytest.mark.asyncio
    async def test_get_schema_info(self, seeded_repo):
        schema = await seeded_repo.get_schema_info()
        assert "nodes" in schema
        assert "relationships" in schema
        # Should reflect seeded count
        node_counts = {n["label"]: n["count"] for n in schema["nodes"]}
        assert node_counts.get("Disease", 0) == 2

    @pytest.mark.asyncio
    async def test_execute_cypher_raises_when_disconnected(self, repo):
        await repo.close()
        with pytest.raises(RuntimeError, match="not connected"):
            await repo.execute_cypher("MATCH (n) RETURN n")

    @pytest.mark.asyncio
    async def test_cypher_results_are_independent_copies(self, repo):
        """Mutating returned list should not affect internal state."""
        repo.set_cypher_results([{"id": 1}])
        result = await repo.execute_cypher("")
        result.append({"id": 2})
        result2 = await repo.execute_cypher("")
        assert len(result2) == 1


# ═══════════════════════════════════════════════════════════════════════════
# 2. InMemoryVectorRepository
# ═══════════════════════════════════════════════════════════════════════════


class TestInMemoryVectorRepository:
    @pytest.fixture
    def repo(self):
        from adapters.in_memory.vector_repository import InMemoryVectorRepository
        return InMemoryVectorRepository()

    @pytest.fixture
    def seeded_repo(self):
        from adapters.in_memory.vector_repository import InMemoryVectorRepository
        r = InMemoryVectorRepository()
        r.seed_answer("tiểu đường", "Tiểu đường là bệnh mãn tính rối loạn chuyển hóa glucose.")
        r.seed_answer("viêm phổi", "Viêm phổi gây ho và sốt.", mode="local")
        return r

    @pytest.mark.asyncio
    async def test_implements_port(self, repo):
        from ports.vector import IVectorRepository
        assert isinstance(repo, IVectorRepository)

    @pytest.mark.asyncio
    async def test_query_matched_answer(self, seeded_repo):
        result = await seeded_repo.query("tiểu đường là gì?")
        assert "Tiểu đường" in result["answer"]
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_query_case_insensitive_matching(self, seeded_repo):
        result = await seeded_repo.query("TIỂU ĐƯỜNG là gì?")
        assert result["success"] is True
        assert "Tiểu đường" in result["answer"]

    @pytest.mark.asyncio
    async def test_query_default_answer_on_miss(self, seeded_repo):
        result = await seeded_repo.query("bệnh lạ không có trong DB")
        assert result["success"] is True
        assert "Xin lỗi" in result["answer"]

    @pytest.mark.asyncio
    async def test_query_custom_default_answer(self, repo):
        repo.set_default_answer("Không tìm thấy kết quả.")
        result = await repo.query("bất cứ câu hỏi nào")
        assert result["answer"] == "Không tìm thấy kết quả."

    @pytest.mark.asyncio
    async def test_query_unhealthy_returns_failure(self, repo):
        repo._healthy = False
        result = await repo.query("tiểu đường")
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_query_mode_passthrough(self, seeded_repo):
        result = await seeded_repo.query("viêm phổi", mode="local")
        # seeded with mode="local"
        assert result["mode"] == "local"

    @pytest.mark.asyncio
    async def test_query_stream_yields_chunks(self, seeded_repo):
        mode, stream = await seeded_repo.query_stream("tiểu đường")
        chunks = [chunk async for chunk in stream]
        assert len(chunks) > 0
        full = "".join(chunks).strip()
        assert "Tiểu đường" in full

    @pytest.mark.asyncio
    async def test_query_stream_mode_returned(self, repo):
        mode, stream = await repo.query_stream("câu hỏi bất kỳ", mode="hybrid")
        assert mode == "hybrid"
        # Consume stream
        async for _ in stream:
            pass

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, repo):
        health = await repo.health_check()
        assert health["lightrag"] == "initialized"
        assert health["llm_server"] == "available"

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, repo):
        repo._healthy = False
        health = await repo.health_check()
        assert health["lightrag"] == "error"
        assert health["llm_server"] == "unavailable"

    @pytest.mark.asyncio
    async def test_seed_answer_extra_fields(self, repo):
        repo.seed_answer("gout", "Gout là bệnh khớp.", extra_field="extra_value")
        result = await repo.query("gout")
        assert result.get("extra_field") == "extra_value"


# ═══════════════════════════════════════════════════════════════════════════
# 3. InMemoryDatabaseRepository
# ═══════════════════════════════════════════════════════════════════════════


class TestInMemoryDatabaseRepository:
    @pytest.fixture
    def db(self):
        from adapters.in_memory.database import InMemoryDatabaseRepository
        return InMemoryDatabaseRepository()

    def test_implements_port(self, db):
        from ports.database import IDatabaseRepository
        assert isinstance(db, IDatabaseRepository)

    def test_fetch_one_returns_preset(self, db):
        expected = {"id": "user-1", "email": "test@example.com", "role": "user"}
        db.set_fetch_one_result(expected)
        result = db.fetch_one("SELECT * FROM users WHERE id = %s", ("user-1",))
        assert result == expected

    def test_fetch_one_returns_none_when_empty(self, db):
        result = db.fetch_one("SELECT * FROM users WHERE id = %s", ("missing",))
        assert result is None

    def test_fetch_one_queues_multiple(self, db):
        db.set_fetch_one_result({"id": "1"})
        db.set_fetch_one_result({"id": "2"})
        r1 = db.fetch_one("SELECT 1")
        r2 = db.fetch_one("SELECT 1")
        assert r1 == {"id": "1"}
        assert r2 == {"id": "2"}

    def test_fetch_one_returns_none_after_queue_exhausted(self, db):
        db.set_fetch_one_result({"id": "1"})
        db.fetch_one("SELECT 1")
        result = db.fetch_one("SELECT 1")
        assert result is None

    def test_fetch_all_returns_preset(self, db):
        rows = [{"id": "1", "role": "user"}, {"id": "2", "role": "admin"}]
        db.set_fetch_all_result(rows)
        result = db.fetch_all("SELECT * FROM users")
        assert result == rows

    def test_fetch_all_returns_empty_when_none_preset(self, db):
        result = db.fetch_all("SELECT * FROM users")
        assert result == []

    def test_fetch_all_queues_multiple(self, db):
        db.set_fetch_all_result([{"id": "1"}])
        db.set_fetch_all_result([{"id": "2"}, {"id": "3"}])
        r1 = db.fetch_all("SELECT 1")
        r2 = db.fetch_all("SELECT 1")
        assert len(r1) == 1
        assert len(r2) == 2

    def test_execute_is_noop(self, db):
        # Should not raise
        db.execute(
            "INSERT INTO conversations (id, user_id) VALUES (%s, %s)",
            ("conv-1", "user-1"),
        )

    def test_transaction_context_manager(self, db):
        """transaction() should yield and not raise."""
        with db.transaction() as conn:
            assert conn is not None

    def test_transaction_yields_self(self, db):
        with db.transaction() as conn:
            assert conn is db

    def test_fetch_one_in_tx_delegates(self, db):
        db.set_fetch_one_result({"id": "tx-1"})
        with db.transaction() as conn:
            result = db.fetch_one_in_tx(conn, "SELECT 1")
        assert result == {"id": "tx-1"}

    def test_execute_in_tx_is_noop(self, db):
        with db.transaction() as conn:
            db.execute_in_tx(conn, "UPDATE users SET role = %s WHERE id = %s", ("admin", "1"))

    def test_execute_many_in_tx(self, db):
        rows = [("1", "user"), ("2", "admin"), ("3", "reviewer")]
        with db.transaction() as conn:
            db.execute_many_in_tx(
                conn,
                "INSERT INTO users (id, role) VALUES (%s, %s)",
                rows,
            )

    def test_seed_table(self, db):
        """seed_table is kept for API compatibility (no-op in upgraded impl)."""
        # Should not raise
        db.seed_table("users", [
            {"id": "1", "email": "a@b.com"},
            {"id": "2", "email": "c@d.com"},
        ])
        # New impl uses dedicated stores; seed_table is a no-op for legacy compat.
        assert True  # Method exists and doesn't raise


    def test_transaction_rollback_on_exception(self, db):
        """Exceptions inside transaction should propagate cleanly."""
        with pytest.raises(ValueError, match="test error"):
            with db.transaction():
                raise ValueError("test error")


# ═══════════════════════════════════════════════════════════════════════════
# 4. InMemoryLlmProvider
# ═══════════════════════════════════════════════════════════════════════════


class TestInMemoryLlmProvider:
    @pytest.fixture
    def llm(self):
        from adapters.in_memory.llm_provider import InMemoryLlmProvider
        return InMemoryLlmProvider()

    @pytest.mark.asyncio
    async def test_implements_port(self, llm):
        from ports.llm import ILlmProvider
        assert isinstance(llm, ILlmProvider)

    @pytest.mark.asyncio
    async def test_returns_default_response(self, llm):
        result = await llm.chat_completion([{"role": "user", "content": "Xin chào"}])
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_set_response(self, llm):
        llm.set_response("Tiểu đường type 2 là bệnh mãn tính.")
        result = await llm.chat_completion([{"role": "user", "content": "Tiểu đường?"}])
        assert result == "Tiểu đường type 2 là bệnh mãn tính."

    @pytest.mark.asyncio
    async def test_set_responses_consumed_in_order(self, llm):
        llm.set_responses(["Câu trả lời 1", "Câu trả lời 2", "Câu trả lời 3"])
        msgs = [{"role": "user", "content": "q"}]
        r1 = await llm.chat_completion(msgs)
        r2 = await llm.chat_completion(msgs)
        r3 = await llm.chat_completion(msgs)
        assert r1 == "Câu trả lời 1"
        assert r2 == "Câu trả lời 2"
        assert r3 == "Câu trả lời 3"

    @pytest.mark.asyncio
    async def test_last_response_repeats(self, llm):
        llm.set_responses(["First", "Last"])
        msgs = [{"role": "user", "content": "q"}]
        await llm.chat_completion(msgs)  # "First"
        r2 = await llm.chat_completion(msgs)  # "Last"
        r3 = await llm.chat_completion(msgs)  # "Last" again
        assert r2 == "Last"
        assert r3 == "Last"

    @pytest.mark.asyncio
    async def test_call_count_increments(self, llm):
        msgs = [{"role": "user", "content": "q"}]
        assert llm.call_count == 0
        await llm.chat_completion(msgs)
        await llm.chat_completion(msgs)
        assert llm.call_count == 2

    @pytest.mark.asyncio
    async def test_call_log_records_messages(self, llm):
        msgs = [{"role": "user", "content": "Tiểu đường?"}]
        await llm.chat_completion(msgs)
        assert llm.call_log[0] == msgs

    @pytest.mark.asyncio
    async def test_unavailable_raises(self, llm):
        llm.set_available(False)
        with pytest.raises(RuntimeError, match="unavailable"):
            await llm.chat_completion([{"role": "user", "content": "test"}])

    @pytest.mark.asyncio
    async def test_check_availability_true(self, llm):
        assert await llm.check_availability() is True

    @pytest.mark.asyncio
    async def test_check_availability_false(self, llm):
        llm.set_available(False)
        assert await llm.check_availability() is False

    @pytest.mark.asyncio
    async def test_stream_yields_chunks(self, llm):
        llm.set_response("Đây là câu trả lời dài hơn gồm nhiều từ")
        stream = await llm.chat_completion_stream([{"role": "user", "content": "q"}])
        chunks = [chunk async for chunk in stream]
        assert len(chunks) > 1
        full = "".join(chunks).strip()
        assert "Đây là câu trả lời" in full

    @pytest.mark.asyncio
    async def test_stream_uses_same_response_logic(self, llm):
        llm.set_response("Chỉ một câu")
        stream = await llm.chat_completion_stream([{"role": "user", "content": "q"}])
        chunks = [chunk async for chunk in stream]
        assert "Chỉ" in "".join(chunks)

    @pytest.mark.asyncio
    async def test_temperature_and_max_tokens_accepted(self, llm):
        """Port contract: these params should not raise."""
        result = await llm.chat_completion(
            [{"role": "user", "content": "q"}],
            temperature=0.7,
            max_tokens=512,
        )
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_call_log_is_independent_copy(self, llm):
        msgs = [{"role": "user", "content": "test"}]
        await llm.chat_completion(msgs)
        log = llm.call_log
        log.append("tampered")
        assert len(llm.call_log) == 1  # Internal state unchanged


# ═══════════════════════════════════════════════════════════════════════════
# 5. InMemoryEmbeddingProvider
# ═══════════════════════════════════════════════════════════════════════════


class TestInMemoryEmbeddingProvider:
    @pytest.fixture
    def provider(self):
        from adapters.in_memory.llm_provider import InMemoryEmbeddingProvider
        return InMemoryEmbeddingProvider()

    @pytest.mark.asyncio
    async def test_implements_port(self, provider):
        from ports.llm import IEmbeddingProvider
        assert isinstance(provider, IEmbeddingProvider)

    @pytest.mark.asyncio
    async def test_embed_returns_correct_count(self, provider):
        texts = ["Tiểu đường", "Viêm phổi", "Cao huyết áp"]
        result = await provider.embed(texts)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_embed_returns_correct_dimension(self, provider):
        result = await provider.embed(["test"])
        assert len(result[0]) == 1024  # default dim

    @pytest.mark.asyncio
    async def test_embed_custom_dimension(self):
        from adapters.in_memory.llm_provider import InMemoryEmbeddingProvider
        provider = InMemoryEmbeddingProvider(dim=384)
        result = await provider.embed(["test"])
        assert len(result[0]) == 384

    @pytest.mark.asyncio
    async def test_embed_returns_floats(self, provider):
        result = await provider.embed(["test"])
        assert all(isinstance(v, float) for v in result[0])

    @pytest.mark.asyncio
    async def test_embed_empty_list(self, provider):
        result = await provider.embed([])
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_unavailable_raises(self, provider):
        provider._available = False
        with pytest.raises(RuntimeError, match="unavailable"):
            await provider.embed(["test"])

    @pytest.mark.asyncio
    async def test_check_availability_true(self, provider):
        assert await provider.check_availability() is True


# ═══════════════════════════════════════════════════════════════════════════
# 6. Port ABC compliance (cannot instantiate abstract ports)
# ═══════════════════════════════════════════════════════════════════════════


class TestPortAbstractCompliance:
    def test_igraph_repository_is_abstract(self):
        from ports.graph import IGraphRepository
        with pytest.raises(TypeError):
            IGraphRepository()  # type: ignore

    def test_ivector_repository_is_abstract(self):
        from ports.vector import IVectorRepository
        with pytest.raises(TypeError):
            IVectorRepository()  # type: ignore

    def test_idatabase_repository_is_abstract(self):
        from ports.database import IDatabaseRepository
        with pytest.raises(TypeError):
            IDatabaseRepository()  # type: ignore

    def test_illm_provider_is_abstract(self):
        from ports.llm import ILlmProvider
        with pytest.raises(TypeError):
            ILlmProvider()  # type: ignore

    def test_iembedding_provider_is_abstract(self):
        from ports.llm import IEmbeddingProvider
        with pytest.raises(TypeError):
            IEmbeddingProvider()  # type: ignore

    def test_iauth_provider_is_abstract(self):
        from ports.auth import IAuthProvider
        with pytest.raises(TypeError):
            IAuthProvider()  # type: ignore
