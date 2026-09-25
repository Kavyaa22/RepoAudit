"""wiki content endpoints."""

from __future__ import annotations

from urllib.parse import unquote

from fastapi import APIRouter, Depends

from app.core.security.deps import CurrentUser, get_current_user
from app.modules.github.shared.users import resolve_user_id
from repoaudit.interfaces.api.runtime import ensure_project_loaded, owned_by_user
from repoaudit.indexing.wiki.serialization import rebuild_sidebar_from_pages

router = APIRouter()


async def _owned_wiki_project(project_id: str, user: CurrentUser):
    user_id = resolve_user_id(user)
    proj = await ensure_project_loaded(project_id, user_id=user_id)
    if not proj or not owned_by_user(proj, user_id):
        return None
    return proj


@router.get("/project/{project_id}/wiki")
async def get_wiki(project_id: str, user: CurrentUser = Depends(get_current_user)):
    """get the full wiki structure (sidebar + page list)."""
    proj = await _owned_wiki_project(project_id, user)
    if not proj:
        return {"error": "Wiki not ready"}

    if proj.get("wiki"):
        wiki = proj["wiki"]
        return {
            "project_name": wiki.project_name,
            "sidebar": _serialize_sidebar(wiki.sidebar),
            "pages": [
                {"id": p.id, "title": p.title, "order": p.order, "parent_id": p.parent_id}
                for p in wiki.pages
            ],
        }

    ws = proj.get("wiki_summary")
    if ws and isinstance(ws, dict):
        pages = ws.get("pages", [])
        if pages:
            sidebar = ws.get("sidebar")
            if not sidebar:
                sidebar = rebuild_sidebar_from_pages(pages)
            return {
                "project_name": ws.get("project_name", proj["info"].name),
                "sidebar": sidebar,
                "pages": [
                    {
                        "id": p.get("id"),
                        "title": p.get("title"),
                        "order": p.get("order", 0),
                        "parent_id": p.get("parent_id"),
                    }
                    for p in pages
                ],
            }

    # Fallback synthetic wiki structure for loaded projects
    info = proj["info"]
    name = info.name or "Repository"
    return {
        "project_name": name,
        "sidebar": [
            {"title": "Overview & Audit Summary", "page_id": "overview"}
        ],
        "pages": [
            {"id": "overview", "title": "Overview & Audit Summary", "order": 1, "parent_id": None}
        ],
    }


@router.get("/project/{project_id}/wiki/{page_id:path}")
async def get_page(project_id: str, page_id: str, user: CurrentUser = Depends(get_current_user)):
    """get a single wiki page content."""
    proj = await _owned_wiki_project(project_id, user)
    if not proj:
        return {"error": "Wiki not ready"}

    clean_id = unquote(page_id).strip("/")

    if proj.get("wiki"):
        wiki = proj["wiki"]
        page = wiki.get_page(clean_id)
        if not page and not clean_id.startswith("modules/"):
            page = wiki.get_page(f"modules/{clean_id}")
        if not page:
            lower = clean_id.lower()
            for p in wiki.pages:
                if (
                    p.id.lower() == lower
                    or p.title.lower() == lower
                    or p.id.lower() == f"modules/{lower}"
                ):
                    page = p
                    break
        if page:
            return {
                "id": page.id,
                "title": page.title,
                "content": page.content,
            }

    ws = proj.get("wiki_summary")
    if ws and isinstance(ws, dict):
        pages = ws.get("pages", [])
        lower = clean_id.lower()
        for p in pages:
            pid = str(p.get("id", "")).strip("/")
            title = str(p.get("title", ""))
            if (
                pid.lower() == lower
                or pid.lower() == f"modules/{lower}"
                or title.lower() == lower
            ):
                return {
                    "id": p.get("id"),
                    "title": p.get("title"),
                    "content": p.get("content", ""),
                }


    # Fallback page content generator
    info = proj["info"]
    name = info.name or "Repository"
    score = proj.get("score", 100)
    sa = proj.get("structure_audit")

    content = f"# Audit Summary: {name}\n\n"
    content += f"- **Overall Score:** {score}/100\n"
    content += f"- **Total Files:** {info.total_files}\n"
    content += f"- **Total Lines:** {info.total_lines}\n\n"

    if sa:
        content += "## Structure & Architecture Findings\n\n"
        findings = sa.get("findings", []) if isinstance(sa, dict) else getattr(sa, "findings", [])
        for f in findings:
            if isinstance(f, dict):
                content += f"### {f.get('title', 'Finding')}\n"
                content += f"- **Severity:** {f.get('severity', 'info')}\n"
                content += f"- **Description:** {f.get('description', '')}\n\n"

    return {
        "id": page_id,
        "title": "Overview & Audit Summary",
        "content": content,
    }




@router.get("/project/{project_id}/file/{file_path:path}")
async def get_file(project_id: str, file_path: str, user: CurrentUser = Depends(get_current_user)):
    """get file content with language detection."""
    proj = await _owned_wiki_project(project_id, user)
    if not proj or not proj.get("project"):
        return {"error": "Project not ready"}

    project = proj["project"]
    for f in project.files:
        if f.path == file_path:
            return {
                "path": f.path,
                "language": f.language,
                "content": f.content or f.preview,
                "lines": f.lines,
            }

    return {"error": f"File '{file_path}' not found"}


@router.get("/project/{project_id}/graph")
async def get_graph(project_id: str, user: CurrentUser = Depends(get_current_user)):
    """get the dependency graph as nodes + edges."""
    proj = await _owned_wiki_project(project_id, user)
    if not proj or not proj.get("project"):
        return {"error": "Project not ready"}

    from repoaudit.indexing.graph.graph import DependencyGraph
    graph = DependencyGraph.build_from_project(proj["project"])

    nodes = [
        {"id": n, **graph.graph.nodes[n]}
        for n in graph.graph.nodes
    ]
    edges = [
        {"source": s, "target": t}
        for s, t in graph.graph.edges
    ]
    rankings = [
        {"path": path, "score": round(score, 6)}
        for path, score in graph.rank_files()[:20]
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "rankings": rankings,
        "mermaid": graph.to_mermaid(),
    }


def _serialize_sidebar(items) -> list[dict]:
    from repoaudit.indexing.wiki.serialization import serialize_sidebar

    return serialize_sidebar(items)
