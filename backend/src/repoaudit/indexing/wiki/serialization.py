"""Serialize and rebuild wiki navigation trees for persistence."""

from __future__ import annotations

from typing import Any


def serialize_sidebar(items) -> list[dict]:
    """Convert SidebarItem dataclass tree to JSON-safe dicts."""
    result = []
    for item in items:
        entry: dict[str, Any] = {"title": item.title, "page_id": item.page_id}
        if item.children:
            entry["children"] = serialize_sidebar(item.children)
        result.append(entry)
    return result


def rebuild_sidebar_from_pages(pages: list[dict]) -> list[dict]:
    """
    Reconstruct sidebar navigation from persisted page metadata.
    Used for legacy records that saved pages but not sidebar.
    """
    if not pages:
        return []

    top_level = [
        p for p in pages
        if not p.get("parent_id")
    ]
    top_level.sort(key=lambda p: p.get("order", 0))

    module_pages = [
        p for p in pages
        if p.get("parent_id") == "modules"
    ]
    module_pages.sort(key=lambda p: p.get("order", 0))

    sidebar: list[dict] = []
    for p in top_level:
        sidebar.append({
            "title": p.get("title", ""),
            "page_id": p.get("id", ""),
        })

    if module_pages:
        sidebar.append({
            "title": "Architecture Domains",
            "page_id": "",
            "children": [
                {"title": p.get("title", ""), "page_id": p.get("id", "")}
                for p in module_pages
            ],
        })

    return sidebar
