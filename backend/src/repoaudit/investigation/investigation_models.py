"""Pydantic data models for Issue Investigation & Root Cause Debugging."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


ConfidenceLevel = Literal["HIGH", "MEDIUM", "LOW"]
EvidenceTier = Literal["A", "B", "C", "D"]
PatchStatus = Literal["draft", "applied_clean", "checks_passed", "unverified"]


class IsolatedTarget(BaseModel):
    """File or component target isolated as relevant to the reported issue."""

    path: str
    scope: Literal["backend", "frontend", "common"] = "backend"
    feature_name: str = ""
    action_name: str = ""
    relevance_score: int = Field(ge=0, le=100, default=80)
    matched_reason: str = ""


class Hypothesis(BaseModel):
    """Diagnostic hypothesis regarding the root cause of an issue."""

    hypothesis_id: str
    category: str
    title: str
    description: str
    likelihood_score: int = Field(ge=0, le=100, default=70)
    confidence_level: ConfidenceLevel = "MEDIUM"
    evidence_signals: list[str] = Field(default_factory=list)
    contradicting_signals: list[str] = Field(default_factory=list)
    suspect_files: list[str] = Field(default_factory=list)
    next_best_check: str = ""


class CodePatch(BaseModel):
    """Unified code diff patch for repairing identified issue."""

    patch_id: str
    file_path: str
    original_snippet: str = ""
    proposed_snippet: str = ""
    unified_diff: str = ""
    explanation: str = ""
    confidence_score: int = Field(ge=0, le=100, default=85)
    status: PatchStatus = "draft"
    verification_summary: str = "Patch generated but not verified."


class LiveArtifact(BaseModel):
    """Runtime artifact supplied by a user during investigation."""

    kind: Literal["console", "network", "backend_trace", "timing", "screenshot_note", "other"] = "other"
    content: str


class EvidenceAssessment(BaseModel):
    """Signal quality and routing decision for an issue report."""

    score: int = Field(ge=0, le=100, default=0)
    tier: EvidenceTier = "A"
    route: Literal["clarify", "locate", "full"] = "clarify"
    signals: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    guidance: str = ""


class InvestigationPhase(BaseModel):
    """A concise phase event for real-time style reporting."""

    name: str
    status: Literal["completed", "partial", "blocked"] = "completed"
    detail: str = ""
    duration_ms: int = 0


class InvestigationMetrics(BaseModel):
    """Per-run observability fields for quality and latency tracking."""

    evidence_tier: EvidenceTier = "A"
    evidence_score: int = 0
    locate_top_score: int = 0
    locate_target_count: int = 0
    hypothesis_category: str = ""
    hypothesis_confidence: ConfidenceLevel | str = ""
    patch_statuses: list[str] = Field(default_factory=list)
    llm_used: bool = False
    llm_fallback: bool = False
    turn: int = 1
    total_duration_ms: int = 0
    phase_durations_ms: dict[str, int] = Field(default_factory=dict)
    correlation_leads: list[str] = Field(default_factory=list)


class IssueReport(BaseModel):
    """User submitted issue report payload."""

    project_name: str = "Repository"
    project_id: str = ""
    branch: str = "main"
    feature_name: str = ""
    action_name: str = ""
    expected_behavior: str = ""
    actual_behavior: str = ""
    environment: str = ""
    severity: str = ""
    issue_description: str
    error_log: str = ""
    live_artifacts: list[LiveArtifact] = Field(default_factory=list)
    investigation_id: str = ""
    repo_path: str = ""
    turn: int = 1


class InvestigationResult(BaseModel):
    """Complete diagnostic investigation result."""

    investigation_id: str
    project_name: str
    status: Literal["SUCCESS", "PARTIAL", "FAILED"] = "SUCCESS"
    summary_verdict: str
    evidence: EvidenceAssessment = Field(default_factory=EvidenceAssessment)
    phases: list[InvestigationPhase] = Field(default_factory=list)
    snapshot_label: str = ""
    isolated_targets: list[IsolatedTarget] = Field(default_factory=list)
    primary_root_cause: Hypothesis | None = None
    all_hypotheses: list[Hypothesis] = Field(default_factory=list)
    remediation_steps: list[str] = Field(default_factory=list)
    code_patches: list[CodePatch] = Field(default_factory=list)
    metrics: InvestigationMetrics = Field(default_factory=InvestigationMetrics)
    clarification_questions: list[str] = Field(default_factory=list)
    repro_checklist: list[str] = Field(default_factory=list)
    turn: int = 1
    artifact_path: str = ""

