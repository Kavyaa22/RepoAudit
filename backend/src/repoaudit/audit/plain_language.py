"""Plain-language labels so audit results read well for non-engineers."""

from __future__ import annotations

from typing import Any

SEVERITY_LABELS = {
    "critical": "Needs action now",
    "high": "High priority",
    "medium": "Should review",
    "low": "Minor",
}

SECURITY_CATEGORY_LABELS = {
    "secret": "Exposed secret or password",
    "vulnerable_dependency": "Outdated library with a known risk",
    "dangerous_pattern": "Risky coding practice",
}

DEAD_CODE_CATEGORY_LABELS = {
    "unused_import": "Unused import",
    "dead_function": "Unused function",
    "dead_class": "Unused class",
    "orphan_file": "File nothing uses",
    "unused_dependency": "Unused package",
    "empty_folder": "Empty folder",
}

CONFIDENCE_LABELS = {
    "HIGH": "Very likely unused",
    "MEDIUM": "Likely unused",
    "LOW": "Worth a look",
}


def severity_label(value: str | None) -> str:
    raw = (value or "medium").strip().lower()
    return SEVERITY_LABELS.get(raw, "Should review")


def security_category_label(value: str | None) -> str:
    return SECURITY_CATEGORY_LABELS.get((value or "").strip().lower(), "Security issue")


def dead_code_category_label(value: str | None) -> str:
    return DEAD_CODE_CATEGORY_LABELS.get((value or "").strip().lower(), "Unused code")


def confidence_label(value: str | None) -> str:
    return CONFIDENCE_LABELS.get((value or "").strip().upper(), "Worth a look")


def attr(item: Any, name: str, default: Any = "") -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def security_verdict(
    total: int,
    critical: int,
    high: int,
    skipped: list[str] | None = None,
) -> str:
    if total:
        parts = [f"We found {total} security issue{'s' if total != 1 else ''} that need a decision"]
        detail = []
        if critical:
            detail.append(f"{critical} urgent")
        if high:
            detail.append(f"{high} high-priority")
        if detail:
            parts.append(f"({', '.join(detail)})")
        verdict = " ".join(parts) + "."
    else:
        verdict = "No security issues were found in this review."
    if skipped:
        verdict += " A few automatic checks could not run, so this is a partial picture."
    return verdict


def dead_code_verdict(total: int, high_count: int) -> str:
    if not total:
        return "This codebase looks tidy — no unused code or leftover packages stood out."
    extra = f" {high_count} of these look safe to remove after a quick check." if high_count else ""
    return (
        f"We found {total} leftover item{'s' if total != 1 else ''} that do not appear to be used."
        f"{extra} Cleaning them up will make the project easier and cheaper to maintain."
    )


def structure_summary(
    *,
    is_valid: bool,
    issue_count: int,
    omitted_dead: int = 0,
) -> str:
    if is_valid and not issue_count:
        reason = "The project folders are easy to follow and look well organized."
    elif is_valid:
        reason = (
            f"The project folders are mostly in good shape, with {issue_count} "
            "item(s) worth a closer look."
        )
    else:
        reason = (
            f"The folder layout has {issue_count} issue(s) that will make the project "
            "harder for the team to maintain."
        )
    if omitted_dead:
        reason += f" Unused files were left out of the recommended layout ({omitted_dead})."
    return reason
