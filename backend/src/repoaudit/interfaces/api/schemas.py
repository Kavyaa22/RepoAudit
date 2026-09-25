"""pydantic models for the API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScanRequest(BaseModel):
    path: str | None = None
    url: str | None = None
    language: str = "en"
    model: str | None = None
    api_key: str | None = None
    # Human-facing identity (from GitHub import / UI selection)
    display_name: str | None = None
    branch: str | None = None
    owner: str | None = None
    repository_name: str | None = None
    project_id: str | None = None
    # action_api (default) | conservative
    structure_style: str | None = None


class ProjectInfo(BaseModel):
    id: str
    name: str
    status: str = "pending"  # pending, scanning, done, error
    total_files: int = 0
    total_lines: int = 0
    error: str = ""
    branch: str = "main"


class ChatRequest(BaseModel):
    question: str
    history: list[dict] = Field(default_factory=list)


class FileReference(BaseModel):
    path: str
    line_start: int = 0
    line_end: int = 0
    snippet: str = ""
