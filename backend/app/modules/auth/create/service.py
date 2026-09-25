"""Auth register service."""

from __future__ import annotations

from uuid import uuid4
from app.core.exceptions import AppError, ConflictError, UnauthorizedError
from app.core.security import create_access_token
from app.modules.auth.create.schema import CreateRequest, CreateResponse
from app.modules.auth.shared.store import user_store


async def execute(payload: CreateRequest) -> CreateResponse:
    email = payload.email.strip().lower()

    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise AppError("Please provide a valid email address.", code="invalid_email")

    # Enforce password confirmation matching if provided
    if payload.confirm_password is not None and payload.password != payload.confirm_password:
        raise AppError("Password and confirm password do not match.", code="password_mismatch")

    existing = user_store.find_by_email(email)
    if existing:
        raise ConflictError("Email address is already registered")

    user = user_store.create(
        email=email,
        password=payload.password,
        full_name=payload.full_name,
        user_id=str(uuid4()),
    )
    token = create_access_token(
        user["user_id"],
        extra={"email": user["email"], "full_name": user["full_name"]},
    )
    return CreateResponse(
        user_id=user["user_id"],
        email=user["email"],
        full_name=user["full_name"],
        access_token=token,
    )

