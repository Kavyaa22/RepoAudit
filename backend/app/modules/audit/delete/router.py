"""Router for audit.delete."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.exceptions import AppError, to_http_exception
from app.core.responses import ApiResponse
from app.core.security import CurrentUser, get_current_user
from app.modules.audit.delete import service
from app.modules.audit.delete.schema import DeleteResponse

router = APIRouter(tags=["audit"])


@router.delete("/audits/{audit_id}", response_model=ApiResponse[DeleteResponse])
async def delete_endpoint(
    audit_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[DeleteResponse]:
    try:
        result = await service.execute(identifier=audit_id, user=user)
    except AppError as exc:
        raise to_http_exception(exc) from exc
    return ApiResponse(data=result)
