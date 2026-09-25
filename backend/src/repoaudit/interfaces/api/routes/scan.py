"""scan and project management endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status as http_status
from fastapi.responses import StreamingResponse

from app.core.security.deps import CurrentUser, get_current_user
from app.core.demo import is_demo_mapping
from repoaudit.interfaces.api.schemas import ProjectInfo, ScanRequest
from repoaudit.interfaces.api.runtime import ensure_cache, get_projects, ensure_project_loaded, owned_by_user
from repoaudit.indexing.wiki.serialization import serialize_sidebar
from repoaudit.platform.config import Config, resolve_model

router = APIRouter()
logger = logging.getLogger(__name__)

STALE_SCAN_SECONDS = 15 * 60
CACHE_PERSIST_INTERVAL_SECONDS = 15.0
STALE_SCAN_MESSAGE = (
    "Scan interrupted because the worker stopped or stalled. Run the audit again."
)


def _resolve_display_name(req: ScanRequest, fallback: str) -> str:
    """Prefer UI/GitHub identity over snapshot folder / commit SHA names."""
    if req.display_name and req.display_name.strip():
        return req.display_name.strip()
    if req.owner and req.repository_name:
        return f"{req.owner.strip()}/{req.repository_name.strip()}"
    if req.repository_name and req.repository_name.strip():
        return req.repository_name.strip()
    name = (fallback or "").strip()
    # Avoid showing raw commit SHAs as the repository name
    if len(name) == 40 and all(c in "0123456789abcdef" for c in name.lower()):
        return "Repository"
    return name or "Repository"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utcnow_iso() -> str:
    return _utcnow().isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _scan_status(proj: dict) -> str:
    info = proj.get("info")
    if info is not None:
        return str(getattr(info, "status", "") or "")
    return str(proj.get("status") or "")


def _touch_heartbeat(proj: dict) -> None:
    proj["last_heartbeat"] = _utcnow_iso()


def _heartbeat_stale(proj: dict) -> bool:
    ts = _parse_iso(proj.get("last_heartbeat") or proj.get("created_at"))
    if ts is None:
        return False
    return (_utcnow() - ts).total_seconds() > STALE_SCAN_SECONDS


def _should_expire(proj: dict) -> bool:
    if _scan_status(proj) not in ("pending", "scanning"):
        return False
    if not proj.get("_worker_live"):
        return True
    return _heartbeat_stale(proj)


def _mark_interrupted(proj: dict, message: str = STALE_SCAN_MESSAGE) -> None:
    info = proj.get("info")
    if info is not None:
        info.status = "error"
        info.error = message
    else:
        proj["status"] = "error"
        proj["error"] = message
    progress = proj.setdefault("progress", [])
    marker = f"Error: {message}"
    if marker not in progress:
        progress.append(marker)
    proj["_worker_live"] = False
    _touch_heartbeat(proj)


def _iter_unique_projects(projects: dict) -> list[tuple[str, dict]]:
    seen: set[int] = set()
    items: list[tuple[str, dict]] = []
    for pid, pdata in projects.items():
        obj_id = id(pdata)
        if obj_id in seen:
            continue
        seen.add(obj_id)
        items.append((str(pid), pdata))
    return items


def _live_project_ids(projects: dict) -> set[str]:
    ids: set[str] = set()
    for pid, pdata in _iter_unique_projects(projects):
        if not pdata.get("_worker_live"):
            continue
        ids.add(pid)
        info = pdata.get("info")
        info_id = getattr(info, "id", None) if info is not None else None
        if info_id:
            ids.add(str(info_id))
        db_id = pdata.get("db_project_id")
        if db_id:
            ids.add(str(db_id))
    return ids


def _find_active_scan_id(
    projects: dict,
    *,
    owner: str | None,
    repository_name: str | None,
    branch: str,
    project_id: str | None,
    user_id: str | None = None,
) -> str | None:
    owner = (owner or "").strip()
    repository_name = (repository_name or "").strip()
    branch = (branch or "main").strip() or "main"
    project_id = (project_id or "").strip() or None

    for pid, pdata in _iter_unique_projects(projects):
        if user_id and str(pdata.get("user_id") or "") != str(user_id):
            continue
        if _scan_status(pdata) not in ("pending", "scanning"):
            continue
        if not pdata.get("_worker_live"):
            continue
        info = pdata.get("info")
        info_id = str(getattr(info, "id", "") or "")
        aliases = {pid, info_id, str(pdata.get("db_project_id") or "")}
        if project_id and project_id in aliases:
            return info_id or pid
        pdata_owner = (pdata.get("owner") or "").strip()
        pdata_repo = (pdata.get("repository_name") or "").strip()
        pdata_branch = (
            str(pdata.get("branch") or "")
            or (str(getattr(info, "branch", "") or "") if info is not None else "")
            or "main"
        ).strip() or "main"
        if (
            owner
            and repository_name
            and pdata_owner == owner
            and pdata_repo == repository_name
            and pdata_branch == branch
        ):
            return info_id or pid
    return None


def _progress_payload(project_id: str, proj: dict) -> dict:
    info = proj.get("info")
    return {
        "id": getattr(info, "id", project_id) if info is not None else project_id,
        "name": getattr(info, "name", "") if info is not None else "",
        "status": getattr(info, "status", "error") if info is not None else "error",
        "progress": list(proj.get("progress") or []),
        "error": (getattr(info, "error", "") if info is not None else "") or "",
    }


def _schedule_cache_persist(project_id: str, proj: dict, *, force: bool = False) -> None:
    """Persist scanning state to SQLite without blocking the worker."""
    if proj.get("_cancelled") or proj.get("_deleted"):
        return
    _touch_heartbeat(proj)
    now = time.monotonic()
    last = float(proj.get("_last_persist_mono") or 0.0)
    if not force and (now - last) < CACHE_PERSIST_INTERVAL_SECONDS:
        return
    if proj.get("_persist_in_flight"):
        return
    proj["_last_persist_mono"] = now
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    async def _run() -> None:
        proj["_persist_in_flight"] = True
        try:
            if not proj.get("_cancelled") and not proj.get("_deleted"):
                await _persist_scan(project_id, proj, include_supabase=False)
        except Exception:
            logger.debug("incremental scan persist failed for %s", project_id, exc_info=True)
        finally:
            proj["_persist_in_flight"] = False

    loop.create_task(_run())


async def _persist_scan(project_id: str, proj: dict, *, include_supabase: bool | None = None):
    """Persist scan snapshot. SQLite always; Supabase only for terminal done/error."""
    if proj.get("_cancelled") or proj.get("_deleted"):
        return
    try:
        cache = await ensure_cache()
        info = proj["info"]
        branch = proj.get("branch") or getattr(info, "branch", None) or "main"
        sa = proj.get("structure_audit")
        score = 100
        is_valid = True
        sa_dict = None
        if sa:
            score = getattr(sa, "overall_score", 100)
            is_valid = getattr(sa, "is_valid", True)
            if hasattr(sa, "model_dump"):
                sa_dict = sa.model_dump()
            elif hasattr(sa, "__dict__"):
                sa_dict = sa.__dict__

        dca = proj.get("dead_code_audit")
        dca_dict = None
        if dca:
            if hasattr(dca, "model_dump"):
                dca_dict = dca.model_dump()
            elif hasattr(dca, "__dict__"):
                dca_dict = dca.__dict__

        seca = proj.get("security_audit")
        seca_dict = None
        if seca:
            if hasattr(seca, "model_dump"):
                seca_dict = seca.model_dump()
            elif hasattr(seca, "__dict__"):
                seca_dict = seca.__dict__

        wiki = proj.get("wiki")
        wiki_summary = None
        if wiki and hasattr(wiki, "pages"):
            wiki_summary = {
                "project_name": getattr(wiki, "project_name", info.name),
                "sidebar": serialize_sidebar(wiki.sidebar) if hasattr(wiki, "sidebar") else [],
                "pages": [
                    {
                        "id": p.id,
                        "title": p.title,
                        "order": getattr(p, "order", 0),
                        "parent_id": getattr(p, "parent_id", None),
                        "content": getattr(p, "content", ""),
                    }
                    for p in wiki.pages
                ],
            }

        data = {
            "id": project_id,
            "name": info.name or "Repository",
            "display_name": proj.get("display_name") or info.name or "Repository",
            "owner": proj.get("owner"),
            "repository_name": proj.get("repository_name"),
            "repository_url": proj.get("repository_url"),
            "user_id": proj.get("user_id"),
            "status": info.status,
            "error": info.error,
            "total_files": info.total_files,
            "total_lines": info.total_lines,
            "created_at": proj.get("created_at", ""),
            "score": score,
            "is_valid": is_valid,
            "branch": branch,
            "progress": proj.get("progress", []),
            "last_heartbeat": proj.get("last_heartbeat") or proj.get("created_at", ""),
            "structure_audit": sa_dict,
            "dead_code_audit": dca_dict,
            "security_audit": seca_dict,
            "wiki_summary": wiki_summary,
        }

        # 1. Always persist to local SQLite cache
        await cache.save_project(project_id, data)

        # 2. Persist to Supabase (projects + repo_snapshots + audit_runs)
        from app.core.db.persist_scan import persist_full_scan

        db_project_id = proj.get("db_project_id")
        user_id = proj.get("user_id")
        workspace_path = proj.get("scan_path") or ""
        status = getattr(info, "status", "")
        if include_supabase is None:
            include_supabase = status in ("done", "error")

        if include_supabase and db_project_id:
            scan_status = "done" if status == "done" else "error"
            audit_id = persist_full_scan(
                db_project_id=str(db_project_id),
                user_id=str(user_id) if user_id else None,
                branch=branch,
                workspace_path=workspace_path,
                scan_summary=data,
                structure_audit=sa_dict,
                dead_code_audit=dca_dict,
                wiki_summary=wiki_summary,
                scan_status=scan_status,
                security_audit=seca_dict,
            )
            if audit_id:
                data["audit_id"] = audit_id
                await cache.save_project(project_id, data)

    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Failed to persist scan %s: %s", project_id, exc)


@router.post("/scan", response_model=ProjectInfo)
async def start_scan(
    req: ScanRequest,
    background_tasks: BackgroundTasks,
    x_api_key: str | None = Header(None),
    user: CurrentUser = Depends(get_current_user),
):
    # Warm cache in the request lifecycle BEFORE background work / possible reload.
    await ensure_cache()

    from app.core.db.persist_scan import resolve_db_project_id
    from app.core.workspace import path_belongs_to_user
    from app.modules.github.shared.users import resolve_user_id
    from app.modules.projects.shared.store import project_store

    branch = (req.branch or "main").strip() or "main"
    user_id = resolve_user_id(user)
    if not user_id:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Sign in required to run an audit",
        )

    scan_path = (req.path or "").strip() or None
    scan_url = (req.url or "").strip() or None
    if scan_path and not path_belongs_to_user(scan_path, user_id):
        if not scan_url:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Scan path is not in this account's workspace",
            )
        scan_path = None
        req.path = None
    else:
        req.path = scan_path

    db_project_id = resolve_db_project_id(
        requested_project_id=(req.project_id or "").strip() or None,
        user_id=user_id,
        display_name=_resolve_display_name(req, ""),
        branch=branch,
        owner=(req.owner or "").strip() or None,
        repository_name=(req.repository_name or "").strip() or None,
        repository_url=scan_url,
        workspace_path=scan_path,
    )

    initial_name = _resolve_display_name(req, "")
    owner = (req.owner or "").strip() or None
    repository_name = (req.repository_name or "").strip() or None
    created_at = _utcnow_iso()
    projects = get_projects()

    for pid, pdata in _iter_unique_projects(projects):
        if _should_expire(pdata):
            _mark_interrupted(pdata)

    active_id = _find_active_scan_id(
        projects,
        owner=owner,
        repository_name=repository_name,
        branch=branch,
        project_id=(db_project_id or req.project_id or "").strip() or None,
        user_id=user_id,
    )
    if active_id:
        for pid, pdata in _iter_unique_projects(projects):
            info_obj = pdata.get("info")
            aliases = {
                pid,
                str(getattr(info_obj, "id", "") or ""),
                str(pdata.get("db_project_id") or ""),
            }
            if active_id in aliases and info_obj is not None:
                return info_obj

    if db_project_id and project_store.get_for_user(db_project_id, user_id):
        project_id = db_project_id
    else:
        project_id = str(uuid.uuid4())[:8]
        db_project_id = db_project_id or None

    info = ProjectInfo(id=project_id, name=initial_name if initial_name != "Repository" else "", status="pending", branch=branch)
    projects[project_id] = {
        "info": info,
        "wiki": None,
        "project": None,
        "progress": [],
        "created_at": created_at,
        "last_heartbeat": created_at,
        "score": 100,
        "is_valid": True,
        "branch": branch,
        "owner": owner,
        "repository_name": repository_name,
        "repository_url": (req.url or "").strip() or None,
        "display_name": (req.display_name or "").strip() or None,
        "db_project_id": db_project_id,
        "user_id": user_id,
        "scan_path": scan_path,
        "_worker_live": True,
    }
    await _persist_scan(project_id, projects[project_id], include_supabase=False)

    background_tasks.add_task(_run_scan, project_id, req, x_api_key)
    return info


@router.get("/scans")
async def list_scans(user: CurrentUser = Depends(get_current_user)):
    """Returns metadata for historical/in-flight scans (no heavy audit/wiki blobs)."""
    from app.modules.github.shared.users import resolve_user_id
    from repoaudit.interfaces.api.scan_enrichment import (
        slim_scan_record_for_list,
        summary_has_active_scan,
    )

    projects = get_projects()
    # Canonical key = project_id when available (avoids SQLite+Supabase duplicates).
    records_by_id: dict[str, dict] = {}
    known_audit_ids: set[str] = set()
    user_id = resolve_user_id(user)
    if not user_id:
        return []

    for pid, pdata in _iter_unique_projects(projects):
        if _should_expire(pdata):
            _mark_interrupted(pdata)
            try:
                await _persist_scan(pid, pdata)
            except Exception:
                logger.debug("failed to persist expired scan %s", pid, exc_info=True)

    live_ids = _live_project_ids(projects)

    def _upsert(record: dict, *, prefer: bool = False) -> None:
        pid = str(record.get("project_id") or record.get("id") or "")
        audit_id = str(record.get("audit_id") or "")
        key = pid or audit_id
        if not key:
            return
        if audit_id:
            known_audit_ids.add(audit_id)
        existing = records_by_id.get(key)
        if existing and not prefer:
            # Merge light fields; keep newer created_at when present
            merged = {**existing, **{k: v for k, v in record.items() if v not in (None, "", [])}}
            records_by_id[key] = merged
        else:
            records_by_id[key] = record
        # Drop duplicate under the other alias so one audit = one row
        if pid and audit_id and pid != audit_id:
            other = audit_id if key == pid else pid
            if other in records_by_id and other != key:
                records_by_id.pop(other, None)

    # 1. Fetch from SQLite persistent cache
    try:
        cache = await ensure_cache()
        cached_projects = await cache.list_projects()
        for pdata in cached_projects:
            p_user = str(pdata.get("user_id") or "")
            if p_user != str(user_id):
                continue
            pid = pdata.get("id")
            if pid:
                record = dict(pdata)
                if record.get("status") in ("pending", "scanning") and str(pid) not in live_ids:
                    record["status"] = "error"
                    record["error"] = STALE_SCAN_MESSAGE
                    try:
                        await cache.save_project(str(pid), record)
                    except Exception:
                        logger.debug("failed to persist orphaned scan %s", pid, exc_info=True)
                record.setdefault("project_id", pid)
                _upsert(record)
    except Exception:
        pass

    # 2. Fetch audit_runs from Supabase (preferred over SQLite duplicates)
    try:
        from app.core.db.repositories.audits import list_audit_runs

        for row in list_audit_runs(user_id=user_id, limit=200):
            result = row.get("result") or {}
            if not isinstance(result, dict):
                result = {}
            project_meta = row.get("projects") or {}
            if isinstance(project_meta, list) and project_meta:
                project_meta = project_meta[0]
            if not isinstance(project_meta, dict):
                project_meta = {}
            pid = str(row.get("project_id") or "")
            audit_id = str(row.get("audit_id") or "")
            if not (audit_id or pid):
                continue
            merged = {
                "id": pid or audit_id,
                "project_id": pid,
                "audit_id": audit_id,
                "name": project_meta.get("display_name") or result.get("display_name") or "Repository",
                "display_name": project_meta.get("display_name") or result.get("display_name"),
                "owner": project_meta.get("owner") or result.get("owner"),
                "repository_name": project_meta.get("repository_name") or result.get("repository_name"),
                "repository_url": project_meta.get("repository_url") or result.get("repository_url"),
                "status": "done" if row.get("status") == "succeeded" else row.get("status", "done"),
                "total_files": result.get("total_files", 0),
                "total_lines": result.get("total_lines", 0),
                "created_at": row.get("created_at") or result.get("created_at", ""),
                "score": row.get("overall_score") if row.get("overall_score") is not None else result.get("score", 100),
                "is_valid": row.get("is_valid") if row.get("is_valid") is not None else result.get("is_valid", True),
                "branch": row.get("branch") or result.get("branch", "main"),
                "audit_type": row.get("audit_type"),
            }
            _upsert(merged, prefer=True)
    except Exception:
        pass

    # 3. Fetch from Supabase projects table (only if audit_id still exists)
    try:
        from app.core.supabase.client import get_supabase_client, supabase_available

        if supabase_available():
            sb_client = get_supabase_client()
            query = sb_client.table("projects").select("*").eq("user_id", str(user_id))
            res = query.execute()
            if res.data and isinstance(res.data, list):
                for item in res.data:
                    pid = str(item.get("project_id", ""))
                    summary = item.get("summary") or {}
                    if not pid or pid in records_by_id:
                        continue
                    if not summary_has_active_scan(summary, known_audit_ids=known_audit_ids):
                        continue
                    merged = dict(summary) if isinstance(summary, dict) else {}
                    merged.setdefault("id", pid)
                    merged.setdefault("project_id", pid)
                    merged.setdefault("name", item.get("display_name") or "Repository")
                    merged.setdefault("display_name", item.get("display_name"))
                    merged.setdefault("owner", item.get("owner"))
                    merged.setdefault("repository_name", item.get("repository_name"))
                    merged.setdefault("branch", item.get("default_branch") or summary.get("branch"))
                    merged.setdefault("default_branch", item.get("default_branch"))
                    _upsert(merged)
    except Exception:
        pass

    # 4. Overlay in-memory projects (active/recent scans) — metadata only
    for pid, pdata in projects.items():
        if str(pdata.get("user_id") or "") != str(user_id):
            continue
        if pdata.get("_cancelled") or pdata.get("_deleted"):
            continue
        if "info" not in pdata:
            continue
        info = pdata["info"]
        raw = dict(records_by_id.get(pid, {}))
        raw.update({
            "id": pid,
            "project_id": pid,
            "audit_id": pdata.get("audit_id") or raw.get("audit_id") or "",
            "name": info.name or raw.get("name") or "Repository",
            "display_name": pdata.get("display_name") or info.name or raw.get("display_name"),
            "owner": pdata.get("owner") or raw.get("owner"),
            "repository_name": pdata.get("repository_name") or raw.get("repository_name"),
            "repository_url": pdata.get("repository_url") or raw.get("repository_url"),
            "status": info.status,
            "error": info.error,
            "total_files": info.total_files,
            "total_lines": info.total_lines,
            "created_at": pdata.get("created_at", raw.get("created_at", "")),
            "last_heartbeat": pdata.get("last_heartbeat", raw.get("last_heartbeat", "")),
            "branch": pdata.get("branch") or getattr(info, "branch", None) or raw.get("branch"),
            "score": pdata.get("score", raw.get("score", 100)),
            "is_valid": pdata.get("is_valid", raw.get("is_valid", True)),
        })
        _upsert(raw, prefer=True)

    records = [slim_scan_record_for_list(raw) for raw in records_by_id.values()]
    records = [item for item in records if not is_demo_mapping(item)]
    records.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return records


@router.get("/project/{project_id}")
async def get_project(project_id: str, user: CurrentUser = Depends(get_current_user)):
    from app.modules.github.shared.users import resolve_user_id

    user_id = resolve_user_id(user)
    proj = await ensure_project_loaded(project_id, user_id=user_id)
    if not proj or not owned_by_user(proj, user_id):
        return {"error": "Project not found"}
    if _should_expire(proj):
        _mark_interrupted(proj)
        await _persist_scan(project_id, proj)
    return proj["info"]


@router.get("/project/{project_id}/progress")
async def get_scan_progress(project_id: str, user: CurrentUser = Depends(get_current_user)):
    """HTTP snapshot of scan status and logs. Source of truth for the UI (Railway-safe)."""
    from app.modules.github.shared.users import resolve_user_id

    user_id = resolve_user_id(user)
    projects = get_projects()
    proj = projects.get(project_id)
    if not proj:
        proj = await ensure_project_loaded(project_id, user_id=user_id)
    if not proj or not owned_by_user(proj, user_id):
        return {
            "id": project_id,
            "name": "",
            "status": "error",
            "progress": [],
            "error": "Project not found",
        }
    if _should_expire(proj):
        _mark_interrupted(proj)
        await _persist_scan(project_id, proj)
    return _progress_payload(project_id, proj)


@router.get("/project/{project_id}/status")
async def stream_status(project_id: str, user: CurrentUser = Depends(get_current_user)):
    """SSE endpoint for scan progress updates."""
    from app.modules.github.shared.users import resolve_user_id

    user_id = resolve_user_id(user)
    if not user_id:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Sign in required",
        )

    async def event_stream():
        projects = get_projects()
        proj = projects.get(project_id)
        if not proj or not owned_by_user(proj, user_id):
            proj = await ensure_project_loaded(project_id, user_id=user_id)

        if not proj or not owned_by_user(proj, user_id):
            yield f"data: {json.dumps({'error': 'not found'})}\n\n"
            return

        seen = 0
        heartbeat = 0
        while True:
            projects = get_projects()
            proj = projects.get(project_id) or proj

            progress = proj.get("progress", []) if proj else []
            if seen < len(progress):
                while seen < len(progress):
                    yield f"data: {json.dumps({'step': progress[seen]})}\n\n"
                    seen += 1
                heartbeat = 0
            else:
                heartbeat += 1
                if heartbeat >= 10:  # Send ping comment every ~5 seconds to keep HTTP/2 connection active
                    yield ": ping\n\n"
                    heartbeat = 0

            info = proj.get("info") if proj else None
            status = getattr(info, "status", "done") if info else "done"
            if status in ("done", "error"):
                yield f"data: {json.dumps({'status': status})}\n\n"
                break

            await asyncio.sleep(0.5)

    headers = {
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)



async def _run_scan(project_id: str, req: ScanRequest, user_api_key: str | None):
    """background task that runs the full scan + analysis pipeline."""
    projects = get_projects()
    proj = projects[project_id]
    proj["info"].status = "scanning"
    proj["_worker_live"] = True
    _touch_heartbeat(proj)
    await _persist_scan(project_id, proj, include_supabase=False)

    try:
        # Always re-ensure at scan start (survives lifespan close during --reload).
        await ensure_cache()

        cfg = Config.load()
        if req.language:
            cfg.language = req.language
        if req.model:
            # UI may pick a model, but env operation tiers (MODEL_WIKI, MODEL_LITE, …) stay in charge.
            cfg.model = resolve_model(req.model)
        if user_api_key:
            cfg.api_key = user_api_key
        elif req.api_key:
            cfg.api_key = req.api_key

        def progress(msg: str):
            proj["progress"].append(msg)
            _schedule_cache_persist(project_id, proj)

        progress("Ingesting project...")
        project = None
        user_id = proj.get("user_id")
        github_token = None
        if user_id:
            try:
                from app.modules.github.shared.store import github_connection_store

                github_token = github_connection_store.get_access_token(str(user_id))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not load GitHub token for scan %s: %s", project_id, exc)

        if req.path:
            from app.core.workspace import path_belongs_to_user

            p = Path(req.path).resolve()
            if p.exists() and p.is_dir() and path_belongs_to_user(p, str(user_id) if user_id else None):
                from repoaudit.ingestion.local import ingest_local

                project = await asyncio.to_thread(
                    ingest_local, str(p), cfg.max_file_size, cfg.max_files
                )
                proj["scan_path"] = str(p)

        if project is None and req.url:
            from repoaudit.ingestion.github.client import ingest_github, parse_git_url

            parsed = parse_git_url(req.url)
            dest = None
            if user_id:
                from app.core.workspace import ingest_workspace_dir, user_workspace_dir

                if parsed:
                    _host, owner_name, repo_name = parsed
                    dest = ingest_workspace_dir(str(user_id), owner_name, repo_name)
                else:
                    dest = user_workspace_dir(str(user_id)) / "ingest" / "unknown"
            if dest is None:
                raise ValueError("Sign in required to clone a repository for scan")
            project = await asyncio.to_thread(
                ingest_github,
                req.url,
                cfg.max_file_size,
                cfg.max_files,
                False,
                github_token,
                dest,
            )
            if project is not None:
                proj["scan_path"] = str(dest)

        if project is None and req.path:
            raise ValueError("Scan path is not in this account's workspace")

        if project is None:
            raise ValueError("Either a valid local path or repository url must be provided")


        proj["project"] = project
        display_name = _resolve_display_name(req, project.name)
        project.name = display_name
        proj["info"].name = display_name
        proj["display_name"] = display_name
        proj["info"].branch = proj.get("branch") or (req.branch or "main").strip() or "main"
        proj["info"].total_files = len(project.files)
        proj["info"].total_lines = project.total_lines
        if req.owner:
            proj["owner"] = req.owner.strip()
        if req.repository_name:
            proj["repository_name"] = req.repository_name.strip()
        if req.url:
            proj["repository_url"] = req.url.strip()

        if not cfg.api_key:
            err_msg = (
                "No API key configured. Please set your API key in Settings or .env file."
            )
            proj["info"].status = "error"
            proj["info"].error = err_msg
            proj["_worker_live"] = False
            progress(f"Error: {err_msg}")
            await _persist_scan(project_id, proj)
            return

        from repoaudit.indexing.analyzer.analyzer import Analyzer
        from repoaudit.indexing.graph.graph import DependencyGraph
        from repoaudit.indexing.llm.client import LLMClient
        from repoaudit.indexing.wiki.builder import WikiBuilder

        cache = await ensure_cache()
        llm = LLMClient(
            model=cfg.model,
            api_key=cfg.api_key,
            api_base=cfg.api_base,
            operation_models=cfg.get_operation_models(),
        )
        analyzer = Analyzer(
            llm=llm, cache=cache, language=cfg.language, concurrency=cfg.concurrency
        )

        if proj.get("_cancelled") or proj.get("_deleted"):
            return
        wiki_data = await analyzer.analyze(project, on_progress=progress)

        if proj.get("_cancelled") or proj.get("_deleted"):
            return
        progress("Executing dead code & unused dependency audit...")
        from repoaudit.audit.engine import AuditEngine

        audit_engine = AuditEngine()
        dead_code_audit = audit_engine.run_dead_code_audit(project)
        wiki_data.dead_code_audit = dead_code_audit
        proj["dead_code_audit"] = dead_code_audit

        if proj.get("_cancelled") or proj.get("_deleted"):
            return
        progress("Scanning for secrets, vulnerable dependencies, and dangerous patterns...")
        security_audit = await audit_engine.run_security_audit(project, llm)
        wiki_data.security_audit = security_audit
        proj["security_audit"] = security_audit

        if proj.get("_cancelled") or proj.get("_deleted"):
            return
        progress("Auditing repository folder structure & architecture...")
        from repoaudit.audit.structure_style import (
            DEFAULT_STRUCTURE_STYLE,
            STRUCTURE_STYLE_CONSERVATIVE,
        )

        style = (req.structure_style or DEFAULT_STRUCTURE_STYLE).strip().lower()
        if style not in {DEFAULT_STRUCTURE_STYLE, STRUCTURE_STYLE_CONSERVATIVE, "action_api"}:
            style = DEFAULT_STRUCTURE_STYLE
        structure_audit = await audit_engine.run_structure_audit(
            project,
            llm,
            dead_code_result=dead_code_audit,
            security_result=security_audit,
            structure_style=style,
        )
        wiki_data.structure_audit = structure_audit
        proj["structure_audit"] = structure_audit

        if proj.get("_cancelled") or proj.get("_deleted"):
            return
        graph = DependencyGraph.build_from_project(project)
        builder = WikiBuilder()
        wiki = builder.build(project, wiki_data, graph)

        if proj.get("_cancelled") or proj.get("_deleted"):
            return
        proj["wiki"] = wiki
        proj["info"].status = "done"
        proj["_worker_live"] = False
        progress("Done!")
        await _persist_scan(project_id, proj)

    except Exception as e:
        import traceback

        logger.exception("scan failed for %s", project_id)
        proj["info"].status = "error"
        proj["info"].error = f"{type(e).__name__}: {e}"
        proj["_worker_live"] = False
        proj["progress"].append(f"Error: {type(e).__name__}: {e}")
        _ = traceback.format_exc()
        await _persist_scan(project_id, proj)

