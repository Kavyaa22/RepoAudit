"""Router for projects.create."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.exceptions import AppError, to_http_exception
from app.core.responses import ApiResponse
from app.core.security import CurrentUser, get_current_user
from app.modules.projects.create import service
from app.modules.projects.create.schema import CreateRequest, CreateResponse

router = APIRouter(tags=["projects"])


@router.post("/projects", response_model=ApiResponse[CreateResponse])
async def create_endpoint(
    payload: CreateRequest,
    user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[CreateResponse]:
    try:
        result = await service.execute(payload, user=user)
    except AppError as exc:
        raise to_http_exception(exc) from exc
    return ApiResponse(data=result)
