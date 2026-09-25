"""Smoke tests for the new app architecture."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_auth_register_login_me():
    import uuid

    email = f"architect-{uuid.uuid4().hex[:8]}@e2m.solutions"
    password = "password123"
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Architect"},
    )
    assert reg.status_code == 200
    token = reg.json()["data"]["access_token"]

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200

    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200
    assert me.json()["data"]["email"] == email


def test_projects_crud():
    import uuid

    email = f"architect-{uuid.uuid4().hex[:8]}@e2m.solutions"
    password = "password123"
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Architect"},
    )
    assert reg.status_code == 200
    token = reg.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    suffix = uuid.uuid4().hex[:8]
    create = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "display_name": f"Widgets-{suffix}",
            "repository_url": f"https://github.com/acme/widgets-{suffix}",
            "owner": "acme",
            "repository_name": f"widgets-{suffix}",
        },
    )
    assert create.status_code == 200
    project_id = create.json()["data"]["project_id"]

    listed = client.get("/api/v1/projects", headers=headers)
    assert listed.status_code == 200
    assert any(p["project_id"] == project_id for p in listed.json()["data"]["items"])

    viewed = client.get(f"/api/v1/projects/{project_id}", headers=headers)
    assert viewed.status_code == 200
    assert viewed.json()["data"]["display_name"] == f"Widgets-{suffix}"


def test_any_email_domain_registration_and_login():
    import uuid

    email = f"user-{uuid.uuid4().hex[:8]}@gmail.com"
    password = "password123"
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Gmail User"},
    )
    assert reg.status_code == 200
    token = reg.json()["data"]["access_token"]
    assert reg.json()["data"]["email"] == email

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200
    assert login.json()["data"]["email"] == email


