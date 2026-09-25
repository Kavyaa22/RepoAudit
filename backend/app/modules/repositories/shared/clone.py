"""Secure read-only clone helpers for repository import."""

from __future__ import annotations

import logging
import os
import shutil
import stat
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_CLONE_TIMEOUT = 180
_MAX_REPO_SIZE_MB = 500


def remove_readonly(func, path, _):
    """Clear read-only attribute on Windows before removing file/dir."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def safe_remove_dir(path: Path) -> None:
    """Safely remove directory tree on Windows handling read-only git files."""
    if not path.exists():
        return
    for item in path.rglob("*"):
        try:
            os.chmod(item, stat.S_IWRITE)
        except Exception:
            pass
    try:
        os.chmod(path, stat.S_IWRITE)
    except Exception:
        pass

    try:
        shutil.rmtree(path, onerror=remove_readonly)
    except Exception:
        shutil.rmtree(path, ignore_errors=True)


def safe_move_dir(src: Path, dst: Path) -> None:
    """Safely move directory tree on Windows, ignoring .git and ensuring src directory is wiped."""
    # Ensure any .git folder in src is wiped first
    git_dir = src / ".git"
    if git_dir.exists():
        safe_remove_dir(git_dir)

    safe_remove_dir(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git"))
    except Exception as e:
        logger.warning("Directory copy encountered warnings (non-fatal): %s", e)
    safe_remove_dir(src)



def authenticated_clone_url(*, owner: str, repo: str, access_token: str) -> str:
    """Build an HTTPS clone URL that embeds a GitHub token (never logged)."""
    return f"https://x-access-token:{access_token}@github.com/{owner}/{repo}.git"


def get_head_sha(dest: Path) -> str:
    """Extract full Git commit SHA from a directory containing a .git folder."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=dest,
            timeout=10,
            check=True,
            capture_output=True,
            text=True,
        )
        return res.stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown_sha"


def clone_repository(
    *,
    owner: str,
    repo: str,
    branch: str,
    access_token: str,
    dest: Path,
    force: bool = False,
) -> tuple[Path, str]:
    """Shallow-clone a specific branch into an isolated sandbox directory and return (path, commit_sha)."""
    if dest.exists() and any(dest.iterdir()) and not force:
        logger.info("Using cached snapshot at %s", dest)
        return dest, dest.name  # directory name is commit_sha if cached in snapshot folder

    if dest.exists():
        safe_remove_dir(dest)

    dest.parent.mkdir(parents=True, exist_ok=True)
    clone_url = authenticated_clone_url(
        owner=owner, repo=repo, access_token=access_token
    )
    public_url = f"https://github.com/{owner}/{repo}.git"
    logger.info("Cloning %s@%s -> %s", public_url, branch, dest)

    try:
        subprocess.run(
            [
                "git",
                "-c",
                "core.longpaths=true",
                "-c",
                "core.protectNTFS=false",
                "clone",
                "--depth",
                "1",
                "--branch",
                branch,
                "--single-branch",
                clone_url,
                str(dest),
            ],
            timeout=_CLONE_TIMEOUT,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired as exc:
        safe_remove_dir(dest)
        raise RuntimeError(f"Clone timed out after {_CLONE_TIMEOUT}s") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        safe_err = stderr.replace(access_token, "***")

        # Handle Windows NTFS case-sensitivity or longpath checkout warnings where files are still fetched
        if "Clone succeeded, but checkout failed" in safe_err and dest.exists() and any(dest.iterdir()):
            logger.warning("Git checkout warning encountered on Windows, but repository files were extracted: %s", safe_err)
        else:
            safe_remove_dir(dest)
            raise RuntimeError(f"Clone failed: {safe_err or 'unknown git error'}") from exc

    commit_sha = get_head_sha(dest)

    total_mb = (
        sum(f.stat().st_size for f in dest.rglob("*") if f.is_file()) / (1024 * 1024)
    )
    if total_mb > _MAX_REPO_SIZE_MB:
        safe_remove_dir(dest)
        raise RuntimeError(
            f"Repo too large ({total_mb:.0f} MB > {_MAX_REPO_SIZE_MB} MB limit)"
        )

    # Strip .git folder to prevent sub-repository tracking
    git_dir = dest / ".git"
    if git_dir.exists():
        safe_remove_dir(git_dir)

    return dest, commit_sha


def summarize_workspace(path: Path) -> dict[str, int | str]:
    """Lightweight post-clone inventory (parser/audit hook point)."""
    files = [f for f in path.rglob("*") if f.is_file() and ".git" not in f.parts]
    extensions: dict[str, int] = {}
    for f in files:
        ext = f.suffix.lower() or "(none)"
        extensions[ext] = extensions.get(ext, 0) + 1
    top_ext = sorted(extensions.items(), key=lambda kv: kv[1], reverse=True)[:8]
    return {
        "file_count": len(files),
        "top_extensions": ", ".join(f"{ext}:{count}" for ext, count in top_ext),
    }
