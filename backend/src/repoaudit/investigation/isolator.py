"""Feature Path Isolator: Maps issue descriptions, stack traces, routes, and RAG hits to code files."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from repoaudit.investigation.evidence import extract_routes, extract_stack_paths
from repoaudit.investigation.graph import build_import_neighbors, expand_via_graph
from repoaudit.investigation.investigation_models import IsolatedTarget, IssueReport
from repoaudit.investigation.keywords import extract_search_terms, primary_feature_action

if TYPE_CHECKING:
    from repoaudit.indexing.models import ProjectContext
    from repoaudit.retrieval.lexical import Chunk

ROUTE_FILE_HINTS = ("route", "routes", "router", "api", "handler", "handlers", "controller", "controllers", "endpoint", "view")
UI_FILE_HINTS = ("component", "components", "page", "pages", "view", "views", "screen", "screens", "hook", "hooks")
ENTRYPOINT_NAMES = (
    "main.py", "app.py", "server.py", "index.ts", "index.tsx", "index.js", "app.tsx", "routes.tsx", "router.ts",
)


class FeaturePathIsolator:
    """Isolates relevant backend & frontend file targets via normalized multi-signal ranking."""

    def isolate_targets(
        self,
        report: IssueReport,
        project: ProjectContext,
        rag_chunks: list[Chunk] | None = None,
        max_targets: int = 10,
    ) -> list[IsolatedTarget]:
        feature, action = primary_feature_action(
            report.issue_description,
            report.feature_name,
            report.action_name,
        )
        combined_text = "\n".join(
            [
                report.issue_description or "",
                report.error_log or "",
                report.expected_behavior or "",
                report.actual_behavior or "",
                "\n".join(a.content for a in report.live_artifacts),
            ]
        )
        search_terms = extract_search_terms(
            report.issue_description,
            report.error_log + "\n" + "\n".join(a.content for a in report.live_artifacts),
            report.feature_name,
            report.action_name,
        )
        trace_paths = extract_stack_paths(combined_text)
        routes = extract_routes(combined_text)
        route_tokens = self._route_tokens(routes)

        scores: dict[str, tuple[int, list[str]]] = {}

        def bump(path: str, amount: int, reason: str) -> None:
            current_score, reasons = scores.get(path, (0, []))
            if reason not in reasons:
                reasons = reasons + [reason]
            scores[path] = (current_score + amount, reasons)

        content_candidates = self._content_candidates(search_terms + route_tokens)

        for file_info in project.files:
            rel_path = file_info.path.replace("\\", "/").strip("/")
            rel_lower = rel_path.lower()
            filename = rel_path.split("/")[-1].lower()
            path_parts = rel_lower.split("/")
            content_lower = (file_info.content or file_info.preview or "").lower()

            for trace_path in trace_paths:
                t_clean = trace_path.lower()
                if rel_lower.endswith(t_clean) or t_clean in rel_lower:
                    bump(rel_path, 115, f"Direct match in error stack trace ('{trace_path}')")
                    break

            for route in routes:
                route_leaf = route.strip("/").split("/")[-1].lower()
                route_fragment = route.strip("/").replace("/", " ").replace("-", "_").lower()
                if route and route.lower() in content_lower:
                    bump(rel_path, 92, f"File declares or calls failing route '{route}'")
                elif route_leaf and (route_leaf in filename or route_leaf in path_parts):
                    bump(rel_path, 78, f"Path matches failing route segment '{route_leaf}'")
                elif route_fragment and all(tok in rel_lower for tok in route_fragment.split()[-2:]):
                    bump(rel_path, 62, f"Path matches route shape '{route}'")

            if feature:
                if feature in path_parts:
                    bump(rel_path, 62, f"Path segment matches feature '{feature}'")
                elif feature in filename:
                    bump(rel_path, 55, f"Filename contains feature '{feature}'")
                elif feature in content_lower and any(hint in rel_lower for hint in UI_FILE_HINTS + ROUTE_FILE_HINTS):
                    bump(rel_path, 28, f"Feature term '{feature}' appears in likely entry file")

            if action:
                if action in filename or action in path_parts:
                    bump(rel_path, 35, f"Path matches action '{action}'")
                elif action in content_lower:
                    bump(rel_path, 20, f"Content references action '{action}'")

            for term in search_terms:
                if term in filename:
                    bump(rel_path, 32, f"Filename contains '{term}'")
                if term in path_parts:
                    bump(rel_path, 26, f"Path segment matches '{term}'")

            if rel_lower.endswith(ENTRYPOINT_NAMES) or getattr(file_info, "is_entrypoint", False):
                if any(token in content_lower for token in route_tokens + [feature, action] if token):
                    bump(rel_path, 24, "Project-aware entrypoint references supplied feature or route")

            for token in content_candidates:
                if token and token in content_lower:
                    bump(rel_path, 10, f"Content references '{token}'")

        if rag_chunks:
            file_chunk_scores: dict[str, list[float]] = {}
            for chunk in rag_chunks:
                if chunk.score <= 0:
                    continue
                file_chunk_scores.setdefault(chunk.file_path, []).append(chunk.score)

            if file_chunk_scores:
                max_score = max(max(vals) for vals in file_chunk_scores.values())
                for path, vals in file_chunk_scores.items():
                    normalized = int(min(70, round((max(vals) / max_score) * 70)))
                    if normalized > 0:
                        bump(path, normalized, "Lexical/hybrid retrieval relevance to issue evidence")

        # Prefer graph neighbors of strong stack/route hits over folder-name guessing.
        seed_paths = [
            path
            for path, (score, _) in scores.items()
            if score >= 60
        ]
        if seed_paths:
            neighbors = build_import_neighbors(project)
            for neighbor in expand_via_graph(seed_paths[:5], neighbors, max_extra=8):
                  bump(neighbor, 48, "Import/AST call-graph neighbor of a high-confidence seed file")

        targets: list[IsolatedTarget] = []
        for path, (score, reasons) in scores.items():
            if score < 28:
                continue
            rel_lower = path.lower()
            scope = (
                "backend"
                if rel_lower.startswith(("backend/", "server/", "api/")) or any(h in rel_lower for h in ROUTE_FILE_HINTS)
                else "frontend"
                if rel_lower.startswith(("frontend/", "client/", "src/", "app/")) or any(h in rel_lower for h in UI_FILE_HINTS)
                else "common"
            )
            targets.append(
                IsolatedTarget(
                    path=path,
                    scope=scope,
                    feature_name=feature or "general",
                    action_name=action or "service",
                    relevance_score=min(100, score),
                    matched_reason="; ".join(reasons),
                )
            )

        targets.sort(key=lambda t: t.relevance_score, reverse=True)
        return targets[:max_targets]

    @staticmethod
    def _route_tokens(routes: list[str]) -> list[str]:
        tokens: list[str] = []
        for route in routes:
            for token in re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", route):
                lowered = token.lower()
                if lowered not in tokens and lowered not in {"api", "v1"}:
                    tokens.append(lowered)
        return tokens

    @staticmethod
    def _content_candidates(tokens: list[str]) -> list[str]:
        keep: list[str] = []
        for token in tokens:
            token = token.strip().lower()
            if len(token) < 4 or token in keep:
                continue
            keep.append(token)
            if len(keep) >= 8:
                break
        return keep
