"""Use Cases — Application layer orchestrating domain logic + ports.

Public API:
    AnswerQuestionUseCase   — Execute the hybrid QA pipeline
    AnswerQuestionStreamUseCase — Streaming variant
    ManageConversationUseCase   — Conversation + message CRUD
    ManageFeedbackUseCase       — Feedback persistence
    ExploreKnowledgeUseCase     — Read-only KG browsing
    ManagePreferencesUseCase    — User preference CRUD
    AdminAnalyticsUseCase       — Admin metrics + review queue
"""

from use_cases.answer_question import AnswerQuestionUseCase, AIServiceResult
from use_cases.answer_question_stream import AnswerQuestionStreamUseCase
from use_cases.conversation_workflow import (
    ConversationAnswerResult,
    ExportConversationUseCase,
    ExportedConversation,
    SendConversationMessageUseCase,
    StreamConversationMessageUseCase,
    StreamUseCaseEvent,
)
from use_cases.manage_conversation import ManageConversationUseCase
from use_cases.manage_feedback import ManageFeedbackUseCase, FeedbackInput, FeedbackOutput
from use_cases.explore_knowledge import ExploreKnowledgeUseCase, DiseaseListResult
from use_cases.manage_preferences import ManagePreferencesUseCase
from use_cases.admin_analytics import AdminAnalyticsUseCase, AdminMetrics, ReviewQueueResult

__all__ = [
    "AnswerQuestionUseCase",
    "AnswerQuestionStreamUseCase",
    "AIServiceResult",
    "ConversationAnswerResult",
    "ExportConversationUseCase",
    "ExportedConversation",
    "SendConversationMessageUseCase",
    "StreamConversationMessageUseCase",
    "StreamUseCaseEvent",
    "ManageConversationUseCase",
    "ManageFeedbackUseCase",
    "FeedbackInput",
    "FeedbackOutput",
    "ExploreKnowledgeUseCase",
    "DiseaseListResult",
    "ManagePreferencesUseCase",
    "AdminAnalyticsUseCase",
    "AdminMetrics",
    "ReviewQueueResult",
]
