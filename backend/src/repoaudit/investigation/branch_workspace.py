"""Ensure the investigated workspace matches the requested branch when possible."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from repoaudit.investigation.project_resolver import resolve_project_directory

logger = logging.getLogger(__name__)


def ensure_branch_workspace(
    *,
    backend_root: Path,
    project_name: str,
    branch: str,
    project_id: str = "",
    repo_path: str = "",
    owner: str = "",
    repository: str = "",
    access_token: str = "",
    user_id: str = "",
) -> Path | None:
    """
    Resolve an on-disk snapshot for the selected branch, only under this user.
    If missing and GitHub credentials are available, shallow-clone that branch.
    """
    if not user_id:
        return None

    existing = resolve_project_directory(
        project_name=project_name,
        repo_path=repo_path,
        project_id=project_id,
        backend_root=backend_root,
        branch=branch,
        user_id=user_id,
    )
    if existing and _looks_like_branch(existing, branch):
        return existing

    if access_token and owner and repository and branch:
        try:
            from app.core.workspace import project_workspace_dir, safe_workspace_segment
            from app.modules.repositories.shared.clone import clone_repository, get_head_sha, safe_move_dir

            folder = project_id or safe_workspace_segment(project_name, fallback="repository")
            workspace = project_workspace_dir(user_id, folder, backend_root=backend_root) / "snapshots"
            workspace.mkdir(parents=True, exist_ok=True)
            tmp = workspace / f"_tmp_{re.sub(r'[^A-Za-z0-9_.-]+', '-', branch)}"
            dest_clone, _ = clone_repository(
                owner=owner,
                repo=repository,
                branch=branch,
                access_token=access_token,
                dest=tmp,
                force=True,
            )
            sha = get_head_sha(dest_clone)
            final = workspace / f"{branch.replace('/', '-')}-{sha[:12]}"
            safe_move_dir(dest_clone, final)
            logger.info("Checked out branch '%s' for investigation at %s", branch, final)
            return final
        except Exception as exc:  # noqa: BLE001
            logger.warning("Exact branch checkout failed for %s@%s: %s", project_name, branch, exc)

    return existing


def _looks_like_branch(path: Path, branch: str) -> bool:
    if not branch:
        return True
    key = branch.strip().lower().replace("/", "-")
    name = path.name.lower()
    parent = path.parent.name.lower()
    return key in name or key in parent or key == "main" or key == "master"
