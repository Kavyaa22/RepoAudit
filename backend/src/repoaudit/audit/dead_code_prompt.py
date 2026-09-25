"""Template-based IDE agent prompts for dead code remediation (no LLM)."""

from __future__ import annotations

from repoaudit.audit.dead_code_models import DeadCodeCategory, DeadCodeFinding, DeadCodeAuditResult

ConfidenceFilter = str | None  # "HIGH" | "MEDIUM" | None


def filter_findings(
    audit: DeadCodeAuditResult,
    *,
    confidence: ConfidenceFilter = None,
    category: DeadCodeCategory | None = None,
    finding_index: int | None = None,
    finding_indices: list[int] | None = None,
) -> list[DeadCodeFinding]:
    """Return findings matching optional filters."""
    findings = list(audit.findings)

    if finding_index is not None:
        if 0 <= finding_index < len(findings):
            return [findings[finding_index]]
        return []

    if finding_indices is not None:
        selected: list[DeadCodeFinding] = []
        for idx in finding_indices:
            if 0 <= idx < len(findings):
                selected.append(findings[idx])
        return selected

    if confidence:
        findings = [f for f in findings if f.confidence_level == confidence]

    if category:
        findings = [f for f in findings if f.category == category]

    return findings


def build_prompt_for_finding(
    finding: DeadCodeFinding,
    *,
    repo_name: str = "Repository",
    branch: str = "main",
) -> str:
    """Build a single-finding IDE agent prompt."""
    signals = "\n".join(f"  - {s}" for s in finding.signals_found) or "  - Static analysis flagged this symbol as unreferenced"
    category_label = finding.category.replace("_", " ").title()

    action_map = {
        "unused_import": "Remove the unused import if confirmed safe.",
        "dead_function": "Remove or refactor the dead function if confirmed safe.",
        "dead_class": "Remove or refactor the dead class if confirmed safe.",
        "orphan_file": "Review whether this file can be deleted or reconnected.",
        "unused_dependency": "Remove the package from dependencies if confirmed unused.",
        "empty_folder": "Remove the empty directory or add a .gitkeep file if intended to be preserved.",
    }
    suggested_action = action_map.get(finding.category, finding.suggestion or "Review and remove if confirmed dead.")

    return f"""You are an IDE coding agent helping clean up dead code in a repository.

## Context
- Repository: {repo_name}
- Branch: {branch}
- Finding source: RepoAudit static dead-code analysis (not LLM-generated)

## Suspected dead code item
- File: `{finding.path}`
- Symbol / dependency: `{finding.symbol_name}`
- Category: {category_label}
- Confidence: {finding.confidence_level} ({finding.confidence_score}%)
- Description: {finding.description}
- RepoAudit suggestion: {finding.suggestion or suggested_action}

## Signals that triggered this finding
{signals}

## Your task
1. **Re-verify** this is truly dead code before making any change:
   - Search the entire codebase for references to `{finding.symbol_name}` (imports, calls, string lookups, config files, tests).
   - Check dynamic usage: reflection, `getattr`, decorators, route registration, plugin entry points, framework hooks.
   - Check if it is used only in tests, docs, or build scripts.
2. **Report your verification** briefly: list evidence for "dead" vs "still used".
3. **Only if confirmed dead**: apply the minimal safe fix ({suggested_action}).
4. **Do not** remove code if there is any reasonable doubt — mark as "needs human review" instead.
5. After changes, ensure the project still builds/lints and note any tests to run.

Work carefully — false positives are worse than leaving unused code in place."""


def build_batch_prompt(
    findings: list[DeadCodeFinding],
    *,
    repo_name: str = "Repository",
    branch: str = "main",
) -> str:
    """Build a batch IDE agent prompt for multiple findings."""
    if not findings:
        return "No dead code findings match the selected filters."

    if len(findings) == 1:
        return build_prompt_for_finding(findings[0], repo_name=repo_name, branch=branch)

    items = []
    for i, f in enumerate(findings, start=1):
        cat = f.category.replace("_", " ").title()
        items.append(
            f"""### {i}. `{f.symbol_name}` in `{f.path}`
- Category: {cat}
- Confidence: {f.confidence_level} ({f.confidence_score}%)
- Description: {f.description}
- Suggestion: {f.suggestion or "Review and remove if confirmed dead."}"""
        )

    findings_block = "\n\n".join(items)

    return f"""You are an IDE coding agent helping clean up dead code in a repository.

## Context
- Repository: {repo_name}
- Branch: {branch}
- Finding source: RepoAudit static dead-code analysis ({len(findings)} items)
- Process **one item at a time** — verify before each change.

## Findings to review

{findings_block}

## Your task (for each item above)
1. **Re-verify** each symbol is truly dead before changing anything (search references, dynamic usage, tests, routes, config).
2. **Report verification** per item: dead / still used / needs human review.
3. **Only remove** items you can confirm are dead with evidence.
4. Prefer **small, isolated commits** or clearly separated changes per item.
5. After all changes, run lint/build and summarize what was removed vs skipped.

Do not bulk-delete without verification. False positives are worse than leaving unused code."""
