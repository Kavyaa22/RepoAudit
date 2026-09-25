"""sqlite-based cache for analysis results."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import aiosqlite

_CACHE_DIR = Path.home() / ".repoaudit"
_CACHE_DB = _CACHE_DIR / "cache.db"
_DEFAULT_TTL = 365 * 24 * 3600  # 1 year

# Cache keys embed a content hash, so an entry is only wrong when the prompts
# or the model change, not when time passes. A year-long TTL therefore keeps
# re-runs of an unchanged repo free of LLM calls, and `repoaudit cache-clear`
# is the explicit way to invalidate after a prompt/model change.


def content_hash(content: str) -> str:
    """sha256 hash truncated to 24 chars, used as cache key."""
    return hashlib.sha256(content.encode()).hexdigest()[:24]


class Cache:
    """async SQLite cache for LLM analysis results."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = str(db_path or _CACHE_DB)
        self._db: aiosqlite.Connection | None = None

    async def init(self):
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.execute(
            "CREATE TABLE IF NOT EXISTS cache "
            "(key TEXT PRIMARY KEY, value TEXT, created_at REAL)"
        )
        await self._db.execute(
            "CREATE TABLE IF NOT EXISTS projects "
            "(id TEXT PRIMARY KEY, data TEXT, created_at REAL)"
        )
        await self._db.commit()

    async def get(self, key: str, ttl: int = _DEFAULT_TTL) -> dict | list | None:
        if not self._db:
            return None
        cursor = await self._db.execute(
            "SELECT value, created_at FROM cache WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        value, created_at = row
        if time.time() - created_at > ttl:
            await self._db.execute("DELETE FROM cache WHERE key = ?", (key,))
            await self._db.commit()
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    async def put(self, key: str, value: dict | list) -> None:
        if not self._db:
            return
        await self._db.execute(
            "INSERT OR REPLACE INTO cache (key, value, created_at) VALUES (?, ?, ?)",
            (key, json.dumps(value, ensure_ascii=False), time.time()),
        )
        await self._db.commit()

    async def save_project(self, project_id: str, data: dict) -> None:
        if not self._db:
            return
        await self._db.execute(
            "INSERT OR REPLACE INTO projects (id, data, created_at) VALUES (?, ?, ?)",
            (project_id, json.dumps(data, ensure_ascii=False), time.time()),
        )
        await self._db.commit()

    async def load_project(self, project_id: str) -> dict | None:
        if not self._db:
            return None
        cursor = await self._db.execute(
            "SELECT data FROM projects WHERE id = ?", (project_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            return None

    async def delete_project(self, project_id: str, *, user_id: str | None = None) -> bool:
        if not self._db:
            return False
        if user_id:
            cursor = await self._db.execute("SELECT data FROM projects WHERE id = ?", (project_id,))
            row = await cursor.fetchone()
            if row:
                try:
                    pdata = json.loads(row[0])
                    if isinstance(pdata, dict) and str(pdata.get("user_id") or "") != str(user_id):
                        return False
                except json.JSONDecodeError:
                    pass
        cursor = await self._db.execute(
            "DELETE FROM projects WHERE id = ?", (project_id,)
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def delete_matching_projects(
        self,
        identifiers: set[str] | list[str],
        *,
        user_id: str | None = None,
    ) -> int:
        """Delete projects matching any identifier by primary key or inner JSON aliases."""
        if not self._db:
            return 0
        norm_ids = {str(i).strip() for i in identifiers if str(i).strip()}
        if not norm_ids:
            return 0

        cursor = await self._db.execute("SELECT id, data FROM projects")
        rows = await cursor.fetchall()
        deleted_count = 0
        ids_to_delete: list[str] = []

        for row_id, raw_data in rows:
            p_id = str(row_id or "")
            match = p_id in norm_ids
            pdata: dict | None = None
            try:
                pdata = json.loads(raw_data) if raw_data else None
            except json.JSONDecodeError:
                pdata = None

            if isinstance(pdata, dict):
                p_user = str(pdata.get("user_id") or "")
                if user_id and p_user and p_user != str(user_id):
                    # Tenant isolation: do not touch projects belonging to another user
                    continue

                aliases = {
                    p_id,
                    str(pdata.get("id") or ""),
                    str(pdata.get("audit_id") or ""),
                    str(pdata.get("db_project_id") or ""),
                }
                if aliases & norm_ids:
                    match = True

            if match:
                ids_to_delete.append(p_id)

        for target_id in ids_to_delete:
            del_cursor = await self._db.execute("DELETE FROM projects WHERE id = ?", (target_id,))
            deleted_count += del_cursor.rowcount

        if deleted_count > 0:
            await self._db.commit()

        return deleted_count

    async def list_projects(self) -> list[dict]:
        if not self._db:
            return []
        cursor = await self._db.execute(
            "SELECT data FROM projects ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            try:
                data = json.loads(row[0])
                if isinstance(data, dict):
                    results.append(data)
            except json.JSONDecodeError:
                continue
        return results

    async def clear(self) -> int:
        """Wipe cached LLM results (not saved projects). Returns rows removed."""
        if not self._db:
            return 0
        cursor = await self._db.execute("SELECT COUNT(*) FROM cache")
        (count,) = await cursor.fetchone()
        await self._db.execute("DELETE FROM cache")
        await self._db.commit()
        return count

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None
