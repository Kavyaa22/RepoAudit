"""Router for projects.view."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.exceptions import AppError, to_http_exception
from app.core.responses import ApiResponse
from app.core.security import CurrentUser, get_current_user
from app.modules.projects.view import service
from app.modules.projects.view.schema import ViewResponse

router = APIRouter(tags=["projects"])


@router.get("/projects/{project_id}", response_model=ApiResponse[ViewResponse])
async def view_endpoint(
    project_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[ViewResponse]:
    try:
        result = await service.execute(project_id=project_id, user=user)
    except AppError as exc:
        raise to_http_exception(exc) from exc
    return ApiResponse(data=result)
