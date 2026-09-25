"""Create project service."""

from __future__ import annotations

from app.core.security import CurrentUser
from app.modules.github.shared.users import require_user_id
from app.modules.projects.create.schema import CreateRequest, CreateResponse
from app.modules.projects.shared.store import project_store


async def execute(payload: CreateRequest, user: CurrentUser | None = None) -> CreateResponse:
    user_id = require_user_id(user)
    project = project_store.create(
        display_name=payload.display_name,
        repository_url=payload.repository_url,
        owner=payload.owner,
        repository_name=payload.repository_name,
        user_id=user_id,
    )
    return CreateResponse(
        project_id=project["project_id"],
        display_name=project["display_name"],
        repository_url=project["repository_url"],
        status=project["status"],
    )
