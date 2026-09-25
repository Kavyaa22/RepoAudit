"""Request / response schemas for github.oauth."""

from __future__ import annotations

from pydantic import BaseModel, Field


class OauthStartResponse(BaseModel):
    authorize_url: str
    state: str
    message: str = "Redirect the user to authorize_url to connect GitHub"


class OauthStatusResponse(BaseModel):
    connected: bool = False
    github_login: str | None = None
    github_user_id: int | None = None
    scopes: str | None = None
    avatar_url: str | None = None
    connected_at: str | None = None
    last_validated_at: str | None = None
    message: str = "GitHub connection status"


class OauthDisconnectResponse(BaseModel):
    disconnected: bool = True
    message: str = "GitHub disconnected"


# Kept for scaffold compatibility
class OauthRequest(BaseModel):
    pass


class OauthResponse(OauthStartResponse):
    message: str = "Start GitHub OAuth"
    authorize_url: str = ""
    state: str = ""
