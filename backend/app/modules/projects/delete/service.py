"""Delete project service."""

from __future__ import annotations

from app.core.exceptions import NotFoundError
from app.core.security import CurrentUser
from app.modules.github.shared.users import require_user_id
from app.modules.projects.delete.schema import DeleteResponse
from app.modules.projects.shared.store import project_store


async def execute(project_id: str, user: CurrentUser | None = None) -> DeleteResponse:
    user_id = require_user_id(user)
    if not project_store.get_for_user(project_id, user_id):
        raise NotFoundError(f"Project {project_id} not found")
    if not project_store.delete(project_id):
        raise NotFoundError(f"Project {project_id} not found")
    return DeleteResponse(message=f"Deleted {project_id}")
