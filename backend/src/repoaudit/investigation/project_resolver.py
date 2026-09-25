"""Resolve local filesystem path for an investigation target project."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def resolve_project_directory(
    *,
    project_name: str,
    repo_path: str = "",
    project_id: str = "",
    backend_root: Path | None = None,
    branch: str = "",
    user_id: str | None = None,
) -> Path | None:
    """Find an on-disk directory owned by this app user. Never walks other tenants."""
    if not user_id:
        return None

    base_dir = backend_root or Path(__file__).resolve().parents[3]

    from app.core.workspace import path_belongs_to_user, user_workspace_dir, workspace_root_for

    if repo_path:
        try:
            candidate = Path(repo_path).expanduser().resolve()
        except OSError:
            candidate = None
        if (
            candidate is not None
            and candidate.is_dir()
            and path_belongs_to_user(candidate, user_id, backend_root=base_dir)
        ):
            return candidate

    workspace_root = workspace_root_for(base_dir)

    if project_id:
        record = _owned_project(project_id, user_id)
        if not record:
            return None
        for path in _paths_from_owned_record(record, workspace_root, base_dir, user_id, branch):
            if path.is_dir():
                return path
        return None

    needle = (project_name or "").strip().lower()
    if needle:
        try:
            from app.modules.projects.shared.store import project_store

            for record in project_store.list(user_id=user_id):
                display = str(record.get("display_name", "")).lower()
                repo = str(record.get("repository_name", "")).lower()
                slug = display.replace(" ", "-")
                if needle not in {display, repo, slug, str(record.get("project_name", "")).lower()}:
                    continue
                for path in _paths_from_owned_record(record, workspace_root, base_dir, user_id, branch):
                    if path.is_dir():
                        return path
        except Exception as exc:  # noqa: BLE001
            logger.debug("Project name lookup skipped: %s", exc)

        try:
            named = user_workspace_dir(user_id, backend_root=base_dir) / project_name
            if named.is_dir() and path_belongs_to_user(named, user_id, backend_root=base_dir):
                return named
        except ValueError:
            pass

    return None


def _owned_project(project_id: str, user_id: str) -> dict | None:
    try:
        from app.modules.projects.shared.store import project_store

        return project_store.get_for_user(project_id, user_id)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Project store lookup skipped: %s", exc)
        return None


def _paths_from_owned_record(
    record: dict,
    workspace_root: Path,
    backend_root: Path,
    user_id: str,
    branch: str,
) -> list[Path]:
    from app.core.workspace import path_belongs_to_user, project_workspace_dir

    paths: list[Path] = []
    project_id = str(record.get("project_id") or "")
    stored = record.get("workspace_path")
    if stored:
        ws = Path(str(stored))
        if not ws.is_absolute():
            ws = backend_root / ws
        paths.append(ws)

    if project_id:
        try:
            scoped = project_workspace_dir(user_id, project_id, backend_root=backend_root)
            paths.append(scoped)
            snaps = scoped / "snapshots"
            paths.append(snaps)
            if snaps.is_dir():
                paths.extend(_prefer_branch_snapshots(snaps, branch)[:1])
        except ValueError:
            pass
        legacy = workspace_root / project_id
        paths.append(legacy)
        legacy_snaps = legacy / "snapshots"
        paths.append(legacy_snaps)
        if legacy_snaps.is_dir():
            paths.extend(_prefer_branch_snapshots(legacy_snaps, branch)[:1])

    owned: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            key = str(path.resolve()) if path.exists() else str(path)
        except OSError:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if path_belongs_to_user(path, user_id, backend_root=backend_root):
            owned.append(path)
    return owned


def _prefer_branch_snapshots(snapshots: Path, branch: str) -> list[Path]:
    try:
        snaps = [p for p in snapshots.iterdir() if p.is_dir()]
    except OSError:
        return []
    if not snaps:
        return []
    branch_key = (branch or "").strip().lower().replace("/", "-")
    if branch_key:
        named = [p for p in snaps if branch_key in p.name.lower()]
        if named:
            return sorted(named, key=lambda p: p.stat().st_mtime, reverse=True)
    return sorted(snaps, key=lambda p: p.stat().st_mtime, reverse=True)
