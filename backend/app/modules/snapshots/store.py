"""Snapshot store with Supabase repo_snapshots persistence and in-memory cache."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.core.supabase.client import get_supabase_client, supabase_available

logger = logging.getLogger(__name__)

_TABLE = "repo_snapshots"


class SnapshotStore:
    def __init__(self) -> None:
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._load_from_db()

    def _load_from_db(self) -> None:
        if not supabase_available():
            return
        try:
            client = get_supabase_client()
            res = client.table(_TABLE).select("*").execute()
            if res.data and isinstance(res.data, list):
                for item in res.data:
                    if isinstance(item, dict) and item.get("snapshot_id"):
                        self._snapshots[str(item["snapshot_id"])] = item
                logger.info("Loaded %s repo snapshot(s) from Supabase DB", len(self._snapshots))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Supabase repo_snapshots load fallback: %s", exc)

    def _db_record(self, record: dict[str, Any]) -> dict[str, Any]:
        summary = record.get("summary") or {}
        file_count = int(record.get("file_count") or summary.get("file_count") or 0)
        line_count = int(record.get("line_count") or summary.get("line_count") or 0)
        return {
            "snapshot_id": record["snapshot_id"],
            "project_id": record["project_id"],
            "user_id": record.get("user_id"),
            "branch": record["branch"],
            "commit_sha": record["commit_sha"],
            "workspace_path": record["workspace_path"],
            "status": record.get("status") or "ready",
            "file_count": file_count,
            "line_count": line_count,
            "summary": summary if isinstance(summary, dict) else {},
            "created_at": record.get("created_at"),
        }

    def _persist(self, record: dict[str, Any]) -> None:
        if not supabase_available():
            return
        try:
            client = get_supabase_client()
            client.table(_TABLE).upsert(self._db_record(record)).execute()
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to persist repo_snapshot %s: %s", record.get("snapshot_id"), exc)

    def create(
        self,
        *,
        project_id: str,
        commit_sha: str,
        branch: str = "main",
        workspace_path: str,
        status: str = "pending",
        summary: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        existing = self.find_by_branch_commit(project_id, branch, commit_sha)
        if existing:
            return existing

        snapshot_id = str(uuid4())
        now = datetime.now(UTC).isoformat()
        summary_data = summary or {}
        record = {
            "snapshot_id": snapshot_id,
            "project_id": project_id,
            "user_id": user_id,
            "commit_sha": commit_sha,
            "branch": branch,
            "workspace_path": workspace_path,
            "status": status,
            "file_count": int(summary_data.get("file_count") or 0),
            "line_count": int(summary_data.get("line_count") or 0),
            "summary": summary_data,
            "created_at": now,
        }
        self._snapshots[snapshot_id] = record
        self._persist(record)
        return record

    def update(self, snapshot_id: str, **fields: Any) -> dict[str, Any] | None:
        item = self._snapshots.get(snapshot_id)
        if not item:
            item = self.get(snapshot_id)
        if not item:
            return None
        item.update(fields)
        self._snapshots[snapshot_id] = item
        self._persist(item)
        return item

    def get(self, snapshot_id: str) -> dict[str, Any] | None:
        if supabase_available():
            try:
                client = get_supabase_client()
                res = client.table(_TABLE).select("*").eq("snapshot_id", snapshot_id).execute()
                if res.data and isinstance(res.data, list) and res.data:
                    record = res.data[0]
                    self._snapshots[snapshot_id] = record
                    return record
            except Exception as exc:  # noqa: BLE001
                logger.warning("Supabase repo_snapshot get failed: %s", exc)
        return self._snapshots.get(snapshot_id)

    def find_by_commit(self, project_id: str, commit_sha: str) -> dict[str, Any] | None:
        if supabase_available():
            try:
                client = get_supabase_client()
                res = (
                    client.table(_TABLE)
                    .select("*")
                    .eq("project_id", project_id)
                    .eq("commit_sha", commit_sha)
                    .limit(1)
                    .execute()
                )
                if res.data and isinstance(res.data, list) and res.data:
                    record = res.data[0]
                    self._snapshots[str(record["snapshot_id"])] = record
                    return record
            except Exception as exc:  # noqa: BLE001
                logger.warning("Supabase repo_snapshot find failed: %s", exc)

        for record in self._snapshots.values():
            if record.get("project_id") == project_id and record.get("commit_sha") == commit_sha:
                return record
        return None

    def find_by_branch_commit(
        self, project_id: str, branch: str, commit_sha: str
    ) -> dict[str, Any] | None:
        if supabase_available():
            try:
                client = get_supabase_client()
                res = (
                    client.table(_TABLE)
                    .select("*")
                    .eq("project_id", project_id)
                    .eq("branch", branch)
                    .eq("commit_sha", commit_sha)
                    .limit(1)
                    .execute()
                )
                if res.data and isinstance(res.data, list) and res.data:
                    record = res.data[0]
                    self._snapshots[str(record["snapshot_id"])] = record
                    return record
            except Exception as exc:  # noqa: BLE001
                logger.warning("Supabase repo_snapshot branch find failed: %s", exc)

        for record in self._snapshots.values():
            if (
                record.get("project_id") == project_id
                and record.get("branch") == branch
                and record.get("commit_sha") == commit_sha
            ):
                return record
        return None

    def list_for_project(self, project_id: str) -> list[dict[str, Any]]:
        if supabase_available():
            try:
                client = get_supabase_client()
                res = client.table(_TABLE).select("*").eq("project_id", project_id).execute()
                if res.data and isinstance(res.data, list):
                    for item in res.data:
                        if isinstance(item, dict) and item.get("snapshot_id"):
                            self._snapshots[str(item["snapshot_id"])] = item
                    return res.data
            except Exception as exc:  # noqa: BLE001
                logger.warning("Supabase repo_snapshot list failed: %s", exc)

        return [s for s in self._snapshots.values() if s.get("project_id") == project_id]


snapshot_store = SnapshotStore()
