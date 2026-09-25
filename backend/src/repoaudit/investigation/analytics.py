"""Lightweight product analytics for investigation funnel quality."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def analytics_path(backend_root: Path) -> Path:
    path = backend_root / "workspace" / "investigation_analytics"
    path.mkdir(parents=True, exist_ok=True)
    return path / "events.jsonl"


def emit_investigation_event(
    backend_root: Path,
    *,
    event: str,
    investigation_id: str,
    payload: dict[str, Any],
) -> None:
    record = {
        "ts": datetime.now(UTC).isoformat(),
        "event": event,
        "investigation_id": investigation_id,
        **payload,
    }
    try:
        with analytics_path(backend_root).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
    except OSError as exc:
        logger.warning("Could not write analytics event: %s", exc)


def summarize_analytics(backend_root: Path) -> dict[str, Any]:
    path = analytics_path(backend_root)
    if not path.is_file():
        return {"events": 0, "runs": 0, "clarified": 0, "continued": 0, "abandoned_estimate": 0}
    runs = clarified = continued = abandoned = 0
    total = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        total += 1
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = row.get("event")
        if name == "investigation_completed":
            runs += 1
            if row.get("route") == "clarify" or row.get("status") == "PARTIAL":
                clarified += 1
        elif name == "investigation_continued":
            continued += 1
        elif name == "investigation_abandoned":
            abandoned += 1
    return {
        "events": total,
        "runs": runs,
        "clarified": clarified,
        "continued": continued,
        "abandoned_estimate": abandoned,
        "paste_after_ask_rate": (continued / clarified) if clarified else 0.0,
    }
