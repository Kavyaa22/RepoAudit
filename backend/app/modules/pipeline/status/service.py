"""Service for pipeline.status."""

from __future__ import annotations

from app.modules.pipeline.status.schema import StatusResponse


async def execute(run_id: str) -> StatusResponse:
    """Business logic stub for pipeline.status."""
    return StatusResponse()
