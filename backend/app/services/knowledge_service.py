"""Knowledge browsing service skeleton."""

from app.api_gateway.errors import not_implemented


async def list_diseases(*, q: str | None, limit: int, offset: int) -> None:
    raise not_implemented(f"list diseases q={q!r} limit={limit} offset={offset}")


async def get_disease(*, disease_id: str) -> None:
    raise not_implemented(f"get disease {disease_id}")

