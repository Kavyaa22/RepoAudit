"""Thin GitHub REST API client (user-scoped, read-only usage)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.core.exceptions import AppError

GITHUB_API = "https://api.github.com"
GITHUB_AUTHORIZE = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN = "https://github.com/login/oauth/access_token"


class GitHubAPIError(AppError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message, code="github_api_error")
        self.status_code = status_code


def build_authorize_url(*, state: str, scopes: str = "read:user,user:email,repo") -> str:
    settings = get_settings()
    if not settings.github_client_id:
        raise AppError("GitHub OAuth is not configured (GITHUB_CLIENT_ID)", code="github_not_configured")
    query = urlencode(
        {
            "client_id": settings.github_client_id,
            "redirect_uri": settings.github_oauth_redirect_uri,
            "scope": scopes,
            "state": state,
            "allow_signup": "true",
        }
    )
    return f"{GITHUB_AUTHORIZE}?{query}"


async def exchange_code_for_token(code: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.github_client_id or not settings.github_client_secret:
        raise AppError("GitHub OAuth is not configured", code="github_not_configured")

    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            GITHUB_TOKEN,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.github_oauth_redirect_uri,
            },
        )
    data = res.json()
    if res.status_code >= 400 or "error" in data:
        raise GitHubAPIError(
            data.get("error_description") or data.get("error") or "Token exchange failed",
            status_code=res.status_code,
        )
    return data


async def github_get(path: str, *, access_token: str, params: dict[str, Any] | None = None) -> Any:
    url = path if path.startswith("http") else f"{GITHUB_API}{path}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.get(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            params=params,
        )
    if res.status_code >= 400:
        detail = res.text[:300]
        raise GitHubAPIError(f"GitHub API error ({res.status_code}): {detail}", status_code=res.status_code)
    return res.json()
