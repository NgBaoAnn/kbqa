"""User Domain — Entities."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UserProfile:
    """Authentication identity of a user."""

    id: str
    email: str | None = None
    role: str = "user"  # "user" | "reviewer" | "admin"
    display_name: str | None = None
    is_active: bool = True
    auth_provider: str = "supabase"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_reviewer(self) -> bool:
        return self.role in ("reviewer", "admin")
