"""Request / response schemas for pipeline.run."""

from __future__ import annotations

from pydantic import BaseModel


class RunRequest(BaseModel):
    """Input payload — expand per operation."""

    pass


class RunResponse(BaseModel):
    """Output payload — expand per operation."""

    message: str = "Start a pipeline run"
