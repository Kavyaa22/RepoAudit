"""Router for repositories.sync."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.responses import ApiResponse
from app.modules.repositories.sync import service
from app.modules.repositories.sync.schema import SyncRequest, SyncResponse

router = APIRouter(tags=["repositories"])


@router.post("/repositories/{repo_id}/sync", response_model=ApiResponse[SyncResponse])
async def sync_endpoint(repo_id: str, payload: SyncRequest) -> ApiResponse[SyncResponse]:
    result = await service.execute(repo_id=repo_id, payload=payload)
    return ApiResponse(data=result)
