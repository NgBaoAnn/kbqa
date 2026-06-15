"""Port: Auth Provider.

Abstracts authentication and user identity resolution.
Adapters: SupabaseAuthProvider, (future) InMemoryAuthProvider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IAuthProvider(ABC):
    """Port for authentication and user identity."""

    @abstractmethod
    async def verify_token(self, token: str) -> dict[str, Any]:
        """Verify a JWT token and return the decoded payload.

        Args:
            token: The bearer token string.

        Returns:
            Dict with at least 'sub' (user ID) and optional claims.

        Raises:
            AuthorizationError: If the token is invalid or expired.
        """
        ...

    @abstractmethod
    async def get_user_role(self, user_id: str) -> str:
        """Resolve the role for a given user ID.

        Args:
            user_id: Supabase user UUID.

        Returns:
            Role string: 'user', 'reviewer', or 'admin'.
        """
        ...
