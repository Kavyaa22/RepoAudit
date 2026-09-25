"""LLM-assisted auditor for identifying unstructured codebase areas and target folder refactoring."""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from repoaudit.audit.dead_code_models import DeadCodeAuditResult
from repoaudit.audit.plain_language import structure_summary
from repoaudit.audit.scoring import compute_structure_score
from repoaudit.audit.structure_context import (
    build_profile_aware_structure,
    format_stack_block,
    validate_folder_changes_payload,
    validate_recommended_structure,
)
from repoaudit.audit.structure_models import FolderViolation
from repoaudit.audit.structure_static import detect_layout_profile
from repoaudit.audit.structure_style import (
    DEFAULT_STRUCTURE_STYLE,
    STRUCTURE_STYLE_ACTION_API,
    style_prompt_block,
)
from repoaudit.audit.structure_target import (
    build_current_structure,
    collect_dead_paths,
    count_file_leaves,
)
from repoaudit.audit.structure_multipass import build_multipass_deterministic
from repoaudit.indexing.llm.prompts import extract_json

if TYPE_CHECKING:
    from repoaudit.indexing.llm.client import LLMClient
    from repoaudit.indexing.models import ProjectContext

logger = logging.getLogger(__name__)

STRUCTURE_AUDIT_SYSTEM_PROMPT = """You are a Project Architecture Analyzer.

Your ONLY responsibility is to analyze and recommend a FOLDER STRUCTURE reorganization.

HARD LIMITS (never violate):
- You do NOT modify, rename-in-place, delete, or edit any file CONTENTS.
- You may ONLY recommend creating folders and MOVING existing files into them.
- Never change imports, code, configuration values, or functionality.
- Never invent files that are not in the inventory.
- Never invent placeholder names like FEATURE, {feature}, or <action>.

CRITICAL SUCCESS RULE — READ THIS:
- Copying today's folder tree is a FAILURE. If your proposed tree still looks like the current
  inventory (same type buckets, same top-level docs/scripts/templates-src), you failed the task.
- You MUST regroup into Feature → Action → Files on BOTH backend and frontend.
- You MUST return a non-empty folder_changes list with real from_path → to_path moves.
- Existing frontend/src/features/ is a STARTING POINT, not "already done" — backend must match
  the same Feature → Action hierarchy, and type folders (components/, services/, lib/, hooks/)
  must be broken up into business features.

Hierarchy:
  Main Area (frontend/ | backend/)
    → Feature (unique business capability)
      → Sub-feature / Action
        → Existing files

Do NOT assume feature names beforehand. Infer them from paths and filenames.

FOLDER RULES:
1. If a suitable feature/action folder already exists, REUSE it (no duplicate names).
2. Feature folder names must be unique — do not create both auth/ and authentication/ for the same thing.
   Canonical name is auth/ (never authentication/).
3. Do NOT organize primarily by technical type:
   FORBIDDEN as primary layout: components/, services/, controllers/, utils/, hooks/, lib/, blocks/
4. Organize by BUSINESS FEATURE / FUNCTIONALITY using a CLOSED catalog of ~8–12 nouns
   (proposals, auth, templates, dashboard, settings, integrations, …).
5. Fold consolidatable top-level roots into product roots:
   docs/ → backend/docs/ ; scripts/ → backend/scripts/ or frontend/… ; templates-src/ → frontend/src/templates/catalog/
6. frontend/ and backend/ each MUST keep their own product-root config:
   .env.example, .gitignore, package.json / pyproject.toml, Dockerfile, etc.
   Never bury these under a feature folder.
7. Shared cross-feature code may live under shared/lib/, shared/ui/, shared/api/ only when truly shared.
8. Actions must be verbs (create, login, export, preview, provision, track) — NEVER camelCase leftovers
   (ThankYouPage → proposals/public, NOT thank/you; relativeTime → shared/lib, NOT relative/time).
9. Omit DEAD files listed in the user message.
10. Both backend AND frontend source trees must use FEATURE/ACTION nesting under src/, with matching feature names.
11. Do not encode file types in folder names (*_css, *_json); keep assets beside the feature action.

OUTPUT FORMAT — respond ONLY with valid JSON:
{
  "problems_found": "string — what was wrong with the previous structure",
  "features_identified": ["string — business features you found"],
  "unstructured_areas": [
    {
      "path": "string",
      "severity": "critical" | "high" | "medium" | "low",
      "description": "string — plain language",
      "suggestion": "string — concrete destination path"
    }
  ],
  "summary_reason": "string — short plain-language overall verdict",
  "recommended_structure": "string — Markdown directory tree of the PROPOSED layout (concrete file leaves from inventory)",
  "explanation": "string — why each major folder exists, which folders are reused vs created",
  "folder_changes": [
    {"from_path": "string", "to_path": "string", "reason": "string"}
  ],
  "migration_phases": ["string"],
  "no_file_content_modified": true
}

folder_changes is MANDATORY whenever the inventory still uses type buckets or top-level docs/scripts/templates-src.
Write plain language a non-engineer can read. Explain business impact (risk, cost, slower delivery, harder onboarding).
"""


def _sample_paths(project: ProjectContext, limit: int = 250) -> list[str]:
    """Prefer a representative sample: all top-level dirs + breadth across modules."""
    all_paths = [f.path.replace("\\", "/") for f in project.files]
    if len(all_paths) <= limit:
        return all_paths

    by_top: dict[str, list[str]] = defaultdict(list)
    for p in all_paths:
        top = p.split("/", 1)[0]
        by_top[top].append(p)

    sampled: list[str] = []
    iterators = {k: iter(v) for k, v in by_top.items()}
    while len(sampled) < limit and iterators:
        done = []
        for key, it in iterators.items():
            if len(sampled) >= limit:
                break
            try:
                sampled.append(next(it))
            except StopIteration:
                done.append(key)
        for key in done:
            iterators.pop(key, None)
    return sampled


def _format_static_findings(static_violations: list[FolderViolation] | None) -> str:
    if not static_violations:
        return "None — static rules reported no issues."
    lines = []
    for v in static_violations[:40]:
        lines.append(f"- [{v.severity}] {v.path}: {v.description}")
    if len(static_violations) > 40:
        lines.append(f"... and {len(static_violations) - 40} more static findings")
    return "\n".join(lines)


def _sanitize_template_tokens(text: str) -> str:
    return (
        text
        .replace("{feature_name}", "auth")
        .replace("{action_name}", "login")
        .replace("<feature_name>", "auth")
        .replace("<action_name>", "login")
        .replace("{feature}", "auth")
        .replace("{action}", "login")
    )


def _append_migration_phases(recommended: str, phases: list[str]) -> str:
    text = (recommended or "").strip()
    if not phases:
        return text
    if "migration phase" in text.lower():
        return text
    lines = [text, "", "**Migration phases:**"]
    for i, phase in enumerate(phases, 1):
        lines.append(f"{i}. {phase}")
    return "\n".join(lines)


def _compose_architecture_report(
    *,
    current_structure: str,
    problems_found: str,
    features_identified: list[str],
    proposed_tree: str,
    explanation: str,
    folder_changes: list[tuple[str, str, str]],
    phases: list[str],
    no_content_modified: bool = True,
) -> str:
    """Assemble the 6-section architecture analysis the product expects."""
    lines: list[str] = [
        "### 1. Previous Structure",
        "",
        (current_structure or "_Current structure unavailable._").strip(),
        "",
        "### 2. Problems Found",
        "",
        (problems_found or "No major structural problems were called out.").strip(),
        "",
        "### 3. Proposed Structure",
        "",
        (proposed_tree or "_No proposed tree._").strip(),
        "",
        "### 4. Explanation / Reasoning",
        "",
    ]
    if features_identified:
        lines.append("**Features identified:** " + ", ".join(features_identified))
        lines.append("")
    lines.append((explanation or "Feature folders were grouped from the live inventory.").strip())
    lines.extend(["", "### 5. Folder Changes Made", ""])
    if folder_changes:
        for src, dest, reason in folder_changes[:100]:
            suffix = f" — {reason}" if reason else ""
            lines.append(f"- `{src}` → `{dest}`{suffix}")
        if len(folder_changes) > 100:
            lines.append(f"- …and {len(folder_changes) - 100} more moves")
    else:
        lines.append("No file moves were required for the proposed target.")
    lines.extend(
        [
            "",
            "### 6. Confirmation",
            "",
            (
                "NO FILE CONTENT was modified. This audit only recommends folder moves "
                "and new empty folders."
                if no_content_modified
                else "Warning: content-modification flag was not confirmed by the model."
            ),
        ]
    )
    if phases and "migration phase" not in (proposed_tree or "").lower():
        lines.extend(["", "**Migration phases:**"])
        for i, phase in enumerate(phases, 1):
            lines.append(f"{i}. {phase}")
    return "\n".join(lines)


def _parse_folder_changes(raw: object) -> list[tuple[str, str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[tuple[str, str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        src = str(item.get("from_path") or item.get("from") or "").replace("\\", "/").strip("/")
        dest = str(item.get("to_path") or item.get("to") or "").replace("\\", "/").strip("/")
        reason = str(item.get("reason") or "").strip()
        if src and dest and src != dest:
            out.append((src, dest, reason or "Group into feature → action folder"))
    return out


@dataclass
class StructureLLMResult:
    unstructured_areas: list[FolderViolation] = field(default_factory=list)
    summary_reason: str = ""
    recommended_structure: str = ""
    folder_changes: list[tuple[str, str, str]] = field(default_factory=list)
    problems_found: str = ""
    explanation: str = ""
    features_identified: list[str] = field(default_factory=list)
    no_file_content_modified: bool = True


def _inventory_set(project: ProjectContext) -> set[str]:
    return {f.path.replace("\\", "/").strip("/") for f in project.files}


def _finalize_recommended_structure(
    raw: str,
    project: ProjectContext,
    profile: str,
    phases: list[str] | None = None,
    exclude_paths: set[str] | None = None,
    structure_style: str = DEFAULT_STRUCTURE_STYLE,
) -> str:
    """Validate LLM tree; fall back to whole-repo file-leaf structure if invalid."""
    exclude = exclude_paths or set()
    fallback = build_profile_aware_structure(
        project, profile, exclude, structure_style=structure_style
    )
    text = _sanitize_template_tokens((raw or "").strip())
    text = _append_migration_phases(text, phases or [])
    if not text or count_file_leaves(text) < 3:
        return fallback

    issues = validate_recommended_structure(
        text,
        inventory_paths=_inventory_set(project),
        exclude_paths=exclude,
        structure_style=structure_style,
    )
    if issues:
        logger.warning(
            "Recommended structure failed validation (%d issue(s)): %s",
            len(issues),
            "; ".join(issues[:3]),
        )
        return fallback
    return text


def _build_user_prompt(
    project: ProjectContext,
    static_violations: list[FolderViolation],
    profile: str,
    validation_feedback: list[str] | None = None,
    exclude_paths: set[str] | None = None,
    *,
    compact: bool = False,
    structure_style: str = DEFAULT_STRUCTURE_STYLE,
) -> str:
    exclude = exclude_paths or set()
    path_limit = 120 if compact else 400
    live_paths = [
        p for p in _sample_paths(project, limit=path_limit)
        if p.replace("\\", "/").strip("/") not in exclude
    ]
    tree_text = "\n".join(live_paths)
    static_block = _format_static_findings(static_violations)
    stack_block = format_stack_block(project, profile)

    parts = [
        f"Project Name: {project.name}",
        f"Total Files: {len(project.files)}",
        "",
        "TARGET STYLE:",
        style_prompt_block(structure_style),
        "",
        "STACK & SIZE ANALYSIS:",
        stack_block,
        "",
        "STATIC RULE FINDINGS:",
        static_block,
        "",
        "Directory Paths (live inventory — recommend a WHOLE-REPO tree with file leaves):",
        tree_text,
    ]
    if exclude:
        parts.extend([
            "",
            "DEAD FILES — omit these files and drop folders that would become empty:",
            *[f"- {p}" for p in sorted(exclude)],
        ])

    if compact:
        parts.extend([
            "",
            "Keep JSON SMALL and COMPLETE. Prefer a short recommended_structure "
            "(top-level folders plus a few key files) over a huge tree that gets cut off. "
            "Always finish summary_reason and unstructured_areas.",
        ])

    if validation_feedback:
        parts.extend([
            "",
            "PREVIOUS OUTPUT FAILED VALIDATION — fix these issues:",
            *[f"- {issue}" for issue in validation_feedback[:8]],
            "",
            "Regenerate a whole-repository recommended_structure that fixes ALL issues above.",
        ])

    return "\n".join(parts)


def _strip_json_fences(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned.startswith("```"):
        return cleaned
    lines = cleaned.splitlines()
    if lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _decode_json_string(raw: str) -> str:
    try:
        return json.loads(f'"{raw}"')
    except json.JSONDecodeError:
        return raw.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")


def _extract_json_string_field(text: str, key: str) -> str | None:
    """Read a JSON string field even when the closing quote was truncated."""
    match = re.search(rf'"{re.escape(key)}"\s*:\s*"', text)
    if not match:
        return None
    raw = text[match.end():]
    chars: list[str] = []
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == "\\" and i + 1 < len(raw):
            chars.append(raw[i : i + 2])
            i += 2
            continue
        if ch == '"':
            break
        chars.append(ch)
        i += 1
    return _decode_json_string("".join(chars)).strip() or None


def _extract_unstructured_areas(text: str) -> list[dict]:
    match = re.search(r'"unstructured_areas"\s*:\s*\[', text)
    if not match:
        return []
    snippet = text[match.end() - 1 :]
    end = snippet.find("]")
    blob = snippet if end < 0 else snippet[: end + 1]
    try:
        parsed = json.loads(blob if blob.endswith("]") else blob + "]")
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
    except json.JSONDecodeError:
        pass
    areas: list[dict] = []
    for obj_match in re.finditer(r"\{[^{}]*\}", blob):
        try:
            item = json.loads(obj_match.group(0))
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            areas.append(item)
    return areas


def salvage_structure_partial(text: str) -> dict:
    """Pull usable structure-audit fields from truncated or messy LLM JSON."""
    if not text:
        return {}
    cleaned = _strip_json_fences(text)
    out: dict = {}
    summary = _extract_json_string_field(cleaned, "summary_reason")
    if summary:
        out["summary_reason"] = summary
    tree = _extract_json_string_field(cleaned, "recommended_structure")
    if tree:
        out["recommended_structure"] = tree
    areas = _extract_unstructured_areas(cleaned)
    if areas:
        out["unstructured_areas"] = areas
    return out


def _close_truncated_json(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    s = text[start:]
    if s.endswith("\\"):
        s = s[:-1]
    in_string = False
    escape = False
    stack: list[str] = []
    for ch in s:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]" and stack and stack[-1] == ch:
            stack.pop()
    if in_string:
        s += '"'
    s = s.rstrip()
    if s.endswith(","):
        s = s[:-1]
    while stack:
        s += stack.pop()
    return s


def _parse_llm_response(cleaned_text: str) -> dict:
    """Parse structure-audit JSON; salvage fields if the model was cut off."""
    text = _strip_json_fences(cleaned_text)
    parsed = extract_json(text)
    if isinstance(parsed, dict) and parsed:
        return parsed
    closed = _close_truncated_json(text)
    if closed:
        parsed = extract_json(closed)
        if isinstance(parsed, dict) and parsed:
            return parsed
    salvaged = salvage_structure_partial(text)
    if salvaged:
        return salvaged
    raise json.JSONDecodeError("No structure JSON could be parsed", text, 0)


class LLMStructureAuditor:
    """LLM-led Project Architecture Analyzer (folder structure only)."""

    async def audit(
        self,
        project: ProjectContext,
        llm: LLMClient,
        static_violations: list[FolderViolation] | None = None,
        dead_code_result: DeadCodeAuditResult | None = None,
        exclude_paths: set[str] | None = None,
        structure_style: str = DEFAULT_STRUCTURE_STYLE,
    ) -> StructureLLMResult:
        """Run one primary LLM analysis (with one retry). Deterministic tree is fallback only."""
        static_violations = static_violations or []
        profile = detect_layout_profile(project)
        exclude = exclude_paths if exclude_paths is not None else collect_dead_paths(
            project, dead_code_result
        )
        inventory = _inventory_set(project)
        current = build_current_structure(project, exclude)
        validation_feedback: list[str] | None = None
        data: dict = {}
        llm_error: Exception | None = None

        if structure_style == STRUCTURE_STYLE_ACTION_API:
            _, fallback_rec = build_multipass_deterministic(project, exclude)
        else:
            fallback_rec = build_profile_aware_structure(
                project, profile, exclude, structure_style=structure_style
            )

        for attempt in range(2):
            prompt = _build_user_prompt(
                project,
                static_violations,
                profile,
                validation_feedback,
                exclude_paths=exclude,
                compact=attempt > 0,
                structure_style=structure_style,
            )
            # Nudge the model toward the 6-section analysis contract.
            prompt = (
                prompt
                + "\n\nAnalyze FIRST (problems, features), then propose a REORGANIZED target tree. "
                "Copying the current layout is a failure. "
                "folder_changes must include real moves out of components/services/lib/hooks "
                "and must fold docs/, scripts/, templates-src/ under backend/ or frontend/. "
                "Both backend and frontend need Feature → Action nesting. "
                "Confirm no_file_content_modified=true."
            )
            messages = [
                {"role": "system", "content": STRUCTURE_AUDIT_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]

            try:
                raw_response = await llm.complete(
                    messages,
                    operation="audit",
                    temperature=0.2,
                    max_tokens=6144 if attempt == 0 else 4096,
                    response_format={"type": "json_object"},
                )
                data = _parse_llm_response(raw_response.strip())
                recommended_structure = data.get("recommended_structure", "")
                issues = validate_recommended_structure(
                    _sanitize_template_tokens(recommended_structure),
                    inventory_paths=inventory,
                    exclude_paths=exclude,
                    structure_style=structure_style,
                )
                issues.extend(
                    validate_folder_changes_payload(
                        data.get("folder_changes"),
                        inventory_paths=inventory,
                        structure_style=structure_style,
                    )
                )
                if (issues or count_file_leaves(recommended_structure) < 3) and attempt == 0:
                    validation_feedback = issues or [
                        "Recommended tree must list concrete file leaves for the whole repository."
                    ]
                    logger.info("Retrying structure audit after validation failure")
                    continue
                if issues or count_file_leaves(recommended_structure) < 3:
                    # Second attempt still invalid — discard and use deterministic fallback.
                    logger.warning(
                        "LLM structure still invalid after retry (%s); using deterministic fallback",
                        "; ".join(issues[:3]) if issues else "too few file leaves",
                    )
                    data = {}
                    llm_error = None
                    break
                llm_error = None
                break
            except Exception as e:
                llm_error = e
                if attempt == 0:
                    logger.warning("LLM structure audit attempt failed, retrying: %s", e)
                    validation_feedback = [
                        "Previous reply was cut off or was not valid JSON. "
                        "Return a smaller complete JSON object."
                    ]
                    continue

        if llm_error is not None and not data:
            logger.error("LLM Structure Audit failed: %s", llm_error)
            return _fallback_result(static_violations, exclude, fallback_rec, current)

        if not data:
            return _fallback_result(
                static_violations,
                exclude,
                fallback_rec,
                current,
                problems_found=(
                    "The model returned a layout that still looked like today's folders "
                    "(type buckets or unfolded docs/scripts). A deterministic Feature → Action "
                    "baseline was applied instead."
                ),
            )

        try:
            return _build_result_from_llm_data(
                data=data,
                project=project,
                profile=profile,
                static_violations=static_violations,
                exclude=exclude,
                structure_style=structure_style,
                current=current,
                fallback_rec=fallback_rec,
            )
        except Exception as e:
            logger.error("LLM Structure Audit failed: %s", e)
            return _fallback_result(static_violations, exclude, fallback_rec, current)


def _features_list(raw: object) -> list[str]:
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()][:40]
    if isinstance(raw, str) and raw.strip():
        return [p.strip() for p in raw.split(",") if p.strip()][:40]
    return []


def _build_result_from_llm_data(
    *,
    data: dict,
    project: ProjectContext,
    profile: str,
    static_violations: list[FolderViolation],
    exclude: set[str],
    structure_style: str,
    current: str,
    fallback_rec: str,
) -> StructureLLMResult:
    unstructured_violations: list[FolderViolation] = []
    for item in data.get("unstructured_areas", []):
        if not isinstance(item, dict):
            continue
        unstructured_violations.append(
            FolderViolation(
                path=item.get("path", "root"),
                violation_type="unstructured_area",
                severity=item.get("severity", "medium"),
                description=item.get("description", "Unstructured codebase area detected."),
                suggestion=item.get("suggestion", ""),
            )
        )

    if static_violations and not unstructured_violations:
        for v in static_violations[:15]:
            if v.severity in {"critical", "high", "medium"}:
                unstructured_violations.append(
                    FolderViolation(
                        path=v.path,
                        violation_type="unstructured_area",
                        severity=v.severity,
                        description=f"Aligned with static finding: {v.description}",
                        suggestion=v.suggestion,
                    )
                )

    summary_reason = data.get(
        "summary_reason",
        "The folder layout was reviewed against a practical whole-project target.",
    )
    if static_violations and "clean" in summary_reason.lower() and "not" not in summary_reason.lower():
        summary_reason = (
            f"Static analysis reported {len(static_violations)} structure finding(s). "
            + summary_reason
        )
    if exclude:
        summary_reason = (
            f"{summary_reason} Unused files were left out of the recommended layout "
            f"({len(exclude)})."
        )

    phases = data.get("migration_phases") or []
    if isinstance(phases, str):
        phases = [phases]
    if not isinstance(phases, list):
        phases = []

    raw_tree = _sanitize_template_tokens(str(data.get("recommended_structure") or ""))
    tree_issues = validate_recommended_structure(
        raw_tree,
        inventory_paths=_inventory_set(project),
        exclude_paths=exclude,
        structure_style=structure_style,
    )
    change_issues = validate_folder_changes_payload(
        data.get("folder_changes"),
        inventory_paths=_inventory_set(project),
        structure_style=structure_style,
    )

    proposed = _finalize_recommended_structure(
        data.get("recommended_structure", ""),
        project,
        profile,
        phases,
        exclude_paths=exclude,
        structure_style=structure_style,
    )
    if not proposed.strip() or tree_issues:
        proposed = fallback_rec

    folder_changes = _parse_folder_changes(data.get("folder_changes"))
    if tree_issues or change_issues:
        # Do not trust LLM moves when the tree failed the reorg contract.
        folder_changes = []

    problems = str(data.get("problems_found") or "").strip()
    if tree_issues and not problems:
        problems = "; ".join(tree_issues[:3])
    explanation = str(data.get("explanation") or "").strip()
    if tree_issues and not explanation:
        explanation = (
            "The first model draft still mirrored today's folders, so a Feature → Action "
            "baseline was substituted. No file contents were changed."
        )
    features = _features_list(data.get("features_identified"))
    no_mod = data.get("no_file_content_modified", True)
    if isinstance(no_mod, str):
        no_mod = no_mod.strip().lower() in {"true", "1", "yes"}

    report = _compose_architecture_report(
        current_structure=current,
        problems_found=problems,
        features_identified=features,
        proposed_tree=proposed,
        explanation=explanation,
        folder_changes=folder_changes,
        phases=[str(p) for p in phases if p],
        no_content_modified=bool(no_mod),
    )

    return StructureLLMResult(
        unstructured_areas=unstructured_violations,
        summary_reason=summary_reason,
        recommended_structure=report,
        folder_changes=folder_changes,
        problems_found=problems,
        explanation=explanation,
        features_identified=features,
        no_file_content_modified=bool(no_mod),
    )


def _fallback_result(
    static_violations: list[FolderViolation],
    exclude: set[str],
    fallback_rec: str,
    current: str = "",
    problems_found: str = "",
) -> StructureLLMResult:
    """Keep static findings visible when the LLM write-up cannot be parsed."""
    fallback_areas: list[FolderViolation] = []
    for v in static_violations[:10]:
        fallback_areas.append(
            FolderViolation(
                path=v.path,
                violation_type="unstructured_area",
                severity=v.severity,
                description=v.description,
                suggestion=v.suggestion,
            )
        )
    _, is_valid = compute_structure_score(static_violations)
    reason = structure_summary(
        is_valid=is_valid,
        issue_count=len(static_violations),
        omitted_dead=len(exclude),
    )
    problems = problems_found or reason
    report = _compose_architecture_report(
        current_structure=current,
        problems_found=problems,
        features_identified=[],
        proposed_tree=fallback_rec,
        explanation=(
            "A deterministic Feature → Action baseline was applied because the model "
            "reply was missing, invalid, or still copied today's type-based folders. "
            "No file contents were changed."
        ),
        folder_changes=[],
        phases=[
            "Fold docs/, scripts/, and templates-src/ under backend/ or frontend/.",
            "Move backend services/lib files into backend/src/FEATURE/ACTION/.",
            "Move frontend components/hooks/lib into frontend/src/FEATURE/ACTION/.",
        ],
        no_content_modified=True,
    )
    return StructureLLMResult(
        unstructured_areas=fallback_areas,
        summary_reason=reason,
        recommended_structure=report,
        folder_changes=[],
        problems_found=problems,
        explanation="Deterministic Feature → Action fallback used.",
        no_file_content_modified=True,
    )

