"""Tests for light audit history list mapping."""

from __future__ import annotations

from app.modules.audit.list.service import _map_row


def test_map_row_excludes_heavy_payloads():
    row = {
        "audit_id": "a1",
        "project_id": "p1",
        "branch": "develop",
        "status": "succeeded",
        "overall_score": 88,
        "is_valid": True,
        "created_at": "2026-08-26T00:00:00Z",
        "audit_type": "full_scan",
        "projects": {
            "display_name": "acme/widget",
            "owner": "acme",
            "repository_name": "widget",
            "repository_url": "https://github.com/acme/widget",
        },
        "result": {
            "total_files": 12,
            "total_lines": 400,
            "score": 88,
            "static_violations": [{"path": "x"}],
            "dead_code_result": {"findings": [{"path": "y"}]},
            "security_result": {"findings": [{"path": "z"}]},
            "wiki_summary": {"pages": [{"id": "overview", "content": "big"}]},
        },
    }
    item = _map_row(row)
    assert item.audit_id == "a1"
    assert item.project_id == "p1"
    assert item.name == "acme/widget"
    assert item.branch == "develop"
    assert item.status == "done"
    assert item.overall_score == 88
    assert item.total_files == 12
    assert item.structure_audit is None
    assert item.dead_code_audit is None
    assert item.security_audit is None
    assert item.wiki_summary is None
