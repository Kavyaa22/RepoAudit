"""Validators for auth.login."""

from __future__ import annotations

from app.modules.auth.login.schema import LoginRequest


def validate_login(payload: LoginRequest) -> LoginRequest:
    """Validate and normalize the request."""
    return payload
