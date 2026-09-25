"""Router for projects.links."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.responses import ApiResponse
from app.modules.projects.links import service
from app.modules.projects.links.schema import LinksResponse

router = APIRouter(tags=["projects"])


@router.get("/projects/{project_id}/links", response_model=ApiResponse[LinksResponse])
async def links_endpoint(project_id: str) -> ApiResponse[LinksResponse]:
    result = await service.execute(project_id=project_id)
    return ApiResponse(data=result)
