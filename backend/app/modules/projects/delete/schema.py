"""Delete project schemas."""

from __future__ import annotations

from pydantic import BaseModel


class DeleteResponse(BaseModel):
    message: str = "Deleted"
