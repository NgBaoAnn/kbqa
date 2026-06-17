"""LLM-backed intent extraction through the LLM port."""

from __future__ import annotations

import json
import logging

from domain.qa.intent_classifier import VALID_QUERY_TYPES, clean_entity
from ports.llm import ILlmProvider
from ports.qa import IIntentExtractor

logger = logging.getLogger(__name__)

INTENT_SYSTEM_PROMPT = """\
You classify a Vietnamese medical question about the VietMedKG knowledge graph.
Return EXACTLY one JSON object: {"query_type": "...", "entity": "..."}.

Valid query_type values:
symptoms, cause, check_method, susceptible_population, medicine, treatment,
advice, prevention, department, profile, linked_diseases,
find_by_symptom, find_by_check_method, find_by_medicine,
find_by_nutrition_avoid, find_by_nutrition_eat, find_by_prevention,
chain_linked_avoid, chain_linked_eat, unknown.

Forward intents use a Vietnamese disease name as entity.
Reverse intents use the constraint keyword as entity, not a disease name.
Strip question words and filler words such as "bệnh", "bị", "mắc", "gì", "nào".
If brackets contain a list, extract the bracket content and prefer the most representative item.
Return only JSON, no markdown."""


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
