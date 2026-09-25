"""Router for repositories.import."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.exceptions import AppError, to_http_exception
from app.core.responses import ApiResponse
from app.core.security import CurrentUser, get_current_user

from . import service
from .schema import ImportRequest, ImportResponse

router = APIRouter(tags=["repositories"])


@router.post("/repositories/import", response_model=ApiResponse[ImportResponse])
async def import_endpoint(
    payload: ImportRequest,
    user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[ImportResponse]:
    try:
        result = await service.execute(payload, user)
    except AppError as exc:
        raise to_http_exception(exc) from exc
    return ApiResponse(data=result)
