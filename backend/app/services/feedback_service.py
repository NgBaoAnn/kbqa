"""Feedback service skeleton."""

from app.api_gateway.errors import not_implemented


async def create_feedback(*, user_id: str, message_id: str, payload: object) -> None:
    raise not_implemented(f"create feedback for message {message_id} by user {user_id}")

