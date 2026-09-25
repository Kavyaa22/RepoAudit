"""Request / response schemas for retrieval.index_op."""

from __future__ import annotations

from pydantic import BaseModel


class IndexOpRequest(BaseModel):
    """Input payload — expand per operation."""

    pass


class IndexOpResponse(BaseModel):
    """Output payload — expand per operation."""

    message: str = "Index maintenance op"
