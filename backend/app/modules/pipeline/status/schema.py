"""Request / response schemas for pipeline.status."""

from __future__ import annotations

from pydantic import BaseModel


class StatusRequest(BaseModel):
    """Input payload — expand per operation."""

    pass


class StatusResponse(BaseModel):
    """Output payload — expand per operation."""

    message: str = "Pipeline run status"
