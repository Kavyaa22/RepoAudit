"""Request / response schemas for repositories.delete."""

from __future__ import annotations

from pydantic import BaseModel


class DeleteRequest(BaseModel):
    """Input payload — expand per operation."""

    pass


class DeleteResponse(BaseModel):
    """Output payload — expand per operation."""

    message: str = "Delete a repository"
