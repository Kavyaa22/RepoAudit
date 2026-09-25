"""Shared AI prompt / model helpers (no feature logic)."""

from __future__ import annotations

from app.core.config import get_settings


def resolve_api_key() -> str:
    settings = get_settings()
    return (
        settings.deepseek_api_key
        or settings.openai_api_key
        or settings.anthropic_api_key
        or ""
    )


def default_model() -> str:
    return get_settings().default_model
