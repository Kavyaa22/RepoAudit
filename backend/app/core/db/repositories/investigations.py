"""Persist investigations to Supabase."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.core.supabase.client import get_supabase_client, supabase_available

logger = logging.getLogger(__name__)


def _status_map(app_status: str) -> str:
    mapping = {
        "SUCCESS": "complete",
        "PARTIAL": "incomplete",
        "FAILED": "failed",
    }
    return mapping.get(app_status.upper(), "incomplete")


def get_investigation(investigation_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    """Load a persisted investigation owned by this app user."""
    if not supabase_available() or not user_id:
        return None
    try:
        client = get_supabase_client()
        response = (
            client.table("investigations")
            .select("*")
            .eq("investigation_id", investigation_id)
            .eq("user_id", str(user_id))
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load investigation %s: %s", investigation_id, exc, exc_info=True)
        return None


def _get_investigation_any(investigation_id: str) -> dict[str, Any] | None:
    """Lookup by id only — used to refuse overwriting another tenant's row."""
    if not supabase_available() or not investigation_id:
        return None
    try:
        client = get_supabase_client()
        response = (
            client.table("investigations")
            .select("investigation_id, user_id")
            .eq("investigation_id", investigation_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to probe investigation %s: %s", investigation_id, exc, exc_info=True)
        return None


def save_investigation(
    *,
    investigation_id: str,
    project_id: str,
    snapshot_id: str | None,
    user_id: str | None,
    branch: str,
    commit_sha: str | None,
    issue_description: str,
    feature_name: str,
    action_name: str,
    error_log: str,
    result: Any,
    workspace_path: str,
    duration_ms: int = 0,
    artifact_path: str = "",
) -> dict[str, Any] | None:
    if not supabase_available() or not user_id:
        return None

    existing = _get_investigation_any(investigation_id)
    if existing and str(existing.get("user_id") or "") != str(user_id):
        logger.error("Refusing to overwrite investigation %s owned by another user", investigation_id)
        return None

    payload: dict[str, Any]
    if hasattr(result, "model_dump"):
        payload = result.model_dump()
    elif isinstance(result, dict):
        payload = result
    else:
        payload = {}

    app_status = str(payload.get("status") or "PARTIAL")
    primary = payload.get("primary_root_cause") or {}
    confidence: float | None = None
    root_cause: str | None = None
    if isinstance(primary, dict):
        root_cause = primary.get("title")
        score = primary.get("likelihood_score")
        if score is not None:
            confidence = float(score) / 100.0

    targets = payload.get("isolated_targets") or []
    now = datetime.now(UTC).isoformat()
    record = {
        "investigation_id": investigation_id,
        "project_id": project_id,
        "user_id": user_id,
        "snapshot_id": snapshot_id,
        "branch": branch,
        "commit_sha": commit_sha,
        "issue": issue_description[:2000],
        "issue_description": issue_description,
        "feature_name": feature_name,
        "action_name": action_name,
        "error_log": error_log,
        "status": _status_map(app_status),
        "root_cause": root_cause,
        "confidence": confidence,
        "ai_available": bool(payload.get("code_patches")),
        "affected_files": len(targets) if isinstance(targets, list) else 0,
        "correlated_findings": len(payload.get("all_hypotheses") or []),
        "path": workspace_path or "",
        "duration_ms": duration_ms,
        "result": payload,
        "artifact_path": artifact_path or payload.get("artifact_path") or "",
        "created_at": now,
        "updated_at": now,
    }

    try:
        client = get_supabase_client()
        client.table("investigations").upsert(record).execute()
        logger.info(
            "Persisted investigation %s for project %s branch %s",
            investigation_id,
            project_id,
            branch,
        )
        return record
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to persist investigation: %s", exc, exc_info=True)
        return None


def list_investigations(user_id: str | None = None) -> list[dict[str, Any]]:
    """List persisted investigations for a user. Never returns another tenant's rows."""
    if not supabase_available() or not user_id:
        return []
    try:
        client = get_supabase_client()
        query = (
            client.table("investigations")
            .select("*, projects(display_name, repository_url, owner, repository_name)")
            .eq("user_id", str(user_id))
            .order("created_at", desc=True)
        )
        res = query.execute()
        return res.data if isinstance(res.data, list) else []
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to list investigations: %s", exc, exc_info=True)
        return []

