"""Knowledge Domain — Entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Disease:
    """A medical condition in the VietMedKG knowledge graph."""

    id: str
    disease_name: str
    description: str | None = None
    disease_category: str | None = None
    symptoms: list[str] = field(default_factory=list)
    treatments: list[str] = field(default_factory=list)
    medicines: list[str] = field(default_factory=list)
    advice: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphSchema:
    """The schema description of the knowledge graph."""

    nodes: list[dict[str, Any]] = field(default_factory=list)
    relationships: list[dict[str, Any]] = field(default_factory=list)
