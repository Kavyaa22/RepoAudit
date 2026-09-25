"""Service for repositories.sync."""

from __future__ import annotations

from app.modules.repositories.sync.schema import SyncRequest, SyncResponse


async def execute(repo_id: str, payload: SyncRequest) -> SyncResponse:
    """Business logic stub for repositories.sync."""
    return SyncResponse()
