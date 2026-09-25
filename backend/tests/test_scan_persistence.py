"""Tests for scan database persistence and historical retrieval."""

from __future__ import annotations

import asyncio

import pytest
from repoaudit.indexing.cache.cache import Cache
from repoaudit.interfaces.api.schemas import ProjectInfo
from repoaudit.interfaces.api.routes.scan import _persist_scan, list_scans
from repoaudit.interfaces.api.runtime import get_projects, ensure_project_loaded


def test_cache_list_projects(tmp_path):
    c = Cache(db_path=tmp_path / "cache.db")
    asyncio.run(c.init())

    asyncio.run(c.save_project("scan1", {"id": "scan1", "name": "Repo 1", "score": 95}))
    asyncio.run(c.save_project("scan2", {"id": "scan2", "name": "Repo 2", "score": 88}))

    projects = asyncio.run(c.list_projects())
    assert len(projects) == 2
    ids = [p["id"] for p in projects]
    assert "scan1" in ids
    assert "scan2" in ids

    loaded = asyncio.run(c.load_project("scan1"))
    assert loaded["name"] == "Repo 1"
    assert loaded["score"] == 95

    asyncio.run(c.close())


def test_persist_and_list_scans(tmp_path):
    cache = Cache(db_path=tmp_path / "cache.db")
    asyncio.run(cache.init())

    info = ProjectInfo(id="p_test1", name="TestRepo", status="done", total_files=10, total_lines=500)
    proj = {
        "info": info,
        "created_at": "2026-08-11T12:00:00Z",
        "score": 92,
        "is_valid": True,
        "progress": ["Ingesting project...", "Done!"],
    }

    asyncio.run(cache.save_project("p_test1", {
        "id": "p_test1",
        "name": "TestRepo",
        "status": "done",
        "total_files": 10,
        "total_lines": 500,
        "score": 92,
        "created_at": "2026-08-11T12:00:00Z",
    }))

    projects = asyncio.run(cache.list_projects())
    p_record = next((r for r in projects if r["id"] == "p_test1"), None)
    assert p_record is not None
    assert p_record["name"] == "TestRepo"
    assert p_record["status"] == "done"
    assert p_record["score"] == 92
    asyncio.run(cache.close())


def test_ensure_project_loaded_from_db(tmp_path):
    cache = Cache(db_path=tmp_path / "cache.db")
    asyncio.run(cache.init())

    info = ProjectInfo(id="p_test2", name="LoadedRepo", status="done")
    proj_data = {
        "id": "p_test2",
        "name": "LoadedRepo",
        "status": "done",
        "score": 99,
        "is_valid": True,
        "wiki_summary": {
            "project_name": "LoadedRepo",
            "pages": [{"id": "overview", "title": "Overview", "content": "Sample content"}],
        },
    }

    asyncio.run(cache.save_project("p_test2", proj_data))
    loaded = asyncio.run(cache.load_project("p_test2"))

    assert loaded is not None
    assert loaded["name"] == "LoadedRepo"
    assert loaded["wiki_summary"]["pages"][0]["title"] == "Overview"
    asyncio.run(cache.close())


def test_ensure_project_loaded_from_supabase(monkeypatch, tmp_path):
    get_projects().clear()

    async def _cache_with_no_project():
        cache = Cache(db_path=tmp_path / "cache.db")
        await cache.init()
        return cache

    monkeypatch.setattr(
        "repoaudit.interfaces.api.runtime.ensure_cache",
        _cache_with_no_project,
    )

    audit_row = {
        "audit_id": "audit-1111",
        "project_id": "project-2222",
        "user_id": "11111111-1111-1111-1111-111111111111",
        "status": "succeeded",
        "overall_score": 71,
        "is_valid": True,
        "branch": "main",
        "created_at": "2026-08-13T12:00:00Z",
        "projects": {
            "display_name": "Repository-Audit",
            "owner": "acme",
            "repository_name": "Repository-Audit",
            "repository_url": "https://github.com/acme/Repository-Audit",
        },
        "result": {
            "total_files": 42,
            "total_lines": 1200,
            "score": 71,
            "wiki_summary": {
                "project_name": "Repository-Audit",
                "pages": [{"id": "overview", "title": "Overview", "content": "Restored content"}],
            },
        },
    }

    monkeypatch.setattr(
        "app.core.db.repositories.audits.resolve_audit_run",
        lambda *, identifier, user_id=None: audit_row if identifier in {"audit-1111", "project-2222"} else None,
    )
    monkeypatch.setattr(
        "app.core.supabase.client.supabase_available",
        lambda: True,
    )

    by_audit = asyncio.run(
        ensure_project_loaded("audit-1111", user_id="11111111-1111-1111-1111-111111111111")
    )
    assert by_audit is not None
    assert by_audit["wiki_summary"]["pages"][0]["content"] == "Restored content"
    assert by_audit["score"] == 71

    by_project = asyncio.run(
        ensure_project_loaded("project-2222", user_id="11111111-1111-1111-1111-111111111111")
    )
    assert by_project is not None
    assert by_project["info"].name in ("Repository-Audit", "acme/Repository-Audit")



def _live_proj(**kwargs):
    from repoaudit.interfaces.api.schemas import ProjectInfo
    from datetime import datetime, timezone

    info = ProjectInfo(
        id=kwargs.get("id", "scan1"),
        name=kwargs.get("name", "org/repo"),
        status=kwargs.get("status", "scanning"),
        branch=kwargs.get("branch", "main"),
    )
    return {
        "info": info,
        "_worker_live": kwargs.get("worker_live", True),
        "owner": kwargs.get("owner", "org"),
        "repository_name": kwargs.get("repository_name", "repo"),
        "branch": kwargs.get("branch", "main"),
        "created_at": kwargs.get("created_at", datetime.now(timezone.utc).isoformat()),
        "last_heartbeat": kwargs.get("last_heartbeat", datetime.now(timezone.utc).isoformat()),
        "progress": kwargs.get("progress", ["Analyzed module 1/10"]),
        "db_project_id": kwargs.get("db_project_id"),
    }


def test_live_scan_with_fresh_heartbeat_is_not_expired():
    from repoaudit.interfaces.api.routes.scan import _should_expire

    assert _should_expire(_live_proj()) is False


def test_restored_scan_without_worker_is_expired():
    from repoaudit.interfaces.api.routes.scan import _should_expire

    assert _should_expire(_live_proj(worker_live=False)) is True


def test_live_scan_with_old_heartbeat_is_expired():
    from datetime import datetime, timedelta, timezone
    from repoaudit.interfaces.api.routes.scan import _should_expire

    old = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    assert _should_expire(_live_proj(last_heartbeat=old, created_at=old)) is True


def test_find_active_scan_reuses_same_repo_branch():
    from repoaudit.interfaces.api.routes.scan import _find_active_scan_id

    projects = {"scan1": _live_proj()}
    found = _find_active_scan_id(
        projects,
        owner="org",
        repository_name="repo",
        branch="main",
        project_id=None,
    )
    assert found == "scan1"


def test_find_active_scan_ignores_finished_and_dead_workers():
    from repoaudit.interfaces.api.routes.scan import _find_active_scan_id

    done = _live_proj(id="done1", status="done")
    dead = _live_proj(id="dead1", worker_live=False)
    projects = {"done1": done, "dead1": dead}
    found = _find_active_scan_id(
        projects,
        owner="org",
        repository_name="repo",
        branch="main",
        project_id=None,
    )
    assert found is None


def test_progress_payload_includes_logs_and_status():
    from repoaudit.interfaces.api.routes.scan import _progress_payload

    proj = _live_proj(progress=["Ingesting project...", "Analyzed module 2/10"])
    payload = _progress_payload("scan1", proj)
    assert payload["status"] == "scanning"
    assert payload["progress"][-1] == "Analyzed module 2/10"
    assert payload["error"] == ""


def test_mark_interrupted_sets_error_status():
    from repoaudit.interfaces.api.routes.scan import STALE_SCAN_MESSAGE, _mark_interrupted, _scan_status

    proj = _live_proj()
    _mark_interrupted(proj)
    assert _scan_status(proj) == "error"
    assert proj["info"].error == STALE_SCAN_MESSAGE
    assert proj["_worker_live"] is False

