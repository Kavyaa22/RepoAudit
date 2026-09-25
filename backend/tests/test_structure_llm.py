import pytest

from repoaudit.audit.structure_llm import (
    LLMStructureAuditor,
    _parse_llm_response,
    salvage_structure_partial,
)
from repoaudit.audit.structure_models import FolderViolation
from repoaudit.indexing.models import FileInfo, ProjectContext


class _StubLLM:
    def __init__(self, payload: str | Exception):
        self.payload = payload
        self.calls = 0

    async def complete(self, messages, **kwargs):
        self.calls += 1
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def _project() -> ProjectContext:
    return ProjectContext(
        name="ClientOnboarding",
        root=".",
        files=[
            FileInfo(path="frontend/src/pages/Home.tsx", size=40, language="tsx"),
            FileInfo(path="frontend/src/lib/api.ts", size=20, language="typescript"),
            FileInfo(path="backend/src/server.ts", size=30, language="typescript"),
            FileInfo(path="README.md", size=10, language="markdown"),
        ],
    )


def _static_issues() -> list[FolderViolation]:
    return [
        FolderViolation(
            path="scripts",
            violation_type="disallowed_root_directory",
            severity="medium",
            description="Unexpected top-level folder.",
            suggestion="Move scripts under backend/scripts.",
        ),
        FolderViolation(
            path="tmp",
            violation_type="disallowed_root_directory",
            severity="medium",
            description="Scratch folder at the repo root.",
            suggestion="Remove or ignore tmp/.",
        ),
    ]


def test_salvage_structure_partial_recovers_truncated_tree():
    raw = (
        '{"unstructured_areas": [{"path": "scripts", "severity": "medium", '
        '"description": "Scratch scripts at the root.", "suggestion": "backend/scripts"}], '
        '"summary_reason": "Two folders sit in the wrong place.", '
        '"recommended_structure": "```text\\nfrontend/\\n  src/pages/Home.tsx\\n  src/'
    )
    saved = salvage_structure_partial(raw)
    assert saved["summary_reason"] == "Two folders sit in the wrong place."
    assert saved["unstructured_areas"][0]["path"] == "scripts"
    assert "frontend/" in saved["recommended_structure"]


def test_parse_llm_response_closes_truncated_json():
    raw = (
        '{"summary_reason": "The folder layout has 2 issues that will make the project '
        'harder for the team to maintain.", "unstructured_areas": [], '
        '"recommended_structure": "```text\\nREADME.md\\nfrontend/src/pages/Home.tsx'
    )
    data = _parse_llm_response(raw)
    assert "2 issues" in data["summary_reason"]
    assert "recommended_structure" in data


@pytest.mark.asyncio
async def test_auditor_uses_salvaged_summary_instead_of_could_not_finish():
    # Enough file leaves + feature/action paths so salvage can pass validation.
    truncated = (
        '{"unstructured_areas": [{"path": "scripts", "severity": "medium", '
        '"description": "Scratch scripts at the root.", "suggestion": "backend/scripts"}], '
        '"summary_reason": "Two folders sit in the wrong place.", '
        '"features_identified": ["home"], '
        '"folder_changes": ['
        '{"from_path": "frontend/src/pages/Home.tsx", "to_path": "frontend/src/home/view/Home.tsx", "reason": "feature"},'
        '{"from_path": "frontend/src/lib/api.ts", "to_path": "frontend/src/common/shared/api.ts", "reason": "shared"},'
        '{"from_path": "scripts/x.mjs", "to_path": "backend/scripts/x.mjs", "reason": "fold"}'
        '], '
        '"recommended_structure": "```text\\n'
        "backend/src/server.ts\\n"
        "frontend/src/home/view/Home.tsx\\n"
        "frontend/src/common/shared/api.ts\\n"
        '```", '
        '"no_file_content_modified": true, '
        '"explanation": "Regrouped.", '
        '"problems_found": "Type folders at the root."}'
    )
    llm = _StubLLM(truncated)
    result = await LLMStructureAuditor().audit(
        _project(),
        llm,
        static_violations=_static_issues(),
    )
    assert "could not finish the full organization review" not in result.summary_reason.lower()
    assert "Two folders sit in the wrong place" in result.summary_reason or result.recommended_structure
    assert result.recommended_structure
    assert result.no_file_content_modified is True


@pytest.mark.asyncio
async def test_auditor_total_failure_uses_static_summary():
    llm = _StubLLM(RuntimeError("model unavailable"))
    result = await LLMStructureAuditor().audit(
        _project(),
        llm,
        static_violations=_static_issues(),
    )
    assert "could not finish the full organization review" not in result.summary_reason.lower()
    assert "2 item" in result.summary_reason
    assert len(result.unstructured_areas) == 2
    assert result.recommended_structure
    assert "NO FILE CONTENT" in result.recommended_structure or "no file" in result.recommended_structure.lower()
    # Primary attempt + one retry.
    assert llm.calls == 2
