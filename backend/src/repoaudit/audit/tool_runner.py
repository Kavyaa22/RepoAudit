"""Fail-soft CLI runner for optional security scanner binaries."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_WINDOWS_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

def resolve_executable(names: list[str]) -> str | None:
    extra_dirs = [
        Path(os.environ["REPOAUDIT_SECURITY_TOOLS_DIR"])
        if os.environ.get("REPOAUDIT_SECURITY_TOOLS_DIR")
        else None,
        Path("/usr/local/bin"),
        Path("/opt/security-tools"),
        Path("/app/.security-tools"),
        Path.cwd() / ".security-tools",
        Path.home() / ".local" / "bin",
    ]
    for name in names:
        found = shutil.which(name)
        if found:
            return found
        for directory in extra_dirs:
            if directory is None:
                continue
            candidate = directory / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    return None


def _run_command(
    command: list[str],
    *,
    cwd: str | Path,
    timeout: int,
    acceptable_codes: set[int],
    tool_name: str,
) -> tuple[int | None, str, str, str | None]:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            encoding="utf-8",
            errors="replace",
            creationflags=_WINDOWS_FLAGS,
        )
    except FileNotFoundError:
        return None, "", "", f"{tool_name} is not installed"
    except subprocess.TimeoutExpired:
        logger.warning("Scanner timed out: %s", " ".join(command[:3]))
        return None, "", "", f"{tool_name} timed out after {timeout}s"
    except Exception as exc:  # noqa: BLE001
        logger.warning("Scanner failed to start (%s): %s", tool_name, exc)
        return None, "", "", f"{tool_name} failed to start: {exc}"

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    if completed.returncode not in acceptable_codes:
        reason = (stderr or stdout).strip().splitlines()
        detail = reason[0] if reason else f"exit {completed.returncode}"
        logger.info("Scanner %s exited %s: %s", tool_name, completed.returncode, detail[:200])
        return completed.returncode, stdout, stderr, f"{tool_name} failed: {detail[:180]}"

    return completed.returncode, stdout, stderr, None


def run_cli(
    names: list[str],
    args: list[str],
    *,
    cwd: str | Path,
    timeout: int,
    acceptable_codes: set[int] | None = None,
) -> tuple[int | None, str, str, str | None]:
    """Run an optional scanner binary.

    Returns (returncode, stdout, stderr, skip_reason).
    skip_reason is set when the binary is missing or the process cannot start.
    Exit codes in acceptable_codes (default {0, 1}) are treated as parseable output.
    """
    allowed = acceptable_codes if acceptable_codes is not None else {0, 1}
    executable = resolve_executable(names)
    if not executable:
        return None, "", "", f"{names[0]} is not installed"
    return _run_command(
        [executable, *args],
        cwd=cwd,
        timeout=timeout,
        acceptable_codes=allowed,
        tool_name=names[0],
    )


def run_python_module(
    module: str,
    args: list[str],
    *,
    cwd: str | Path,
    timeout: int,
    acceptable_codes: set[int] | None = None,
) -> tuple[int | None, str, str, str | None]:
    """Run a pip-installed scanner as `python -m module` (venv-safe on Railway)."""
    allowed = acceptable_codes if acceptable_codes is not None else {0, 1}
    return _run_command(
        [sys.executable, "-m", module, *args],
        cwd=cwd,
        timeout=timeout,
        acceptable_codes=allowed,
        tool_name=module.split(".")[0],
    )
