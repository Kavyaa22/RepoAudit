from repoaudit.indexing.graph.graph import DependencyGraph
from repoaudit.indexing.llm.prompts import salvage_architecture_partial
from repoaudit.indexing.models import ArchitectureDiagram, FileInfo, ProjectContext, WikiData
from repoaudit.indexing.wiki.builder import WikiBuilder, normalize_mermaid


def _project(files: dict[str, tuple[str, str]]) -> ProjectContext:
    return ProjectContext(
        name="fixture",
        root=".",
        files=[
            FileInfo(path=path, size=len(content), language=language, content=content)
            for path, (language, content) in files.items()
        ],
    )


def _linked_project() -> ProjectContext:
    return _project(
        {
            "src/app/api/routes.py": ("python", "from ..services.users import get_user\n"),
            "src/app/services/users.py": ("python", "def get_user(): ...\n"),
        }
    )


def test_wiki_has_dedicated_architecture_and_dependency_pages_with_mermaid():
    project = _linked_project()
    graph = DependencyGraph.build_from_project(project)
    wiki = WikiBuilder().build(project, WikiData(), graph)

    ids = [p.id for p in wiki.pages]
    assert "architecture" in ids
    assert "dependencies" in ids

    arch = wiki.get_page("architecture")
    deps = wiki.get_page("dependencies")
    struct = wiki.get_page("structure-audit")
    assert arch is not None and deps is not None and struct is not None
    assert "```mermaid" in arch.content
    assert "```mermaid" in deps.content
    assert "Showing how files talk to each other" in arch.content
    assert "```mermaid" not in struct.content
    sidebar_ids = [item.page_id for item in wiki.sidebar]
    assert "architecture" in sidebar_ids
    assert "dependencies" in sidebar_ids
    assert "security-audit" in ids
    assert "security-audit" in sidebar_ids


def test_architecture_page_uses_llm_mermaid_when_present():
    project = _linked_project()
    graph = DependencyGraph.build_from_project(project)
    wiki = WikiBuilder().build(
        project,
        WikiData(
            architecture=ArchitectureDiagram(
                mermaid_component="graph TD\\n  A[Client] --> B[API]",
            )
        ),
        graph,
    )
    arch = wiki.get_page("architecture")
    assert arch is not None
    assert "A[Client] --> B[API]" in arch.content or "A[Client]" in arch.content
    assert "Import-graph fallback" not in arch.content
    assert "Showing how files talk to each other" not in arch.content


def test_normalize_mermaid_expands_literal_newlines_and_strips_fences():
    assert "graph TD" in normalize_mermaid("```mermaid\ngraph TD\n  A --> B\n```")
    expanded = normalize_mermaid("graph TD\\n  A --> B")
    assert "\n" in expanded
    assert "A --> B" in expanded


def test_salvage_architecture_partial_recovers_mermaid_from_truncated_json():
    raw = (
        '{"architecture_type": "Layered", "mermaid_component": "graph TD\\n  A --> B", '
        '"description": "cut off'
    )
    saved = salvage_architecture_partial(raw)
    assert saved["architecture_type"] == "Layered"
    assert "A --> B" in saved["mermaid_component"]


def test_structure_audit_page_emits_side_by_side_tree_fences():
    from repoaudit.audit.structure_models import FolderStructureAuditResult
    from repoaudit.indexing.wiki.builder import extract_fenced_tree_body

    project = _linked_project()
    audit = FolderStructureAuditResult(
        summary_reason="Folders need regrouping.",
        current_structure="### Current\n\n```text\nbackend/\n└── src/\n    └── a.py\n```",
        recommended_structure=(
            "### 3. Proposed Structure\n\n```text\nbackend/\n└── src/\n"
            "    └── auth/\n        └── login/\n            └── a.py\n```"
        ),
        structure_style="action_api",
        style_score=70,
        no_file_content_modified=True,
    )
    wiki = WikiBuilder().build(
        project,
        WikiData(structure_audit=audit),
        DependencyGraph.build_from_project(project),
    )
    struct = wiki.get_page("structure-audit")
    assert struct is not None
    assert "```structure-current" in struct.content
    assert "```structure-suggested" in struct.content
    assert "## Architecture" in struct.content
    assert "## Folder changes at a glance" in struct.content
    assert "| From | To | Why |" not in struct.content
    assert "backend/" in extract_fenced_tree_body(audit.current_structure)
    assert "auth/" in extract_fenced_tree_body(audit.recommended_structure)


def test_folder_delta_from_trees_lists_added_and_removed():
    from repoaudit.indexing.wiki.builder import folder_delta_from_trees

    current = "backend/\n└── src/\n    └── services/\n        └── a.py\n"
    suggested = (
        "backend/\n└── src/\n    └── auth/\n        └── login/\n            └── a.py\n"
    )
    added, removed = folder_delta_from_trees(current, suggested)
    assert any(p.endswith("auth") or p.endswith("auth/login") or "auth" in p for p in added)
    assert any("services" in p for p in removed)
    project = _project(
        {
            r"frontend\src\pages\home.tsx": (
                "typescript",
                "import { api } from '../lib/api';\n",
            ),
            r"frontend\src\lib\api.ts": ("typescript", "export const api = {};\n"),
        }
    )
    graph = DependencyGraph.build_from_project(project)
    wiki = WikiBuilder().build(project, WikiData(), graph)

    arch = wiki.get_page("architecture")
    deps = wiki.get_page("dependencies")
    assert arch is not None and deps is not None
    assert "```mermaid" in arch.content
    assert "```mermaid" in deps.content
    assert "No picture could be drawn" not in arch.content
    assert "We could not draw a connection map" not in deps.content
