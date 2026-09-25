"""Request / response schemas for knowledge.view."""

from __future__ import annotations

from pydantic import BaseModel


class ViewRequest(BaseModel):
    """Input payload — expand per operation."""

    pass


class ViewResponse(BaseModel):
    """Output payload — expand per operation."""

    message: str = "View knowledge artifact"
