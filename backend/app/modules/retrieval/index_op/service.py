"""Service for retrieval.index_op."""

from __future__ import annotations

from app.modules.retrieval.index_op.schema import IndexOpRequest, IndexOpResponse


async def execute(payload: IndexOpRequest) -> IndexOpResponse:
    """Business logic stub for retrieval.index_op."""
    _ = payload
    return IndexOpResponse()
