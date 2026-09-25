"""Validators for retrieval.index_op."""

from __future__ import annotations

from app.modules.retrieval.index_op.schema import IndexOpRequest


def validate_index_op(payload: IndexOpRequest) -> IndexOpRequest:
    """Validate and normalize the request."""
    return payload
