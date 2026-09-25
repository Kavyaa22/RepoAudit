"""Service for repositories.import."""

from __future__ import annotations

import asyncio

from app.core.exceptions import AppError, UnauthorizedError
from app.core.security import CurrentUser
from app.core.workspace import project_workspace_dir
from app.modules.github.shared.client import GitHubAPIError, github_get
from app.modules.github.shared.store import github_connection_store
from app.modules.github.shared.users import require_user_id
from app.modules.projects.shared.store import project_store
from app.modules.repositories.shared.clone import (
    clone_repository,
    safe_move_dir,
    safe_remove_dir,
    summarize_workspace,
)
from app.modules.snapshots.store import snapshot_store
from .schema import ImportRequest, ImportResponse


async def execute(payload: ImportRequest, user: CurrentUser) -> ImportResponse:
    user_id = require_user_id(user)
    token = github_connection_store.get_access_token(user_id)
    if not token:
        raise UnauthorizedError("Connect GitHub before importing a repository")

    owner = payload.owner.strip()
    repo = payload.repo.strip()
    branch = (payload.branch or "main").strip() or "main"
    repository_url = f"https://github.com/{owner}/{repo}"
    display_name = (payload.display_name or repo).strip()

    try:
        meta = await github_get(f"/repos/{owner}/{repo}", access_token=token)
    except GitHubAPIError as exc:
        raise AppError(
            f"Cannot access {owner}/{repo}: {exc.message}",
            code="github_api_error",
        ) from exc

    private = bool(meta.get("private"))
    project = project_store.create(
        display_name=display_name,
        repository_url=repository_url,
        owner=owner,
        repository_name=repo,
        default_branch=branch,
        user_id=user_id,
        status="importing",
        private=private,
    )
    project_id = project["project_id"]
    user_root = project_workspace_dir(user_id, project_id)
    temp_clone_dest = user_root / "cloning_temp"

    try:
        _, commit_sha = await asyncio.to_thread(
            clone_repository,
            owner=owner,
            repo=repo,
            branch=branch,
            access_token=token,
            dest=temp_clone_dest,
            force=True,
        )

        snapshot_dest = user_root / "snapshots" / commit_sha
        safe_move_dir(temp_clone_dest, snapshot_dest)

        summary = await asyncio.to_thread(summarize_workspace, snapshot_dest)

        snapshot_record = snapshot_store.create(
            project_id=project_id,
            commit_sha=commit_sha,
            branch=branch,
            workspace_path=str(snapshot_dest),
            status="ready",
            summary=summary,
            user_id=user_id,
        )

        project_store.update(
            project_id,
            status="ready",
            summary=summary,
            workspace_path=str(snapshot_dest),
            latest_snapshot_id=snapshot_record["snapshot_id"],
            latest_commit_sha=commit_sha,
        )
    except Exception as exc:
        if temp_clone_dest.exists():
            safe_remove_dir(temp_clone_dest)
        project_store.update(project_id, status="failed", summary={"error": str(exc)})
        raise AppError(f"Import failed: {exc}", code="import_failed") from exc

    return ImportResponse(
        project_id=project_id,
        display_name=display_name,
        repository_url=repository_url,
        owner=owner,
        repository_name=repo,
        branch=branch,
        workspace_path=str(snapshot_dest),
        status="ready",
        private=private,
        file_count=int(summary.get("file_count") or 0),
        message=f"Repository cloned into immutable snapshot ({commit_sha[:7]}) and ready for audit",
    )
