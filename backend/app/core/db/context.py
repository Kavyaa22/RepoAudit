"""Resolve project/snapshot context for persistence."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.supabase.client import supabase_available
from app.modules.projects.shared.store import project_store
from app.modules.snapshots.store import snapshot_store

logger = logging.getLogger(__name__)


@dataclass
class PersistenceContext:
    project_id: str | None
    snapshot_id: str | None
    branch: str
    commit_sha: str | None
    workspace_path: str
    user_id: str | None


def _infer_commit_sha(workspace_path: Path) -> str:
    name = workspace_path.name
    if len(name) == 40 and all(c in "0123456789abcdef" for c in name.lower()):
        return name
    return "working"


def resolve_persistence_context(
    *,
    project_id: str = "",
    project_name: str = "",
    branch: str = "main",
    repo_path: str = "",
    user_id: str | None = None,
    backend_root: Path | None = None,
) -> PersistenceContext:
    """Resolve project + snapshot IDs for DB writes."""
    branch = (branch or "main").strip() or "main"
    resolved_project_id = project_id.strip() or None
    project_record: dict[str, Any] | None = None

    if resolved_project_id:
        project_record = project_store.get(resolved_project_id)
        if project_record and user_id and str(project_record.get("user_id") or "") != str(user_id):
            project_record = None
            resolved_project_id = None

    if project_record is None and project_name:
        for item in project_store.list(user_id=user_id):
            if item.get("display_name") == project_name or item.get("project_name") == project_name:
                project_record = item
                resolved_project_id = str(item.get("project_id"))
                break

    workspace_path = repo_path.strip()
    if not workspace_path and project_record:
        workspace_path = str(project_record.get("workspace_path") or "")

    if not workspace_path:
        from repoaudit.investigation.project_resolver import resolve_project_directory

        base = backend_root or Path(__file__).resolve().parents[3]
        target = resolve_project_directory(
            project_name=project_name or "Repository",
            repo_path=repo_path,
            project_id=resolved_project_id or "",
            backend_root=base,
            user_id=user_id,
        )
        workspace_path = str(target) if target else ""

    path_obj = Path(workspace_path) if workspace_path else None
    commit_sha = _infer_commit_sha(path_obj) if path_obj and path_obj.is_dir() else "working"
    snapshot_id: str | None = None

    if resolved_project_id and path_obj and path_obj.is_dir():
        existing = snapshot_store.find_by_branch_commit(resolved_project_id, branch, commit_sha)
        if existing:
            snapshot_id = str(existing.get("snapshot_id"))
        else:
            try:
                summary: dict[str, Any] = {}
                if project_record and isinstance(project_record.get("summary"), dict):
                    summary = project_record["summary"]
                created = snapshot_store.create(
                    project_id=resolved_project_id,
                    commit_sha=commit_sha,
                    branch=branch,
                    workspace_path=workspace_path,
                    status="ready",
                    summary=summary,
                    user_id=user_id,
                )
                snapshot_id = str(created.get("snapshot_id"))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not create repo_snapshot: %s", exc)

    return PersistenceContext(
        project_id=resolved_project_id,
        snapshot_id=snapshot_id,
        branch=branch,
        commit_sha=commit_sha if commit_sha != "working" else None,
        workspace_path=workspace_path,
        user_id=user_id,
    )


def ensure_project_for_audit(
    *,
    project_id: str = "",
    project_name: str,
    branch: str,
    repo_path: str,
    user_id: str | None,
    backend_root: Path,
) -> PersistenceContext:
    """Ensure a project row exists so audit_runs FK succeeds."""
    ctx = resolve_persistence_context(
        project_id=project_id,
        project_name=project_name,
        branch=branch,
        repo_path=repo_path,
        user_id=user_id,
        backend_root=backend_root,
    )

    if ctx.project_id:
        if not ctx.snapshot_id and Path(ctx.workspace_path).is_dir():
            try:
                snap = snapshot_store.create(
                    project_id=ctx.project_id,
                    commit_sha=ctx.commit_sha or _infer_commit_sha(Path(ctx.workspace_path)),
                    branch=branch,
                    workspace_path=ctx.workspace_path,
                    status="ready",
                    summary={},
                    user_id=user_id,
                )
                ctx.snapshot_id = str(snap.get("snapshot_id"))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Snapshot create during audit ensure failed: %s", exc)
        return ctx

    if not supabase_available() or not user_id:
        return ctx

    workspace = Path(repo_path) if repo_path else None
    if workspace is None or not workspace.is_dir():
        from repoaudit.investigation.project_resolver import resolve_project_directory

        workspace = resolve_project_directory(
            project_name=project_name,
            repo_path=repo_path,
            backend_root=backend_root,
            user_id=user_id,
        )

    if workspace is None or not workspace.is_dir():
        return ctx

    slug = project_name.lower().replace(" ", "-") or "repository"
    record = project_store.create(
        display_name=project_name or "Repository",
        repository_url=f"local://{slug}",
        owner="local",
        repository_name=slug,
        default_branch=branch,
        user_id=user_id,
        status="ready",
        workspace_path=str(workspace),
    )
    ctx.project_id = str(record["project_id"])
    ctx.workspace_path = str(workspace)
    ctx.commit_sha = _infer_commit_sha(workspace)

    try:
        snap = snapshot_store.create(
            project_id=ctx.project_id,
            commit_sha=ctx.commit_sha or "working",
            branch=branch,
            workspace_path=str(workspace),
            status="ready",
            summary={},
            user_id=user_id,
        )
        ctx.snapshot_id = str(snap.get("snapshot_id"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Snapshot create during audit ensure failed: %s", exc)

    return ctx
