"""Validators for pipeline.status."""

from __future__ import annotations

from app.modules.pipeline.status.schema import StatusRequest


def validate_status(payload: StatusRequest) -> StatusRequest:
    """Validate and normalize the request."""
    return payload
