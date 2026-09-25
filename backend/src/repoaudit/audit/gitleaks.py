"""Gitleaks wrapper — secrets and credential exposure."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

from repoaudit.audit.findings import ScannerStatus, SecurityFinding, normalize_severity
from repoaudit.audit.tool_runner import run_cli
from repoaudit.investigation.evidence import redact_sensitive_text

logger = logging.getLogger(__name__)

SCANNER_NAME = "gitleaks"


def parse_gitleaks_json(raw: str) -> list[SecurityFinding]:
    """Map Gitleaks JSON (array or object) to security findings. Secret values are never stored."""
    if not raw or not raw.strip():
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Gitleaks returned non-JSON output")
        return []

    if isinstance(payload, dict):
        rows = payload.get("leaks") or payload.get("Findings") or payload.get("findings") or []
    elif isinstance(payload, list):
        rows = payload
    else:
        return []

    findings: list[SecurityFinding] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        path = str(row.get("File") or row.get("file") or row.get("Path") or "").replace("\\", "/")
        if not path:
            continue
        line = int(row.get("StartLine") or row.get("start_line") or row.get("Line") or 0)
        rule_id = str(row.get("RuleID") or row.get("rule_id") or row.get("Rule") or "secret")
        title = str(row.get("Description") or row.get("description") or rule_id)
        location = f"{path}:{line}" if line else path
        findings.append(
            SecurityFinding(
                category="secret",
                severity=normalize_severity(row.get("Severity") or "critical")
                if row.get("Severity")
                else "critical",
                path=path,
                line=line,
                title=title,
                description=f"Potential secret ({rule_id}) exposed at {location}.",
                suggestion=(
                    "Remove the credential from source control, rotate it, "
                    "and load it from environment variables or a secret manager."
                ),
                scanner=SCANNER_NAME,
                rule_id=rule_id,
                evidence=redact_sensitive_text(f"Gitleaks rule `{rule_id}` matched at {location}."),
            )
        )
    return findings


def scan_gitleaks(root: str | Path) -> tuple[list[SecurityFinding], ScannerStatus]:
    """Run Gitleaks against a snapshot. Fail-soft if the binary is missing."""
    root_path = Path(root)
    status = ScannerStatus(name=SCANNER_NAME, available=True)
    with tempfile.TemporaryDirectory(prefix="repoaudit-gitleaks-") as tmp:
        report_path = Path(tmp) / "gitleaks.json"
        _code, stdout, stderr, skip = run_cli(
            ["gitleaks"],
            [
                "detect",
                "--source",
                str(root_path),
                "--no-git",
                "--report-format",
                "json",
                "--report-path",
                str(report_path),
                "--no-banner",
            ],
            cwd=root_path,
            timeout=90,
        )
        if skip:
            status.available = False
            status.skip_reason = skip
            return [], status

        raw = ""
        if report_path.is_file():
            raw = report_path.read_text(encoding="utf-8", errors="replace")
        if not raw.strip():
            raw = stdout or stderr
        findings = parse_gitleaks_json(raw)
        status.finding_count = len(findings)
        return findings, status
