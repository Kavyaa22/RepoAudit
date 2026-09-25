"""Pydantic schemas for Investigation API endpoint."""

from __future__ import annotations

from pydantic import BaseModel, Field

from repoaudit.investigation.investigation_models import InvestigationResult, LiveArtifact


class InvestigationRunRequest(BaseModel):
    project_name: str = Field(default="Repository")
    branch: str = Field(default="main")
    project_id: str = Field(default="", description="Imported workspace project UUID when available")
    feature_name: str = Field(default="")
    action_name: str = Field(default="")
    expected_behavior: str = Field(default="")
    actual_behavior: str = Field(default="")
    environment: str = Field(default="")
    severity: str = Field(default="")
    issue_description: str = Field(..., min_length=3)
    error_log: str = Field(default="")
    live_artifacts: list[LiveArtifact] = Field(default_factory=list)
    investigation_id: str = Field(default="", description="Reuse to continue a prior investigation turn")
    repo_path: str = Field(default="")
    turn: int = Field(default=1, ge=1)


class InvestigationContinueRequest(BaseModel):
    """Add evidence to an existing investigation and re-run the loop."""

    feature_name: str = Field(default="")
    action_name: str = Field(default="")
    expected_behavior: str = Field(default="")
    actual_behavior: str = Field(default="")
    environment: str = Field(default="")
    severity: str = Field(default="")
    issue_description: str = Field(default="")
    error_log: str = Field(default="")
    live_artifacts: list[LiveArtifact] = Field(default_factory=list)
    branch: str = Field(default="")
    project_name: str = Field(default="")
    project_id: str = Field(default="")
    repo_path: str = Field(default="")


class InvestigationRunResponse(BaseModel):
    success: bool = True
    result: InvestigationResult | None = None
    message: str = ""


class InvestigationListItem(BaseModel):
    investigation_id: str
    project_id: str | None = None
    user_id: str | None = None
    branch: str
    project_name: str
    issue_description: str
    status: str
    created_at: str | None = None
    turn: int = 1


class InvestigationListResponse(BaseModel):
    success: bool = True
    results: list[InvestigationListItem] = []
    message: str = ""

