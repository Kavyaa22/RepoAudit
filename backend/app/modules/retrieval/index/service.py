"""Service for retrieval.index."""

from __future__ import annotations

from app.modules.retrieval.index.schema import IndexRequest, IndexResponse


async def execute(payload: IndexRequest) -> IndexResponse:
    """Business logic stub for retrieval.index."""
    _ = payload
    return IndexResponse()
