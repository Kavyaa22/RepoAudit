"""Router for github.oauth."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse

from app.core.exceptions import AppError, to_http_exception
from app.core.responses import ApiResponse
from app.core.security import CurrentUser, get_current_user
from app.modules.github.oauth import service
from app.modules.github.oauth.schema import (
    OauthDisconnectResponse,
    OauthStartResponse,
    OauthStatusResponse,
)

router = APIRouter(tags=["github"])


@router.get("/github/oauth/start", response_model=ApiResponse[OauthStartResponse])
async def oauth_start(
    user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[OauthStartResponse]:
    try:
        result = await service.start(user)
    except AppError as exc:
        raise to_http_exception(exc) from exc
    return ApiResponse(data=result)


@router.get("/github/oauth/callback")
async def oauth_callback(
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
) -> RedirectResponse:
    return await service.callback(code=code, state=state, error=error)


@router.get("/github/status", response_model=ApiResponse[OauthStatusResponse])
async def oauth_status(
    user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[OauthStatusResponse]:
    result = await service.status(user)
    return ApiResponse(data=result)


@router.post("/github/disconnect", response_model=ApiResponse[OauthDisconnectResponse])
async def oauth_disconnect(
    user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[OauthDisconnectResponse]:
    result = await service.disconnect(user)
    return ApiResponse(data=result)
