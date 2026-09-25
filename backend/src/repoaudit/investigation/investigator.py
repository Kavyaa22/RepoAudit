"""Investigation Investigator: multi-phase locate ? diagnose ? verify coordinator."""

from __future__ import annotations

import logging
import subprocess
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from repoaudit.indexing.models import ProjectContext
from repoaudit.investigation.correlation import build_correlation_leads, correlation_summary
from repoaudit.investigation.diagnosis import diagnose_issue
from repoaudit.investigation.evidence import assess_evidence, sanitized_report
from repoaudit.investigation.hypotheses import HypothesisEngine
from repoaudit.investigation.investigation_models import (
    CodePatch,
    InvestigationMetrics,
    InvestigationPhase,
    InvestigationResult,
    IssueReport,
)
from repoaudit.investigation.isolator import FeaturePathIsolator
from repoaudit.investigation.keywords import build_retrieval_query
from repoaudit.investigation.patch_generator import PatchGenerator
from repoaudit.retrieval.hybrid import HybridRAG

if TYPE_CHECKING:
    from repoaudit.indexing.llm.client import LLMClient

logger = logging.getLogger(__name__)

PhaseCallback = Callable[[dict[str, Any]], Awaitable[None] | None]


class InvestigationEngine:
    """Orchestrates evidence scoring, hybrid locate, diagnosis, patching, and verification."""

    def __init__(self) -> None:
        self.isolator = FeaturePathIsolator()
        self.hypothesis_engine = HypothesisEngine()
        self.patch_generator = PatchGenerator()

    async def run_investigation(
        self,
        report: IssueReport,
        project: ProjectContext | None = None,
        llm: LLMClient | None = None,
        on_phase: PhaseCallback | None = None,
    ) -> InvestigationResult:
        """Executes targeted issue investigation workflow."""
        started = time.perf_counter()
        inv_id = report.investigation_id.strip() or f"INV-{uuid.uuid4().hex[:8].upper()}"
        report = sanitized_report(report)
        report.investigation_id = inv_id
        turn = max(1, int(report.turn or 1))
        phases: list[InvestigationPhase] = []
        phase_durations: dict[str, int] = {}

        async def mark_phase(name: str, status: str, detail: str, phase_started: float) -> None:
            duration = int((time.perf_counter() - phase_started) * 1000)
            phase_durations[name] = duration
            phase = InvestigationPhase(name=name, status=status, detail=detail, duration_ms=duration)  # type: ignore[arg-type]
            phases.append(phase)
            if on_phase is not None:
                maybe = on_phase(
                    {
                        "type": "phase",
                        "investigation_id": inv_id,
                        "name": name,
                        "status": status,
                        "detail": detail,
                        "duration_ms": duration,
                        "turn": turn,
                    }
                )
                if maybe is not None:
                    await maybe

        if project is None:
            from repoaudit.ingestion.local import ingest_local

            base_dir = Path(__file__).resolve().parents[3]
            target_dir = Path(report.repo_path) if report.repo_path else base_dir / "workspace" / report.project_name
            if not target_dir.is_dir():
                target_dir = base_dir
            project = ingest_local(target_dir)

        orient_started = time.perf_counter()
        snapshot_label = self._snapshot_label(project, report.branch)
        evidence = assess_evidence(report)
        artifact_text = "\n".join(a.content for a in report.live_artifacts)
        leads = build_correlation_leads(report.error_log, artifact_text, report.issue_description)
        lead_details = correlation_summary(leads)
        orient_detail = f"Looking at {snapshot_label}."
        if lead_details:
            orient_detail += " " + lead_details[0]
        elif evidence.route == "clarify":
            orient_detail += " The report is still too vague to search with confidence."
        else:
            orient_detail += " Searching the repository from the issue description."
        await mark_phase(
            "orient",
            "completed" if evidence.route != "clarify" else "partial",
            orient_detail,
            orient_started,
        )

        logger.info("Starting issue investigation '%s' turn %s for project '%s'", inv_id, turn, report.project_name)

        locate_started = time.perf_counter()
        rag = HybridRAG()
        rag.index(project)
        query = build_retrieval_query(
            "\n".join([report.issue_description, report.expected_behavior, report.actual_behavior]),
            report.error_log + "\n" + artifact_text,
            report.feature_name,
            report.action_name,
        )
        rag_chunks = rag.retrieve(query, top_k=15)
        targets = self.isolator.isolate_targets(report, project, rag_chunks=rag_chunks)
        locate_status = "completed" if self._locate_confident(targets, evidence.score) else "partial"
        await mark_phase("locate", locate_status, self._locate_detail(targets), locate_started)

        if evidence.route == "clarify" and not self._locate_confident(targets, evidence.score):
            ask_started = time.perf_counter()
            primary = self.hypothesis_engine.generate_hypotheses(report, project, targets, rag_chunks)[0]
            remediation_steps = self._clarification_steps(evidence, primary.next_best_check)
            clarification = self._clarification_questions(evidence, primary.next_best_check)
            await mark_phase(
                "ask_or_act",
                "blocked",
                "Need a clearer description before naming a cause or suggesting a code change.",
                ask_started,
            )
            status = "PARTIAL"
            total_ms = int((time.perf_counter() - started) * 1000)
            metrics = self._metrics(
                evidence=evidence,
                targets=targets,
                primary=primary,
                patches=[],
                llm_used=False,
                llm_available=llm is not None,
                turn=turn,
                total_ms=total_ms,
                phase_durations=phase_durations,
                leads=lead_details,
            )
            return InvestigationResult(
                investigation_id=inv_id,
                project_name=report.project_name,
                status=status,
                summary_verdict=self._build_summary(targets, primary, status, False, llm is not None, evidence),
                evidence=evidence,
                phases=phases,
                snapshot_label=snapshot_label,
                isolated_targets=targets,
                primary_root_cause=primary,
                all_hypotheses=[primary],
                remediation_steps=remediation_steps,
                code_patches=[],
                metrics=metrics,
                clarification_questions=clarification,
                repro_checklist=[],
                turn=turn,
            )

        inspect_started = time.perf_counter()
        inspected = self._inspect_suspects(project, targets[:3])
        await mark_phase(
            "inspect",
            "completed" if inspected else "partial",
            inspected or "Opened the likely files but could not extract a focused function to quote.",
            inspect_started,
        )

        diagnose_started = time.perf_counter()
        hypotheses = self.hypothesis_engine.generate_hypotheses(report, project, targets, rag_chunks)
        for lead in lead_details:
            if hypotheses:
                if lead not in hypotheses[0].evidence_signals:
                    hypotheses[0].evidence_signals.append(lead)
        primary = hypotheses[0] if hypotheses else None
        llm_diagnosis = None
        if llm and getattr(llm, "api_key", None):
            llm_diagnosis = await diagnose_issue(report, project, targets, rag_chunks, llm, primary)
            if llm_diagnosis and primary:
                primary.title = llm_diagnosis.cause_title or primary.title
                primary.description = llm_diagnosis.cause_detail or primary.description
        await mark_phase(
            "diagnose",
            "completed" if primary and primary.confidence_level != "LOW" else "partial",
            primary.title if primary else "Could not form a clear cause from the report and files.",
            diagnose_started,
        )

        remediation_steps: list[str] = []
        code_patches: list[CodePatch] = []
        llm_generated = False
        act_started = time.perf_counter()
        if llm_diagnosis:
            remediation_steps = list(llm_diagnosis.steps)
            if llm_diagnosis.diffs:
                for idx, (path, diff_text) in enumerate(llm_diagnosis.diffs, start=1):
                    patch = CodePatch(
                        patch_id=f"PATCH-{idx:02d}",
                        file_path=path,
                        unified_diff=diff_text.strip(),
                        explanation=llm_diagnosis.patch_explanation
                        or llm_diagnosis.cause_detail
                        or f"Suggested change in {path}",
                        confidence_score=82,
                        status="draft",
                    )
                    code_patches.append(self.patch_generator.verifier.verify(project.root, patch))
                llm_generated = True
            elif primary:
                extra_steps, extra_patches, extra_llm = await self.patch_generator.generate_patches_and_remediation(
                    report,
                    project,
                    primary,
                    targets,
                    llm=None,
                    context_chunks=rag_chunks,
                )
                if extra_patches:
                    code_patches = extra_patches
                    llm_generated = extra_llm
                if not remediation_steps:
                    remediation_steps = extra_steps
        elif primary:
            remediation_steps, code_patches, llm_generated = await self.patch_generator.generate_patches_and_remediation(
                report,
                project,
                primary,
                targets,
                llm=llm,
                context_chunks=rag_chunks,
            )
        await mark_phase(
            "ask_or_act",
            "completed" if code_patches or (primary and primary.confidence_level != "LOW") else "partial",
            "Suggested a concrete fix." if code_patches else "Wrote next steps from the files that matched.",
            act_started,
        )

        verify_started = time.perf_counter()
        await mark_phase("verify", self._verify_phase_status(code_patches), self._verify_detail(code_patches), verify_started)

        status = self._compute_status(targets, primary, code_patches, evidence.score)
        report_started = time.perf_counter()
        await mark_phase("report", "completed", "Report is ready.", report_started)

        total_ms = int((time.perf_counter() - started) * 1000)
        metrics = self._metrics(
            evidence=evidence,
            targets=targets,
            primary=primary,
            patches=code_patches,
            llm_used=llm_generated or bool(llm_diagnosis),
            llm_available=llm is not None,
            turn=turn,
            total_ms=total_ms,
            phase_durations=phase_durations,
            leads=lead_details,
        )
        repro = self._repro_checklist(report, primary)
        summary = (
            llm_diagnosis.summary
            if llm_diagnosis and llm_diagnosis.summary
            else self._build_summary(targets, primary, status, llm_generated, llm is not None, evidence)
        )

        return InvestigationResult(
            investigation_id=inv_id,
            project_name=report.project_name,
            status=status,
            summary_verdict=summary,
            evidence=evidence,
            phases=phases,
            snapshot_label=snapshot_label,
            isolated_targets=targets,
            primary_root_cause=primary,
            all_hypotheses=hypotheses,
            remediation_steps=remediation_steps,
            code_patches=code_patches,
            metrics=metrics,
            clarification_questions=self._clarification_questions(evidence, primary.next_best_check if primary else ""),
            repro_checklist=repro,
            turn=turn,
        )

    @staticmethod
    def _locate_confident(targets, evidence_score: int) -> bool:
        if not targets:
            return False
        top = targets[0].relevance_score
        return top >= 55 or (top >= 45 and evidence_score >= 55)

    @staticmethod
    def _compute_status(targets, primary, code_patches, evidence_score: int) -> str:
        if not primary:
            return "FAILED"
        if not targets:
            return "PARTIAL"
        if primary.confidence_level == "LOW" or evidence_score < 35:
            return "PARTIAL"
        if code_patches:
            return "SUCCESS" if any(p.status == "checks_passed" for p in code_patches) else "PARTIAL"
        return "SUCCESS" if primary.confidence_level == "HIGH" and targets[0].relevance_score >= 70 else "PARTIAL"

    @staticmethod
    def _build_summary(
        targets,
        primary,
        status: str,
        llm_generated: bool,
        llm_available: bool,
        evidence,
    ) -> str:
        file_hint = f" Start with `{targets[0].path}`." if targets else ""
        if primary:
            title = (primary.title or "").rstrip(".")
            detail = (primary.description or "").strip()
            if detail and detail.lower() not in title.lower():
                body = f"{title}. {detail.rstrip('.')}."
            else:
                body = f"{title}." if title else "I could not pin down a single cause yet."
        else:
            body = "I could not pin down a single cause from this report."

        if status == "PARTIAL" and evidence.route == "clarify":
            return (
                f"{body} This description is still too thin to be sure, so I have not suggested a code change."
                f"{file_hint} Add what you clicked, what you expected, and any error text."
            )
        if status == "PARTIAL" and not targets:
            return (
                f"{body} I could not match this to a source file. "
                "Name the screen or paste a stack trace so the search has something to lock onto."
            )
        if status == "PARTIAL" and llm_generated:
            return f"{body}{file_hint} A suggested change is included — review it before applying."
        if status == "PARTIAL" and not llm_generated:
            extra = (
                " I stopped short of a code diff because the match is not certain enough."
                if llm_available
                else " I listed what to check next instead of guessing a code diff."
            )
            return f"{body}{file_hint}{extra}"
        if llm_generated:
            return f"{body}{file_hint} A suggested code change is included below."
        return f"{body}{file_hint}"

    @staticmethod
    def _locate_detail(targets) -> str:
        if not targets:
            return "No files stood out from this description."
        top = targets[0]
        return f"Most likely file: {top.path}."

    @staticmethod
    def _verify_phase_status(code_patches) -> str:
        if not code_patches:
            return "partial"
        if any(p.status == "checks_passed" for p in code_patches):
            return "completed"
        return "partial"

    @staticmethod
    def _verify_detail(code_patches) -> str:
        if not code_patches:
            return "No code change to check — the next steps below are the result."
        ready = [p for p in code_patches if p.status == "checks_passed"]
        if ready:
            return f"{len(ready)} suggested change(s) passed basic checks."
        return "A suggested change is included. Read it before applying — it has not been fully verified."

    @staticmethod
    def _clarification_steps(evidence, next_best_check: str) -> list[str]:
        steps = [evidence.guidance] if evidence.guidance else []
        steps.extend(gap.rstrip(".") + "." for gap in evidence.gaps[:3] if gap not in steps)
        if next_best_check and next_best_check not in steps:
            steps.append(next_best_check)
        steps.append("Add that detail on this same report and run it again.")
        return [step for step in steps if step]

    @staticmethod
    def _clarification_questions(evidence, next_best_check: str) -> list[str]:
        questions = [gap for gap in evidence.gaps[:3] if gap]
        if next_best_check and next_best_check not in questions:
            questions.append(next_best_check)
        if not questions:
            questions.append("What did you click, and what error or wrong screen did you see?")
        return questions

    @staticmethod
    def _repro_checklist(report: IssueReport, primary) -> list[str]:
        feature = report.feature_name.strip() or "the feature you reported"
        action = report.action_name.strip() or "the same action"
        checklist = [
            f"On branch `{report.branch or 'main'}`, open {feature}.",
            f"Do {action} once and confirm you still see the same wrong result.",
        ]
        if primary and primary.next_best_check:
            checklist.append(primary.next_best_check)
        checklist.append("After any fix, repeat the same action and check the console or network tab.")
        return checklist

    @staticmethod
    def _inspect_suspects(project: ProjectContext, targets) -> str:
        if not targets:
            return ""
        notes: list[str] = []
        for target in targets:
            file_info = next((f for f in project.files if f.path.replace("\\", "/") == target.path), None)
            content = ""
            if file_info:
                content = file_info.content or file_info.preview or ""
            if not content:
                abs_path = Path(project.root) / target.path
                if abs_path.is_file():
                    try:
                        content = abs_path.read_text(encoding="utf-8", errors="ignore")
                    except OSError:
                        content = ""
            if not content:
                continue
            symbols = []
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith(("def ", "async def ", "function ", "export function ", "export async function ", "class ", "@router.", "@app.")):
                    symbols.append(stripped[:120])
                if len(symbols) >= 3:
                    break
            if symbols:
                notes.append(f"{target.path}: " + "; ".join(symbols))
            else:
                notes.append(f"{target.path}: inspected {min(len(content), 800)} chars of focused context")
        return f"Inspected {len(notes)} suspect file(s). " + " | ".join(notes[:3])

    @staticmethod
    def _metrics(*, evidence, targets, primary, patches, llm_used: bool, llm_available: bool, turn: int, total_ms: int, phase_durations, leads) -> InvestigationMetrics:
        return InvestigationMetrics(
            evidence_tier=evidence.tier,
            evidence_score=evidence.score,
            locate_top_score=targets[0].relevance_score if targets else 0,
            locate_target_count=len(targets),
            hypothesis_category=primary.category if primary else "",
            hypothesis_confidence=primary.confidence_level if primary else "",
            patch_statuses=[p.status for p in patches],
            llm_used=llm_used,
            llm_fallback=bool(llm_available and not llm_used),
            turn=turn,
            total_duration_ms=total_ms,
            phase_durations_ms=phase_durations,
            correlation_leads=leads,
        )

    @staticmethod
    def _snapshot_label(project: ProjectContext, branch: str) -> str:
        root = Path(project.root)
        commit = "unknown commit"
        try:
            result = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0 and result.stdout.strip():
                commit = result.stdout.strip()
        except Exception:
            commit = "unknown commit"
        return f"{project.name} @ branch {branch or 'unknown'} ({commit})"
