"""Validators for projects.edit."""

from __future__ import annotations

from app.modules.projects.edit.schema import EditRequest


def validate_edit(payload: EditRequest) -> EditRequest:
    """Validate and normalize the request."""
    return payload
