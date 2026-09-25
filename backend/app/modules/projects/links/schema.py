"""Request / response schemas for projects.links."""

from __future__ import annotations

from pydantic import BaseModel


class LinksRequest(BaseModel):
    """Input payload — expand per operation."""

    pass


class LinksResponse(BaseModel):
    """Output payload — expand per operation."""

    message: str = "Project links"
