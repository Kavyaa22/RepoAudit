"""Request / response schemas for knowledge.list."""

from __future__ import annotations

from pydantic import BaseModel


class ListRequest(BaseModel):
    """Input payload — expand per operation."""

    pass


class ListResponse(BaseModel):
    """Output payload — expand per operation."""

    message: str = "List knowledge artifacts"
