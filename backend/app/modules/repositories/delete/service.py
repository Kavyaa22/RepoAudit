"""Service for repositories.delete."""

from __future__ import annotations

from app.modules.repositories.delete.schema import DeleteResponse


async def execute(repo_id: str) -> DeleteResponse:
    """Business logic stub for repositories.delete."""
    return DeleteResponse()
