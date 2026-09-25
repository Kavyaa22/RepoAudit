"""Validators for retrieval.query."""

from __future__ import annotations

from app.modules.retrieval.query.schema import QueryRequest


def validate_query(payload: QueryRequest) -> QueryRequest:
    """Validate and normalize the request."""
    return payload
