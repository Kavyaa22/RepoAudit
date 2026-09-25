"""assemble wiki pages from analysis results."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from repoaudit.audit.plain_language import (
    attr,
    confidence_label,
    dead_code_category_label,
    security_category_label,
    severity_label,
)
from repoaudit.indexing.graph.graph import DependencyGraph
from repoaudit.indexing.models import ProjectContext, WikiData


def normalize_mermaid(text: str | None) -> str:
    """Turn LLM/graph mermaid into a fence-ready diagram body."""
    if not text:
        return ""
    cleaned = text.strip()
    cleaned = cleaned.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\r", "")
    cleaned = re.sub(r"^```(?:mermaid)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    # Strip dark theme / style directives that cause unreadable text
    cleaned = re.sub(r"%%\{.*?\}%%", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"^\s*classDef\b.*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s*style\b.*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'(\b[A-Za-z0-9_]+)\[([^"\]\n\r]*[():/&,\\-][^"\]\n\r]*)\]', r'\1["\2"]', cleaned)
    # Collapse blank lines left by stripped directives
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def extract_fenced_tree_body(text: str | None) -> str:
    """Pull the first ``` / ```text tree body, or return cleaned plain text."""
    if not text:
        return ""
    raw = text.strip()
    # Prefer an explicit Proposed Structure section when the LLM report is composed.
    lower = raw.lower()
    for marker in (
        "### 3. proposed structure",
        "### proposed structure",
        "## recommended layout",
        "### recommended target structure",
    ):
        idx = lower.find(marker)
        if idx >= 0:
            raw = raw[idx:]
            break
    match = re.search(r"```(?:text|plaintext)?\s*\n([\s\S]*?)```", raw)
    if match:
        return match.group(1).strip()
    # Strip markdown headings / prose lines; keep path-like and tree lines.
    lines: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") or stripped.startswith(">"):
            continue
        if stripped.startswith("**") and stripped.endswith("**"):
            continue
        if stripped.lower().startswith(("hierarchy:", "built with", "confirmation", "features identified")):
            continue
        if stripped.startswith(("1.", "2.", "3.", "- ")):
            continue
        lines.append(line.rstrip())
    return "\n".join(lines).strip()


_KNOWN_FILE_NAMES = {
    "dockerfile",
    "dockerfile.api",
    "dockerfile.web",
    "makefile",
    "gemfile",
    "rakefile",
    "procfile",
    "license",
    "licence",
    "readme",
    "changelog",
    "authors",
    "contributors",
    "copying",
    "nginx",
    "vagrantfile",
}


def _looks_like_file(name: str) -> bool:
    base = name.rstrip("/")
    lower = base.lower()
    if lower in _KNOWN_FILE_NAMES:
        return True
    if lower.startswith(".") and "." in lower[1:]:
        return True
    if lower.startswith(".") and "/" not in lower[1:]:
        return True
    return bool(re.search(r"\.[a-z0-9]+$", base, re.IGNORECASE))


def collect_dir_paths_from_tree(body: str) -> set[str]:
    """Collect directory paths from an ASCII tree or flat path list."""
    dirs: set[str] = set()
    if not body or not body.strip():
        return dirs

    stack: list[str] = []
    for line in body.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith(("```", "#")):
            continue
        if stripped.startswith(("Built with", "**Migration", "Hierarchy:", "### ")):
            continue

        match = re.match(r"^(.*?)([├└]──\s+|──\s+)(.+)$", line)
        if match:
            prefix = match.group(1) or ""
            name = match.group(3).strip()
            depth = len(prefix.replace("\t", "    ")) // 4
            while len(stack) > depth:
                stack.pop()
            dir_hint = name.endswith("/")
            name = name.rstrip("/")
            if name.startswith(("…", "...")):
                continue
            if len(stack) <= depth:
                stack.extend([""] * (depth + 1 - len(stack)))
            stack[depth] = name
            full = "/".join(stack[: depth + 1])
            treat_as_dir = False if _looks_like_file(name) else (dir_hint or not _looks_like_file(name))
            if treat_as_dir:
                dirs.add(full)
            continue

        if "/" in stripped and "──" not in stripped and not stripped.startswith("│"):
            clean = re.sub(r"^[*-]\s*", "", stripped).replace("`", "").split(" — ")[0].split(" - ")[0].strip()
            body_path = clean.rstrip("/")
            parts = [p for p in body_path.split("/") if p]
            if not parts:
                continue
            last = parts[-1]
            end = len(parts) if (clean.endswith("/") or not _looks_like_file(last)) else len(parts) - 1
            for i in range(1, end + 1):
                dirs.add("/".join(parts[:i]))
            continue

        if re.match(r"^[A-Za-z0-9_.@-]+/?$", stripped):
            name = stripped.rstrip("/")
            stack = [name]
            if not _looks_like_file(name):
                dirs.add(name)

    return dirs


def compact_folder_roots(paths: set[str]) -> list[str]:
    """Keep only highest-level folders (drop children when parent is present)."""
    ordered = sorted(paths, key=lambda p: (p.count("/"), len(p), p))
    roots: list[str] = []
    for path in ordered:
        if any(path == root or path.startswith(root + "/") for root in roots):
            continue
        roots.append(path)
    return sorted(roots)


def folder_delta_from_trees(current_body: str, suggested_body: str) -> tuple[list[str], list[str]]:
    """Return (added_folders, removed_folders) comparing two tree texts."""
    current = collect_dir_paths_from_tree(current_body)
    suggested = collect_dir_paths_from_tree(suggested_body)
    added = compact_folder_roots(suggested - current)
    removed = compact_folder_roots(current - suggested)
    return added, removed


def slugify_domain(name: str) -> str:
    """Convert a domain name like 'Frontend & UI Presentation' to a URL-safe slug."""
    slug = name.lower()
    slug = re.sub(r"[&]+", "", slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "domain"



@dataclass
class WikiPage:
    id: str
    title: str
    content: str
    parent_id: str = ""
    order: int = 0


@dataclass
class SidebarItem:
    title: str
    page_id: str
    children: list[SidebarItem] = field(default_factory=list)


@dataclass
class Wiki:
    pages: list[WikiPage] = field(default_factory=list)
    sidebar: list[SidebarItem] = field(default_factory=list)
    project_name: str = ""

    def get_page(self, page_id: str) -> WikiPage | None:
        for p in self.pages:
            if p.id == page_id:
                return p
        return None


class WikiBuilder:
    """constructs a Wiki from analysis results."""

    def build(
        self,
        project: ProjectContext,
        wiki_data: WikiData,
        graph: DependencyGraph,
    ) -> Wiki:
        pages: list[WikiPage] = []
        sidebar: list[SidebarItem] = []

        # 1. Overview
        overview_md = self._build_overview_page(wiki_data.overview, project)
        pages.append(WikiPage(id="index", title="Overview", content=overview_md, order=0))
        sidebar.append(SidebarItem(title="Overview", page_id="index"))

        # 2. Phase 1: Folder Structure Audit
        if wiki_data.structure_audit:
            struct_md = self._build_structure_audit_page(wiki_data.structure_audit)
        else:
            struct_md = "# How the project is organized\n\n> This review is still running."
        pages.append(WikiPage(id="structure-audit", title="How it's organized", content=struct_md, order=1))
        sidebar.append(SidebarItem(title="How it's organized", page_id="structure-audit"))

        # 3. Architecture diagrams (dedicated page so Mermaid is not buried in Phase 1)
        arch_md = self._build_architecture_page(wiki_data.architecture, project, graph)
        pages.append(WikiPage(id="architecture", title="How the system fits together", content=arch_md, order=2))
        sidebar.append(SidebarItem(title="How the system fits together", page_id="architecture"))

        # 4. Phase 2: Dead Code & Unused Dependency Audit
        dead_md = self._build_dead_code_audit_page(wiki_data.dead_code_audit)
        pages.append(WikiPage(id="dead-code-audit", title="Unused code", content=dead_md, order=3))
        sidebar.append(SidebarItem(title="Unused code", page_id="dead-code-audit"))

        security_md = self._build_security_audit_page(wiki_data.security_audit)
        pages.append(WikiPage(id="security-audit", title="Security health", content=security_md, order=4))
        sidebar.append(SidebarItem(title="Security health", page_id="security-audit"))

        # 6. Codebase Reading Guide
        guide_md = self._build_reading_guide_page(wiki_data.reading_guide, project)
        pages.append(WikiPage(id="reading-guide", title="Codebase Reading Guide", content=guide_md, order=5))
        sidebar.append(SidebarItem(title="Codebase Reading Guide", page_id="reading-guide"))

        # 7. Module Dependency Graph (always includes a Mermaid block when edges exist)
        mermaid = graph.to_mermaid()
        dep_md = self._build_dependency_page(graph, mermaid)
        pages.append(WikiPage(id="dependencies", title="How files connect", content=dep_md, order=6))
        sidebar.append(SidebarItem(title="How files connect", page_id="dependencies"))

        # 7. Architecture Domain Pages
        module_sidebar = SidebarItem(title="Architecture Domains", page_id="", children=[])
        for i, mod in enumerate(wiki_data.modules):
            mod_id = f"modules/{slugify_domain(mod.name)}"
            mod_md = self._build_module_page(mod)
            pages.append(WikiPage(
                id=mod_id, title=mod.name, content=mod_md,
                parent_id="modules", order=i,
            ))
            module_sidebar.children.append(SidebarItem(title=mod.name, page_id=mod_id))
        if module_sidebar.children:
            sidebar.append(module_sidebar)

        return Wiki(pages=pages, sidebar=sidebar, project_name=project.name)

    def _build_overview_page(self, overview, project) -> str:
        lines = [f"# {overview.name or project.name}\n"]
        if overview.one_liner:
            lines.append(f"> {overview.one_liner}\n")
        else:
            lines.append(f"> Codebase analysis & auditing report for **{project.name}**.\n")

        if overview.description:
            lines.append(f"{overview.description}\n")
        else:
            lines.append(
                f"This project contains {len(project.files)} files and approximately "
                f"{project.total_lines} lines of code. Explore the folder structure audit "
                f"and module pages for deeper subsystem detail.\n"
            )

        lines.append("## Repository Snapshot\n")
        lines.append(f"- **Files analyzed:** {len(project.files)}")
        lines.append(f"- **Approx. lines of code:** {project.total_lines}")
        if project.file_tree:
            preview = "\n".join(project.file_tree.splitlines()[:40])
            lines.append("\n### File tree (excerpt)\n")
            lines.append(f"```\n{preview}\n```\n")
        else:
            lines.append("")

        if overview.tech_stack:
            lines.append("## Tech Stack\n")
            for t in overview.tech_stack:
                ver = f" {t.version}" if t.version else ""
                cat = f" ({t.category})" if t.category else ""
                lines.append(f"- **{t.name}**{ver}{cat}")
            lines.append("")

        if overview.key_features:
            lines.append("## Key Features\n")
            for feat in overview.key_features:
                lines.append(f"- {feat}")
            lines.append("")

        if overview.setup_instructions:
            lines.append("## Getting Started\n")
            for i, step in enumerate(overview.setup_instructions, 1):
                lines.append(f"{i}. {step}")
            lines.append("")

        return "\n".join(lines)

    def _build_architecture_page(self, arch, project, graph: DependencyGraph | None = None) -> str:
        """Dedicated architecture page with Mermaid (LLM first, import-graph fallback)."""
        lines = ["# How the system fits together\n"]

        arch_type = (arch.architecture_type if arch else "") or "A typical product with a few main parts"
        lines.append(f"**Style of this project:** {arch_type}\n")

        if arch and arch.description:
            lines.append(f"> {arch.description}\n")
        else:
            lines.append(
                f"> A simple picture of how `{project.name}` is put together, "
                "so you can see the main parts without reading the code.\n"
            )

        llm_mermaid = normalize_mermaid(arch.mermaid_component if arch else "")
        fallback = graph.to_mermaid() if graph is not None else ""
        component_mermaid = llm_mermaid or fallback
        lines.append("## Picture of the main parts\n")
        lines.append(
            "Click the diagram to open a larger view. You can zoom and drag, like a map.\n"
        )
        if component_mermaid:
            if not llm_mermaid and fallback:
                lines.append(
                    "> Showing how files talk to each other, because a simpler sketch was not available.\n"
                )
            lines.append(f"```mermaid\n{component_mermaid}\n```\n")
        else:
            lines.append(
                "> No picture could be drawn for this scan.\n"
            )

        if arch and arch.components:
            lines.append("## Main parts of the product\n")
            for c in arch.components:
                lines.append(f"### {c.name}\n")
                if c.purpose:
                    lines.append(f"{c.purpose}\n")
                if c.files:
                    lines.append("**Key files:** " + ", ".join(f"`{f}`" for f in c.files) + "\n")

        seq = normalize_mermaid(arch.mermaid_sequence if arch else "")
        if seq:
            lines.append("## How a typical request flows\n")
            lines.append("Click to expand, then zoom and drag.\n")
            lines.append(f"```mermaid\n{seq}\n```\n")

        if arch and arch.data_flow:
            lines.append("## How information moves\n")
            lines.append(f"{arch.data_flow}\n")

        return "\n".join(lines)

    def _build_dead_code_audit_page(self, audit) -> str:
        lines = ["# Unused code and leftover packages\n"]
        lines.append(
            "This is a cleanup review: things the team is still carrying that do not appear to be used. "
            "Removing them usually means less cost, less confusion, and a smaller risk surface.\n"
        )

        if not audit:
            lines.append("No unused code was flagged in this review.\n")
            return "\n".join(lines)

        lines.append(f"> {audit.summary_verdict}\n")

        lines.append("## What looks unused\n")
        if audit.findings:
            lines.append("| What it is | File | How sure we are | Why it matters |")
            lines.append("|---|---|---|---|")
            for f in audit.findings:
                cat_label = dead_code_category_label(f.category)
                conf = confidence_label(f.confidence_level)
                lines.append(
                    f"| {cat_label}: `{f.symbol_name}` | `{f.path}` | {conf} | {f.description} |"
                )
            lines.append("")
        else:
            lines.append("Nothing unused stood out in this review.\n")

        lines.append("## Suggested next steps\n")
        lines.append("1. **Confirm with the team** that flagged items are not used in a hidden way (plugins, late-bound calls, or scripts).\n")
        lines.append("2. **Remove leftover packages** so the project is smaller and cheaper to keep up to date.\n")
        lines.append("3. **Delete unused files and functions** once confirmed, so new people can find the real code faster.\n")

        return "\n".join(lines)

    def _build_security_audit_page(self, audit) -> str:
        lines = ["# Security health check\n"]
        lines.append(
            "This health check looks for common safety risks: "
            "passwords or secrets accidentally left in the code, outdated packages with known security issues, "
            "and unsafe coding shortcuts. Everything is written to be easily actionable with your AI coding tools.\n"
        )

        if not audit:
            lines.append("A security review has not been stored for this audit yet.\n")
            return "\n".join(lines)

        findings = getattr(audit, "findings", None) or []
        verdict = getattr(audit, "summary_verdict", "")
        if verdict:
            lines.append(f"> {verdict}\n")

        if findings:
            lines.append("## What needs your attention\n")
            lines.append(
                "Review the items below. You can copy the suggested prompt straight into your AI coding assistant (e.g., Cursor, Claude, or ChatGPT) to resolve them.\n"
            )

            for i, item in enumerate(findings, 1):
                severity_raw = str(attr(item, "severity", "medium")).lower()
                category = str(attr(item, "category", ""))
                title = str(attr(item, "title", "") or security_category_label(category))
                path = str(attr(item, "path", ""))
                line = attr(item, "line", 0) or 0
                description = str(attr(item, "description", "") or attr(item, "evidence", ""))
                suggestion = str(attr(item, "suggestion", "") or "Ask your AI assistant to review and replace this with a safer pattern.")
                location = f"{path} (line {line})" if line else path
                meaning = security_category_label(category)
                headline = title if title.lower() not in meaning.lower() else meaning
                sev_text = severity_label(severity_raw)

                if severity_raw == "critical":
                    sev_icon = "🔴"
                    sev_tag = "Urgent — Fix Now"
                elif severity_raw == "high":
                    sev_icon = "🟠"
                    sev_tag = "High Priority"
                elif severity_raw == "low":
                    sev_icon = "🔵"
                    sev_tag = "Minor / Good Practice"
                else:
                    sev_icon = "🟡"
                    sev_tag = "Should Review"

                lines.append(f"### {sev_icon} {i}. {meaning}: {headline}\n")
                lines.append(f"- **Priority:** {sev_icon} **{sev_text}** ({sev_tag})")
                lines.append(f"- **Where:** `{location}`")
                lines.append(f"- **Why it matters:** {description}")
                lines.append(f"- **How to fix:** {suggestion}")
                lines.append(f"> 🤖 **AI Prompt to fix this:** `Please fix the security issue in {location}: {suggestion}`\n")

            lines.append("")
        else:
            lines.append("## Status: Clean & Safe 🎉\n")
            lines.append(
                "> **No security issues found!** We checked for exposed passwords, outdated risky libraries, "
                "and unsafe code shortcuts, and everything looks clean.\n"
            )

        lines.append("## How to handle these with AI\n")
        lines.append("1. **If a secret or API key was found:** treat it as leaked — rotate it in your provider dashboard immediately and store it inside an environment file (`.env`).\n")
        lines.append("2. **If a package is outdated:** ask your AI assistant to update it to the latest secure version in your project dependencies.\n")
        lines.append("3. **If a risky shortcut was found:** copy the prompt above into your AI tool to refactor the code safely.\n")

        return "\n".join(lines)

    def _build_module_page(self, mod) -> str:
        lines = [f"# {mod.name}\n"]
        if mod.purpose:
            lines.append(f"> {mod.purpose}\n")
        if mod.description:
            lines.append(f"{mod.description}\n")

        if mod.key_concepts:
            lines.append("## Key Capabilities & Core Concepts\n")
            for c in mod.key_concepts:
                lines.append(f"- **{c.name}**: {c.explanation}")
            lines.append("")

        if mod.relationships:
            lines.append("## Cross-Domain & Inter-File Connections\n")
            for r in mod.relationships:
                lines.append(f"- `{r.source}` → `{r.target}`: {r.description}")
            lines.append("")

        if mod.files:
            lines.append("## Primary Files & Responsibilities\n")
            for f in mod.files[:25]:
                lines.append(f"### `{f.path}`\n")
                if f.purpose:
                    lines.append(f"{f.purpose}\n")
                if f.key_symbols:
                    for s in f.key_symbols[:6]:
                        desc = f" — {s.description}" if s.description else ""
                        lines.append(f"- `{s.name}` ({s.kind}){desc}")
                    lines.append("")
            if len(mod.files) > 25:
                lines.append(f"\n_... and {len(mod.files) - 25} additional supporting files in this domain._\n")
        else:
            lines.append("## Primary Files\n")
            lines.append("_No files were indexed for this domain._\n")

        return "\n".join(lines)

    def _build_reading_guide_page(self, guide, project) -> str:
        lines = ["# Codebase Reading Guide\n"]
        if guide.introduction:
            lines.append(f"{guide.introduction}\n")
        else:
            lines.append(f"Recommended step-by-step reading roadmap to efficiently understand `{project.name}`.\n")

        if guide.steps:
            for step in guide.steps:
                time_est = f" (~{step.time_estimate})" if step.time_estimate else ""
                lines.append(f"## Step {step.order}: {step.title}{time_est}\n")
                if step.files:
                    lines.append("**Files:** " + ", ".join(f"`{f}`" for f in step.files) + "\n")
                if step.explanation:
                    lines.append(f"{step.explanation}\n")
        else:
            lines.append("## Recommended Inspection Order\n")
            lines.append("1. **Configuration & Entry Points**: Read main application entry points and environment settings.\n")
            lines.append("2. **Core Modules**: Explore high-volume service logic and primary API routes.\n")
            lines.append("3. **Utilities & Shared Helpers**: Review common utility scripts and database client instantiations.\n")

        if guide.tips:
            lines.append("## Developer Tips\n")
            for tip in guide.tips:
                lines.append(f"- {tip}")
            lines.append("")

        return "\n".join(lines)

    def _build_dependency_page(self, graph: DependencyGraph, mermaid: str) -> str:
        lines = ["# How files connect\n"]
        lines.append(
            "This map shows which parts of the project depend on which others. "
            "Click the picture to open a larger view, then zoom and drag to read the clustered areas.\n"
        )
        mermaid = normalize_mermaid(mermaid) or (graph.to_mermaid() if graph else "")
        if mermaid:
            lines.append("```mermaid\n" + mermaid + "\n```\n")
        else:
            lines.append(
                "> We could not draw a connection map for this scan. "
                "The lists below still highlight important and leftover files when they exist.\n"
            )

        core = graph.get_core_files(10)
        if core:
            lines.append("## Files that everything else leans on\n")
            for i, path in enumerate(core, 1):
                lines.append(f"{i}. `{path}`")
            lines.append("")

        entries = graph.get_entry_points()
        if entries:
            lines.append("## Likely starting points\n")
            for e in entries[:10]:
                lines.append(f"- `{e}`")
            lines.append("")

        cycles = graph.find_circular_dependencies()
        if cycles:
            lines.append("## Loops that make change harder\n")
            lines.append("These files depend on each other in a circle. That usually means a small change can have surprising side effects:\n")
            for cycle in cycles:
                files = ", ".join(f"`{p}`" for p in cycle)
                lines.append(f"- {files}")
            lines.append("")

        isolated = graph.find_isolated_files()
        if isolated:
            lines.append("## Files that sit on their own\n")
            lines.append("These files do not appear to connect to the rest of the project:\n")
            for f in isolated[:15]:
                lines.append(f"- `{f}`")
            lines.append("")

        return "\n".join(lines)

    def _build_structure_audit_page(self, audit) -> str:
        lines = ["# How the project is organized\n"]

        lines.append(f"> {audit.summary_reason}\n")
        lines.append(
            "Pictures of how the system fits together are on "
            "[How the system fits together](architecture) and [How files connect](dependencies).\n"
        )

        lines.append("## Folder issues\n")
        if audit.static_violations:
            lines.append("| Where | Priority | What's going on | Suggested fix |")
            lines.append("|---|---|---|---|")
            for v in audit.static_violations:
                lines.append(
                    f"| `{v.path}` | {severity_label(v.severity)} | {v.description} | {v.suggestion} |"
                )
            lines.append("")
        else:
            lines.append("The top-level folders look like a normal, well-kept project.\n")

        lines.append("## Files or folders in unexpected places\n")
        if audit.unstructured_areas:
            lines.append("| Where | Priority | What's going on | Better home |")
            lines.append("|---|---|---|---|")
            for u in audit.unstructured_areas:
                lines.append(
                    f"| `{u.path}` | {severity_label(u.severity)} | {u.description} | `{u.suggestion}` |"
                )
            lines.append("")
        else:
            lines.append("Nothing looked dumped in the wrong place.\n")

        style = getattr(audit, "structure_style", "") or "action_api"
        style_score = getattr(audit, "style_score", None)
        lines.append(f"## Structure style\n\nUsing **{style}** (Main Folder → Feature → Action → Files).\n")
        if style_score is not None:
            lines.append(f"Style match score: **{style_score}/100**.\n")
            gaps = getattr(audit, "style_gaps", None) or []
            if gaps:
                lines.append("Style gaps:\n")
                for gap in gaps[:8]:
                    lines.append(f"- {gap}")
                lines.append("")

        current_body = extract_fenced_tree_body(getattr(audit, "current_structure", None) or "")
        suggested_body = extract_fenced_tree_body(getattr(audit, "recommended_structure", None) or "")
        # If recommended is a full report without a clean tree, keep whatever we extracted.
        if not suggested_body and getattr(audit, "recommended_structure", None):
            suggested_body = str(audit.recommended_structure)

        lines.append("## Architecture\n")
        lines.append(
            "Current architecture first, then the suggested Feature → Action layout. "
            "Folders are collapsible — dig into deeper levels as needed.\n"
        )
        lines.append("```structure-current")
        lines.append(current_body or "repository/")
        lines.append("```")
        lines.append("")
        lines.append("```structure-suggested")
        lines.append(suggested_body or "repository/")
        lines.append("```")
        lines.append("")

        lines.append("## Folder changes at a glance\n")
        added_folders, removed_folders = folder_delta_from_trees(current_body, suggested_body)
        if added_folders or removed_folders:
            lines.append(
                "A simple look at what the suggested layout introduces or stops using "
                "(nested folders under these are included).\n"
            )
            if added_folders:
                lines.append("### New folders we'd create\n")
                for path in added_folders[:60]:
                    lines.append(f"- `{path}/`")
                if len(added_folders) > 60:
                    lines.append(f"- …and {len(added_folders) - 60} more")
                lines.append("")
            else:
                lines.append("### New folders we'd create\n\nNone — the suggestion reuses today's folder names.\n")
            if removed_folders:
                lines.append("### Folders we can leave behind\n")
                for path in removed_folders[:60]:
                    lines.append(f"- `{path}/`")
                if len(removed_folders) > 60:
                    lines.append(f"- …and {len(removed_folders) - 60} more")
                lines.append("")
            else:
                lines.append(
                    "### Folders we can leave behind\n\n"
                    "None — today's folders still appear in the suggestion "
                    "(files may still move between them).\n"
                )
        else:
            lines.append(
                "The suggested layout keeps the same folders — nothing major to add or remove at a glance.\n"
            )

        lines.append("## Why this suggestion\n")
        lines.append(
            "File contents are never modified — only folder placement is suggested.\n"
        )
        if getattr(audit, "features_identified", None):
            lines.append(
                "**Features identified:** "
                + ", ".join(audit.features_identified)
                + "\n"
            )
        if getattr(audit, "problems_found", None):
            lines.append("### Problems found\n")
            lines.append(audit.problems_found)
            lines.append("")
        if getattr(audit, "explanation", None):
            lines.append("### Reasoning\n")
            lines.append(audit.explanation)
            lines.append("")
        if getattr(audit, "no_file_content_modified", True):
            lines.append(
                "_Confirmation: no file contents were modified by this recommendation._\n"
            )

        return "\n".join(lines)
