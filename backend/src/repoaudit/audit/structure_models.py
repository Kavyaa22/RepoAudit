"""models for repository folder structure audit."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


from repoaudit.audit.dead_code_models import DeadCodeAuditResult
from repoaudit.audit.findings import SecurityAuditResult
from repoaudit.audit.structure_style import DEFAULT_STRUCTURE_STYLE


class FolderViolation(BaseModel):
    """represents a single folder structure or architectural violation."""

    path: str
    violation_type: Literal[
        "disallowed_root_directory",
        "invalid_path_depth",
        "misplaced_file",
        "unstructured_area",
        "naming_convention_violation"
    ]
    severity: Literal["critical", "high", "medium", "low"] = "medium"
    description: str
    suggestion: str = ""


class FileMove(BaseModel):
    """One suggested file relocation from current layout to target layout."""

    from_path: str
    to_path: str
    reason: str = ""


class FolderStructureAuditResult(BaseModel):
    """consolidated output of static and LLM folder structure audit."""

    is_valid: bool = True
    overall_score: int = 100  # 0 to 100
    static_violations: list[FolderViolation] = Field(default_factory=list)
    unstructured_areas: list[FolderViolation] = Field(default_factory=list)
    structure_style: str = DEFAULT_STRUCTURE_STYLE
    current_structure: str = ""  # Markdown tree of today's layout
    structure_changes: list[FileMove] = Field(default_factory=list)
    recommended_structure: str = ""  # Markdown folder tree suggestion / full report
    style_score: int = 0  # 0-100 closeness to chosen structure style
    style_gaps: list[str] = Field(default_factory=list)
    summary_reason: str = ""
    problems_found: str = ""
    explanation: str = ""
    features_identified: list[str] = Field(default_factory=list)
    no_file_content_modified: bool = True
    dead_code_result: DeadCodeAuditResult | None = None
    security_result: SecurityAuditResult | None = None
