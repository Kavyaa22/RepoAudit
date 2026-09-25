"""Local embedding index for investigation retrieval (no external API required)."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from repoaudit.indexing.models import ProjectContext
from repoaudit.retrieval.lexical import Chunk

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def _tokenize(text: str) -> list[str]:
    tokens = [t.lower() for t in _TOKEN_RE.findall(text or "")]
    # Character trigrams improve semantic-ish matching across naming styles.
    grams: list[str] = []
    compact = re.sub(r"[^a-z0-9]+", " ", (text or "").lower())
    for word in compact.split():
        padded = f"#{word}#"
        grams.extend(padded[i : i + 3] for i in range(max(0, len(padded) - 2)))
    return tokens + grams


def _vectorize(tokens: list[str]) -> dict[str, float]:
    counts = Counter(tokens)
    if not counts:
        return {}
    norm = math.sqrt(sum(v * v for v in counts.values())) or 1.0
    return {k: v / norm for k, v in counts.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


@dataclass
class _IndexedChunk:
    chunk: Chunk
    vector: dict[str, float]


class EmbeddingIndex:
    """Dense-ish local embeddings via token+trigram hashing and cosine similarity."""

    def __init__(self) -> None:
        self._items: list[_IndexedChunk] = []

    def index(self, project: ProjectContext, max_chars: int = 2500) -> None:
        self._items = []
        for file_info in project.files:
            content = file_info.content or file_info.preview or ""
            if not content.strip():
                continue
            path = file_info.path.replace("\\", "/").strip("/")
            text = f"{path}\n{content[:max_chars]}"
            chunk = Chunk(
                file_path=path,
                line_start=1,
                line_end=max(1, text.count("\n") + 1),
                content=text[:1200],
                score=0.0,
            )
            self._items.append(_IndexedChunk(chunk=chunk, vector=_vectorize(_tokenize(text))))

    def retrieve(self, query: str, top_k: int = 15) -> list[Chunk]:
        q = _vectorize(_tokenize(query))
        scored: list[Chunk] = []
        for item in self._items:
            score = _cosine(q, item.vector)
            if score <= 0.05:
                continue
            chunk = Chunk(
                file_path=item.chunk.file_path,
                line_start=item.chunk.line_start,
                line_end=item.chunk.line_end,
                content=item.chunk.content,
                score=float(score),
            )
            scored.append(chunk)
        scored.sort(key=lambda c: c.score, reverse=True)
        return scored[:top_k]
