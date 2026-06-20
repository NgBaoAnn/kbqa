"""User Domain — Value Objects."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UserPreferencesValue:
    """Validated user preference settings."""

    language: str = "vi"
    explanation_level: str = "general"
    answer_style: str = "concise"

    def __post_init__(self) -> None:
        if self.language not in ("vi", "en"):
            raise ValueError(f"Invalid language: '{self.language}'.")
        if self.explanation_level not in ("general", "detailed", "expert"):
            raise ValueError(f"Invalid explanation_level: '{self.explanation_level}'.")
        if self.answer_style not in ("concise", "detailed"):
            raise ValueError(f"Invalid answer_style: '{self.answer_style}'.")
