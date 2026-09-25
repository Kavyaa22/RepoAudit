"""Security audit engine: deterministic scanners first, optional LLM explanation last."""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from repoaudit.audit.findings import (
    ScannerStatus,
    SecurityAuditResult,
    SecurityFinding,
    summarize_security,
)
from repoaudit.audit.bandit import scan_bandit
from repoaudit.audit.gitleaks import scan_gitleaks
from repoaudit.audit.osv import scan_osv
from repoaudit.audit.semgrep import scan_semgrep
from repoaudit.investigation.evidence import redact_sensitive_text

if TYPE_CHECKING:
    from repoaudit.indexing.llm.client import LLMClient
    from repoaudit.indexing.models import ProjectContext

logger = logging.getLogger(__name__)

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\[.*?\])\s*```", re.DOTALL)


class SecurityEngine:
    """Runs V1 scanners and normalizes their output into one security result."""

    def run_audit(self, project: ProjectContext) -> SecurityAuditResult:
        """Execute Gitleaks, OSV-Scanner, Bandit; Semgrep if installed. Never raises."""
        logger.info("Executing security scanners (secrets, dependencies, patterns)...")
        findings: list[SecurityFinding] = []
        scanners: list[ScannerStatus] = []
        root = project.root

        for scanner_fn in (scan_gitleaks, scan_osv, scan_bandit, scan_semgrep):
            try:
                scanner_findings, status = scanner_fn(root)
            except Exception as exc:  # noqa: BLE001
                name = getattr(scanner_fn, "__name__", "scanner").replace("scan_", "")
                logger.warning("Security scanner %s crashed: %s", name, exc)
                scanner_findings = []
                status = ScannerStatus(name=name, available=False, skip_reason=str(exc)[:180])
            findings.extend(scanner_findings)
            scanners.append(status)
            if status.available:
                logger.info("%s: %s finding(s)", status.name, len(scanner_findings))
            else:
                logger.info("%s skipped: %s", status.name, status.skip_reason)

        return summarize_security(findings, scanners)

    async def explain_findings(
        self,
        result: SecurityAuditResult,
        llm: LLMClient | None,
    ) -> SecurityAuditResult:
        """Optionally add short remediation text. Never adds new findings."""
        if llm is None or not result.findings:
            return result
        top = result.findings[:8]
        payload = [
            {
                "index": index,
                "category": item.category,
                "severity": item.severity,
                "path": item.path,
                "line": item.line,
                "title": item.title,
                "description": redact_sensitive_text(item.description),
                "evidence": redact_sensitive_text(item.evidence),
            }
            for index, item in enumerate(top)
        ]
        messages = [
            {
                "role": "system",
                "content": (
                    "You explain existing security findings for a non-technical manager. "
                    "Do not invent new findings. Do not repeat secret values. "
                    "Do not mention scanner names, rule IDs, CVEs, or code jargon. "
                    "Write explanation as: what this means in business terms and why it matters. "
                    "Write suggestion as a clear next step a manager can assign. "
                    "Return JSON only: an array of "
                    '{"index": number, "explanation": string, "suggestion": string}.'
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"findings": payload}, ensure_ascii=False),
            },
        ]
        try:
            text = await llm.complete(
                messages,
                operation="security_audit",
                temperature=0.1,
                max_tokens=1200,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Security LLM explanation skipped: %s", exc)
            return result

        updates = _parse_explanation_json(text)
        if not updates:
            return result

        for item in updates:
            try:
                index = int(item.get("index"))
            except (TypeError, ValueError):
                continue
            if index < 0 or index >= len(top):
                continue
            explanation = redact_sensitive_text(str(item.get("explanation") or "").strip())
            suggestion = redact_sensitive_text(str(item.get("suggestion") or "").strip())
            finding = top[index]
            if explanation:
                finding.description = f"{finding.description} {explanation}".strip()
            if suggestion:
                finding.suggestion = suggestion
        return result


def _parse_explanation_json(text: str) -> list[dict]:
    raw = (text or "").strip()
    if not raw:
        return []
    fenced = _JSON_FENCE.search(raw)
    if fenced:
        raw = fenced.group(1)
    start = raw.find("[")
    end = raw.rfind("]")
    if start < 0 or end < start:
        return []
    try:
        parsed = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return []
    return [row for row in parsed if isinstance(row, dict)]
