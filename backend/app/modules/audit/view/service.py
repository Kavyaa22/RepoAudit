"""Service for audit.view — fetch a single audit run from Supabase."""

from __future__ import annotations

from app.core.db.repositories.audits import get_audit_run, list_findings_for_audit
from app.core.exceptions import NotFoundError
from app.core.security import CurrentUser
from app.modules.audit.view.schema import ViewResponse
from app.modules.github.shared.users import resolve_user_id


async def execute(audit_id: str, user: CurrentUser | None = None) -> ViewResponse:
    user_id = resolve_user_id(user)
    if not user_id:
        raise NotFoundError(f"Audit {audit_id} not found")

    row = get_audit_run(audit_id=audit_id, user_id=user_id)
    if not row:
        raise NotFoundError(f"Audit {audit_id} not found")

    result = row.get("result") or {}
    if not isinstance(result, dict):
        result = {}

    return ViewResponse(
        audit_id=str(row.get("audit_id") or audit_id),
        project_id=str(row.get("project_id") or ""),
        branch=str(row.get("branch") or "main"),
        audit_type=str(row.get("audit_type") or ""),
        status=str(row.get("status") or ""),
        overall_score=row.get("overall_score"),
        is_valid=row.get("is_valid"),
        result=result,
        findings=list_findings_for_audit(audit_id),
        created_at=str(row.get("created_at") or ""),
    )
