"""Bandit wrapper — Python dangerous-code patterns (Railway-friendly, pip install)."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from repoaudit.audit.findings import ScannerStatus, SecurityFinding, normalize_severity
from repoaudit.audit.tool_runner import run_cli, run_python_module
from repoaudit.investigation.evidence import redact_sensitive_text

logger = logging.getLogger(__name__)

SCANNER_NAME = "bandit"

_EXCLUDE = ",".join(
    [
        "./node_modules",
        "./.venv",
        "./venv",
        "./env",
        "./dist",
        "./build",
        "./.git",
        "./.next",
        "./__pycache__",
    ]
)

_BANDIT_ARGS = [
    "-r",
    ".",
    "-f",
    "json",
    "-q",
    "-ll",
    "-x",
    _EXCLUDE,
]


def parse_bandit_json(raw: str) -> list[SecurityFinding]:
    """Map Bandit JSON results to security findings."""
    if not raw or not raw.strip():
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        if start < 0:
            logger.warning("Bandit returned non-JSON output")
            return []
        try:
            payload = json.loads(raw[start:])
        except json.JSONDecodeError:
            logger.warning("Bandit returned non-JSON output")
            return []

    rows = payload.get("results") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []

    findings: list[SecurityFinding] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        path = str(row.get("filename") or row.get("path") or "").replace("\\", "/")
        if not path:
            continue
        line = int(row.get("line_number") or row.get("line") or 0)
        rule_id = str(row.get("test_id") or row.get("test_name") or "bandit")
        title = str(row.get("test_name") or rule_id).replace("_", " ")
        message = redact_sensitive_text(str(row.get("issue_text") or title).splitlines()[0][:280])
        severity = normalize_severity(str(row.get("issue_severity") or "medium"))
        location = f"{path}:{line}" if line else path
        findings.append(
            SecurityFinding(
                category="dangerous_pattern",
                severity=severity if severity != "critical" else "high",
                path=path,
                line=line,
                title=title,
                description=f"{message} ({location})",
                suggestion=f"Review and replace the unsafe pattern flagged by Bandit `{rule_id}`.",
                scanner=SCANNER_NAME,
                rule_id=rule_id,
                evidence=redact_sensitive_text(f"Bandit `{rule_id}` at {location}."),
            )
        )
    return findings


def scan_bandit(root: str | Path) -> tuple[list[SecurityFinding], ScannerStatus]:
    """Run Bandit on Python sources. Uses `python -m bandit` so the venv install is enough."""
    root_path = Path(root)
    status = ScannerStatus(name=SCANNER_NAME, available=True)
    last_skip = "bandit is not installed"

    attempts = [
        lambda: run_cli(["bandit", "bandit.exe"], _BANDIT_ARGS, cwd=root_path, timeout=90),
        lambda: run_python_module("bandit", _BANDIT_ARGS, cwd=root_path, timeout=90),
        lambda: run_python_module("bandit.__main__", _BANDIT_ARGS, cwd=root_path, timeout=90),
    ]
    for attempt in attempts:
        _code, stdout, stderr, skip = attempt()
        if _missing_bandit(stdout, stderr, skip):
            last_skip = "bandit is not installed"
            continue
        if skip:
            last_skip = skip
            continue
        findings = parse_bandit_json(stdout)
        status.finding_count = len(findings)
        logger.debug("bandit via %s", sys.executable)
        return findings, status

    status.available = False
    status.skip_reason = last_skip
    return [], status


def _missing_bandit(stdout: str, stderr: str, skip: str | None) -> bool:
    blob = f"{skip or ''}\n{stdout}\n{stderr}"
    return "No module named" in blob
