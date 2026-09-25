"""Stack detection, project context enrichment, and recommended-structure validation."""

from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from repoaudit.indexing.models import ProjectContext

SOURCE_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".rs", ".java", ".kt"}
IMPORT_RE = re.compile(
    r"""^(?:import\s+(?:[\w*{}\s,]+\s+from\s+)?|from\s+)['"](\.[^'"]+)['"]""",
    re.MULTILINE,
)

# Primary layout buckets that action_api must not keep as the main organization.
TYPE_BUCKET_SEGMENTS = frozenset(
    {
        "components",
        "services",
        "controllers",
        "utils",
        "hooks",
        "lib",
        "blocks",
        "helpers",
        "middleware",
        "models",
        "schemas",
        "routes",
        "pages",
    }
)

# Consolidatable roots that must not remain top-level in the proposed tree.
MUST_FOLD_TOP_LEVEL = frozenset(
    {"docs", "doc", "scripts", "script", "templates-src", "templates_src", "tools", "tooling"}
)


def _norm_paths(project: ProjectContext) -> list[str]:
    return [f.path.replace("\\", "/").strip("/") for f in project.files]


def _read_package_json(project: ProjectContext, rel_path: str) -> dict | None:
    for f in project.files:
        if f.path.replace("\\", "/").strip("/") == rel_path and f.content:
            try:
                return json.loads(f.content)
            except json.JSONDecodeError:
                return None
    return None


def detect_stack_hints(project: ProjectContext) -> dict[str, list[str] | str | int]:
    """Infer stack signals from package.json content and path heuristics."""
    paths = _norm_paths(project)
    hints: dict[str, list[str] | str | int] = {
        "backend_frameworks": [],
        "frontend_frameworks": [],
        "databases": [],
        "build_tools": [],
    }

    for pkg_path, key in (
        ("backend/package.json", "backend"),
        ("frontend/package.json", "frontend"),
        ("package.json", "root"),
    ):
        pkg = _read_package_json(project, pkg_path)
        if not pkg:
            continue
        deps = {
            **pkg.get("dependencies", {}),
            **pkg.get("devDependencies", {}),
        }
        dep_names = " ".join(deps.keys()).lower()
        if "express" in dep_names:
            hints["backend_frameworks"] = list(hints.get("backend_frameworks", [])) + ["express"]
        if "fastapi" in dep_names or "uvicorn" in dep_names:
            hints["backend_frameworks"] = list(hints.get("backend_frameworks", [])) + ["fastapi"]
        if "react" in dep_names:
            hints["frontend_frameworks"] = list(hints.get("frontend_frameworks", [])) + ["react"]
        if "next" in dep_names:
            hints["frontend_frameworks"] = list(hints.get("frontend_frameworks", [])) + ["next"]
        if "vite" in dep_names:
            hints["build_tools"] = list(hints.get("build_tools", [])) + ["vite"]
        if "supabase" in dep_names:
            hints["databases"] = list(hints.get("databases", [])) + ["supabase"]

    if any(p.endswith("frontend/vite.config.ts") for p in paths):
        build = list(hints.get("build_tools", []))
        if "vite" not in build:
            hints["build_tools"] = build + ["vite"]
    if any(p.endswith("backend/src/server.ts") for p in paths):
        bf = list(hints.get("backend_frameworks", []))
        if "express" not in bf:
            hints["backend_frameworks"] = bf + ["express (inferred from server.ts)"]

    python_manifest = _read_text_blob(project, ("backend/pyproject.toml", "pyproject.toml", "backend/requirements.txt", "requirements.txt"))
    if python_manifest:
        blob = python_manifest.lower()
        bf = list(hints.get("backend_frameworks", []))
        if "fastapi" in blob or "uvicorn" in blob:
            if "fastapi" not in " ".join(bf).lower():
                hints["backend_frameworks"] = bf + ["fastapi"]
        if "sqlalchemy" in blob or "alembic" in blob:
            dbs = list(hints.get("databases", []))
            if "sqlalchemy" not in " ".join(dbs).lower():
                hints["databases"] = dbs + ["sqlalchemy"]

    hints["source_file_count"] = count_source_files(project)
    return hints


def _read_text_blob(project: ProjectContext, rel_paths: tuple[str, ...]) -> str:
    for rel in rel_paths:
        for f in project.files:
            if f.path.replace("\\", "/").strip("/") == rel and (f.content or f.preview):
                return f.content or f.preview
    return ""


def count_source_files(project: ProjectContext) -> int:
    return sum(
        1
        for f in project.files
        if os.path.splitext(f.path)[1].lower() in SOURCE_EXTENSIONS
    )


def build_folder_file_counts(project: ProjectContext, top_n: int = 12) -> str:
    """Summarize file counts per directory for LLM context."""
    counts: Counter[str] = Counter()
    for f in project.files:
        p = f.path.replace("\\", "/").strip("/")
        parent = "/".join(p.split("/")[:-1]) or "(root)"
        counts[parent] += 1
    lines = ["Per-folder file counts (top directories):"]
    for folder, n in counts.most_common(top_n):
        lines.append(f"  - {folder}/: {n} file(s)")
    return "\n".join(lines)


def detect_entry_points(project: ProjectContext) -> list[str]:
    """Known bootstrap / routing entry files."""
    candidates = {
        "backend/src/index.ts",
        "backend/src/server.ts",
        "backend/src/main.py",
        "backend/app/main.py",
        "frontend/src/main.tsx",
        "frontend/src/App.tsx",
        "frontend/src/app/layout.tsx",
    }
    paths = set(_norm_paths(project))
    found = sorted(p for p in candidates if p in paths)
    for f in project.files:
        if f.is_entrypoint:
            p = f.path.replace("\\", "/").strip("/")
            if p not in found:
                found.append(p)
    return found


def build_import_hub_summary(project: ProjectContext, top_n: int = 8) -> str:
    """Files with the most local imports — likely architectural hubs."""
    import_counts: Counter[str] = Counter()
    for f in project.files:
        ext = os.path.splitext(f.path)[1].lower()
        if ext not in {".ts", ".tsx", ".js", ".jsx", ".py"} or not f.content:
            continue
        rel = f.path.replace("\\", "/").strip("/")
        local_imports = [
            m.group(1)
            for m in IMPORT_RE.finditer(f.content)
            if m.group(1).startswith(".")
        ]
        if local_imports:
            import_counts[rel] += len(local_imports)

    if not import_counts:
        # Path-based hub heuristic when file content is unavailable
        for p in _norm_paths(project):
            name = os.path.basename(p).lower()
            if name in {"monitor.ts", "server.ts", "index.ts", "dashboard.tsx", "app.tsx"}:
                import_counts[p] += 5

    if not import_counts:
        return "Import hub summary: unavailable (no parseable source content)."

    lines = ["High-coupling hub files (many local imports — group these in domain modules):"]
    for path, n in import_counts.most_common(top_n):
        lines.append(f"  - {path}: ~{n} local import(s)")
    return "\n".join(lines)


def format_stack_block(project: ProjectContext, profile: str) -> str:
    """Human-readable stack + size block for the LLM user prompt."""
    hints = detect_stack_hints(project)
    src_count = hints.get("source_file_count", 0)
    size_band = "small" if src_count < 80 else "medium" if src_count < 300 else "large"

    lines = [
        f"Detected layout profile: {profile}",
        f"Source file count: {src_count} ({size_band} project — right-size recommendations)",
        f"Backend frameworks: {', '.join(hints.get('backend_frameworks', [])) or 'unknown'}",
        f"Frontend frameworks: {', '.join(hints.get('frontend_frameworks', [])) or 'unknown'}",
        f"Build tools: {', '.join(hints.get('build_tools', [])) or 'unknown'}",
        f"Entry points: {', '.join(detect_entry_points(project)) or 'none detected'}",
        "",
        build_folder_file_counts(project),
        "",
        build_import_hub_summary(project),
    ]
    return "\n".join(lines)


def _strip_tree_decorations(line: str) -> str:
    return line.strip().lstrip("│├└─ ").strip()


def _fenced_tree_body(text: str) -> str:
    if "```" not in text:
        return text
    parts = text.split("```")
    if len(parts) < 2:
        return text
    body = parts[1]
    if body.lstrip().startswith("text"):
        body = body.lstrip()[4:]
    return body


def _ascii_tree_depth(line: str) -> int | None:
    """
    Depth of an ASCII tree row (├── / └──).
    Bare 'backend/' at column 0 → 0.
    '├── docs/' under a root → 1; '│   └── file' → 2.
    """
    m = re.match(r"^([\s│]*)(?:├──|└──)\s+(.+)$", line)
    if m:
        prefix = m.group(1).replace("│", " ")
        # Connector rows are always nested under a parent (bare root or prior folder).
        return len(prefix) // 4 + 1
    # Root-ish entry without connector: "backend/" or "repository/"
    if re.match(r"^[A-Za-z0-9_.@+-]+/?\s*$", line.strip()):
        return 0
    return None


def extract_paths_from_tree(text: str) -> list[str]:
    """Best-effort extraction of file paths from a markdown directory tree.

    Supports:
      - flat full paths: backend/src/task/create/foo.ts
      - nested ASCII trees: backend/ → src/ → task/ → create/ → foo.ts
    """
    paths: list[str] = []
    stack: list[str] = []  # directory names at each depth

    for line in _fenced_tree_body(text).splitlines():
        if "→" in line or "->" in line:
            continue
        raw = line.rstrip("\n")
        if not raw.strip() or raw.strip().startswith("#") or raw.strip().startswith("```"):
            continue
        stripped = _strip_tree_decorations(raw)
        if not stripped:
            continue
        if stripped.startswith("- ") or stripped.startswith("* "):
            continue

        # Already a full path leaf (common in LLM / list output)
        if "/" in stripped and not stripped.endswith("/") and "." in os.path.basename(stripped):
            if re.match(r"^(backend|frontend|src|app)/", stripped.replace("\\", "/")):
                paths.append(stripped.replace("\\", "/"))
                continue
            # Other absolute-ish inventory paths
            if stripped.count("/") >= 1 and not stripped.startswith("├") and "──" not in raw:
                # Only treat as full path when the raw line had little tree chrome
                if _ascii_tree_depth(raw) is None and not raw.lstrip().startswith(("│", "├", "└")):
                    paths.append(stripped.replace("\\", "/"))
                    continue

        depth = _ascii_tree_depth(raw)
        if depth is None:
            # Fallback: treat as depth-0 name when it looks like a root folder
            if stripped.endswith("/") or "." not in os.path.basename(stripped.rstrip("/")):
                depth = 0
            else:
                # orphan file name — attach to current stack if any
                if stack and "." in os.path.basename(stripped):
                    paths.append("/".join(stack + [stripped.rstrip("/")]))
                elif "." in os.path.basename(stripped):
                    paths.append(stripped.replace("\\", "/"))
                continue

        name = stripped.rstrip("/")
        is_dir = stripped.endswith("/") or ("." not in os.path.basename(stripped))

        # Truncate stack to parent depth
        stack = stack[:depth]
        if is_dir:
            stack.append(name)
        else:
            paths.append("/".join(stack + [name]))

    return paths


def validate_recommended_structure(
    text: str,
    inventory_paths: set[str] | None = None,
    exclude_paths: set[str] | None = None,
    *,
    structure_style: str | None = None,
    enforce_quality_gate: bool = False,
) -> list[str]:
    """
    Validate LLM recommended_structure for common anti-patterns.
    Returns a list of issue descriptions (empty = valid).

    For action_api style, consolidatable top-level roots (docs, scripts,
    templates-src, …) may be folded under backend/ or frontend/ and do not
    need to remain top-level in the target tree.

    When enforce_quality_gate is True, also apply catalog/scatter/verb-purity checks.
    """
    from repoaudit.audit.structure_style import (
        CONSOLIDATABLE_ROOTS,
        DEFAULT_STRUCTURE_STYLE,
        PRODUCT_ROOTS,
        STRUCTURE_STYLE_CONSERVATIVE,
    )

    style = structure_style or DEFAULT_STRUCTURE_STYLE
    issues: list[str] = []
    if re.search(r"[<{](?:feature|action)(?:_name)?[>}]|modules/<[^>/]+>", text, re.IGNORECASE):
        issues.append("Recommended tree contains placeholder tokens like <feature> — use real filenames")

    paths = extract_paths_from_tree(text)
    if not paths:
        if text.strip():
            issues.append("Recommended tree has no identifiable file leaves.")
        return issues

    joined = " ".join(paths).lower()
    has_pages = any("/pages/" in p or p.startswith("pages/") for p in paths)
    has_features = any("/features/" in p for p in paths)
    has_feature_action = any(
        re.search(r"(?:frontend|backend)/src/[^/]+/[^/]+/", p) is not None
        for p in paths
    )
    has_app_nested = any("/app/dashboard/" in p or "/app/settings/" in p for p in paths)
    if has_pages and (has_features or has_feature_action or has_app_nested):
        issues.append(
            "Hybrid frontend layout: recommended tree mixes pages/ with feature/action folders — "
            "use exactly ONE routing pattern"
        )
        by_basename: dict[str, list[str]] = defaultdict(list)
        for p in paths:
            by_basename[os.path.basename(p)].append(p)
        for basename, locs in by_basename.items():
            if len(locs) > 1 and os.path.splitext(basename)[1].lower() in SOURCE_EXTENSIONS | {".css", ".html"}:
                issues.append(
                    f"Duplicate destination for '{basename}': {', '.join(locs)} "
                    "(pick exactly one location per file)"
                )

    if "src/lib/scripts" in joined or "src/scripts/" in joined:
        issues.append(
            "CLI/maintenance scripts belong in backend/scripts/ (outside src/), not under src/lib/scripts/"
        )

    # Single-file folder: dirname matches filename stem
    # Action-api leaf folders (..._api / create / update) are allowed even with one file.
    dir_files: dict[str, list[str]] = defaultdict(list)
    for p in paths:
        parent = os.path.dirname(p)
        dir_files[parent].append(os.path.basename(p))

    action_leaf_names = {
        "components",
        "hooks",
        "lib",
        "shared",
        "common",
        "types",
        "views",
        "routes",
        "services",
        "schemas",
        "create",
        "update",
        "delete",
        "list",
        "get",
        "login",
        "signup",
        "settings",
        "auth",
        "run",
        "scan",
        "audit",
        "core",
        "public",
        "preview",
        "export",
        "upload",
        "catalog",
        "memory",
        "session",
        "ui",
        "api",
        "db",
    }
    for folder, files in dir_files.items():
        if len(files) != 1:
            continue
        fname = files[0]
        stem = os.path.splitext(fname)[0].lower()
        folder_name = os.path.basename(folder).lower()
        # Action folders (create/, login/, shared/, …_api) are allowed with one file.
        if folder_name.endswith("_api") or folder_name in action_leaf_names:
            continue
        parent_parts = folder.replace("\\", "/").split("/")
        # .../src/{feature}/{action}/file — action leaf under src is intentional
        if len(parent_parts) >= 3 and parent_parts[-3] == "src":
            continue
        if stem == folder_name and folder_name not in action_leaf_names:
            issues.append(
                f"Over-nested single-file folder: {folder}/{fname} "
                "(flatten or group related modules together)"
            )

    if "backend/src/app/" in joined and "express" in joined:
        issues.append(
            "Express/Node backend should use src/integrations/ and src/domain/, not src/app/ "
            "(src/app/ is for Next.js-style frontends or FastAPI app packages)"
        )

    exclude = {p.replace("\\", "/").strip("/") for p in (exclude_paths or set())}
    tree_body = _fenced_tree_body(text).replace("\\", "/")
    tree_lower = tree_body.lower()
    for dead in sorted(exclude):
        if dead and dead in tree_body:
            issues.append(f"Dead file '{dead}' must be omitted from the recommended target")

    live_inventory = {
        p.replace("\\", "/").strip("/")
        for p in (inventory_paths or set())
        if p.replace("\\", "/").strip("/") not in exclude
    }
    if live_inventory:
        inventory_roots = {
            p.split("/", 1)[0]
            for p in live_inventory
            if "/" in p and not p.startswith(".")
        }

        def _root_present(root: str) -> bool:
            r = root.lower()
            return f"{r}/" in tree_lower or f"\n{r}\n" in tree_lower or tree_lower.startswith(f"{r}/")

        # Product roots that exist today must appear in the target.
        for root in sorted(inventory_roots & PRODUCT_ROOTS):
            if not _root_present(root):
                issues.append(
                    f"Recommended tree omits product root '{root}/' "
                    "(target should keep backend/ and frontend/ when they exist)"
                )

        if style == STRUCTURE_STYLE_CONSERVATIVE:
            # Old behavior: every live top-level root must remain top-level.
            for root in sorted(inventory_roots):
                if not _root_present(root):
                    issues.append(
                        f"Recommended tree omits top-level '{root}/' (must cover the whole repository)"
                    )
        else:
            # action_api: consolidatable roots may move under backend/ or frontend/.
            for root in sorted(inventory_roots - PRODUCT_ROOTS):
                if root.lower() in CONSOLIDATABLE_ROOTS:
                    continue
                if not _root_present(root):
                    issues.append(
                        f"Recommended tree omits top-level '{root}/' "
                        "(non-consolidatable root must stay visible or be renamed under backend/frontend)"
                    )

        if style != STRUCTURE_STYLE_CONSERVATIVE:
            issues.extend(
                _action_api_reorg_issues(
                    paths=paths,
                    tree_lower=tree_lower,
                    live_inventory=live_inventory,
                )
            )

    if enforce_quality_gate and style != STRUCTURE_STYLE_CONSERVATIVE:
        from repoaudit.audit.structure_tree_quality import quality_issues_for_validation

        issues.extend(quality_issues_for_validation(text))

    return issues


def _is_top_level_root_in_tree(tree_lower: str, root: str, paths: list[str] | None = None) -> bool:
    """True when root is a sibling of backend/frontend, not nested under them."""
    r = root.lower().rstrip("/")
    # Already folded under a product root.
    if f"backend/{r}/" in tree_lower or f"frontend/{r}/" in tree_lower:
        return False
    if f"backend/{r}\n" in tree_lower or f"frontend/{r}\n" in tree_lower:
        return False

    # Full path leaves: docs/foo.md is top-level; backend/docs/foo.md is not.
    if paths:
        for p in paths:
            pl = p.replace("\\", "/").lower().strip("/")
            if pl == r or pl.startswith(f"{r}/"):
                return True

    # repository/ wrapper style: ├── docs/ next to ├── backend/
    if re.search(r"(?m)^[├└]──\s*backend/", tree_lower) and re.search(
        rf"(?m)^[├└]──\s*{re.escape(r)}/", tree_lower
    ):
        return True

    # Bare path list / heading: docs/... at column 0
    if re.search(rf"(?m)^{re.escape(r)}/", tree_lower):
        return True
    return False


def _path_has_type_bucket(path: str) -> bool:
    parts = path.replace("\\", "/").lower().split("/")
    # Ignore product-root config and entry files
    if len(parts) <= 2:
        return False
    # backend/src/services/foo.ts or frontend/src/components/x.tsx
    for i, part in enumerate(parts):
        if part in TYPE_BUCKET_SEGMENTS:
            # Allow .../shared/lib/... or .../common/utils/... only at the end shared zone
            if part in {"lib", "utils", "helpers"} and i >= 1 and parts[i - 1] in {
                "shared",
                "common",
            }:
                continue
            # frontend/src/features/... is OK even if deeper has no type bucket
            if "features" in parts[:i]:
                # type bucket under features is still wrong (features/auth/components)
                return True
            return True
    return False


def _count_feature_action_paths(paths: list[str], root: str) -> int:
    """Count files under root/src/FEATURE/ACTION/ or root/src/features/FEATURE/ACTION/."""
    n = 0
    prefix = f"{root}/src/"
    for p in paths:
        pl = p.replace("\\", "/").lower()
        if not pl.startswith(prefix):
            continue
        rest = pl[len(prefix) :]
        segs = [s for s in rest.split("/") if s]
        if len(segs) < 3:
            continue
        # features/FEATURE/ACTION/file
        if segs[0] == "features" and len(segs) >= 4:
            if segs[1] not in TYPE_BUCKET_SEGMENTS and segs[2] not in TYPE_BUCKET_SEGMENTS:
                n += 1
            continue
        # FEATURE/ACTION/file
        if segs[0] not in TYPE_BUCKET_SEGMENTS and segs[1] not in TYPE_BUCKET_SEGMENTS:
            n += 1
    return n


def _action_api_reorg_issues(
    *,
    paths: list[str],
    tree_lower: str,
    live_inventory: set[str],
) -> list[str]:
    """Reject copy-current / type-bucket / unfolded consolidatable layouts."""
    issues: list[str] = []

    for root in sorted(MUST_FOLD_TOP_LEVEL):
        if _is_top_level_root_in_tree(tree_lower, root, paths):
            # Also present in inventory as top-level → must fold
            if any(p.split("/", 1)[0].lower() == root for p in live_inventory if "/" in p):
                dest = "backend/docs/" if root in {"docs", "doc"} else (
                    "frontend/src/templates/catalog/" if "template" in root else "backend/ or frontend/"
                )
                issues.append(
                    f"Top-level '{root}/' must be folded under {dest} — "
                    "do not leave it as a sibling of backend/frontend"
                )

    type_bucket_paths = [p for p in paths if _path_has_type_bucket(p)]
    # Only flag when many source files remain in type buckets
    source_buckets = [
        p
        for p in type_bucket_paths
        if os.path.splitext(p)[1].lower() in SOURCE_EXTENSIONS
    ]
    if len(source_buckets) >= 3:
        sample = ", ".join(source_buckets[:3])
        issues.append(
            "Proposed tree still organizes by technical type "
            f"(components/services/lib/hooks/…). Examples: {sample}. "
            "Regroup into Feature → Action folders instead."
        )

    has_backend = any(p.replace("\\", "/").lower().startswith("backend/") for p in paths)
    has_frontend = any(p.replace("\\", "/").lower().startswith("frontend/") for p in paths)
    be_src = [
        p
        for p in paths
        if p.lower().startswith("backend/src/")
        and os.path.splitext(p)[1].lower() in SOURCE_EXTENSIONS
    ]
    fe_src = [
        p
        for p in paths
        if p.lower().startswith("frontend/src/")
        and os.path.splitext(p)[1].lower() in SOURCE_EXTENSIONS
    ]
    be_fa = _count_feature_action_paths(paths, "backend")
    fe_fa = _count_feature_action_paths(paths, "frontend")
    if has_backend and len(be_src) >= 3 and be_fa < 2:
        issues.append(
            "Backend source files are not under Feature → Action folders "
            "(expected backend/src/FEATURE/ACTION/...)."
        )
    if has_frontend and len(fe_src) >= 3 and fe_fa < 2:
        issues.append(
            "Frontend source files are not under Feature → Action folders "
            "(expected frontend/src/FEATURE/ACTION/... or frontend/src/features/FEATURE/ACTION/...)."
        )

    # Same-as-current: most proposed leaves identical to inventory paths
    inv_norm = {p.replace("\\", "/").strip("/") for p in live_inventory}
    prop_norm = {p.replace("\\", "/").strip("/") for p in paths}
    if inv_norm and prop_norm:
        overlap = len(inv_norm & prop_norm)
        # If almost every proposed path is unchanged AND inventory had type buckets / fold roots
        needs_reorg = any(
            p.split("/", 1)[0].lower() in MUST_FOLD_TOP_LEVEL for p in inv_norm if "/" in p
        ) or any(_path_has_type_bucket(p) for p in inv_norm)
        if needs_reorg and overlap >= max(5, int(0.75 * len(prop_norm))):
            issues.append(
                "Proposed tree is too similar to the current inventory (copy-current). "
                "You must move files into Feature → Action folders and fold docs/scripts/templates-src."
            )

    return issues


def inventory_needs_reorganization(inventory_paths: set[str] | list[str]) -> bool:
    """True when action_api should require real folder_changes."""
    paths = [p.replace("\\", "/").strip("/") for p in inventory_paths]
    if any(p.split("/", 1)[0].lower() in MUST_FOLD_TOP_LEVEL for p in paths if "/" in p):
        return True
    if sum(1 for p in paths if _path_has_type_bucket(p)) >= 3:
        return True
    return False


def validate_folder_changes_payload(
    folder_changes: object,
    *,
    inventory_paths: set[str] | None = None,
    structure_style: str | None = None,
) -> list[str]:
    """Require a real move map when the inventory still needs reorganization."""
    from repoaudit.audit.structure_style import (
        DEFAULT_STRUCTURE_STYLE,
        STRUCTURE_STYLE_CONSERVATIVE,
    )

    style = structure_style or DEFAULT_STRUCTURE_STYLE
    if style == STRUCTURE_STYLE_CONSERVATIVE:
        return []
    inventory = {p.replace("\\", "/").strip("/") for p in (inventory_paths or set())}
    if not inventory_needs_reorganization(inventory):
        return []

    issues: list[str] = []
    if not isinstance(folder_changes, list) or len(folder_changes) < 3:
        issues.append(
            "folder_changes must list at least 3 real file moves "
            "(from_path → to_path) — copying the current tree is not enough"
        )
        return issues

    moved = 0
    for item in folder_changes:
        if not isinstance(item, dict):
            continue
        src = str(item.get("from_path") or item.get("from") or "").replace("\\", "/").strip("/")
        dest = str(item.get("to_path") or item.get("to") or "").replace("\\", "/").strip("/")
        if src and dest and src != dest:
            moved += 1
    if moved < 3:
        issues.append(
            "folder_changes must include at least 3 paths that actually change location"
        )
    return issues


def build_profile_aware_structure(
    project: ProjectContext,
    profile: str,
    exclude_paths: set[str] | None = None,
    structure_style: str | None = None,
) -> str:
    """
    Whole-repository target tree with file leaves.
    Dead files (and folders that become empty) are omitted.
    """
    from repoaudit.audit.structure_target import build_whole_repo_structure

    return build_whole_repo_structure(
        project, profile, exclude_paths, structure_style=structure_style
    )


def _feature_from_filename(filename: str) -> str:
    stem = os.path.splitext(filename)[0].lower().replace("-", "_")
    parts = [p for p in stem.split("_") if p]
    return parts[0] if parts else "common"


def _map_backend_path(rel: str) -> str:
    lower = rel.lower()
    fname = os.path.basename(rel)
    if lower.startswith("backend/scripts/"):
        return rel
    if lower.startswith("backend/supabase/") or lower.startswith("supabase/"):
        return rel if lower.startswith("backend/") else f"backend/{rel}"
    if any(v in lower for v in ("/amos/", "amos/", "maestral/", "/google/", "/email/")):
        if "amos" in lower:
            vendor = "amos"
        elif "maestral" in lower:
            vendor = "maestral"
        elif "google" in lower:
            vendor = "google"
        else:
            vendor = "email"
        return f"backend/src/integrations/{vendor}/{fname}"
    if any(v in lower for v in ("detector", "notify", "events", "stopthreshold")):
        return f"backend/src/domain/alerts/{fname}"
    if any(v in lower for v in ("monitor", "watchlist", "index.ts")):
        return f"backend/src/domain/monitor/{fname}"
    if any(v in lower for v in ("eta", "match", "gpsactiveload", "loadmilestone", "companyyard")):
        return f"backend/src/domain/tracking/{fname}"
    if any(v in lower for v in ("geo", "time")):
        return f"backend/src/lib/{fname}"
    if fname in {"config.ts", "store.ts", "server.ts"}:
        return f"backend/src/{fname}"
    if lower.startswith("backend/src/"):
        return f"backend/src/domain/{_feature_from_filename(fname)}/{fname}"
    return rel


def _map_frontend_path(rel: str, use_features: bool) -> str:
    lower = rel.lower()
    fname = os.path.basename(rel)
    if not lower.startswith("frontend/src/"):
        return rel
    if fname in {"main.tsx", "App.tsx", "styles.css", "types.ts", "util.ts"}:
        if fname in {"types.ts", "util.ts"}:
            return f"frontend/src/shared/{fname}"
        return f"frontend/src/{fname}"

    if "/pages/settings" in lower or fname.lower() == "settings.tsx":
        return f"frontend/src/features/settings/{fname}" if use_features else rel

    if "/pages/status" in lower or "statusguide" in fname.lower().replace("-", ""):
        return f"frontend/src/features/status-guide/{fname}" if use_features else rel

    dashboard_only = (
        "fleettable", "statcards", "timeline", "toolbar", "pagination",
        "dashboard", "loadtimeline",
    )
    shared_components = ("header", "notification", "pagination")
    if any(k in lower.replace("-", "").replace("_", "") for k in dashboard_only):
        if use_features:
            sub = "components" if "/components/" in lower or fname.endswith(".tsx") else "hooks"
            if "/hooks/" in lower:
                sub = "hooks"
            if "/pages/dashboard" in lower:
                return f"frontend/src/features/dashboard/{fname}"
            return f"frontend/src/features/dashboard/{sub}/{fname}"
        return rel

    if any(k in lower for k in shared_components):
        return f"frontend/src/shared/components/{fname}"

    if "/hooks/" in lower:
        return f"frontend/src/shared/hooks/{fname}"

    if "/pages/" in lower and use_features:
        page = _feature_from_filename(fname)
        return f"frontend/src/features/{page}/{fname}"

    if "/api/" in lower:
        return f"frontend/src/shared/api/{fname}"

    return rel


def build_inventory_tree(project: ProjectContext, max_files_per_dir: int = 8, max_lines: int = 220) -> str:
    """Build a folder tree with multiple file leaves from the real inventory."""
    paths = sorted({f.path.replace("\\", "/") for f in project.files})
    by_dir: dict[str, list[str]] = defaultdict(list)
    dirs: set[str] = set()
    for p in paths:
        parts = p.split("/")
        for i in range(1, len(parts)):
            dirs.add("/".join(parts[:i]))
        parent = "/".join(parts[:-1]) if len(parts) > 1 else ""
        by_dir[parent].append(parts[-1])

    lines = ["```text", "repository/"]

    def _render(prefix: str, depth: int) -> None:
        if len(lines) >= max_lines:
            return

        if prefix:
            children_dirs = sorted(
                d for d in dirs
                if d.startswith(prefix + "/") and d.count("/") == prefix.count("/") + 1
            )
        else:
            children_dirs = sorted(d for d in dirs if "/" not in d)

        files_here = sorted(by_dir.get(prefix, []))
        shown = files_here[:max_files_per_dir]
        indent = "│   " * depth
        for fname in shown:
            if len(lines) >= max_lines:
                return
            lines.append(f"{indent}├── {fname}")
        extra = len(files_here) - len(shown)
        if extra > 0 and len(lines) < max_lines:
            lines.append(f"{indent}├── … (+{extra} more files)")

        for d in children_dirs:
            if len(lines) >= max_lines:
                return
            name = d.split("/")[-1]
            lines.append(f"{indent}├── {name}/")
            _render(d, depth + 1)

    _render("", 0)
    lines.append("```")
    return "\n".join(lines)


