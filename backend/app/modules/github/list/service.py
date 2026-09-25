"""Service for github.list."""

from __future__ import annotations

from app.core.exceptions import AppError, UnauthorizedError
from app.core.security import CurrentUser
from app.modules.github.list.schema import (
    BranchItem,
    ListBranchesResponse,
    ListReposResponse,
    RepoCountResponse,
    RepoItem,
)
from app.modules.github.shared.client import GitHubAPIError, github_get
from app.modules.github.shared.store import github_connection_store
from app.modules.github.shared.users import require_user_id


def _require_token(user: CurrentUser) -> str:
    user_id = require_user_id(user)
    token = github_connection_store.get_access_token(user_id)
    if not token:
        raise UnauthorizedError("Connect GitHub before listing repositories")
    return token


async def list_repos(user: CurrentUser, *, page: int = 1, per_page: int = 50) -> ListReposResponse:
    token = _require_token(user)
    try:
        raw = await github_get(
            "/user/repos",
            access_token=token,
            params={
                "per_page": min(per_page, 100),
                "page": page,
                "sort": "updated",
                "affiliation": "owner,collaborator,organization_member",
            },
        )
    except GitHubAPIError as exc:
        raise AppError(exc.message, code="github_api_error") from exc

    items: list[RepoItem] = []
    for r in raw or []:
        owner = (r.get("owner") or {}).get("login") or ""
        items.append(
            RepoItem(
                id=int(r.get("id") or 0),
                full_name=r.get("full_name") or f"{owner}/{r.get('name')}",
                name=r.get("name") or "",
                owner=owner,
                private=bool(r.get("private")),
                description=r.get("description"),
                default_branch=r.get("default_branch") or "main",
                html_url=r.get("html_url") or "",
                clone_url=r.get("clone_url") or "",
                language=r.get("language"),
                updated_at=r.get("updated_at"),
            )
        )
    return ListReposResponse(items=items, page=page, per_page=per_page)


async def count_repos(user: CurrentUser) -> RepoCountResponse:
    """Count all repositories visible to the connected GitHub account."""
    token = _require_token(user)
    total = 0
    page = 1
    per_page = 100
    while page <= 100:
        try:
            raw = await github_get(
                "/user/repos",
                access_token=token,
                params={
                    "per_page": per_page,
                    "page": page,
                    "sort": "updated",
                    "affiliation": "owner,collaborator,organization_member",
                },
            )
        except GitHubAPIError as exc:
            raise AppError(exc.message, code="github_api_error") from exc

        batch = raw or []
        total += len(batch)
        if len(batch) < per_page:
            break
        page += 1

    return RepoCountResponse(total=total)


async def list_branches(
    user: CurrentUser,
    *,
    owner: str,
    repo: str,
) -> ListBranchesResponse:
    token = _require_token(user)
    owner = owner.strip()
    repo = repo.strip()
    try:
        raw = await github_get(
            f"/repos/{owner}/{repo}/branches",
            access_token=token,
            params={"per_page": 100},
        )
        meta = await github_get(f"/repos/{owner}/{repo}", access_token=token)
    except GitHubAPIError as exc:
        raise AppError(exc.message, code="github_api_error") from exc

    items = [
        BranchItem(
            name=b.get("name") or "",
            protected=bool(b.get("protected")),
            commit_sha=((b.get("commit") or {}).get("sha")),
        )
        for b in (raw or [])
    ]
    return ListBranchesResponse(
        owner=owner,
        repo=repo,
        default_branch=meta.get("default_branch"),
        items=items,
    )


async def execute() -> ListReposResponse:
    return ListReposResponse()
