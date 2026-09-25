"""Phase 6 golden: x_task-style action folders end-to-end without LLM."""

from __future__ import annotations

import pytest

from repoaudit.audit.engine import AuditEngine
from repoaudit.audit.structure_context import validate_recommended_structure
from repoaudit.audit.structure_scoring import score_structure_style
from repoaudit.audit.structure_style import STRUCTURE_STYLE_ACTION_API
from repoaudit.indexing.models import FileInfo, ProjectContext


def _xtask_monorepo() -> list[FileInfo]:
    return [
        FileInfo(path="backend/src/index.ts", size=20, content="import './routes/taskRoutes'"),
        FileInfo(
            path="backend/src/routes/taskRoutes.ts",
            size=40,
            content="import { createTask } from '../services/createTask'\nexport {}",
        ),
        FileInfo(
            path="backend/src/services/createTask.ts",
            size=40,
            content="export function createTask() { return 1 }",
        ),
        FileInfo(
            path="backend/src/schemas/taskSchema.ts",
            size=40,
            content="export const taskSchema = {}",
        ),
        FileInfo(
            path="frontend/src/main.tsx",
            size=20,
            content="import { CreateTaskPage } from './pages/CreateTaskPage'",
        ),
        FileInfo(
            path="frontend/src/pages/CreateTaskPage.tsx",
            size=40,
            content="export function CreateTaskPage() { return null }",
        ),
        FileInfo(
            path="frontend/src/hooks/useCreateTask.ts",
            size=40,
            content="export function useCreateTask() {}",
        ),
        FileInfo(path="docs/API.md", size=20, content="# API"),
        FileInfo(path="templates-src/sim/index.html", size=20, content="<html></html>"),
        FileInfo(path="scripts/extract_template/prep.mjs", size=20, content=""),
        FileInfo(path="backend/package.json", size=20, content='{"dependencies":{"express":"4"}}'),
        FileInfo(
            path="frontend/package.json",
            size=20,
            content='{"dependencies":{"react":"18"},"devDependencies":{"vite":"5"}}',
        ),
        FileInfo(path="frontend/vite.config.ts", size=20, content="export default {}"),
    ]


@pytest.mark.asyncio
async def test_golden_xtask_action_api_audit():
    project = ProjectContext(name="XTaskGold", root="/tmp/xtask", files=_xtask_monorepo())
    result = await AuditEngine().run_structure_audit(
        project, llm=None, structure_style=STRUCTURE_STYLE_ACTION_API
    )

    assert result.structure_style == "action_api"
    assert result.current_structure and "Current structure" in result.current_structure
    assert result.recommended_structure
    assert "multipass" in result.recommended_structure or "action_api" in result.recommended_structure

    # Move map covers consolidation + action grouping
    tos = [m.to_path for m in result.structure_changes]
    assert any(t.startswith("backend/docs/") for t in tos)
    assert any("/task/" in t and ("/create/" in t or "/shared/" in t) for t in tos)
    assert any(t.startswith("frontend/src/task/") for t in tos)

    issues = validate_recommended_structure(
        result.recommended_structure,
        inventory_paths={f.path for f in project.files},
        structure_style=STRUCTURE_STYLE_ACTION_API,
    )
    assert issues == [], issues

    style_score, gaps = score_structure_style(
        result.recommended_structure, STRUCTURE_STYLE_ACTION_API
    )
    assert result.style_score == style_score
    assert style_score >= 55, f"style_score={style_score} gaps={gaps}"


@pytest.mark.asyncio
async def test_golden_sim_like_consolidation():
    """docs + templates-src fold under product roots in the move map."""
    files = _xtask_monorepo()
    project = ProjectContext(name="SIMLike", root="/tmp/sim", files=files)
    result = await AuditEngine().run_structure_audit(project, llm=None)
    by_src = {m.from_path: m.to_path for m in result.structure_changes}
    assert by_src.get("docs/API.md") == "backend/docs/API.md"
    assert by_src["templates-src/sim/index.html"].startswith("frontend/src/templates/")
