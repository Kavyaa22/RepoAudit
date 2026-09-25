"""Router for auth.logout."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.responses import ApiResponse
from app.modules.auth.logout import service
from app.modules.auth.logout.schema import LogoutResponse

router = APIRouter(tags=["auth"])


@router.post("/auth/logout", response_model=ApiResponse[LogoutResponse])
async def logout_endpoint() -> ApiResponse[LogoutResponse]:
    result = await service.execute()
    return ApiResponse(data=result)
