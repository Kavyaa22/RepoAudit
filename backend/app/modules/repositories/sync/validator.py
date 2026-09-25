"""Validators for repositories.sync."""

from __future__ import annotations

from app.modules.repositories.sync.schema import SyncRequest


def validate_sync(payload: SyncRequest) -> SyncRequest:
    """Validate and normalize the request."""
    return payload
