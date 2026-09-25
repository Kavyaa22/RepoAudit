"""Router for pipeline.status."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.responses import ApiResponse
from app.modules.pipeline.status import service
from app.modules.pipeline.status.schema import StatusResponse

router = APIRouter(tags=["pipeline"])


@router.get("/pipeline/{run_id}/status", response_model=ApiResponse[StatusResponse])
async def status_endpoint(run_id: str) -> ApiResponse[StatusResponse]:
    result = await service.execute(run_id=run_id)
    return ApiResponse(data=result)
