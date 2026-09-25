"""Delete audit service."""

from __future__ import annotations

import logging

from app.core.exceptions import NotFoundError, UnauthorizedError
from app.core.security import CurrentUser
from app.modules.audit.delete.schema import DeleteResponse
from app.modules.github.shared.users import resolve_user_id
from repoaudit.interfaces.api.runtime import owned_by_user

logger = logging.getLogger(__name__)


def _reset_project_summary(*, client, project_store, project_id: str, user_id: str) -> bool:
    """Clear scan summary on a project. Returns True on success."""
    try:
        client.table("projects").update(
            {"summary": {}, "audit_project_id": None, "latest_snapshot_id": None}
        ).eq("project_id", project_id).eq("user_id", str(user_id)).execute()
        project_store.update(
            project_id,
            summary={},
            audit_project_id=None,
            latest_snapshot_id=None,
        )
        return True
    except Exception as exc:
        logger.warning("Failed to reset project summary for %s: %s", project_id, exc)
        return False


async def execute(*, identifier: str, user: CurrentUser | None = None) -> DeleteResponse:
    from app.core.db.repositories.audits import (
        delete_audit_run,
        delete_audit_runs_for_project,
        resolve_audit_run,
    )
    from app.core.supabase.client import get_supabase_client, supabase_available
    from app.modules.projects.shared.store import project_store
    from repoaudit.interfaces.api.runtime import ensure_cache, get_projects, purge_project_cache

    audit_key = identifier.strip()
    if not audit_key:
        raise NotFoundError("Audit identifier is required")

    user_id = resolve_user_id(user)
    if not user_id:
        raise UnauthorizedError("Sign in required to delete an audit")

    deleted = False
    purge_keys: set[str] = {audit_key}
    deleted_ids: set[str] = set()
    purged_project_ids: set[str] = set()
    project_id: str | None = None
    summary_reset_failed = False

    # 1. Check Supabase audit_runs table
    row = resolve_audit_run(identifier=audit_key, user_id=user_id)
    if row:
        audit_id = str(row.get("audit_id") or audit_key)
        project_id = str(row.get("project_id") or "") or None
        purge_keys.update({audit_key, audit_id})
        deleted_ids.add(audit_id)
        if project_id:
            purge_keys.add(project_id)
            purged_project_ids.add(project_id)
        if delete_audit_run(audit_id=audit_id, user_id=user_id):
            deleted = True
            deleted_ids.add(audit_id)
        # Product rule: deleting an audit clears all runs for that project
        if project_id:
            removed = delete_audit_runs_for_project(project_id=project_id, user_id=user_id)
            if removed > 0:
                deleted = True
    elif delete_audit_runs_for_project(project_id=audit_key, user_id=user_id) > 0:
        deleted = True
        project_id = audit_key
        purge_keys.add(audit_key)
        purged_project_ids.add(audit_key)
        deleted_ids.add(audit_key)

    # 2. Check Supabase projects table & project_store for matching audit references
    if supabase_available():
        try:
            client = get_supabase_client()
            res = (
                client.table("projects")
                .select("project_id, summary, audit_project_id")
                .eq("user_id", str(user_id))
                .execute()
            )
            if res.data and isinstance(res.data, list):
                for p_rec in res.data:
                    pid = str(p_rec.get("project_id") or "")
                    summary = p_rec.get("summary") or {}
                    sm_aid = str(summary.get("audit_id") or "") if isinstance(summary, dict) else ""
                    p_aid = str(p_rec.get("audit_project_id") or "")
                    matches = audit_key in {pid, sm_aid, p_aid} or (project_id and pid == project_id)
                    # Also clear any project whose summary references a purged audit id
                    if not matches and isinstance(summary, dict) and deleted_ids:
                        if str(summary.get("audit_id") or "") in deleted_ids:
                            matches = True
                    if not matches or not pid:
                        continue
                    purge_keys.add(pid)
                    purged_project_ids.add(pid)
                    if sm_aid:
                        purge_keys.add(sm_aid)
                        deleted_ids.add(sm_aid)
                    if p_aid:
                        purge_keys.add(p_aid)
                        deleted_ids.add(p_aid)
                    if _reset_project_summary(
                        client=client,
                        project_store=project_store,
                        project_id=pid,
                        user_id=str(user_id),
                    ):
                        deleted = True
                    else:
                        summary_reset_failed = True
        except Exception as exc:
            logger.warning("Projects table probe failed during audit delete: %s", exc)
            summary_reset_failed = True

    # 3. Check and clean SQLite persistent cache
    try:
        cache = await ensure_cache()
        removed_cache_count = await cache.delete_matching_projects(purge_keys, user_id=user_id)
        if removed_cache_count > 0:
            deleted = True
    except Exception as exc:
        logger.warning("SQLite cache cleanup failed during audit delete: %s", exc)

    # 4. Check and clean in-memory projects
    projects_mem = get_projects()
    for key in list(purge_keys):
        mem = projects_mem.get(key)
        if mem and owned_by_user(mem, user_id):
            deleted = True
            info = mem.get("info")
            if info and getattr(info, "id", None):
                purge_keys.add(str(info.id))
            if mem.get("db_project_id"):
                purge_keys.add(str(mem["db_project_id"]))
                purged_project_ids.add(str(mem["db_project_id"]))
            if mem.get("audit_id"):
                aid = str(mem["audit_id"])
                purge_keys.add(aid)
                deleted_ids.add(aid)

    for cache_key, proj in list(projects_mem.items()):
        if not isinstance(proj, dict):
            continue
        if not owned_by_user(proj, user_id):
            continue
        info = proj.get("info")
        aliases = {
            str(cache_key),
            str(proj.get("audit_id") or ""),
            str(proj.get("db_project_id") or ""),
            str(proj.get("id") or ""),
            str(getattr(info, "id", "") or ""),
        }
        if aliases & purge_keys:
            deleted = True
            purge_keys.update(aliases)
            for a in aliases:
                if a:
                    deleted_ids.add(a)

    purge_project_cache(*purge_keys, user_id=user_id)

    if not deleted:
        raise NotFoundError(f"Audit {audit_key} not found")

    if summary_reset_failed:
        logger.warning(
            "Audit %s deleted but one or more project summaries may still reference it",
            audit_key,
        )

    # Ensure the original key is always reported
    deleted_ids.add(audit_key)
    if project_id:
        purged_project_ids.add(project_id)

    return DeleteResponse(
        message=f"Deleted audit {audit_key}",
        deleted_ids=sorted(i for i in deleted_ids if i),
        purged_project_ids=sorted(i for i in purged_project_ids if i),
    )
