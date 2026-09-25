"""FastAPI application factory."""

from __future__ import annotations

import importlib
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# app/main.py -> parents[0]=app, parents[1]=backend
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_SRC = _BACKEND_ROOT / "src"
_REPOAUDIT_READY = False


def _ensure_local_repoaudit(*, force: bool = False) -> Path:
    """Prefer backend/src/repoaudit. Skip re-import if already loaded (keeps route bindings)."""
    global _REPOAUDIT_READY

    src = str(_SRC.resolve())
    sys.path = [p for p in sys.path if Path(p).resolve() != _SRC.resolve()]
    sys.path.insert(0, src)

    existing = sys.modules.get("repoaudit")
    if existing is not None and not force and _REPOAUDIT_READY:
        origin = Path(getattr(existing, "__file__", "") or "").resolve()
        # Confirm runtime is importable without wiping modules
        importlib.import_module("repoaudit.interfaces.api.runtime")
        return origin

    # Preserve process-level scan singleton across reimports
    shared = sys.modules.get("_repoaudit_shared_state")

    for name in list(sys.modules):
        if name == "repoaudit" or name.startswith("repoaudit."):
            del sys.modules[name]

    if shared is not None:
        sys.modules["_repoaudit_shared_state"] = shared

    pkg = importlib.import_module("repoaudit")
    origin = Path(getattr(pkg, "__file__", "") or "").resolve()
    importlib.import_module("repoaudit.interfaces.api.runtime")
    _REPOAUDIT_READY = True
    return origin


_REPOAUDIT_BOOT_ERROR: Exception | None
try:
    _ensure_local_repoaudit(force=True)
except Exception as _repoaudit_boot_err:  # noqa: BLE001
    _REPOAUDIT_BOOT_ERROR = _repoaudit_boot_err
else:
    _REPOAUDIT_BOOT_ERROR = None

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.core.utils import ensure_runtime_dirs

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    ensure_runtime_dirs()
    settings = get_settings()

    from app.core.supabase.client import supabase_available
    from app.core.supabase.auth_client import supabase_auth_available

    if settings.auth_disabled:
        logger.warning("AUTH_DISABLED=true — authentication checks are bypassed")
    elif supabase_available() and supabase_auth_available():
        logger.info("Supabase auth configured (URL + service role + anon key)")
    elif supabase_available():
        logger.warning(
            "Supabase partially configured: missing SUPABASE_ANON_KEY — login will fail"
        )
    else:
        logger.warning(
            "Supabase not configured — using in-memory auth (dev only; data is lost on restart)"
        )

    try:
        # Do NOT re-evict/reimport repoaudit here — routes already bound to runtime.
        from repoaudit.interfaces.api import runtime as api_runtime

        await api_runtime.ensure_cache()
        origin = Path(getattr(sys.modules.get("repoaudit"), "__file__", "") or "")
        logger.info("Legacy scan/wiki cache initialized (repoaudit=%s)", origin)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Legacy scan/wiki cache init failed: %s", exc)

    # Bare ``uvicorn --reload`` watches cwd (workspace/.venv) and kills in-flight scans.
    if "--reload" in " ".join(sys.argv) and "--reload-dir" not in " ".join(sys.argv):
        logger.warning(
            "Unsafe reload watch detected. Prefer: python run_dev.py  "
            "(or: python -m app / uvicorn with --reload-dir app --reload-dir src)"
        )

    logger.info(
        "Starting %s v%s (auth_disabled=%s)",
        settings.app_name,
        __version__,
        settings.auth_disabled,
    )
    yield
    try:
        from repoaudit.interfaces.api import runtime as api_runtime

        await api_runtime.close_cache()
    except Exception:  # noqa: BLE001
        pass
    logger.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    """Application factory used by uvicorn and tests."""
    configure_logging()
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        description="Codebase understanding, auditing, and investigation",
        version=__version__,
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex or None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(RequestContextMiddleware)

    application.include_router(api_router, prefix=settings.api_v1_prefix)

    try:
        if _REPOAUDIT_BOOT_ERROR is not None:
            _ensure_local_repoaudit(force=True)
        origin = _ensure_local_repoaudit()
        from repoaudit.interfaces.api.routes import chat, dead_code, scan, wiki

        application.include_router(scan.router, prefix="/api")
        application.include_router(wiki.router, prefix="/api")
        application.include_router(chat.router, prefix="/api")
        application.include_router(dead_code.router, prefix="/api")
        logger.info(
            "Mounted legacy /api scan, wiki, chat routes (repoaudit=%s)",
            origin,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not mount legacy scan routes: %s", exc)

    return application


app = create_app()


def run(host: str = "0.0.0.0", port: int = 8001, *, reload: bool = False) -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
        reload_dirs=[str(_BACKEND_ROOT / "app"), str(_BACKEND_ROOT / "src")] if reload else None,
    )


if __name__ == "__main__":
    run(reload=True)
