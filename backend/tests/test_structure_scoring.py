"""Phase 4: action_api style scoring."""

from repoaudit.audit.structure_scoring import score_action_api_style, score_structure_style
from repoaudit.audit.structure_style import STRUCTURE_STYLE_ACTION_API


def test_score_high_for_action_api_tree():
    tree = """
```text
backend/src/task/create/route.ts
backend/src/task/create/service.ts
frontend/src/task/create/CreateTaskPage.tsx
frontend/src/task/create/useCreateTask.ts
```
"""
    score, gaps = score_action_api_style(tree)
    assert score >= 80
    assert gaps == [] or score >= 80


def test_score_high_for_legacy_api_tree():
    tree = """
```text
backend/src/api/task_api/task_create_api/route.ts
frontend/src/features/task/create/CreateTaskPage.tsx
```
"""
    score, _ = score_action_api_style(tree)
    assert score >= 70


def test_score_low_when_docs_left_at_root():
    tree = """
```text
docs/README.md
backend/src/index.ts
frontend/src/main.tsx
```
"""
    score, gaps = score_action_api_style(tree)
    assert score < 80
    assert any("docs" in g for g in gaps)


def test_score_structure_style_dispatch():
    tree = """
```text
backend/src/auth/login/login.route.ts
frontend/src/auth/login/LoginPage.tsx
```
"""
    score, _ = score_structure_style(tree, STRUCTURE_STYLE_ACTION_API)
    assert score >= 70
