"""Background jobs for investigation retention and analytics rollups."""

from __future__ import annotations

import logging
from pathlib import Path

from repoaudit.investigation.analytics import summarize_analytics
from repoaudit.investigation.artifacts import cleanup_expired_artifacts

logger = logging.getLogger(__name__)


def run_investigation_maintenance(backend_root: Path | None = None) -> dict:
    """Cleanup expired artifacts and summarize analytics funnel metrics."""
    root = backend_root or Path(__file__).resolve().parents[3]
    removed = cleanup_expired_artifacts(root)
    summary = summarize_analytics(root)
    logger.info(
        "Investigation maintenance removed=%s analytics=%s",
        removed,
        summary,
    )
    return {"removed_artifacts": removed, "analytics": summary}
