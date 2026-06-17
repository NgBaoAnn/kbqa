"""Dependency Injection container for the KBQA application.

Creates and wires all real infrastructure adapters from Settings.
Use this in FastAPI lifespan context to manage adapter lifecycle.

Usage (FastAPI main.py)::

    from api.dependencies import AppContainer

    container: AppContainer | None = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global container
        container = await AppContainer.create()
        yield
        await container.close()

    def get_container() -> AppContainer:
        return container
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from api.config import Settings, settings as default_settings
from ports.auth import IAuthProvider
from ports.database import IDatabaseRepository
from ports.graph import IGraphRepository
from ports.llm import IEmbeddingProvider, ILlmProvider
from ports.qa import ICypherQaEngine, IIntentExtractor
from ports.vector import IVectorRepository
from use_cases.admin_analytics import AdminAnalyticsUseCase
from use_cases.answer_question import AnswerQuestionUseCase
from use_cases.answer_question_stream import AnswerQuestionStreamUseCase
from use_cases.explore_knowledge import ExploreKnowledgeUseCase
from use_cases.manage_conversation import ManageConversationUseCase
from use_cases.manage_feedback import ManageFeedbackUseCase
from use_cases.manage_preferences import ManagePreferencesUseCase

logger = logging.getLogger(__name__)


@dataclass
class AppContainer:
    """Holds all live infrastructure adapter instances and pre-built use cases.

    Attributes typed to Port interfaces so use-cases depend only on abstractions.
    Use cases are pre-built here to avoid constructing them per-request.
    """

    graph: IGraphRepository
    vector: IVectorRepository
    db: IDatabaseRepository
    auth: IAuthProvider
    llm: ILlmProvider
    embedding: IEmbeddingProvider
    intent_extractor: IIntentExtractor
    cypher_engine: ICypherQaEngine
    # Pre-built use cases (avoid re-instantiation per request)
    answer_question: AnswerQuestionUseCase
    answer_question_stream: AnswerQuestionStreamUseCase
    manage_conversation: ManageConversationUseCase
    manage_feedback: ManageFeedbackUseCase
    explore_knowledge: ExploreKnowledgeUseCase
    manage_preferences: ManagePreferencesUseCase
    admin_analytics: AdminAnalyticsUseCase
    version_metadata: dict[str, str]

    @classmethod
    async def create(cls, settings: Settings = default_settings) -> "AppContainer":
        """Build and warm-up all adapters from the provided Settings.

        By default this only constructs adapters. Expensive connectivity checks
        stay lazy so startup matches the legacy backend behavior.
        """
        from adapters.neo4j.graph_repository import Neo4jGraphRepository
        from adapters.supabase.database_repository import SupabaseDatabaseRepository
        from adapters.supabase.auth_provider import SupabaseAuthProvider
        from adapters.lightrag.vector_repository import LightragVectorRepository
        from adapters.ollama.llm_provider import OllamaLlmProvider, OllamaEmbeddingProvider
        from use_cases.cypher_qa_engine import CypherQaEngine
        from use_cases.intent_extractor import LlmIntentExtractor

        logger.info("Initializing AppContainer…")

        # ── Graph (Neo4j) ────────────────────────────────────────────────
        graph = Neo4jGraphRepository(
            uri=settings.neo4j_uri,
            username=settings.neo4j_username,
            password=settings.neo4j_password,
        )
        if settings.check_infra_on_startup and not await graph.check_connectivity():
            logger.warning("Neo4j connectivity check FAILED — Cypher path will not work")

        # ── Database (Supabase Postgres) ──────────────────────────────────
        db = SupabaseDatabaseRepository(db_url=settings.supabase_db_url or None)

        # ── Auth (Supabase JWT) ───────────────────────────────────────────
        auth = SupabaseAuthProvider(
            jwt_secret=settings.supabase_jwt_secret,
            db=db,
        )

        # ── LLM (Ollama) ──────────────────────────────────────────────────
        llm = OllamaLlmProvider(
            base_url=settings.llm_base_url,
            model_name=settings.llm_model_name,
            timeout_seconds=settings.llm_timeout_seconds,
        )

        # ── Embedding (Ollama) ────────────────────────────────────────────
        embedding = OllamaEmbeddingProvider(
            base_url=settings.embedding_base_url,
            model_name=settings.embedding_model,
            embedding_dim=settings.embedding_dim,
            timeout_seconds=settings.llm_timeout_seconds,
        )

        # ── Vector (LightRAG + Qdrant) ────────────────────────────────────
        vector = LightragVectorRepository(
            working_dir=settings.lightrag_working_dir,
            llm_base_url=settings.llm_base_url,
            llm_model_name=settings.llm_model_name,
            embedding_base_url=settings.embedding_base_url,
            embedding_model=settings.embedding_model,
            embedding_dim=settings.embedding_dim,
            kg_storage=settings.lightrag_kg_storage,
            vector_storage=settings.lightrag_vector_storage,
            doc_storage=settings.lightrag_doc_storage,
            neo4j_uri=settings.neo4j_uri,
            neo4j_username=settings.neo4j_username,
            neo4j_password=settings.neo4j_password,
            force_naive_mode=settings.force_lightrag_naive_mode,
            default_query_mode=settings.default_query_mode,
            llm_timeout_seconds=settings.llm_timeout_seconds,
        )
        intent_extractor = LlmIntentExtractor(llm=llm)
        cypher_engine = CypherQaEngine(llm=llm)

        # ── Use Cases ─────────────────────────────────────────────────────
        answer_question = AnswerQuestionUseCase(
            graph=graph,
            vector=vector,
            llm=llm,
            intent_extractor=intent_extractor,
            cypher_engine=cypher_engine,
            disable_cypher_path=settings.disable_cypher_path,
            default_lightrag_mode=settings.default_query_mode,
        )
        answer_question_stream = AnswerQuestionStreamUseCase(
            graph=graph,
            vector=vector,
            llm=llm,
            intent_extractor=intent_extractor,
            cypher_engine=cypher_engine,
            disable_cypher_path=settings.disable_cypher_path,
            default_lightrag_mode=settings.default_query_mode,
        )
        version_metadata = {
            "prompt_version": settings.prompt_version,
            "model_name": settings.model_name,
            "kg_version": settings.kg_version,
            "pipeline_version": settings.pipeline_version,
        }
        manage_conversation = ManageConversationUseCase(
            db=db,
            version_metadata=version_metadata,
        )
        manage_feedback = ManageFeedbackUseCase(db=db)
        explore_knowledge = ExploreKnowledgeUseCase(graph=graph)
        manage_preferences = ManagePreferencesUseCase(db=db)
        admin_analytics = AdminAnalyticsUseCase(db=db)

        logger.info("AppContainer ready.")
        return cls(
            graph=graph,
            vector=vector,
            db=db,
            auth=auth,
            llm=llm,
            embedding=embedding,
            intent_extractor=intent_extractor,
            cypher_engine=cypher_engine,
            answer_question=answer_question,
            answer_question_stream=answer_question_stream,
            manage_conversation=manage_conversation,
            manage_feedback=manage_feedback,
            explore_knowledge=explore_knowledge,
            manage_preferences=manage_preferences,
            admin_analytics=admin_analytics,
            version_metadata=version_metadata,
        )

    async def close(self) -> None:
        """Release all adapter resources."""
        try:
            await self.graph.close()
            logger.info("Neo4j driver closed.")
        except Exception as exc:
            logger.warning("Error closing Neo4j driver: %s", exc)
        logger.info("AppContainer shut down.")
