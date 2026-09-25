"""List projects schemas."""

from __future__ import annotations

from pydantic import BaseModel


class ProjectSummary(BaseModel):
    project_id: str
    display_name: str
    repository_url: str
    status: str
    owner: str | None = None
    repository_name: str | None = None
    default_branch: str | None = None
    workspace_path: str | None = None
    private: bool = False
    file_count: int = 0
    audit_project_id: str | None = None


class ListResponse(BaseModel):
    items: list[ProjectSummary]
    message: str = "Projects"
