"""Create project schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    repository_url: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    repository_name: str = Field(min_length=1)


class CreateResponse(BaseModel):
    project_id: str
    display_name: str
    repository_url: str
    status: str
    message: str = "Project created"
