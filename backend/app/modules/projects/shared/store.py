"""Project store with Supabase DB persistence and in-memory cache."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.core.supabase.client import get_supabase_client, supabase_available

logger = logging.getLogger(__name__)


class ProjectStore:
    def __init__(self) -> None:
        self._projects: dict[str, dict[str, Any]] = {}
        self._load_from_db()

    def _load_from_db(self) -> None:
        if not supabase_available():
            return
        try:
            client = get_supabase_client()
            res = client.table("projects").select("*").execute()
            if res.data and isinstance(res.data, list):
                for item in res.data:
                    if isinstance(item, dict) and item.get("project_id"):
                        self._projects[str(item["project_id"])] = item
                logger.info("Loaded %s project(s) from Supabase DB", len(self._projects))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Supabase DB project query fallback (will use memory store): %s", exc)

    def _db_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        latest_sha = record.get("latest_commit_sha") or record.get("current_commit_sha")
        payload = {
            "project_id": record["project_id"],
            "user_id": record.get("user_id"),
            "project_name": record["project_name"],
            "display_name": record["display_name"],
            "repository_url": record["repository_url"],
            "owner": record["owner"],
            "repository_name": record["repository_name"],
            "default_branch": record["default_branch"],
            "workspace_path": record["workspace_path"],
            "status": record.get("status") or "importing",
            "source": record.get("source") or "github",
            "private": bool(record.get("private", False)),
            "summary": record.get("summary") or {},
            "latest_snapshot_id": record.get("latest_snapshot_id"),
            "latest_commit_sha": latest_sha,
            "current_commit_sha": latest_sha,
            "audit_project_id": record.get("audit_project_id"),
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
        }
        return payload

    def _persist(self, record: dict[str, Any]) -> None:
        if not supabase_available():
            return
        try:
            client = get_supabase_client()
            client.table("projects").upsert(self._db_payload(record)).execute()
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to persist project %s to Supabase DB: %s", record.get("project_id"), exc)

    def find_existing(
        self,
        *,
        user_id: str | None,
        display_name: str | None = None,
        owner: str | None = None,
        repository_name: str | None = None,
        repository_url: str | None = None,
    ) -> dict[str, Any] | None:
        """Find an existing project matching owner/repo, repository_url, or project_name."""
        target_slug = (display_name or repository_name or "").lower().replace(" ", "-")
        norm_url = (repository_url or "").strip().rstrip("/").lower()

        # 1. Search local memory cache
        for p in self._projects.values():
            p_user = str(p.get("user_id") or "")
            if str(user_id or "") != p_user:
                continue
            if norm_url and str(p.get("repository_url") or "").strip().rstrip("/").lower() == norm_url:
                return p
            if owner and repository_name:
                if str(p.get("owner") or "").lower() == owner.lower() and str(p.get("repository_name") or "").lower() == repository_name.lower():
                    return p
            if target_slug and str(p.get("project_name") or "").lower() == target_slug:
                return p

        # 2. Query Supabase if not in memory (this user only)
        if supabase_available() and user_id:
            try:
                client = get_supabase_client()
                if norm_url:
                    q = client.table("projects").select("*").ilike("repository_url", norm_url)
                    q = q.eq("user_id", user_id)
                    res = q.execute()
                    if res.data and isinstance(res.data, list) and len(res.data) > 0:
                        rec = res.data[0]
                        self._projects[str(rec["project_id"])] = rec
                        return rec
                if owner and repository_name:
                    q = client.table("projects").select("*").ilike("owner", owner).ilike("repository_name", repository_name)
                    q = q.eq("user_id", user_id)
                    res = q.execute()
                    if res.data and isinstance(res.data, list) and len(res.data) > 0:
                        rec = res.data[0]
                        self._projects[str(rec["project_id"])] = rec
                        return rec
                if target_slug:
                    q = client.table("projects").select("*").eq("project_name", target_slug)
                    q = q.eq("user_id", user_id)
                    res = q.execute()
                    if res.data and isinstance(res.data, list) and len(res.data) > 0:
                        rec = res.data[0]
                        self._projects[str(rec["project_id"])] = rec
                        return rec
            except Exception as exc:  # noqa: BLE001
                logger.debug("find_existing query failed: %s", exc)

        return None

    def create(
        self,
        *,
        display_name: str,
        repository_url: str,
        owner: str,
        repository_name: str,
        default_branch: str = "main",
        user_id: str | None = None,
        status: str = "ready",
        private: bool = False,
        workspace_path: str | None = None,
    ) -> dict[str, Any]:
        # Check if project already exists for this user / repo to reuse and prevent unique constraint collisions
        existing = self.find_existing(
            user_id=user_id,
            display_name=display_name,
            owner=owner,
            repository_name=repository_name,
            repository_url=repository_url,
        )
        if existing:
            project_id = str(existing["project_id"])
            fields_to_update = {
                "display_name": display_name,
                "repository_url": repository_url,
                "owner": owner,
                "repository_name": repository_name,
                "default_branch": default_branch,
                "status": status,
                "private": private,
            }
            if workspace_path:
                fields_to_update["workspace_path"] = workspace_path
            updated = self.update(project_id, **fields_to_update)
            return updated or existing

        project_id = str(uuid4())
        now = datetime.now(UTC).isoformat()
        record = {
            "project_id": project_id,
            "project_name": display_name.lower().replace(" ", "-"),
            "display_name": display_name,
            "repository_url": repository_url,
            "owner": owner,
            "repository_name": repository_name,
            "default_branch": default_branch,
            "workspace_path": workspace_path
            or (f"workspace/{user_id}/{project_id}" if user_id else f"workspace/{project_id}"),
            "latest_snapshot_id": None,
            "latest_commit_sha": None,
            "status": status,
            "private": private,
            "user_id": user_id,
            "summary": {},
            "audit_project_id": None,
            "source": "github",
            "created_at": now,
            "updated_at": now,
        }
        self._projects[project_id] = record
        self._persist(record)
        return record

    def list(self, *, user_id: str | None = None) -> list[dict[str, Any]]:
        if not user_id:
            return []
        if supabase_available():
            try:
                client = get_supabase_client()
                query = client.table("projects").select("*").eq("user_id", user_id)
                res = query.execute()
                if res.data and isinstance(res.data, list):
                    for item in res.data:
                        if isinstance(item, dict) and item.get("project_id"):
                            self._projects[str(item["project_id"])] = item
                    return res.data
            except Exception as exc:  # noqa: BLE001
                logger.warning("Supabase list query failed, returning in-memory items: %s", exc)

        items = list(self._projects.values())
        return [p for p in items if str(p.get("user_id") or "") == str(user_id)]

    def get(self, project_id: str) -> dict[str, Any] | None:
        if supabase_available():
            try:
                client = get_supabase_client()
                res = client.table("projects").select("*").eq("project_id", project_id).execute()
                if res.data and isinstance(res.data, list) and len(res.data) > 0:
                    record = res.data[0]
                    self._projects[project_id] = record
                    return record
            except Exception as exc:  # noqa: BLE001
                logger.warning("Supabase get query failed: %s", exc)

        return self._projects.get(project_id)

    def get_for_user(self, project_id: str, user_id: str | None) -> dict[str, Any] | None:
        record = self.get(project_id)
        if not record or not user_id:
            return None
        if str(record.get("user_id") or "") != str(user_id):
            return None
        return record

    def update(self, project_id: str, **fields: Any) -> dict[str, Any] | None:
        project = self._projects.get(project_id)
        if not project:
            project = self.get(project_id)
            if not project:
                return None

        for key, value in fields.items():
            if value is not None:
                project[key] = value
        project["updated_at"] = datetime.now(UTC).isoformat()
        self._projects[project_id] = project
        self._persist(project)
        return project

    def delete(self, project_id: str) -> bool:
        removed = self._projects.pop(project_id, None) is not None
        if supabase_available():
            try:
                client = get_supabase_client()
                client.table("projects").delete().eq("project_id", project_id).execute()
                removed = True
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to delete project %s from Supabase DB: %s", project_id, exc)

        return removed


project_store = ProjectStore()
