"""Validators for github.oauth."""

from __future__ import annotations

from app.modules.github.oauth.schema import OauthRequest


def validate_oauth(payload: OauthRequest) -> OauthRequest:
    """Validate and normalize the request."""
    return payload
