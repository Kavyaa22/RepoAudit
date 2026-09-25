"""Router for auth.create."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.exceptions import AppError, to_http_exception
from app.core.responses import ApiResponse
from app.modules.auth.create import service
from app.modules.auth.create.schema import CreateRequest, CreateResponse

router = APIRouter(tags=["auth"])


@router.post("/auth/register", response_model=ApiResponse[CreateResponse])
async def create_endpoint(payload: CreateRequest) -> ApiResponse[CreateResponse]:
    try:
        result = await service.execute(payload)
    except AppError as exc:
        raise to_http_exception(exc) from exc
    return ApiResponse(data=result)
