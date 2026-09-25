"""Import graph + AST call-graph hops for investigation locate."""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from repoaudit.indexing.models import ProjectContext

_IMPORT_PATTERNS = (
    re.compile(r"^\s*from\s+([A-Za-z0-9_./]+)\s+import\s+", re.M),
    re.compile(r"^\s*import\s+([A-Za-z0-9_./]+)", re.M),
    re.compile(r"""(?:import|require)\(\s*['"]([^'"]+)['"]\s*\)"""),
    re.compile(r"""from\s+['"]([^'"]+)['"]"""),
    re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)"""),
)
_CALL_NAME_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\s*\(")


def build_import_neighbors(project: ProjectContext) -> dict[str, set[str]]:
    """Map each file path to neighboring files referenced by relative imports."""
    by_stem: dict[str, list[str]] = defaultdict(list)
    path_set: set[str] = set()
    for file_info in project.files:
        rel = file_info.path.replace("\\", "/").strip("/")
        path_set.add(rel)
        stem = Path(rel).stem.lower()
        by_stem[stem].append(rel)

    neighbors: dict[str, set[str]] = defaultdict(set)

    # Prefer DependencyGraph when networkx graph is available.
    try:
        from repoaudit.indexing.graph.graph import DependencyGraph

        dg = DependencyGraph.build_from_project(project)
        for src, dst in dg.graph.edges:
            s = str(src).replace("\\", "/")
            d = str(dst).replace("\\", "/")
            neighbors[s].add(d)
            neighbors[d].add(s)
    except Exception:
        pass

    for file_info in project.files:
        src = file_info.path.replace("\\", "/").strip("/")
        content = file_info.content or file_info.preview or ""
        if not content:
            continue
        for pattern in _IMPORT_PATTERNS:
            for match in pattern.finditer(content):
                raw = match.group(1).strip()
                resolved = _resolve_import(src, raw, path_set, by_stem)
                if resolved and resolved != src:
                    neighbors[src].add(resolved)
                    neighbors[resolved].add(src)

        # AST / heuristic call-graph edges (Python AST + name matching elsewhere).
        for callee in _extract_call_names(src, content):
            matches = by_stem.get(callee.lower(), [])
            for dst in matches:
                if dst != src:
                    neighbors[src].add(dst)
                    neighbors[dst].add(src)
    return neighbors


def expand_via_graph(seed_paths: list[str], neighbors: dict[str, set[str]], max_extra: int = 12) -> list[str]:
    """Return unique one- and two-hop neighbors of seed paths."""
    extras: list[str] = []
    seen = set(seed_paths)
    frontier = list(seed_paths)
    hops = 0
    while frontier and hops < 2 and len(extras) < max_extra:
        nxt: list[str] = []
        for seed in frontier:
            for neighbor in sorted(neighbors.get(seed, set())):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                extras.append(neighbor)
                nxt.append(neighbor)
                if len(extras) >= max_extra:
                    return extras
        frontier = nxt
        hops += 1
    return extras


def _extract_call_names(source_path: str, content: str) -> set[str]:
    names: set[str] = set()
    if source_path.endswith(".py"):
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Name):
                        names.add(func.id)
                    elif isinstance(func, ast.Attribute):
                        names.add(func.attr)
        except SyntaxError:
            pass
    for match in _CALL_NAME_RE.finditer(content):
        names.add(match.group(1))
    # Drop common noise.
    return {n for n in names if n.lower() not in {"print", "len", "str", "int", "list", "dict", "set", "super", "require", "fetch"}}


def _resolve_import(
    source_path: str,
    raw: str,
    path_set: set[str],
    by_stem: dict[str, list[str]],
) -> str | None:
    cleaned = raw.replace("\\", "/").strip()
    if not cleaned or cleaned.startswith(("http:", "https:", "node:", "fs", "path", "os", "sys", "re")):
        return None

    if cleaned.startswith("."):
        dir_parts = source_path.split("/")[:-1]
        rest = cleaned
        while rest.startswith(".."):
            if dir_parts:
                dir_parts.pop()
            rest = rest[2:]
            if rest.startswith("/"):
                rest = rest[1:]
        if rest.startswith("."):
            rest = rest[1:]
        rest = rest.lstrip("/")
        module_path = "/".join([*dir_parts, *rest.replace(".", "/").split("/")]).strip("/")
        for suffix in ("", ".ts", ".tsx", ".js", ".jsx", ".py", "/index.ts", "/index.tsx", "/index.js", "/__init__.py"):
            trial = f"{module_path}{suffix}".replace("\\", "/").strip("/")
            if trial in path_set:
                return trial
        stem = Path(rest).stem.lower() if rest else ""
        matches = by_stem.get(stem, [])
        same_dir = [m for m in matches if m.rsplit("/", 1)[0] == "/".join(dir_parts)]
        if same_dir:
            return same_dir[0]
        return matches[0] if len(matches) == 1 else None

    dotted = cleaned.replace(".", "/")
    for path in path_set:
        if path.endswith(f"{dotted}.py") or f"/{dotted}/" in f"/{path}/":
            return path
        if Path(path).stem.lower() == Path(dotted).name.lower() and dotted.split("/")[-1].lower() in path.lower():
            return path

    stem = Path(cleaned).stem.lower() or cleaned.lower().split("/")[-1]
    matches = by_stem.get(stem, [])
    return matches[0] if len(matches) == 1 else None
