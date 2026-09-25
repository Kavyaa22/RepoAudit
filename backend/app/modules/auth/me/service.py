"""Auth me service — profile read, update, and account deletion."""

from __future__ import annotations

from app.core.exceptions import NotFoundError, UnauthorizedError
from app.core.security import CurrentUser
from app.modules.auth.me.schema import MeDeleteRequest, MeResponse, MeUpdateRequest
from app.modules.auth.shared.store import user_store


async def execute(user: CurrentUser) -> MeResponse:
    if user.user_id is None:
        return MeResponse(user_id=None, email=user.email, full_name=user.full_name or "Anonymous")
    record = user_store.find_by_user_id(str(user.user_id))
    if record:
        return MeResponse(
            user_id=record["user_id"],
            email=record["email"],
            full_name=record["full_name"],
        )
    return MeResponse(
        user_id=str(user.user_id),
        email=user.email,
        full_name=user.full_name,
    )


async def update_profile(user: CurrentUser, payload: MeUpdateRequest) -> MeResponse:
    if user.user_id is None:
        raise UnauthorizedError("Authentication required to update profile.")
    updated = user_store.update_profile(str(user.user_id), full_name=payload.full_name)
    if not updated:
        raise NotFoundError("User account not found.")
    return MeResponse(
        user_id=updated["user_id"],
        email=updated["email"],
        full_name=updated["full_name"],
        message="Profile updated",
    )


async def delete_account(user: CurrentUser, payload: MeDeleteRequest) -> MeResponse:
    if user.user_id is None:
        raise UnauthorizedError("Authentication required to delete account.")
    deleted = user_store.delete_user(str(user.user_id), payload.password)
    if not deleted:
        raise UnauthorizedError("Invalid password or account not found.")
    from app.modules.github.shared.store import github_connection_store

    github_connection_store.disconnect(str(user.user_id))
    return MeResponse(user_id=str(user.user_id), message="Account deleted")
