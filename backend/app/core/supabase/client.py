"""Supabase service-role client (bypasses RLS)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.core.config import get_settings


class SupabaseNotConfiguredError(RuntimeError):
    """Raised when Supabase env vars are missing."""


@lru_cache
def get_supabase_client() -> Any:
    """Return a service-role Supabase client, or raise if not configured."""
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise SupabaseNotConfiguredError(
            "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in backend/.env"
        )

    try:
        from supabase import create_client
    except ImportError as exc:
        raise RuntimeError(
            "supabase package not installed. Run: pip install supabase"
        ) from exc

    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def supabase_available() -> bool:
    settings = get_settings()
    return bool(settings.supabase_url and settings.supabase_service_role_key)
