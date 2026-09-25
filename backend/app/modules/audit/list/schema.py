"""Request / response schemas for audit.list."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ListRequest(BaseModel):
    """Optional filters (reserved for future pagination)."""

    limit: int = Field(default=100, ge=1, le=500)


class AuditHistoryItem(BaseModel):
    """Metadata-only history row. Heavy audit/wiki blobs load on View Report."""

    audit_id: str = ""
    project_id: str = ""
    name: str = "Repository"
    display_name: str | None = None
    branch: str = "main"
    audit_type: str = "full_scan"
    status: str = "done"
    overall_score: int | None = None
    is_valid: bool | None = None
    total_files: int = 0
    total_lines: int = 0
    created_at: str = ""
    owner: str | None = None
    repository_name: str | None = None
    repository_url: str | None = None
    # Kept optional for backward compatibility; list endpoints leave these None.
    structure_audit: dict[str, Any] | None = None
    dead_code_audit: dict[str, Any] | None = None
    security_audit: dict[str, Any] | None = None
    wiki_summary: dict[str, Any] | None = None


class ListResponse(BaseModel):
    items: list[AuditHistoryItem] = Field(default_factory=list)
