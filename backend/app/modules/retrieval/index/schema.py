"""Request / response schemas for retrieval.index."""

from __future__ import annotations

from pydantic import BaseModel


class IndexRequest(BaseModel):
    """Input payload — expand per operation."""

    pass


class IndexResponse(BaseModel):
    """Output payload — expand per operation."""

    message: str = "Build retrieval index"
