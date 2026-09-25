"""Delete audit schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DeleteResponse(BaseModel):
    message: str = "Deleted"
    deleted_ids: list[str] = Field(default_factory=list)
    purged_project_ids: list[str] = Field(default_factory=list)
