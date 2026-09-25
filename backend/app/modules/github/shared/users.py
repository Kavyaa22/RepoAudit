"""Map authenticated app users onto GitHub connection keys."""

from __future__ import annotations

from app.core.exceptions import UnauthorizedError
from app.core.security import CurrentUser


def resolve_user_id(user: CurrentUser | None) -> str | None:
    """Return the app user UUID, or None. Never falls back to email or anonymous."""
    if user is None or user.user_id is None:
        return None
    value = str(user.user_id).strip()
    if not value or value == "anonymous" or value.lower().startswith("email:"):
        return None
    return value


def require_user_id(user: CurrentUser | None) -> str:
    user_id = resolve_user_id(user)
    if not user_id:
        raise UnauthorizedError("Sign in required")
    return user_id
