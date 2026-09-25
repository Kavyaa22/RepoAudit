"""Service for audit.list — reads generated audits from Supabase (metadata only)."""

from __future__ import annotations

from app.core.db.repositories.audits import list_audit_runs
from app.core.demo import is_demo_record
from app.core.security import CurrentUser
from app.modules.audit.list.schema import AuditHistoryItem, ListResponse
from app.modules.github.shared.users import resolve_user_id


def _map_row(row: dict) -> AuditHistoryItem:
    """Map a DB row to a light history item — no heavy audit/wiki payloads."""
    result = row.get("result") or {}
    if not isinstance(result, dict):
        result = {}
    project_meta = row.get("projects") or {}
    if isinstance(project_meta, list) and project_meta:
        project_meta = project_meta[0]
    if not isinstance(project_meta, dict):
        project_meta = {}

    return AuditHistoryItem(
        audit_id=str(row.get("audit_id") or ""),
        project_id=str(row.get("project_id") or ""),
        name=str(
            project_meta.get("display_name")
            or result.get("display_name")
            or result.get("name")
            or "Repository"
        ),
        display_name=project_meta.get("display_name") or result.get("display_name"),
        branch=str(row.get("branch") or result.get("branch") or "main"),
        audit_type=str(row.get("audit_type") or "full_scan"),
        status="done" if row.get("status") == "succeeded" else str(row.get("status") or "done"),
        overall_score=(
            row.get("overall_score") if row.get("overall_score") is not None else result.get("score")
        ),
        is_valid=(
            row.get("is_valid") if row.get("is_valid") is not None else result.get("is_valid")
        ),
        total_files=int(result.get("total_files") or 0),
        total_lines=int(result.get("total_lines") or 0),
        created_at=str(row.get("created_at") or result.get("created_at") or ""),
        owner=project_meta.get("owner") or result.get("owner"),
        repository_name=project_meta.get("repository_name") or result.get("repository_name"),
        repository_url=project_meta.get("repository_url") or result.get("repository_url"),
        structure_audit=None,
        dead_code_audit=None,
        security_audit=None,
        wiki_summary=None,
    )


async def execute(user: CurrentUser | None = None) -> ListResponse:
    user_id = resolve_user_id(user)
    if not user_id:
        return ListResponse(items=[])

    rows = list_audit_runs(user_id=user_id, limit=200)
    items = [_map_row(row) for row in rows if isinstance(row, dict)]
    items = [
        item
        for item in items
        if not is_demo_record(
            name=item.name,
            display_name=item.display_name,
            owner=item.owner,
            repository_name=item.repository_name,
            repository_url=item.repository_url,
        )
    ]
    return ListResponse(items=items)
