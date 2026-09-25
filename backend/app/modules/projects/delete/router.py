"""Router for projects.delete."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.exceptions import AppError, to_http_exception
from app.core.responses import ApiResponse
from app.core.security import CurrentUser, get_current_user
from app.modules.projects.delete import service
from app.modules.projects.delete.schema import DeleteResponse

router = APIRouter(tags=["projects"])


@router.delete("/projects/{project_id}", response_model=ApiResponse[DeleteResponse])
async def delete_endpoint(
    project_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[DeleteResponse]:
    try:
        result = await service.execute(project_id=project_id, user=user)
    except AppError as exc:
        raise to_http_exception(exc) from exc
    return ApiResponse(data=result)
