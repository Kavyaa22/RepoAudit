"""Validators for projects.view."""

from __future__ import annotations

from app.modules.projects.view.schema import ViewRequest


def validate_view(payload: ViewRequest) -> ViewRequest:
    """Validate and normalize the request."""
    return payload
