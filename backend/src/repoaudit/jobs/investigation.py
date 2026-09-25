"""Investigation maintenance job entrypoint."""

from __future__ import annotations

from pathlib import Path

from repoaudit.investigation.jobs.investigation import run_investigation_maintenance


def run(backend_root: Path | None = None) -> dict:
    return run_investigation_maintenance(backend_root)
