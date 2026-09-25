"""Audit orchestration engine combining static rules and LLM-assisted analysis."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from repoaudit.audit.dead_code_engine import DeadCodeEngine
from repoaudit.audit.dead_code_models import DeadCodeAuditResult
from repoaudit.audit.findings import SecurityAuditResult
from repoaudit.audit.scoring import compute_structure_score
from repoaudit.audit.security import SecurityEngine
from repoaudit.audit.structure_context import build_profile_aware_structure
from repoaudit.audit.structure_llm import LLMStructureAuditor
from repoaudit.audit.structure_models import FileMove, FolderStructureAuditResult, FolderViolation
from repoaudit.audit.structure_static import StaticStructureAuditor, detect_layout_profile
from repoaudit.audit.plain_language import structure_summary
from repoaudit.audit.structure_style import DEFAULT_STRUCTURE_STYLE, STRUCTURE_STYLE_ACTION_API
from repoaudit.audit.structure_target import (
    build_current_structure,
    build_structure_changes,
    collect_dead_paths,
)
from repoaudit.audit.structure_multipass import build_multipass_deterministic
from repoaudit.audit.structure_scoring import score_structure_style

if TYPE_CHECKING:
    from repoaudit.indexing.llm.client import LLMClient
    from repoaudit.indexing.models import ProjectContext

logger = logging.getLogger(__name__)


class AuditEngine:
    """main orchestrator for repository audit tasks."""

    def __init__(self) -> None:
        self.static_auditor = StaticStructureAuditor()
        self.llm_auditor = LLMStructureAuditor()
        self.dead_code_engine = DeadCodeEngine()
        self.security_engine = SecurityEngine()

    def run_dead_code_audit(self, project: ProjectContext) -> DeadCodeAuditResult:
        """Executes multi-signal dead code and unused dependency analysis."""
        logger.info("Executing dead code & unused dependency audit...")
        return self.dead_code_engine.run_audit(project)

    async def run_security_audit(
        self,
        project: ProjectContext,
        llm: LLMClient | None = None,
    ) -> SecurityAuditResult:
        """Run deterministic security scanners, then optional LLM explanation."""
        try:
            result = self.security_engine.run_audit(project)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Security audit failed; continuing without findings: %s", exc)
            from repoaudit.audit.findings import ScannerStatus, summarize_security

            result = summarize_security(
                [],
                [ScannerStatus(name="security", available=False, skip_reason=str(exc)[:180])],
            )
        if llm is not None:
            try:
                result = await self.security_engine.explain_findings(result, llm)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Security LLM explanation failed: %s", exc)
        return result

    async def run_structure_audit(
        self,
        project: ProjectContext,
        llm: LLMClient | None = None,
        dead_code_result: DeadCodeAuditResult | None = None,
        security_result: SecurityAuditResult | None = None,
        structure_style: str = DEFAULT_STRUCTURE_STYLE,
    ) -> FolderStructureAuditResult:
        """executes hybrid static + LLM folder structure audit."""
        logger.info("Executing static folder structure audit...")
        static_violations = self.static_auditor.audit(project)
        exclude_paths = collect_dead_paths(project, dead_code_result)
        profile = detect_layout_profile(project)

        unstructured_areas: list[FolderViolation] = []
        summary_reason = ""
        problems_found = ""
        explanation = ""
        features_identified: list[str] = []
        no_file_content_modified = True
        multipass_topology: dict | None = None
        if structure_style == STRUCTURE_STYLE_ACTION_API:
            multipass_topology, recommended_structure = build_multipass_deterministic(
                project, exclude_paths
            )
        else:
            recommended_structure = build_profile_aware_structure(
                project, profile, exclude_paths, structure_style=structure_style
            )
        current_structure = build_current_structure(project, exclude_paths)
        change_tuples = build_structure_changes(
            project, profile, exclude_paths, structure_style=structure_style
        )
        structure_changes = [
            FileMove(from_path=src, to_path=dest, reason=reason)
            for src, dest, reason in change_tuples
        ]

        if llm:
            logger.info("Executing LLM Project Architecture Analyzer (structure only)...")
            llm_result = await self.llm_auditor.audit(
                project,
                llm,
                static_violations=static_violations,
                dead_code_result=dead_code_result,
                exclude_paths=exclude_paths,
                structure_style=structure_style,
            )
            unstructured_areas = llm_result.unstructured_areas
            summary_reason = llm_result.summary_reason
            recommended_structure = llm_result.recommended_structure
            problems_found = llm_result.problems_found
            explanation = llm_result.explanation
            features_identified = llm_result.features_identified
            no_file_content_modified = llm_result.no_file_content_modified
            # Prefer LLM-authored move map when present; else keep deterministic baseline.
            if llm_result.folder_changes:
                structure_changes = [
                    FileMove(from_path=src, to_path=dest, reason=reason)
                    for src, dest, reason in llm_result.folder_changes
                ]
        else:
            omitted = (
                f" Unused files were left out of the recommended layout ({len(exclude_paths)})."
                if exclude_paths
                else ""
            )
            summary_reason = (
                "The folder layout was checked against common project-organization practices."
                + omitted
            )
            problems_found = summary_reason
            explanation = (
                "No LLM was configured; a deterministic feature → action baseline was used. "
                "No file contents were modified."
            )

        all_violations = static_violations + unstructured_areas
        score, is_valid = compute_structure_score(all_violations)

        if not summary_reason:
            summary_reason = structure_summary(
                is_valid=is_valid,
                issue_count=len(all_violations),
                omitted_dead=len(exclude_paths),
            )

        style_score, style_gaps = score_structure_style(
            recommended_structure, structure_style
        )
        # Only force deterministic rebuild when there was no LLM report at all.
        if (
            structure_style == STRUCTURE_STYLE_ACTION_API
            and style_score < 40
            and "Proposed Structure" not in (recommended_structure or "")
            and "multipass" not in (recommended_structure or "")
        ):
            multipass_topology, recommended_structure = build_multipass_deterministic(
                project, exclude_paths
            )
            style_score, style_gaps = score_structure_style(
                recommended_structure, structure_style
            )

        # Surface catalog features + quality gate notes when LLM did not provide them
        if structure_style == STRUCTURE_STYLE_ACTION_API and multipass_topology:
            if not features_identified:
                features_identified = list(multipass_topology.get("catalog") or [])
            q = multipass_topology.get("quality") or {}
            for issue in (q.get("issues") or [])[:5]:
                if issue not in style_gaps:
                    style_gaps.append(issue)

        return FolderStructureAuditResult(
            is_valid=is_valid,
            overall_score=score,
            static_violations=static_violations,
            unstructured_areas=unstructured_areas,
            structure_style=structure_style,
            current_structure=current_structure,
            structure_changes=structure_changes,
            recommended_structure=recommended_structure,
            style_score=style_score,
            style_gaps=style_gaps,
            summary_reason=summary_reason,
            problems_found=problems_found,
            explanation=explanation,
            features_identified=features_identified,
            no_file_content_modified=no_file_content_modified,
            dead_code_result=dead_code_result,
            security_result=security_result,
        )

    async def run_full_audit(
        self,
        project: ProjectContext,
        llm: LLMClient | None = None,
        structure_style: str = DEFAULT_STRUCTURE_STYLE,
    ) -> FolderStructureAuditResult:
        """Executes full repository audit: dead code, security, then folder structure."""
        dead_code_result = self.run_dead_code_audit(project)
        security_result = await self.run_security_audit(project, llm=llm)
        return await self.run_structure_audit(
            project,
            llm=llm,
            dead_code_result=dead_code_result,
            security_result=security_result,
            structure_style=structure_style,
        )
