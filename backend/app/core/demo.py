"""Identify smoke-test / fixture repositories that must not appear in product UI."""

from __future__ import annotations

import re
from typing import Any

_DEMO_OWNER_REPO = re.compile(r"^(example/)?demo(-[0-9a-f]{6,})?$", re.IGNORECASE)
_DEMO_DISPLAY = re.compile(r"^demo(-[0-9a-f]{6,})?$", re.IGNORECASE)
_DEMO_URL = re.compile(r"github\.com/example/demo", re.IGNORECASE)


def _text(value: Any) -> str:
    return str(value or "").strip()


def is_demo_record(
    *,
    name: Any = None,
    display_name: Any = None,
    project_name: Any = None,
    owner: Any = None,
    repository_name: Any = None,
    repository_url: Any = None,
    full_name: Any = None,
) -> bool:
    owner_text = _text(owner)
    repo_text = _text(repository_name)
    if owner_text.lower() == "example" and _DEMO_DISPLAY.match(repo_text):
        return True

    candidates = [
        full_name,
        name,
        display_name,
        project_name,
        repository_url,
        f"{owner_text}/{repo_text}" if owner_text and repo_text else "",
    ]
    for value in candidates:
        text = _text(value)
        if not text:
            continue
        if _DEMO_URL.search(text):
            return True
        if _DEMO_OWNER_REPO.match(text) or _DEMO_DISPLAY.match(text):
            return True
    return False


def is_demo_mapping(record: dict[str, Any] | None) -> bool:
    if not isinstance(record, dict):
        return False
    project_meta = record.get("projects") or {}
    if isinstance(project_meta, list) and project_meta:
        project_meta = project_meta[0]
    if not isinstance(project_meta, dict):
        project_meta = {}
    return is_demo_record(
        name=record.get("name"),
        display_name=record.get("display_name") or project_meta.get("display_name"),
        project_name=record.get("project_name"),
        owner=record.get("owner") or project_meta.get("owner"),
        repository_name=record.get("repository_name") or project_meta.get("repository_name"),
        repository_url=record.get("repository_url") or project_meta.get("repository_url"),
        full_name=record.get("full_name"),
    )
