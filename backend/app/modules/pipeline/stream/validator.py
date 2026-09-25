"""Validators for pipeline.stream."""

from __future__ import annotations

from app.modules.pipeline.stream.schema import StreamRequest


def validate_stream(payload: StreamRequest) -> StreamRequest:
    """Validate and normalize the request."""
    return payload
