"""ManagePreferencesUseCase — User preference CRUD.

Extracted from backend/app/services/preference_service.py.
Uses only IDatabaseRepository port.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_PREF_COLS = """
    id::text as id,
    user_id::text as user_id,
    language,
    explanation_level,
    answer_style,
    created_at::text as created_at,
    updated_at::text as updated_at
"""

_DEFAULTS: dict[str, str] = {
    "language": "vi",
    "explanation_level": "general",
    "answer_style": "concise",
}

_ALLOWED: dict[str, set[str]] = {
    "language": {"vi", "en"},
    "explanation_level": {"general", "detailed", "expert"},
    "answer_style": {"concise", "detailed"},
}


class ManagePreferencesUseCase:
    """Read and update user preferences.

    Args:
        db: IDatabaseRepository
    """

    def __init__(self, *, db) -> None:
        self._db = db

    def get_preferences(self, *, user_id: str) -> dict[str, Any]:
        """Return preferences for user, creating defaults if missing."""
        row = self._db.fetch_one(
            f"select {_PREF_COLS} from public.user_preferences where user_id = %s",
            (user_id,),
        )
        if row is not None:
            return dict(row)

        # Create default row
        row = self._db.fetch_one(
            f"""
            insert into public.user_preferences (user_id, language, explanation_level, answer_style)
            values (%s, %s, %s, %s)
            on conflict (user_id) do update
                set updated_at = public.user_preferences.updated_at
            returning {_PREF_COLS}
            """,
            (user_id, _DEFAULTS["language"], _DEFAULTS["explanation_level"], _DEFAULTS["answer_style"]),
        )
        if row is None:
            raise RuntimeError("Failed to create default preferences.")
        return dict(row)

    def update_preferences(
        self, *, user_id: str, patch: dict[str, Any]
    ) -> dict[str, Any]:
        """Partially update preferences. Raises ValueError on invalid values."""
        clean = self._validate(patch)
        if not clean:
            return self.get_preferences(user_id=user_id)

        # Ensure row exists first
        self.get_preferences(user_id=user_id)

        set_clauses = ", ".join(f"{field} = %s" for field in clean)
        values = list(clean.values()) + [user_id]

        row = self._db.fetch_one(
            f"update public.user_preferences set {set_clauses} where user_id = %s returning {_PREF_COLS}",
            tuple(values),
        )
        if row is None:
            raise RuntimeError("Failed to update preferences.")
        return dict(row)

    @staticmethod
    def _validate(patch: dict[str, Any]) -> dict[str, Any]:
        clean: dict[str, Any] = {}
        for field, allowed in _ALLOWED.items():
            if field in patch:
                val = patch[field]
                if val not in allowed:
                    raise ValueError(
                        f"INVALID_PREFERENCE_VALUE: '{val}' for '{field}'. Allowed: {sorted(allowed)}"
                    )
                clean[field] = val
        return clean
