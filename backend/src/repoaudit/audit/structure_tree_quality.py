"""Post-placement tree quality gates for feature → action recommendations.

Mirrors the human critique rubric:
  - top-level feature count (~8–12)
  - synonym scatter (auth + authentication)
  - action verb purity (no thank/you leftovers)
  - FE/BE feature symmetry
  - orphan features (tests-only / css-only)
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from repoaudit.audit.structure_catalog import (
    ALLOWED_ACTIONS,
    JUNK_ACTION_NAMES,
    SOFT_FEATURE_CAP,
    SOFT_FEATURE_MIN,
    canonicalize_feature,
    scatter_families,
)
from repoaudit.audit.structure_context import extract_paths_from_tree

SOURCE_EXT = {".ts", ".tsx", ".js", ".jsx", ".py", ".mjs", ".cjs", ".html", ".vue", ".svelte"}
TEST_MARKERS = (".test.", ".spec.", "/tests/", "/test/", "test_")
STYLE_EXT = {".css", ".scss", ".sass", ".less"}


@dataclass
class TreeQualityReport:
    feature_count: int = 0
    features: list[str] = field(default_factory=list)
    backend_features: set[str] = field(default_factory=set)
    frontend_features: set[str] = field(default_factory=set)
    verb_purity: float = 1.0  # 0–1
    scatter_hits: list[str] = field(default_factory=list)
    junk_actions: list[str] = field(default_factory=list)
    orphan_features: list[str] = field(default_factory=list)
    fe_be_jaccard: float = 1.0
    issues: list[str] = field(default_factory=list)
    score: int = 100  # 0–100 quality sub-score

    @property
    def ok(self) -> bool:
        return not self.issues


def _proposed_paths(text: str) -> list[str]:
    return [p.replace("\\", "/").strip("/") for p in extract_paths_from_tree(text or "")]


def _feature_action_from_dest(path: str) -> tuple[str | None, str | None]:
    """Extract FEATURE/ACTION from .../src/FEATURE/ACTION/... or .../src/features/FEATURE/ACTION/."""
    pl = path.replace("\\", "/").lower()
    m = re.search(r"(?:backend|frontend)/src/(?:features/)?([a-z0-9_-]+)/([a-z0-9_-]+)/", pl)
    if not m:
        return None, None
    feature, action = m.group(1), m.group(2)
    if feature in {"shared", "common"} and action in {"lib", "ui", "api", "db", "logger"}:
        return feature, action
    return feature, action


def evaluate_tree_quality(recommended_structure: str) -> TreeQualityReport:
    paths = _proposed_paths(recommended_structure)
    report = TreeQualityReport()
    if not paths:
        report.issues.append("Recommended tree has no file leaves")
        report.score = 0
        return report

    features: set[str] = set()
    actions_seen: list[str] = []
    be: set[str] = set()
    fe: set[str] = set()
    by_feature_files: dict[str, list[str]] = {}

    for p in paths:
        feature, action = _feature_action_from_dest(p)
        if not feature or not action:
            continue
        features.add(feature)
        actions_seen.append(action)
        by_feature_files.setdefault(feature, []).append(p)
        if p.lower().startswith("backend/"):
            be.add(feature)
        elif p.lower().startswith("frontend/"):
            fe.add(feature)

    # Exclude shared from "product feature" count pressure
    product_features = sorted(f for f in features if f != "shared")
    report.features = product_features
    report.feature_count = len(product_features)
    report.backend_features = be - {"shared"}
    report.frontend_features = fe - {"shared"}

    # Verb purity
    if actions_seen:
        good = sum(
            1
            for a in actions_seen
            if a in ALLOWED_ACTIONS or a not in JUNK_ACTION_NAMES
        )
        # Stricter: count junk explicitly
        junk = [a for a in actions_seen if a in JUNK_ACTION_NAMES or a not in ALLOWED_ACTIONS]
        # Template variant actions may not be in ALLOWED_ACTIONS but aren't junk
        junk = [
            a
            for a in actions_seen
            if a in JUNK_ACTION_NAMES
            or (
                a not in ALLOWED_ACTIONS
                and canonicalize_feature(a) == a
                and len(a) <= 3  # very short leftovers like in, you, you
            )
        ]
        report.junk_actions = sorted(set(junk))[:20]
        report.verb_purity = 1.0 - (len(junk) / max(1, len(actions_seen)))
    else:
        report.verb_purity = 0.0

    # Scatter: same alias family appears as multiple top-level feature folders
    families = scatter_families()
    present_lower = {f.lower().replace("-", "_") for f in features}
    for canon, aliases in families.items():
        hits = sorted(a for a in aliases if a in present_lower and a != canon)
        # Also if both auth and authentication present
        family_present = [a for a in aliases if a in present_lower]
        if len(set(canonicalize_feature(x) or x for x in family_present)) == 1 and len(family_present) > 1:
            # Multiple spellings of same canon both as folders
            if len([f for f in features if canonicalize_feature(f) == canon]) > 1:
                report.scatter_hits.append(
                    f"{canon}: multiple folders {sorted(f for f in features if canonicalize_feature(f) == canon)}"
                )
        # Direct: auth and authentication both in features
        spellings = [f for f in features if canonicalize_feature(f) == canon]
        if len(set(spellings)) > 1:
            msg = f"{canon} scattered as {sorted(set(spellings))}"
            if msg not in report.scatter_hits:
                report.scatter_hits.append(msg)

    # Orphans: feature with only tests or only css/json
    for feature, files in by_feature_files.items():
        if feature == "shared":
            continue
        sources = [
            f
            for f in files
            if os.path.splitext(f)[1].lower() in SOURCE_EXT
            and not any(m in f.lower() for m in TEST_MARKERS)
            and not f.lower().split("/")[-1].startswith("test_")
        ]
        if not sources:
            only_style = all(os.path.splitext(f)[1].lower() in STYLE_EXT | {".json"} for f in files)
            report.orphan_features.append(
                f"{feature} ({'styles/json only' if only_style else 'tests only / no production source'})"
            )

    # FE/BE Jaccard
    if report.backend_features or report.frontend_features:
        inter = report.backend_features & report.frontend_features
        union = report.backend_features | report.frontend_features
        report.fe_be_jaccard = len(inter) / len(union) if union else 1.0
    else:
        report.fe_be_jaccard = 1.0

    # Build issues + score
    score = 100
    if report.feature_count > SOFT_FEATURE_CAP:
        over = report.feature_count - SOFT_FEATURE_CAP
        score -= min(30, over * 3)
        report.issues.append(
            f"Too many top-level features ({report.feature_count}); aim for {SOFT_FEATURE_MIN}–{SOFT_FEATURE_CAP}"
        )
    elif report.feature_count > 20:
        score -= 35
        report.issues.append(f"Feature explosion ({report.feature_count} domains)")

    if report.scatter_hits:
        score -= min(25, 8 * len(report.scatter_hits))
        report.issues.append("Feature synonym scatter: " + "; ".join(report.scatter_hits[:3]))

    if report.verb_purity < 0.85:
        score -= int((1.0 - report.verb_purity) * 40)
        report.issues.append(
            f"Action verb purity {report.verb_purity:.0%}; junk actions: {', '.join(report.junk_actions[:8]) or 'n/a'}"
        )

    if report.orphan_features:
        score -= min(15, 5 * len(report.orphan_features))
        report.issues.append(
            "Orphan feature folders (no production source): " + ", ".join(report.orphan_features[:5])
        )

    if (
        report.backend_features
        and report.frontend_features
        and report.fe_be_jaccard < 0.35
        and len(report.backend_features | report.frontend_features) >= 4
    ):
        score -= 15
        report.issues.append(
            f"Weak backend/frontend feature symmetry (Jaccard={report.fe_be_jaccard:.2f})"
        )

    report.score = max(0, min(100, score))
    return report


def quality_issues_for_validation(recommended_structure: str) -> list[str]:
    """Issues list suitable to append to validate_recommended_structure."""
    return evaluate_tree_quality(recommended_structure).issues
