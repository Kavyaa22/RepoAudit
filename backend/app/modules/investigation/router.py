"""Router for Issue Investigation API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse

from app.core.security import CurrentUser, get_current_user
from app.modules.investigation import service
from app.modules.investigation.schema import (
    InvestigationContinueRequest,
    InvestigationRunRequest,
    InvestigationRunResponse,
    InvestigationListResponse,
)

router = APIRouter(prefix="/investigation", tags=["Investigation"])


@router.post(
    "/run",
    response_model=InvestigationRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Run targeted root cause issue investigation",
)
async def run_investigation(
    payload: InvestigationRunRequest,
    user: CurrentUser = Depends(get_current_user),
) -> InvestigationRunResponse:
    """Trigger feature-scoped issue investigation, root cause diagnosis, and patch generation."""
    return await service.execute_investigation(payload, user=user)


@router.post(
    "/run/stream",
    status_code=status.HTTP_200_OK,
    summary="Run investigation with SSE phase streaming",
)
async def run_investigation_stream(
    payload: InvestigationRunRequest,
    user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    return StreamingResponse(
        service.stream_investigation_events(payload, user=user),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/{investigation_id}/continue",
    response_model=InvestigationRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Continue an investigation with additional evidence",
)
async def continue_investigation(
    investigation_id: str,
    payload: InvestigationContinueRequest,
    user: CurrentUser = Depends(get_current_user),
) -> InvestigationRunResponse:
    return await service.continue_investigation(investigation_id, payload, user=user)


@router.get(
    "/list",
    response_model=InvestigationListResponse,
    status_code=status.HTTP_200_OK,
    summary="List prior investigations for the current user",
)
async def list_investigations(
    user: CurrentUser = Depends(get_current_user),
) -> InvestigationListResponse:
    try:
        results = service.list_user_investigations(user)
        return InvestigationListResponse(success=True, results=results, message="Investigations retrieved successfully.")
    except Exception as exc:
        return InvestigationListResponse(success=False, results=[], message=f"Failed to list investigations: {exc}")


@router.get(
    "/{investigation_id}",
    response_model=InvestigationRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Fetch a prior investigation result",
)
async def get_investigation(
    investigation_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> InvestigationRunResponse:
    return service.get_investigation_result(investigation_id, user=user)
