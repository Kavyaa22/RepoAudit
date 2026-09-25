"""Unit tests for settings environment variable parsing."""

import os
from app.core.config.settings import Settings


def test_cors_origins_parsing_single_string(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://myfrontend.up.railway.app")
    s = Settings()
    assert s.cors_origins == ["https://myfrontend.up.railway.app"]


def test_cors_origins_parsing_comma_separated(monkeypatch):
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://localhost:3000, https://myfrontend.up.railway.app"
    )
    s = Settings()
    assert s.cors_origins == [
        "http://localhost:3000",
        "https://myfrontend.up.railway.app",
    ]


def test_cors_origins_parsing_json_array(monkeypatch):
    monkeypatch.setenv(
        "CORS_ORIGINS",
        '["https://myfrontend.up.railway.app", "http://localhost:3000"]'
    )
    s = Settings()
    assert s.cors_origins == [
        "https://myfrontend.up.railway.app",
        "http://localhost:3000",
    ]


def test_cors_origins_parsing_bare_domain(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "myfrontend.up.railway.app")
    s = Settings()
    assert s.cors_origins == ["https://myfrontend.up.railway.app"]
