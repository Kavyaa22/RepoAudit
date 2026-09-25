"""Automated Solution & Patch Generator with confidence gates and verification metadata."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from repoaudit.investigation.investigation_models import CodePatch, Hypothesis, IsolatedTarget, IssueReport
from repoaudit.investigation.verification import PatchVerifier
from repoaudit.retrieval.lexical import format_context

if TYPE_CHECKING:
    from repoaudit.indexing.llm.client import LLMClient
    from repoaudit.indexing.models import ProjectContext
    from repoaudit.retrieval.lexical import Chunk

logger = logging.getLogger(__name__)


class PatchGenerator:
    """Generates unified patch diffs and step-by-step remediation plans."""

    def __init__(self) -> None:
        self.verifier = PatchVerifier()

    async def generate_patches_and_remediation(
        self,
        report: IssueReport,
        project: ProjectContext,
        primary_hypothesis: Hypothesis,
        targets: list[IsolatedTarget],
        llm: LLMClient | None = None,
        context_chunks: list[Chunk] | None = None,
    ) -> tuple[list[str], list[CodePatch], bool]:
        """Returns (remediation_steps, code_patches, llm_generated)."""
        if not targets:
            return self._no_targets_remediation(report, primary_hypothesis), [], False

        if not self._patch_allowed(primary_hypothesis, targets):
            return self._confidence_gate_remediation(primary_hypothesis, targets)

        target_file = targets[0].path
        context_text = format_context(context_chunks or [])
        file_snippets = self._load_target_snippets(project, targets[:3])

        if llm and llm.api_key:
            llm_result = await self._generate_with_llm(
                report=report,
                project=project,
                primary_hypothesis=primary_hypothesis,
                target_file=target_file,
                targets=targets,
                file_snippets=file_snippets,
                context_text=context_text,
                llm=llm,
            )
            if llm_result is not None:
                return llm_result

        return self._deterministic_fallback(
            primary_hypothesis=primary_hypothesis,
            targets=targets,
            file_snippets=file_snippets,
        )

    @staticmethod
    def _patch_allowed(primary_hypothesis: Hypothesis, targets: list[IsolatedTarget]) -> bool:
        top_score = targets[0].relevance_score if targets else 0
        if primary_hypothesis.confidence_level == "LOW":
            return False
        if primary_hypothesis.likelihood_score < 65 or top_score < 55:
            return False
        return True

    async def _generate_with_llm(
        self,
        *,
        report: IssueReport,
        project: ProjectContext,
        primary_hypothesis: Hypothesis,
        target_file: str,
        targets: list[IsolatedTarget],
        file_snippets: str,
        context_text: str,
        llm: LLMClient,
    ) -> tuple[list[str], list[CodePatch], bool] | None:
        try:
            suspect_list = ", ".join(t.path for t in targets[:5])
            llm_prompt = (
                "You are a staff engineer suggesting the smallest safe fix for a reported bug.\n"
                "Write for a teammate. Name real files and functions from the snippets. Do not invent code.\n"
                "If you are not confident, return REMEDIATION steps only and omit PATCH.\n\n"
                f"Issue:\n{report.issue_description}\n\n"
                f"Expected: {report.expected_behavior or '(not given)'}\n"
                f"Actual: {report.actual_behavior or '(not given)'}\n"
                f"Error log:\n{report.error_log or '(none)'}\n\n"
                f"Likely cause: {primary_hypothesis.title}\n"
                f"{primary_hypothesis.description}\n\n"
                f"Likely files: {suspect_list}\n\n"
                f"Code:\n{context_text}\n\n"
                f"Snippets:\n{file_snippets}\n\n"
                "Respond with:\n"
                "1. REMEDIATION: numbered, file-specific steps a developer can follow.\n"
                "2. PATCH: a valid unified diff starting with "
                f"`--- a/{target_file}` and `+++ b/{target_file}`.\n"
                "Do not wrap the diff in markdown fences. Do not mention evidence tiers or pipelines."
            )
            response = await llm.complete(
                messages=[{"role": "user", "content": llm_prompt}],
                temperature=0.2,
            )
            if not response or response.startswith("[LLM Error"):
                return None

            remediation = self._parse_remediation_steps(response)
            diff_blocks = self._extract_diff_blocks(response)
            if not diff_blocks:
                return None

            patches: list[CodePatch] = []
            for idx, (path, diff_text) in enumerate(diff_blocks, start=1):
                patch = CodePatch(
                    patch_id=f"PATCH-{idx:02d}",
                    file_path=path,
                    unified_diff=diff_text.strip(),
                    explanation=f"Suggested change in {path} for: {primary_hypothesis.title}",
                    confidence_score=88,
                    status="draft",
                )
                patches.append(self.verifier.verify(project.root, patch))

            if not remediation:
                remediation = [
                    f"Open `{target_file}` and compare it with the failure you reported.",
                    "Make the smallest change that matches the cause above.",
                    "Re-run the same user action and confirm the error is gone.",
                ]
            remediation.append(self._verification_remediation(patches))

            return remediation, patches, True
        except Exception as exc:
            logger.warning("LLM patch generation failed: %s", exc)
            return None

    def _deterministic_fallback(
        self,
        *,
        primary_hypothesis: Hypothesis,
        targets: list[IsolatedTarget],
        file_snippets: str,
    ) -> tuple[list[str], list[CodePatch], bool]:
        target_file = targets[0].path
        category = primary_hypothesis.category

        if category == "null_pointer":
            remediation = [
                f"Open `{target_file}` and find the line that reads a value from the API, state, or props.",
                "Guard that read: if the value is missing, show a fallback instead of crashing.",
                "Check the code that is supposed to set that value and confirm it actually runs.",
                "Reproduce once with empty data so the crash cannot come back.",
            ]
        elif category == "signature_mismatch":
            remediation = [
                f"In `{target_file}`, list the arguments or fields the function expects.",
                "Compare that list with what the caller actually sends.",
                "Add the missing field, or make it optional with a default, then update every caller.",
            ]
        elif category == "runtime_network":
            remediation = [
                f"Open `{target_file}` and confirm it is the handler for the failing request.",
                "Compare method, URL, body, and auth with what the frontend sends.",
                "Reproduce with the same payload and read the backend error for that request.",
            ]
        elif category == "navigation_mismatch":
            remediation = [
                f"Open `{target_file}` and follow what happens after the click.",
                "Check that the route, panel id, or scroll key still matches what is rendered.",
                "Fix the key or wait until the target is on screen before scrolling.",
            ]
        elif category == "missing_data":
            remediation = [
                f"Start at `{target_file}` and find where the payload or mapping is read.",
                "Check the response that should fill those fields.",
                "Align the write-side keys with the read-side keys.",
            ]
        else:
            remediation = [
                f"Read `{target_file}` against the failure you described.",
                "Add a log on the failing path, reproduce once, then make a small targeted change.",
            ]

        if file_snippets.strip():
            remediation.append("No automatic code diff was generated — follow the steps above in the file.")

        return remediation, [], False

    def _confidence_gate_remediation(
        self,
        primary_hypothesis: Hypothesis,
        targets: list[IsolatedTarget],
    ) -> tuple[list[str], list[CodePatch], bool]:
        target_text = ", ".join(t.path for t in targets[:3]) or "none"
        return [
            "I did not generate a code change because the match is not certain enough yet.",
            f"Most likely: {primary_hypothesis.title}.",
            f"Files to open first: {target_text}.",
            primary_hypothesis.next_best_check or "Paste a stack trace or the failed request if you have one.",
        ], [], False

    def _no_targets_remediation(
        self,
        report: IssueReport,
        primary_hypothesis: Hypothesis,
    ) -> list[str]:
        return [
            "I could not match this issue to a source file in the current repository snapshot.",
            "Name the screen or paste a stack trace / failed URL so the search can lock onto a file.",
            f"You reported: {report.issue_description[:160]}",
            f"Best guess for now: {primary_hypothesis.title}.",
            "No code patch generated because applying a generic template patch would be misleading.",
        ]

    def _load_target_snippets(self, project: ProjectContext, targets: list[IsolatedTarget]) -> str:
        blocks: list[str] = []
        for target in targets:
            abs_path = Path(project.root) / target.path
            content = ""
            if abs_path.is_file():
                try:
                    content = abs_path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    content = ""
            if not content:
                file_info = next((f for f in project.files if f.path.replace("\\", "/") == target.path), None)
                content = getattr(file_info, "content", "") or getattr(file_info, "preview", "") if file_info else ""
            if content:
                blocks.append(f"### {target.path}\n```\n{content[:2500]}\n```")
        return "\n\n".join(blocks)

    @staticmethod
    def _parse_remediation_steps(response: str) -> list[str]:
        steps: list[str] = []
        in_remediation = False
        for line in response.splitlines():
            stripped = line.strip()
            lower = stripped.lower()
            if lower.startswith("remediation:") or lower.startswith("1. remediation"):
                in_remediation = True
                continue
            if lower.startswith("patch:") or stripped.startswith("--- a/"):
                break
            if in_remediation and stripped:
                cleaned = re.sub(r"^\d+[\).\]]\s*", "", stripped)
                steps.append(cleaned)
        return steps

    @staticmethod
    def _extract_diff_blocks(response: str) -> list[tuple[str, str]]:
        blocks: list[tuple[str, str]] = []
        lines = response.replace("\r\n", "\n").split("\n")
        idx = 0
        while idx < len(lines):
            if not lines[idx].startswith("--- a/"):
                idx += 1
                continue
            start = idx
            path = lines[idx][6:].strip()
            idx += 1
            if idx >= len(lines) or not lines[idx].startswith("+++ b/"):
                continue
            idx += 1
            while idx < len(lines) and not lines[idx].startswith("--- a/"):
                idx += 1
            diff = "\n".join(lines[start:idx]).strip()
            if "@@" in diff:
                blocks.append((path, diff))
        return blocks

    @staticmethod
    def _verification_remediation(patches: list[CodePatch]) -> str:
        if any(p.status == "checks_passed" for p in patches):
            return "At least one suggested change passed basic syntax checks."
        if any(p.status == "applied_clean" for p in patches):
            return "The suggested change applies cleanly. Run the tests for this file before merging."
        return "Read the suggested change before applying. It has not been fully verified."
