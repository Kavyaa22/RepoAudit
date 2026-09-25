"""Validators for repositories.delete."""

from __future__ import annotations

from app.modules.repositories.delete.schema import DeleteRequest


def validate_delete(payload: DeleteRequest) -> DeleteRequest:
    """Validate and normalize the request."""
    return payload
