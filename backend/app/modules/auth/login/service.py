"""Auth login service."""

from __future__ import annotations

from app.core.exceptions import UnauthorizedError
from app.core.security import create_access_token
from app.modules.auth.login.schema import LoginRequest, LoginResponse
from app.modules.auth.shared.store import user_store


async def execute(payload: LoginRequest) -> LoginResponse:
    email = payload.email.strip().lower()

    user = user_store.verify(email, payload.password)
    if not user:
        raise UnauthorizedError("Invalid email or password")

    token = create_access_token(
        user["user_id"],
        extra={"email": user["email"], "full_name": user["full_name"]},
    )
    return LoginResponse(
        user_id=user["user_id"],
        email=user["email"],
        full_name=user["full_name"],
        access_token=token,
    )

