"""Tests for dead code IDE prompt generation."""

from repoaudit.audit.dead_code_models import DeadCodeAuditResult, DeadCodeFinding
from repoaudit.audit.dead_code_prompt import (
    build_batch_prompt,
    build_prompt_for_finding,
    filter_findings,
)


def _sample_finding(**overrides) -> DeadCodeFinding:
    base = {
        "path": "src/utils.py",
        "symbol_name": "unused_helper",
        "category": "dead_function",
        "confidence_level": "HIGH",
        "confidence_score": 85,
        "signals_found": ["Static scanner detected unreferenced function 'unused_helper'"],
        "description": "Function 'unused_helper' has no callers.",
        "suggestion": "Refactor or remove dead function 'unused_helper'.",
    }
    base.update(overrides)
    return DeadCodeFinding(**base)


def test_build_prompt_includes_symbol_and_verification_steps():
    finding = _sample_finding()
    prompt = build_prompt_for_finding(finding, repo_name="MyRepo", branch="develop")

    assert "MyRepo" in prompt
    assert "develop" in prompt
    assert "unused_helper" in prompt
    assert "src/utils.py" in prompt
    assert "Re-verify" in prompt
    assert "Do not" in prompt or "false positives" in prompt.lower()


def test_filter_by_confidence():
    audit = DeadCodeAuditResult(
        findings=[
            _sample_finding(confidence_level="HIGH", symbol_name="high_fn"),
            _sample_finding(confidence_level="MEDIUM", symbol_name="med_fn", confidence_score=60),
        ]
    )
    high_only = filter_findings(audit, confidence="HIGH")
    assert len(high_only) == 1
    assert high_only[0].symbol_name == "high_fn"


def test_filter_by_category():
    audit = DeadCodeAuditResult(
        findings=[
            _sample_finding(category="unused_import", symbol_name="os"),
            _sample_finding(category="dead_function", symbol_name="dead_fn"),
        ]
    )
    imports = filter_findings(audit, category="unused_import")
    assert len(imports) == 1
    assert imports[0].symbol_name == "os"


def test_filter_by_index():
    audit = DeadCodeAuditResult(
        findings=[
            _sample_finding(symbol_name="a"),
            _sample_finding(symbol_name="b"),
        ]
    )
    one = filter_findings(audit, finding_index=1)
    assert len(one) == 1
    assert one[0].symbol_name == "b"


def test_batch_prompt_lists_all_findings():
    audit = DeadCodeAuditResult(
        findings=[
            _sample_finding(symbol_name="fn_one"),
            _sample_finding(symbol_name="fn_two"),
        ]
    )
    prompt = build_batch_prompt(audit.findings, repo_name="BatchRepo", branch="main")
    assert "fn_one" in prompt
    assert "fn_two" in prompt
    assert "2 items" in prompt or "one item at a time" in prompt


def test_single_finding_batch_delegates_to_single_prompt():
    finding = _sample_finding()
    batch = build_batch_prompt([finding])
    single = build_prompt_for_finding(finding)
    assert batch == single
