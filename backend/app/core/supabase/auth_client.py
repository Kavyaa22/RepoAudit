"""Supabase anon client for password sign-in."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.core.config import get_settings


@lru_cache
def get_supabase_auth_client() -> Any:
    """Return a Supabase client using the anon key (for sign-in)."""
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise RuntimeError("Set SUPABASE_URL and SUPABASE_ANON_KEY in backend/.env")

    from supabase import create_client

    return create_client(settings.supabase_url, settings.supabase_anon_key)


def supabase_auth_available() -> bool:
    settings = get_settings()
    return bool(settings.supabase_url and settings.supabase_anon_key)
