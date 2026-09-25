"""Auth logout service (stateless JWT — client discards token)."""

from __future__ import annotations

from app.modules.auth.logout.schema import LogoutResponse


async def execute() -> LogoutResponse:
    return LogoutResponse()
