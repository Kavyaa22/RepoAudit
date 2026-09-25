"""Per-app-user GitHub and project isolation."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.modules.github.shared.store import GitHubConnectionStore

client = TestClient(app)


def _register(suffix: str | None = None) -> tuple[str, str, str]:
    email = f"iso-{suffix or uuid.uuid4().hex[:8]}@e2m.solutions"
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "password123",
            "full_name": "Isolation User",
        },
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    return data["access_token"], data["user_id"], email


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_new_account_github_is_disconnected():
    token, _uid, _email = _register()
    res = client.get("/api/v1/github/status", headers=_auth(token))
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["connected"] is False
    repos = client.get("/api/v1/github/repos", headers=_auth(token))
    assert repos.status_code == 401


def test_github_connection_does_not_follow_email_or_new_user(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.modules.github.shared.store._store_path",
        lambda: tmp_path / "github_connections.json",
    )
    monkeypatch.setattr(
        "app.modules.github.shared.store._oauth_state_path",
        lambda: tmp_path / "oauth_states.json",
    )
    monkeypatch.setattr("app.modules.github.shared.store.supabase_available", lambda: False)

    store = GitHubConnectionStore()
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    shared_email = "shared@e2m.solutions"

    store.upsert_connection(
        user_id=user_a,
        access_token="token-user-a",
        github_login="alice",
        github_user_id=111,
        scopes="repo",
        email=shared_email,
    )

    assert store.status_for(user_a)["connected"] is True
    assert store.get_access_token(user_a) == "token-user-a"
    assert store.status_for(user_b) is None
    assert store.status_for(user_b, email=shared_email) is None
    assert store.get_access_token(user_b, email=shared_email) is None
    assert store.status_for("anonymous") is None
    assert store.get_access_token("email:" + shared_email) is None


def test_projects_are_isolated_between_accounts():
    token_a, _uid_a, _email_a = _register()
    token_b, _uid_b, _email_b = _register()
    suffix = uuid.uuid4().hex[:8]

    created = client.post(
        "/api/v1/projects",
        headers=_auth(token_a),
        json={
            "display_name": f"OnlyA-{suffix}",
            "repository_url": f"https://github.com/acme/only-a-{suffix}",
            "owner": "acme",
            "repository_name": f"only-a-{suffix}",
        },
    )
    assert created.status_code == 200, created.text
    project_id = created.json()["data"]["project_id"]

    listed_a = client.get("/api/v1/projects", headers=_auth(token_a))
    assert listed_a.status_code == 200
    ids_a = {p["project_id"] for p in listed_a.json()["data"]["items"]}
    assert project_id in ids_a

    listed_b = client.get("/api/v1/projects", headers=_auth(token_b))
    assert listed_b.status_code == 200
    ids_b = {p["project_id"] for p in listed_b.json()["data"]["items"]}
    assert project_id not in ids_b

    viewed_b = client.get(f"/api/v1/projects/{project_id}", headers=_auth(token_b))
    assert viewed_b.status_code == 404


def test_investigations_are_isolated_between_accounts(tmp_path):
    from app.core.security.deps import CurrentUser
    from app.modules.investigation.service import get_investigation_result, list_user_investigations
    from repoaudit.investigation.investigation_models import EvidenceAssessment, InvestigationResult, IssueReport
    from repoaudit.investigation.session import save_local_session, load_local_session

    token_a, uid_a, _ = _register()
    token_b, uid_b, _ = _register()
    user_a = CurrentUser(user_id=uuid.UUID(uid_a), email="a@e2m.solutions")
    user_b = CurrentUser(user_id=uuid.UUID(uid_b), email="b@e2m.solutions")

    report = IssueReport(project_name="OnlyA", issue_description="login broken")
    result = InvestigationResult(
        investigation_id="INV-OWNEDA",
        project_name="OnlyA",
        status="PARTIAL",
        summary_verdict="partial",
        evidence=EvidenceAssessment(),
    )
    save_local_session(
        tmp_path,
        investigation_id="INV-OWNEDA",
        report=report,
        result=result,
        workspace_path=str(tmp_path),
        user_id=uid_a,
    )
    assert load_local_session(tmp_path, "INV-OWNEDA", user_id=uid_a) is not None
    assert load_local_session(tmp_path, "INV-OWNEDA", user_id=uid_b) is None

    listed_b = client.get("/api/v1/investigation/list", headers=_auth(token_b))
    assert listed_b.status_code == 200
    ids_b = {item["investigation_id"] for item in listed_b.json().get("results") or []}
    assert "INV-OWNEDA" not in ids_b

    fetched_b = client.get("/api/v1/investigation/INV-OWNEDA", headers=_auth(token_b))
    assert fetched_b.status_code == 200
    body = fetched_b.json()
    assert body.get("success") is False
    assert body.get("result") is None

    continued = client.post(
        "/api/v1/investigation/INV-OWNEDA/continue",
        headers=_auth(token_b),
        json={"issue_description": "more evidence from B"},
    )
    assert continued.status_code == 200
    assert continued.json().get("success") is False

    fetched_unauth = client.get("/api/v1/investigation/INV-OWNEDA")
    assert fetched_unauth.status_code == 401

    assert get_investigation_result("INV-OWNEDA", user=user_b).success is False
    assert get_investigation_result("INV-OWNEDA", user=user_a).success is False
    disk_ids = {item["investigation_id"] for item in list_user_investigations(user_b)}
    assert "INV-OWNEDA" not in disk_ids


def test_scan_rejects_foreign_local_path():
    token, _uid, _ = _register()
    res = client.post(
        "/api/scan",
        headers=_auth(token),
        json={"path": "C:\\Windows", "url": ""},
    )
    assert res.status_code == 400


def test_scan_progress_and_status_require_owner():
    token_a, _uid_a, _ = _register()
    token_b, _uid_b, _ = _register()
    foreign = str(uuid.uuid4())

    progress = client.get(f"/api/project/{foreign}/progress", headers=_auth(token_b))
    assert progress.status_code == 200
    assert progress.json().get("error") == "Project not found"

    unauth_status = client.get(f"/api/project/{foreign}/status")
    assert unauth_status.status_code == 401

    owned_status = client.get(f"/api/project/{foreign}/status", headers=_auth(token_a))
    assert owned_status.status_code == 200


def test_chat_requires_auth_and_ownership():
    token_b, _uid_b, _ = _register()
    foreign = str(uuid.uuid4())
    unauth = client.post(f"/api/project/{foreign}/chat", json={"question": "hello"})
    assert unauth.status_code == 401

    other = client.post(
        f"/api/project/{foreign}/chat",
        headers=_auth(token_b),
        json={"question": "hello"},
    )
    assert other.status_code == 200
    assert "Project not found" in other.text or "Sign in required" in other.text or "error" in other.text.lower()


def test_workspace_paths_are_user_scoped(tmp_path):
    from app.core.workspace import (
        ingest_workspace_dir,
        path_belongs_to_user,
        project_workspace_dir,
        user_workspace_dir,
    )
    from repoaudit.investigation.project_resolver import resolve_project_directory

    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    project_id = str(uuid.uuid4())

    a_root = user_workspace_dir(user_a, backend_root=tmp_path)
    b_secret = project_workspace_dir(user_b, project_id, backend_root=tmp_path) / "snapshots" / "abc"
    b_secret.mkdir(parents=True)
    (b_secret / "file.py").write_text("print(1)\n", encoding="utf-8")

    a_snap = project_workspace_dir(user_a, project_id, backend_root=tmp_path) / "snapshots" / "def"
    a_snap.mkdir(parents=True)

    assert path_belongs_to_user(a_snap, user_a, backend_root=tmp_path) is True
    assert path_belongs_to_user(b_secret, user_a, backend_root=tmp_path) is False
    assert path_belongs_to_user(b_secret, user_b, backend_root=tmp_path) is True
    assert str(user_a) in str(ingest_workspace_dir(user_a, "acme", "repo", backend_root=tmp_path))
    assert a_root == tmp_path / "workspace" / user_a

    leaked = resolve_project_directory(
        project_name="secret",
        repo_path=str(b_secret),
        backend_root=tmp_path,
        user_id=user_a,
    )
    assert leaked is None

    owned = resolve_project_directory(
        project_name="mine",
        repo_path=str(a_snap),
        backend_root=tmp_path,
        user_id=user_a,
    )
    assert owned is not None
    assert owned == a_snap.resolve()

    wandered = resolve_project_directory(
        project_name="anything",
        backend_root=tmp_path,
        user_id=user_a,
    )
    assert wandered is None or path_belongs_to_user(wandered, user_a, backend_root=tmp_path)

