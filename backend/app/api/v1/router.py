"""Assemble API v1 routers from feature modules."""

from __future__ import annotations

import importlib
from typing import Iterable

from fastapi import APIRouter

from app.api.v1 import system

# (module path to router attribute)
_OPERATION_ROUTERS: tuple[str, ...] = (
    "app.modules.auth.create.router",
    "app.modules.auth.login.router",
    "app.modules.auth.logout.router",
    "app.modules.auth.me.router",
    "app.modules.github.oauth.router",
    "app.modules.github.list.router",
    "app.modules.repositories.import.router",
    "app.modules.repositories.sync.router",
    "app.modules.repositories.delete.router",
    "app.modules.projects.create.router",
    "app.modules.projects.list.router",
    "app.modules.projects.view.router",
    "app.modules.projects.edit.router",
    "app.modules.projects.delete.router",
    "app.modules.projects.links.router",
    "app.modules.pipeline.run.router",
    "app.modules.pipeline.status.router",
    "app.modules.pipeline.stream.router",
    "app.modules.knowledge.list.router",
    "app.modules.knowledge.view.router",
    "app.modules.retrieval.index.router",
    "app.modules.retrieval.index_op.router",
    "app.modules.retrieval.query.router",
    "app.modules.audit.list.router",
    "app.modules.audit.run.router",
    "app.modules.audit.view.router",
    "app.modules.audit.delete.router",
    "app.modules.investigation.router",
)


def _load_routers(module_paths: Iterable[str]) -> list[APIRouter]:
    routers: list[APIRouter] = []
    for path in module_paths:
        module = importlib.import_module(path)
        routers.append(module.router)
    return routers


def build_v1_router() -> APIRouter:
    """Compose the versioned API from system + feature operation routers."""
    api = APIRouter()
    api.include_router(system.router)
    for router in _load_routers(_OPERATION_ROUTERS):
        api.include_router(router)
    return api


api_router = build_v1_router()
