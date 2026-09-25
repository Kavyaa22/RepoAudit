"""Request / response schemas for projects.edit."""

from __future__ import annotations

from pydantic import BaseModel


class EditRequest(BaseModel):
    """Input payload — expand per operation."""

    pass


class EditResponse(BaseModel):
    """Output payload — expand per operation."""

    message: str = "Edit a project"
