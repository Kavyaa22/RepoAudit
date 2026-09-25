"""Normalized security audit findings shared by all V1 scanners."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from repoaudit.audit.plain_language import security_verdict

SecurityCategory = Literal["secret", "vulnerable_dependency", "dangerous_pattern"]
SecuritySeverity = Literal["critical", "high", "medium", "low"]


class SecurityFinding(BaseModel):
    """A single deterministic security finding with file-level evidence."""

    category: SecurityCategory
    severity: SecuritySeverity = "medium"
    path: str
    line: int = 0
    title: str
    description: str
    suggestion: str = ""
    scanner: str
    rule_id: str = ""
    evidence: str = ""
    package_name: str = ""
    package_version: str = ""
    cve_id: str = ""


class ScannerStatus(BaseModel):
    """Whether a scanner ran, was skipped, or failed."""

    name: str
    available: bool = True
    skip_reason: str = ""
    finding_count: int = 0


class SecurityAuditResult(BaseModel):
    """Consolidated output of secrets, dependency, and pattern scanners."""

    total_findings: int = 0
    security_score: int = 100
    summary_verdict: str = "No security issues were found in this review."
    findings: list[SecurityFinding] = Field(default_factory=list)
    counts_by_severity: dict[str, int] = Field(default_factory=dict)
    counts_by_category: dict[str, int] = Field(default_factory=dict)
    scanners: list[ScannerStatus] = Field(default_factory=list)


_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_SCORE_WEIGHTS = {"critical": 25, "high": 12, "medium": 6, "low": 2}


def normalize_severity(value: str | None) -> SecuritySeverity:
    """Map scanner-specific severity labels onto RepoAudit severities."""
    raw = (value or "").strip().lower()
    if raw in {"critical", "crit", "very high"}:
        return "critical"
    if raw in {"high", "error", "severe"}:
        return "high"
    if raw in {"medium", "moderate", "warning", "warn"}:
        return "medium"
    if raw in {"low", "info", "note", "informational"}:
        return "low"
    if raw.startswith("cvss"):
        return _severity_from_cvss(raw)
    return "medium"


def _severity_from_cvss(raw: str) -> SecuritySeverity:
    digits = "".join(ch if ch.isdigit() or ch == "." else " " for ch in raw)
    parts = [p for p in digits.split() if p]
    try:
        score = float(parts[-1]) if parts else 0.0
    except ValueError:
        return "medium"
    if score >= 9.0:
        return "critical"
    if score >= 7.0:
        return "high"
    if score >= 4.0:
        return "medium"
    return "low"


def compute_security_score(findings: list[SecurityFinding]) -> int:
    score = 100
    for finding in findings:
        score -= _SCORE_WEIGHTS.get(finding.severity, 6)
    return max(0, min(100, score))


def finding_fingerprint(finding: SecurityFinding) -> tuple[str, str, int, str]:
    return (finding.category, finding.path.replace("\\", "/"), finding.line, finding.rule_id or finding.title)


def merge_findings(findings: list[SecurityFinding]) -> list[SecurityFinding]:
    seen: set[tuple[str, str, int, str]] = set()
    merged: list[SecurityFinding] = []
    for finding in findings:
        key = finding_fingerprint(finding)
        if key in seen:
            continue
        seen.add(key)
        merged.append(finding)
    merged.sort(key=lambda item: (_SEVERITY_RANK.get(item.severity, 9), item.path, item.line, item.title))
    return merged


def summarize_security(findings: list[SecurityFinding], scanners: list[ScannerStatus]) -> SecurityAuditResult:
    findings = merge_findings(findings)
    counts_by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    counts_by_category = {"secret": 0, "vulnerable_dependency": 0, "dangerous_pattern": 0}
    for finding in findings:
        counts_by_severity[finding.severity] = counts_by_severity.get(finding.severity, 0) + 1
        counts_by_category[finding.category] = counts_by_category.get(finding.category, 0) + 1

    skipped = [s.name for s in scanners if not s.available]
    score = compute_security_score(findings)
    verdict = security_verdict(
        len(findings),
        counts_by_severity["critical"],
        counts_by_severity["high"],
        skipped,
    )

    for scanner in scanners:
        scanner.finding_count = sum(1 for item in findings if item.scanner == scanner.name)

    return SecurityAuditResult(
        total_findings=len(findings),
        security_score=score,
        summary_verdict=verdict,
        findings=findings,
        counts_by_severity=counts_by_severity,
        counts_by_category=counts_by_category,
        scanners=scanners,
    )
