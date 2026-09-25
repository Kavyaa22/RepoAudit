"""Validators for auth.logout."""

from __future__ import annotations

from app.modules.auth.logout.schema import LogoutRequest


def validate_logout(payload: LogoutRequest) -> LogoutRequest:
    """Validate and normalize the request."""
    return payload
