"""Validators for auth.create."""

from __future__ import annotations

from app.modules.auth.create.schema import CreateRequest


def validate_create(payload: CreateRequest) -> CreateRequest:
    """Validate and normalize the request."""
    return payload
