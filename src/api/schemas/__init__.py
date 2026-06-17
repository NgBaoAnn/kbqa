"""API Schemas package.

Quick imports::

    from api.schemas.requests import MessageCreateRequest, FeedbackCreateRequest
    from api.schemas.responses import ChatResponse, ConversationSummary
    from api.schemas.streaming import build_delta_event, build_final_event
"""

from api.schemas.requests import (
    ConversationCreateRequest,
    FeedbackCreateRequest,
    MessageCreateRequest,
    QueryRequest,
    UserPreferencesUpdateRequest,
)
from api.schemas.responses import (
    AdminMetricsResponse,
    ChatMetadata,
    ChatResponse,
    ChatSource,
    ChatSourceType,
    ConversationDetail,
    ConversationSummary,
    CurrentUserResponse,
    DiseaseDetailResponse,
    DiseaseListResponse,
    DiseaseSummary,
    FeedbackResponse,
    MessageFeedback,
    MessageRecord,
    MessageTraceResponse,
    ReviewItemRecord,
    ReviewQueueResponse,
    SafetyPayload,
    UserPreferencesResponse,
    VersionMetadata,
)
from api.schemas.streaming import (
    StreamDeltaPayload,
    StreamErrorPayload,
    StreamFinalPayload,
    StreamMetadataPayload,
    StreamSourcesPayload,
    StreamStagePayload,
    build_delta_event,
    build_error_event,
    build_final_event,
    build_metadata_event,
    build_sources_event,
    build_stage_event,
)

__all__ = [
    # Requests
    "ConversationCreateRequest",
    "FeedbackCreateRequest",
    "MessageCreateRequest",
    "QueryRequest",
    "UserPreferencesUpdateRequest",
    # Responses
    "AdminMetricsResponse",
    "ChatMetadata",
    "ChatResponse",
    "ChatSource",
    "ChatSourceType",
    "ConversationDetail",
    "ConversationSummary",
    "CurrentUserResponse",
    "DiseaseDetailResponse",
    "DiseaseListResponse",
    "DiseaseSummary",
    "FeedbackResponse",
    "MessageFeedback",
    "MessageRecord",
    "MessageTraceResponse",
    "ReviewItemRecord",
    "ReviewQueueResponse",
    "SafetyPayload",
    "UserPreferencesResponse",
    "VersionMetadata",
    # Streaming
    "StreamDeltaPayload",
    "StreamErrorPayload",
    "StreamFinalPayload",
    "StreamMetadataPayload",
    "StreamSourcesPayload",
    "StreamStagePayload",
    "build_delta_event",
    "build_error_event",
    "build_final_event",
    "build_metadata_event",
    "build_sources_event",
    "build_stage_event",
]
