"""FastAPI application entry point for RepoAudit (legacy wiki server)."""

from __future__ import annotations

from contextlib import asynccontextmanager

from repoaudit import __version__
from repoaudit.interfaces.api import runtime as api_runtime


def get_cache():
    return api_runtime.get_cache()


def get_projects() -> dict:
    return api_runtime.get_projects()


def create_app():
    """Application factory (used by tests and custom deployments)."""
    try:
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:
        raise RuntimeError(
            "FastAPI not installed. Run: pip install repoaudit[web]"
        ) from exc

    @asynccontextmanager
    async def lifespan(app):
        await api_runtime.init_cache()
        yield
        await api_runtime.close_cache()

    application = FastAPI(
        title="RepoAudit",
        description="Codebase understanding, auditing, and investigation",
        version=__version__,
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from repoaudit.interfaces.api.routes import chat, dead_code, investigation, scan, wiki

    application.include_router(scan.router, prefix="/api")
    application.include_router(wiki.router, prefix="/api")
    application.include_router(chat.router, prefix="/api")
    application.include_router(dead_code.router, prefix="/api")
    application.include_router(investigation.router, prefix="/api")

    @application.get("/api/health")
    async def health():
        return {"status": "ok", "version": __version__}

    from pathlib import Path

    static_dir = Path(__file__).parent / "interfaces" / "api" / "static"
    if static_dir.is_dir():
        application.mount("/", StaticFiles(directory=str(static_dir), html=True))

    return application


app = create_app()


def run(host: str = "0.0.0.0", port: int = 8000, *, reload: bool = False) -> None:
    """Start the ASGI server (used by CLI and `python -m repoaudit.main`)."""
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError(
            "Uvicorn not installed. Run: pip install repoaudit[web]"
        ) from exc

    uvicorn.run(
        "repoaudit.main:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    run(reload=True)
