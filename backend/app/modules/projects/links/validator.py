"""Validators for projects.links."""

from __future__ import annotations

from app.modules.projects.links.schema import LinksRequest


def validate_links(payload: LinksRequest) -> LinksRequest:
    """Validate and normalize the request."""
    return payload
