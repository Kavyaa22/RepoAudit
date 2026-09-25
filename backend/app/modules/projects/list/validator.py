"""Validators for projects.list."""

from __future__ import annotations

from app.modules.projects.list.schema import ListRequest


def validate_list(payload: ListRequest) -> ListRequest:
    """Validate and normalize the request."""
    return payload
