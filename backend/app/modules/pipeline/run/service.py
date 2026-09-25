"""Service for pipeline.run."""

from __future__ import annotations

from app.modules.pipeline.run.schema import RunRequest, RunResponse


async def execute(payload: RunRequest) -> RunResponse:
    """Business logic stub for pipeline.run."""
    _ = payload
    return RunResponse()
