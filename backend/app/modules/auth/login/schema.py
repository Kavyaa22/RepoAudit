"""Auth login schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    user_id: str
    email: str
    full_name: str
    access_token: str
    token_type: str = "bearer"
    message: str = "Logged in"
