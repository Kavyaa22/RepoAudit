"""Persist audit runs and normalized findings to Supabase."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.core.supabase.client import get_supabase_client, supabase_available

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _model_to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return {}


def extract_findings(
    *,
    audit_id: str,
    project_id: str,
    snapshot_id: str | None,
    user_id: str | None,
    branch: str,
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    base = {
        "audit_id": audit_id,
        "project_id": project_id,
        "snapshot_id": snapshot_id,
        "user_id": user_id,
        "branch": branch,
    }

    for key, kind in (
        ("static_violations", "structure_violation"),
        ("unstructured_areas", "unstructured_area"),
    ):
        for item in result.get(key) or []:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    **base,
                    "finding_id": str(uuid4()),
                    "finding_kind": kind,
                    "severity": item.get("severity"),
                    "path": item.get("path") or "",
                    "symbol_name": item.get("violation_type") or "",
                    "title": item.get("violation_type") or kind,
                    "description": item.get("description") or "",
                    "suggestion": item.get("suggestion") or "",
                    "metadata": item,
                }
            )

    dead_code = result.get("dead_code_result") or {}
    if isinstance(dead_code, dict):
        for item in dead_code.get("findings") or []:
            if not isinstance(item, dict):
                continue
            category = str(item.get("category") or "dead_code")
            kind = "unused_dependency" if category == "unused_dependency" else "dead_code"
            rows.append(
                {
                    **base,
                    "finding_id": str(uuid4()),
                    "finding_kind": kind,
                    "severity": "medium",
                    "path": item.get("path") or "",
                    "symbol_name": item.get("symbol_name") or "",
                    "title": category,
                    "description": item.get("description") or "",
                    "suggestion": item.get("suggestion") or "",
                    "confidence_score": item.get("confidence_score"),
                    "metadata": item,
                }
            )

    security = result.get("security_result") or result.get("security_audit") or {}
    if isinstance(security, dict):
        for item in security.get("findings") or []:
            if not isinstance(item, dict):
                continue
            category = str(item.get("category") or "dangerous_pattern")
            kind = category if category in {"secret", "vulnerable_dependency", "dangerous_pattern"} else "dangerous_pattern"
            rows.append(
                {
                    **base,
                    "finding_id": str(uuid4()),
                    "finding_kind": kind,
                    "severity": item.get("severity") or "medium",
                    "path": item.get("path") or "",
                    "symbol_name": item.get("rule_id") or item.get("package_name") or "",
                    "title": item.get("title") or kind,
                    "description": item.get("description") or "",
                    "suggestion": item.get("suggestion") or "",
                    "metadata": item,
                }
            )

    return rows


def save_audit_run(
    *,
    project_id: str,
    snapshot_id: str | None,
    user_id: str | None,
    branch: str,
    commit_sha: str | None,
    audit_type: str,
    result: Any,
    status: str = "succeeded",
    duration_ms: int = 0,
    error: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not supabase_available() or not user_id:
        return None

    payload = _model_to_dict(result)
    audit_id = str(uuid4())
    finished = _now_iso()
    record = {
        "audit_id": audit_id,
        "project_id": project_id,
        "snapshot_id": snapshot_id,
        "user_id": user_id,
        "branch": branch,
        "commit_sha": commit_sha,
        "audit_type": audit_type,
        "status": status,
        "overall_score": payload.get("overall_score") or payload.get("score"),
        "is_valid": payload.get("is_valid"),
        "result": payload,
        "error": error,
        "duration_ms": duration_ms,
        "created_at": finished,
        "finished_at": finished,
    }

    try:
        client = get_supabase_client()
        
        # Check if an audit_run already exists for this project_id and branch
        existing_res = (
            client.table("audit_runs")
            .select("audit_id")
            .eq("project_id", project_id)
            .eq("branch", branch)
            .eq("audit_type", audit_type)
        )
        if user_id:
            existing_res = existing_res.eq("user_id", str(user_id))
        existing_res = existing_res.execute()
        existing_runs = existing_res.data if existing_res.data and isinstance(existing_res.data, list) else []

        if existing_runs:
            target_audit_id = str(existing_runs[0]["audit_id"])
            record["audit_id"] = target_audit_id
            client.table("audit_runs").update(record).eq("audit_id", target_audit_id).eq(
                "user_id", str(user_id)
            ).execute()
            audit_id = target_audit_id
            # Clean up previous findings for this audit to overwrite with fresh results
            try:
                client.table("audit_findings").delete().eq("audit_id", target_audit_id).execute()
            except Exception as exc:
                logger.debug("Failed to clean previous findings for %s: %s", target_audit_id, exc)
        else:
            client.table("audit_runs").insert(record).execute()

        try:
            findings = extract_findings(
                audit_id=audit_id,
                project_id=project_id,
                snapshot_id=snapshot_id,
                user_id=user_id,
                branch=branch,
                result=payload,
            )
            if findings:
                client.table("audit_findings").insert(findings).execute()
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to persist audit findings for %s: %s", audit_id, exc)

        logger.info(
            "Persisted audit %s (%s) for project %s branch %s (overwrite=%s)",
            audit_id,
            audit_type,
            project_id,
            branch,
            bool(existing_runs),
        )
        return record
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to persist audit run: %s", exc, exc_info=True)
        return None


def list_audit_runs(*, user_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    if not supabase_available() or not user_id:
        return []
    try:
        client = get_supabase_client()
        query = (
            client.table("audit_runs")
            .select("*, projects(display_name, repository_url, owner, repository_name)")
            .eq("user_id", str(user_id))
            .order("created_at", desc=True)
            .limit(limit)
        )
        res = query.execute()
        return res.data if isinstance(res.data, list) else []
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to list audit runs: %s", exc)
        return []


def get_audit_run(*, audit_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    if not supabase_available() or not user_id:
        return None
    try:
        client = get_supabase_client()
        query = (
            client.table("audit_runs")
            .select("*, projects(display_name, repository_url, owner, repository_name)")
            .eq("audit_id", audit_id)
            .eq("user_id", str(user_id))
        )
        res = query.execute()
        if res.data and isinstance(res.data, list) and res.data:
            return res.data[0]
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to get audit run %s: %s", audit_id, exc)
    return None


def get_latest_audit_for_project(
    *,
    project_id: str,
    user_id: str | None = None,
) -> dict[str, Any] | None:
    """Return the most recent succeeded audit run for a Supabase project."""
    if not supabase_available() or not user_id:
        return None
    try:
        client = get_supabase_client()
        query = (
            client.table("audit_runs")
            .select("*, projects(display_name, repository_url, owner, repository_name)")
            .eq("project_id", project_id)
            .eq("status", "succeeded")
            .eq("user_id", str(user_id))
            .order("created_at", desc=True)
            .limit(1)
        )
        res = query.execute()
        if res.data and isinstance(res.data, list) and res.data:
            return res.data[0]
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to get latest audit for project %s: %s", project_id, exc)
    return None


def resolve_audit_run(*, identifier: str, user_id: str | None = None) -> dict[str, Any] | None:
    """Resolve an audit run by audit_id or latest succeeded run for project_id."""
    row = get_audit_run(audit_id=identifier, user_id=user_id)
    if row:
        return row
    row = get_latest_audit_for_project(project_id=identifier, user_id=user_id)
    if row:
        return row
    return None


def delete_audit_runs_for_project(*, project_id: str, user_id: str | None = None) -> int:
    """Delete every audit run for a project, clear findings, and reset project summary."""
    if not supabase_available() or not project_id or not user_id:
        return 0
    try:
        from app.modules.projects.shared.store import project_store

        client = get_supabase_client()
        lookup = (
            client.table("audit_runs")
            .select("audit_id")
            .eq("project_id", project_id)
            .eq("user_id", str(user_id))
        )
        existing = lookup.execute()
        rows = existing.data if isinstance(existing.data, list) else []
        if not rows:
            # Still ensure stale summary on project is reset if project exists
            try:
                client.table("projects").update(
                    {"summary": {}, "audit_project_id": None, "latest_snapshot_id": None}
                ).eq("project_id", project_id).eq("user_id", str(user_id)).execute()
                project_store.update(project_id, summary={}, audit_project_id=None, latest_snapshot_id=None)
            except Exception:
                pass
            return 0

        # Delete findings for all matching audits
        for row in rows:
            aid = str(row.get("audit_id") or "")
            if aid:
                try:
                    client.table("audit_findings").delete().eq("audit_id", aid).execute()
                except Exception as exc:
                    logger.debug("Failed to delete findings for audit %s: %s", aid, exc)

        client.table("audit_runs").delete().eq("project_id", project_id).eq(
            "user_id", str(user_id)
        ).execute()

        # Reset summary on the project
        try:
            client.table("projects").update(
                {"summary": {}, "audit_project_id": None, "latest_snapshot_id": None}
            ).eq("project_id", project_id).eq("user_id", str(user_id)).execute()
            project_store.update(project_id, summary={}, audit_project_id=None, latest_snapshot_id=None)
        except Exception as exc:
            logger.debug("Failed to reset project summary for %s: %s", project_id, exc)

        logger.info("Deleted %s audit run(s) and reset summary for project %s", len(rows), project_id)
        return len(rows)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to delete audit runs for project %s: %s", project_id, exc)
        return 0


def delete_audit_run(*, audit_id: str, user_id: str | None = None) -> bool:
    """Delete an audit run, cascade-delete findings, and sync project summary. Returns True if removed."""
    if not supabase_available():
        return False

    row = get_audit_run(audit_id=audit_id, user_id=user_id)
    if not row:
        return False

    project_id = str(row.get("project_id") or "")

    try:
        from app.modules.projects.shared.store import project_store

        client = get_supabase_client()
        # 1. Delete findings for this audit run
        try:
            client.table("audit_findings").delete().eq("audit_id", audit_id).execute()
        except Exception as exc:
            logger.debug("Failed to delete findings for %s: %s", audit_id, exc)

        # 2. Delete the audit run
        del_query = client.table("audit_runs").delete().eq("audit_id", audit_id)
        if user_id:
            del_query = del_query.eq("user_id", str(user_id))
        del_query.execute()
        logger.info("Deleted audit run %s", audit_id)

        # 3. Synchronize project summary
        if project_id and user_id:
            latest = get_latest_audit_for_project(project_id=project_id, user_id=user_id)
            if latest:
                latest_res = latest.get("result") or {}
                client.table("projects").update(
                    {
                        "summary": {**latest_res, "audit_id": latest.get("audit_id")},
                        "audit_project_id": str(latest.get("audit_id") or ""),
                    }
                ).eq("project_id", project_id).eq("user_id", str(user_id)).execute()
                project_store.update(
                    project_id,
                    summary={**latest_res, "audit_id": latest.get("audit_id")},
                    audit_project_id=str(latest.get("audit_id") or ""),
                )
            else:
                client.table("projects").update(
                    {"summary": {}, "audit_project_id": None, "latest_snapshot_id": None}
                ).eq("project_id", project_id).eq("user_id", str(user_id)).execute()
                project_store.update(
                    project_id,
                    summary={},
                    audit_project_id=None,
                    latest_snapshot_id=None,
                )

        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to delete audit run %s: %s", audit_id, exc)
        return False



def list_findings_for_audit(audit_id: str) -> list[dict[str, Any]]:
    if not supabase_available():
        return []
    try:
        client = get_supabase_client()
        res = (
            client.table("audit_findings")
            .select("*")
            .eq("audit_id", audit_id)
            .order("created_at")
            .execute()
        )
        return res.data if isinstance(res.data, list) else []
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to list findings for audit %s: %s", audit_id, exc)
        return []
