"""static rule auditor for repo folder structure enforcement."""

from __future__ import annotations

import os
from collections import defaultdict

from repoaudit.audit.structure_models import FolderViolation
from repoaudit.indexing.models import ProjectContext

# Standard whitelisted root files inside repository root or backend/frontend sub-roots
ALLOWED_ROOT_FILES = {
    ".gitignore",
    ".gitattributes",
    ".dockerignore",
    ".env",
    ".env.example",
    ".env.local",
    "README.md",
    "readme.md",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Dockerfile",
    "pyproject.toml",
    "requirements.txt",
    "tsconfig.json",
    "tsconfig.app.json",
    "tsconfig.node.json",
    "vite.config.ts",
    "vite.config.js",
    "vite.config.mts",
    "next.config.js",
    "next.config.mjs",
    "tailwind.config.js",
    "tailwind.config.ts",
    "postcss.config.js",
    "postcss.config.cjs",
    "index.html",
    "main.py",
    "run_dev.py",
    "alembic.ini",
    "setup.py",
    "pytest.ini",
    "tox.ini",
    "license",
    "LICENSE",
    "components.json",
    "Makefile",
    "makefile",
    "Cargo.toml",
    "go.mod",
}

ALLOWED_ROOT_DIRS = {"backend", "frontend"}

# Benign extra roots (docs, tooling) — advisory, not critical
ADVISORY_ROOT_DIRS = {
    "docs",
    "doc",
    "scripts",
    "script",
    "tools",
    "tooling",
    "ops",
    "infra",
    "infrastructure",
    "deploy",
    "deployment",
    "ci",
    "assets",
    "examples",
    "example",
    "samples",
    "notebooks",
    "data",
    "shared",
    "packages",
    "libs",
    "lib",
    "common",
    "config",
    "configs",
    "helm",
    "k8s",
    "terraform",
    "charts",
}

# Allowed first-level dirs inside backend/frontend (in addition to src/)
ALLOWED_TOP_SUBDIRS = {
    "tests",
    "test",
    "docs",
    "public",
    "alembic",
    "migrations",
    "static",
    "assets",
    "scripts",
    "bin",
    "config",
    "configs",
    "docker",
    "deploy",
    "locale",
    "locales",
    "types",
    "typings",
}

# Conventional app code layouts that should not flood medium violations
ALLOWED_SRC_PREFIXES = (
    "src/integrations/",
    "src/domain/",
    "src/app/services/",
    "src/app/modules/",
    "src/app/api/",
    "src/app/core/",
    "src/app/shared/",
    "src/app/components/",
    "src/app/pages/",
    "src/app/features/",
    "src/app/hooks/",
    "src/app/lib/",
    "src/app/utils/",
    "src/app/stores/",
    "src/app/router/",
    "src/app/services/",
    "src/components/",
    "src/pages/",
    "src/features/",
    "src/hooks/",
    "src/lib/",
    "src/utils/",
    "src/stores/",
    "src/router/",
    "src/routes/",
    "src/api/",
    "src/core/",
    "src/shared/",
    "src/types/",
    "src/styles/",
    "src/assets/",
    "src/config/",
    "src/contexts/",
    "src/providers/",
    "src/layouts/",
    "src/ui/",
)

# Package-style backends: backend/src/<pkg>/... or backend/app/...
ALLOWED_BACKEND_NON_SRC_PREFIXES = (
    "app/",
    "apps/",
)


def _feature_from_filename(filename: str) -> str:
    stem = os.path.splitext(filename)[0].lower().replace("-", "_")
    parts = [p for p in stem.split("_") if p]
    return parts[0] if parts else "common"


def _suggest_express_vite(rel_path: str, root_dir: str) -> str:
    filename = os.path.basename(rel_path)
    lower = rel_path.lower()
    if root_dir == "frontend":
        if any(k in lower for k in ("fleet", "stat", "timeline", "toolbar", "dashboard")):
            return f"frontend/src/features/dashboard/components/{filename}"
        if "settings" in lower:
            return f"frontend/src/features/settings/{filename}"
        if any(k in lower for k in ("header", "notification")):
            return f"frontend/src/shared/components/{filename}"
        if "/hooks/" in lower:
            return f"frontend/src/shared/hooks/{filename}"
        if "/pages/" in lower:
            return f"frontend/src/features/{_feature_from_filename(filename)}/{filename}"
        return f"frontend/src/shared/{filename}"
    if lower.startswith(f"{root_dir}/scripts/"):
        return rel_path
    if any(v in lower for v in ("/amos/", "amos/", "maestral/", "/google/", "/email/")):
        vendor = (
            "amos" if "amos" in lower
            else "maestral" if "maestral" in lower
            else "google" if "google" in lower
            else "email"
        )
        return f"backend/src/integrations/{vendor}/{filename}"
    if any(v in lower for v in ("detector", "notify", "events", "stopthreshold")):
        return f"backend/src/domain/alerts/{filename}"
    if any(v in lower for v in ("monitor", "watchlist")):
        return f"backend/src/domain/monitor/{filename}"
    if any(v in lower for v in ("eta", "match", "gps", "milestone", "companyyard")):
        return f"backend/src/domain/tracking/{filename}"
    if any(v in lower for v in ("geo", "time")):
        return f"backend/src/lib/{filename}"
    return f"backend/src/domain/{_feature_from_filename(filename)}/{filename}"


def _suggest_react(rel_path: str, root_dir: str) -> str:
    filename = os.path.basename(rel_path)
    if "/pages/" in rel_path:
        return rel_path
    if "/components/" in rel_path:
        return rel_path
    return f"{root_dir}/src/features/{_feature_from_filename(filename)}/{filename}"


def _suggest_package_src(rel_path: str, root_dir: str) -> str:
    filename = os.path.basename(rel_path)
    return f"{root_dir}/src/domain/{_feature_from_filename(filename)}/{filename}"


def _suggest_fastapi(rel_path: str, root_dir: str) -> str:
    filename = os.path.basename(rel_path)
    feature = _feature_from_filename(filename)
    return f"{root_dir}/app/modules/{feature}/{filename}"


def _suggest_services_modular(rel_path: str, root_dir: str) -> str:
    filename = os.path.basename(rel_path)
    name_no_ext = os.path.splitext(filename)[0].lower()
    clean_parts = [p for p in name_no_ext.replace("-", "_").split("_") if p]
    if len(clean_parts) >= 2:
        feature, action = clean_parts[0], clean_parts[1]
    elif len(clean_parts) == 1:
        feature, action = clean_parts[0], "service"
    else:
        feature, action = "common", "utils"
    return f"{root_dir}/src/app/services/{feature}/{action}/{filename}"


def infer_suggested_path(rel_path: str, root_dir: str, profile: str = "mixed") -> str:
    """Profile-aware target path for a misplaced file."""
    suggesters = {
        "express_vite_monorepo": _suggest_express_vite,
        "react_src": _suggest_react,
        "package_src": _suggest_package_src,
        "fastapi_app": _suggest_fastapi,
        "services_modular": _suggest_services_modular,
    }
    fn = suggesters.get(profile, _suggest_package_src)
    return fn(rel_path, root_dir)


def detect_layout_profile(project: ProjectContext) -> str:
    """
    Detect dominant layout style so rules stay layout-aware.
    Returns: express_vite_monorepo | services_modular | fastapi_app | react_src | package_src | mixed
    """
    paths = [f.path.replace("\\", "/").strip("/") for f in project.files]
    scores = {
        "express_vite_monorepo": 0,
        "services_modular": 0,
        "fastapi_app": 0,
        "react_src": 0,
        "package_src": 0,
    }

    flat_backend_ts = sum(
        1 for p in paths
        if p.startswith("backend/src/") and p.count("/") == 2 and p.endswith((".ts", ".tsx"))
    )
    has_server = any(p.endswith("backend/src/server.ts") for p in paths)
    has_vite = any(p.endswith("frontend/vite.config.ts") for p in paths)
    has_pages = any("/frontend/src/pages/" in p for p in paths)

    if flat_backend_ts >= 4:
        scores["express_vite_monorepo"] += 3
    if has_server:
        scores["express_vite_monorepo"] += 3
    if has_vite:
        scores["express_vite_monorepo"] += 2
    if has_pages:
        scores["express_vite_monorepo"] += 2
    if any(p.startswith("backend/scripts/") for p in paths):
        scores["express_vite_monorepo"] += 1

    for f in project.files:
        if f.path.replace("\\", "/") == "backend/package.json" and f.content:
            if "express" in f.content.lower():
                scores["express_vite_monorepo"] += 3

    for p in paths:
        lower = p.lower()
        if "/src/app/services/" in f"/{lower}":
            scores["services_modular"] += 3
        if lower.startswith("backend/app/") or "/app/modules/" in f"/{lower}" or "/app/api/" in f"/{lower}":
            scores["fastapi_app"] += 2
        if any(
            x in f"/{lower}"
            for x in ("/src/pages/", "/src/components/", "/src/features/")
        ):
            scores["react_src"] += 1
        if "/src/app/" in f"/{lower}" and "frontend/" in lower:
            scores["react_src"] += 1
        if lower.startswith("backend/src/") and "/src/app/" not in f"/{lower}":
            # Flat Express/Node src/*.ts — only counts as package_src without SPA signals
            if not (has_server or has_vite):
                scores["package_src"] += 2

    if has_server and has_vite:
        scores["express_vite_monorepo"] += 5
    if has_server and has_pages:
        scores["express_vite_monorepo"] += 3

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "mixed"
    ordered = sorted(scores.values(), reverse=True)
    if len(ordered) > 1 and ordered[0] > 0 and ordered[1] >= ordered[0] * 0.6:
        # Prefer express_vite when tied with package_src for monorepos
        if scores["express_vite_monorepo"] >= scores["package_src"] and scores["express_vite_monorepo"] > 0:
            if has_vite or has_server:
                return "express_vite_monorepo"
        return "mixed"
    return best


def _detect_layout_profile(project: ProjectContext) -> str:
    """Backward-compatible alias."""
    return detect_layout_profile(project)


def _is_allowed_under_src(sub_path: str) -> bool:
    if any(sub_path.startswith(prefix) for prefix in ALLOWED_SRC_PREFIXES):
        return True
    # Generic package under src/<name>/...
    parts = sub_path.split("/")
    if len(parts) >= 2 and parts[0] == "src" and parts[1] not in {"", "."}:
        # Allow src/<package>/... for library-style backends
        return True
    return False


def _is_allowed_backend_app_layout(sub_path: str) -> bool:
    return any(sub_path.startswith(prefix) for prefix in ALLOWED_BACKEND_NON_SRC_PREFIXES)


class StaticStructureAuditor:
    """performs deterministic, rule-based folder structure validation."""

    def audit(self, project: ProjectContext) -> list[FolderViolation]:
        violations: list[FolderViolation] = []
        profile = detect_layout_profile(project)

        # Aggregate buckets to avoid per-file flood
        outside_src: dict[str, list[str]] = defaultdict(list)  # root -> paths
        non_modular_app: dict[str, list[str]] = defaultdict(list)
        seen_root_dirs: set[str] = set()

        # 1. Top-Level Root Directory Audit
        for file_info in project.files:
            rel_path = file_info.path.replace("\\", "/").strip("/")
            parts = rel_path.split("/")

            if len(parts) > 1:
                root_part = parts[0]
                if not root_part.startswith(".") and root_part not in ALLOWED_ROOT_DIRS:
                    seen_root_dirs.add(root_part)

        for disallowed_dir in sorted(seen_root_dirs):
            lower = disallowed_dir.lower()
            if lower in ADVISORY_ROOT_DIRS:
                violations.append(
                    FolderViolation(
                        path=disallowed_dir,
                        violation_type="disallowed_root_directory",
                        severity="low",
                        description=(
                            f"Root folder '{disallowed_dir}' is outside the primary "
                            "'backend' / 'frontend' code roots. Common for docs/tooling."
                        ),
                        suggestion=(
                            f"Keep '{disallowed_dir}' if it is docs/tooling, or relocate "
                            "product code into 'backend' or 'frontend'."
                        ),
                    )
                )
            else:
                violations.append(
                    FolderViolation(
                        path=disallowed_dir,
                        violation_type="disallowed_root_directory",
                        severity="medium",
                        description=(
                            f"Root folder '{disallowed_dir}' is not a primary code root. "
                            "Preferred major roots are 'backend' and 'frontend'."
                        ),
                        suggestion=(
                            f"Relocate product code from '{disallowed_dir}' into 'backend' "
                            "or 'frontend' when it is application source (not docs/infra)."
                        ),
                    )
                )

        # 2. Path conventions inside backend/frontend (aggregated)
        for file_info in project.files:
            rel_path = file_info.path.replace("\\", "/").strip("/")
            parts = rel_path.split("/")

            if len(parts) <= 1 or parts[0].startswith("."):
                continue

            root_dir = parts[0]
            if root_dir not in ALLOWED_ROOT_DIRS:
                continue

            sub_path = "/".join(parts[1:])
            filename = parts[-1]

            if len(parts) == 2 and (filename in ALLOWED_ROOT_FILES or filename.startswith(".")):
                continue

            top_sub = parts[1] if len(parts) > 1 else ""
            if top_sub in ALLOWED_TOP_SUBDIRS:
                continue

            # backend/app/... FastAPI-style — allowed for fastapi_app / mixed profiles
            if root_dir == "backend" and _is_allowed_backend_app_layout(sub_path):
                if profile in {"fastapi_app", "mixed", "package_src"}:
                    continue
                non_modular_app[root_dir].append(rel_path)
                continue

            if not sub_path.startswith("src/"):
                outside_src[root_dir].append(rel_path)
                continue

            # Under src/: allow conventional prefixes / package layouts
            if _is_allowed_under_src(sub_path):
                # Soft nudge only if profile is services_modular and path is not services/
                if (
                    profile == "services_modular"
                    and sub_path.startswith("src/app/")
                    and not sub_path.startswith("src/app/services/")
                ):
                    non_modular_app[root_dir].append(rel_path)
                continue

            # src/app/... but unusual — soft aggregate
            if sub_path.startswith("src/app/"):
                non_modular_app[root_dir].append(rel_path)
            else:
                outside_src[root_dir].append(rel_path)

        # Emit aggregated outside-src findings (one per root, not per file)
        for root_dir, paths in sorted(outside_src.items()):
            sample = paths[:5]
            more = len(paths) - len(sample)
            sample_txt = ", ".join(f"`{p}`" for p in sample)
            if more > 0:
                sample_txt += f" (+{more} more)"
            example = infer_suggested_path(paths[0], root_dir, profile)
            violations.append(
                FolderViolation(
                    path=f"{root_dir}/ (outside src/)",
                    violation_type="invalid_path_depth",
                    severity="medium",
                    description=(
                        f"{len(paths)} file(s) under '{root_dir}/' sit outside the usual "
                        f"'src/' hierarchy. Examples: {sample_txt}."
                    ),
                    suggestion=(
                        f"Prefer placing application code under '{root_dir}/src/...'. "
                        f"Example target pattern: '{example}'."
                    ),
                )
            )

        # Emit aggregated modularity nudges
        for root_dir, paths in sorted(non_modular_app.items()):
            # Deduplicate paths that may have been appended in multiple branches
            uniq = sorted(set(paths))
            sample = uniq[:5]
            more = len(uniq) - len(sample)
            sample_txt = ", ".join(f"`{p}`" for p in sample)
            if more > 0:
                sample_txt += f" (+{more} more)"
            example = infer_suggested_path(uniq[0], root_dir, profile)
            severity = "low" if profile not in {"services_modular"} else "medium"
            # Skip modularity nudges for stacks with their own conventions
            if profile in {"express_vite_monorepo", "react_src", "package_src", "fastapi_app"}:
                continue
            target_pattern = {
                "services_modular": "src/app/services/<feature>/<action>/...",
            }.get(profile, "src/domain/ or src/integrations/ (backend), src/features/ (frontend)")
            violations.append(
                FolderViolation(
                    path=f"{root_dir}/src/app/ (non-services layout)",
                    violation_type="invalid_path_depth",
                    severity=severity,
                    description=(
                        f"{len(uniq)} file(s) under '{root_dir}' use an app layout that "
                        f"differs from the recommended '{target_pattern}' pattern. "
                        f"Detected profile: {profile}. Examples: {sample_txt}."
                    ),
                    suggestion=(
                        f"Optionally restructure feature modules toward '{example}'. "
                        "Existing conventional layouts (pages/components/modules) remain acceptable."
                    ),
                )
            )

        return violations
