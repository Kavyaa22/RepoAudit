"""Multi-pass structure generation: catalog → place → validate → merge.

Pass order:
  1. Discover closed feature catalog (aliases merged, soft-capped)
  2. Place each inventory file into catalog feature + allowed action
  3. Validate tree quality (scatter, verb purity, FE/BE, orphans)
  4. Merge into recommended markdown tree (+ quality footer)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING

from repoaudit.audit.structure_action_style import infer_feature_action, suggest_action_api_path
from repoaudit.audit.structure_catalog import discover_feature_catalog
from repoaudit.audit.structure_style import PRODUCT_ROOTS
from repoaudit.audit.structure_target import live_inventory_paths, render_directory_tree
from repoaudit.audit.structure_tree_quality import evaluate_tree_quality

if TYPE_CHECKING:
    from repoaudit.indexing.models import ProjectContext

logger = logging.getLogger(__name__)


def build_topology(
    project: ProjectContext,
    exclude_paths: set[str] | None = None,
) -> dict:
    """
    Pass 1–2 (deterministic): catalog discovery, then feature/action placement.
    """
    paths = live_inventory_paths(project, exclude_paths)
    catalog = discover_feature_catalog(paths)
    features: dict[str, set[str]] = defaultdict(set)
    consolidations: list[dict[str, str]] = []
    backend_paths: list[str] = []
    frontend_paths: list[str] = []
    other_paths: list[str] = []

    for src in paths:
        dest = suggest_action_api_path(src, catalog=catalog)
        top = src.split("/", 1)[0]
        if top not in PRODUCT_ROOTS and dest != src:
            consolidations.append({"from": src, "to": dest})
        if dest.startswith("backend/"):
            backend_paths.append(dest)
            if "/src/" in dest and dest.count("/") >= 4:
                fa = infer_feature_action(src, catalog=catalog)
                features[fa.feature].add(fa.action)
            elif "/api/" in dest:
                fa = infer_feature_action(src, catalog=catalog)
                features[fa.feature].add(fa.action)
        elif dest.startswith("frontend/"):
            frontend_paths.append(dest)
            if "/src/" in dest and dest.count("/") >= 4:
                fa = infer_feature_action(src, catalog=catalog)
                features[fa.feature].add(fa.action)
            elif "/features/" in dest:
                fa = infer_feature_action(src, catalog=catalog)
                features[fa.feature].add(fa.action)
        else:
            other_paths.append(dest if dest != src else src)

    return {
        "catalog": catalog,
        "features": {k: sorted(v) for k, v in sorted(features.items())},
        "consolidations": consolidations[:80],
        "backend_paths": sorted(set(backend_paths)),
        "frontend_paths": sorted(set(frontend_paths)),
        "other_paths": sorted(set(other_paths)),
    }


def format_topology_block(topology: dict) -> str:
    lines = ["Detected feature → action topology:"]
    catalog = topology.get("catalog") or []
    if catalog:
        lines.append("  Catalog (closed): " + ", ".join(catalog))
    feats = topology.get("features") or {}
    if not feats:
        lines.append("  (none detected yet — place into catalog features only)")
    for feature, actions in feats.items():
        lines.append(f"  - {feature}: {', '.join(actions)}")
    consolidations = topology.get("consolidations") or []
    if consolidations:
        lines.append("Consolidations (fold into backend/frontend):")
        for item in consolidations[:20]:
            lines.append(f"  - {item['from']} → {item['to']}")
    return "\n".join(lines)


def merge_product_trees(
    backend_paths: list[str],
    frontend_paths: list[str],
    other_paths: list[str] | None = None,
    *,
    title: str = "action_api multipass",
    quality_footer: str | None = None,
) -> str:
    """Pass 4: merge backend + frontend path lists into one recommended markdown tree."""
    all_paths = list(backend_paths) + list(frontend_paths) + list(other_paths or [])
    # Drop empty / trailing-slash-only
    all_paths = [p.replace("\\", "/").strip("/") for p in all_paths if p and not p.endswith("/")]
    header = (
        f"### Recommended target structure ({title})\n\n"
        "Hierarchy: **Main Folder → Feature → Action → Files** "
        "(not by components/services/hooks).\n\n"
        "**Migration phases:**\n"
        "1. Fold consolidatable roots into backend/ and frontend/.\n"
        "2. Move backend files into feature/action folders under backend/src/.\n"
        "3. Move frontend files into feature/action folders under frontend/src/."
    )
    parts = [
        header,
        "",
        "Built with multipass: catalog → place → validate → merge.",
        "",
        render_directory_tree(all_paths),
    ]
    if quality_footer:
        parts.extend(["", quality_footer])
    return "\n".join(parts)


def _quality_footer(tree: str, catalog: list[str] | None = None) -> str:
    report = evaluate_tree_quality(tree)
    lines = [
        "### Structure quality gate",
        f"- Quality score: **{report.score}/100**",
        f"- Product features: {report.feature_count} ({', '.join(report.features) or 'none'})",
        f"- Action verb purity: {report.verb_purity:.0%}",
        f"- Backend↔frontend Jaccard: {report.fe_be_jaccard:.2f}",
    ]
    if catalog:
        lines.append(f"- Catalog used: {', '.join(catalog)}")
    if report.issues:
        lines.append("- Gate findings:")
        for issue in report.issues[:8]:
            lines.append(f"  - {issue}")
    else:
        lines.append("- Gate findings: none")
    return "\n".join(lines)


def build_multipass_deterministic(
    project: ProjectContext,
    exclude_paths: set[str] | None = None,
) -> tuple[dict, str]:
    """Full deterministic multipass without LLM: catalog → place → validate → merge."""
    topology = build_topology(project, exclude_paths)
    bare = merge_product_trees(
        topology["backend_paths"],
        topology["frontend_paths"],
        topology.get("other_paths"),
        title="action_api multipass",
    )
    report = evaluate_tree_quality(bare)
    topology["quality"] = {
        "score": report.score,
        "issues": report.issues,
        "features": report.features,
        "verb_purity": report.verb_purity,
        "fe_be_jaccard": report.fe_be_jaccard,
    }
    tree = merge_product_trees(
        topology["backend_paths"],
        topology["frontend_paths"],
        topology.get("other_paths"),
        title="action_api multipass",
        quality_footer=_quality_footer(bare, topology.get("catalog")),
    )
    if report.issues:
        logger.info(
            "Multipass quality gate: score=%s issues=%s",
            report.score,
            "; ".join(report.issues[:3]),
        )
    return topology, tree


def root_slice_prompt(
    *,
    root: str,
    paths: list[str],
    topology_block: str,
    style_block: str,
) -> str:
    """User prompt for generating one product-root tree."""
    shown = paths[:200]
    return "\n".join(
        [
            f"Generate ONLY the `{root}/` portion of the recommended_structure.",
            "Return JSON: {\"tree_paths\": [\"root/.../file.ext\", ...], \"notes\": \"string\"}",
            "List concrete file paths (not folders only). Follow the target style.",
            "Place files ONLY into the closed feature catalog from the topology block.",
            "Actions must be real verbs (create, login, export, …) — never camelCase leftovers.",
            "",
            "TARGET STYLE:",
            style_block,
            "",
            topology_block,
            "",
            f"Live/mapped paths for {root}/:",
            *shown,
        ]
    )
