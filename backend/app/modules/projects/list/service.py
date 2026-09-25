"""List projects service."""

from __future__ import annotations

from app.core.demo import is_demo_record
from app.core.security import CurrentUser
from app.modules.github.shared.users import resolve_user_id
from app.modules.projects.list.schema import ListResponse, ProjectSummary
from app.modules.projects.shared.store import project_store


async def execute(user: CurrentUser | None = None) -> ListResponse:
    user_id = resolve_user_id(user)
    if not user_id:
        return ListResponse(items=[])

    items = []
    for p in project_store.list(user_id=user_id):
        if is_demo_record(
            name=p.get("display_name"),
            display_name=p.get("display_name"),
            owner=p.get("owner"),
            repository_name=p.get("repository_name"),
            repository_url=p.get("repository_url"),
        ):
            continue
        summary = p.get("summary") or {}
        file_count = 0
        if isinstance(summary, dict):
            file_count = int(summary.get("file_count") or 0)
        items.append(
            ProjectSummary(
                project_id=p["project_id"],
                display_name=p["display_name"],
                repository_url=p["repository_url"],
                status=p["status"],
                owner=p.get("owner"),
                repository_name=p.get("repository_name"),
                default_branch=p.get("default_branch"),
                workspace_path=p.get("workspace_path"),
                private=bool(p.get("private")),
                file_count=file_count,
                audit_project_id=p.get("audit_project_id"),
            )
        )
    return ListResponse(items=items)
