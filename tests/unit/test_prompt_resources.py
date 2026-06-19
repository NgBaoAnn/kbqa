"""Prompt resource tests.

Verifies that:
1. The prompt loader can read all three prompt files without error.
2. The runtime constants in domain/use_cases/adapters match the .md files
   (parity test — prevents silent drift between file and code).
3. Each prompt file contains minimum expected content (non-empty, key phrases).
"""

from __future__ import annotations

import pytest
from pathlib import Path

# Load via the loader API (exercises lru_cache path too)
from prompts.loader import load_prompt


# ── 1. Loader API ─────────────────────────────────────────────────────────

def test_load_prompt_text_to_cypher_returns_non_empty() -> None:
    content = load_prompt("text_to_cypher")
    assert isinstance(content, str)
    assert len(content) > 100


def test_load_prompt_intent_system_returns_non_empty() -> None:
    content = load_prompt("intent_system")
    assert isinstance(content, str)
    assert len(content) > 100


def test_load_prompt_medical_user_returns_non_empty() -> None:
    content = load_prompt("medical_user")
    assert isinstance(content, str)
    assert len(content) > 5


def test_load_prompt_unknown_raises_file_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        load_prompt("__nonexistent_prompt__")


# ── 2. Runtime parity ─────────────────────────────────────────────────────

def test_schema_prompt_runtime_matches_file() -> None:
    """domain.qa.cypher_builder.SCHEMA_PROMPT must equal text_to_cypher.md."""
    from domain.qa.cypher_builder import SCHEMA_PROMPT
    assert SCHEMA_PROMPT == load_prompt("text_to_cypher")


def test_intent_system_prompt_runtime_matches_file() -> None:
    """use_cases.intent_extractor.INTENT_SYSTEM_PROMPT must equal intent_system.md."""
    from use_cases.intent_extractor import INTENT_SYSTEM_PROMPT
    assert INTENT_SYSTEM_PROMPT == load_prompt("intent_system")


def test_medical_user_prompt_runtime_matches_file() -> None:
    """adapters.lightrag.vector_repository._MEDICAL_USER_PROMPT must equal medical_user.md."""
    from adapters.lightrag.vector_repository import _MEDICAL_USER_PROMPT
    assert _MEDICAL_USER_PROMPT == load_prompt("medical_user")


# ── 3. Content smoke-tests ────────────────────────────────────────────────

def test_text_to_cypher_contains_schema_keywords() -> None:
    content = load_prompt("text_to_cypher")
    for kw in ("Disease", "HAS_SYMPTOM", "LIMIT", "Cypher"):
        assert kw in content, f"Expected keyword '{kw}' in text_to_cypher.md"


def test_intent_system_contains_query_types() -> None:
    content = load_prompt("intent_system")
    for qt in ("symptoms", "medicine", "treatment", "find_by_symptom", "unknown"):
        assert qt in content, f"Expected query type '{qt}' in intent_system.md"


def test_medical_user_prompt_is_vietnamese() -> None:
    content = load_prompt("medical_user")
    # Must contain at least one Vietnamese word
    assert "tiếng Việt" in content or "thuốc" in content or "Việt" in content
