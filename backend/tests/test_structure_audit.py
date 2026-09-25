import pytest
from repoaudit.audit.engine import AuditEngine
from repoaudit.audit.scoring import compute_structure_score
from repoaudit.audit.structure_context import (
    build_profile_aware_structure,
    detect_stack_hints,
    validate_recommended_structure,
)
from repoaudit.audit.structure_models import FolderViolation
from repoaudit.audit.structure_static import (
    StaticStructureAuditor,
    detect_layout_profile,
    infer_suggested_path,
)
from repoaudit.indexing.models import FileInfo, ProjectContext


def test_static_auditor_compliant_repo():
    files = [
        FileInfo(path="README.md", size=100),
        FileInfo(path=".gitignore", size=20),
        FileInfo(path="backend/src/app/services/auth/login/handler.py", size=500),
        FileInfo(path="frontend/src/app/services/auth/login/Component.tsx", size=600),
    ]
    project = ProjectContext(name="CompliantRepo", root="/tmp/repo", files=files)
    auditor = StaticStructureAuditor()
    violations = auditor.audit(project)

    assert len(violations) == 0


def test_static_auditor_disallowed_root_directory():
    files = [
        FileInfo(path="backend/src/app/services/auth/login/handler.py", size=500),
        FileInfo(path="frontend/src/app/services/auth/login/Component.tsx", size=600),
        FileInfo(path="random_scripts/helper.sh", size=100),
    ]
    project = ProjectContext(name="NonCompliantRepo", root="/tmp/repo", files=files)
    auditor = StaticStructureAuditor()
    violations = auditor.audit(project)

    assert len(violations) >= 1
    root_violations = [v for v in violations if v.violation_type == "disallowed_root_directory"]
    assert len(root_violations) == 1
    assert root_violations[0].path == "random_scripts"


def test_static_auditor_aggregates_instead_of_flooding():
    files = [
        FileInfo(path="backend/scripts/a.py", size=10),
        FileInfo(path="backend/scripts/b.py", size=10),
        FileInfo(path="backend/scripts/c.py", size=10),
        FileInfo(path="backend/legacy/d.py", size=10),
        FileInfo(path="frontend/src/pages/Home.tsx", size=10),
        FileInfo(path="frontend/src/components/Button.tsx", size=10),
    ]
    project = ProjectContext(name="MixedRepo", root="/tmp/repo", files=files)
    auditor = StaticStructureAuditor()
    violations = auditor.audit(project)

    assert len(violations) < len(files)
    assert all(v.path != "frontend/src/pages/Home.tsx" for v in violations)


def test_score_caps_prevent_always_zero():
    violations = [
        FolderViolation(
            path=f"backend/file_{i}.py",
            violation_type="invalid_path_depth",
            severity="high",
            description="x",
        )
        for i in range(50)
    ]
    score, is_valid = compute_structure_score(violations)
    assert score > 0
    assert score >= 100 - 35
    assert is_valid is False


@pytest.mark.asyncio
async def test_audit_engine_structure_audit():
    files = [
        FileInfo(path="backend/src/app/services/user/create/service.py", size=400),
        FileInfo(path="frontend/src/app/services/user/create/Page.tsx", size=400),
    ]
    project = ProjectContext(name="ValidRepo", root="/tmp/repo", files=files)
    engine = AuditEngine()
    result = await engine.run_structure_audit(project, llm=None)

    assert result.is_valid is True
    assert result.overall_score == 100
    assert len(result.static_violations) == 0


@pytest.mark.asyncio
async def test_fastapi_style_backend_not_flooded():
    files = [
        FileInfo(path="backend/app/main.py", size=100),
        FileInfo(path="backend/app/modules/audit/run/service.py", size=100),
        FileInfo(path="backend/app/api/v1/router.py", size=100),
        FileInfo(path="frontend/src/pages/Home.tsx", size=100),
        FileInfo(path="frontend/src/components/Nav.tsx", size=100),
    ]
    project = ProjectContext(name="ProductRepo", root="/tmp/repo", files=files)
    engine = AuditEngine()
    result = await engine.run_structure_audit(project, llm=None)

    assert result.overall_score > 0
    assert len(result.static_violations) < 10


def _fleet_monitor_files() -> list[FileInfo]:
    """Minimal Traffix/fleet Express + Vite React monorepo layout."""
    backend_src = [
        "backend/src/server.ts",
        "backend/src/index.ts",
        "backend/src/config.ts",
        "backend/src/store.ts",
        "backend/src/monitor.ts",
        "backend/src/watchlist.ts",
        "backend/src/detector.ts",
        "backend/src/detector.test.ts",
        "backend/src/events.ts",
        "backend/src/notify.ts",
        "backend/src/eta.ts",
        "backend/src/match.ts",
        "backend/src/geo.ts",
        "backend/src/time.ts",
        "backend/src/stopThreshold.ts",
        "backend/src/gpsActiveLoad.ts",
        "backend/src/loadMilestones.ts",
        "backend/src/companyYards.ts",
        "backend/src/amos/auth.ts",
        "backend/src/amos/tripClient.ts",
        "backend/src/maestral/client.ts",
        "backend/src/email/mailer.ts",
        "backend/src/email/routes.ts",
        "backend/src/google/auth.ts",
        "backend/src/google/routes.ts",
    ]
    backend_scripts = [
        "backend/scripts/amos-loads-audit.ts",
        "backend/scripts/mapping-report-30d.ts",
    ]
    frontend = [
        "frontend/vite.config.ts",
        "frontend/src/main.tsx",
        "frontend/src/App.tsx",
        "frontend/src/pages/Dashboard.tsx",
        "frontend/src/pages/Settings.tsx",
        "frontend/src/pages/StatusGuide.tsx",
        "frontend/src/components/FleetTable.tsx",
        "frontend/src/components/StatCards.tsx",
        "frontend/src/components/LoadTimeline.tsx",
        "frontend/src/components/Header.tsx",
        "frontend/src/components/NotificationBell.tsx",
        "frontend/src/components/Pagination.tsx",
        "frontend/src/components/Toolbar.tsx",
        "frontend/src/hooks/useTrailers.ts",
        "frontend/src/hooks/useStopEvents.ts",
        "frontend/src/hooks/useSound.ts",
        "frontend/src/hooks/useReadState.ts",
        "frontend/src/hooks/useMonitorConfig.ts",
        "frontend/src/api/client.ts",
        "frontend/src/types.ts",
        "frontend/src/util.ts",
    ]
    root = [
        "docs/fleet-analysis.md",
        "backend/supabase/migration.sql",
        FileInfo(
            path="backend/package.json",
            size=200,
            content='{"dependencies":{"express":"^4.21.2","@supabase/supabase-js":"^2.45.4"}}',
        ),
        FileInfo(
            path="frontend/package.json",
            size=200,
            content='{"dependencies":{"react":"^18.0.0","react-router-dom":"^6.0.0"},"devDependencies":{"vite":"^5.0.0"}}',
        ),
    ]
    files: list[FileInfo] = []
    for p in backend_src + backend_scripts + frontend:
        files.append(FileInfo(path=p, size=100))
    for item in root:
        if isinstance(item, FileInfo):
            files.append(item)
        else:
            files.append(FileInfo(path=item, size=100))
    return files


def test_express_vite_profile_detection():
    project = ProjectContext(name="FleetMonitor", root="/tmp/repo", files=_fleet_monitor_files())
    profile = detect_layout_profile(project)
    assert profile == "express_vite_monorepo"


def test_express_vite_static_audit_not_flooded():
    project = ProjectContext(name="FleetMonitor", root="/tmp/repo", files=_fleet_monitor_files())
    auditor = StaticStructureAuditor()
    violations = auditor.audit(project)
    assert len(violations) <= 2
    assert all("src/app/services" not in v.suggestion for v in violations)


def test_infer_suggested_path_express_vite():
    assert infer_suggested_path(
        "backend/src/monitor.ts", "backend", "express_vite_monorepo"
    ).startswith("backend/src/domain/")
    assert infer_suggested_path(
        "backend/src/amos/auth.ts", "backend", "express_vite_monorepo"
    ) == "backend/src/integrations/amos/auth.ts"
    assert infer_suggested_path(
        "backend/scripts/audit.ts", "backend", "express_vite_monorepo"
    ) == "backend/scripts/audit.ts"
    assert infer_suggested_path(
        "frontend/src/components/FleetTable.tsx", "frontend", "express_vite_monorepo"
    ).startswith("frontend/src/features/dashboard/")


def test_validate_recommended_structure_rejects_hybrid_frontend():
    bad_tree = """
```text
frontend/src/pages/Dashboard.tsx
frontend/src/features/dashboard/Dashboard.tsx
frontend/src/app/dashboard/Dashboard.tsx
```
"""
    issues = validate_recommended_structure(bad_tree)
    assert any("Hybrid frontend" in i for i in issues)
    assert any("Duplicate" in i for i in issues)


def test_validate_recommended_structure_rejects_scripts_in_src():
    bad_tree = """
```text
backend/src/lib/scripts/amos-loads-audit.ts
```
"""
    issues = validate_recommended_structure(bad_tree)
    assert any("backend/scripts/" in i for i in issues)


def test_validate_recommended_structure_rejects_single_file_folder():
    bad_tree = """
```text
backend/src/stopThreshold/stopThreshold.ts
```
"""
    issues = validate_recommended_structure(bad_tree)
    assert any("Over-nested" in i for i in issues)


def test_profile_aware_structure_fleet_repo_passes_validation():
    from repoaudit.audit.structure_style import STRUCTURE_STYLE_CONSERVATIVE

    project = ProjectContext(name="FleetMonitor", root="/tmp/repo", files=_fleet_monitor_files())
    tree = build_profile_aware_structure(
        project, "express_vite_monorepo", structure_style=STRUCTURE_STYLE_CONSERVATIVE
    )
    issues = validate_recommended_structure(
        tree, structure_style=STRUCTURE_STYLE_CONSERVATIVE
    )
    assert issues == [], f"Expected no validation issues, got: {issues}"
    assert "scripts/" in tree and "outside src" in tree
    assert "src/integrations/" in tree
    assert "src/domain/" in tree
    assert "src/features/" in tree
    assert "src/pages/" not in tree.split("frontend/")[1].split("```")[0]
    assert "src/lib/scripts" not in tree


def test_stack_hints_detect_express_and_vite():
    project = ProjectContext(name="FleetMonitor", root="/tmp/repo", files=_fleet_monitor_files())
    hints = detect_stack_hints(project)
    assert "express" in " ".join(hints.get("backend_frameworks", [])).lower()
    assert "vite" in " ".join(hints.get("build_tools", [])).lower()
    assert hints.get("source_file_count", 0) >= 40


@pytest.mark.asyncio
async def test_fleet_repo_static_structure_score_high():
    project = ProjectContext(name="FleetMonitor", root="/tmp/repo", files=_fleet_monitor_files())
    engine = AuditEngine()
    result = await engine.run_structure_audit(project, llm=None)
    assert result.overall_score >= 90
    assert result.is_valid is True
    assert result.recommended_structure
    assert "backend/" in result.recommended_structure
    assert "frontend/" in result.recommended_structure


def _fastapi_monorepo_files(*, include_orphan: bool = True) -> list[FileInfo]:
    files = [
        FileInfo(
            path="backend/app/main.py",
            size=80,
            language="python",
            content="from fastapi import FastAPI\nfrom app.api.v1.router import api_router\napp = FastAPI()\napp.include_router(api_router)\n",
        ),
        FileInfo(
            path="backend/app/api/v1/router.py",
            size=80,
            language="python",
            content="from fastapi import APIRouter\nfrom app.modules.audit.list.router import router as audit_router\nrouter = APIRouter()\nrouter.include_router(audit_router)\n",
        ),
        FileInfo(
            path="backend/app/modules/audit/list/router.py",
            size=80,
            language="python",
            content="from fastapi import APIRouter\nfrom .service import list_audits\nrouter = APIRouter()\n",
        ),
        FileInfo(
            path="backend/app/modules/audit/list/service.py",
            size=40,
            language="python",
            content="def list_audits():\n    return []\n",
        ),
        FileInfo(
            path="backend/app/core/config/settings.py",
            size=40,
            language="python",
            content="class Settings:\n    pass\n",
        ),
        FileInfo(
            path="frontend/src/main.tsx",
            size=40,
            language="tsx",
            content="import { App } from './App'\n",
        ),
        FileInfo(
            path="frontend/src/App.tsx",
            size=40,
            language="tsx",
            content="export const App = () => null\n",
        ),
        FileInfo(
            path="frontend/src/app/audit/list/page.tsx",
            size=40,
            language="tsx",
            content="export default function Page() { return null }\n",
        ),
        FileInfo(path="docs/ARCHITECTURE.md", size=20, content="# Architecture\n"),
        FileInfo(
            path="backend/pyproject.toml",
            size=40,
            content='[project]\ndependencies = ["fastapi", "uvicorn"]\n',
        ),
    ]
    if include_orphan:
        files.append(
            FileInfo(
                path="backend/app/unused/orphan.py",
                size=20,
                language="python",
                content="VALUE = 1\n",
            )
        )
    return files


def test_fastapi_whole_repo_tree_lists_file_leaves_and_omits_dead():
    from repoaudit.audit.structure_target import collect_dead_paths, count_file_leaves

    project = ProjectContext(name="ProductRepo", root="/tmp/repo", files=_fastapi_monorepo_files())
    dead = collect_dead_paths(project)
    assert "backend/app/unused/orphan.py" in dead

    tree = build_profile_aware_structure(project, "fastapi_app", exclude_paths=dead)
    assert "<feature>" not in tree
    assert "backend/" in tree
    assert "frontend/" in tree
    assert "docs/" in tree
    assert "main.py" in tree
    assert "service.py" in tree
    assert "page.tsx" in tree
    assert "ARCHITECTURE.md" in tree
    assert "orphan.py" not in tree.split("```")[1]
    assert "unused/" not in tree.split("```")[1]
    assert count_file_leaves(tree) >= 8
    issues = validate_recommended_structure(
        tree,
        inventory_paths={f.path for f in project.files},
        exclude_paths=dead,
    )
    assert issues == [], f"Expected no validation issues, got: {issues}"


@pytest.mark.asyncio
async def test_structure_audit_without_llm_still_emits_whole_repo_tree():
    project = ProjectContext(name="ProductRepo", root="/tmp/repo", files=_fastapi_monorepo_files())
    engine = AuditEngine()
    result = await engine.run_structure_audit(project, llm=None)
    assert result.recommended_structure
    assert "main.py" in result.recommended_structure
    assert "frontend/" in result.recommended_structure
    assert "orphan.py" not in result.recommended_structure.split("```text")[-1].split("```")[0]


def test_validate_recommended_structure_rejects_placeholder_slice():
    stub = """
### Recommended target structure (FastAPI)

```text
backend/app/
├── main.py
├── api/
├── modules/<feature>/
└── core/
```
"""
    issues = validate_recommended_structure(
        stub,
        inventory_paths={"backend/app/main.py", "frontend/src/main.tsx"},
    )
    assert any("placeholder" in i.lower() for i in issues)
    assert any("frontend" in i.lower() for i in issues)


def test_phase0_action_api_style_locked():
    from repoaudit.audit.structure_style import (
        DEFAULT_STRUCTURE_STYLE,
        GOLDEN_ACTION_API_EXAMPLE,
        STRUCTURE_STYLE_ACTION_API,
        style_prompt_block,
    )

    assert DEFAULT_STRUCTURE_STYLE == STRUCTURE_STYLE_ACTION_API
    assert "auth/" in GOLDEN_ACTION_API_EXAMPLE or "auth" in GOLDEN_ACTION_API_EXAMPLE
    assert "authentication/" not in GOLDEN_ACTION_API_EXAMPLE
    assert "login" in GOLDEN_ACTION_API_EXAMPLE
    assert ".env.example" in GOLDEN_ACTION_API_EXAMPLE
    assert ".gitignore" in GOLDEN_ACTION_API_EXAMPLE
    block = style_prompt_block()
    assert "auth" in block.lower()
    assert ".env.example" in block
    assert "Feature → Action" in block or "feature-first" in block.lower()


def test_phase1_validate_allows_consolidating_docs_under_backend():
    """action_api style: docs/ may leave the top level and live under backend/docs/."""
    tree = """
```text
backend/
├── docs/
│   └── ARCHITECTURE.md
└── src/
    └── index.ts
frontend/
└── src/
    └── main.tsx
```
"""
    inventory = {
        "backend/src/index.ts",
        "frontend/src/main.tsx",
        "docs/ARCHITECTURE.md",
        "templates-src/sim-final/index.html",
    }
    issues = validate_recommended_structure(
        tree,
        inventory_paths=inventory,
        structure_style="action_api",
    )
    # templates-src still missing from tree is OK for this small fixture; docs folded is the point.
    assert not any("docs/" in i and "folded" in i.lower() for i in issues)
    assert not any("copy-current" in i.lower() for i in issues)


def test_validate_rejects_copy_current_type_buckets():
    from repoaudit.audit.structure_context import validate_folder_changes_payload

    tree = """
```text
docs/README.md
scripts/dev.mjs
templates-src/sim/index.html
backend/src/services/createTask.ts
backend/src/services/listTask.ts
backend/src/lib/util.ts
frontend/src/components/Foo.tsx
frontend/src/components/Bar.tsx
frontend/src/hooks/useFoo.ts
frontend/src/lib/api.ts
```
"""
    inventory = {
        "docs/README.md",
        "scripts/dev.mjs",
        "templates-src/sim/index.html",
        "backend/src/services/createTask.ts",
        "backend/src/services/listTask.ts",
        "backend/src/lib/util.ts",
        "frontend/src/components/Foo.tsx",
        "frontend/src/components/Bar.tsx",
        "frontend/src/hooks/useFoo.ts",
        "frontend/src/lib/api.ts",
    }
    issues = validate_recommended_structure(
        tree, inventory_paths=inventory, structure_style="action_api"
    )
    assert issues, "Expected copy-current / type-bucket rejection"
    assert any("folded" in i.lower() or "type" in i.lower() or "similar" in i.lower() for i in issues)

    change_issues = validate_folder_changes_payload(
        [], inventory_paths=inventory, structure_style="action_api"
    )
    assert change_issues


def test_validate_accepts_feature_action_reorg():
    tree = """
```text
backend/docs/README.md
backend/src/task/create/createTask.ts
backend/src/task/list/listTask.ts
backend/src/task/shared/util.ts
frontend/template-sources/sim/index.html
frontend/src/task/create/Foo.tsx
frontend/src/task/list/Bar.tsx
frontend/src/task/create/useFoo.ts
frontend/src/common/shared/api.ts
```
"""
    inventory = {
        "docs/README.md",
        "templates-src/sim/index.html",
        "backend/src/services/createTask.ts",
        "backend/src/services/listTask.ts",
        "backend/src/lib/util.ts",
        "frontend/src/components/Foo.tsx",
        "frontend/src/components/Bar.tsx",
        "frontend/src/hooks/useFoo.ts",
        "frontend/src/lib/api.ts",
    }
    issues = validate_recommended_structure(
        tree, inventory_paths=inventory, structure_style="action_api"
    )
    assert issues == [], issues


def test_phase1_validate_still_requires_backend_and_frontend():
    tree = """
```text
backend/
└── src/
    └── index.ts
```
"""
    inventory = {
        "backend/src/index.ts",
        "frontend/src/main.tsx",
        "docs/README.md",
    }
    issues = validate_recommended_structure(tree, inventory_paths=inventory)
    assert any("frontend" in i.lower() for i in issues)


def test_phase1_conservative_style_still_requires_docs_root():
    from repoaudit.audit.structure_style import STRUCTURE_STYLE_CONSERVATIVE

    tree = """
```text
backend/
└── src/
    └── index.ts
frontend/
└── src/
    └── main.tsx
```
"""
    inventory = {
        "backend/src/index.ts",
        "frontend/src/main.tsx",
        "docs/README.md",
    }
    issues = validate_recommended_structure(
        tree,
        inventory_paths=inventory,
        structure_style=STRUCTURE_STYLE_CONSERVATIVE,
    )
    assert any("docs" in i.lower() for i in issues)


@pytest.mark.asyncio
async def test_phase1_structure_audit_emits_current_changes_recommended():
    project = ProjectContext(
        name="Phase1Repo",
        root="/tmp/repo",
        files=_fastapi_monorepo_files(include_orphan=False),
    )
    engine = AuditEngine()
    result = await engine.run_structure_audit(project, llm=None)

    assert result.structure_style == "action_api"
    assert result.current_structure
    assert "Current structure" in result.current_structure
    assert "backend/" in result.current_structure
    assert result.recommended_structure
    assert isinstance(result.structure_changes, list)
    # Dual output: current and recommended are both present and distinct sections
    assert "main.py" in result.current_structure or "main.py" in result.recommended_structure

