"""Request / response schemas for audit.view."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ViewResponse(BaseModel):
    audit_id: str
    project_id: str = ""
    branch: str = "main"
    audit_type: str = ""
    status: str = ""
    overall_score: int | None = None
    is_valid: bool | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = ""
