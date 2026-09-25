"""Router for projects.edit."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.responses import ApiResponse
from app.modules.projects.edit import service
from app.modules.projects.edit.schema import EditRequest, EditResponse

router = APIRouter(tags=["projects"])


@router.patch("/projects/{project_id}", response_model=ApiResponse[EditResponse])
async def edit_endpoint(project_id: str, payload: EditRequest) -> ApiResponse[EditResponse]:
    result = await service.execute(project_id=project_id, payload=payload)
    return ApiResponse(data=result)
