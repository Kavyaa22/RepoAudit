"""Auth logout schemas."""

from __future__ import annotations

from pydantic import BaseModel


class LogoutResponse(BaseModel):
    message: str = "Logged out"
