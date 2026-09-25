"""Request / response schemas for retrieval.query."""

from __future__ import annotations

from pydantic import BaseModel


class QueryRequest(BaseModel):
    """Input payload — expand per operation."""

    pass


class QueryResponse(BaseModel):
    """Output payload — expand per operation."""

    message: str = "Query retrieval index"
