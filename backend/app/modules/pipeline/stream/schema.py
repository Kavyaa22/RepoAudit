"""Request / response schemas for pipeline.stream."""

from __future__ import annotations

from pydantic import BaseModel


class StreamRequest(BaseModel):
    """Input payload — expand per operation."""

    pass


class StreamResponse(BaseModel):
    """Output payload — expand per operation."""

    message: str = "Stream pipeline events"
