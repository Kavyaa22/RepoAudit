"""Service for projects.edit."""

from __future__ import annotations

from app.modules.projects.edit.schema import EditRequest, EditResponse


async def execute(project_id: str, payload: EditRequest) -> EditResponse:
    """Business logic stub for projects.edit."""
    return EditResponse()
