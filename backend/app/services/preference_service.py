"""Sprint 1 — User Preferences service.

Reads/writes user preference rows from ``public.user_preferences``.
Defaults: language=vi, explanation_level=general, answer_style=concise.

Usage::

    from app.services import preference_service

    prefs = await preference_service.get_preferences(user_id)
    updated = await preference_service.update_preferences(user_id, patch)
"""

from __future__ import annotations

from typing import Any

from app.database import SupabaseDatabase, get_database

# ── Column projection ──────────────────────────────────────────────────────

PREF_COLUMNS = """
    id::text as id,
    user_id::text as user_id,
    language,
    explanation_level,
    answer_style,
    created_at::text as created_at,
    updated_at::text as updated_at
"""

# ── Defaults ───────────────────────────────────────────────────────────────

_DEFAULTS = {
    "language": "vi",
    "explanation_level": "general",
    "answer_style": "concise",
}

# ── Allowed values (validation mirrors DB CHECK constraints) ───────────────

_ALLOWED: dict[str, set[str]] = {
    "language": {"vi", "en"},
    "explanation_level": {"general", "detailed", "expert"},
    "answer_style": {"concise", "detailed"},
}


def _validate_patch(patch: dict[str, Any]) -> dict[str, Any]:
    """Return only recognised, valid fields from the patch dict."""
    clean: dict[str, Any] = {}
    for field, allowed in _ALLOWED.items():
        if field in patch:
            val = patch[field]
            if val not in allowed:
                from fastapi import HTTPException, status

                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "error_code": "INVALID_PREFERENCE_VALUE",
                        "message": f"Invalid value '{val}' for field '{field}'. "
                        f"Allowed: {sorted(allowed)}",
                    },
                )
            clean[field] = val
    return clean


async def get_preferences(
    user_id: str,
    database: SupabaseDatabase | None = None,
) -> dict[str, Any]:
    """Return preferences for *user_id*, inserting defaults if the row is missing."""
    db = database or get_database()

    row = db.fetch_one(
        f"""
        select {PREF_COLUMNS}
        from public.user_preferences
        where user_id = %s
        """,
        (user_id,),
    )
    if row is not None:
        return row

    # Create default row
    row = db.fetch_one(
        f"""
        insert into public.user_preferences (user_id, language, explanation_level, answer_style)
        values (%s, %s, %s, %s)
        on conflict (user_id) do update
            set updated_at = public.user_preferences.updated_at
        returning {PREF_COLUMNS}
        """,
        (
            user_id,
            _DEFAULTS["language"],
            _DEFAULTS["explanation_level"],
            _DEFAULTS["answer_style"],
        ),
    )
    if row is None:
        raise RuntimeError("Failed to create default preferences.")
    return row


async def update_preferences(
    user_id: str,
    patch: dict[str, Any],
    database: SupabaseDatabase | None = None,
) -> dict[str, Any]:
    """Partially update preferences for *user_id*.

    Only recognised fields (language, explanation_level, answer_style) are
    applied.  Unknown keys are silently ignored.  An empty patch is a no-op
    that returns the current preferences.
    """
    db = database or get_database()

    clean = _validate_patch(patch)

    if not clean:
        # No valid updates — return current state (upsert defaults if missing)
        return await get_preferences(user_id, database=db)

    # Ensure the row exists first (upsert defaults), then apply the patch.
    await get_preferences(user_id, database=db)

    set_clauses = ", ".join(f"{field} = %s" for field in clean)
    values = list(clean.values()) + [user_id]

    row = db.fetch_one(
        f"""
        update public.user_preferences
        set {set_clauses}
        where user_id = %s
        returning {PREF_COLUMNS}
        """,
        tuple(values),
    )
    if row is None:
        raise RuntimeError("Failed to update preferences.")
    return row
