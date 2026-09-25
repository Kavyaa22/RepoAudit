"""Router for audit.view."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.responses import ApiResponse
from app.core.security import CurrentUser, get_current_user
from app.modules.audit.view import service
from app.modules.audit.view.schema import ViewResponse

router = APIRouter(tags=["audit"])


@router.get("/audits/{audit_id}", response_model=ApiResponse[ViewResponse])
async def view_endpoint(
    audit_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[ViewResponse]:
    result = await service.execute(audit_id=audit_id, user=user)
    return ApiResponse(data=result)
