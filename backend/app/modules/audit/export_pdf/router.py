"""FastAPI router for exporting audit reports as PDF documents."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from app.modules.audit.export_pdf.service import generate_audit_pdf

router = APIRouter(prefix="/audit", tags=["audit"])


class PDFExportRequest(BaseModel):
    """Payload for generating customized PDF audit reports."""

    project_id: str | None = Field(default=None)
    project_name: str = Field(default="Repository")
    branch: str = Field(default="main")
    audit_result: dict[str, Any] | None = Field(default=None)


@router.post("/export-pdf")
async def export_audit_pdf(payload: PDFExportRequest) -> Response:
    """Generates and downloads a PDF audit report."""
    pdf_bytes, filename = await generate_audit_pdf(
        project_id=payload.project_id,
        project_name=payload.project_name,
        branch=payload.branch,
        audit_result=payload.audit_result,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


@router.get("/export-pdf")
async def export_audit_pdf_get(
    project_id: str | None = None,
    project_name: str = "Repository",
    branch: str = "main",
) -> Response:
    """GET endpoint for downloading default PDF audit report."""
    pdf_bytes, filename = await generate_audit_pdf(
        project_id=project_id,
        project_name=project_name,
        branch=branch,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )
