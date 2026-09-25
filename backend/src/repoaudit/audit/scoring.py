"""Shared structure health scoring for audits and history enrichment."""

from __future__ import annotations

from repoaudit.audit.structure_models import FolderViolation

_MAX_DEDUCTION_BY_SEVERITY = {
    "critical": 30,
    "high": 35,
    "medium": 25,
    "low": 10,
}
_PER_VIOLATION = {
    "critical": 20,
    "high": 12,
    "medium": 6,
    "low": 2,
}


def compute_structure_score(violations: list[FolderViolation]) -> tuple[int, bool]:
    """Compute health score with per-severity caps (avoids always-0 flood)."""
    by_sev = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for v in violations:
        sev = v.severity if v.severity in by_sev else "medium"
        by_sev[sev] += 1

    deduction = 0
    for sev, count in by_sev.items():
        if count <= 0:
            continue
        raw = count * _PER_VIOLATION[sev]
        deduction += min(raw, _MAX_DEDUCTION_BY_SEVERITY[sev])

    score = max(0, min(100, 100 - deduction))
    is_valid = by_sev["critical"] == 0 and by_sev["high"] == 0
    return score, is_valid


def violations_from_audit_payload(audit: dict | None) -> list[FolderViolation]:
    """Rebuild violation list from persisted structure_audit JSON."""
    if not audit or not isinstance(audit, dict):
        return []
    violations: list[FolderViolation] = []
    for key in ("static_violations", "unstructured_areas"):
        for item in audit.get(key) or []:
            if not isinstance(item, dict):
                continue
            try:
                violations.append(FolderViolation(**item))
            except Exception:
                continue
    return violations
