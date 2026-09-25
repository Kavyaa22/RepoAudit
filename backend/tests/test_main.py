"""Smoke test for the webapp entry point."""

import importlib
import importlib.util


def test_main_app_imports_when_web_installed():
    if importlib.util.find_spec("fastapi") is None:
        return

    main = importlib.import_module("repoaudit.main")
    assert main.app is not None
    assert main.app.title == "RepoAudit"
