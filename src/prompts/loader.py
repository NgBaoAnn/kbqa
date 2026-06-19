"""Prompt template loader.

Reads ``.md`` files from the ``src/prompts/`` directory and caches them in
memory so every module gets the same string without repeated disk I/O.

Usage::

    from prompts.loader import load_prompt

    schema_prompt = load_prompt("text_to_cypher")   # reads text_to_cypher.md
    intent_prompt = load_prompt("intent_system")     # reads intent_system.md
    user_prompt   = load_prompt("medical_user")      # reads medical_user.md
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    """Return the content of ``{name}.md`` in the prompts directory.

    The file is read once and the result is cached for the lifetime of the
    process.  Leading/trailing whitespace is stripped so callers don't need
    to worry about trailing newlines.

    Args:
        name: Prompt file stem (without ``.md`` extension).

    Returns:
        The stripped prompt string.

    Raises:
        FileNotFoundError: If the prompt file does not exist.
    """
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(
            f"Prompt file not found: {path}. "
            f"Available prompts: {[p.stem for p in _PROMPTS_DIR.glob('*.md')]}"
        )
    return path.read_text(encoding="utf-8").strip()
