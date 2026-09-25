"""Request / response schemas for audit.run."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field
from repoaudit.audit.structure_models import FolderStructureAuditResult


class RunRequest(BaseModel):
    project_name: str = Field(default="Repository")
    branch: str = Field(default="main")
    repo_path: str = Field(default="")
    project_id: str = Field(default="", description="Imported workspace project UUID when available")
    structure_style: str = Field(
        default="action_api",
        description="action_api (feature→action folders) or conservative",
    )


class RunResponse(BaseModel):
    success: bool = True
    message: str = "Audit completed successfully."
    result: FolderStructureAuditResult | dict[str, Any] | None = None
