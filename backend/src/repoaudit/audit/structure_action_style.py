"""Feature → action → files destinations for structure_style=action_api.

Hierarchy (Main Folder → Feature → Action → Files):

  backend/src/FEATURE/ACTION/...
  frontend/src/FEATURE/ACTION/...

Do not organize primarily by technical type (components/, services/, hooks/).
Do not invent folders by chopping camelCase leftovers.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from repoaudit.audit.structure_catalog import (
    ALLOWED_ACTIONS,
    JUNK_ACTION_NAMES,
    canonicalize_feature,
    feature_in_catalog,
    is_utility_stem,
    match_compound,
    normalize_action,
    strip_type_suffix,
    strip_ui_suffix_tokens,
)
from repoaudit.audit.structure_style import (
    CONSOLIDATABLE_ROOTS,
    PRODUCT_ROOT_CONFIG_FILES,
    PRODUCT_ROOTS,
)

SOURCE_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".py", ".mjs", ".cjs"}

ACTION_ALIASES = {
    "create": "create",
    "add": "create",
    "new": "create",
    "insert": "create",
    "update": "update",
    "edit": "update",
    "patch": "patch",
    "modify": "update",
    "delete": "delete",
    "remove": "delete",
    "destroy": "delete",
    "list": "list",
    "index": "list",
    "get": "get",
    "view": "view",
    "show": "get",
    "detail": "get",
    "share": "share",
    "send": "send",
    "export": "export",
    "import": "import",
    "upload": "upload",
    "download": "download",
    "sign": "sign",
    "auth": "login",
    "login": "login",
    "logout": "logout",
    "signup": "signup",
    "register": "signup",
    "forgot": "forgot_password",
    "reset": "reset_password",
    "settings": "settings",
    "config": "settings",
    "analytics": "stats",
    "memory": "memory",
    "generate": "generate",
    "render": "render",
    "preview": "preview",
    "run": "run",
    "scan": "scan",
    "audit": "audit",
    "track": "track",
    "provision": "provision",
    "public": "public",
    "catalog": "catalog",
    "dossier": "dossier",
    "stats": "stats",
    "engagement": "engagement",
    "workspace": "workspace",
    "store": "store",
    "extract": "extract",
    "followup": "followup",
    "session": "session",
}

# Path / filename tokens that are technical roles, not features or actions.
ROLE_NAMES = {
    "route",
    "routes",
    "router",
    "handler",
    "handlers",
    "service",
    "services",
    "schema",
    "schemas",
    "model",
    "models",
    "controller",
    "controllers",
    "dto",
    "validator",
    "middleware",
    "test",
    "tests",
    "spec",
    "utils",
    "util",
    "helper",
    "helpers",
    "types",
    "type",
    "index",
    "page",
    "pages",
    "view",
    "views",
    "hook",
    "hooks",
    "component",
    "components",
    "api",
    "lib",
    "shared",
    "common",
    "public",
    "assets",
    "styles",
    "style",
    "css",
    "store",
    "stores",
    "context",
    "contexts",
    "provider",
    "providers",
    "module",
    "modules",
    "feature",
    "features",
    "domain",
    "integrations",
    "integration",
    "interface",
    "interfaces",
    "src",
    "app",
    "backend",
    "frontend",
    "layout",
    "layouts",
    "client",
    "server",
    "data",
}

# Folder names skipped when walking a path for feature names.
SKIP_PATH_PARTS = ROLE_NAMES | {
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    "coverage",
    "static",
    "templates",
}


@dataclass(frozen=True)
class FeatureAction:
    feature: str
    action: str
    role: str  # route | service | schema | test | view | hook | other


def _norm(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def _stem(filename: str) -> str:
    name = os.path.basename(filename)
    for suffix in (".test", ".spec"):
        if name.lower().endswith(suffix + os.path.splitext(name)[1].lower()):
            base = name[: -len(os.path.splitext(name)[1])]
            if base.lower().endswith(suffix):
                return base[: -len(suffix)]
    return os.path.splitext(name)[0]


def _tokens(stem: str) -> list[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", stem)
    spaced = spaced.replace("-", "_").replace(".", "_")
    return [t.lower() for t in spaced.split("_") if t]


def _strip_hook_prefix(tokens: list[str]) -> list[str]:
    """useCreateTask → create, task (drop leading 'use')."""
    if tokens and tokens[0] == "use" and len(tokens) > 1:
        return tokens[1:]
    return tokens


def _infer_role(path: str, tokens: list[str]) -> str:
    lower = path.lower()
    fname = os.path.basename(path).lower()
    if ".test." in fname or ".spec." in fname or fname.startswith("test_"):
        return "test"
    if any(t in {"route", "routes", "router", "handler", "handlers"} for t in tokens) or "/routes/" in lower:
        return "route"
    if any(t in {"service", "services"} for t in tokens) or "/services/" in lower:
        return "service"
    if any(t in {"schema", "schemas", "model", "dto", "controller"} for t in tokens):
        return "schema"
    if fname.startswith("use") or "/hooks/" in lower:
        return "hook"
    if fname.endswith((".tsx", ".jsx")) and any(t in {"page", "view"} for t in tokens):
        return "view"
    if fname.endswith((".tsx", ".jsx")):
        return "view"
    return "other"


def _clean_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value).strip("_") or "shared"


def _pick_action(tokens: list[str], feature: str) -> str | None:
    """First real action verb in tokens that is not the feature name."""
    for t in tokens:
        if t == feature or t in ROLE_NAMES or t in JUNK_ACTION_NAMES:
            continue
        if t in ACTION_ALIASES:
            mapped = ACTION_ALIASES[t]
            if mapped != feature and mapped not in JUNK_ACTION_NAMES:
                return mapped
        if t in ALLOWED_ACTIONS and t not in JUNK_ACTION_NAMES:
            return t
    return None


def _pick_feature_from_tokens(tokens: list[str]) -> str | None:
    """Prefer a catalog-canonical noun that is not an action verb or role."""
    cleaned = strip_ui_suffix_tokens(tokens)
    for t in cleaned:
        if t in ROLE_NAMES or t in ACTION_ALIASES or t in JUNK_ACTION_NAMES:
            continue
        canon = canonicalize_feature(t)
        if canon:
            return canon
    # Fall back: noun after an action (createTask → task)
    for i, t in enumerate(cleaned):
        if t in ACTION_ALIASES and i + 1 < len(cleaned):
            nxt = cleaned[i + 1]
            if nxt not in ROLE_NAMES and nxt not in ACTION_ALIASES and nxt not in JUNK_ACTION_NAMES:
                return canonicalize_feature(nxt) or nxt
    return None


def _feature_from_path(parts: list[str]) -> str | None:
    for part in parts:
        clean = part.lower().replace("-", "_")
        if clean.endswith("_api"):
            clean = clean[: -len("_api")]
        clean = strip_type_suffix(clean)
        if clean in SKIP_PATH_PARTS:
            continue
        if any(clean.endswith(ext) for ext in SOURCE_EXTENSIONS):
            continue
        if clean:
            return canonicalize_feature(clean) or clean
    return None


AUTH_FEATURE_ACTIONS = frozenset(
    {"login", "logout", "signup", "auth", "forgot_password", "reset_password", "session"}
)


def _action_from_path_after_feature(parts: list[str], feature: str) -> str | None:
    """If path is .../{feature}/{action}/file, use that action folder when it is a real verb."""
    lowered = [strip_type_suffix(p.lower().replace("-", "_")) for p in parts]
    # Also accept alias path segment that maps to feature
    idx = -1
    for i, part in enumerate(lowered):
        if canonicalize_feature(part) == feature or part == feature:
            idx = i
            break
    if idx < 0:
        return None
    for part in lowered[idx + 1 :]:
        if any(part.endswith(ext) for ext in SOURCE_EXTENSIONS):
            break
        if part in SKIP_PATH_PARTS or part in JUNK_ACTION_NAMES:
            continue
        if part == feature or canonicalize_feature(part) == feature:
            continue
        if part in ACTION_ALIASES:
            return ACTION_ALIASES[part]
        if part in ALLOWED_ACTIONS:
            return part
        # Do not treat arbitrary path leftovers as actions
        return None
    return None


def infer_feature_action(
    path: str,
    *,
    catalog: list[str] | None = None,
) -> FeatureAction:
    """Best-effort feature + action from a file path/name (catalog-aware)."""
    path = _norm(path)
    stem = _stem(path)
    raw_tokens = _tokens(stem)
    tokens = _strip_hook_prefix(raw_tokens)
    role = _infer_role(path, raw_tokens)
    parts = [p for p in path.split("/") if p]

    # 1) Compound / known multi-word names (ThankYouPage, HighRidgeV4, …)
    compound = match_compound(stem)
    if compound:
        feature = feature_in_catalog(compound.feature, catalog)
        action = normalize_action(compound.action, feature)
        return FeatureAction(feature=feature, action=action, role=role)

    # 2) Utilities → shared/lib (never invent relative/time)
    if is_utility_stem(stem):
        return FeatureAction(feature="shared", action="lib", role=role)

    path_feature = _feature_from_path(parts)
    token_feature = _pick_feature_from_tokens(tokens)

    feature = path_feature or token_feature or "shared"
    if feature in ROLE_NAMES:
        feature = token_feature or "shared"
    # Filename entity when path only had technical folders (services/, pages/, …)
    if path_feature is None and token_feature:
        feature = token_feature
    elif path_feature in ROLE_NAMES and token_feature:
        feature = token_feature

    action_hint = _pick_action(tokens, feature or "shared")
    # LoginPage / SignupForm with no feature noun → auth (canonical)
    if (feature in {"shared", "common", None} or feature in ROLE_NAMES) and action_hint in AUTH_FEATURE_ACTIONS:
        feature = "auth"

    feature = canonicalize_feature(feature) or "shared"
    feature = feature_in_catalog(feature, catalog)
    feature = _clean_slug(feature)

    action = _action_from_path_after_feature(parts, feature)
    if action is None:
        action = action_hint or _pick_action(tokens, feature)
    # NEVER invent action from leftover camelCase tokens (thank/you, measure/in).
    action = normalize_action(action, feature)
    action = _clean_slug(action)
    if action == feature or action in JUNK_ACTION_NAMES:
        action = "lib" if feature == "shared" else "core"

    return FeatureAction(feature=feature, action=action, role=role)


def _role_filename(role: str, original: str) -> str:
    """Keep descriptive names; only normalize opaque role-only basenames."""
    fname = os.path.basename(original)
    stem = os.path.splitext(fname)[0].lower()
    if stem in ROLE_NAMES or stem in {"route", "service", "schema", "router", "handler", "page"}:
        ext = os.path.splitext(fname)[1] or ".ts"
        return {
            "route": f"route{ext}",
            "service": f"service{ext}",
            "schema": f"schema{ext}",
            "test": f"route.test{ext}" if ext in {".ts", ".js"} else f"test{ext}",
            "view": fname if fname.endswith((".tsx", ".jsx")) else f"Page{ext}",
            "hook": fname if fname.startswith("use") else f"useAction{ext}",
        }.get(role, fname)
    return fname


def suggest_action_api_path(
    path: str,
    *,
    catalog: list[str] | None = None,
) -> str:
    """
    Map a live inventory path to feature → action → files under backend/ or frontend/.
    Non-source / config files are consolidated under product roots when possible.
    """
    path = _norm(path)
    if not path:
        return path

    fname = os.path.basename(path)
    # Dotfiles / config at repo root stay put (LLM may still recommend per-root copies).
    if "/" not in path and (path.startswith(".") or fname in PRODUCT_ROOT_CONFIG_FILES):
        return path

    top = path.split("/", 1)[0]
    rest = path.split("/", 1)[1] if "/" in path else ""
    ext = os.path.splitext(fname)[1].lower()

    if top in PRODUCT_ROOTS:
        # Always keep product-root config at frontend/ or backend/ root — never under a feature.
        if fname in PRODUCT_ROOT_CONFIG_FILES and (
            not rest or rest == fname or "/" not in rest
        ):
            return f"{top}/{fname}"
        if fname in PRODUCT_ROOT_CONFIG_FILES and rest.count("/") == 0:
            return f"{top}/{fname}"

        if top == "backend":
            if rest.startswith("scripts/") or rest.startswith("assets/") or rest.startswith("docs/"):
                return path
            if fname in PRODUCT_ROOT_CONFIG_FILES:
                return f"backend/{fname}" if rest != fname else path
            if ext not in SOURCE_EXTENSIONS:
                return path
            if fname in {"index.ts", "server.ts", "main.ts", "main.py", "app.py"} and rest.count("/") <= 1:
                return f"backend/src/{fname}" if not rest.startswith("src/") else path

            fa = infer_feature_action(path, catalog=catalog)
            out_name = _role_filename(fa.role, fname)
            return f"backend/src/{fa.feature}/{fa.action}/{out_name}"

        # frontend
        if rest.startswith("public/"):
            return path
        if fname in PRODUCT_ROOT_CONFIG_FILES:
            return f"frontend/{fname}" if rest != fname else path
        if ext not in SOURCE_EXTENSIONS | {".css", ".json"}:
            return path
        if fname in {"main.tsx", "main.ts", "App.tsx", "App.jsx", "index.css", "vite-env.d.ts"}:
            return f"frontend/src/{fname}" if "src/" in path else path

        fa = infer_feature_action(path, catalog=catalog)
        out_name = _role_filename(fa.role, fname)
        # Keep CSS/JSON beside the feature action (no *_css feature folders)
        return f"frontend/src/{fa.feature}/{fa.action}/{out_name}"

    # Consolidate advisory roots
    if top.lower() in CONSOLIDATABLE_ROOTS or top.lower().replace("_", "-") in CONSOLIDATABLE_ROOTS:
        key = top.lower().replace("_", "-")
        if key in {"docs", "doc"}:
            return f"backend/docs/{rest}" if rest else "backend/docs/"
        if key in {"scripts", "script", "tools", "tooling"}:
            if "template" in path.lower() or "extract" in path.lower() or "dossier" in path.lower():
                return f"frontend/templates/catalog/{rest}" if rest else "frontend/templates/catalog/"
            return f"backend/scripts/{rest}" if rest else "backend/scripts/"
        if "template" in key:
            # Fold into templates/catalog (not a parallel template-sources root)
            return f"frontend/src/templates/catalog/{rest}" if rest else "frontend/src/templates/catalog/"
        return f"backend/{top}/{rest}" if rest else f"backend/{top}/"

    return path


def map_paths_action_api(
    paths: list[str],
    *,
    catalog: list[str] | None = None,
) -> list[tuple[str, str]]:
    """Return (src, dest) for paths that change under action_api style."""
    moves: list[tuple[str, str]] = []
    for src in paths:
        dest = suggest_action_api_path(src, catalog=catalog)
        if dest and dest != src:
            moves.append((src, dest))
    return moves
