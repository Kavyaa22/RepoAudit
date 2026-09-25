"""Request / response schemas for repositories.sync."""

from __future__ import annotations

from pydantic import BaseModel


class SyncRequest(BaseModel):
    """Input payload — expand per operation."""

    pass


class SyncResponse(BaseModel):
    """Output payload — expand per operation."""

    message: str = "Sync a repository"
