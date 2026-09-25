"""Auth me schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MeResponse(BaseModel):
    user_id: str | None
    email: str | None = None
    full_name: str | None = None
    message: str = "Current user"


class MeUpdateRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=120)


class MeDeleteRequest(BaseModel):
    password: str = Field(..., min_length=1)
