"""Persist completed scan/audit pipelines to Supabase."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.core.db.repositories.audits import save_audit_run
from app.core.supabase.client import supabase_available
from app.modules.projects.shared.store import project_store
from app.modules.snapshots.store import snapshot_store

logger = logging.getLogger(__name__)


def _infer_commit_sha(workspace_path: str) -> str:
    name = Path(workspace_path).name
    if len(name) == 40 and all(c in "0123456789abcdef" for c in name.lower()):
        return name
    return "working"


def _ensure_snapshot(
    *,
    project_id: str,
    user_id: str | None,
    branch: str,
    workspace_path: str,
    summary: dict[str, Any],
) -> dict[str, Any] | None:
    commit_sha = _infer_commit_sha(workspace_path)
    existing = snapshot_store.find_by_branch_commit(project_id, branch, commit_sha)
    if existing:
        return existing
    try:
        return snapshot_store.create(
            project_id=project_id,
            commit_sha=commit_sha,
            branch=branch,
            workspace_path=workspace_path,
            status="ready",
            summary=summary,
            user_id=user_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to create repo_snapshot: %s", exc)
        return None


def persist_full_scan(
    *,
    db_project_id: str,
    user_id: str | None,
    branch: str,
    workspace_path: str,
    scan_summary: dict[str, Any],
    structure_audit: dict[str, Any] | None,
    dead_code_audit: dict[str, Any] | None,
    wiki_summary: dict[str, Any] | None,
    scan_status: str = "done",
    security_audit: dict[str, Any] | None = None,
) -> str | None:
    """Write full scan results to projects, repo_snapshots, audit_runs. Returns audit_id."""
    if not supabase_available() or not db_project_id or not user_id:
        return None

    project = project_store.get_for_user(db_project_id, user_id) if user_id else None
    if not project:
        logger.warning("persist_full_scan: project %s not found for this user", db_project_id)
        return None

    from app.core.workspace import path_belongs_to_user

    workspace = workspace_path or str(project.get("workspace_path") or "")
    if workspace and not path_belongs_to_user(workspace, user_id):
        workspace = str(project.get("workspace_path") or "")
        if workspace and not path_belongs_to_user(workspace, user_id):
            workspace = ""

    snapshot = None
    if workspace:
        snapshot = _ensure_snapshot(
            project_id=db_project_id,
            user_id=user_id,
            branch=branch,
            workspace_path=workspace,
            summary=scan_summary,
        )
    snapshot_id = str(snapshot["snapshot_id"]) if snapshot else project.get("latest_snapshot_id")
    commit_sha = snapshot.get("commit_sha") if snapshot else project.get("latest_commit_sha")

    combined: dict[str, Any] = dict(scan_summary)
    if structure_audit:
        combined.update(structure_audit)
    if dead_code_audit:
        combined["dead_code_result"] = dead_code_audit
    if security_audit:
        combined["security_result"] = security_audit
        combined["security_audit"] = security_audit
    if wiki_summary:
        combined["wiki_summary"] = wiki_summary

    audit_status = "succeeded" if scan_status == "done" else "failed"
    saved = save_audit_run(
        project_id=db_project_id,
        snapshot_id=str(snapshot_id) if snapshot_id else None,
        user_id=user_id,
        branch=branch,
        commit_sha=commit_sha,
        audit_type="full_scan",
        result=combined,
        status=audit_status,
    )

    audit_id = str(saved["audit_id"]) if saved else None
    project_store.update(
        db_project_id,
        status="ready" if scan_status == "done" else "failed",
        summary={**scan_summary, "audit_id": audit_id},
        latest_snapshot_id=snapshot_id,
        latest_commit_sha=commit_sha,
        default_branch=branch,
    )
    return audit_id


def resolve_db_project_id(
    *,
    requested_project_id: str | None,
    user_id: str | None,
    display_name: str,
    branch: str,
    owner: str | None,
    repository_name: str | None,
    repository_url: str | None,
    workspace_path: str | None,
) -> str | None:
    """Resolve imported project UUID for DB persistence. Never returns another user's project."""
    if not user_id:
        return None

    if requested_project_id:
        owned = project_store.get_for_user(requested_project_id, user_id)
        if owned:
            return requested_project_id

    if repository_url:
        for item in project_store.list(user_id=user_id):
            if item.get("repository_url") == repository_url:
                return str(item["project_id"])

    if not workspace_path:
        return None

    from app.core.workspace import path_belongs_to_user

    if not path_belongs_to_user(workspace_path, user_id):
        return None

    slug = (repository_name or display_name or "repository").lower().replace(" ", "-")
    record = project_store.create(
        display_name=display_name or repository_name or "Repository",
        repository_url=repository_url or f"local://{slug}",
        owner=owner or "local",
        repository_name=repository_name or slug,
        default_branch=branch,
        user_id=user_id,
        status="ready",
        workspace_path=workspace_path,
    )
    return str(record["project_id"])
