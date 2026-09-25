"""Tests for structure tree quality gate (critique rubric)."""

from repoaudit.audit.structure_scoring import score_action_api_style
from repoaudit.audit.structure_tree_quality import evaluate_tree_quality


def test_quality_penalizes_camelcase_fake_features():
    tree = """
```text
frontend/src/thank/you/ThankYouPage.tsx
frontend/src/measure/in/MeasureInView.tsx
frontend/src/relative/time/relativeTime.ts
backend/src/auth/login/login.ts
```
"""
    report = evaluate_tree_quality(tree)
    assert report.feature_count >= 3
    score, gaps = score_action_api_style(tree)
    assert score < 80
    assert any("camelCase" in g or "feature" in g.lower() or "verb" in g.lower() for g in gaps)


def test_quality_rewards_catalog_shaped_tree():
    tree = """
```text
backend/src/auth/login/login.route.ts
backend/src/proposals/create/create.ts
backend/src/templates/ink_copper/render.ts
frontend/src/auth/login/LoginPage.tsx
frontend/src/proposals/public/ThankYouPage.tsx
frontend/src/templates/ink_copper/InkCopper.tsx
frontend/src/shared/lib/relativeTime.ts
```
"""
    report = evaluate_tree_quality(tree)
    assert report.feature_count <= 12
    assert "thank" not in report.features
    assert report.verb_purity >= 0.85
    assert not report.scatter_hits
    score, _ = score_action_api_style(tree)
    assert score >= 80


def test_quality_detects_auth_scatter():
    tree = """
```text
backend/src/auth/login/a.ts
backend/src/authentication/signup/b.ts
frontend/src/auth/login/LoginPage.tsx
```
"""
    report = evaluate_tree_quality(tree)
    assert report.scatter_hits or any("scatter" in i.lower() or "auth" in i.lower() for i in report.issues)
