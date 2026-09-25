"""Per-app-user workspace paths. Clones and artifacts live under workspace/{user_id}/."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def workspace_root_for(backend_root: Path | None = None) -> Path:
    if backend_root is not None:
        return Path(backend_root) / "workspace"
    from app.core.config import get_settings

    return Path(get_settings().workspace_dir)


def is_path_within(child: Path, parent: Path) -> bool:
    """True when child is parent or a descendant. Both paths are resolved."""
    try:
        child_res = child.expanduser().resolve()
        parent_res = parent.expanduser().resolve()
        child_res.relative_to(parent_res)
        return True
    except (ValueError, OSError):
        return False


def is_usable_user_id(user_id: str | None) -> bool:
    if not user_id:
        return False
    try:
        uuid.UUID(str(user_id).strip())
        return True
    except ValueError:
        return False


def safe_workspace_segment(value: str, *, fallback: str = "workspace") -> str:
    text = _UNSAFE.sub("-", (value or "").strip()).strip(".-")
    if not text or text in {".", ".."}:
        return fallback
    return text[:128]


def user_workspace_dir(user_id: str, *, backend_root: Path | None = None) -> Path:
    uid = str(user_id).strip()
    if not is_usable_user_id(uid):
        raise ValueError("user_id must be a UUID")
    return workspace_root_for(backend_root) / uid


def project_workspace_dir(user_id: str, project_id: str, *, backend_root: Path | None = None) -> Path:
    pid = safe_workspace_segment(project_id, fallback="project")
    return user_workspace_dir(user_id, backend_root=backend_root) / pid


def ingest_workspace_dir(
    user_id: str,
    owner: str,
    repo: str,
    *,
    backend_root: Path | None = None,
) -> Path:
    return (
        user_workspace_dir(user_id, backend_root=backend_root)
        / "ingest"
        / safe_workspace_segment(owner, fallback="owner")
        / safe_workspace_segment(repo, fallback="repo")
    )


def path_belongs_to_user(
    path: str | Path,
    user_id: str | None,
    *,
    backend_root: Path | None = None,
) -> bool:
    """True when path is under this user's workspace or an owned project's stored path."""
    if not is_usable_user_id(user_id) or not path:
        return False
    try:
        resolved = Path(path).expanduser().resolve()
    except OSError:
        return False

    try:
        user_root = user_workspace_dir(str(user_id), backend_root=backend_root)
    except ValueError:
        return False
    if is_path_within(resolved, user_root):
        return True

    ws_root = workspace_root_for(backend_root)
    try:
        from app.modules.projects.shared.store import project_store

        records = project_store.list(user_id=str(user_id))
    except Exception:
        records = []

    for record in records:
        pid = str(record.get("project_id") or "")
        stored = record.get("workspace_path")
        if stored:
            stored_path = Path(str(stored))
            if not stored_path.is_absolute():
                stored_path = (Path(backend_root) if backend_root else ws_root.parent) / stored_path
            if is_path_within(resolved, stored_path):
                return True
        if pid:
            legacy = ws_root / pid
            if is_path_within(resolved, legacy):
                return True
    return False
