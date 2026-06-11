"""AI service adapter skeleton.

This module is the only backend service that should call `ai_engine` directly.
"""

from app.api_gateway.errors import not_implemented


async def answer_question(*, question: str, mode: str | None = None) -> None:
    raise not_implemented(f"answer question with mode={mode or 'auto'}")

