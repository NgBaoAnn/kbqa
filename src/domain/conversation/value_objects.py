"""Conversation Domain — Value Objects."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeedbackRatingValue:
    """A validated feedback rating."""

    rating: str  # "up" | "down"

    def __post_init__(self) -> None:
        if self.rating not in ("up", "down"):
            raise ValueError(f"Invalid feedback rating: '{self.rating}'. Must be 'up' or 'down'.")

    @property
    def is_negative(self) -> bool:
        return self.rating == "down"
