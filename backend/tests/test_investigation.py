import pytest
from repoaudit.indexing.models import FileInfo, ProjectContext
from repoaudit.investigation.hypotheses import HypothesisEngine
from repoaudit.investigation.investigator import InvestigationEngine
from repoaudit.investigation.investigation_models import CodePatch, Hypothesis, IssueReport
from repoaudit.investigation.isolator import FeaturePathIsolator
from repoaudit.investigation.keywords import extract_search_terms
from repoaudit.investigation.patch_generator import PatchGenerator
from repoaudit.retrieval.lexical import SimpleRAG


def test_extract_search_terms_expands_mom_synonyms():
    terms = extract_search_terms(
        "In generated mom the redirecting from transcript to mom is not working well",
        feature_name="mom",
    )
    assert "mom" in terms
    assert "transcript" in terms
    assert "meeting" in terms or "meetings" in terms


def test_feature_path_isolator():
    files = [
        FileInfo(path="README.md", size=100),
        FileInfo(path="backend/src/app/services/auth/login/handler.py", size=500),
        FileInfo(path="backend/src/app/services/auth/login/dto.py", size=200),
        FileInfo(path="frontend/src/app/services/auth/login/Component.tsx", size=600),
        FileInfo(path="backend/src/app/services/user/profile/view.py", size=400),
    ]
    project = ProjectContext(name="TestRepo", root="/tmp/repo", files=files)
    isolator = FeaturePathIsolator()

    report = IssueReport(
        project_name="TestRepo",
        feature_name="auth",
        action_name="login",
        issue_description="Login fails when clicking submit button with 500 error",
        error_log="AttributeError: 'NoneType' object has no attribute 'username' in backend/src/app/services/auth/login/handler.py line 42",
    )

    targets = isolator.isolate_targets(report, project)
    assert len(targets) >= 1
    assert targets[0].path == "backend/src/app/services/auth/login/handler.py"
    assert targets[0].relevance_score >= 80


def test_isolator_finds_frontend_components():
    nav_content = (
        "export function handleNavigateToMomLine(line: string) {\n"
        "  scrollToMomLineKey(findMomLineForTranscriptLine(line)?.key);\n"
        "}\n"
    )
    files = [
        FileInfo(
            path="frontend/src/components/meetings/MOMDetailsSection.tsx",
            size=len(nav_content),
            content=nav_content,
        ),
        FileInfo(path="frontend/src/utils/transcriptMomCoverage.ts", size=100, content="export function findMomLineForTranscriptLine() {}\n"),
    ]
    project = ProjectContext(name="TestRepo", root="/tmp/repo", files=files)
    isolator = FeaturePathIsolator()

    report = IssueReport(
        project_name="TestRepo",
        feature_name="mom",
        issue_description="Navigation redirect after clicking green transcript line is not working properly",
    )

    rag = SimpleRAG()
    rag.index(project)
    chunks = rag.retrieve(report.issue_description + " mom transcript scroll navigate", top_k=5)
    targets = isolator.isolate_targets(report, project, rag_chunks=chunks)

    assert len(targets) >= 1
    assert any("MOMDetailsSection" in t.path or "transcriptMomCoverage" in t.path for t in targets)


def test_hypothesis_engine_navigation():
    report = IssueReport(
        project_name="TestRepo",
        issue_description="Redirect from transcript to mom panel scroll is broken",
    )
    engine = HypothesisEngine()
    hypotheses = engine.generate_hypotheses(report, ProjectContext(name="TestRepo", root="/tmp", files=[]), [])

    assert hypotheses[0].category == "navigation_mismatch"


def test_hypothesis_engine():
    files = [
        FileInfo(path="backend/src/app/services/auth/login/handler.py", size=500),
    ]
    project = ProjectContext(name="TestRepo", root="/tmp/repo", files=files)

    report = IssueReport(
        project_name="TestRepo",
        issue_description="Login fails with TypeError or AttributeError",
        error_log="TypeError: cannot read property 'token' of undefined",
    )

    isolator = FeaturePathIsolator()
    targets = isolator.isolate_targets(report, project)

    hypo_engine = HypothesisEngine()
    hypotheses = hypo_engine.generate_hypotheses(report, project, targets)

    assert len(hypotheses) >= 1
    primary = hypotheses[0]
    assert primary.category == "null_pointer"
    assert primary.confidence_level in ("HIGH", "MEDIUM")


@pytest.mark.asyncio
async def test_patch_generator_no_fake_diff_without_llm():
    files = [
        FileInfo(
            path="backend/src/app/services/auth/login/handler.py",
            size=50,
            content="def execute_action(payload):\n    return payload.data.value\n",
        ),
    ]
    project = ProjectContext(name="TestRepo", root="/tmp/repo", files=files)

    report = IssueReport(
        project_name="TestRepo",
        feature_name="auth",
        action_name="login",
        issue_description="Login throws NoneType error",
    )

    isolator = FeaturePathIsolator()
    targets = isolator.isolate_targets(report, project)

    hypo_engine = HypothesisEngine()
    hypotheses = hypo_engine.generate_hypotheses(report, project, targets)

    patch_gen = PatchGenerator()
    remediation, patches, llm_generated = await patch_gen.generate_patches_and_remediation(
        report, project, hypotheses[0], targets, llm=None
    )

    assert len(remediation) > 0
    assert patches == []
    assert llm_generated is False


@pytest.mark.asyncio
async def test_patch_generator_no_targets_returns_empty_patches():
    project = ProjectContext(name="TestRepo", root="/tmp/repo", files=[])

    report = IssueReport(
        project_name="TestRepo",
        issue_description="Something vague broke",
    )

    hypo = Hypothesis(
        hypothesis_id="HYP-00",
        category="unhandled_exception",
        title="Unverified Logic Failure",
        description="Unknown",
        likelihood_score=45,
        confidence_level="LOW",
    )

    patch_gen = PatchGenerator()
    remediation, patches, llm_generated = await patch_gen.generate_patches_and_remediation(
        report, project, hypo, [], llm=None
    )

    assert patches == []
    assert llm_generated is False
    assert any("No code patch generated" in step for step in remediation)


@pytest.mark.asyncio
async def test_patch_generator_navigation_remediation():
    files = [
        FileInfo(
            path="frontend/src/app/services/wiki/navigation.ts",
            size=200,
            content="export function scrollToLine() {}\n",
        ),
    ]
    project = ProjectContext(name="TestRepo", root="/tmp/repo", files=files)

    report = IssueReport(
        project_name="TestRepo",
        issue_description="Navigation redirect after clicking green line is not working properly",
    )

    isolator = FeaturePathIsolator()
    targets = isolator.isolate_targets(report, project)

    hypo = Hypothesis(
        hypothesis_id="HYP-04",
        category="navigation_mismatch",
        title="Cross-Panel Navigation Failure",
        description="Scroll keys mismatch",
        likelihood_score=88,
        confidence_level="HIGH",
    )

    patch_gen = PatchGenerator()
    remediation, patches, _ = await patch_gen.generate_patches_and_remediation(
        report, project, hypo, targets, llm=None
    )

    assert len(remediation) > 0
    assert patches == []
    assert any("navigation" in step.lower() or "scroll" in step.lower() for step in remediation)


@pytest.mark.asyncio
async def test_investigation_engine_full():
    files = [
        FileInfo(
            path="backend/src/app/services/payment/checkout/service.py",
            size=300,
            content="async def checkout(amount):\n    pass\n",
        ),
    ]
    project = ProjectContext(name="TestRepo", root="/tmp/repo", files=files)

    report = IssueReport(
        project_name="TestRepo",
        feature_name="payment",
        action_name="checkout",
        issue_description="Checkout action fails with missing positional argument",
        error_log="TypeError: missing required positional argument 'amount'",
    )

    engine = InvestigationEngine()
    result = await engine.run_investigation(report=report, project=project)

    assert result.status in ("SUCCESS", "PARTIAL")
    assert result.primary_root_cause is not None
    assert len(result.isolated_targets) >= 1
    assert len(result.remediation_steps) >= 1
    lowered = result.summary_verdict.lower()
    assert "tier " not in lowered
    assert "inv-" not in lowered
    assert "confidence gate" not in lowered
    assert "pipeline" not in lowered

from repoaudit.investigation.evidence import assess_evidence


def test_evidence_assessment_routes_tiers_and_gaps():
    weak = assess_evidence(IssueReport(project_name="TestRepo", issue_description="It is broken"))
    assert weak.tier == "A"
    assert weak.route == "clarify"
    assert weak.gaps

    detailed = assess_evidence(
        IssueReport(
            project_name="TestRepo",
            issue_description="Checkout succeeds, but the order never shows up in the dashboard after payment.",
        )
    )
    assert detailed.route in ("locate", "full")
    assert "tier a" not in (detailed.guidance or "").lower()

    strong = assess_evidence(
        IssueReport(
            project_name="TestRepo",
            feature_name="billing",
            action_name="submit",
            issue_description="Submitting billing form returns a server error instead of saving",
            error_log="POST /api/billing/checkout 500 TypeError in backend/src/routes/billing.py:22",
        )
    )
    assert strong.tier in ("C", "D")
    assert strong.route == "full"
    assert strong.score >= 70


def test_isolator_routes_failed_url_to_handler():
    files = [
        FileInfo(path="backend/src/routes/billing.py", size=100, content="@router.post('/api/billing/checkout')\ndef checkout(): pass"),
        FileInfo(path="frontend/src/components/BillingForm.tsx", size=100, content="fetch('/api/billing/checkout')"),
    ]
    project = ProjectContext(name="TestRepo", root="/tmp/repo", files=files)
    report = IssueReport(
        project_name="TestRepo",
        feature_name="billing",
        action_name="submit",
        issue_description="Checkout submit fails",
        error_log="POST /api/billing/checkout 500",
    )

    targets = FeaturePathIsolator().isolate_targets(report, project)

    assert targets
    assert targets[0].path == "backend/src/routes/billing.py"
    assert "failing route" in targets[0].matched_reason.lower()


@pytest.mark.asyncio
async def test_investigation_engine_vague_report_stays_partial():
    project = ProjectContext(name="TestRepo", root="/tmp/repo", files=[FileInfo(path="src/app.py", size=10, content="print('ok')")])
    report = IssueReport(project_name="TestRepo", issue_description="Something is not working")

    result = await InvestigationEngine().run_investigation(report=report, project=project)

    assert result.status == "PARTIAL"
    assert result.evidence.tier == "A"
    assert result.code_patches == []
    assert any(phase.name == "ask_or_act" and phase.status == "blocked" for phase in result.phases)


def test_code_patch_has_verification_status_defaults():
    patch = CodePatch(patch_id="PATCH-01", file_path="src/app.py")
    assert patch.status == "draft"
    assert "not verified" in patch.verification_summary.lower()

