"""Supabase Auth Admin + profiles persistence."""

from __future__ import annotations

import logging
from typing import Any

from app.core.exceptions import ConflictError, NotFoundError, UnauthorizedError
from app.core.supabase.auth_client import get_supabase_auth_client, supabase_auth_available
from app.core.supabase.client import get_supabase_client, supabase_available

logger = logging.getLogger(__name__)


def _admin_client():
    return get_supabase_client()


def _profile_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": str(row["user_id"]),
        "email": str(row.get("email", "")).lower(),
        "full_name": str(row.get("full_name") or ""),
    }


def create_user(*, email: str, password: str, full_name: str) -> dict[str, Any]:
    """Register via Supabase Auth Admin; profile row created by DB trigger."""
    if not supabase_available():
        raise RuntimeError("Supabase is not configured")

    lower_email = email.strip().lower()
    client = _admin_client()

    try:
        resp = client.auth.admin.create_user(
            {
                "email": lower_email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {"full_name": full_name.strip()},
            }
        )
    except Exception as exc:  # noqa: BLE001
        message = str(exc).lower()
        if "already" in message or "duplicate" in message or "exists" in message:
            raise ConflictError("An account with this email address already exists.") from exc
        logger.error("Supabase create_user failed: %s", exc)
        raise

    user = getattr(resp, "user", None) or (resp.get("user") if isinstance(resp, dict) else None)
    if user is None:
        raise RuntimeError("Supabase did not return a user on registration")

    user_id = str(getattr(user, "id", None) or user.get("id"))
    profile = get_profile(user_id)
    if profile:
        return profile

    # Fallback if trigger did not run yet
    meta = getattr(user, "user_metadata", None) or {}
    if isinstance(user, dict):
        meta = user.get("user_metadata") or {}
    return {
        "user_id": user_id,
        "email": lower_email,
        "full_name": full_name.strip() or str(meta.get("full_name") or ""),
    }


def verify_user(*, email: str, password: str) -> dict[str, Any]:
    """Verify credentials via Supabase sign-in."""
    if not supabase_auth_available():
        raise RuntimeError("Supabase auth is not configured")

    lower_email = email.strip().lower()
    auth_client = get_supabase_auth_client()

    try:
        session = auth_client.auth.sign_in_with_password(
            {"email": lower_email, "password": password}
        )
    except Exception as exc:  # noqa: BLE001
        raise UnauthorizedError("Invalid email or password") from exc

    user = getattr(session, "user", None)
    if user is None and isinstance(session, dict):
        user = session.get("user")
    if user is None:
        raise UnauthorizedError("Invalid email or password")

    user_id = str(getattr(user, "id", None) or user.get("id"))
    profile = get_profile(user_id)
    if profile:
        return profile

    meta = getattr(user, "user_metadata", None) or {}
    if isinstance(user, dict):
        meta = user.get("user_metadata") or {}
    return {
        "user_id": user_id,
        "email": lower_email,
        "full_name": str(meta.get("full_name") or ""),
    }


def get_profile(user_id: str) -> dict[str, Any] | None:
    if not supabase_available():
        return None
    try:
        client = _admin_client()
        res = client.table("profiles").select("*").eq("user_id", user_id).execute()
        if res.data and isinstance(res.data, list) and res.data:
            return _profile_from_row(res.data[0])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load profile %s: %s", user_id, exc)
    return None


def update_profile(user_id: str, *, full_name: str) -> dict[str, Any]:
    if not supabase_available():
        raise RuntimeError("Supabase is not configured")

    client = _admin_client()
    payload = {"full_name": full_name.strip()}
    try:
        res = (
            client.table("profiles")
            .update(payload)
            .eq("user_id", user_id)
            .execute()
        )
        if res.data and isinstance(res.data, list) and res.data:
            return _profile_from_row(res.data[0])
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to update profile %s: %s", user_id, exc)
        raise

    existing = get_profile(user_id)
    if not existing:
        raise NotFoundError("User account not found.")
    return existing


def delete_user(user_id: str, *, email: str, password: str) -> None:
    if not supabase_available() or not supabase_auth_available():
        raise RuntimeError("Supabase is not configured")

    verify_user(email=email, password=password)
    client = _admin_client()
    try:
        client.auth.admin.delete_user(user_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to delete Supabase user %s: %s", user_id, exc)
        raise
