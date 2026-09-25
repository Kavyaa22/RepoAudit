"""Investigation Planner for orchestrating diagnostic sub-tasks."""

from __future__ import annotations

from repoaudit.investigation.investigation_models import IssueReport


class InvestigationPlanner:
    """Plans diagnostic phases for issue investigation."""

    def plan_phases(self, report: IssueReport) -> list[str]:
        return [
            f"Phase 1: Isolate target feature directory for '{report.feature_name or 'general'}'",
            "Phase 2: Perform AST & error log trace analysis",
            "Phase 3: Formulate and score diagnostic hypotheses",
            "Phase 4: Generate step-by-step resolution plan and unified diff patch",
        ]
