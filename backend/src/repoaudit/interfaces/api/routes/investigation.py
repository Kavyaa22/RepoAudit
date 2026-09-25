"""Issue investigation API routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header

from app.core.security.deps import CurrentUser, get_current_user
from app.core.workspace import path_belongs_to_user
from app.modules.github.shared.users import resolve_user_id
from repoaudit.interfaces.api.runtime import ensure_project_context, owned_by_user
from repoaudit.investigation.investigation_models import IssueReport
from repoaudit.investigation.workflow import get_investigation_engine
from repoaudit.platform.config import Config, resolve_model

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/investigation/run")
async def run_investigation(
    req: IssueReport,
    user: CurrentUser = Depends(get_current_user),
    x_api_key: str | None = Header(None),
    x_model: str | None = Header(None),
):
    """Run a targeted issue investigation for an imported or local project snapshot."""
    user_id = resolve_user_id(user)
    if not user_id:
        return {"success": False, "message": "Sign in required.", "result": None}

    project = None
    project_record = None
    if req.repo_path:
        if not path_belongs_to_user(req.repo_path, user_id):
            return {"success": False, "message": "Repository path is not in this account's workspace.", "result": None}
        from repoaudit.ingestion.local import ingest_local

        project = ingest_local(req.repo_path)
        project.name = req.project_name
    elif req.investigation_id and not req.project_name:
        return {"success": False, "message": "Project name is required to continue an investigation.", "result": None}
    elif getattr(req, "project_id", None):
        project_record, project = await ensure_project_context(getattr(req, "project_id"), user_id=user_id)
        if project_record and not owned_by_user(project_record, user_id):
            return {"success": False, "message": "Project not found.", "result": None}
    else:
        project_record = None

    project_id = getattr(req, "project_id", "")
    if project is None and project_id:
        project_record, project = await ensure_project_context(project_id, user_id=user_id)

    if project is None and project_id and not project_record:
        return {
            "success": False,
            "message": "Project not found. Open a scanned repository from the dashboard first.",
            "result": None,
        }
    if project is None and project_id:
        return {
            "success": False,
            "message": "Project source code is not loaded. Re-run a scan on this repository, then investigate again.",
            "result": None,
        }

    cfg = Config.load()
    if x_api_key:
        cfg.api_key = x_api_key
    if x_model:
        resolved = resolve_model(x_model)
        cfg.model = resolved
        cfg.model_investigator = resolved

    llm = None
    if cfg.api_key:
        from repoaudit.indexing.llm.client import LLMClient

        llm = LLMClient(
            model=cfg.model,
            api_key=cfg.api_key,
            api_base=cfg.api_base,
            operation_models=cfg.get_operation_models(),
        )

    engine = get_investigation_engine()
    try:
        result = await engine.run_investigation(req, project=project, llm=llm)
    except Exception as exc:
        logger.exception("Investigation failed for %s", req.project_name)
        return {"success": False, "message": f"Investigation failed: {exc}", "result": None}

    return {"success": True, "message": result.summary_verdict, "result": result.model_dump()}

