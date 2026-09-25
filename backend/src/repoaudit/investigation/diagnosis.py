"""LLM diagnosis: plain-language root cause, steps, and an optional patch."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from repoaudit.indexing.llm.prompts import extract_json
from repoaudit.investigation.investigation_models import IsolatedTarget, IssueReport
from repoaudit.retrieval.lexical import format_context

if TYPE_CHECKING:
    from repoaudit.indexing.llm.client import LLMClient
    from repoaudit.indexing.models import ProjectContext
    from repoaudit.investigation.investigation_models import Hypothesis
    from repoaudit.retrieval.lexical import Chunk

logger = logging.getLogger(__name__)

DIAGNOSIS_SYSTEM = """You are an expert AI software architect writing an issue diagnosis for a "vibe coder" or builder who uses AI coding agents (like Cursor, Claude, Windsurf, ChatGPT, Antigravity) to build and fix their apps.

Rules:
1. Write in plain, clear, conversational English. Avoid cryptic compiler jargon, abstract type theory, or overly technical system buzzwords.
2. Clearly explain:
   - What is going wrong from the user's perspective (what breaks on the screen or in the workflow).
   - Why it happens (the root cause in simple, intuitive terms).
   - Which file and component needs to be updated.
3. Steps must be simple, direct, and actionable so either a person or an AI coding assistant can follow them easily.
4. Never use internal jargon words like "evidence tier", "hypothesis pipeline", "RAG", "confidence gate", or "isolated targets".
5. If you are confident in a code fix, provide a clean, accurate unified diff starting with --- a/path and +++ b/path.

Return ONLY valid JSON with this shape:
{
  "summary": "2-3 plain-language sentences: what is broken, why it happened, and how to fix it in simple terms.",
  "cause_title": "A short, plain-English headline (max 10 words, no jargon). Example: Profile page crashes because user data is accessed before loading completes",
  "cause_detail": "A simple, friendly 1-2 paragraph explanation of why this bug happens in the code, written so any vibe coder can understand.",
  "steps": [
    "Step 1: Open <filename>",
    "Step 2: Update <function/logic> to <action>",
    "Step 3: Test <behavior>"
  ],
  "patch_explanation": "A friendly 1-2 sentence explanation of what the suggested code change does.",
  "unified_diff": "A valid unified diff starting with --- a/path and +++ b/path, or empty string if no patch."
}"""


@dataclass
class DiagnosisDraft:
    summary: str
    cause_title: str
    cause_detail: str
    steps: list[str] = field(default_factory=list)
    patch_explanation: str = ""
    diffs: list[tuple[str, str]] = field(default_factory=list)


def _load_snippets(project: ProjectContext, targets: list[IsolatedTarget], limit: int = 3) -> str:
    blocks: list[str] = []
    for target in targets[:limit]:
        content = ""
        abs_path = Path(project.root) / target.path
        if abs_path.is_file():
            try:
                content = abs_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                content = ""
        if not content:
            file_info = next((f for f in project.files if f.path.replace("\\", "/") == target.path), None)
            content = (getattr(file_info, "content", "") or getattr(file_info, "preview", "")) if file_info else ""
        if content:
            blocks.append(f"### {target.path}\n```\n{content[:3500]}\n```")
    return "\n\n".join(blocks)


def _extract_diff_blocks(response: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    lines = response.replace("\r\n", "\n").replace("```diff", "").replace("```", "").split("\n")
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


async def diagnose_issue(
    report: IssueReport,
    project: ProjectContext,
    targets: list[IsolatedTarget],
    rag_chunks: list[Chunk] | None,
    llm: LLMClient,
    primary: Hypothesis | None,
) -> DiagnosisDraft | None:
    """Ask the LLM for a human-readable diagnosis grounded in retrieved files."""
    if not getattr(llm, "api_key", None):
        return None

    suspect_list = ", ".join(t.path for t in targets[:6]) or "(none isolated)"
    snippets = _load_snippets(project, targets)
    context_text = format_context(rag_chunks or [])
    artifacts = "\n".join(f"- {a.kind}: {a.content[:800]}" for a in report.live_artifacts) or "(none)"
    heuristic = ""
    if primary:
        heuristic = (
            f"A first-pass guess (may be wrong — prefer the code): {primary.title}. {primary.description}"
        )

    user_content = (
        f"Repository: {report.project_name}\n"
        f"Branch: {report.branch or 'unknown'}\n\n"
        f"What the user reported:\n{report.issue_description}\n\n"
        f"Expected: {report.expected_behavior or '(not given)'}\n"
        f"Actual: {report.actual_behavior or '(not given)'}\n"
        f"Error log:\n{report.error_log or '(none)'}\n\n"
        f"Extra notes:\n{artifacts}\n\n"
        f"{heuristic}\n\n"
        f"Likely files, highest relevance first: {suspect_list}\n\n"
        f"Retrieved code:\n{context_text[:6000]}\n\n"
        f"File contents:\n{snippets or '(could not load file text)'}\n"
    )

    try:
        response = await llm.complete(
            messages=[
                {"role": "system", "content": DIAGNOSIS_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            temperature=0.15,
            max_tokens=2500,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM diagnosis failed: %s", exc)
        return None

    if not response or response.startswith("[LLM Error"):
        return None

    parsed = extract_json(response)
    if not isinstance(parsed, dict):
        logger.warning("LLM diagnosis was not JSON; ignoring.")
        return None

    summary = str(parsed.get("summary") or "").strip()
    cause_title = str(parsed.get("cause_title") or "").strip()
    cause_detail = str(parsed.get("cause_detail") or "").strip()
    raw_steps = parsed.get("steps") or []
    steps = [str(step).strip() for step in raw_steps if str(step).strip()][:8]
    patch_explanation = str(parsed.get("patch_explanation") or "").strip()
    unified_diff = str(parsed.get("unified_diff") or "").strip()
    diffs = _extract_diff_blocks(unified_diff) if unified_diff else []

    if not summary and not cause_detail:
        return None

    if not summary:
        summary = cause_detail
    if not cause_title:
        cause_title = "Likely cause in the files below"
    if not cause_detail:
        cause_detail = summary
    if not steps:
        if targets:
            steps = [
                f"Open `{targets[0].path}` and compare it with the behavior you reported.",
                "Add a log around the failing path, reproduce once, then apply a small targeted fix.",
            ]

    # Strip leftover jargon if the model slipped.
    for junk in ("evidence tier", "confidence gate", "pipeline routing"):
        summary = re.sub(junk, "", summary, flags=re.I)

    return DiagnosisDraft(
        summary=summary,
        cause_title=cause_title[:120],
        cause_detail=cause_detail,
        steps=steps,
        patch_explanation=patch_explanation,
        diffs=diffs,
    )
