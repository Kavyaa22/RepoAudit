"""View project service."""

from __future__ import annotations

from app.core.exceptions import NotFoundError
from app.core.security import CurrentUser
from app.modules.github.shared.users import require_user_id
from app.modules.projects.shared.store import project_store
from app.modules.projects.view.schema import ViewResponse


async def execute(project_id: str, user: CurrentUser | None = None) -> ViewResponse:
    user_id = require_user_id(user)
    project = project_store.get_for_user(project_id, user_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found")
    return ViewResponse(
        project_id=project["project_id"],
        display_name=project["display_name"],
        repository_url=project["repository_url"],
        owner=project["owner"],
        repository_name=project["repository_name"],
        status=project["status"],
        workspace_path=project["workspace_path"],
    )
