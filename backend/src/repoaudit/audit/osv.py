"""OSV-Scanner wrapper — known vulnerable dependencies."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from repoaudit.audit.findings import ScannerStatus, SecurityFinding, normalize_severity
from repoaudit.audit.tool_runner import run_cli

logger = logging.getLogger(__name__)

SCANNER_NAME = "osv-scanner"


def _package_info(pkg: dict) -> tuple[str, str]:
    info = pkg.get("package") if isinstance(pkg.get("package"), dict) else pkg
    name = str(info.get("name") or info.get("Name") or "")
    version = str(info.get("version") or info.get("Version") or "")
    return name, version


def _vuln_severity(vuln: dict) -> str:
    db = vuln.get("database_specific") if isinstance(vuln.get("database_specific"), dict) else {}
    if db.get("severity"):
        return str(db["severity"])
    for item in vuln.get("severity") or []:
        if isinstance(item, dict) and item.get("score"):
            return str(item["score"])
        if isinstance(item, str):
            return item
    return "medium"


def parse_osv_json(raw: str) -> list[SecurityFinding]:
    """Map OSV-Scanner JSON (v1/v2) to security findings."""
    if not raw or not raw.strip():
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        # OSV may print logs before JSON; try the last object/array.
        start = raw.find("{")
        if start < 0:
            start = raw.find("[")
        if start < 0:
            logger.warning("OSV-Scanner returned non-JSON output")
            return []
        try:
            payload = json.loads(raw[start:])
        except json.JSONDecodeError:
            logger.warning("OSV-Scanner returned non-JSON output")
            return []

    if isinstance(payload, dict):
        results = payload.get("results") or []
    elif isinstance(payload, list):
        results = payload
    else:
        return []

    findings: list[SecurityFinding] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        source = result.get("source") if isinstance(result.get("source"), dict) else {}
        source_path = str(source.get("path") or source.get("Path") or "").replace("\\", "/")
        packages = result.get("packages") or result.get("package_vulnerabilities") or []
        for pkg in packages:
            if not isinstance(pkg, dict):
                continue
            name, version = _package_info(pkg)
            vulns = pkg.get("vulnerabilities") or pkg.get("vulns") or []
            for vuln in vulns:
                if not isinstance(vuln, dict):
                    continue
                cve_id = str(vuln.get("id") or vuln.get("aliases") or "OSV")
                if isinstance(vuln.get("aliases"), list) and vuln["aliases"]:
                    aliases = [str(a) for a in vuln["aliases"] if str(a).startswith("CVE-")]
                    if aliases:
                        cve_id = aliases[0]
                summary = str(vuln.get("summary") or vuln.get("details") or "Known vulnerability")
                summary = summary.splitlines()[0][:240]
                pkg_label = f"{name} {version}".strip() or "dependency"
                title = f"{pkg_label} — {cve_id}"
                findings.append(
                    SecurityFinding(
                        category="vulnerable_dependency",
                        severity=normalize_severity(_vuln_severity(vuln)),
                        path=source_path or "dependencies",
                        line=0,
                        title=title,
                        description=f"{pkg_label} has a known vulnerability ({cve_id}): {summary}",
                        suggestion=f"Upgrade `{name}` from {version or 'the current version'} to a patched release.",
                        scanner=SCANNER_NAME,
                        rule_id=str(vuln.get("id") or cve_id),
                        evidence=f"OSV match in `{source_path or 'lockfile'}` for `{pkg_label}`.",
                        package_name=name,
                        package_version=version,
                        cve_id=cve_id,
                    )
                )
    return findings


def scan_osv(root: str | Path) -> tuple[list[SecurityFinding], ScannerStatus]:
    """Run OSV-Scanner against lockfiles/manifests. Fail-soft if missing."""
    root_path = Path(root)
    status = ScannerStatus(name=SCANNER_NAME, available=True)

    attempts = [
        ["scan", "--format", "json", "--recursive", str(root_path)],
        ["--format", "json", "-r", str(root_path)],
    ]
    last_skip = f"{SCANNER_NAME} is not installed"
    for args in attempts:
        _code, stdout, _stderr, skip = run_cli(
            ["osv-scanner", "osv-scanner.exe"],
            args,
            cwd=root_path,
            timeout=120,
        )
        if skip and "is not installed" in skip:
            last_skip = skip
            break
        if skip:
            last_skip = skip
            continue
        findings = parse_osv_json(stdout)
        status.finding_count = len(findings)
        return findings, status

    status.available = False
    status.skip_reason = last_skip
    return [], status
