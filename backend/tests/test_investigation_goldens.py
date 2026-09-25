"""Golden evaluation suite for Issue Investigator quality gates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from repoaudit.indexing.models import FileInfo, ProjectContext
from repoaudit.investigation.investigator import InvestigationEngine
from repoaudit.investigation.investigation_models import IssueReport, LiveArtifact
from repoaudit.investigation.session import merge_reports, save_local_session, load_local_session
from repoaudit.investigation.verification import PatchVerifier
from repoaudit.investigation.investigation_models import CodePatch
from repoaudit.investigation.correlation import build_correlation_leads
from repoaudit.investigation.graph import build_import_neighbors, expand_via_graph


FIXTURE = Path(__file__).parent / "fixtures" / "investigation_goldens.json"


def _golden_project() -> ProjectContext:
    files = [
        FileInfo(
            path="backend/src/app/services/auth/login/handler.py",
            size=200,
            content="from .dto import LoginDTO\ndef execute_action(payload):\n    return payload.data.username\n",
        ),
        FileInfo(
            path="backend/src/app/services/auth/login/dto.py",
            size=80,
            content="class LoginDTO:\n    username: str\n",
        ),
        FileInfo(
            path="frontend/src/app/services/auth/login/Component.tsx",
            size=120,
            content="export function LoginBadge({user}: any) { return user.token; }\n",
        ),
        FileInfo(
            path="backend/src/app/services/payment/checkout/service.py",
            size=100,
            content="async def checkout(amount):\n    pass\n",
        ),
        FileInfo(
            path="backend/src/routes/billing.py",
            size=120,
            content="@router.post('/api/billing/checkout')\ndef checkout():\n    pass\n",
        ),
        FileInfo(
            path="frontend/src/components/BillingForm.tsx",
            size=120,
            content="export function submit() { fetch('/api/billing/checkout'); }\n",
        ),
        FileInfo(
            path="frontend/src/components/meetings/MOMDetailsSection.tsx",
            size=180,
            content="export function handleNavigateToMomLine(line: string) { scrollToMomLineKey(line); }\n",
        ),
        FileInfo(
            path="frontend/src/utils/transcriptMomCoverage.ts",
            size=140,
            content="export function findMomLineForTranscriptLine() { return null; }\n",
        ),
        FileInfo(path="src/app.py", size=20, content="print('ok')\n"),
    ]
    return ProjectContext(name="GoldenRepo", root="/tmp/golden-repo", files=files)


@pytest.mark.asyncio
async def test_golden_investigation_suite_meets_acceptance_bar():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    scenarios = payload["scenarios"]
    project = _golden_project()
    engine = InvestigationEngine()

    locate_cases = 0
    locate_hits = 0
    tier_a_ok = 0
    tier_a_total = 0

    for scenario in scenarios:
        report = IssueReport(
            project_name="GoldenRepo",
            feature_name=scenario.get("feature_name") or "",
            action_name=scenario.get("action_name") or "",
            issue_description=scenario["issue_description"],
            error_log=scenario.get("error_log") or "",
            live_artifacts=[LiveArtifact(**a) for a in scenario.get("live_artifacts") or []],
        )
        result = await engine.run_investigation(report=report, project=project)

        assert result.status in scenario["expect_status"], scenario["id"]
        assert result.metrics is not None
        assert result.phases

        if scenario.get("must_clarify"):
            tier_a_total += 1
            if result.status == "PARTIAL" and (
                result.evidence.route == "clarify"
                or any(p.name == "ask_or_act" and p.status == "blocked" for p in result.phases)
                or bool(result.clarification_questions)
            ):
                tier_a_ok += 1

        expected_top3 = scenario.get("expected_top3") or []
        if expected_top3:
            locate_cases += 1
            actual = [t.path for t in result.isolated_targets[:3]]
            if any(path in actual for path in expected_top3):
                locate_hits += 1

        if scenario.get("expected_category") and not scenario.get("allow_any_category"):
            assert result.primary_root_cause is not None
            assert result.primary_root_cause.category == scenario["expected_category"], scenario["id"]

        for patch in result.code_patches:
            if result.status == "SUCCESS":
                assert patch.status == "checks_passed"

    assert locate_cases > 0
    recall = locate_hits / locate_cases
    assert recall >= payload["acceptance"]["top3_locate_recall_with_log"]
    assert tier_a_total == 0 or tier_a_ok == tier_a_total


def test_correlation_leads_from_network_artifact():
    leads = build_correlation_leads("POST /api/billing/checkout 502 correlation_id=abc-123-xyz")
    assert leads
    assert any(lead.kind == "network_to_handler" for lead in leads)
    assert any(lead.correlation_ids for lead in leads)


def test_graph_expands_handler_to_dto_neighbor():
    project = _golden_project()
    neighbors = build_import_neighbors(project)
    extras = expand_via_graph(["backend/src/app/services/auth/login/handler.py"], neighbors)
    assert "backend/src/app/services/auth/login/dto.py" in extras


def test_patch_verifier_marks_python_checks_passed(tmp_path: Path):
    target = tmp_path / "svc.py"
    target.write_text("def run(x):\n    return x\n", encoding="utf-8")
    patch = CodePatch(
        patch_id="PATCH-01",
        file_path="svc.py",
        unified_diff=(
            "--- a/svc.py\n"
            "+++ b/svc.py\n"
            "@@ -1,2 +1,3 @@\n"
            " def run(x):\n"
            "+    # guard\n"
            "     return x\n"
        ),
    )
    verified = PatchVerifier().verify(str(tmp_path), patch)
    assert verified.status == "checks_passed"


def test_embedding_index_retrieves_by_meaning():
    from repoaudit.retrieval.semantic import EmbeddingIndex

    files = [
        FileInfo(path="backend/auth/token_validation_handler.py", size=50, content="class TokenValidationHandler:\n    def validate(self): pass\n"),
        FileInfo(path="backend/billing/invoice.py", size=50, content="def create_invoice(): pass\n"),
    ]
    project = ProjectContext(name="Emb", root="/tmp/emb", files=files)
    index = EmbeddingIndex()
    index.index(project)
    hits = index.retrieve("authentication failure login token validation", top_k=3)
    assert hits
    assert "token_validation" in hits[0].file_path


def test_artifact_retention_and_analytics(tmp_path: Path):
    from datetime import UTC, datetime, timedelta

    from repoaudit.investigation.analytics import emit_investigation_event, summarize_analytics
    from repoaudit.investigation.artifacts import cleanup_expired_artifacts, save_artifacts
    from repoaudit.investigation.investigation_models import EvidenceAssessment, InvestigationResult

    report = IssueReport(project_name="X", issue_description="broken", error_log="password=secret123 token=abc")
    result = InvestigationResult(
        investigation_id="INV-ART01",
        project_name="X",
        status="PARTIAL",
        summary_verdict="partial",
        evidence=EvidenceAssessment(),
    )
    path = save_artifacts(tmp_path, investigation_id="INV-ART01", report=report, result=result, retention_days=30)
    assert Path(path).is_dir()
    redacted = (Path(path) / "report.json").read_text(encoding="utf-8")
    assert "secret123" not in redacted

    meta = Path(path) / "meta.json"
    meta.write_text(
        meta.read_text(encoding="utf-8").replace(
            '"expires_at":',
            f'"expires_at": "{(datetime.now(UTC) - timedelta(days=1)).isoformat()}", "old":',
        ),
        encoding="utf-8",
    )
    # Force expiry by rewriting meta cleanly.
    import json

    meta.write_text(
        json.dumps(
            {
                "investigation_id": "INV-ART01",
                "expires_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    removed = cleanup_expired_artifacts(tmp_path)
    assert removed >= 1

    emit_investigation_event(tmp_path, event="investigation_completed", investigation_id="INV-1", payload={"route": "clarify", "status": "PARTIAL"})
    emit_investigation_event(tmp_path, event="investigation_continued", investigation_id="INV-1", payload={})
    summary = summarize_analytics(tmp_path)
    assert summary["runs"] >= 1
    assert summary["continued"] >= 1


def test_session_merge_and_local_cache(tmp_path: Path):
    prior = IssueReport(project_name="X", issue_description="broken login", feature_name="auth", error_log="")
    incoming = IssueReport(
        project_name="X",
        issue_description="broken login",
        error_log="AttributeError in handler.py",
        live_artifacts=[LiveArtifact(kind="network", content="POST /api/login 500")],
        investigation_id="INV-TEST01",
    )
    merged = merge_reports(prior, incoming)
    assert "AttributeError" in merged.error_log
    assert merged.live_artifacts

    from repoaudit.investigation.investigation_models import EvidenceAssessment, InvestigationResult

    result = InvestigationResult(
        investigation_id="INV-TEST01",
        project_name="X",
        status="PARTIAL",
        summary_verdict="partial",
        evidence=EvidenceAssessment(),
    )
    save_local_session(
        tmp_path,
        investigation_id="INV-TEST01",
        report=merged,
        result=result,
        workspace_path=str(tmp_path),
        user_id="11111111-1111-1111-1111-111111111111",
    )
    loaded = load_local_session(
        tmp_path,
        "INV-TEST01",
        user_id="11111111-1111-1111-1111-111111111111",
    )
    assert loaded is not None
    assert loaded["investigation_id"] == "INV-TEST01"


@pytest.mark.asyncio
async def test_investigation_emits_phase_callback():
    project = _golden_project()
    report = IssueReport(
        project_name="GoldenRepo",
        feature_name="auth",
        action_name="login",
        issue_description="Login fails",
        error_log="AttributeError in backend/src/app/services/auth/login/handler.py",
    )
    seen: list[str] = []

    async def on_phase(event):
        seen.append(str(event.get("name")))

    result = await InvestigationEngine().run_investigation(report=report, project=project, on_phase=on_phase)
    assert result.phases
    assert "orient" in seen
    assert "locate" in seen
    assert "report" in seen
