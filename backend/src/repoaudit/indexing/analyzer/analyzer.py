"""orchestrates the multi-step LLM analysis pipeline."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from repoaudit.indexing.cache.cache import Cache, content_hash
from repoaudit.indexing.graph.graph import DependencyGraph
from repoaudit.indexing.llm.client import LLMClient
from repoaudit.indexing.llm.prompts import (
    build_architecture_prompt,
    build_module_prompt,
    build_overview_prompt,
    build_reading_guide_prompt,
    extract_json,
    salvage_architecture_partial,
)
from repoaudit.indexing.analyzer.module_grouping import (
    build_inventory_module_doc,
    group_files_into_modules,
    is_rich_module_doc,
    merge_module_doc,
    module_cache_key,
    select_files_for_llm,
)
from repoaudit.indexing.models import (
    ArchitectureDiagram,
    FileInfo,
    ModuleDoc,
    ProjectContext,
    ProjectOverview,
    ReadingGuide,
    WikiData,
)

logger = logging.getLogger(__name__)


class Analyzer:
    """runs the full wiki generation pipeline."""

    def __init__(
        self,
        llm: LLMClient,
        cache: Cache,
        language: str = "en",
        concurrency: int = 5,
    ):
        self.llm = llm
        self.cache = cache
        self.language = language
        self._sem = asyncio.Semaphore(concurrency)

    async def analyze(
        self,
        project: ProjectContext,
        on_progress: Callable[[str], None] | None = None,
    ) -> WikiData:
        """run the full analysis pipeline and return WikiData."""

        def progress(msg: str):
            if on_progress:
                on_progress(msg)

        # 1. prepare context
        progress("Preparing file context...")
        key_files_text = self._build_key_files_context(project)
        tree_hash = content_hash(project.file_tree + key_files_text)

        # 2. generate overview
        progress("Generating project overview...")
        overview = await self._generate_overview(project, key_files_text, tree_hash)

        # 3. group files into modules and analyze each
        modules_map = group_files_into_modules(project.files)
        progress(f"Analyzing {len(modules_map)} modules...")
        module_docs = await self._analyze_modules(
            modules_map, overview.one_liner, project, progress
        )

        # 4. generate architecture diagram
        progress("Detecting architecture...")
        architecture = await self._generate_architecture(project, key_files_text, tree_hash)

        # 5. generate reading guide (needs module summaries + rankings placeholder)
        progress("Creating reading guide...")
        reading_guide = await self._generate_reading_guide(
            project, module_docs, tree_hash
        )

        progress("Done!")
        return WikiData(
            overview=overview,
            modules=module_docs,
            architecture=architecture,
            reading_guide=reading_guide,
        )

    def _build_key_files_context(self, project: ProjectContext) -> str:
        """collect config files and entrypoints for the overview prompt."""
        parts = []
        for f in project.files:
            if f.is_config or f.is_entrypoint:
                content = f.content if f.content else f.preview
                # truncate large files
                if len(content) > 4096:
                    content = content[:4096] + "\n... (truncated)"
                parts.append(f"### {f.path}\n```{f.language}\n{content}\n```")
        return "\n\n".join(parts)

    async def _generate_overview(
        self, project: ProjectContext, key_files: str, tree_hash: str
    ) -> ProjectOverview:
        cache_key = f"overview:{tree_hash}"
        cached = await self.cache.get(cache_key)
        if cached:
            try:
                return ProjectOverview(**cached)
            except Exception:
                pass

        messages = build_overview_prompt(project.file_tree, key_files, self.language)
        raw = await self.llm.complete(messages, max_tokens=4096, operation="wiki")
        data = extract_json(raw)
        if not data or not isinstance(data, dict):
            logger.warning("Failed to parse overview JSON, using defaults")
            return ProjectOverview(name=project.name)

        filtered = {k: v for k, v in data.items() if k in ProjectOverview.model_fields}
        try:
            overview = ProjectOverview(**filtered)
        except Exception:
            overview = ProjectOverview(name=project.name)
        await self.cache.put(cache_key, overview.model_dump())
        return overview

    def _group_into_modules(self, files: list[FileInfo]) -> dict[str, list[FileInfo]]:
        """Deprecated: use group_files_into_modules(). Kept for tests."""
        return group_files_into_modules(files)

    async def _analyze_one_module(
        self,
        name: str,
        files: list[FileInfo],
        project_summary: str,
        project: ProjectContext,
    ) -> tuple[ModuleDoc | None, bool]:
        async with self._sem:
            inventory_doc = build_inventory_module_doc(name, files)
            llm_files = select_files_for_llm(files)
            files_text_parts = []
            content_parts = []
            for f in llm_files:
                content = f.content if f.content else f.preview
                if len(content) > 4096:
                    content = content[:4096] + "\n... (truncated)"
                files_text_parts.append(
                    f"### {f.path} ({f.language})\n```{f.language}\n{content}\n```"
                )
                content_parts.append(content)

            files_context = "\n\n".join(files_text_parts)
            if len(files) > len(llm_files):
                files_context += (
                    f"\n\n_Note: showing {len(llm_files)} of {len(files)} files; "
                    "full inventory is generated separately._"
                )

            cache_key = module_cache_key(name, content_hash("".join(f.path for f in files)))

            cached = await self.cache.get(cache_key)
            if cached:
                try:
                    cached_doc = ModuleDoc(**cached)
                    if is_rich_module_doc(cached_doc):
                        return merge_module_doc(cached_doc, inventory_doc), True
                except Exception:
                    pass

            llm_doc: ModuleDoc | None = None
            try:
                messages = build_module_prompt(name, files_context, project_summary, self.language)
                raw = await self.llm.complete(messages, max_tokens=3072, operation="summary")
                data = extract_json(raw)
                if data and isinstance(data, dict):
                    data.setdefault("name", name)
                    filtered = {k: v for k, v in data.items() if k in ModuleDoc.model_fields}
                    try:
                        llm_doc = ModuleDoc(**filtered)
                    except Exception:
                        llm_doc = ModuleDoc(name=name, purpose=data.get("purpose", ""))
                else:
                    logger.warning("Failed to parse module '%s' JSON", name)
            except Exception as exc:
                logger.warning("LLM module analysis failed for '%s': %s", name, exc)

            doc = merge_module_doc(llm_doc, inventory_doc)
            if is_rich_module_doc(doc):
                await self.cache.put(cache_key, doc.model_dump())
            return doc, False

    async def _analyze_modules(
        self,
        modules: dict[str, list[FileInfo]],
        project_summary: str,
        project: ProjectContext,
        progress: Callable[[str], None],
    ) -> list[ModuleDoc]:
        tasks = []
        for name, files in modules.items():
            tasks.append(self._analyze_one_module(name, files, project_summary, project))

        results = []
        reused = 0
        regenerated = 0
        for i, coro in enumerate(asyncio.as_completed(tasks)):
            doc, was_cached = await coro
            if doc:
                results.append(doc)
                if was_cached:
                    reused += 1
                else:
                    regenerated += 1
            progress(f"Analyzed module {i + 1}/{len(tasks)}")

        if reused:
            progress(f"Module analysis: {reused} reused from cache, {regenerated} regenerated")

        results.sort(key=lambda m: -len(m.files))
        return results

    async def _generate_architecture(
        self, project: ProjectContext, key_files: str, tree_hash: str
    ) -> ArchitectureDiagram:
        cache_key = f"arch:v2:{tree_hash}"
        cached = await self.cache.get(cache_key)
        if cached:
            try:
                return ArchitectureDiagram(**cached)
            except Exception:
                pass

        messages = build_architecture_prompt(project.file_tree, key_files, self.language)
        raw = await self.llm.complete(messages, max_tokens=4096, operation="wiki")
        data = extract_json(raw)
        partial = salvage_architecture_partial(raw)
        if not data or not isinstance(data, dict):
            logger.warning("Failed to parse architecture JSON; salvaging mermaid fields")
            data = partial
        else:
            for key, value in partial.items():
                if value and not data.get(key):
                    data[key] = value

        filtered = {k: v for k, v in data.items() if k in ArchitectureDiagram.model_fields}
        try:
            arch = ArchitectureDiagram(**filtered)
        except Exception:
            arch = ArchitectureDiagram()
        await self.cache.put(cache_key, arch.model_dump())
        return arch

    async def _generate_reading_guide(
        self,
        project: ProjectContext,
        module_docs: list[ModuleDoc],
        tree_hash: str,
    ) -> ReadingGuide:
        # PageRank over the import graph decides which files matter; scan order
        # only fills the tail when the graph is smaller than the display limit.
        ranked = DependencyGraph.build_from_project(project).rank_files()
        by_path = {f.path: f for f in project.files}
        ranked_paths = [path for path, _ in ranked[:20]]
        seen = set(ranked_paths)
        for f in project.files:
            if len(ranked_paths) >= 20:
                break
            if f.path not in seen:
                ranked_paths.append(f.path)
                seen.add(f.path)

        rankings_parts = []
        for i, path in enumerate(ranked_paths, 1):
            f = by_path[path]
            tag = ""
            if f.is_entrypoint:
                tag = " [entrypoint]"
            elif f.is_config:
                tag = " [config]"
            rankings_parts.append(f"{i}. {path}{tag} ({f.lines} lines)")
        rankings = "\n".join(rankings_parts)

        module_parts = []
        for m in module_docs:
            module_parts.append(f"- **{m.name}**: {m.purpose}")
        module_summaries = "\n".join(module_parts)

        # key on the actual prompt inputs so an import-only edit that reshuffles
        # the ranking also invalidates the cached guide
        cache_key = f"guide:{tree_hash}:{content_hash(rankings + module_summaries)}"
        cached = await self.cache.get(cache_key)
        if cached:
            try:
                return ReadingGuide(**cached)
            except Exception:
                pass

        messages = build_reading_guide_prompt(rankings, module_summaries, self.language)
        raw = await self.llm.complete(messages, max_tokens=2048, operation="wiki")
        data = extract_json(raw)
        if not data or not isinstance(data, dict):
            logger.warning("Failed to parse reading guide JSON")
            return ReadingGuide()

        filtered = {k: v for k, v in data.items() if k in ReadingGuide.model_fields}
        try:
            guide = ReadingGuide(**filtered)
        except Exception:
            guide = ReadingGuide()
        await self.cache.put(cache_key, guide.model_dump())
        return guide
