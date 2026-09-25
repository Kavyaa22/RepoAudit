"""Service for projects.links."""

from __future__ import annotations

from app.modules.projects.links.schema import LinksResponse


async def execute(project_id: str) -> LinksResponse:
    """Business logic stub for projects.links."""
    return LinksResponse()
