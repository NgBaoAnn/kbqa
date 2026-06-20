"""LLM-backed intent extraction through the LLM port."""

from __future__ import annotations

import json
import logging

from domain.qa.intent_classifier import VALID_QUERY_TYPES, clean_entity
from ports.llm import ILlmProvider
from ports.qa import IIntentExtractor
from prompts.loader import load_prompt

logger = logging.getLogger(__name__)

# Loaded from src/prompts/intent_system.md at import time.
# Keeping the name for backward-compatibility with existing callers/tests.
INTENT_SYSTEM_PROMPT: str = load_prompt("intent_system")



class LlmIntentExtractor(IIntentExtractor):
    """Use case service for structured intent extraction via ``ILlmProvider``."""

    def __init__(self, llm: ILlmProvider) -> None:
        self._llm = llm

    async def extract_intent(self, question: str) -> tuple[str | None, str | None]:
        """Return ``(query_type, entity)``; failures degrade to regex fallback."""
        try:
            raw = await self._llm.chat_completion(
                [
                    {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                    {"role": "user", "content": question},
                ],
                temperature=0.0,
                max_tokens=160,
            )
            raw = raw.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(lines[1:-1]) if len(lines) >= 3 else raw

            parsed = json.loads(raw)
            q_type = parsed.get("query_type") or "unknown"
            if q_type not in VALID_QUERY_TYPES:
                q_type = None

            entity_raw = parsed.get("entity") or None
            entity = clean_entity(str(entity_raw)) if entity_raw else None
            logger.info("LLM intent: type=%s entity=%r", q_type, entity)
            return q_type, entity
        except Exception as exc:
            logger.warning("LLM intent extraction failed: %s", exc)
            return None, None
