"""Request / response schemas for repositories.import."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ImportRequest(BaseModel):
    owner: str = Field(min_length=1)
    repo: str = Field(min_length=1)
    branch: str = "main"
    display_name: str | None = None


class ImportResponse(BaseModel):
    project_id: str
    display_name: str
    repository_url: str
    owner: str
    repository_name: str
    branch: str
    workspace_path: str
    status: str
    private: bool = False
    file_count: int = 0
    message: str = "Repository imported"
