"""Investigation Workflow Orchestration."""

from __future__ import annotations

from repoaudit.investigation.investigator import InvestigationEngine


def get_investigation_engine() -> InvestigationEngine:
    """Returns singleton/default InvestigationEngine instance."""
    return InvestigationEngine()
