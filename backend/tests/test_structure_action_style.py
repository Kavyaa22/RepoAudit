"""Phase 2 tests: action_api feature → action → files mapping."""

from __future__ import annotations

import pytest

from repoaudit.audit.engine import AuditEngine
from repoaudit.audit.structure_action_style import (
    infer_feature_action,
    suggest_action_api_path,
)
from repoaudit.audit.structure_context import validate_recommended_structure
from repoaudit.audit.structure_style import STRUCTURE_STYLE_ACTION_API
from repoaudit.audit.structure_target import build_structure_changes, build_whole_repo_structure
from repoaudit.indexing.models import FileInfo, ProjectContext


def _x_task_files() -> list[FileInfo]:
    return [
        FileInfo(path="backend/src/services/createTask.ts", size=40, content="export function createTask() {}"),
        FileInfo(path="backend/src/routes/taskRoutes.ts", size=40, content="import { createTask } from '../services/createTask'"),
        FileInfo(path="backend/src/schemas/taskSchema.ts", size=40, content="export const taskSchema = {}"),
        FileInfo(path="frontend/src/pages/CreateTaskPage.tsx", size=40, content="export default function CreateTaskPage() { return null }"),
        FileInfo(path="frontend/src/hooks/useCreateTask.ts", size=40, content="export function useCreateTask() {}"),
        FileInfo(path="docs/API.md", size=20, content="# API"),
        FileInfo(path="templates-src/sim-final/index.html", size=20, content="<html></html>"),
        FileInfo(path="backend/package.json", size=20, content='{"dependencies":{"express":"4.0.0"}}'),
        FileInfo(path="frontend/package.json", size=20, content='{"dependencies":{"react":"18.0.0"},"devDependencies":{"vite":"5.0.0"}}'),
        FileInfo(path="frontend/vite.config.ts", size=20, content="export default {}"),
        FileInfo(path="backend/src/index.ts", size=20, content="console.log('hi')"),
        FileInfo(path="frontend/src/main.tsx", size=20, content="import './App'"),
    ]


def test_infer_feature_action_from_create_task():
    fa = infer_feature_action("backend/src/services/createTask.ts")
    assert fa.action == "create"
    assert "task" in fa.feature


def test_infer_avoids_duplicate_feature_action():
    fa = infer_feature_action("backend/src/routes/taskRoutes.ts")
    assert fa.feature == "task"
    assert fa.action != "task"
    assert fa.action == "core"


def test_infer_hook_strips_use_prefix():
    fa = infer_feature_action("frontend/src/hooks/useCreateTask.ts")
    assert fa.feature == "task"
    assert fa.action == "create"


def test_infer_login_page_as_auth():
    fa = infer_feature_action("frontend/src/pages/LoginPage.tsx")
    assert fa.feature == "auth"
    assert fa.action == "login"


def test_infer_path_action_folder():
    fa = infer_feature_action("backend/app/modules/audit/run/service.py")
    assert fa.feature == "audit"
    assert fa.action == "run"


def test_critique_thank_you_not_split():
    fa = infer_feature_action("frontend/src/pages/ThankYouPage.tsx")
    assert fa.feature == "proposals"
    assert fa.action == "public"
    dest = suggest_action_api_path("frontend/src/pages/ThankYouPage.tsx")
    assert "thank/you" not in dest
    assert dest == "frontend/src/proposals/public/ThankYouPage.tsx"


def test_critique_measure_in_not_split():
    fa = infer_feature_action("frontend/src/hooks/useMeasureInView.ts")
    assert fa.feature == "shared"
    assert fa.action == "lib"
    dest = suggest_action_api_path("frontend/src/MeasureInView.tsx")
    assert "measure/in" not in dest


def test_critique_highridge_under_templates():
    fa = infer_feature_action("frontend/src/templates/HighRidgeV4.tsx")
    assert fa.feature == "templates"
    assert fa.action == "high_ridge_v4"


def test_critique_relative_time_is_utility():
    fa = infer_feature_action("frontend/src/lib/relativeTime.ts")
    assert fa.feature == "shared"
    assert fa.action == "lib"
    dest = suggest_action_api_path("frontend/src/lib/relativeTime.ts")
    assert "relative/time" not in dest


def test_critique_peg_viewport_is_utility():
    fa = infer_feature_action("frontend/src/PegViewport.tsx")
    assert fa.feature == "shared"
    assert fa.action == "lib"


def test_critique_ink_copper_css_not_type_folder():
    dest = suggest_action_api_path("frontend/src/ink_copper_exact_css/theme.css")
    assert "ink_copper_exact_css" not in dest
    assert "/templates/" in dest
    assert dest.endswith("theme.css")


def test_auth_and_authentication_collapse():
    a = infer_feature_action("frontend/src/auth/login/LoginPage.tsx")
    b = infer_feature_action("frontend/src/authentication/login/LoginPage.tsx")
    assert a.feature == b.feature == "auth"


def test_suggest_action_api_path_groups_create_task():
    dest = suggest_action_api_path("backend/src/services/createTask.ts")
    assert dest == "backend/src/task/create/createTask.ts"


def test_suggest_frontend_feature_action():
    dest = suggest_action_api_path("frontend/src/hooks/useCreateTask.ts")
    assert dest == "frontend/src/task/create/useCreateTask.ts"


def test_suggest_keeps_product_root_config():
    assert suggest_action_api_path("backend/.env.example") == "backend/.env.example"
    assert suggest_action_api_path("frontend/.env.example") == "frontend/.env.example"
    assert suggest_action_api_path("backend/.gitignore") == "backend/.gitignore"
    assert suggest_action_api_path("frontend/.gitignore") == "frontend/.gitignore"
    assert suggest_action_api_path("backend/package.json") == "backend/package.json"
    # Never bury config under a feature folder
    assert suggest_action_api_path("frontend/src/auth/.env.example") == "frontend/.env.example"


def test_action_api_tree_uses_feature_action_folders():
    project = ProjectContext(name="XTask", root="/tmp/xtask", files=_x_task_files())
    tree = build_whole_repo_structure(
        project, "express_vite_monorepo", structure_style=STRUCTURE_STYLE_ACTION_API
    )
    assert "action_api" in tree or "Feature → Action" in tree or "task/" in tree
    assert "backend/src/task/" in tree or "task/create" in tree
    assert "frontend/src/task/" in tree or "task/create" in tree
    assert "backend/docs/" in tree
    assert "templates/" in tree or "template" in tree.lower()
    issues = validate_recommended_structure(
        tree,
        inventory_paths={f.path for f in project.files},
        structure_style=STRUCTURE_STYLE_ACTION_API,
    )
    assert issues == [], f"Unexpected issues: {issues}"


def test_action_api_move_map_lists_create_task():
    project = ProjectContext(name="XTask", root="/tmp/xtask", files=_x_task_files())
    changes = build_structure_changes(
        project, "express_vite_monorepo", structure_style=STRUCTURE_STYLE_ACTION_API
    )
    by_src = {src: dest for src, dest, _ in changes}
    assert "backend/src/services/createTask.ts" in by_src
    assert by_src["backend/src/services/createTask.ts"] == "backend/src/task/create/createTask.ts"
    assert "docs/API.md" in by_src
    assert by_src["docs/API.md"] == "backend/docs/API.md"


@pytest.mark.asyncio
async def test_engine_action_api_emits_moves_and_target():
    project = ProjectContext(name="XTask", root="/tmp/xtask", files=_x_task_files())
    engine = AuditEngine()
    result = await engine.run_structure_audit(
        project, llm=None, structure_style=STRUCTURE_STYLE_ACTION_API
    )
    assert result.structure_style == "action_api"
    assert result.structure_changes
    assert any("/task/create/" in m.to_path for m in result.structure_changes)
    assert "task" in result.recommended_structure
    assert result.current_structure
    assert result.features_identified
    assert "Structure quality gate" in result.recommended_structure
