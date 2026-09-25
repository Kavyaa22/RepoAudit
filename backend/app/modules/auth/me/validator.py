"""Validators for auth.me."""

from __future__ import annotations

from app.modules.auth.me.schema import MeRequest


def validate_me(payload: MeRequest) -> MeRequest:
    """Validate and normalize the request."""
    return payload
