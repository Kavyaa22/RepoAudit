"""Router for projects.list."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.responses import ApiResponse
from app.core.security import CurrentUser, get_current_user
from app.modules.projects.list import service
from app.modules.projects.list.schema import ListResponse

router = APIRouter(tags=["projects"])


@router.get("/projects", response_model=ApiResponse[ListResponse])
async def list_endpoint(user: CurrentUser = Depends(get_current_user)) -> ApiResponse[ListResponse]:
    result = await service.execute(user=user)
    return ApiResponse(data=result)
