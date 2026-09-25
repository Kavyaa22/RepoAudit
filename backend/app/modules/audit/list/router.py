"""Router for audit.list."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.responses import ApiResponse
from app.core.security import CurrentUser, get_current_user
from app.modules.audit.list import service
from app.modules.audit.list.schema import ListResponse

router = APIRouter(tags=["audit"])


@router.get("/audits", response_model=ApiResponse[ListResponse])
async def list_endpoint(user: CurrentUser = Depends(get_current_user)) -> ApiResponse[ListResponse]:
    result = await service.execute(user=user)
    return ApiResponse(data=result)
