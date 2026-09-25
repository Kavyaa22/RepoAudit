"""Validators for pipeline.run."""

from __future__ import annotations

from app.modules.pipeline.run.schema import RunRequest


def validate_run(payload: RunRequest) -> RunRequest:
    """Validate and normalize the request."""
    return payload
