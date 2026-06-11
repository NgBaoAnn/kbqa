"""Shared API error helpers."""

from fastapi import HTTPException, status


def not_implemented(feature: str) -> HTTPException:
    """Return a consistent contract-stub error."""
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "error_code": "NOT_IMPLEMENTED",
            "message": f"{feature} is defined in the API contract but not implemented yet.",
        },
    )

