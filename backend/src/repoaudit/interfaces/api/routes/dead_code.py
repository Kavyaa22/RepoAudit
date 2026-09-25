"""Dead code audit data and IDE prompt generation endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends

from app.core.security.deps import CurrentUser, get_current_user
from app.modules.github.shared.users import resolve_user_id
from repoaudit.interfaces.api.runtime import ensure_project_loaded, owned_by_user
from pydantic import BaseModel, Field

from repoaudit.audit.dead_code_models import DeadCodeAuditResult, DeadCodeCategory, DeadCodeFinding
from repoaudit.audit.dead_code_prompt import build_batch_prompt, filter_findings

router = APIRouter()


class DeadCodePromptRequest(BaseModel):
    finding_index: int | None = None
    finding_indices: list[int] | None = None
    confidence: Literal["HIGH", "MEDIUM"] | None = None
    category: DeadCodeCategory | None = None


class DeadCodePromptResponse(BaseModel):
    prompt: str
    count: int
    finding_indices: list[int] = Field(default_factory=list)


def _parse_audit(raw) -> DeadCodeAuditResult | None:
    if raw is None:
        return None
    if isinstance(raw, DeadCodeAuditResult):
        return raw
    if isinstance(raw, dict):
        try:
            return DeadCodeAuditResult(**raw)
        except Exception:
            return None
    return None


def _finding_to_dict(f: DeadCodeFinding, index: int) -> dict:
    return {
        "index": index,
        **f.model_dump(),
    }


@router.get("/project/{project_id}/dead-code-audit")
async def get_dead_code_audit(project_id: str, user: CurrentUser = Depends(get_current_user)):
    """Return structured dead code audit findings for a scanned project."""
    user_id = resolve_user_id(user)
    proj = await ensure_project_loaded(project_id, user_id=user_id)
    if not proj or not owned_by_user(proj, user_id):
        return {"error": "Project not found"}

    audit = _parse_audit(proj.get("dead_code_audit"))
    if not audit:
        return {
            "project_name": proj["info"].name,
            "branch": proj.get("branch") or getattr(proj["info"], "branch", "main"),
            "total_findings": 0,
            "health_score": 100,
            "summary_verdict": "No dead code audit available.",
            "findings": [],
            "counts_by_category": {},
        }

    branch = proj.get("branch") or getattr(proj["info"], "branch", "main")
    return {
        "project_name": proj["info"].name,
        "branch": branch,
        "total_findings": audit.total_findings,
        "health_score": audit.health_score,
        "summary_verdict": audit.summary_verdict,
        "findings": [_finding_to_dict(f, i) for i, f in enumerate(audit.findings)],
        "counts_by_category": audit.counts_by_category,
    }


@router.post("/project/{project_id}/dead-code/prompt", response_model=DeadCodePromptResponse)
async def generate_dead_code_prompt(
    project_id: str,
    req: DeadCodePromptRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Generate a copy-paste IDE agent prompt for dead code remediation (template-based, no LLM)."""
    user_id = resolve_user_id(user)
    proj = await ensure_project_loaded(project_id, user_id=user_id)
    if not proj or not owned_by_user(proj, user_id):
        return DeadCodePromptResponse(prompt="Project not found.", count=0)

    audit = _parse_audit(proj.get("dead_code_audit"))
    if not audit or not audit.findings:
        return DeadCodePromptResponse(
            prompt="No dead code findings available for this project. Run a full scan first.",
            count=0,
        )

    selected = filter_findings(
        audit,
        confidence=req.confidence,
        category=req.category,
        finding_index=req.finding_index,
        finding_indices=req.finding_indices,
    )

    if not selected:
        return DeadCodePromptResponse(
            prompt="No findings match the selected filters.",
            count=0,
        )

    finding_key = lambda f: (f.path, f.symbol_name, f.category)
    selected_keys = {finding_key(f) for f in selected}
    selected_indices = [
        i for i, f in enumerate(audit.findings) if finding_key(f) in selected_keys
    ]

    repo_name = proj["info"].name or "Repository"
    branch = proj.get("branch") or getattr(proj["info"], "branch", "main")
    prompt = build_batch_prompt(selected, repo_name=repo_name, branch=branch)

    return DeadCodePromptResponse(
        prompt=prompt,
        count=len(selected),
        finding_indices=selected_indices,
    )
