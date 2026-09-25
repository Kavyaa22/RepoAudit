"""Tests for scan history enrichment and wiki sidebar serialization."""

from repoaudit.interfaces.api.scan_enrichment import (
    enrich_scan_record,
    is_commit_sha,
    slim_scan_record_for_list,
    summary_has_active_scan,
)
from repoaudit.indexing.wiki.serialization import rebuild_sidebar_from_pages
from repoaudit.indexing.analyzer.module_grouping import (
    build_inventory_module_doc,
    group_files_into_modules,
    is_rich_module_doc,
)
from repoaudit.indexing.models import FileInfo


def test_is_commit_sha():
    assert is_commit_sha("a537723885cdb856675a2523c47c8d2f91feba94")
    assert not is_commit_sha("owner/repo")


def test_enrich_scan_record_masks_sha_and_recomputes_score():
    sha = "a537723885cdb856675a2523c47c8d2f91feba94"
    raw = {
        "id": "abc123",
        "name": sha,
        "score": 0,
        "branch": "main",
        "structure_audit": {
            "static_violations": [
                {
                    "path": "backend/ (outside src/)",
                    "violation_type": "invalid_path_depth",
                    "severity": "medium",
                    "description": "aggregated",
                    "suggestion": "move",
                }
            ],
            "unstructured_areas": [],
        },
    }
    out = enrich_scan_record(raw)
    assert out["name"] == f"Repository ({sha[:7]})"
    assert out["score"] > 0


def test_slim_scan_record_strips_heavy_blobs():
    raw = {
        "id": "p1",
        "project_id": "p1",
        "audit_id": "a1",
        "name": "Repo",
        "score": 90,
        "branch": "main",
        "structure_audit": {"static_violations": []},
        "dead_code_audit": {"findings": []},
        "security_audit": {"findings": []},
        "wiki_summary": {"pages": [{"id": "x", "content": "huge"}]},
        "progress": ["step"],
    }
    out = slim_scan_record_for_list(raw)
    assert "structure_audit" not in out
    assert "dead_code_audit" not in out
    assert "security_audit" not in out
    assert "wiki_summary" not in out
    assert "progress" not in out
    assert out["audit_id"] == "a1"
    assert out["name"] == "Repo"


def test_summary_has_active_scan_requires_known_audit_id():
    assert not summary_has_active_scan({"status": "done", "total_files": 10})
    assert not summary_has_active_scan({"audit_id": "gone"}, known_audit_ids=set())
    assert summary_has_active_scan({"audit_id": "alive"}, known_audit_ids={"alive"})
    assert not summary_has_active_scan({})


def test_rebuild_sidebar_includes_modules():
    pages = [
        {"id": "index", "title": "Overview", "order": 0, "parent_id": None},
        {"id": "modules/backend", "title": "backend", "order": 0, "parent_id": "modules"},
        {"id": "modules/frontend", "title": "frontend", "order": 1, "parent_id": "modules"},
    ]
    sidebar = rebuild_sidebar_from_pages(pages)
    assert sidebar[0]["page_id"] == "index"
    modules = next(item for item in sidebar if item["title"] == "Architecture Domains")
    assert len(modules["children"]) == 2


def test_module_grouping_splits_monorepo():
    files = [
        FileInfo(path="backend/app/modules/audit/run/service.py", size=1),
        FileInfo(path="backend/app/modules/investigation/router.py", size=1),
        FileInfo(path="frontend/src/pages/WikiView.tsx", size=1),
        FileInfo(path="frontend/src/components/Nav.tsx", size=1),
    ]
    groups = group_files_into_modules(files)
    keys = set(groups.keys())
    # Backend .py files should land in Core Business & Services (or API for router)
    assert any("Service" in k or "Business" in k for k in keys)
    # Frontend .tsx files should land in Frontend & UI Presentation
    assert any("Frontend" in k or "UI" in k for k in keys)


def test_inventory_module_doc_is_rich():
    files = [
        FileInfo(path="backend/a.py", size=1, language="python", lines=10),
        FileInfo(path="backend/b.py", size=1, language="python", lines=5),
        FileInfo(path="backend/c.py", size=1, language="python", lines=3),
    ]
    doc = build_inventory_module_doc("backend/app", files)
    assert is_rich_module_doc(doc)
    assert len(doc.files) == 3
