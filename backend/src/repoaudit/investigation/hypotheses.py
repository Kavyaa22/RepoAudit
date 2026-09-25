"""Hypothesis Engine: Generates and ranks evidence-based root cause hypotheses."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from repoaudit.investigation.correlation import build_correlation_leads, correlation_summary
from repoaudit.investigation.evidence import extract_routes, extract_stack_paths
from repoaudit.investigation.investigation_models import Hypothesis, IsolatedTarget, IssueReport

if TYPE_CHECKING:
    from repoaudit.indexing.models import ProjectContext
    from repoaudit.retrieval.lexical import Chunk


@dataclass
class _Candidate:
    category: str
    title: str
    description: str
    score: int = 0
    support: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    next_check: str = ""

    def add(self, points: int, signal: str) -> None:
        self.score += points
        if signal not in self.support:
            self.support.append(signal)

    def penalize(self, points: int, signal: str) -> None:
        self.score -= points
        if signal not in self.contradictions:
            self.contradictions.append(signal)


class HypothesisEngine:
    """Generates competing diagnostic hypotheses from explicit evidence."""

    def generate_hypotheses(
        self,
        report: IssueReport,
        project: ProjectContext,
        targets: list[IsolatedTarget],
        rag_chunks: list[Chunk] | None = None,
    ) -> list[Hypothesis]:
        text = "\n".join(
            [
                report.error_log or "",
                report.issue_description or "",
                report.expected_behavior or "",
                report.actual_behavior or "",
                "\n".join(a.content for a in report.live_artifacts),
            ]
        )
        lower = text.lower()
        target_paths = [t.path for t in targets]
        chunk_paths = [c.file_path for c in (rag_chunks or [])[:3]]
        routes = extract_routes(text)
        stack_paths = extract_stack_paths(text)

        def suspect_files() -> list[str]:
            merged: list[str] = []
            for path in target_paths + chunk_paths + stack_paths:
                normalized = path.replace("\\", "/")
                if normalized not in merged:
                    merged.append(normalized)
            return merged[:5]

        candidates = [
            _Candidate(
                "null_pointer",
                "A missing value is used before it exists",
                "The code expects data from state, props, or an API response, but that value is empty and then gets read anyway. This usually shows up as undefined, null, or NoneType.",
                next_check="Paste the exact error line and, if you have it, the JSON/body returned right before the crash.",
            ),
            _Candidate(
                "signature_mismatch",
                "The caller and the handler disagree on the data shape",
                "A function, API, or form is sending fields (or arguments) that the other side does not accept, or is missing a required one.",
                next_check="Share the request body and the validation or 400/422 response if you have them.",
            ),
            _Candidate(
                "missing_import",
                "A module or export cannot be found",
                "The app fails while loading a file because an import path, package, or exported name does not exist.",
                next_check="Paste the full 'cannot find module' / ImportError line, including the missing name.",
            ),
            _Candidate(
                "navigation_mismatch",
                "Click, scroll, or route goes to the wrong place",
                "A click or redirect points at a route, panel, or key that no longer matches what is on screen.",
                next_check="Say what you clicked, where you expected to land, and any console error after the click.",
            ),
            _Candidate(
                "missing_data",
                "The UI or handler is missing the data it needs",
                "A payload, mapping, or generated object does not contain the fields this flow reads, so the screen stays empty or breaks after reload.",
                next_check="Paste the network response for the call that should have loaded this data.",
            ),
            _Candidate(
                "runtime_network",
                "A request fails, times out, or hits the wrong handler",
                "The screen depends on an API call that errors, hangs, or is wired to the wrong backend function.",
                next_check="Paste the failed URL, status code, and a short response body if you have them.",
            ),
        ]
        by_category = {c.category: c for c in candidates}

        if targets:
            for candidate in candidates:
                candidate.add(8, f"Suspect files isolated: {', '.join(target_paths[:3])}")
        else:
            for candidate in candidates:
                candidate.penalize(8, "No source file was isolated; diagnosis remains evidence-limited")

        if stack_paths:
            for candidate in candidates:
                candidate.add(12, f"Stack/file path evidence present: {', '.join(stack_paths[:3])}")

        if routes:
            by_category["runtime_network"].add(28, f"Failing route/API evidence present: {', '.join(routes[:3])}")
            by_category["signature_mismatch"].add(12, "API boundary is involved")
            by_category["navigation_mismatch"].add(8, "Route-like evidence may indicate navigation/routing")

        if report.live_artifacts:
            by_category["runtime_network"].add(12, "Live runtime artifact supplied")
            by_category["missing_data"].add(8, "Runtime artifact can reveal missing payload data")

        for lead in correlation_summary(build_correlation_leads(text)):
            by_category["runtime_network"].add(10, lead)
            if "route" in lead.lower() or "handler" in lead.lower():
                by_category["signature_mismatch"].add(6, "Runtime route evidence may indicate contract mismatch")

        if re.search(r"\b(attributeerror|nonetype|undefined|null|cannot read (?:property|properties)|reading ['\"]?\w+)\b", lower):
            by_category["null_pointer"].add(34, "Null/undefined dereference signature found")
        elif re.search(r"\btypeerror\b", lower) and not re.search(r"missing required|positional argument|unexpected keyword|takes \d+", lower):
            by_category["null_pointer"].add(18, "TypeError present without signature-mismatch wording")

        if re.search(r"missing required positional argument|unexpected keyword|takes \d+ .* given|invalid argument|validationerror|422|400 bad request|bad request", lower):
            by_category["signature_mismatch"].add(34, "Argument/schema/validation mismatch signature found")
        elif re.search(r"\b400\b|\b500\b", lower):
            by_category["signature_mismatch"].add(8, "HTTP status is present but too broad without response details")
            by_category["signature_mismatch"].penalize(6, "Bare HTTP status is weak evidence by itself")

        if re.search(r"importerror|modulenotfounderror|cannot find module|cannot import name|module not found", lower):
            by_category["missing_import"].add(40, "Module/import resolution error signature found")

        if re.search(r"redirect|navigation|navigate|scroll|click|highlight|routing|route|wrong line|panel", lower):
            by_category["navigation_mismatch"].add(28, "Issue describes click, route, scroll, highlight, or panel navigation")

        if re.search(r"mapping|mappings|payload|generated|coverage|transcript|mom|empty|missing data|response", lower):
            by_category["missing_data"].add(24, "Issue references payload, generated data, or source-output mapping")

        if re.search(r"\bmappings?\b", lower) and re.search(r"empty|missing|stale|reload|incomplete", lower):
            by_category["missing_data"].add(18, "Explicit missing/stale mapping or reload data gap")
            by_category["navigation_mismatch"].penalize(10, "Data/mapping omission better explains the failure than navigation alone")

        if re.search(r"timeout|hang|pending|network|fetch|axios|failed request|cors|401|403|404|409|429|502|503|504", lower):
            by_category["runtime_network"].add(30, "Network/runtime failure signal found")

        if not report.error_log.strip() and not report.live_artifacts:
            for candidate in candidates:
                candidate.penalize(6, "No log, failed request, or runtime artifact was supplied")

        hypotheses: list[Hypothesis] = []
        hyp_num = 1
        for candidate in sorted(candidates, key=lambda c: c.score, reverse=True):
            if candidate.score < 12:
                continue
            score = max(0, min(100, candidate.score + 35))
            confidence = "HIGH" if score >= 78 and not candidate.contradictions else "MEDIUM" if score >= 55 else "LOW"
            hypotheses.append(
                Hypothesis(
                    hypothesis_id=f"HYP-{hyp_num:02d}",
                    category=candidate.category,
                    title=candidate.title,
                    description=candidate.description,
                    likelihood_score=score,
                    confidence_level=confidence,
                    evidence_signals=candidate.support[:6],
                    contradicting_signals=candidate.contradictions[:4],
                    suspect_files=suspect_files(),
                    next_best_check=candidate.next_check,
                )
            )
            hyp_num += 1

        if not hypotheses:
            hypotheses.append(
                Hypothesis(
                    hypothesis_id="HYP-00",
                    category="unverified_logic_failure",
                    title="Not enough detail to name a cause yet",
                    description=(
                        "The report does not say which screen, action, or error to search for, "
                        "so a specific root cause would be a guess."
                    ),
                    likelihood_score=35 if not targets else 50,
                    confidence_level="LOW",
                    evidence_signals=[
                        f"User reported: {report.issue_description[:120]}",
                        f"Candidate files: {', '.join(target_paths[:3]) if target_paths else 'none'}",
                    ],
                    contradicting_signals=["No strong exception type, route, payload, or stack trace was found"],
                    suspect_files=suspect_files(),
                    next_best_check="Name the screen or feature, what you did, and paste any error text you saw.",
                )
            )

        return hypotheses[:3]

