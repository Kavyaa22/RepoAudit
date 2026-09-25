"""Shared runtime state for scan / wiki / chat routes.

Uses a process-level singleton in ``sys.modules`` so cache/projects survive
accidental re-imports of this module (uvicorn reload / path eviction).
"""

from __future__ import annotations

import logging
import sys
import types
from typing import Any

from repoaudit.indexing.cache.cache import Cache

logger = logging.getLogger(__name__)

_STATE_MODULE = "_repoaudit_shared_state"


def _state() -> types.ModuleType:
    box = sys.modules.get(_STATE_MODULE)
    if box is None:
        box = types.ModuleType(_STATE_MODULE)
        box.projects = {}  # type: ignore[attr-defined]
        box.cache = None  # type: ignore[attr-defined]
        sys.modules[_STATE_MODULE] = box
    return box


def get_projects() -> dict[str, Any]:
    return _state().projects  # type: ignore[return-value]


def owned_by_user(proj: dict[str, Any] | None, user_id: str | None) -> bool:
    """True when the in-memory/cache project belongs to this app user."""
    if not proj or not user_id:
        return False
    return str(proj.get("user_id") or "") == str(user_id)


def get_cache() -> Cache:
    """Return shared cache instance. Never raises — creates an empty Cache if needed.

    Callers in async code should prefer ``await ensure_cache()`` so the DB is open.
    """
    box = _state()
    if box.cache is None:
        box.cache = Cache()  # type: ignore[attr-defined]
    return box.cache  # type: ignore[return-value]


async def ensure_cache() -> Cache:
    """Idempotent async cache init (safe from scan, lifespan, and after reload)."""
    box = _state()
    existing: Cache | None = box.cache  # type: ignore[assignment]
    if existing is not None and getattr(existing, "_db", None) is not None:
        return existing
    cache = existing if existing is not None else Cache()
    try:
        # Re-open if close_cache() left the singleton with _db=None.
        await cache.init()
    except Exception:
        # DB may be locked briefly during reload — retry once with a fresh connection
        logger.warning("cache.init() failed; retrying with a new Cache instance", exc_info=True)
        cache = Cache()
        await cache.init()
    box.cache = cache  # type: ignore[attr-defined]
    logger.debug("cache ready at %s", cache.db_path)
    return cache


async def init_cache() -> Cache:
    """Startup helper — same as ensure_cache()."""
    return await ensure_cache()


async def close_cache() -> None:
    """Close DB handle but keep the singleton so in-flight scans can re-open via ensure_cache."""
    box = _state()
    cache: Cache | None = box.cache  # type: ignore[assignment]
    if cache is not None:
        try:
            await cache.close()
        except Exception:  # noqa: BLE001
            logger.debug("cache.close() ignored during shutdown", exc_info=True)


def _build_proj_from_pdata(pdata: dict[str, Any], cache_key: str) -> dict[str, Any]:
    from repoaudit.interfaces.api.schemas import ProjectInfo
    from repoaudit.interfaces.api.scan_enrichment import enrich_scan_record

    enriched = enrich_scan_record(pdata)
    canonical_id = str(pdata.get("id") or cache_key)
    info = ProjectInfo(
        id=canonical_id,
        name=enriched.get("name") or pdata.get("name", "Repository"),
        status=pdata.get("status", "done"),
        total_files=pdata.get("total_files", 0),
        total_lines=pdata.get("total_lines", 0),
        error=pdata.get("error", ""),
        branch=enriched.get("branch") or pdata.get("branch") or "main",
    )
    return {
        "info": info,
        "wiki": None,
        "project": None,
        "progress": pdata.get("progress", []),
        "created_at": pdata.get("created_at", ""),
        "score": enriched.get("score", pdata.get("score", 100)),
        "is_valid": enriched.get("is_valid", pdata.get("is_valid", True)),
        "branch": enriched.get("branch") or pdata.get("branch") or "main",
        "display_name": pdata.get("display_name"),
        "owner": pdata.get("owner"),
        "repository_name": pdata.get("repository_name"),
        "repository_url": pdata.get("repository_url"),
        "structure_audit": pdata.get("structure_audit"),
        "dead_code_audit": pdata.get("dead_code_audit"),
        "security_audit": pdata.get("security_audit"),
        "wiki_summary": pdata.get("wiki_summary"),
        "audit_id": pdata.get("audit_id"),
        "db_project_id": canonical_id,
        "user_id": pdata.get("user_id"),
    }


def _audit_row_to_pdata(row: dict[str, Any]) -> dict[str, Any]:
    result = row.get("result") or {}
    if not isinstance(result, dict):
        result = {}

    project_meta = row.get("projects") or {}
    if isinstance(project_meta, list) and project_meta:
        project_meta = project_meta[0]
    if not isinstance(project_meta, dict):
        project_meta = {}

    dead_code = result.get("dead_code_result") or result.get("dead_code_audit")
    security = result.get("security_result") or result.get("security_audit")
    structure = result
    if result.get("static_violations") is None and isinstance(result.get("structure_audit"), dict):
        structure = result.get("structure_audit") or result

    project_id = str(row.get("project_id") or "")
    status = "done" if row.get("status") == "succeeded" else str(row.get("status") or "done")

    return {
        "id": project_id,
        "audit_id": str(row.get("audit_id") or ""),
        "name": project_meta.get("display_name") or result.get("display_name") or result.get("name") or "Repository",
        "display_name": project_meta.get("display_name") or result.get("display_name"),
        "owner": project_meta.get("owner") or result.get("owner"),
        "repository_name": project_meta.get("repository_name") or result.get("repository_name"),
        "repository_url": project_meta.get("repository_url") or result.get("repository_url"),
        "status": status,
        "error": result.get("error", ""),
        "total_files": result.get("total_files", 0),
        "total_lines": result.get("total_lines", 0),
        "created_at": row.get("created_at") or result.get("created_at", ""),
        "score": row.get("overall_score") if row.get("overall_score") is not None else result.get("score", 100),
        "is_valid": row.get("is_valid") if row.get("is_valid") is not None else result.get("is_valid", True),
        "branch": row.get("branch") or result.get("branch", "main"),
        "progress": result.get("progress", []),
        "structure_audit": structure,
        "dead_code_audit": dead_code,
        "security_audit": security,
        "wiki_summary": result.get("wiki_summary"),
        "user_id": row.get("user_id"),
    }


def purge_project_cache(*keys: str, user_id: str | None = None) -> None:
    """Remove project entries from the in-memory scan/wiki cache and cancel in-flight scans."""
    projects = get_projects()
    normalized = {str(key).strip() for key in keys if str(key).strip()}
    if not normalized:
        return

    for cache_key, proj in list(projects.items()):
        if not isinstance(proj, dict):
            if cache_key in normalized:
                projects.pop(cache_key, None)
            continue

        if user_id and not owned_by_user(proj, user_id):
            continue

        info = proj.get("info")
        aliases = {
            str(cache_key),
            str(proj.get("audit_id") or ""),
            str(proj.get("db_project_id") or ""),
            str(proj.get("id") or ""),
            str(getattr(info, "id", "") or ""),
        }
        if aliases & normalized or cache_key in normalized:
            proj["_cancelled"] = True
            proj["_deleted"] = True
            proj["_worker_live"] = False
            projects.pop(cache_key, None)


def _cache_project(projects: dict[str, Any], cache_key: str, proj: dict[str, Any]) -> None:
    projects[cache_key] = proj
    info = proj.get("info")
    canonical_id = getattr(info, "id", None) if info is not None else proj.get("db_project_id")
    if canonical_id and str(canonical_id) != cache_key:
        projects[str(canonical_id)] = proj
    audit_id = proj.get("audit_id")
    if audit_id and str(audit_id) not in projects:
        projects[str(audit_id)] = proj


async def ensure_project_loaded(project_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    """Load project from memory, SQLite cache, or Supabase for this app user only."""
    if not user_id:
        return None

    projects = get_projects()
    if project_id in projects:
        proj = projects[project_id]
        return proj if owned_by_user(proj, user_id) else None

    try:
        cache = await ensure_cache()
        pdata = await cache.load_project(project_id)
        if pdata and isinstance(pdata, dict) and str(pdata.get("user_id") or "") == str(user_id):
            proj = _build_proj_from_pdata(pdata, project_id)
            _cache_project(projects, project_id, proj)
            return proj
    except Exception as exc:
        logger.warning("Could not restore project %s from SQLite: %s", project_id, exc)

    try:
        from app.core.db.repositories.audits import resolve_audit_run
        from app.core.supabase.client import supabase_available

        if supabase_available():
            row = resolve_audit_run(identifier=project_id, user_id=user_id)
            if row:
                pdata = _audit_row_to_pdata(row)
                proj = _build_proj_from_pdata(pdata, project_id)
                if owned_by_user(proj, user_id):
                    _cache_project(projects, project_id, proj)
                    logger.info("Restored project %s from Supabase audit run", project_id)
                    return proj
    except Exception as exc:
        logger.warning("Could not restore project %s from Supabase: %s", project_id, exc)

    return None


async def ensure_project_context(project_id: str, user_id: str | None = None):
    """Return ProjectContext with file contents, re-ingesting from this user's workspace."""
    import asyncio

    from repoaudit.indexing.models import ProjectContext
    from repoaudit.investigation.project_resolver import resolve_project_directory
    from repoaudit.platform.config import Config

    if not user_id:
        return None, None

    proj = await ensure_project_loaded(project_id, user_id=user_id)
    if not proj or not owned_by_user(proj, user_id):
        return None, None

    existing = proj.get("project")
    if existing is not None:
        return proj, existing

    info = proj.get("info")
    project_name = getattr(info, "name", None) or proj.get("display_name") or "Repository"
    repo_url = proj.get("repository_url") or ""

    cfg = Config.load()
    project: ProjectContext | None = None

    snap_dir = resolve_project_directory(
        project_name=project_name,
        project_id=project_id,
        repo_path="",
        user_id=user_id,
    )
    if snap_dir is not None:
        from repoaudit.ingestion.local import ingest_local

        try:
            project = await asyncio.to_thread(
                ingest_local,
                str(snap_dir),
                cfg.max_file_size,
                cfg.max_files,
            )
            if project:
                project.name = project_name
                logger.info(
                    "Restored project context for %s from %s (%d files)",
                    project_id,
                    snap_dir,
                    len(project.files),
                )
        except Exception as exc:
            logger.warning("Failed to ingest snapshot for %s: %s", project_id, exc)

    if project is None and repo_url:
        from app.core.workspace import ingest_workspace_dir
        from app.modules.github.shared.store import github_connection_store
        from repoaudit.ingestion.github.client import ingest_github, parse_git_url

        parsed = parse_git_url(repo_url)
        dest = None
        token = github_connection_store.get_access_token(user_id)
        if parsed:
            _host, owner_name, repo_name = parsed
            dest = ingest_workspace_dir(user_id, owner_name, repo_name)
        if dest is not None:
            try:
                project = await asyncio.to_thread(
                    ingest_github,
                    repo_url,
                    cfg.max_file_size,
                    cfg.max_files,
                    False,
                    token,
                    dest,
                )
                if project:
                    project.name = project_name
                    logger.info(
                        "Restored project context for %s from GitHub (%d files)",
                        project_id,
                        len(project.files),
                    )
            except Exception as exc:
                logger.warning("Failed to re-ingest GitHub repo for %s: %s", project_id, exc)

    if project is not None:
        proj["project"] = project

    return proj, project
