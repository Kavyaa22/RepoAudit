"""Router for pipeline.run."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.responses import ApiResponse
from app.modules.pipeline.run import service
from app.modules.pipeline.run.schema import RunRequest, RunResponse

router = APIRouter(tags=["pipeline"])


@router.post("/pipeline/run", response_model=ApiResponse[RunResponse])
async def run_endpoint(payload: RunRequest) -> ApiResponse[RunResponse]:
    result = await service.execute(payload)
    return ApiResponse(data=result)
