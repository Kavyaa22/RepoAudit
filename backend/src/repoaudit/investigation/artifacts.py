"""Persistent investigation artifacts with retention cleanup."""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from repoaudit.investigation.investigation_models import InvestigationResult, IssueReport, LiveArtifact

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = 30


def artifacts_root(backend_root: Path, user_id: str | None = None) -> Path:
    if user_id:
        path = backend_root / "workspace" / user_id / "investigation_artifacts"
    else:
        path = backend_root / "workspace" / "investigation_artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def investigation_dir(
    backend_root: Path,
    investigation_id: str,
    user_id: str | None = None,
    *,
    create: bool = True,
) -> Path:
    path = artifacts_root(backend_root, user_id=user_id) / investigation_id
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def save_artifacts(
    backend_root: Path,
    *,
    investigation_id: str,
    report: IssueReport,
    result: InvestigationResult,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    user_id: str | None = None,
) -> str:
    """Persist redacted report/result/live artifacts; return artifact directory path."""
    folder = investigation_dir(backend_root, investigation_id, user_id=user_id, create=True)
    expires_at = datetime.now(UTC) + timedelta(days=retention_days)
    meta = {
        "investigation_id": investigation_id,
        "user_id": user_id,
        "created_at": datetime.now(UTC).isoformat(),
        "expires_at": expires_at.isoformat(),
        "retention_days": retention_days,
        "turn": result.turn,
        "status": result.status,
    }
    (folder / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    from repoaudit.investigation.evidence import sanitized_report

    safe_report = sanitized_report(report)
    (folder / "report.json").write_text(json.dumps(safe_report.model_dump(), indent=2), encoding="utf-8")
    (folder / "result.json").write_text(json.dumps(result.model_dump(), indent=2), encoding="utf-8")

    artifacts_payload = []
    for idx, artifact in enumerate(safe_report.live_artifacts):
        redacted = artifact.content
        artifacts_payload.append({"kind": artifact.kind, "content": redacted})
        (folder / f"artifact_{idx:02d}_{artifact.kind}.txt").write_text(redacted, encoding="utf-8")
    (folder / "live_artifacts.json").write_text(json.dumps(artifacts_payload, indent=2), encoding="utf-8")
    return str(folder)


def load_artifact_report(
    backend_root: Path,
    investigation_id: str,
    user_id: str | None = None,
) -> IssueReport | None:
    if not user_id:
        return None
    path = investigation_dir(backend_root, investigation_id, user_id=user_id, create=False) / "report.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["live_artifacts"] = [
            LiveArtifact(**a) if isinstance(a, dict) else a for a in data.get("live_artifacts") or []
        ]
        return IssueReport(**data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load artifact report %s: %s", investigation_id, exc)
        return None


def load_artifact_result(
    backend_root: Path,
    investigation_id: str,
    user_id: str | None = None,
) -> dict[str, Any] | None:
    if not user_id:
        return None
    path = investigation_dir(backend_root, investigation_id, user_id=user_id, create=False) / "result.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load artifact result %s: %s", investigation_id, exc)
        return None


def _remove_artifact_folder(folder: Path) -> bool:
    try:
        for child in folder.rglob("*"):
            if child.is_file():
                child.unlink(missing_ok=True)
        for child in sorted(folder.rglob("*"), reverse=True):
            if child.is_dir():
                child.rmdir()
        folder.rmdir()
        return True
    except OSError as exc:
        logger.warning("Failed cleaning artifacts for %s: %s", folder.name, exc)
        return False


def _cleanup_root(root: Path, current: datetime) -> int:
    removed = 0
    if not root.is_dir():
        return 0
    for folder in root.iterdir():
        if not folder.is_dir():
            continue
        meta_path = folder / "meta.json"
        expires = None
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                expires = datetime.fromisoformat(meta.get("expires_at"))
            except Exception:  # noqa: BLE001
                expires = None
        if expires is None:
            age_days = (time.time() - folder.stat().st_mtime) / 86400
            if age_days < DEFAULT_RETENTION_DAYS:
                continue
        elif expires > current:
            continue
        if _remove_artifact_folder(folder):
            removed += 1
    return removed


def cleanup_expired_artifacts(backend_root: Path, now: datetime | None = None) -> int:
    """Delete expired artifact folders. Returns number removed."""
    current = now or datetime.now(UTC)
    workspace = backend_root / "workspace"
    removed = _cleanup_root(workspace / "investigation_artifacts", current)
    if workspace.is_dir():
        for user_dir in workspace.iterdir():
            if not user_dir.is_dir():
                continue
            removed += _cleanup_root(user_dir / "investigation_artifacts", current)
    return removed
