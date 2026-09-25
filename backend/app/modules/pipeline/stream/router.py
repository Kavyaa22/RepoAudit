"""Router for pipeline.stream."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.responses import ApiResponse
from app.modules.pipeline.stream import service
from app.modules.pipeline.stream.schema import StreamResponse

router = APIRouter(tags=["pipeline"])


@router.get("/pipeline/{run_id}/stream", response_model=ApiResponse[StreamResponse])
async def stream_endpoint(run_id: str) -> ApiResponse[StreamResponse]:
    result = await service.execute(run_id=run_id)
    return ApiResponse(data=result)
