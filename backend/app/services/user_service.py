"""User/profile service backed by Supabase Postgres."""

from __future__ import annotations

from typing import Any

from app.api_gateway.dependencies import CurrentUser
from app.database import SupabaseDatabase, get_database


PROFILE_COLUMNS = """
    id::text as id,
    display_name,
    role,
    is_active,
    created_at::text as created_at,
    updated_at::text as updated_at
"""


def _default_display_name(email: str | None) -> str:
    if email and "@" in email:
        return email.split("@", 1)[0]
    return "User"


def _to_current_user(token_user: CurrentUser, row: dict[str, Any]) -> CurrentUser:
    return CurrentUser(
        id=str(row["id"]),
        email=token_user.email,
        role=row["role"],
        display_name=row.get("display_name"),
        is_active=bool(row["is_active"]),
        claims=token_user.claims,
    )


async def get_or_create_profile(
    token_user: CurrentUser,
    database: SupabaseDatabase | None = None,
) -> CurrentUser:
    """Return the app profile for a verified Supabase user, creating it if needed."""
    db = database or get_database()
    row = db.fetch_one(
        f"""
        select {PROFILE_COLUMNS}
        from public.profiles
        where id = %s
        """,
        (token_user.id,),
    )
    if row is None:
        row = db.fetch_one(
            f"""
            insert into public.profiles (id, display_name, role)
            values (%s, %s, 'user')
            on conflict (id) do update
            set updated_at = public.profiles.updated_at
            returning {PROFILE_COLUMNS}
            """,
            (token_user.id, _default_display_name(token_user.email)),
        )

    if row is None:
        raise RuntimeError("Failed to create or load user profile.")

    return _to_current_user(token_user, row)


async def get_profile(current_user_id: str, database: SupabaseDatabase | None = None) -> dict | None:
    db = database or get_database()
    return db.fetch_one(
        f"""
        select {PROFILE_COLUMNS}
        from public.profiles
        where id = %s
        """,
        (current_user_id,),
    )
