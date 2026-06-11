"""User/profile service skeleton.

S1-ARCH-05 intentionally defines module boundaries only. Người 2 will implement
profile persistence against Supabase Postgres in S1-BE-01.
"""

from app.api_gateway.errors import not_implemented


async def get_profile(current_user_id: str) -> None:
    raise not_implemented(f"get profile for user {current_user_id}")

