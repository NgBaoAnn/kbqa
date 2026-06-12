"""Sprint 1 — Versioning service.

Reads prompt/model/KG/pipeline version from environment/config and exposes
a single ``get_version_metadata()`` helper that returns a dict ready to be
merged into assistant message ``metadata`` and ``query_logs.metadata``.

Usage::

    from app.services import versioning_service

    version_meta = versioning_service.get_version_metadata()
    # → {"prompt_version": "v1.0.0", "model_name": "llama3:8b", ...}
"""

from __future__ import annotations

from typing import TypedDict

from app.config import KG_VERSION, MODEL_NAME, PIPELINE_VERSION, PROMPT_VERSION


class VersionMetadata(TypedDict):
    """Version metadata keys persisted with every assistant message."""

    prompt_version: str
    model_name: str
    kg_version: str
    pipeline_version: str


def get_version_metadata() -> VersionMetadata:
    """Return current version metadata snapshot from environment config.

    This function is intentionally synchronous and side-effect-free so that it
    can be called safely from any context (including tests).
    """
    return VersionMetadata(
        prompt_version=PROMPT_VERSION,
        model_name=MODEL_NAME,
        kg_version=KG_VERSION,
        pipeline_version=PIPELINE_VERSION,
    )
