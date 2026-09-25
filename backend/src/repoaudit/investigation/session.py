"""Session cache + merge helpers for multi-turn investigations."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from repoaudit.investigation.investigation_models import InvestigationResult, IssueReport, LiveArtifact

logger = logging.getLogger(__name__)


def cache_dir(backend_root: Path, user_id: str | None = None) -> Path:
    if user_id:
        path = backend_root / "workspace" / user_id / ".investigation_cache"
    else:
        path = backend_root / "workspace" / ".investigation_cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_local_session(
    backend_root: Path,
    *,
    investigation_id: str,
    report: IssueReport,
    result: InvestigationResult,
    workspace_path: str,
    user_id: str | None = None,
) -> None:
    payload = {
        "investigation_id": investigation_id,
        "user_id": user_id,
        "workspace_path": workspace_path,
        "report": report.model_dump(),
        "result": result.model_dump(),
    }
    target = cache_dir(backend_root, user_id=user_id) / f"{investigation_id}.json"
    try:
        target.write_text(json.dumps(payload), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not cache investigation session %s: %s", investigation_id, exc)


def load_local_session(
    backend_root: Path,
    investigation_id: str,
    user_id: str | None = None,
) -> dict[str, Any] | None:
    if not user_id:
        return None
    target = cache_dir(backend_root, user_id=user_id) / f"{investigation_id}.json"
    if not target.is_file():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not load investigation session %s: %s", investigation_id, exc)
        return None
    stored_uid = str(payload.get("user_id") or "")
    if stored_uid and stored_uid != str(user_id):
        return None
    return payload


def merge_reports(prior: IssueReport, incoming: IssueReport) -> IssueReport:
    """Merge continue-turn evidence into the prior report without dropping strong signals."""

    def prefer(old: str, new: str) -> str:
        old_s = (old or "").strip()
        new_s = (new or "").strip()
        if not new_s:
            return old_s
        if not old_s:
            return new_s
        if new_s in old_s:
            return old_s
        if old_s in new_s:
            return new_s
        return f"{old_s}\n{new_s}".strip()

    artifacts: list[LiveArtifact] = list(prior.live_artifacts)
    for artifact in incoming.live_artifacts:
        if not any(a.kind == artifact.kind and a.content.strip() == artifact.content.strip() for a in artifacts):
            artifacts.append(artifact)

    return IssueReport(
        project_name=incoming.project_name or prior.project_name,
        project_id=incoming.project_id or prior.project_id,
        branch=incoming.branch or prior.branch,
        feature_name=incoming.feature_name or prior.feature_name,
        action_name=incoming.action_name or prior.action_name,
        expected_behavior=prefer(prior.expected_behavior, incoming.expected_behavior),
        actual_behavior=prefer(prior.actual_behavior, incoming.actual_behavior),
        environment=incoming.environment or prior.environment,
        severity=incoming.severity or prior.severity,
        issue_description=prefer(prior.issue_description, incoming.issue_description) or incoming.issue_description,
        error_log=prefer(prior.error_log, incoming.error_log),
        live_artifacts=artifacts,
        investigation_id=incoming.investigation_id or prior.investigation_id,
        repo_path=incoming.repo_path or prior.repo_path,
    )
