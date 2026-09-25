"""Whole-repository target layout: file leaves, dead-file omission, empty-folder drop."""

from __future__ import annotations

import os
import re

from repoaudit.audit.dead_code_models import DeadCodeAuditResult
from repoaudit.indexing.models import FileInfo, ProjectContext

SOURCE_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".rs", ".java", ".kt"}

_LANG_FROM_EXT = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".jsx": "jsx",
}

DEAD_DIR_MARKERS = (
    "/unused/",
    "/dead/",
    "/orphan/",
    "/scratch/",
    "/deprecated/",
    "/legacy/",
    "/tmp/",
)

PROTECTED_BASENAMES = {
    "main.py",
    "app.py",
    "run.py",
    "run_dev.py",
    "server.py",
    "wsgi.py",
    "asgi.py",
    "manage.py",
    "__init__.py",
    "__main__.py",
    "server.ts",
    "index.ts",
    "index.tsx",
    "index.js",
    "index.jsx",
    "main.ts",
    "main.tsx",
    "main.js",
    "app.tsx",
    "app.jsx",
    "page.tsx",
    "page.jsx",
    "layout.tsx",
    "layout.jsx",
    "router.py",
    "routes.py",
    "settings.py",
    "config.py",
    "deps.py",
    "vite.config.ts",
    "vite.config.js",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "readme.md",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
}

PROFILE_TITLES = {
    "express_vite_monorepo": "Express + Vite React monorepo",
    "fastapi_app": "FastAPI + frontend monorepo",
    "react_src": "React application",
    "services_modular": "modular services monorepo",
    "package_src": "package / library layout",
    "mixed": "full repository",
}

EXPRESS_HEADER = """### Recommended target structure (Express + Vite React monorepo)

**Migration phases:**
1. Backend: move vendor code to `src/integrations/`, core engine to `src/domain/` (low risk).
2. Frontend: extract dashboard-only UI to `src/features/dashboard/`; keep shared hooks in `src/shared/`.
3. Optional: rename `features/*/...Page.tsx` once imports are updated.

Keep `backend/scripts/` and repo-root `docs/` outside src/.
"""


def _norm(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def _norm_paths(project: ProjectContext) -> list[str]:
    return [_norm(f.path) for f in project.files]


def _is_source_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SOURCE_EXTENSIONS


def _is_protected_path(path: str) -> bool:
    name = os.path.basename(path)
    lower_name = name.lower()
    if lower_name in PROTECTED_BASENAMES or name.startswith("."):
        return True
    lower = path.lower()
    markers = (
        "/test/",
        "/tests/",
        "test_",
        "_test.",
        ".test.",
        ".spec.",
        "/migrations/",
        "/alembic/",
        "/__snapshots__/",
        "/core/",
        "/config/",
    )
    if any(m in lower for m in markers):
        return True
    if lower_name.endswith((".md", ".json", ".toml", ".yml", ".yaml", ".lock", ".css", ".html", ".sql", ".txt")):
        return True
    return False


def _infer_language(path: str, existing: str) -> str:
    if existing and existing not in {"", "unknown"}:
        return existing
    ext = os.path.splitext(path)[1].lower()
    return _LANG_FROM_EXT.get(ext, existing or "unknown")


def _in_dead_named_folder(path: str) -> bool:
    wrapped = f"/{path.lower()}/"
    return any(marker in wrapped for marker in DEAD_DIR_MARKERS)


def _never_referenced_sources(project: ProjectContext) -> set[str]:
    """Source files whose module stem never appears in any other file."""
    entries: list[tuple[str, str]] = []
    for f in project.files:
        path = _norm(f.path)
        entries.append((path, f.content or f.preview or ""))

    dead: set[str] = set()
    for path, _content in entries:
        if not _is_source_file(path) or _is_protected_path(path):
            continue
        if not _content.strip():
            continue
        stem = os.path.splitext(os.path.basename(path))[0]
        if stem.lower() in {"index", "init", "mod", "main", "app", "server", "types", "util", "utils"}:
            continue
        others = "\n".join(
            text for other_path, text in entries if other_path != path and text.strip()
        )
        if not others.strip():
            continue
        if stem and stem not in others:
            dead.add(path)
    return dead


def collect_dead_paths(
    project: ProjectContext,
    dead_code_result: DeadCodeAuditResult | None = None,
) -> set[str]:
    """
    Paths to omit from the recommended target tree.

    Isolated source files (no inbound/outbound project imports), never-referenced
    modules, high-confidence orphan-file findings, and files under unused/legacy
    folders. Config, tests, entrypoints, and docs are kept.
    Folders that only contained these files disappear because the tree is file-driven.
    """
    dead: set[str] = set()

    if dead_code_result:
        for finding in dead_code_result.findings:
            if finding.category != "orphan_file":
                continue
            if finding.confidence_score < 70:
                continue
            path = _norm(finding.path)
            if path and not _is_protected_path(path):
                dead.add(path)

    for path in _norm_paths(project):
        if _in_dead_named_folder(path) and _is_source_file(path) and not _is_protected_path(path):
            dead.add(path)

    dead.update(_never_referenced_sources(project))

    enriched = []
    has_parseable_source = False
    for f in project.files:
        lang = _infer_language(f.path, f.language)
        content = f.content or f.preview
        if _is_source_file(_norm(f.path)) and content:
            has_parseable_source = True
        enriched.append(
            FileInfo(
                path=_norm(f.path),
                size=f.size,
                language=lang,
                lines=f.lines,
                preview=f.preview,
                content=content,
                is_config=f.is_config,
                is_entrypoint=f.is_entrypoint,
            )
        )

    if has_parseable_source:
        from repoaudit.indexing.graph.graph import DependencyGraph

        graph_project = ProjectContext(
            name=project.name,
            root=project.root,
            files=enriched,
            file_tree=project.file_tree,
        )
        graph = DependencyGraph.build_from_project(graph_project)
        if graph.graph.number_of_edges() > 0:
            for path in graph.find_isolated_files():
                npath = _norm(path)
                if not _is_source_file(npath) or _is_protected_path(npath):
                    continue
                info = next((f for f in enriched if f.path == npath), None)
                if info and (info.is_entrypoint or info.is_config):
                    continue
                dead.add(npath)

    return dead


def count_file_leaves(text: str) -> int:
    count = 0
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            continue
        if stripped.startswith(("- ", "* ", "#")):
            continue
        leaf = stripped.lstrip("│├└─ ").rstrip("/")
        if "→" in leaf or "->" in leaf:
            continue
        if "." in os.path.basename(leaf) and not leaf.endswith("/"):
            count += 1
    return count


def render_directory_tree(paths: list[str], max_lines: int = 2500) -> str:
    """ASCII tree from file paths. Empty folders never appear (no files → no dir)."""
    unique = sorted({_norm(p) for p in paths if _norm(p)})
    tree: dict = {"__files__": []}
    for path in unique:
        parts = [p for p in path.split("/") if p]
        if not parts:
            continue
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {"__files__": []})
        node.setdefault("__files__", []).append(parts[-1])

    lines = ["```text", "repository/"]

    def _walk(node: dict, prefix: str) -> None:
        if len(lines) >= max_lines:
            return
        dirs = sorted(k for k in node if k != "__files__")
        files = sorted(set(node.get("__files__", [])))
        entries: list[tuple[str, bool]] = [(d, True) for d in dirs] + [(f, False) for f in files]
        for i, (name, is_dir) in enumerate(entries):
            if len(lines) >= max_lines:
                remaining = len(entries) - i
                lines.append(f"{prefix}└── … (+{remaining} more)")
                return
            last = i == len(entries) - 1
            branch = "└── " if last else "├── "
            suffix = "/" if is_dir else ""
            lines.append(f"{prefix}{branch}{name}{suffix}")
            if is_dir:
                extension = "    " if last else "│   "
                _walk(node[name], prefix + extension)

    _walk(tree, "")
    if len(lines) >= max_lines:
        lines.append("… (tree truncated)")
    lines.append("```")
    return "\n".join(lines)


def map_inventory_path(
    rel: str,
    profile: str,
    structure_style: str | None = None,
    *,
    catalog: list[str] | None = None,
) -> str:
    """Profile-aware destination for a live inventory path."""
    from repoaudit.audit.structure_context import _map_backend_path, _map_frontend_path
    from repoaudit.audit.structure_style import (
        DEFAULT_STRUCTURE_STYLE,
        STRUCTURE_STYLE_ACTION_API,
    )

    rel = _norm(rel)
    style = structure_style or DEFAULT_STRUCTURE_STYLE
    if style == STRUCTURE_STYLE_ACTION_API:
        from repoaudit.audit.structure_action_style import suggest_action_api_path

        return suggest_action_api_path(rel, catalog=catalog)

    if profile == "express_vite_monorepo":
        if rel.startswith("backend/"):
            return _map_backend_path(rel)
        if rel.startswith("frontend/"):
            return _map_frontend_path(rel, use_features=True)
        return rel
    if profile == "react_src" and rel.startswith("frontend/"):
        return _map_frontend_path(rel, use_features=False)
    return rel


def live_inventory_paths(
    project: ProjectContext,
    exclude_paths: set[str] | None = None,
) -> list[str]:
    exclude = {_norm(p) for p in (exclude_paths or set())}
    return [p for p in _norm_paths(project) if p not in exclude]


def mapped_targets(
    project: ProjectContext,
    profile: str,
    exclude_paths: set[str] | None = None,
    structure_style: str | None = None,
) -> tuple[list[str], list[tuple[str, str]]]:
    from repoaudit.audit.structure_catalog import discover_feature_catalog
    from repoaudit.audit.structure_style import (
        DEFAULT_STRUCTURE_STYLE,
        STRUCTURE_STYLE_ACTION_API,
    )

    paths = live_inventory_paths(project, exclude_paths)
    style = structure_style or DEFAULT_STRUCTURE_STYLE
    catalog = (
        discover_feature_catalog(paths)
        if style == STRUCTURE_STYLE_ACTION_API
        else None
    )
    mapped: list[str] = []
    moves: list[tuple[str, str]] = []
    for src in paths:
        dest = map_inventory_path(
            src, profile, structure_style=structure_style, catalog=catalog
        )
        mapped.append(dest)
        if dest != src:
            moves.append((src, dest))
    return mapped, moves


def inventory_top_roots(project: ProjectContext, exclude_paths: set[str] | None = None) -> set[str]:
    roots: set[str] = set()
    for path in live_inventory_paths(project, exclude_paths):
        if "/" in path:
            root = path.split("/", 1)[0]
            if not root.startswith("."):
                roots.add(root)
    return roots


def build_current_structure(
    project: ProjectContext,
    exclude_paths: set[str] | None = None,
) -> str:
    """Markdown tree of today's live inventory (dead files omitted)."""
    paths = live_inventory_paths(project, exclude_paths)
    return "\n".join(
        [
            "### Current structure",
            "",
            "How the repository looks today (unused files omitted).",
            "",
            render_directory_tree(paths),
        ]
    )


def build_structure_changes(
    project: ProjectContext,
    profile: str,
    exclude_paths: set[str] | None = None,
    structure_style: str | None = None,
) -> list[tuple[str, str, str]]:
    """
    Suggested moves as (from_path, to_path, reason) tuples.
    Only includes paths that actually change.
    """
    from repoaudit.audit.structure_style import DEFAULT_STRUCTURE_STYLE, STRUCTURE_STYLE_ACTION_API

    style = structure_style or DEFAULT_STRUCTURE_STYLE
    _, moves = mapped_targets(project, profile, exclude_paths, structure_style=style)
    out: list[tuple[str, str, str]] = []
    for src, dest in moves:
        if style == STRUCTURE_STYLE_ACTION_API:
            if src.split("/", 1)[0] != dest.split("/", 1)[0]:
                reason = "Fold into backend/ or frontend/"
            elif "/api/" in dest or "/features/" in dest:
                reason = "Group into feature → action folder"
            elif re.search(r"/(?:backend|frontend)/src/[^/]+/[^/]+/", f"/{dest}"):
                reason = "Group into feature → action folder"
            else:
                reason = "Place under feature → action folder"
        else:
            reason = "Move into the recommended layout"
            if src.split("/", 1)[0] != dest.split("/", 1)[0]:
                reason = "Fold into the matching product root (backend/ or frontend/)"
        out.append((src, dest, reason))
    return out


def format_structure_changes(changes: list[tuple[str, str, str]]) -> str:
    """Markdown block for the move map."""
    if not changes:
        return (
            "### What to change\n\n"
            "No file moves are required for the deterministic baseline target."
        )
    lines = [
        "### What to change",
        "",
        "Suggested moves from the current layout to the recommended target:",
        "",
    ]
    for src, dest, reason in changes:
        suffix = f" — {reason}" if reason else ""
        lines.append(f"- `{src}` → `{dest}`{suffix}")
    return "\n".join(lines)


def build_whole_repo_structure(
    project: ProjectContext,
    profile: str,
    exclude_paths: set[str] | None = None,
    structure_style: str | None = None,
) -> str:
    """
    Whole-repository migration target with concrete file leaves.

    Dead files are omitted; folders that would be empty after that omission
    are not rendered.
    """
    from repoaudit.audit.structure_style import DEFAULT_STRUCTURE_STYLE, STRUCTURE_STYLE_ACTION_API

    exclude = {_norm(p) for p in (exclude_paths or set())}
    style = structure_style or DEFAULT_STRUCTURE_STYLE
    mapped, moves = mapped_targets(project, profile, exclude, structure_style=style)
    title = PROFILE_TITLES.get(profile, "full repository")

    if style == STRUCTURE_STYLE_ACTION_API:
        header = (
            "### Recommended target structure (action_api)\n\n"
            "**Migration phases:**\n"
            "1. Fold docs/scripts/templates into backend/ and frontend/ (low risk).\n"
            "2. Group APIs into feature_api / action_api folders under src/api/.\n"
            "3. Group UI into feature/action folders under src/features/."
        )
    elif profile == "express_vite_monorepo":
        header = EXPRESS_HEADER.rstrip()
    else:
        header = f"### Recommended target structure ({title})"

    sections = [
        header,
        "",
        "Whole-repository target (file leaves shown). Dead files and empty folders are omitted.",
        "",
        render_directory_tree(mapped),
    ]

    if moves:
        sections.extend(["", "### File migration map (from current inventory)"])
        for src, dest in moves:
            sections.append(f"- `{src}` → `{dest}`")

    if exclude:
        sections.extend(["", "### Removed as dead (omitted from target)"])
        for path in sorted(exclude):
            sections.append(f"- `{path}`")
        sections.append("")
        sections.append(
            "Folders and sub-folders that only contained dead files are also omitted."
        )

    return "\n".join(sections)
