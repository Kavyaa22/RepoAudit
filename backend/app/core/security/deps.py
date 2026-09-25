"""JWT helpers and CurrentUser dependency."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.config import get_settings

_bearer = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    user_id: UUID | None
    email: str | None = None
    full_name: str | None = None
    raw: dict[str, Any] | None = None


def create_access_token(
    subject: str,
    *,
    extra: dict[str, Any] | None = None,
    expires_minutes: int | None = None,
) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(
        minutes=expires_minutes or settings.jwt_expire_minutes
    )
    payload: dict[str, Any] = {"sub": subject, "exp": expire}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ] = None,
) -> CurrentUser:
    settings = get_settings()
    if credentials is None or not credentials.credentials:
        if settings.auth_disabled:
            return CurrentUser(user_id=None, email=None, full_name="Anonymous")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    try:
        payload = decode_token(credentials.credentials)
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
        email = payload.get("email")
        full_name = payload.get("full_name")
        if not email or not full_name:
            from app.modules.auth.shared.store import user_store

            record = user_store.find_by_user_id(str(sub))
            if record:
                email = email or record.get("email")
                full_name = full_name or record.get("full_name")
            elif not email:
                for u in user_store._users.values():
                    if u.get("user_id") == str(sub):
                        email = u.get("email")
                        full_name = full_name or u.get("full_name")
                        break

        return CurrentUser(
            user_id=UUID(str(sub)),
            email=email,
            full_name=full_name,
            raw=payload,
        )
    except (JWTError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc


OptionalUser = Annotated[CurrentUser, Depends(get_current_user)]


async def get_optional_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ] = None,
) -> CurrentUser | None:
    """Return authenticated user when a bearer token is present; otherwise None."""
    settings = get_settings()
    if credentials is None or not credentials.credentials:
        if settings.auth_disabled:
            return CurrentUser(user_id=None, email=None, full_name="Anonymous")
        return None

    try:
        payload = decode_token(credentials.credentials)
        sub = payload.get("sub")
        if not sub:
            return None
        email = payload.get("email")
        full_name = payload.get("full_name")
        if not email or not full_name:
            from app.modules.auth.shared.store import user_store

            record = user_store.find_by_user_id(str(sub))
            if record:
                email = email or record.get("email")
                full_name = full_name or record.get("full_name")

        return CurrentUser(
            user_id=UUID(str(sub)),
            email=email,
            full_name=full_name,
            raw=payload,
        )
    except (JWTError, ValueError):
        return None
