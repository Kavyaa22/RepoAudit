"""Service for github.oauth."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi.responses import RedirectResponse

from app.core.config import get_settings
from app.core.exceptions import AppError, UnauthorizedError
from app.core.security import CurrentUser
from app.modules.github.shared.client import (
    GitHubAPIError,
    build_authorize_url,
    exchange_code_for_token,
    github_get,
)
from app.modules.github.shared.store import github_connection_store
from app.modules.github.shared.users import require_user_id, resolve_user_id
from app.modules.github.oauth.schema import (
    OauthDisconnectResponse,
    OauthStartResponse,
    OauthStatusResponse,
)


async def start(user: CurrentUser) -> OauthStartResponse:
    user_id = require_user_id(user)
    state = github_connection_store.create_oauth_state(user_id=user_id, email=user.email)
    settings = get_settings()
    authorize_url = build_authorize_url(state=state, scopes=settings.github_oauth_scopes)
    return OauthStartResponse(authorize_url=authorize_url, state=state)


async def status(user: CurrentUser) -> OauthStatusResponse:
    user_id = resolve_user_id(user)
    if not user_id:
        return OauthStatusResponse(connected=False, message="GitHub not connected")
    record = github_connection_store.status_for(user_id)
    if not record:
        return OauthStatusResponse(connected=False, message="GitHub not connected")
    return OauthStatusResponse(**record, message="GitHub connected")


async def disconnect(user: CurrentUser) -> OauthDisconnectResponse:
    user_id = require_user_id(user)
    github_connection_store.disconnect(user_id)
    return OauthDisconnectResponse()


def _frontend_redirect(**params: str) -> RedirectResponse:
    settings = get_settings()
    base = settings.github_oauth_frontend_redirect.rstrip("/")
    query = urlencode({k: v for k, v in params.items() if v})
    url = f"{base}?{query}" if query else base
    return RedirectResponse(url=url, status_code=302)


async def callback(*, code: str | None, state: str | None, error: str | None) -> RedirectResponse:
    if error:
        return _frontend_redirect(github="error", reason=error)
    if not code or not state:
        return _frontend_redirect(github="error", reason="missing_code_or_state")

    pending = github_connection_store.pop_oauth_state(state)
    if not pending:
        return _frontend_redirect(github="error", reason="invalid_or_expired_state")
    pending_uid = str(pending.get("user_id") or "").strip()
    if not pending_uid or pending_uid == "anonymous" or pending_uid.lower().startswith("email:"):
        return _frontend_redirect(github="error", reason="invalid_user")

    try:
        token_data = await exchange_code_for_token(code)
        access_token = token_data.get("access_token")
        if not access_token:
            return _frontend_redirect(github="error", reason="no_access_token")
        scopes = token_data.get("scope") or "read:user,user:email,repo"
        profile = await github_get("/user", access_token=access_token)
        github_connection_store.upsert_connection(
            user_id=pending_uid,
            access_token=access_token,
            github_login=profile.get("login") or "",
            github_user_id=int(profile.get("id") or 0),
            scopes=scopes,
            avatar_url=profile.get("avatar_url"),
            email=pending.get("email"),
        )
    except (AppError, GitHubAPIError) as exc:
        return _frontend_redirect(github="error", reason=str(exc.message)[:120])
    except Exception as exc:  # noqa: BLE001
        return _frontend_redirect(github="error", reason=str(exc)[:120])

    return _frontend_redirect(github="connected")


# Scaffold alias
async def execute() -> OauthStartResponse:
    raise UnauthorizedError("Use start() with an authenticated user")
