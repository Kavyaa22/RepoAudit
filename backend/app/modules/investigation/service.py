"""Service layer for issue investigation API (run/continue/stream/persist)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from app.core.db.context import ensure_project_for_audit
from app.core.db.repositories.investigations import get_investigation, save_investigation, list_investigations
from app.core.demo import is_demo_record
from app.core.supabase.client import supabase_available
from datetime import UTC, datetime
from app.core.security import CurrentUser
from app.modules.github.shared.users import resolve_user_id
from app.modules.investigation.schema import (
    InvestigationContinueRequest,
    InvestigationRunRequest,
    InvestigationRunResponse,
)
from repoaudit.ingestion.local import ingest_local
from repoaudit.investigation.analytics import emit_investigation_event
from repoaudit.investigation.artifacts import (
    cleanup_expired_artifacts,
    load_artifact_report,
    load_artifact_result,
    save_artifacts,
)
from repoaudit.investigation.branch_workspace import ensure_branch_workspace
from repoaudit.investigation.investigator import InvestigationEngine
from repoaudit.investigation.investigation_models import IssueReport, LiveArtifact
from repoaudit.investigation.session import load_local_session, merge_reports, save_local_session
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
        logger.warning("Could not initialize LLM client for investigation: %s", exc)
        return None


def _payload_to_report(payload: InvestigationRunRequest) -> IssueReport:
    return IssueReport(
        project_name=payload.project_name,
        project_id=payload.project_id or "",
        branch=payload.branch,
        feature_name=payload.feature_name,
        action_name=payload.action_name,
        expected_behavior=payload.expected_behavior,
        actual_behavior=payload.actual_behavior,
        environment=payload.environment,
        severity=payload.severity,
        issue_description=payload.issue_description,
        error_log=payload.error_log,
        live_artifacts=list(payload.live_artifacts or []),
        investigation_id=payload.investigation_id or "",
        repo_path=payload.repo_path,
        turn=payload.turn or 1,
    )


def _github_clone_context(
    user: CurrentUser | None,
    project_name: str,
    project_id: str = "",
) -> tuple[str, str, str]:
    """Best-effort owner/repo/token for exact branch checkout — this app user only."""
    token = ""
    owner = ""
    repo = project_name
    try:
        from app.modules.github.shared.store import github_connection_store
        from app.modules.projects.shared.store import project_store

        user_id = resolve_user_id(user)
        if user_id:
            token = github_connection_store.get_access_token(user_id) or ""
            if project_id:
                record = project_store.get_for_user(project_id, user_id)
                if record:
                    owner = str(record.get("owner") or "")
                    repo = str(record.get("repository_name") or repo)
    except Exception:  # noqa: BLE001
        token = ""
    if not owner and "/" in project_name:
        owner, repo = project_name.split("/", 1)
    return owner, repo, token


async def execute_investigation(
    payload: InvestigationRunRequest,
    user: CurrentUser | None = None,
    on_phase: Callable[[dict[str, Any]], Any] | None = None,
) -> InvestigationRunResponse:
    """Executes issue investigation workflow and returns diagnostic report."""
    started = time.perf_counter()
    user_id = resolve_user_id(user)
    if not user_id:
        return InvestigationRunResponse(
            success=False,
            result=None,
            message="Sign in required to run an investigation.",
        )
    backend_root = Path(__file__).resolve().parents[3]
    # Opportunistic retention cleanup (cheap).
    try:
        cleanup_expired_artifacts(backend_root)
    except Exception:  # noqa: BLE001
        pass

    try:
        report = _payload_to_report(payload)
        if report.project_id:
            from app.modules.projects.shared.store import project_store

            if not project_store.get_for_user(report.project_id, user_id):
                report.project_id = ""

        continuing = False
        if report.investigation_id:
            prior_report = _load_prior_report(backend_root, report.investigation_id, user_id)
            if prior_report is None:
                report.investigation_id = ""
            else:
                continuing = True
                report = merge_reports(prior_report, report)
                report.turn = max(prior_report.turn + 1, report.turn, 2)

        from app.modules.projects.shared.store import project_store as _project_store

        if report.project_id and not _project_store.get_for_user(report.project_id, user_id):
            report.project_id = ""
        owned_project_id = report.project_id or ""
        if not owned_project_id and payload.project_id:
            if _project_store.get_for_user(payload.project_id, user_id):
                owned_project_id = payload.project_id
                report.project_id = owned_project_id

        owner, repo_name, token = _github_clone_context(
            user, report.project_name, owned_project_id
        )
        target_dir = ensure_branch_workspace(
            backend_root=backend_root,
            project_name=report.project_name,
            branch=report.branch,
            project_id=owned_project_id,
            repo_path=report.repo_path or payload.repo_path,
            owner=owner,
            repository=repo_name,
            access_token=token,
            user_id=user_id,
        )

        if not target_dir:
            return InvestigationRunResponse(
                success=False,
                result=None,
                message=f"Target directory for project '{payload.project_name}' not found.",
            )

        ctx = ensure_project_for_audit(
            project_id=owned_project_id,
            project_name=report.project_name,
            branch=report.branch,
            repo_path=str(target_dir),
            user_id=user_id,
            backend_root=backend_root,
        )

        project = ingest_local(target_dir)
        if report.project_name and report.project_name != "Repository":
            guessed = project.name
            if len(guessed) == 40 and all(c in "0123456789abcdef" for c in guessed.lower()):
                project.name = report.project_name

        engine = InvestigationEngine()
        llm = _maybe_llm_client()
        result = await engine.run_investigation(report=report, project=project, llm=llm, on_phase=on_phase)

        duration_ms = int((time.perf_counter() - started) * 1000)
        if result.metrics:
            result.metrics.total_duration_ms = duration_ms

        artifact_path = save_artifacts(
            backend_root,
            investigation_id=result.investigation_id,
            report=report,
            result=result,
            user_id=user_id,
        )
        result.artifact_path = artifact_path

        save_local_session(
            backend_root,
            investigation_id=result.investigation_id,
            report=report,
            result=result,
            workspace_path=str(target_dir),
            user_id=user_id,
        )

        emit_investigation_event(
            backend_root,
            event="investigation_continued" if continuing else "investigation_completed",
            investigation_id=result.investigation_id,
            payload={
                "status": result.status,
                "route": result.evidence.route if result.evidence else "",
                "tier": result.evidence.tier if result.evidence else "",
                "score": result.evidence.score if result.evidence else 0,
                "turn": result.turn,
                "duration_ms": duration_ms,
                "locate_top_score": result.metrics.locate_top_score if result.metrics else 0,
                "llm_used": result.metrics.llm_used if result.metrics else False,
                "patch_statuses": result.metrics.patch_statuses if result.metrics else [],
            },
        )

        if ctx.project_id:
            save_investigation(
                investigation_id=result.investigation_id,
                project_id=ctx.project_id,
                snapshot_id=ctx.snapshot_id,
                user_id=user_id,
                branch=ctx.branch,
                commit_sha=ctx.commit_sha,
                issue_description=report.issue_description,
                feature_name=report.feature_name,
                action_name=report.action_name,
                error_log=report.error_log,
                result=result,
                workspace_path=str(target_dir),
                duration_ms=duration_ms,
                artifact_path=artifact_path,
            )

        return InvestigationRunResponse(
            success=True,
            result=result,
            message="Investigation completed successfully.",
        )
    except Exception as exc:
        logger.error("Investigation execution failed: %s", exc, exc_info=True)
        return InvestigationRunResponse(
            success=False,
            result=None,
            message=f"Investigation failed: {str(exc)}",
        )


async def stream_investigation_events(
    payload: InvestigationRunRequest,
    user: CurrentUser | None = None,
) -> AsyncIterator[str]:
    """Yield SSE payloads while an investigation runs."""
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def on_phase(event: dict[str, Any]) -> None:
        await queue.put(event)

    async def runner() -> None:
        try:
            response = await execute_investigation(payload, user=user, on_phase=on_phase)
            await queue.put(
                {
                    "type": "result",
                    "success": response.success,
                    "message": response.message,
                    "result": response.result.model_dump() if response.result else None,
                }
            )
        except Exception as exc:  # noqa: BLE001
            await queue.put({"type": "error", "error": str(exc)})
        finally:
            await queue.put(None)

    task = asyncio.create_task(runner())
    try:
        yield _sse({"type": "started", "message": "Investigation stream started"})
        while True:
            event = await queue.get()
            if event is None:
                break
            yield _sse(event)
        yield _sse({"done": True})
    finally:
        await task


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def continue_investigation(
    investigation_id: str,
    payload: InvestigationContinueRequest,
    user: CurrentUser | None = None,
) -> InvestigationRunResponse:
    """Merge new evidence into a prior investigation and re-run."""
    user_id = resolve_user_id(user)
    if not user_id:
        return InvestigationRunResponse(
            success=False,
            result=None,
            message="Sign in required to continue an investigation.",
        )
    backend_root = Path(__file__).resolve().parents[3]
    prior = _load_prior_report(backend_root, investigation_id, user_id)
    if prior is None:
        return InvestigationRunResponse(
            success=False,
            result=None,
            message=f"Investigation '{investigation_id}' was not found. Run a new investigation first.",
        )

    incoming = IssueReport(
        project_name=payload.project_name or prior.project_name,
        project_id=payload.project_id or prior.project_id,
        branch=payload.branch or prior.branch,
        feature_name=payload.feature_name,
        action_name=payload.action_name,
        expected_behavior=payload.expected_behavior,
        actual_behavior=payload.actual_behavior,
        environment=payload.environment,
        severity=payload.severity,
        issue_description=payload.issue_description or prior.issue_description,
        error_log=payload.error_log,
        live_artifacts=list(payload.live_artifacts or []),
        investigation_id=investigation_id,
        repo_path=payload.repo_path or prior.repo_path,
        turn=prior.turn + 1,
    )
    merged = merge_reports(prior, incoming)
    merged.investigation_id = investigation_id
    merged.turn = prior.turn + 1

    run_payload = InvestigationRunRequest(
        project_name=merged.project_name,
        branch=merged.branch,
        project_id=merged.project_id,
        feature_name=merged.feature_name,
        action_name=merged.action_name,
        expected_behavior=merged.expected_behavior,
        actual_behavior=merged.actual_behavior,
        environment=merged.environment,
        severity=merged.severity,
        issue_description=merged.issue_description,
        error_log=merged.error_log,
        live_artifacts=merged.live_artifacts,
        investigation_id=investigation_id,
        repo_path=merged.repo_path,
        turn=merged.turn,
    )
    return await execute_investigation(run_payload, user=user)


def get_investigation_result(
    investigation_id: str,
    user: CurrentUser | None = None,
) -> InvestigationRunResponse:
    user_id = resolve_user_id(user)
    if not user_id:
        return InvestigationRunResponse(success=False, result=None, message="Sign in required.")
    backend_root = Path(__file__).resolve().parents[3]
    artifact_result = load_artifact_result(backend_root, investigation_id, user_id=user_id)
    if artifact_result:
        from repoaudit.investigation.investigation_models import InvestigationResult

        try:
            result = InvestigationResult(**artifact_result)
            return InvestigationRunResponse(success=True, result=result, message="Loaded investigation artifacts.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Artifact result parse failed: %s", exc)

    local = load_local_session(backend_root, investigation_id, user_id=user_id)
    if local and local.get("result"):
        from repoaudit.investigation.investigation_models import InvestigationResult

        try:
            result = InvestigationResult(**local["result"])
            return InvestigationRunResponse(success=True, result=result, message="Loaded local investigation session.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Local investigation parse failed: %s", exc)

    record = get_investigation(investigation_id, user_id=user_id)
    if not record:
        return InvestigationRunResponse(success=False, result=None, message="Investigation not found.")
    payload = record.get("result") or {}
    from repoaudit.investigation.investigation_models import InvestigationResult

    try:
        result = InvestigationResult(**payload)
    except Exception:
        return InvestigationRunResponse(success=False, result=None, message="Stored investigation payload is invalid.")
    return InvestigationRunResponse(success=True, result=result, message="Loaded investigation.")


def _load_prior_report(
    backend_root: Path,
    investigation_id: str,
    user_id: str | None,
) -> IssueReport | None:
    if not user_id:
        return None
    artifact_report = load_artifact_report(backend_root, investigation_id, user_id=user_id)
    if artifact_report is not None:
        return artifact_report

    local = load_local_session(backend_root, investigation_id, user_id=user_id)
    if local and local.get("report"):
        try:
            data = local["report"]
            data["live_artifacts"] = [LiveArtifact(**a) if isinstance(a, dict) else a for a in data.get("live_artifacts") or []]
            return IssueReport(**data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not restore prior report from cache: %s", exc)

    record = get_investigation(investigation_id, user_id=user_id)
    if not record:
        return None
    result = record.get("result") or {}
    return IssueReport(
        project_name=result.get("project_name") or "Repository",
        branch=record.get("branch") or "main",
        feature_name=record.get("feature_name") or "",
        action_name=record.get("action_name") or "",
        issue_description=record.get("issue_description") or record.get("issue") or "continued investigation",
        error_log=record.get("error_log") or "",
        investigation_id=investigation_id,
        repo_path=record.get("path") or "",
        turn=int((result.get("turn") or 1)),
    )


def list_user_investigations(user: CurrentUser | None) -> list[dict[str, Any]]:
    """List investigations for this app user only (Supabase + this user's disk cache)."""
    user_id = resolve_user_id(user)
    if not user_id:
        return []
    backend_root = Path(__file__).resolve().parents[3]
    by_id: dict[str, dict[str, Any]] = {}

    if supabase_available():
        for row in list_investigations(user_id):
            proj = row.get("projects") or {}
            result_payload = row.get("result") or {}
            status_val = "PARTIAL"
            db_status = str(row.get("status") or "").lower()
            if db_status == "complete":
                status_val = "SUCCESS"
            elif db_status == "failed":
                status_val = "FAILED"
            elif db_status == "incomplete":
                status_val = "PARTIAL"
            inv_id = str(row.get("investigation_id") or "")
            if not inv_id:
                continue
            by_id[inv_id] = {
                "investigation_id": inv_id,
                "project_id": row.get("project_id"),
                "user_id": row.get("user_id") or user_id,
                "branch": row.get("branch") or "main",
                "project_name": proj.get("display_name") or row.get("project_name") or proj.get("repository_name") or "Repository",
                "issue_description": row.get("issue_description") or row.get("issue") or "",
                "status": status_val,
                "created_at": row.get("created_at"),
                "turn": result_payload.get("turn", 1) if isinstance(result_payload, dict) else 1,
            }

    from repoaudit.investigation.session import cache_dir

    cache_path = cache_dir(backend_root, user_id=user_id)
    if cache_path.is_dir():
        for file in cache_path.glob("*.json"):
            if not file.is_file():
                continue
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                stored_uid = str(data.get("user_id") or "")
                if stored_uid and stored_uid != str(user_id):
                    continue
                inv_id = str(data.get("investigation_id") or "")
                if not inv_id or inv_id in by_id:
                    continue
                report = data.get("report") or {}
                res = data.get("result") or {}
                mtime = datetime.fromtimestamp(file.stat().st_mtime, UTC).isoformat()
                by_id[inv_id] = {
                    "investigation_id": inv_id,
                    "project_id": report.get("project_id"),
                    "user_id": user_id,
                    "branch": report.get("branch") or "main",
                    "project_name": report.get("project_name") or "Repository",
                    "issue_description": report.get("issue_description") or "",
                    "status": res.get("status") or "SUCCESS",
                    "created_at": mtime,
                    "turn": res.get("turn") or report.get("turn") or 1,
                }
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not parse cached investigation session file %s: %s", file.name, exc)

    results = list(by_id.values())
    results.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return _without_demo_investigations(results)


def _without_demo_investigations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for item in items
        if not is_demo_record(
            name=item.get("project_name"),
            display_name=item.get("project_name"),
            project_name=item.get("project_name"),
        )
    ]

