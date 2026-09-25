"""Product feature catalog: aliases, compounds, utilities, discovery.

Rule of thumb:
  feature = product noun users care about (closed catalog when possible)
  action  = verb the code performs (never invent from camelCase leftovers)
"""

from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Canonical feature names (prefer short product nouns)
# ---------------------------------------------------------------------------

FEATURE_ALIASES: dict[str, str] = {
    # auth family → one root
    "auth": "auth",
    "authentication": "auth",
    "authorization": "auth",
    "signin": "auth",
    "sign_in": "auth",
    "signout": "auth",
    "sign_out": "auth",
    "session": "auth",
    "oauth": "auth",
    "supabase_auth": "auth",
    # proposals
    "proposal": "proposals",
    "proposals": "proposals",
    "proposal_creator": "proposals",
    "pitch": "proposals",
    "thank_you": "proposals",
    "thankyou": "proposals",
    "uploaded": "proposals",
    "upload": "proposals",
    # templates
    "template": "templates",
    "templates": "templates",
    "template_sources": "templates",
    "template_pipeline": "templates",
    "highridge": "templates",
    "highridgev4": "templates",
    "high_ridge": "templates",
    "high_ridge_v4": "templates",
    "ink": "templates",
    "ink_copper": "templates",
    "ink_copper_exact_css": "templates",
    "rootv1": "templates",
    "root_v1": "templates",
    "strategic": "templates",
    "strategicv3": "templates",
    "strategic_v3": "templates",
    "dossier": "templates",
    "renderers": "templates",
    "bones": "templates",
    "boneyard": "templates",
    "boneyard_config_json": "templates",
    # dashboard / analytics
    "dashboard": "dashboard",
    "analytics": "dashboard",
    "engagement": "dashboard",
    "metric": "dashboard",
    "metrics": "dashboard",
    "heatmap": "dashboard",
    "stats": "dashboard",
    # settings / memory
    "settings": "settings",
    "setting": "settings",
    "memory": "settings",
    "workspace": "settings",
    # integrations
    "integrations": "integrations",
    "integration": "integrations",
    "calendly": "integrations",
    "slack": "integrations",
    "google": "integrations",
    "gmail": "integrations",
    "drive": "integrations",
    "webhook": "integrations",
    "read_ai": "integrations",
    "readai": "integrations",
    # email
    "email": "email",
    "mail": "email",
    "followup": "email",
    "follow_up": "email",
    # tasks (generic demo / CRUD apps)
    "task": "task",
    "tasks": "task",
    # audit product domains (RepoAudit itself)
    "audit": "audit",
    "projects": "projects",
    "project": "projects",
    "repositories": "repositories",
    "repository": "repositories",
    "investigation": "investigation",
    "knowledge": "knowledge",
    "retrieval": "retrieval",
    "reports": "reports",
    "parser": "parser",
    "pipeline": "pipeline",
    "snapshots": "snapshots",
    "github": "integrations",
    "ai": "ai",
    "chat": "ai",
    # shared catch-alls
    "shared": "shared",
    "common": "shared",
    "utils": "shared",
    "util": "shared",
    "helpers": "shared",
    "helper": "shared",
    "lib": "shared",
}

# Strip these suffixes from folder/feature slugs (type encoded in name).
TYPE_SUFFIXES = (
    "_exact_css",
    "_bones_json",
    "_config_json",
    "_css",
    "_json",
    "_html",
    "_tsx",
    "_ts",
    "_jsx",
    "_js",
    "_py",
)

# Real action verbs / known UI actions (not layers/roles).
ALLOWED_ACTIONS: frozenset[str] = frozenset(
    {
        "create",
        "update",
        "delete",
        "list",
        "get",
        "view",
        "share",
        "send",
        "export",
        "import",
        "upload",
        "download",
        "sign",
        "login",
        "logout",
        "signup",
        "forgot_password",
        "reset_password",
        "session",
        "settings",
        "generate",
        "render",
        "preview",
        "run",
        "scan",
        "audit",
        "track",
        "provision",
        "patch",
        "export_pdf",
        "export_docx",
        "public",
        "catalog",
        "dossier",
        "stats",
        "engagement",
        "workspace",
        "memory",
        "store",
        "extract",
        "followup",
        "templates",
        "core",  # default when feature known but no verb
        "lib",  # shared utilities only
        "ui",
        "api",
        "db",
        "logger",
        # template variant actions (product sub-features as actions under templates/)
        "high_ridge_v4",
        "ink_copper",
        "root_v1",
        "strategic_v3",
        "thank_you",
    }
)

# Roles / layers that must NEVER be treated as actions.
JUNK_ACTION_NAMES: frozenset[str] = frozenset(
    {
        "shared",
        "common",
        "data",
        "layout",
        "layouts",
        "client",
        "server",
        "components",
        "component",
        "hooks",
        "hook",
        "services",
        "service",
        "utils",
        "util",
        "helpers",
        "helper",
        "types",
        "type",
        "styles",
        "style",
        "css",
        "assets",
        "pages",
        "page",
        "views",
        "view",
        "providers",
        "provider",
        "context",
        "contexts",
        "store",
        "stores",
        "models",
        "model",
        "controllers",
        "controller",
        "middleware",
        "dto",
        "schema",
        "schemas",
        "validator",
        "route",
        "routes",
        "router",
        "handler",
        "handlers",
        "index",
        "main",
        "app",
        "src",
        "test",
        "tests",
        "spec",
        "in",  # measure/in leftover
        "you",  # thank/you leftover
        "exact",
        "bones",
        "config",
        "v1",
        "v2",
        "v3",
        "v4",
    }
)

# Multi-word stems → (feature, action). Checked before naive token split.
# Keys are lowercase alphanumeric-only (underscores stripped for lookup).
COMPOUND_MAP: dict[str, tuple[str, str]] = {
    "thankyou": ("proposals", "public"),
    "thankyoupage": ("proposals", "public"),
    "measurein": ("shared", "lib"),
    "measureinview": ("shared", "lib"),
    "highridgev4": ("templates", "high_ridge_v4"),
    "highridge": ("templates", "high_ridge_v4"),
    "relativetime": ("shared", "lib"),
    "pegviewport": ("shared", "lib"),
    "inkcopper": ("templates", "ink_copper"),
    "inkcopperexactcss": ("templates", "ink_copper"),
    "inkcopperexact": ("templates", "ink_copper"),
    "forgotpassword": ("auth", "forgot_password"),
    "forgotpasswordpage": ("auth", "forgot_password"),
    "resetpassword": ("auth", "reset_password"),
    "resetpasswordpage": ("auth", "reset_password"),
    "signup": ("auth", "signup"),
    "signuppage": ("auth", "signup"),
    "signupform": ("auth", "signup"),
    "signin": ("auth", "login"),
    "signinpage": ("auth", "login"),
    "loginpage": ("auth", "login"),
    "loginform": ("auth", "login"),
    "logoutpage": ("auth", "logout"),
    "createtask": ("task", "create"),
    "createtaskpage": ("task", "create"),
    "usecreatetask": ("task", "create"),
    "taskroutes": ("task", "core"),
    "taskschema": ("task", "core"),
    "rootv1": ("templates", "root_v1"),
    "strategicv3": ("templates", "strategic_v3"),
}

# Filename stems (after stripping Page/View/…) that are utilities, not features.
UTILITY_STEM_RE = re.compile(
    r"^(relative|format|parse|clamp|debounce|throttle|memoize|cn|clsx|cx|"
    r"peg|scroll|viewport|observe|measure|uuid|slug|hash|encode|decode|"
    r"normalize|sanitize|truncate|pluralize|capitalize)",
    re.IGNORECASE,
)

UI_SUFFIXES = (
    "page",
    "view",
    "form",
    "modal",
    "dialog",
    "drawer",
    "panel",
    "widget",
    "component",
    "screen",
    "layout",
    "provider",
    "context",
    "hook",
    "route",
    "router",
    "service",
    "schema",
    "controller",
    "handler",
    "api",
    "test",
    "spec",
)

SOFT_FEATURE_CAP = 12
SOFT_FEATURE_MIN = 8


@dataclass(frozen=True)
class CatalogHit:
    feature: str
    action: str | None = None
    reason: str = ""


def _alnum_key(stem: str) -> str:
    return re.sub(r"[^a-z0-9]", "", stem.lower())


def strip_type_suffix(slug: str) -> str:
    """Remove file-type encodings from folder/feature names."""
    s = slug.lower().replace("-", "_")
    changed = True
    while changed:
        changed = False
        for suf in TYPE_SUFFIXES:
            if s.endswith(suf) and len(s) > len(suf):
                s = s[: -len(suf)].rstrip("_")
                changed = True
                break
    return s or slug


def canonicalize_feature(name: str | None) -> str | None:
    if not name:
        return None
    raw = name.lower().replace("-", "_").strip("_")
    raw = strip_type_suffix(raw)
    if raw in FEATURE_ALIASES:
        return FEATURE_ALIASES[raw]
    # Prefix / contains match for long folder names
    for alias, canonical in FEATURE_ALIASES.items():
        if raw.startswith(alias + "_") or raw.endswith("_" + alias):
            return canonical
    return raw


def strip_ui_suffix_tokens(tokens: list[str]) -> list[str]:
    out = list(tokens)
    while out and out[-1] in UI_SUFFIXES:
        out.pop()
    return out


def match_compound(stem: str) -> CatalogHit | None:
    key = _alnum_key(stem)
    if key.startswith("use") and len(key) > 3:
        key_no_use = key[3:]
    else:
        key_no_use = key
    for candidate in (key, key_no_use):
        if candidate in COMPOUND_MAP:
            feature, action = COMPOUND_MAP[candidate]
            return CatalogHit(feature=feature, action=action, reason="compound")
    # Strip common UI suffixes then retry
    tokens = re.findall(r"[a-z0-9]+", re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", stem).lower())
    if tokens and tokens[0] == "use":
        tokens = tokens[1:]
    stripped = strip_ui_suffix_tokens(tokens)
    if stripped:
        key2 = "".join(stripped)
        if key2 in COMPOUND_MAP:
            feature, action = COMPOUND_MAP[key2]
            return CatalogHit(feature=feature, action=action, reason="compound")
    return None


def is_utility_stem(stem: str) -> bool:
    key = _alnum_key(stem)
    if key.startswith("use") and len(key) > 3:
        key = key[3:]
    if key in COMPOUND_MAP and COMPOUND_MAP[key][0] == "shared":
        return True
    tokens = re.findall(r"[a-z0-9]+", re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", stem).lower())
    if tokens and tokens[0] == "use":
        tokens = tokens[1:]
    stripped = strip_ui_suffix_tokens(tokens)
    joined = "".join(stripped) if stripped else key
    if joined in {"relativetime", "pegviewport", "measurein", "measureinview"}:
        return True
    if stripped and UTILITY_STEM_RE.match(stripped[0] or ""):
        productish = {
            canonicalize_feature(t)
            for t in stripped
            if canonicalize_feature(t) and canonicalize_feature(t) not in {"shared", t}
        }
        productish.discard(None)
        # Also drop identity mappings where alias == token and not a known product canon
        productish = {p for p in productish if p in FEATURE_ALIASES.values() and p != "shared"}
        if not productish:
            return True
    return False


# Verb synonyms used when normalizing actions (kept here to avoid circular imports).
_ACTION_SYNONYMS: dict[str, str] = {
    "add": "create",
    "new": "create",
    "insert": "create",
    "edit": "update",
    "modify": "update",
    "remove": "delete",
    "destroy": "delete",
    "index": "list",
    "show": "get",
    "detail": "get",
    "view": "get",
    "register": "signup",
    "forgot": "forgot_password",
    "reset": "reset_password",
    "config": "settings",
    "auth": "login",
}


def normalize_action(action: str | None, feature: str) -> str:
    """Map action to an allowed verb; never return junk leftovers."""
    if not action:
        return "lib" if feature == "shared" else "core"
    a = action.lower().replace("-", "_").strip("_")
    a = strip_type_suffix(a)
    if a in JUNK_ACTION_NAMES or a == feature:
        return "lib" if feature == "shared" else "core"
    if a in _ACTION_SYNONYMS:
        a = _ACTION_SYNONYMS[a]
    if a in ALLOWED_ACTIONS:
        return a
    # Template variant slugs are allowed as actions under templates/
    if feature == "templates" and a and a not in JUNK_ACTION_NAMES:
        return a
    return "lib" if feature == "shared" else "core"


def discover_feature_catalog(paths: list[str], *, soft_cap: int = SOFT_FEATURE_CAP) -> list[str]:
    """
    Pass 1: closed list of product features from inventory paths/filenames.
    Merges synonyms via FEATURE_ALIASES; prefers high-frequency domains.
    """
    counts: Counter[str] = Counter()
    for path in paths:
        path = path.replace("\\", "/").strip("/")
        parts = [p for p in path.split("/") if p]
        stem = os.path.splitext(os.path.basename(path))[0]
        compound = match_compound(stem)
        if compound:
            counts[compound.feature] += 3
            continue
        if is_utility_stem(stem):
            counts["shared"] += 1
            continue
        # Path segments (skip technical roots)
        skip = {
            "backend",
            "frontend",
            "src",
            "app",
            "modules",
            "services",
            "routes",
            "hooks",
            "pages",
            "components",
            "lib",
            "utils",
            "schemas",
            "models",
            "controllers",
            "tests",
            "test",
            "public",
            "assets",
            "styles",
            "docs",
            "scripts",
            "node_modules",
            "features",
            "domain",
            "api",
            "v1",
            "shared",
            "common",
        }
        for part in parts[:-1]:
            clean = strip_type_suffix(part.lower().replace("-", "_"))
            if clean in skip or clean.endswith("_api"):
                continue
            canon = canonicalize_feature(clean)
            if canon and canon not in skip:
                counts[canon] += 2
        # Filename noun (first non-action token via compound / alias only)
        tokens = re.findall(
            r"[a-z0-9]+",
            re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", stem).lower(),
        )
        tokens = strip_ui_suffix_tokens(tokens)
        if tokens and tokens[0] == "use" and len(tokens) > 1:
            tokens = tokens[1:]
        for t in tokens:
            canon = canonicalize_feature(t)
            if canon and canon in FEATURE_ALIASES.values():
                counts[canon] += 1
                break

    # Cap product features; always keep shared available for utilities.
    ordered = [f for f, _ in counts.most_common() if f != "shared"]
    product = ordered[:soft_cap]
    if "shared" not in product:
        product.append("shared")
    return product or ["shared"]


def feature_in_catalog(feature: str, catalog: list[str] | None) -> str:
    """Snap feature onto catalog when provided; else canonicalize only."""
    canon = canonicalize_feature(feature) or "shared"
    if not catalog:
        return canon
    if canon in catalog:
        return canon
    # Fuzzy: alias target in catalog
    for c in catalog:
        if canonicalize_feature(c) == canon:
            return c
    return "shared"


def scatter_families() -> dict[str, set[str]]:
    """Canonical feature → set of alias spellings (for scatter detection)."""
    families: dict[str, set[str]] = defaultdict(set)
    for alias, canon in FEATURE_ALIASES.items():
        families[canon].add(alias)
        families[canon].add(canon)
    return dict(families)
