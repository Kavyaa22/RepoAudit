"""Router for knowledge.view."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.responses import ApiResponse
from app.modules.knowledge.view import service
from app.modules.knowledge.view.schema import ViewResponse

router = APIRouter(tags=["knowledge"])


@router.get("/knowledge/{knowledge_id}", response_model=ApiResponse[ViewResponse])
async def view_endpoint(knowledge_id: str) -> ApiResponse[ViewResponse]:
    result = await service.execute(knowledge_id=knowledge_id)
    return ApiResponse(data=result)
