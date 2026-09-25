"""Enrich persisted scan records for history UI without re-running audits."""

from __future__ import annotations

import re
from typing import Any

from repoaudit.audit.scoring import compute_structure_score, violations_from_audit_payload

_COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)


def is_commit_sha(value: str | None) -> bool:
    if not value:
        return False
    return bool(_COMMIT_SHA_RE.match(value.strip()))


def _pick_display_name(raw: dict[str, Any]) -> str:
    """Resolve human-readable repository name from persisted scan payload."""
    candidates = [
        raw.get("display_name"),
        raw.get("name"),
        (raw.get("wiki_summary") or {}).get("project_name"),
    ]
    owner = (raw.get("owner") or "").strip()
    repo = (raw.get("repository_name") or "").strip()
    if owner and repo:
        candidates.insert(0, f"{owner}/{repo}")

    for cand in candidates:
        if not cand or not str(cand).strip():
            continue
        text = str(cand).strip()
        if is_commit_sha(text):
            continue
        return text

    # Commit SHA folder name → friendly label (no re-scan required)
    name = str(raw.get("name") or "").strip()
    if is_commit_sha(name):
        return f"Repository ({name[:7]})"

    return "Repository"


def _pick_branch(raw: dict[str, Any]) -> str:
    branch = (raw.get("branch") or "").strip()
    if branch and branch.lower() != "main":
        return branch
    # Some import records only stored branch on linked project metadata
    alt = (raw.get("default_branch") or "").strip()
    return alt or branch or "main"


def _pick_score(raw: dict[str, Any]) -> tuple[int, bool]:
    """Recompute score from stored structure_audit when possible."""
    sa = raw.get("structure_audit")
    if isinstance(sa, dict):
        violations = violations_from_audit_payload(sa)
        if violations:
            return compute_structure_score(violations)
        overall = sa.get("overall_score")
        if isinstance(overall, int):
            return overall, bool(sa.get("is_valid", overall >= 80))

    score = raw.get("score", 100)
    if not isinstance(score, int):
        try:
            score = int(score)
        except (TypeError, ValueError):
            score = 100
    return score, bool(raw.get("is_valid", score >= 80))


def enrich_scan_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a scan/history row for API responses."""
    score, is_valid = _pick_score(raw)
    project_id = raw.get("project_id") or raw.get("id") or ""
    out = dict(raw) if isinstance(raw, dict) else {}
    out.update(
        {
            "id": raw.get("id") or project_id or "",
            "project_id": project_id,
            "audit_id": raw.get("audit_id") or "",
            "name": _pick_display_name(raw),
            "status": raw.get("status", "done"),
            "error": raw.get("error", ""),
            "total_files": raw.get("total_files", 0),
            "total_lines": raw.get("total_lines", 0),
            "created_at": raw.get("created_at", ""),
            "score": score,
            "is_valid": is_valid,
            "branch": _pick_branch(raw),
        }
    )
    return out


def slim_scan_record_for_list(raw: dict[str, Any]) -> dict[str, Any]:
    """Drop heavy audit/wiki blobs so history lists stay fast."""
    enriched = enrich_scan_record(raw)
    for key in ("structure_audit", "dead_code_audit", "security_audit", "wiki_summary", "progress"):
        enriched.pop(key, None)
    return enriched


def summary_has_active_scan(summary: Any, *, known_audit_ids: set[str] | None = None) -> bool:
    """
    True when a projects.summary blob should appear in history.

    Requires a live audit_id that still exists in audit_runs when known_audit_ids
    is provided. Bare status/total_files alone must not resurrect deleted audits.
    """
    if not isinstance(summary, dict) or not summary:
        return False
    audit_id = str(summary.get("audit_id") or "").strip()
    if not audit_id:
        return False
    if known_audit_ids is not None and audit_id not in known_audit_ids:
        return False
    return True
