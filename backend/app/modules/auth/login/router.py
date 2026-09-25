"""Router for auth.login."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.exceptions import AppError, to_http_exception
from app.core.responses import ApiResponse
from app.modules.auth.login import service
from app.modules.auth.login.schema import LoginRequest, LoginResponse

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=ApiResponse[LoginResponse])
async def login_endpoint(payload: LoginRequest) -> ApiResponse[LoginResponse]:
    try:
        result = await service.execute(payload)
    except AppError as exc:
        raise to_http_exception(exc) from exc
    return ApiResponse(data=result)
