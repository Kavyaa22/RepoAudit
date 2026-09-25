"""Score how closely a recommended tree matches the action_api style pack."""

from __future__ import annotations

import re

from repoaudit.audit.structure_context import (
    TYPE_BUCKET_SEGMENTS,
    extract_paths_from_tree,
)
from repoaudit.audit.structure_style import (
    DEFAULT_STRUCTURE_STYLE,
    STRUCTURE_STYLE_ACTION_API,
    STRUCTURE_STYLE_CONSERVATIVE,
)
from repoaudit.audit.structure_tree_quality import evaluate_tree_quality


def _proposed_section(text: str) -> str:
    """Prefer the Proposed Structure section so Previous Structure does not skew scores."""
    lower = text.lower()
    markers = (
        "### 3. proposed structure",
        "## proposed structure",
        "### proposed structure",
        "### recommended target structure",
    )
    start = -1
    for marker in markers:
        idx = lower.find(marker)
        if idx >= 0:
            start = idx
            break
    if start < 0:
        return text
    rest = text[start:]
    # Cut at next major section if present
    cut = re.search(r"\n###\s+[1-9]\.\s+", rest[10:])
    if cut:
        return rest[: cut.start() + 10]
    cut2 = re.search(r"\n###\s+4\.\s+", rest)
    if cut2:
        return rest[: cut2.start()]
    return rest


def score_action_api_style(recommended_structure: str) -> tuple[int, list[str]]:
    """
    Return (0-100 score, list of short gap notes).
    Higher = closer to feature → action → files.
    """
    text = _proposed_section(recommended_structure or "")
    text_lower = text.lower()
    paths = extract_paths_from_tree(text)
    notes: list[str] = []
    if not text.strip():
        return 0, ["Recommended tree is empty"]

    score = 100

    has_backend = "backend/" in text_lower or any(
        str(p).lower().startswith("backend/") for p in paths
    )
    has_frontend = "frontend/" in text_lower or any(
        str(p).lower().startswith("frontend/") for p in paths
    )
    if not has_backend:
        score -= 25
        notes.append("Missing backend/ files")
    if not has_frontend:
        score -= 25
        notes.append("Missing frontend/ files")

    for root, label in (
        ("docs", "docs/"),
        ("scripts", "scripts/"),
        ("templates-src", "templates-src/"),
    ):
        top_path = any(
            p.replace("\\", "/").lower().startswith(f"{root}/") for p in paths
        )
        top_tree = bool(re.search(rf"(?m)^[├└]──\s*{re.escape(root)}/", text_lower))
        if top_path or top_tree:
            score -= 12
            notes.append(f"Top-level '{label}' should be folded into backend/ or frontend/")

    # Penalize leftover type buckets in the proposed tree
    type_hits = sum(
        1
        for p in paths
        if any(f"/{seg}/" in f"/{p.replace(chr(92), '/').lower()}/" for seg in TYPE_BUCKET_SEGMENTS)
    )
    if type_hits >= 5:
        score -= 25
        notes.append("Many files still sit under type folders (components/services/lib/…)")
    elif type_hits >= 2:
        score -= 12
        notes.append("Some files still sit under type folders (components/services/lib/…)")

    # Feature → action nesting (from reconstructed paths + raw text)
    def _fa_count(root: str) -> int:
        n = 0
        for p in paths:
            pl = p.replace("\\", "/").lower()
            if re.search(rf"{root}/src/(?:features/)?[a-z0-9_-]+/[a-z0-9_-]+/", pl):
                n += 1
        return n

    be_hits = _fa_count("backend") + len(
        re.findall(r"backend/src/[a-z0-9_-]+/[a-z0-9_-]+/", text_lower)
    )
    fe_hits = _fa_count("frontend") + len(
        re.findall(r"frontend/src/[a-z0-9_-]+/[a-z0-9_-]+/", text_lower)
    )
    legacy_api = len(re.findall(r"/api/[^/\s]+_api/[^/\s]+_api/", text_lower))
    legacy_feat = len(re.findall(r"/features/[^/\s]+/[^/\s]+/", text_lower))

    backend_action = be_hits + legacy_api
    frontend_action = fe_hits + legacy_feat

    if has_backend and backend_action < 1:
        score -= 20
        notes.append("Few backend files sit under feature/action folders")
    elif has_backend and backend_action < 2:
        score -= 8
        notes.append("Only some backend files use feature/action folders")

    if has_frontend and frontend_action < 1:
        score -= 15
        notes.append("Few frontend files sit under feature/action folders")
    elif has_frontend and frontend_action < 2:
        score -= 6
        notes.append("Only some frontend files use feature/action folders")

    if "src/pages/" in text_lower and (
        "/features/" in text_lower or re.search(r"frontend/src/[a-z0-9_-]+/[a-z0-9_-]+/", text_lower)
    ):
        score -= 10
        notes.append("Frontend still mixes pages/ with feature/action folders")

    # Critique rubric: catalog size, scatter, verb purity, FE/BE symmetry, orphans
    quality = evaluate_tree_quality(text)
    if quality.feature_count > 12:
        score -= min(20, (quality.feature_count - 12) * 2)
        notes.append(
            f"Too many top-level features ({quality.feature_count}); aim for ~8–12"
        )
    if quality.scatter_hits:
        score -= min(20, 6 * len(quality.scatter_hits))
        notes.append("Same feature scattered under synonym folders")
    if quality.verb_purity < 0.9:
        score -= int((1.0 - quality.verb_purity) * 25)
        notes.append(
            f"Action folders are not meaningful verbs (purity {quality.verb_purity:.0%})"
        )
    if quality.orphan_features:
        score -= min(12, 4 * len(quality.orphan_features))
        notes.append("Feature folders without production source (tests/css only)")
    if (
        quality.backend_features
        and quality.frontend_features
        and quality.fe_be_jaccard < 0.35
        and len(quality.backend_features | quality.frontend_features) >= 4
    ):
        score -= 10
        notes.append("Backend and frontend feature sets are poorly aligned")

    # Fake camelCase hierarchy smell (thank/you, measure/in)
    if re.search(r"/(thank|measure|relative|peg)/(you|in|time|viewport)/", text_lower):
        score -= 25
        notes.append("Folders look like camelCase filename splits, not product features")

    return max(0, min(100, score)), notes


def score_structure_style(
    recommended_structure: str,
    structure_style: str = DEFAULT_STRUCTURE_STYLE,
) -> tuple[int, list[str]]:
    if structure_style == STRUCTURE_STYLE_CONSERVATIVE:
        if not (recommended_structure or "").strip():
            return 0, ["No file paths found"]
        return 80, []
    if structure_style == STRUCTURE_STYLE_ACTION_API:
        return score_action_api_style(recommended_structure)
    return score_action_api_style(recommended_structure)
