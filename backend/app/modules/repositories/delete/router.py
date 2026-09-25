"""Router for repositories.delete."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.responses import ApiResponse
from app.modules.repositories.delete import service
from app.modules.repositories.delete.schema import DeleteResponse

router = APIRouter(tags=["repositories"])


@router.delete("/repositories/{repo_id}", response_model=ApiResponse[DeleteResponse])
async def delete_endpoint(repo_id: str) -> ApiResponse[DeleteResponse]:
    result = await service.execute(repo_id=repo_id)
    return ApiResponse(data=result)
