"""System routes: health and version."""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.core.config import get_settings
from app.core.responses import ApiResponse
from app.core.supabase import supabase_available

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "version": __version__,
        "auth_disabled": settings.auth_disabled,
        "supabase": supabase_available(),
    }


@router.get("/version", response_model=ApiResponse[dict])
async def version() -> ApiResponse[dict]:
    return ApiResponse(data={"version": __version__, "name": get_settings().app_name})
