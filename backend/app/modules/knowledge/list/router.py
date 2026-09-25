"""Router for knowledge.list."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.responses import ApiResponse
from app.modules.knowledge.list import service
from app.modules.knowledge.list.schema import ListResponse

router = APIRouter(tags=["knowledge"])


@router.get("/knowledge", response_model=ApiResponse[ListResponse])
async def list_endpoint() -> ApiResponse[ListResponse]:
    result = await service.execute()
    return ApiResponse(data=result)
