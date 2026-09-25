"""Phase 3 tests: multipass topology → backend/frontend → merge."""

from __future__ import annotations

import pytest

from repoaudit.audit.engine import AuditEngine
from repoaudit.audit.structure_context import validate_recommended_structure
from repoaudit.audit.structure_multipass import (
    build_multipass_deterministic,
    build_topology,
    merge_product_trees,
)
from repoaudit.audit.structure_style import STRUCTURE_STYLE_ACTION_API
from repoaudit.indexing.models import FileInfo, ProjectContext


def _files() -> list[FileInfo]:
    return [
        FileInfo(path="backend/src/services/createTask.ts", size=40),
        FileInfo(path="backend/src/index.ts", size=20),
        FileInfo(path="frontend/src/pages/CreateTaskPage.tsx", size=40),
        FileInfo(path="frontend/src/main.tsx", size=20),
        FileInfo(path="docs/API.md", size=20),
        FileInfo(path="templates-src/a/index.html", size=20),
    ]


def test_topology_detects_features_and_consolidations():
    project = ProjectContext(name="MP", root="/tmp", files=_files())
    topo = build_topology(project)
    assert "backend_paths" in topo and topo["backend_paths"]
    assert "frontend_paths" in topo and topo["frontend_paths"]
    assert "catalog" in topo and topo["catalog"]
    assert any(c["from"].startswith("docs/") for c in topo["consolidations"])
    assert any("template" in c["to"] for c in topo["consolidations"])


def test_merge_product_trees_contains_both_roots():
    tree = merge_product_trees(
        ["backend/src/task/create/createTask.ts"],
        ["frontend/src/task/create/CreateTaskPage.tsx"],
    )
    assert "backend/" in tree
    assert "frontend/" in tree
    assert "multipass" in tree
    assert "createTask.ts" in tree


def test_deterministic_multipass_validates():
    project = ProjectContext(name="MP", root="/tmp", files=_files())
    topo, tree = build_multipass_deterministic(project)
    assert topo["backend_paths"]
    assert "quality" in topo
    issues = validate_recommended_structure(
        tree,
        inventory_paths={f.path for f in project.files},
        structure_style=STRUCTURE_STYLE_ACTION_API,
    )
    assert issues == [], issues
    assert "multipass" in tree
    assert "Structure quality gate" in tree


@pytest.mark.asyncio
async def test_engine_uses_multipass_for_action_api():
    project = ProjectContext(name="MP", root="/tmp", files=_files())
    result = await AuditEngine().run_structure_audit(
        project, llm=None, structure_style=STRUCTURE_STYLE_ACTION_API
    )
    assert "multipass" in result.recommended_structure
    assert result.current_structure
    assert any(m.to_path.startswith("backend/docs/") for m in result.structure_changes)
    assert result.features_identified
