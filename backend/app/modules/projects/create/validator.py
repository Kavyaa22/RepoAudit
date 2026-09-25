"""Validators for projects.create."""

from __future__ import annotations

from app.modules.projects.create.schema import CreateRequest


def validate_create(payload: CreateRequest) -> CreateRequest:
    """Validate and normalize the request."""
    return payload
