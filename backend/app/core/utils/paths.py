"""Shared path helpers."""

from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings


def ensure_runtime_dirs() -> None:
    settings = get_settings()
    for path in (
        settings.workspace_dir,
        settings.knowledge_dir,
        settings.logs_dir,
        settings.temp_dir,
        settings.data_dir,
    ):
        Path(path).mkdir(parents=True, exist_ok=True)
