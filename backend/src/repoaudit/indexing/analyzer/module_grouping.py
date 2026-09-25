"""Module grouping and deterministic inventory fallbacks for wiki generation."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from repoaudit.indexing.models import FileDoc, FileInfo, ModuleDoc

MAX_MODULE_FILES = 35
MAX_LLM_FILES = 24
MODULE_CACHE_VERSION = "v3"


def module_cache_key(name: str, content_hash: str) -> str:
    return f"module:{MODULE_CACHE_VERSION}:{name}:{content_hash}"


DOMAIN_FRONTEND = "Frontend & UI Presentation"
DOMAIN_API = "API & Controller Gateway"
DOMAIN_SERVICES = "Core Business & Services"
DOMAIN_DATA = "Data & Storage Layer"
DOMAIN_INFRA = "Infrastructure & Utilities"

DOMAIN_ORDER = [
    DOMAIN_FRONTEND,
    DOMAIN_API,
    DOMAIN_SERVICES,
    DOMAIN_DATA,
    DOMAIN_INFRA,
]


def infer_domain_slice(path: str) -> str:
    """
    Classify a file path into one of the 4-5 high-level architecture domain slices:
      - Frontend & UI Presentation (pages, components, views, UI stores, client assets)
      - API & Controller Gateway (routes, controllers, endpoints, routers, middlewares)
      - Core Business & Services (services, core business logic, domain engines, integrations)
      - Data & Storage Layer (models, schemas, entities, db migrations, cache adapters)
      - Infrastructure & Utilities (config, scripts, utils, helpers, build/deploy)
    """
    norm = path.replace("\\", "/").lower()
    parts = [p.lower() for p in Path(norm).parts]

    # Frontend matching
    if any(p in ("frontend", "client", "ui", "web", "views", "components", "pages") for p in parts):
        return DOMAIN_FRONTEND
    if any(norm.endswith(ext) for ext in (".tsx", ".jsx", ".vue", ".svelte", ".css", ".scss", ".html")):
        return DOMAIN_FRONTEND

    # API / Routing gateway matching
    if any(p in ("routes", "routers", "router", "controllers", "controller", "endpoints", "api", "v1", "v2") for p in parts):
        return DOMAIN_API
    if any(k in norm for k in ("/routes/", "/router.", "/routes.", "/endpoints/", "/api/")):
        return DOMAIN_API

    # Data & Storage matching
    if any(p in ("models", "schemas", "schema", "db", "database", "entities", "entity", "migrations", "repository", "repositories", "cache") for p in parts):
        return DOMAIN_DATA
    if any(k in norm for k in ("/models.", "/schemas.", "/schema.", "/models/", "/db/")):
        return DOMAIN_DATA

    # Infrastructure & Utilities matching
    if any(p in ("config", "scripts", "utils", "util", "helpers", "helper", "common", "infra", "deploy", "docker", "test", "tests") for p in parts):
        return DOMAIN_INFRA
    if any(norm.endswith(ext) for ext in (".yml", ".yaml", ".json", ".toml", ".ini", ".env", ".dockerfile", ".sh", ".ps1")):
        return DOMAIN_INFRA

    # Core Business / Services matching (services, core, modules, engine, audit, etc.)
    if any(p in ("services", "service", "core", "modules", "module", "engine", "domain", "logic", "workflows", "pipeline") for p in parts):
        return DOMAIN_SERVICES

    # Default based on root directory or fallback to services/infra
    if parts[0] == "backend":
        return DOMAIN_SERVICES
    if parts[0] == "frontend":
        return DOMAIN_FRONTEND

    return DOMAIN_SERVICES


def infer_module_key(path: str) -> str:
    """Classify path into high-level architecture domain slice."""
    return infer_domain_slice(path)


def group_files_into_modules(files: list[FileInfo]) -> dict[str, list[FileInfo]]:
    """Group repository files into consolidated architecture domain buckets."""
    buckets: dict[str, list[FileInfo]] = defaultdict(list)
    for f in files:
        domain = infer_domain_slice(f.path)
        buckets[domain].append(f)

    # Return domains that have files, sorted by canonical architecture order
    result: dict[str, list[FileInfo]] = {}
    for domain in DOMAIN_ORDER:
        if domain in buckets and buckets[domain]:
            result[domain] = buckets[domain]

    # Include any custom domain that might not be in standard order
    for domain, flist in buckets.items():
        if domain not in result and flist:
            result[domain] = flist

    return result


def select_files_for_llm(files: list[FileInfo], limit: int = MAX_LLM_FILES) -> list[FileInfo]:
    """Pick representative files for LLM context (entrypoints/configs first)."""

    def sort_key(f: FileInfo) -> tuple:
        priority = 2
        if f.is_entrypoint:
            priority = 0
        elif f.is_config:
            priority = 1
        return (priority, -f.lines, f.path)

    return sorted(files, key=sort_key)[:limit]


def _infer_file_role(f: FileInfo) -> str:
    """Derive a short role sentence for a file based on its properties."""
    parts: list[str] = []
    if f.is_entrypoint:
        parts.append("Application entry point")
    elif f.is_config:
        parts.append("Configuration file")
    else:
        ext = Path(f.path).suffix.lower()
        ext_roles = {
            ".tsx": "React component", ".jsx": "React component",
            ".vue": "Vue component", ".svelte": "Svelte component",
            ".css": "Stylesheet", ".scss": "Stylesheet",
            ".html": "HTML template",
            ".py": "Python module", ".rs": "Rust module",
            ".go": "Go module", ".java": "Java class",
            ".ts": "TypeScript module", ".js": "JavaScript module",
            ".sql": "SQL schema or query",
            ".json": "JSON data / config", ".yaml": "YAML config",
            ".yml": "YAML config", ".toml": "TOML config",
            ".sh": "Shell script", ".ps1": "PowerShell script",
            ".md": "Documentation",
        }
        parts.append(ext_roles.get(ext, f"{f.language or 'source'} file".capitalize()))

    stem = Path(f.path).stem.lower()
    if "test" in stem or "spec" in stem:
        parts.append("(test)")
    elif "util" in stem or "helper" in stem:
        parts.append("(utility)")
    elif "model" in stem or "schema" in stem:
        parts.append("(data model)")
    elif "route" in stem or "router" in stem:
        parts.append("(routing)")
    elif "service" in stem:
        parts.append("(service logic)")

    return " ".join(parts)


def build_inventory_module_doc(name: str, files: list[FileInfo]) -> ModuleDoc:
    """Deterministic domain documentation from scan inventory (structured & human-readable)."""
    file_docs: list[FileDoc] = []
    for f in sorted(files, key=lambda x: x.path):
        file_docs.append(
            FileDoc(
                path=f.path,
                purpose=_infer_file_role(f),
            )
        )

    langs: dict[str, int] = defaultdict(int)
    for f in files:
        langs[f.language or "unknown"] += 1
    lang_summary = ", ".join(
        f"{lang} ({count})" for lang, count in sorted(langs.items(), key=lambda x: -x[1])[:5]
    )

    entrypoints = [f.path for f in files if f.is_entrypoint][:6]
    entrypoint_note = ""
    if entrypoints:
        entrypoint_note = (
            " **Primary entry points & anchors:** "
            + ", ".join(f"`{p}`" for p in entrypoints)
            + ".\n\n"
        )

    domain_descriptions = {
        DOMAIN_FRONTEND: (
            "Encapsulates user interface views, layout components, interactive pages, "
            "and client-side state management that deliver the product experience to users."
        ),
        DOMAIN_API: (
            "Provides HTTP endpoints, request routing, validation layers, authentication guards, "
            "and API gateways through which external clients and frontend components interact."
        ),
        DOMAIN_SERVICES: (
            "Houses core domain workflows, business rules, third-party service integrations, "
            "and processing pipelines that execute the central application capabilities."
        ),
        DOMAIN_DATA: (
            "Defines database models, serialization schemas, query abstractions, database entities, "
            "and caching mechanisms responsible for persistent data storage and retrieval."
        ),
        DOMAIN_INFRA: (
            "Contains operational configuration, automation scripts, deployment declarations, "
            "shared utility helpers, and foundational tooling supporting the system."
        ),
    }

    desc = domain_descriptions.get(
        name,
        f"This domain encapsulates key components and workflows belonging to {name}."
    )

    return ModuleDoc(
        name=name,
        purpose=desc,
        description=(
            f"### Domain Overview\n{desc}\n\n"
            f"{entrypoint_note}"
            f"**Composition:** Contains **{len(files)}** files spanning {lang_summary}."
        ),
        files=file_docs,
    )


def is_rich_module_doc(doc: ModuleDoc) -> bool:
    """True when module doc has enough substance to cache safely."""
    if doc.description and len(doc.description.strip()) > 60:
        return True
    if len(doc.files) >= 3:
        return True
    if doc.files and any((f.purpose or "").strip() for f in doc.files):
        return True
    return False


def merge_module_doc(llm_doc: ModuleDoc | None, inventory: ModuleDoc) -> ModuleDoc:
    """Prefer LLM narrative but always retain file inventory coverage."""
    if llm_doc is None:
        return inventory
    if not is_rich_module_doc(llm_doc):
        return inventory

    merged_files = list(llm_doc.files)
    known_paths = {f.path for f in merged_files}
    for f in inventory.files:
        if f.path not in known_paths:
            merged_files.append(f)

    return ModuleDoc(
        name=inventory.name,
        purpose=llm_doc.purpose or inventory.purpose,
        description=llm_doc.description or inventory.description,
        files=merged_files,
        relationships=llm_doc.relationships,
        key_concepts=llm_doc.key_concepts,
    )
