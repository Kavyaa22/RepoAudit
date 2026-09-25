"""Semgrep integration — dangerous code patterns (default rules only)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from repoaudit.audit.findings import ScannerStatus, SecurityFinding, normalize_severity
from repoaudit.audit.tool_runner import run_cli
from repoaudit.investigation.evidence import redact_sensitive_text

logger = logging.getLogger(__name__)

SCANNER_NAME = "semgrep"


def parse_semgrep_json(raw: str) -> list[SecurityFinding]:
    """Map Semgrep JSON results to security findings."""
    if not raw or not raw.strip():
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        if start < 0:
            logger.warning("Semgrep returned non-JSON output")
            return []
        try:
            payload = json.loads(raw[start:])
        except json.JSONDecodeError:
            logger.warning("Semgrep returned non-JSON output")
            return []

    rows = payload.get("results") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []

    findings: list[SecurityFinding] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
        start = row.get("start") if isinstance(row.get("start"), dict) else {}
        path = str(row.get("path") or extra.get("path") or "").replace("\\", "/")
        if not path:
            continue
        line = int(start.get("line") or extra.get("line") or 0)
        rule_id = str(row.get("check_id") or extra.get("fingerprint") or "semgrep")
        message = str(extra.get("message") or row.get("message") or rule_id)
        message = redact_sensitive_text(message.splitlines()[0][:280])
        severity = normalize_severity(str(extra.get("severity") or row.get("severity") or "warning"))
        location = f"{path}:{line}" if line else path
        suggestion = str(extra.get("fix") or "").strip()
        if not suggestion:
            suggestion = f"Review and replace the unsafe pattern flagged by `{rule_id}`."
        findings.append(
            SecurityFinding(
                category="dangerous_pattern",
                severity=severity if severity != "critical" else "high",
                path=path,
                line=line,
                title=rule_id.split(".")[-1].replace("-", " ").replace("_", " "),
                description=f"{message} ({location})",
                suggestion=suggestion,
                scanner=SCANNER_NAME,
                rule_id=rule_id,
                evidence=redact_sensitive_text(f"Semgrep `{rule_id}` at {location}."),
            )
        )
    return findings


def scan_semgrep(root: str | Path) -> tuple[list[SecurityFinding], ScannerStatus]:
    """Run Semgrep with the public security-audit ruleset. Fail-soft if missing."""
    root_path = Path(root)
    status = ScannerStatus(name=SCANNER_NAME, available=True)

    args_sets = [
        [
            "scan",
            "--config",
            "p/security-audit",
            "--json",
            "--quiet",
            "--metrics",
            "off",
            "--disable-version-check",
            str(root_path),
        ],
        [
            "--config",
            "p/security-audit",
            "--json",
            "--quiet",
            "--metrics",
            "off",
            str(root_path),
        ],
    ]
    last_skip = f"{SCANNER_NAME} is not installed"
    for args in args_sets:
        _code, stdout, _stderr, skip = run_cli(
            ["semgrep", "semgrep.exe"],
            args,
            cwd=root_path,
            timeout=180,
        )
        if skip and "is not installed" in skip:
            last_skip = skip
            break
        if skip:
            last_skip = skip
            continue
        findings = parse_semgrep_json(stdout)
        status.finding_count = len(findings)
        return findings, status

    status.available = False
    status.skip_reason = last_skip
    return [], status
