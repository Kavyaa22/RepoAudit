"""View project schemas."""

from __future__ import annotations

from pydantic import BaseModel


class ViewResponse(BaseModel):
    project_id: str
    display_name: str
    repository_url: str
    owner: str
    repository_name: str
    status: str
    workspace_path: str
    message: str = "Project"
