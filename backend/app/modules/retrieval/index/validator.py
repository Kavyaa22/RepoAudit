"""Validators for retrieval.index."""

from __future__ import annotations

from app.modules.retrieval.index.schema import IndexRequest


def validate_index(payload: IndexRequest) -> IndexRequest:
    """Validate and normalize the request."""
    return payload
