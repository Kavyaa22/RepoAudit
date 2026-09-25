"""Service for audit.run — executes live folder structure and dead code audit."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from app.core.db.context import ensure_project_for_audit
from app.core.db.repositories.audits import save_audit_run
from app.core.security import CurrentUser
from app.modules.audit.run.schema import RunRequest, RunResponse
from app.modules.github.shared.users import resolve_user_id
from app.modules.projects.shared.store import project_store
from repoaudit.audit.engine import AuditEngine
from repoaudit.ingestion.local import ingest_local
from repoaudit.platform.config import Config

logger = logging.getLogger(__name__)


def _maybe_llm_client():
    """Build LLM client when API key is configured; otherwise return None."""
    try:
        cfg = Config.load()
        if not cfg.api_key:
            return None
        from repoaudit.indexing.llm.client import LLMClient

        return LLMClient(
            model=cfg.model,
            api_key=cfg.api_key,
            api_base=cfg.api_base,
            operation_models=cfg.get_operation_models(),
        )
    except Exception as exc:
        logger.warning("Could not initialize LLM client for audit.run: %s", exc)
        return None


async def execute(payload: RunRequest, user: CurrentUser | None = None) -> RunResponse:
    """Executes full repository folder structure & dead code audit."""
    started = time.perf_counter()
    user_id = resolve_user_id(user)

    try:
        backend_root = Path(__file__).resolve().parents[3]
        candidate_paths: list[Path] = []
        owned = None
        if payload.project_id and user_id:
            owned = project_store.get_for_user(payload.project_id, user_id)
        if owned and owned.get("workspace_path"):
            candidate_paths.append(Path(str(owned["workspace_path"])))
        if payload.repo_path and owned:
            repo_path = Path(payload.repo_path)
            ws = Path(str(owned.get("workspace_path") or ""))
            try:
                repo_path.resolve().relative_to(ws.resolve())
                candidate_paths.append(repo_path)
            except (OSError, ValueError):
                pass
        elif payload.repo_path and user_id:
            # Only accept explicit paths that belong to this user's workspace dir.
            repo_path = Path(payload.repo_path)
            user_root = backend_root / "workspace"
            try:
                resolved = repo_path.resolve()
                if resolved.is_dir() and str(resolved).startswith(str(user_root.resolve())):
                    # Prefer project_id folders that this user owns.
                    for rec in project_store.list(user_id=user_id):
                        rec_ws = Path(str(rec.get("workspace_path") or ""))
                        if rec_ws:
                            try:
                                resolved.relative_to(rec_ws.resolve())
                                candidate_paths.append(repo_path)
                                break
                            except (OSError, ValueError):
                                continue
            except (OSError, ValueError, AttributeError):
                pass

        target_dir = None
        for p in candidate_paths:
            if p and p.is_dir():
                target_dir = p
                break

        if not target_dir:
            return RunResponse(
                success=False,
                message=f"Target directory for project '{payload.project_name}' not found.",
                result=None,
            )

        ctx = ensure_project_for_audit(
            project_id=payload.project_id,
            project_name=payload.project_name,
            branch=payload.branch,
            repo_path=str(target_dir),
            user_id=user_id,
            backend_root=backend_root,
        )

        project = ingest_local(target_dir)
        if payload.project_name and payload.project_name != "Repository":
            guessed = project.name
            if len(guessed) == 40 and all(c in "0123456789abcdef" for c in guessed.lower()):
                project.name = payload.project_name

        engine = AuditEngine()
        llm = _maybe_llm_client()
        style = (payload.structure_style or "action_api").strip().lower()
        if style not in {"action_api", "conservative"}:
            style = "action_api"
        result = await engine.run_full_audit(project, llm=llm, structure_style=style)

        duration_ms = int((time.perf_counter() - started) * 1000)
        if ctx.project_id and user_id:
            save_audit_run(
                project_id=ctx.project_id,
                snapshot_id=ctx.snapshot_id,
                user_id=user_id,
                branch=ctx.branch,
                commit_sha=ctx.commit_sha,
                audit_type="combined",
                result=result,
                duration_ms=duration_ms,
            )

        return RunResponse(
            success=True,
            message=f"Audit completed for project '{payload.project_name}'.",
            result=result,
        )
    except Exception as exc:
        logger.error("Audit run failed: %s", exc, exc_info=True)
        return RunResponse(
            success=False,
            message=f"Audit run failed: {str(exc)}",
            result=None,
        )
