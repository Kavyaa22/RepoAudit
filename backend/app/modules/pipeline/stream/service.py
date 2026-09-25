"""Service for pipeline.stream."""

from __future__ import annotations

from app.modules.pipeline.stream.schema import StreamResponse


async def execute(run_id: str) -> StreamResponse:
    """Business logic stub for pipeline.stream."""
    return StreamResponse()
