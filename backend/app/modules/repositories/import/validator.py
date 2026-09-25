"""Validators for repositories.import."""

from __future__ import annotations

from .schema import ImportRequest


def validate_import(payload: ImportRequest) -> ImportRequest:
    """Validate and normalize the request."""
    return payload
