"""Service for retrieval.query."""

from __future__ import annotations

from app.modules.retrieval.query.schema import QueryRequest, QueryResponse


async def execute(payload: QueryRequest) -> QueryResponse:
    """Business logic stub for retrieval.query."""
    _ = payload
    return QueryResponse()
