"""Hybrid retrieval: lexical TF-IDF + local embedding cosine + synonym boosts."""

from __future__ import annotations

from dataclasses import dataclass

from repoaudit.indexing.models import ProjectContext
from repoaudit.investigation.keywords import SYNONYMS, extract_search_terms
from repoaudit.retrieval.lexical import Chunk, SimpleRAG, format_context
from repoaudit.retrieval.semantic import EmbeddingIndex

__all__ = ["HybridRAG", "SimpleRAG", "format_context", "Chunk", "EmbeddingIndex"]


@dataclass
class _BoostedChunk:
    chunk: Chunk
    boost: float


class HybridRAG:
    """Merge TF-IDF, embedding similarity, and synonym/path boosts."""

    def __init__(self) -> None:
        self._lexical = SimpleRAG()
        self._embeddings = EmbeddingIndex()
        self._project: ProjectContext | None = None

    def index(self, project: ProjectContext) -> None:
        self._project = project
        self._lexical.index(project)
        self._embeddings.index(project)

    def retrieve(self, query: str, top_k: int = 15) -> list[Chunk]:
        lexical = self._lexical.retrieve(query, top_k=max(top_k, 20))
        semantic = self._embeddings.retrieve(query, top_k=max(top_k, 20))
        terms = extract_search_terms(query)
        expanded: set[str] = set(terms)
        for term in terms:
            for synonym in SYNONYMS.get(term, []):
                expanded.add(synonym.lower())

        boosted: dict[str, _BoostedChunk] = {}

        def upsert(chunk: Chunk, weight: float, key_suffix: str = "") -> None:
            key = f"{chunk.file_path}:{chunk.line_start}:{chunk.line_end}:{key_suffix}"
            score = float(chunk.score) * weight
            existing = boosted.get(key)
            if existing is None:
                boosted[key] = _BoostedChunk(chunk=chunk, boost=score)
            else:
                existing.boost = min(1.5, existing.boost + score)

        for chunk in lexical:
            upsert(chunk, weight=1.0, key_suffix="lex")
        for chunk in semantic:
            # Embeddings are primary for wording mismatch; weight slightly higher.
            upsert(chunk, weight=1.15, key_suffix="emb")

        if self._project is not None and expanded:
            for file_info in self._project.files:
                path = file_info.path.replace("\\", "/").strip("/")
                haystack = f"{path}\n{file_info.content or file_info.preview or ''}".lower()
                overlap = sum(1 for term in expanded if term and term in haystack)
                if overlap <= 0:
                    continue
                preview = (file_info.content or file_info.preview or "")[:1200]
                semantic_score = min(0.95, 0.15 * overlap)
                upsert(
                    Chunk(
                        file_path=path,
                        line_start=1,
                        line_end=max(1, preview.count("\n") + 1),
                        content=preview,
                        score=semantic_score,
                    ),
                    weight=0.8,
                    key_suffix="syn",
                )

        # Collapse by file path keeping best boost, preserve chunk text from best hit.
        by_file: dict[str, _BoostedChunk] = {}
        for item in boosted.values():
            path = item.chunk.file_path
            prev = by_file.get(path)
            if prev is None or item.boost > prev.boost:
                by_file[path] = item

        ranked = sorted(by_file.values(), key=lambda item: item.boost, reverse=True)
        results: list[Chunk] = []
        for item in ranked[:top_k]:
            item.chunk.score = item.boost
            results.append(item.chunk)
        return results
