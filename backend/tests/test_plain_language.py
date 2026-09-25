"""Tests for Gemini Flash Lite aliases and manager-facing copy."""

from repoaudit.audit.findings import ScannerStatus, SecurityFinding, summarize_security
from repoaudit.audit.plain_language import dead_code_verdict, security_verdict, structure_summary
from repoaudit.platform.config import GEMINI_FLASH_LITE, resolve_model


def test_gemini_aliases_resolve_to_flash_lite():
    assert resolve_model("gemini-flash-lite") == GEMINI_FLASH_LITE
    assert resolve_model("gemini-flash") == GEMINI_FLASH_LITE
    assert resolve_model("gemini") == GEMINI_FLASH_LITE
    assert resolve_model("flash") == GEMINI_FLASH_LITE
    assert resolve_model(GEMINI_FLASH_LITE) == GEMINI_FLASH_LITE


def test_security_verdict_is_plain_language():
    finding = SecurityFinding(
        category="secret",
        severity="critical",
        path="config.py",
        title="AWS Access Key",
        description="Potential secret exposed.",
        scanner="gitleaks",
    )
    result = summarize_security([finding], [])
    assert "We found 1 security issue" in result.summary_verdict
    assert "urgent" in result.summary_verdict
    assert "gitleaks" not in result.summary_verdict.lower()


def test_skipped_scanners_do_not_name_tools_in_verdict():
    verdict = security_verdict(0, 0, 0, skipped=["semgrep", "gitleaks"])
    assert "partial picture" in verdict
    assert "semgrep" not in verdict
    assert "gitleaks" not in verdict


def test_dead_code_and_structure_copy_is_non_technical():
    assert "leftover" in dead_code_verdict(3, 2)
    assert "tidy" in dead_code_verdict(0, 0)
    assert "easy to follow" in structure_summary(is_valid=True, issue_count=0)
    assert "harder" in structure_summary(is_valid=False, issue_count=4)
