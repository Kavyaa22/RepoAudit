"""Data models for dead code & unused dependency audit findings."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

DeadCodeCategory = Literal[
    "unused_import",
    "dead_function",
    "dead_class",
    "orphan_file",
    "unused_dependency",
    "empty_folder",
]

ConfidenceLevel = Literal["HIGH", "MEDIUM", "LOW"]


class DeadCodeFinding(BaseModel):
    """Represents a single flagged dead code item or unused dependency."""

    path: str
    symbol_name: str
    category: DeadCodeCategory
    confidence_level: ConfidenceLevel = "HIGH"
    confidence_score: int = 90  # 0 to 100
    signals_found: list[str] = Field(default_factory=list)
    description: str
    suggestion: str = ""


class DeadCodeAuditResult(BaseModel):
    """Consolidated summary of repository dead code analysis."""

    total_findings: int = 0
    health_score: int = 100  # 0 to 100
    summary_verdict: str = "This codebase looks tidy — no unused code or leftover packages stood out."
    findings: list[DeadCodeFinding] = Field(default_factory=list)
    counts_by_category: dict[str, int] = Field(default_factory=dict)
