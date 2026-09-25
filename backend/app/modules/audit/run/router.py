"""Router for audit.run."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.responses import ApiResponse
from app.core.security import CurrentUser, get_current_user
from app.modules.audit.run import service
from app.modules.audit.run.schema import RunRequest, RunResponse

router = APIRouter(tags=["audit"])


@router.post("/audits/run", response_model=ApiResponse[RunResponse])
async def run_endpoint(
    payload: RunRequest,
    user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[RunResponse]:
    result = await service.execute(payload, user=user)
    return ApiResponse(data=result)
