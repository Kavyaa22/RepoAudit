"""User store: Supabase profiles when configured, in-memory fallback for local dev/tests."""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from typing import Any

from app.core.exceptions import AppError, ConflictError, UnauthorizedError
from app.core.supabase.client import supabase_available
from app.modules.auth.shared import supabase_auth

logger = logging.getLogger(__name__)


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False


def _hash_password(password: str, *, salt: str = "repoaudit-dev") -> str:
    return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()


class UserStore:
    def __init__(self) -> None:
        self._users: dict[str, dict[str, Any]] = {}

    def find_by_email(self, email: str) -> dict[str, Any] | None:
        lower_email = email.strip().lower()
        cached = self._users.get(lower_email)
        if cached is not None:
            return cached

        if supabase_available():
            try:
                from app.core.supabase.client import get_supabase_client

                client = get_supabase_client()
                res = (
                    client.table("profiles")
                    .select("*")
                    .ilike("email", lower_email)
                    .limit(1)
                    .execute()
                )
                if res.data and isinstance(res.data, list) and res.data:
                    row = res.data[0]
                    record = {
                        "user_id": str(row["user_id"]),
                        "email": lower_email,
                        "full_name": str(row.get("full_name") or ""),
                    }
                    self._users[lower_email] = record
                    return record
            except Exception as exc:  # noqa: BLE001
                logger.warning("Supabase profile lookup failed: %s", exc)
        return self._users.get(lower_email)

    def create(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        user_id: str,
    ) -> dict[str, Any]:
        lower_email = email.strip().lower()

        if supabase_available() and _is_uuid(user_id):
            try:
                return supabase_auth.create_user(
                    email=lower_email,
                    password=password,
                    full_name=full_name,
                )
            except ConflictError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Supabase registration failed (Supabase is configured; not using memory fallback): %s",
                    exc,
                )
                raise AppError(
                    "Registration failed: authentication service unavailable. "
                    "Ensure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set on the backend.",
                    code="auth_unavailable",
                ) from exc

        if lower_email in self._users:
            raise ConflictError("An account with this email address already exists.")

        record = {
            "user_id": user_id,
            "email": lower_email,
            "full_name": full_name.strip(),
            "password_hash": _hash_password(password),
        }
        self._users[lower_email] = record
        return record

    def verify(self, email: str, password: str) -> dict[str, Any] | None:
        lower_email = email.strip().lower()

        if supabase_available():
            try:
                from app.core.supabase.auth_client import supabase_auth_available

                if supabase_auth_available():
                    record = supabase_auth.verify_user(email=lower_email, password=password)
                    self._users[lower_email] = {**record, "password_hash": ""}
                    return record
            except UnauthorizedError:
                # Allow in-memory dev/test users when Supabase has no matching account.
                memory_user = self._users.get(lower_email)
                if memory_user:
                    expected = memory_user.get("password_hash", "")
                    if expected:
                        actual = _hash_password(password)
                        if hmac.compare_digest(expected, actual):
                            return memory_user
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Supabase sign-in failed (Supabase is configured; not using memory fallback): %s",
                    exc,
                )
                raise AppError(
                    "Login failed: authentication service unavailable. "
                    "Ensure SUPABASE_URL and SUPABASE_ANON_KEY are set on the backend.",
                    code="auth_unavailable",
                ) from exc

        user = self._users.get(lower_email)
        if not user:
            return None
        expected = user.get("password_hash", "")
        if not expected:
            return None
        actual = _hash_password(password)
        if not hmac.compare_digest(expected, actual):
            return None
        return user

    def find_by_user_id(self, user_id: str) -> dict[str, Any] | None:
        if supabase_available() and _is_uuid(user_id):
            profile = supabase_auth.get_profile(user_id)
            if profile:
                self._users[profile["email"]] = profile
                return profile

        for user in self._users.values():
            if user.get("user_id") == user_id:
                return user
        return None

    def update_profile(self, user_id: str, *, full_name: str) -> dict[str, Any] | None:
        if supabase_available() and _is_uuid(user_id):
            try:
                updated = supabase_auth.update_profile(user_id, full_name=full_name)
                self._users[updated["email"]] = updated
                return updated
            except Exception as exc:  # noqa: BLE001
                logger.warning("Supabase profile update failed: %s", exc)

        user = self.find_by_user_id(user_id)
        if not user:
            return None
        user["full_name"] = full_name.strip()
        email = user.get("email")
        if email:
            self._users[email] = user
        return user

    def delete_user(self, user_id: str, password: str) -> bool:
        user = self.find_by_user_id(user_id)
        if not user:
            return False
        email = str(user.get("email") or "")

        if supabase_available() and _is_uuid(user_id):
            try:
                from app.core.supabase.auth_client import supabase_auth_available

                if supabase_auth_available() and email:
                    supabase_auth.delete_user(user_id, email=email, password=password)
                    self._users.pop(email.lower(), None)
                    return True
            except Exception as exc:  # noqa: BLE001
                logger.warning("Supabase user delete failed: %s", exc)
                return False

        expected = user.get("password_hash", "")
        actual = _hash_password(password)
        if not expected or not hmac.compare_digest(expected, actual):
            return False
        if email and email in self._users:
            del self._users[email]
            return True
        return False


user_store = UserStore()
