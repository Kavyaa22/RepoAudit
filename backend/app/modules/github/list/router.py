"""Router for github.list."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.exceptions import AppError, to_http_exception
from app.core.responses import ApiResponse
from app.core.security import CurrentUser, get_current_user
from app.modules.github.list import service
from app.modules.github.list.schema import ListBranchesResponse, ListReposResponse, RepoCountResponse

router = APIRouter(tags=["github"])


@router.get("/github/repos", response_model=ApiResponse[ListReposResponse])
async def list_repos_endpoint(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[ListReposResponse]:
    try:
        result = await service.list_repos(user, page=page, per_page=per_page)
    except AppError as exc:
        raise to_http_exception(exc) from exc
    return ApiResponse(data=result)


@router.get("/github/repos/count", response_model=ApiResponse[RepoCountResponse])
async def count_repos_endpoint(
    user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[RepoCountResponse]:
    try:
        result = await service.count_repos(user)
    except AppError as exc:
        raise to_http_exception(exc) from exc
    return ApiResponse(data=result)


@router.get(
    "/github/repos/{owner}/{repo}/branches",
    response_model=ApiResponse[ListBranchesResponse],
)
async def list_branches_endpoint(
    owner: str,
    repo: str,
    user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[ListBranchesResponse]:
    try:
        result = await service.list_branches(user, owner=owner, repo=repo)
    except AppError as exc:
        raise to_http_exception(exc) from exc
    return ApiResponse(data=result)
