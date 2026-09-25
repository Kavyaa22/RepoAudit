"""Auth register schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreateRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)
    confirm_password: str | None = None
    full_name: str = Field(min_length=1, max_length=120)


class CreateResponse(BaseModel):
    user_id: str
    email: str
    full_name: str
    access_token: str
    token_type: str = "bearer"
    message: str = "Registered successfully"
