"""Tests for Version 1 security audit scanners and wiring."""

from __future__ import annotations

import json

import pytest

from app.core.db.repositories.audits import extract_findings
from repoaudit.audit.bandit import parse_bandit_json
from repoaudit.audit.engine import AuditEngine
from repoaudit.audit.findings import SecurityFinding, summarize_security
from repoaudit.audit.gitleaks import parse_gitleaks_json
from repoaudit.audit.osv import parse_osv_json
from repoaudit.audit.security import SecurityEngine, _parse_explanation_json
from repoaudit.audit.semgrep import parse_semgrep_json
from repoaudit.indexing.graph.graph import DependencyGraph
from repoaudit.indexing.models import FileInfo, ProjectContext, WikiData
from repoaudit.indexing.wiki.builder import WikiBuilder


def _project(tmp_path) -> ProjectContext:
    sample = tmp_path / "app.py"
    sample.write_text("print('ok')\n", encoding="utf-8")
    return ProjectContext(
        name="SecApp",
        root=str(tmp_path),
        files=[FileInfo(path="app.py", size=12, language="python")],
    )


def test_gitleaks_parser_redacts_secret_values():
    raw = json.dumps(
        [
            {
                "Description": "AWS Access Key",
                "StartLine": 42,
                "File": "config.py",
                "RuleID": "aws-access-key",
                "Secret": "AKIASECRETVALUE",
                "Match": "AKIASECRETVALUE",
            }
        ]
    )
    findings = parse_gitleaks_json(raw)
    assert len(findings) == 1
    dumped = findings[0].model_dump_json()
    assert "AKIASECRETVALUE" not in dumped
    assert findings[0].category == "secret"
    assert findings[0].severity == "critical"
    assert findings[0].path == "config.py"
    assert findings[0].line == 42
    assert findings[0].scanner == "gitleaks"


def test_osv_parser_maps_cve_and_severity():
    raw = json.dumps(
        {
            "results": [
                {
                    "source": {"path": "requirements.txt", "type": "lockfile"},
                    "packages": [
                        {
                            "package": {"name": "fastapi", "version": "0.1.0", "ecosystem": "PyPI"},
                            "vulnerabilities": [
                                {
                                    "id": "GHSA-xxxx-yyyy",
                                    "aliases": ["CVE-2024-1234"],
                                    "summary": "Known vulnerability in FastAPI",
                                    "database_specific": {"severity": "HIGH"},
                                }
                            ],
                        }
                    ],
                }
            ]
        }
    )
    findings = parse_osv_json(raw)
    assert len(findings) == 1
    assert findings[0].category == "vulnerable_dependency"
    assert findings[0].severity == "high"
    assert findings[0].cve_id == "CVE-2024-1234"
    assert findings[0].package_name == "fastapi"
    assert findings[0].path == "requirements.txt"


def test_semgrep_parser_maps_patterns():
    raw = json.dumps(
        {
            "results": [
                {
                    "check_id": "python.lang.security.audit.eval-detected.eval-detected",
                    "path": "users.py",
                    "start": {"line": 124},
                    "extra": {
                        "message": "Detected the use of eval().",
                        "severity": "ERROR",
                    },
                }
            ]
        }
    )
    findings = parse_semgrep_json(raw)
    assert len(findings) == 1
    assert findings[0].category == "dangerous_pattern"
    assert findings[0].severity == "high"
    assert findings[0].path == "users.py"
    assert findings[0].line == 124
    assert findings[0].scanner == "semgrep"


def test_bandit_parser_maps_patterns():
    raw = json.dumps(
        {
            "results": [
                {
                    "filename": "users.py",
                    "line_number": 124,
                    "issue_severity": "HIGH",
                    "issue_text": "Use of exec detected.",
                    "test_id": "B102",
                    "test_name": "exec_used",
                }
            ]
        }
    )
    findings = parse_bandit_json(raw)
    assert len(findings) == 1
    assert findings[0].category == "dangerous_pattern"
    assert findings[0].severity == "high"
    assert findings[0].path == "users.py"
    assert findings[0].line == 124
    assert findings[0].scanner == "bandit"
    assert findings[0].rule_id == "B102"


def test_missing_scanners_do_not_fail_engine(monkeypatch, tmp_path):
    monkeypatch.setattr("repoaudit.audit.tool_runner.resolve_executable", lambda _names: None)
    monkeypatch.setattr(
        "repoaudit.audit.bandit.run_python_module",
        lambda *args, **kwargs: (None, "", "", "bandit is not installed"),
    )
    monkeypatch.setattr(
        "repoaudit.audit.semgrep.run_cli",
        lambda *args, **kwargs: (None, "", "", "semgrep is not installed"),
    )
    engine = SecurityEngine()
    result = engine.run_audit(_project(tmp_path))
    assert result.total_findings == 0
    assert result.security_score == 100
    names = {scanner.name for scanner in result.scanners}
    assert names >= {"gitleaks", "osv-scanner", "bandit", "semgrep"}
    assert all(not scanner.available for scanner in result.scanners)
    assert "partial picture" in result.summary_verdict


@pytest.mark.asyncio
async def test_audit_engine_attaches_security_result(monkeypatch, tmp_path):
    monkeypatch.setattr("repoaudit.audit.tool_runner.resolve_executable", lambda _names: None)
    engine = AuditEngine()
    result = await engine.run_full_audit(_project(tmp_path), llm=None)
    assert result.dead_code_result is not None
    assert result.security_result is not None
    assert result.security_result.total_findings == 0
    assert result.static_violations is not None


def test_extract_findings_includes_security_kinds():
    rows = extract_findings(
        audit_id="a1",
        project_id="p1",
        snapshot_id=None,
        user_id=None,
        branch="main",
        result={
            "static_violations": [],
            "unstructured_areas": [],
            "dead_code_result": {"findings": []},
            "security_result": {
                "findings": [
                    {
                        "category": "secret",
                        "severity": "critical",
                        "path": "config.py",
                        "title": "AWS Access Key",
                        "description": "Potential secret exposed.",
                        "suggestion": "Rotate the key.",
                        "rule_id": "aws-access-key",
                    }
                ]
            },
        },
    )
    kinds = {row["finding_kind"] for row in rows}
    assert "secret" in kinds
    secret = next(row for row in rows if row["finding_kind"] == "secret")
    assert secret["path"] == "config.py"
    assert secret["severity"] == "critical"


def test_wiki_security_page_renders_findings(tmp_path):
    finding = SecurityFinding(
        category="secret",
        severity="critical",
        path="config.py",
        line=42,
        title="AWS Access Key",
        description="Potential secret exposed.",
        suggestion="Rotate the key.",
        scanner="gitleaks",
        rule_id="aws-access-key",
        evidence="Gitleaks rule `aws-access-key` matched at config.py:42.",
    )
    result = summarize_security([finding], [])
    project = _project(tmp_path)
    wiki = WikiBuilder().build(
        project,
        WikiData(security_audit=result),
        DependencyGraph.build_from_project(project),
    )
    page = wiki.get_page("security-audit")
    assert page is not None
    assert "AWS Access Key" in page.content
    assert "config.py" in page.content
    assert "line 42" in page.content
    assert "Needs action now" in page.content
    assert "Exposed secret" in page.content


def test_llm_explanation_parser_reads_fenced_json():
    parsed = _parse_explanation_json(
        '```json\n[{"index": 0, "explanation": "Rotate now.", "suggestion": "Use env vars."}]\n```'
    )
    assert parsed[0]["index"] == 0
    assert "Rotate" in parsed[0]["explanation"]
