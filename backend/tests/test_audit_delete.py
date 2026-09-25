"""Tests for audit delete service."""

from __future__ import annotations

from uuid import uuid4

import pytest
from repoaudit.indexing.cache.cache import Cache
from repoaudit.interfaces.api.runtime import get_projects, purge_project_cache

from app.core.exceptions import NotFoundError, UnauthorizedError
from app.core.security.deps import CurrentUser
from app.modules.audit.delete import service as delete_service


def _user(uid=None) -> CurrentUser:
    return CurrentUser(user_id=uid or uuid4(), email="owner@e2m.solutions")


@pytest.mark.asyncio
async def test_delete_legacy_scan_from_sqlite(monkeypatch, tmp_path):
    get_projects().clear()
    user = _user()
    uid = str(user.user_id)

    cache = Cache(db_path=tmp_path / "cache.db")
    await cache.init()
    await cache.save_project(
        "scan-legacy",
        {"id": "scan-legacy", "name": "Legacy Repo", "status": "done", "score": 80, "user_id": uid},
    )

    async def _ensure_cache():
        return cache

    monkeypatch.setattr(
        "repoaudit.interfaces.api.runtime.ensure_cache",
        _ensure_cache,
    )
    monkeypatch.setattr(
        "app.core.db.repositories.audits.get_audit_run",
        lambda *, audit_id, user_id=None: None,
    )
    monkeypatch.setattr(
        "app.core.db.repositories.audits.delete_audit_run",
        lambda *, audit_id, user_id=None: False,
    )
    monkeypatch.setattr(
        "app.core.db.repositories.audits.get_latest_audit_for_project",
        lambda *, project_id, user_id=None: None,
    )
    monkeypatch.setattr(
        "app.core.db.repositories.audits.delete_audit_runs_for_project",
        lambda *, project_id, user_id=None: 0,
    )

    result = await delete_service.execute(identifier="scan-legacy", user=user)
    assert "Deleted audit scan-legacy" in result.message
    assert "scan-legacy" in result.deleted_ids
    assert await cache.load_project("scan-legacy") is None
    assert "scan-legacy" not in get_projects()

    await cache.close()
    purge_project_cache("scan-legacy")


@pytest.mark.asyncio
async def test_delete_requires_sign_in(monkeypatch, tmp_path):
    get_projects().clear()
    cache = Cache(db_path=tmp_path / "cache.db")
    await cache.init()
    await cache.save_project(
        "scan-legacy",
        {"id": "scan-legacy", "name": "Legacy Repo", "status": "done", "user_id": str(uuid4())},
    )

    async def _ensure_cache():
        return cache

    monkeypatch.setattr("repoaudit.interfaces.api.runtime.ensure_cache", _ensure_cache)
    with pytest.raises(UnauthorizedError):
        await delete_service.execute(identifier="scan-legacy", user=None)
    assert await cache.load_project("scan-legacy") is not None
    await cache.close()


@pytest.mark.asyncio
async def test_delete_does_not_wipe_another_users_cache(monkeypatch, tmp_path):
    get_projects().clear()
    owner = _user()
    attacker = _user()
    cache = Cache(db_path=tmp_path / "cache.db")
    await cache.init()
    await cache.save_project(
        "scan-a",
        {"id": "scan-a", "name": "Owner Repo", "status": "done", "user_id": str(owner.user_id)},
    )
    get_projects()["scan-a"] = {"info": None, "user_id": str(owner.user_id)}

    async def _ensure_cache():
        return cache

    monkeypatch.setattr("repoaudit.interfaces.api.runtime.ensure_cache", _ensure_cache)
    monkeypatch.setattr(
        "app.core.db.repositories.audits.get_audit_run",
        lambda *, audit_id, user_id=None: None,
    )
    monkeypatch.setattr(
        "app.core.db.repositories.audits.delete_audit_run",
        lambda *, audit_id, user_id=None: False,
    )
    monkeypatch.setattr(
        "app.core.db.repositories.audits.get_latest_audit_for_project",
        lambda *, project_id, user_id=None: None,
    )
    monkeypatch.setattr(
        "app.core.db.repositories.audits.delete_audit_runs_for_project",
        lambda *, project_id, user_id=None: 0,
    )

    with pytest.raises(NotFoundError):
        await delete_service.execute(identifier="scan-a", user=attacker)

    assert await cache.load_project("scan-a") is not None
    assert "scan-a" in get_projects()
    await cache.close()
    purge_project_cache("scan-a")


@pytest.mark.asyncio
async def test_delete_supabase_audit_clears_cache_when_last_for_project(monkeypatch, tmp_path):
    get_projects().clear()
    user = _user()
    uid = str(user.user_id)

    cache = Cache(db_path=tmp_path / "cache.db")
    await cache.init()
    await cache.save_project(
        "project-1",
        {"id": "project-1", "name": "Repo", "status": "done", "score": 90, "user_id": uid},
    )

    async def _ensure_cache():
        return cache

    audit_row = {"audit_id": "audit-1", "project_id": "project-1", "user_id": uid}

    monkeypatch.setattr(
        "repoaudit.interfaces.api.runtime.ensure_cache",
        _ensure_cache,
    )
    monkeypatch.setattr(
        "app.core.db.repositories.audits.get_audit_run",
        lambda *, audit_id, user_id=None: audit_row if audit_id == "audit-1" and user_id == uid else None,
    )
    monkeypatch.setattr(
        "app.core.db.repositories.audits.delete_audit_run",
        lambda *, audit_id, user_id=None: audit_id == "audit-1" and user_id == uid,
    )
    monkeypatch.setattr(
        "app.core.db.repositories.audits.get_latest_audit_for_project",
        lambda *, project_id, user_id=None: None,
    )
    monkeypatch.setattr(
        "app.core.db.repositories.audits.delete_audit_runs_for_project",
        lambda *, project_id, user_id=None: 1 if project_id == "project-1" and user_id == uid else 0,
    )

    get_projects()["project-1"] = {"info": None, "audit_id": "audit-1", "user_id": uid}

    result = await delete_service.execute(identifier="audit-1", user=user)
    assert "Deleted audit audit-1" in result.message
    assert "audit-1" in result.deleted_ids
    assert "project-1" in result.purged_project_ids
    assert await cache.load_project("project-1") is None
    assert "project-1" not in get_projects()
    assert "audit-1" not in get_projects()

    await cache.close()
    purge_project_cache("audit-1", "project-1")


@pytest.mark.asyncio
async def test_delete_by_project_id_resolves_latest_audit(monkeypatch, tmp_path):
    get_projects().clear()
    user = _user()
    uid = str(user.user_id)

    cache = Cache(db_path=tmp_path / "cache.db")
    await cache.init()
    await cache.save_project(
        "project-2",
        {"id": "project-2", "name": "Repo", "status": "done", "score": 90, "user_id": uid},
    )

    async def _ensure_cache():
        return cache

    audit_row = {"audit_id": "audit-2", "project_id": "project-2", "user_id": uid}

    monkeypatch.setattr(
        "repoaudit.interfaces.api.runtime.ensure_cache",
        _ensure_cache,
    )
    monkeypatch.setattr(
        "app.core.db.repositories.audits.get_audit_run",
        lambda *, audit_id, user_id=None: audit_row if audit_id == "audit-2" and user_id == uid else None,
    )
    monkeypatch.setattr(
        "app.core.db.repositories.audits.get_latest_audit_for_project",
        lambda *, project_id, user_id=None: audit_row if project_id == "project-2" and user_id == uid else None,
    )
    monkeypatch.setattr(
        "app.core.db.repositories.audits.delete_audit_run",
        lambda *, audit_id, user_id=None: audit_id == "audit-2" and user_id == uid,
    )
    monkeypatch.setattr(
        "app.core.db.repositories.audits.delete_audit_runs_for_project",
        lambda *, project_id, user_id=None: 1 if project_id == "project-2" and user_id == uid else 0,
    )

    result = await delete_service.execute(identifier="project-2", user=user)
    assert "Deleted audit project-2" in result.message
    assert await cache.load_project("project-2") is None

    await cache.close()
    purge_project_cache("audit-2", "project-2")


@pytest.mark.asyncio
async def test_delete_by_audit_id_clears_sqlite_stored_by_project_id(monkeypatch, tmp_path):
    get_projects().clear()
    user = _user()
    uid = str(user.user_id)

    cache = Cache(db_path=tmp_path / "cache.db")
    await cache.init()
    # Stored with primary key = project_id, but inner json has audit_id = audit-uuid-999
    await cache.save_project(
        "proj-abc",
        {
            "id": "proj-abc",
            "audit_id": "audit-uuid-999",
            "name": "Target Repo",
            "status": "done",
            "score": 95,
            "user_id": uid,
        },
    )

    async def _ensure_cache():
        return cache

    monkeypatch.setattr("repoaudit.interfaces.api.runtime.ensure_cache", _ensure_cache)
    monkeypatch.setattr(
        "app.core.db.repositories.audits.get_audit_run",
        lambda *, audit_id, user_id=None: None,
    )
    monkeypatch.setattr(
        "app.core.db.repositories.audits.delete_audit_run",
        lambda *, audit_id, user_id=None: False,
    )
    monkeypatch.setattr(
        "app.core.db.repositories.audits.get_latest_audit_for_project",
        lambda *, project_id, user_id=None: None,
    )
    monkeypatch.setattr(
        "app.core.db.repositories.audits.delete_audit_runs_for_project",
        lambda *, project_id, user_id=None: 0,
    )

    # Deleting by audit_id should find and delete proj-abc from SQLite
    result = await delete_service.execute(identifier="audit-uuid-999", user=user)
    assert "Deleted audit audit-uuid-999" in result.message
    assert await cache.load_project("proj-abc") is None
    assert len(await cache.list_projects()) == 0

    await cache.close()


@pytest.mark.asyncio
async def test_delete_cancels_in_flight_scan(monkeypatch, tmp_path):
    get_projects().clear()
    user = _user()
    uid = str(user.user_id)

    cache = Cache(db_path=tmp_path / "cache.db")
    await cache.init()

    async def _ensure_cache():
        return cache

    monkeypatch.setattr("repoaudit.interfaces.api.runtime.ensure_cache", _ensure_cache)
    monkeypatch.setattr(
        "app.core.db.repositories.audits.get_audit_run",
        lambda *, audit_id, user_id=None: None,
    )
    monkeypatch.setattr(
        "app.core.db.repositories.audits.delete_audit_run",
        lambda *, audit_id, user_id=None: False,
    )
    monkeypatch.setattr(
        "app.core.db.repositories.audits.get_latest_audit_for_project",
        lambda *, project_id, user_id=None: None,
    )
    monkeypatch.setattr(
        "app.core.db.repositories.audits.delete_audit_runs_for_project",
        lambda *, project_id, user_id=None: 0,
    )

    proj_dict = {
        "id": "scan-inflight",
        "audit_id": "audit-inflight",
        "user_id": uid,
        "_worker_live": True,
    }
    get_projects()["scan-inflight"] = proj_dict

    result = await delete_service.execute(identifier="audit-inflight", user=user)
    assert "Deleted audit audit-inflight" in result.message
    assert "scan-inflight" not in get_projects()
    assert proj_dict.get("_cancelled") is True
    assert proj_dict.get("_deleted") is True

    await cache.close()
    purge_project_cache("scan-inflight")

