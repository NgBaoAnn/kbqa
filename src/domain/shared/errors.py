"""Domain-level exceptions for the KBQA system.

These exceptions model business failures and are independent of any
framework (FastAPI, HTTP, etc.).  The API layer is responsible for
mapping them to HTTP status codes.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain-level errors."""

    def __init__(self, message: str, *, error_code: str = "DOMAIN_ERROR") -> None:
        self.error_code = error_code
        super().__init__(message)


# ── QA Domain ──────────────────────────────────────────────────────────────


class IntentClassificationError(DomainError):
    """Raised when intent classification fails (both regex and LLM)."""

    def __init__(self, message: str = "Could not classify the question intent.") -> None:
        super().__init__(message, error_code="INTENT_CLASSIFICATION_FAILED")


class CypherGenerationError(DomainError):
    """Raised when the system cannot generate a valid Cypher query."""

    def __init__(self, message: str = "Cypher query generation failed.") -> None:
        super().__init__(message, error_code="CYPHER_GENERATION_FAILED")


class CypherValidationError(DomainError):
    """Raised when a generated Cypher query fails validation/sanitization."""

    def __init__(self, message: str = "Cypher query validation failed.") -> None:
        super().__init__(message, error_code="CYPHER_VALIDATION_FAILED")


class EntityNotFoundError(DomainError):
    """Raised when the target entity cannot be found in the knowledge graph."""

    def __init__(self, entity: str) -> None:
        super().__init__(
            f"Entity '{entity}' not found in the knowledge graph.",
            error_code="ENTITY_NOT_FOUND",
        )
        self.entity = entity


class PipelineError(DomainError):
    """Raised when the QA pipeline encounters an unrecoverable error."""

    def __init__(self, message: str = "Pipeline execution failed.") -> None:
        super().__init__(message, error_code="PIPELINE_ERROR")


class AnswerSynthesisError(DomainError):
    """Raised when LLM answer synthesis fails."""

    def __init__(self, message: str = "Answer synthesis failed.") -> None:
        super().__init__(message, error_code="ANSWER_SYNTHESIS_FAILED")


# ── Conversation Domain ───────────────────────────────────────────────────


class ConversationNotFoundError(DomainError):
    """Raised when a conversation ID does not exist or is inaccessible."""

    def __init__(self, conversation_id: str) -> None:
        super().__init__(
            f"Conversation '{conversation_id}' not found.",
            error_code="CONVERSATION_NOT_FOUND",
        )
        self.conversation_id = conversation_id


class MessageNotFoundError(DomainError):
    """Raised when a message ID does not exist."""

    def __init__(self, message_id: str) -> None:
        super().__init__(
            f"Message '{message_id}' not found.",
            error_code="MESSAGE_NOT_FOUND",
        )
        self.message_id = message_id


# ── User Domain ───────────────────────────────────────────────────────────


class AuthorizationError(DomainError):
    """Raised when a user lacks permission for the requested operation."""

    def __init__(self, message: str = "Insufficient permissions.") -> None:
        super().__init__(message, error_code="AUTHORIZATION_ERROR")


class UserNotFoundError(DomainError):
    """Raised when a user profile cannot be found."""

    def __init__(self, user_id: str) -> None:
        super().__init__(
            f"User '{user_id}' not found.",
            error_code="USER_NOT_FOUND",
        )
        self.user_id = user_id


# ── Infrastructure (surfaced through domain) ─────────────────────────────


class InfrastructureError(DomainError):
    """Raised when an infrastructure dependency is unavailable.

    Adapters catch infrastructure-specific exceptions and re-raise as
    this type so the domain/use-case layers stay decoupled.
    """

    def __init__(self, message: str, *, service: str = "unknown") -> None:
        super().__init__(message, error_code="INFRASTRUCTURE_ERROR")
        self.service = service
