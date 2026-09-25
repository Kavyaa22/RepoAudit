import pytest
from app.modules.audit.export_pdf.service import generate_audit_pdf
from repoaudit.audit.dead_code_models import DeadCodeAuditResult, DeadCodeFinding
from repoaudit.audit.findings import SecurityAuditResult, SecurityFinding
from repoaudit.audit.structure_models import FolderStructureAuditResult, FolderViolation


@pytest.mark.asyncio
async def test_pdf_export_default():
    audit_result = FolderStructureAuditResult(is_valid=True, overall_score=100, summary_reason="Default test")
    pdf_bytes, filename = await generate_audit_pdf(project_name="TestProject", branch="main", audit_result=audit_result)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b"%PDF")
    assert filename == "Audit_Report_TestProject.pdf"


@pytest.mark.asyncio
async def test_pdf_export_with_violations():
    audit_result = FolderStructureAuditResult(
        is_valid=False,
        overall_score=65,
        static_violations=[
            FolderViolation(
                path="temp_scripts",
                violation_type="disallowed_root_directory",
                severity="critical",
                description="Root directory 'temp_scripts' is disallowed.",
                suggestion="Relocate to backend or frontend.",
            )
        ],
        unstructured_areas=[
            FolderViolation(
                path="backend/src/utils/dump.py",
                violation_type="unstructured_area",
                severity="medium",
                description="Junk drawer file detected.",
                suggestion="Move to backend/src/app/services/common/utils/dump.py",
            )
        ],
        recommended_structure="repository/\n├── backend/\n└── frontend/",
        summary_reason="Folder structure audit identified 2 violations.",
        dead_code_result=DeadCodeAuditResult(
            total_findings=2,
            health_score=80,
            summary_verdict="Identified 2 dead code finding(s).",
            findings=[
                DeadCodeFinding(
                    path="backend/app/old_util.py",
                    symbol_name="unused_helper",
                    category="dead_function",
                    confidence_level="HIGH",
                    confidence_score=95,
                    description="Function 'unused_helper' has no callers across codebase.",
                    suggestion="Safely remove function.",
                ),
                DeadCodeFinding(
                    path="backend/requirements.txt",
                    symbol_name="unused_lib",
                    category="unused_dependency",
                    confidence_level="HIGH",
                    confidence_score=90,
                    description="Package 'unused-lib' is never imported.",
                    suggestion="Remove from requirements.txt.",
                ),
            ],
        ),
    )

    pdf_bytes, filename = await generate_audit_pdf(
        project_name="ViolatingProject",
        branch="feature/audit",
        audit_result=audit_result,
    )

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b"%PDF")
    assert filename == "Audit_Report_ViolatingProject.pdf"


@pytest.mark.asyncio
async def test_pdf_export_with_project_id_and_wiki_summary():
    audit_result = FolderStructureAuditResult(
        is_valid=True,
        overall_score=95,
        summary_reason="Branch architecture complies with strict modular layout.",
        recommended_structure="repository/\n├── backend/\n└── frontend/",
    )

    pdf_bytes, filename = await generate_audit_pdf(
        project_id="test-scan-123",
        project_name="CustomBranchRepo",
        branch="release/v2.0",
        audit_result=audit_result,
    )

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b"%PDF")
    assert filename == "Audit_Report_CustomBranchRepo.pdf"


@pytest.mark.asyncio
async def test_pdf_export_with_security_findings():
    audit_result = FolderStructureAuditResult(
        is_valid=True,
        overall_score=90,
        summary_reason="Structure is compliant.",
        recommended_structure="repository/\n├── backend/\n└── frontend/",
        security_result=SecurityAuditResult(
            total_findings=1,
            security_score=75,
            summary_verdict="Identified 1 security finding(s) (1 critical, 0 high).",
            findings=[
                SecurityFinding(
                    category="secret",
                    severity="critical",
                    path="config.py",
                    line=42,
                    title="AWS Access Key",
                    description="Potential secret exposed at config.py:42.",
                    suggestion="Rotate the key.",
                    scanner="gitleaks",
                    rule_id="aws-access-key",
                    evidence="Gitleaks rule `aws-access-key` matched at config.py:42.",
                )
            ],
        ),
    )
    pdf_bytes, filename = await generate_audit_pdf(
        project_name="SecureProject",
        branch="main",
        audit_result=audit_result,
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")
    assert filename == "Audit_Report_SecureProject.pdf"
