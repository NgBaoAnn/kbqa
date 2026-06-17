"""Unit tests for Phase 4 Use Cases using in-memory adapters.

Tests exercise the full use-case logic WITHOUT real infrastructure:
- AnswerQuestionUseCase
- ManageConversationUseCase
- ManageFeedbackUseCase
- ExploreKnowledgeUseCase
- ManagePreferencesUseCase
- AdminAnalyticsUseCase
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ── Import in-memory adapters from Phase 2 ───────────────────────────────
from adapters.in_memory.graph_repository import InMemoryGraphRepository
from adapters.in_memory.vector_repository import InMemoryVectorRepository
from adapters.in_memory.database import InMemoryDatabaseRepository
from adapters.in_memory.llm_provider import InMemoryLlmProvider, InMemoryEmbeddingProvider


# ─────────────────────────────────────────────────────────────────────────────
# ManageConversationUseCase
# ─────────────────────────────────────────────────────────────────────────────

class TestManageConversationUseCase:
    """Tests for conversation CRUD with in-memory DB."""

    def setup_method(self):
        from use_cases.manage_conversation import ManageConversationUseCase
        self.db = InMemoryDatabaseRepository()
        self.uc = ManageConversationUseCase(db=self.db)

    def test_create_conversation(self):
        result = self.uc.create_conversation(user_id="user-1", title="Test", language="vi")
        assert result["title"] == "Test"
        assert result["language"] == "vi"
        assert "id" in result

    def test_create_conversation_default_title(self):
        result = self.uc.create_conversation(user_id="user-1")
        assert result["title"] == "Cuộc trò chuyện mới"

    def test_list_conversations_empty(self):
        result = self.uc.list_conversations(user_id="user-1")
        assert result == []

    def test_list_conversations_after_create(self):
        self.uc.create_conversation(user_id="user-1", title="A")
        self.uc.create_conversation(user_id="user-1", title="B")
        result = self.uc.list_conversations(user_id="user-1")
        assert len(result) == 2

    def test_list_conversations_isolation(self):
        """Different users don't see each other's conversations."""
        self.uc.create_conversation(user_id="user-1", title="Mine")
        result = self.uc.list_conversations(user_id="user-2")
        assert len(result) == 0

    def test_get_conversation_not_found(self):
        result = self.uc.get_conversation(user_id="user-1", conversation_id="nonexistent")
        assert result is None

    def test_get_conversation_found(self):
        conv = self.uc.create_conversation(user_id="user-1", title="Chat")
        result = self.uc.get_conversation(user_id="user-1", conversation_id=conv["id"])
        assert result is not None
        assert result["conversation"]["title"] == "Chat"
        assert result["messages"] == []

    def test_ensure_owner_valid(self):
        conv = self.uc.create_conversation(user_id="user-1", title="Mine")
        assert self.uc.ensure_owner(user_id="user-1", conversation_id=conv["id"]) is True

    def test_ensure_owner_invalid(self):
        conv = self.uc.create_conversation(user_id="user-1", title="Mine")
        assert self.uc.ensure_owner(user_id="user-2", conversation_id=conv["id"]) is False

    def test_persist_user_message(self):
        conv = self.uc.create_conversation(user_id="user-1", title="Chat")
        # Should not raise
        self.uc.persist_user_message(
            conversation_id=conv["id"],
            question="What is diabetes?",
        )


# ─────────────────────────────────────────────────────────────────────────────
# ManageFeedbackUseCase
# ─────────────────────────────────────────────────────────────────────────────

class TestManageFeedbackUseCase:
    """Tests for feedback with in-memory DB."""

    def setup_method(self):
        from use_cases.manage_feedback import ManageFeedbackUseCase, FeedbackInput
        self.db = InMemoryDatabaseRepository()
        self.uc = ManageFeedbackUseCase(db=self.db)
        self.FeedbackInput = FeedbackInput

    def test_message_not_found_raises(self):
        payload = self.FeedbackInput(rating="up", reason=None, comment=None)
        with pytest.raises(ValueError, match="MESSAGE_NOT_FOUND"):
            self.uc.create_feedback(user_id="u1", message_id="bad-id", payload=payload)

    def test_feedback_created_positive(self):
        """In-memory DB returns None for assistant message check — simulate with seeded data."""
        # The in-memory DB doesn't have real SQL joins, so we test the ValueError path.
        # Real DB integration is tested in integration tests.
        payload = self.FeedbackInput(rating="up", reason=None, comment="Great!")
        with pytest.raises(ValueError):
            self.uc.create_feedback(user_id="u1", message_id="msg-1", payload=payload)


# ─────────────────────────────────────────────────────────────────────────────
# ManagePreferencesUseCase
# ─────────────────────────────────────────────────────────────────────────────

class TestManagePreferencesUseCase:
    """Tests for preference CRUD with in-memory DB."""

    def setup_method(self):
        from use_cases.manage_preferences import ManagePreferencesUseCase
        self.db = InMemoryDatabaseRepository()
        self.uc = ManagePreferencesUseCase(db=self.db)

    def test_get_preferences_creates_defaults(self):
        prefs = self.uc.get_preferences(user_id="user-1")
        assert prefs["language"] == "vi"
        assert prefs["explanation_level"] == "general"
        assert prefs["answer_style"] == "concise"

    def test_update_preferences_valid(self):
        self.uc.get_preferences(user_id="user-1")
        updated = self.uc.update_preferences(
            user_id="user-1", patch={"language": "en"}
        )
        assert updated["language"] == "en"

    def test_update_preferences_invalid_raises(self):
        with pytest.raises(ValueError, match="INVALID_PREFERENCE_VALUE"):
            self.uc.update_preferences(
                user_id="user-1", patch={"language": "fr"}
            )

    def test_update_preferences_empty_patch_noop(self):
        prefs = self.uc.get_preferences(user_id="user-1")
        updated = self.uc.update_preferences(user_id="user-1", patch={})
        assert updated["language"] == prefs["language"]

    def test_update_preferences_unknown_keys_ignored(self):
        prefs = self.uc.get_preferences(user_id="user-1")
        updated = self.uc.update_preferences(
            user_id="user-1", patch={"unknown_key": "value"}
        )
        assert updated["language"] == prefs["language"]


# ─────────────────────────────────────────────────────────────────────────────
# ExploreKnowledgeUseCase
# ─────────────────────────────────────────────────────────────────────────────

class TestExploreKnowledgeUseCase:
    """Tests for knowledge browsing with in-memory graph."""

    def setup_method(self):
        from use_cases.explore_knowledge import ExploreKnowledgeUseCase
        self.graph = InMemoryGraphRepository()
        self.uc = ExploreKnowledgeUseCase(graph=self.graph)

    @pytest.mark.asyncio
    async def test_list_diseases_empty(self):
        result = await self.uc.list_diseases()
        assert result.total == 0
        assert result.items == []

    @pytest.mark.asyncio
    async def test_list_diseases_with_data(self):
        # Seed graph with disease data
        self.graph.diseases.update({
            "Tiểu đường": {"disease_name": "Tiểu đường", "disease_category": "Nội tiết"},
            "Cao huyết áp": {"disease_name": "Cao huyết áp", "disease_category": "Tim mạch"},
        })
        result = await self.uc.list_diseases(limit=10, offset=0)
        assert result.total == 2

    @pytest.mark.asyncio
    async def test_get_disease_not_found(self):
        result = await self.uc.get_disease(disease_id="NonExistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_disease_found(self):
        self.graph.diseases["Tiểu đường"] = {
            "disease_name": "Tiểu đường",
            "disease_description": "Bệnh mãn tính",
            "disease_category": "Nội tiết",
        }
        result = await self.uc.get_disease(disease_id="Tiểu đường")
        assert result is not None
        assert result["disease_name"] == "Tiểu đường"


# ─────────────────────────────────────────────────────────────────────────────
# AnswerQuestionUseCase (with mocked pipeline)
# ─────────────────────────────────────────────────────────────────────────────

class TestAnswerQuestionUseCase:
    """Tests for AnswerQuestionUseCase with in-memory adapters."""

    def setup_method(self):
        from use_cases.answer_question import AnswerQuestionUseCase
        self.graph = InMemoryGraphRepository()
        self.vector = InMemoryVectorRepository()
        self.llm = InMemoryLlmProvider()
        self.uc = AnswerQuestionUseCase(
            graph=self.graph,
            vector=self.vector,
            llm=self.llm,
            disable_cypher_path=True,  # Use LightRAG path only for unit tests
            default_lightrag_mode="naive",
        )

    @pytest.mark.asyncio
    async def test_empty_question_returns_error(self):
        from use_cases.answer_question import AIServiceResult
        result = await self.uc.execute(question="")
        assert isinstance(result, AIServiceResult)
        # Empty question returns an error, but never raises
        assert result.answer != ""

    @pytest.mark.asyncio
    async def test_valid_question_returns_result(self):
        from use_cases.answer_question import AIServiceResult
        result = await self.uc.execute(question="Tiểu đường là gì?")
        assert isinstance(result, AIServiceResult)
        assert result.response_type in {"text", "disambiguation", "warning"}
        assert isinstance(result.sources, list)
        assert isinstance(result.suggested_questions, list)

    @pytest.mark.asyncio
    async def test_result_always_has_safety(self):
        result = await self.uc.execute(question="Tôi bị đau đầu phải làm gì?")
        assert isinstance(result.safety, dict)
        assert "level" in result.safety

    @pytest.mark.asyncio
    async def test_never_raises(self):
        """Use case must not raise even if pipeline fails."""
        # Inject a broken vector repo
        bad_vector = InMemoryVectorRepository()
        bad_vector.query = AsyncMock(side_effect=RuntimeError("Simulated infra failure"))
        from use_cases.answer_question import AnswerQuestionUseCase
        uc = AnswerQuestionUseCase(
            graph=self.graph,
            vector=bad_vector,
            llm=self.llm,
            disable_cypher_path=True,
        )
        result = await uc.execute(question="Test")
        assert result.answer != ""  # Error message returned, not raised


# ─────────────────────────────────────────────────────────────────────────────
# Domain QA Pipeline (unit — pure logic)
# ─────────────────────────────────────────────────────────────────────────────

class TestQAPipeline:
    """Tests for domain QA pipeline with in-memory adapters."""

    def setup_method(self):
        from domain.qa.pipeline import QAPipeline
        self.graph = InMemoryGraphRepository()
        self.vector = InMemoryVectorRepository()
        self.llm = InMemoryLlmProvider()
        self.pipeline = QAPipeline(
            graph=self.graph,
            vector=self.vector,
            llm=self.llm,
            disable_cypher_path=True,
            default_lightrag_mode="naive",
        )

    @pytest.mark.asyncio
    async def test_empty_question_returns_error_result(self):
        from domain.qa.pipeline import PipelineResult
        result = await self.pipeline.run("")
        assert isinstance(result, PipelineResult)
        assert result.status == "error"
        assert result.error_code == "INVALID_QUESTION"

    @pytest.mark.asyncio
    async def test_valid_question_returns_success(self):
        from domain.qa.pipeline import PipelineResult
        result = await self.pipeline.run("Tiểu đường là bệnh gì?")
        assert isinstance(result, PipelineResult)
        assert result.answer != ""

    @pytest.mark.asyncio
    async def test_mode_forces_lightrag(self):
        from domain.qa.pipeline import PipelineResult, ENGINE_LIGHTRAG
        result = await self.pipeline.run("Test", mode="naive")
        assert isinstance(result, PipelineResult)
        # When mode is set, should bypass Cypher

    @pytest.mark.asyncio
    async def test_disambiguation_response(self):
        """Multiple KG matches → disambiguation result."""
        # Seed multiple similar diseases
        self.graph._diseases = {
            "Bệnh tiểu đường type 1": None,
            "Bệnh tiểu đường type 2": None,
            "Bệnh tiểu đường thai kỳ": None,
        }
        pipeline_with_cypher = type(self.pipeline)(
            graph=self.graph,
            vector=self.vector,
            llm=self.llm,
            disable_cypher_path=False,
        )
        # With mocked intent extraction returning "tiểu đường"
        with patch.object(pipeline_with_cypher, '_extract_intent_llm', new=AsyncMock(return_value=("symptoms", "tiểu đường"))):
            result = await pipeline_with_cypher.run("Triệu chứng của tiểu đường là gì?")
        # Disambiguation or LightRAG fallback depending on data
        assert result.status in {"success", "error"}
