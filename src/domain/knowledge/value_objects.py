"""Knowledge Domain — Value Objects."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiseaseName:
    """A normalised disease name.

    Invariant: non-empty, first letter capitalised.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("DiseaseName cannot be empty.")
        normalised = self.value.strip()
        normalised = normalised[0].upper() + normalised[1:]
        object.__setattr__(self, "value", normalised)

    def __str__(self) -> str:
        return self.value
