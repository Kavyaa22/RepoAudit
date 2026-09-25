"""Service for knowledge.view."""

from __future__ import annotations

from app.modules.knowledge.view.schema import ViewResponse


async def execute(knowledge_id: str) -> ViewResponse:
    """Business logic stub for knowledge.view."""
    return ViewResponse()
