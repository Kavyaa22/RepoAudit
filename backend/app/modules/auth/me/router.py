"""Router for auth.me."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.exceptions import AppError, to_http_exception
from app.core.responses import ApiResponse
from app.core.security import CurrentUser, get_current_user
from app.modules.auth.me import service
from app.modules.auth.me.schema import MeDeleteRequest, MeResponse, MeUpdateRequest

router = APIRouter(tags=["auth"])


@router.get("/auth/me", response_model=ApiResponse[MeResponse])
async def me_endpoint(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse[MeResponse]:
    result = await service.execute(user)
    return ApiResponse(data=result)


@router.patch("/auth/me", response_model=ApiResponse[MeResponse])
async def update_me_endpoint(
    payload: MeUpdateRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse[MeResponse]:
    try:
        result = await service.update_profile(user, payload)
    except AppError as exc:
        raise to_http_exception(exc) from exc
    return ApiResponse(data=result)


@router.delete("/auth/me", response_model=ApiResponse[MeResponse])
async def delete_me_endpoint(
    payload: MeDeleteRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiResponse[MeResponse]:
    try:
        result = await service.delete_account(user, payload)
    except AppError as exc:
        raise to_http_exception(exc) from exc
    return ApiResponse(data=result)
