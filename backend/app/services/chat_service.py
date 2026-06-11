"""Conversation and chat service skeleton."""

from app.api_gateway.errors import not_implemented


async def create_conversation(*, user_id: str, payload: object) -> None:
    raise not_implemented(f"create conversation for user {user_id}")


async def list_conversations(*, user_id: str) -> None:
    raise not_implemented(f"list conversations for user {user_id}")


async def get_conversation(*, user_id: str, conversation_id: str) -> None:
    raise not_implemented(f"get conversation {conversation_id} for user {user_id}")


async def create_message(*, user_id: str, conversation_id: str, payload: object) -> None:
    raise not_implemented(f"create message in conversation {conversation_id} for user {user_id}")

