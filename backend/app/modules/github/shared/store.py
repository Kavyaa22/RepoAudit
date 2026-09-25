"""GitHub OAuth connection store.

Persists to local JSON (survives reloads / multi-worker) and to Supabase
when configured so a user stays connected across login and page refresh.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.supabase.client import get_supabase_client, supabase_available
from app.modules.github.shared.crypto import decrypt_token, encrypt_token

logger = logging.getLogger(__name__)

_CONNECTIONS_TABLE = "github_connections"
_OAUTH_STATES_TABLE = "oauth_states"


def _store_path() -> Path:
    settings = get_settings()
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "github_connections.json"


def _oauth_state_path() -> Path:
    settings = get_settings()
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "github_oauth_states.json"


def _is_uuid(value: str | None) -> bool:
    if not value:
        return False
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


def _scopes_to_list(scopes: str | list[str] | None) -> list[str]:
    if isinstance(scopes, list):
        return [str(s).strip() for s in scopes if str(s).strip()]
    if isinstance(scopes, str) and scopes.strip():
        return [part.strip() for part in scopes.split(",") if part.strip()]
    return []


class GitHubConnectionStore:
    def __init__(self) -> None:
        self._connections: dict[str, dict[str, Any]] = {}
        self._oauth_states: dict[str, dict[str, Any]] = {}
        self._load()
        self._load_oauth_states()

    def _load(self) -> None:
        path = _store_path()
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._connections = {
                    str(k): v for k, v in raw.items() if isinstance(v, dict)
                }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load GitHub connections: %s", exc)

    def _save(self) -> None:
        path = _store_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(self._connections, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to persist GitHub connections: %s", exc)

    def _load_oauth_states(self) -> None:
        path = _oauth_state_path()
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._oauth_states = {
                    str(k): v for k, v in raw.items() if isinstance(v, dict)
                }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load GitHub OAuth states: %s", exc)

    def _save_oauth_states(self) -> None:
        path = _oauth_state_path()
        try:
            serializable = {}
            for key, record in self._oauth_states.items():
                item = dict(record)
                expires = item.get("expires_at")
                if isinstance(expires, datetime):
                    item["expires_at"] = expires.isoformat()
                serializable[key] = item
            path.write_text(
                json.dumps(serializable, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to persist GitHub OAuth states: %s", exc)

    def _record_from_db_row(self, row: dict[str, Any]) -> dict[str, Any]:
        scopes = row.get("scopes")
        if isinstance(scopes, list):
            scopes_str = ",".join(str(s) for s in scopes)
        else:
            scopes_str = str(scopes or "")
        return {
            "user_id": str(row.get("user_id") or ""),
            "app_email": row.get("app_email"),
            "access_token_enc": row.get("access_token_encrypted") or row.get("access_token_enc"),
            "github_login": row.get("github_login"),
            "github_user_id": row.get("github_user_id"),
            "scopes": scopes_str,
            "avatar_url": row.get("avatar_url"),
            "connected_at": str(row.get("connected_at") or ""),
            "last_validated_at": str(row.get("last_validated_at") or ""),
        }

    def _usable_user_id(self, user_id: str | None) -> str | None:
        if not user_id:
            return None
        value = str(user_id).strip()
        if not value or value == "anonymous" or value.lower().startswith("email:"):
            return None
        return value

    def _db_find(self, user_id: str) -> dict[str, Any] | None:
        if not supabase_available() or not _is_uuid(user_id):
            return None
        try:
            client = get_supabase_client()
            res = (
                client.table(_CONNECTIONS_TABLE)
                .select("*")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            if res.data:
                return self._record_from_db_row(res.data[0])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Supabase GitHub connection lookup failed: %s", exc)
        return None

    def _db_upsert(self, record: dict[str, Any]) -> None:
        if not supabase_available():
            return
        user_id = str(record.get("user_id") or "")
        if not _is_uuid(user_id):
            return
        try:
            client = get_supabase_client()
            payload: dict[str, Any] = {
                "user_id": user_id,
                "github_user_id": int(record.get("github_user_id") or 0),
                "github_login": record.get("github_login") or "",
                "access_token_encrypted": record.get("access_token_enc") or "",
                "scopes": _scopes_to_list(record.get("scopes")),
                "token_type": "bearer",
                "connected_at": record.get("connected_at") or _now_iso(),
                "last_validated_at": record.get("last_validated_at") or _now_iso(),
            }
            client.table(_CONNECTIONS_TABLE).upsert(payload, on_conflict="user_id").execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to persist GitHub connection to Supabase: %s", exc)
            text = str(exc).lower()
            if "github_user_id" in text and (
                "unique" in text or "duplicate" in text or "23505" in text
            ):
                raise AppError(
                    "Could not save GitHub connection because the database still unique-indexes "
                    "github_user_id. Apply migrations/005_github_connection_per_user.sql in "
                    "Supabase, then reconnect this account.",
                    code="github_persist_failed",
                ) from exc
            raise AppError(
                "Could not save GitHub connection for this account",
                code="github_persist_failed",
            ) from exc

    def _db_delete(self, user_id: str) -> None:
        if not supabase_available() or not _is_uuid(user_id):
            return
        try:
            client = get_supabase_client()
            client.table(_CONNECTIONS_TABLE).delete().eq("user_id", user_id).execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to delete GitHub connection from Supabase: %s", exc)

    def _find(self, user_id: str) -> dict[str, Any] | None:
        uid = self._usable_user_id(user_id)
        if not uid:
            return None
        self._load()
        record = self._connections.get(uid)
        if isinstance(record, dict):
            return record

        db_record = self._db_find(uid)
        if not db_record:
            return None
        db_record["user_id"] = uid
        self._connections[uid] = db_record
        self._save()
        return db_record

    def create_oauth_state(
        self,
        *,
        user_id: str,
        email: str | None = None,
        ttl_minutes: int = 15,
    ) -> str:
        self._load_oauth_states()
        state = uuid.uuid4().hex
        expires_at = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
        self._oauth_states[state] = {
            "user_id": user_id,
            "email": (email or "").strip().lower() or None,
            "expires_at": expires_at,
        }
        self._save_oauth_states()
        if supabase_available() and _is_uuid(user_id):
            try:
                client = get_supabase_client()
                client.table(_OAUTH_STATES_TABLE).upsert(
                    {
                        "state": state,
                        "user_id": user_id,
                        "provider": "github",
                        "expires_at": expires_at.isoformat(),
                    }
                ).execute()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to persist OAuth state to Supabase: %s", exc)
        return state

    def pop_oauth_state(self, state: str) -> dict[str, Any] | None:
        self._load_oauth_states()
        record = self._oauth_states.pop(state, None)
        if record:
            self._save_oauth_states()
            expires = _parse_dt(record.get("expires_at"))
            if expires and expires < datetime.now(UTC):
                return None
            return record

        if not supabase_available():
            return None
        try:
            client = get_supabase_client()
            res = (
                client.table(_OAUTH_STATES_TABLE)
                .select("*")
                .eq("state", state)
                .limit(1)
                .execute()
            )
            if not res.data:
                return None
            row = res.data[0]
            client.table(_OAUTH_STATES_TABLE).delete().eq("state", state).execute()
            expires = _parse_dt(row.get("expires_at"))
            if expires and expires < datetime.now(UTC):
                return None
            return {
                "user_id": str(row.get("user_id") or ""),
                "email": None,
                "expires_at": row.get("expires_at"),
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Supabase OAuth state lookup failed: %s", exc)
            return None

    def upsert_connection(
        self,
        *,
        user_id: str,
        access_token: str,
        github_login: str,
        github_user_id: int,
        scopes: str,
        avatar_url: str | None = None,
        email: str | None = None,
    ) -> dict[str, Any]:
        uid = self._usable_user_id(user_id)
        if not uid:
            raise AppError("Sign in required to connect GitHub", code="unauthorized")
        now = _now_iso()
        app_email = (email or "").strip().lower() or None
        record = {
            "user_id": uid,
            "app_email": app_email,
            "access_token_enc": encrypt_token(access_token),
            "github_login": github_login,
            "github_user_id": github_user_id,
            "scopes": scopes,
            "avatar_url": avatar_url,
            "connected_at": now,
            "last_validated_at": now,
        }

        self._load()
        previous = self._connections.get(uid)
        self._connections[uid] = record
        try:
            self._db_upsert(record)
        except AppError:
            if previous is None:
                self._connections.pop(uid, None)
            else:
                self._connections[uid] = previous
            self._save()
            raise
        self._save()
        return self.status_for(uid)

    def get_access_token(self, user_id: str, email: str | None = None) -> str | None:
        del email  # legacy kwarg; connections are keyed only by user_id
        record = self._find(user_id)
        if not record:
            return None
        token_enc = record.get("access_token_enc")
        if not token_enc:
            return None
        return decrypt_token(str(token_enc))

    def status_for(self, user_id: str, email: str | None = None) -> dict[str, Any] | None:
        del email
        record = self._find(user_id)
        if not record:
            return None
        return {
            "connected": True,
            "github_login": record.get("github_login"),
            "github_user_id": record.get("github_user_id"),
            "scopes": record.get("scopes"),
            "avatar_url": record.get("avatar_url"),
            "connected_at": record.get("connected_at"),
            "last_validated_at": record.get("last_validated_at"),
        }

    def disconnect(self, user_id: str, email: str | None = None) -> bool:
        del email
        uid = self._usable_user_id(user_id)
        if not uid:
            return False
        self._load()
        removed = self._connections.pop(uid, None) is not None
        drop_keys = [
            key
            for key, item in self._connections.items()
            if str(item.get("user_id") or "") == uid
        ]
        for key in drop_keys:
            self._connections.pop(key, None)
            removed = True
        if removed:
            self._save()
        self._db_delete(uid)
        return removed


github_connection_store = GitHubConnectionStore()
