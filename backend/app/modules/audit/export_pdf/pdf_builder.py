"""PDF document builder for Repository Audit & Folder Structure reports."""

from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from repoaudit.audit.plain_language import (
    dead_code_category_label,
    security_category_label,
    severity_label,
)
from repoaudit.audit.structure_models import FolderStructureAuditResult


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas for rendering running headers and dynamic 'Page X of Y' footers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_decorations(self, page_count: int):
        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#64748B"))

        doc_project = getattr(self, "project_name", "Repository")
        doc_branch = getattr(self, "branch", "main")

        # Running Header (pages 2+)
        if self._pageNumber > 1:
            self.drawString(36, 756, f"RepoAudit Architecture Report — {doc_project}")
            self.drawRightString(576, 756, f"Branch: {doc_branch}")
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(36, 748, 576, 748)

        # Running Footer (all pages)
        self.setFont("Helvetica", 8)
        self.drawString(36, 20, "RepoAudit Automated Pipeline | Branch-Wise Repository Report")
        self.drawRightString(576, 20, f"Page {self._pageNumber} of {page_count}")
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(36, 32, 576, 32)

        self.restoreState()


def make_numbered_canvas(project_name: str, branch: str):
    class CanvasWrapper(NumberedCanvas):
        pass

    CanvasWrapper.project_name = project_name
    CanvasWrapper.branch = branch
    return CanvasWrapper


def _format_code_text(text: str) -> str:
    """Escapes HTML special chars and preserves indentation/newlines for ReportLab code blocks."""
    if not text:
        return ""
    clean = text.strip()
    if clean.startswith("```"):
        lines = clean.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        clean = "\n".join(lines)
    escaped = (
        clean.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
        .replace(" ", "&nbsp;")
    )
    return escaped


def _pdf_text(text: object) -> str:
    """Escape scanner text so ReportLab Paragraph XML stays valid."""
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


class AuditPDFBuilder:
    """Generates clean, professional PDF reports for branch-wise repository audits."""

    def build_pdf(
        self,
        project_name: str,
        branch: str,
        audit_result: FolderStructureAuditResult | dict[str, Any],
        project_id: str | None = None,
        owner: str | None = None,
        repository_url: str | None = None,
        total_files: int | None = None,
        total_lines: int | None = None,
        branch_tree: str | None = None,
        wiki_summary: dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> bytes:
        """Renders comprehensive repository audit result into a binary PDF stream."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=48,
            bottomMargin=48,
        )

        styles = getSampleStyleSheet()

        # Custom design system styles
        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            textColor=colors.HexColor("#0F172A"),
        )
        subtitle_style = ParagraphStyle(
            "DocSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#64748B"),
        )
        h2_style = ParagraphStyle(
            "Heading2Custom",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=colors.HexColor("#0F172A"),
            spaceBefore=14,
            spaceAfter=6,
        )
        body_style = ParagraphStyle(
            "BodyCustom",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#334155"),
        )
        body_bold = ParagraphStyle(
            "BodyBoldCustom",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#0F172A"),
        )
        code_style = ParagraphStyle(
            "CodeTreeStyle",
            parent=styles["Normal"],
            fontName="Courier",
            fontSize=7.5,
            leading=10.5,
            textColor=colors.HexColor("#0F172A"),
            backColor=colors.HexColor("#F8FAFC"),
            borderColor=colors.HexColor("#CBD5E1"),
            borderWidth=0.8,
            borderPadding=8,
            spaceBefore=4,
            spaceAfter=8,
        )
        table_cell_style = ParagraphStyle(
            "TableCell",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#1E293B"),
        )
        table_header_style = ParagraphStyle(
            "TableHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=colors.white,
        )
        kpi_label_style = ParagraphStyle(
            "KPILabel",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor("#64748B"),
            alignment=1,  # Center
        )
        kpi_val_style = ParagraphStyle(
            "KPIVal",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=colors.HexColor("#0F172A"),
            alignment=1,  # Center
        )

        elements = []

        # Convert dict to FolderStructureAuditResult if needed
        if isinstance(audit_result, dict):
            audit_result = FolderStructureAuditResult(**audit_result)

        # Parse Dead Code Audit if present
        dead_code = getattr(audit_result, "dead_code_result", None)
        if isinstance(dead_code, dict):
            from repoaudit.audit.dead_code_models import DeadCodeAuditResult
            dead_code = DeadCodeAuditResult(**dead_code)

        security = getattr(audit_result, "security_result", None)
        if isinstance(security, dict):
            from repoaudit.audit.findings import SecurityAuditResult
            try:
                security = SecurityAuditResult(**security)
            except Exception:
                security = None

        # Calculate visual counts
        status_text = "IN GOOD SHAPE" if audit_result.is_valid else "NEEDS ATTENTION"
        status_color_hex = "#16A34A" if audit_result.is_valid else "#DC2626"

        static_violation_count = len(audit_result.static_violations)
        unstructured_count = len(audit_result.unstructured_areas)
        dead_code_findings = dead_code.findings if dead_code and getattr(dead_code, "findings", None) else []
        dead_code_count = len(dead_code_findings)
        security_findings = security.findings if security and getattr(security, "findings", None) else []
        security_count = len(security_findings)

        # ---------------------------------------------------------
        # Document Header Banner
        # ---------------------------------------------------------
        elements.append(Paragraph("Project health report", title_style))
        elements.append(
            Paragraph(
                f"A management-friendly review of organization, leftover code, and security • Branch: <b>{branch}</b>",
                subtitle_style,
            )
        )
        elements.append(Spacer(1, 8))
        elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2563EB"), spaceAfter=10))

        # ---------------------------------------------------------
        # Executive KPI Grid (540pt printable width)
        # ---------------------------------------------------------
        kpi_data = [
            [
                Paragraph("VERDICT", kpi_label_style),
                Paragraph("FOLDER ISSUES", kpi_label_style),
                Paragraph("MISPLACED ITEMS", kpi_label_style),
                Paragraph("UNUSED CODE", kpi_label_style),
            ],
            [
                Paragraph(f"<font color='{status_color_hex}'><b>{status_text}</b></font>", kpi_val_style),
                Paragraph(f"<b>{static_violation_count}</b>", kpi_val_style),
                Paragraph(f"<b>{unstructured_count}</b>", kpi_val_style),
                Paragraph(f"<b>{dead_code_count}</b>", kpi_val_style),
            ],
        ]
        kpi_table = Table(kpi_data, colWidths=[135, 135, 135, 135])
        kpi_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                    ("PADDING", (0, 0), (-1, -1), 6),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#E2E8F0")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ]
            )
        )
        elements.append(kpi_table)
        elements.append(Spacer(1, 12))

        # ---------------------------------------------------------
        # Section 1: Branch Repository Metadata & Overview
        # ---------------------------------------------------------
        elements.append(Paragraph("1. Project snapshot", h2_style))

        date_str = created_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        files_str = str(total_files) if total_files is not None else "Scanned"
        lines_str = f"{total_lines:,}" if total_lines is not None else "Scanned"
        owner_str = owner or "Account / Local"
        url_str = repository_url or f"workspace/{project_id or 'default'}"

        meta_rows = [
            [
                Paragraph(f"<b>Project Name:</b> {project_name}", body_style),
                Paragraph(f"<b>Target Branch:</b> <font color='#2563EB'><b>{branch}</b></font>", body_style),
                Paragraph(f"<b>Audit Date:</b> {date_str}", body_style),
            ],
            [
                Paragraph(f"<b>Owner / Org:</b> {owner_str}", body_style),
                Paragraph(f"<b>Total Files:</b> {files_str}", body_style),
                Paragraph(f"<b>Total LOC:</b> {lines_str}", body_style),
            ],
            [
                Paragraph(f"<b>Repository Spec:</b> {url_str}", body_style),
                Paragraph(f"<b>Scan ID:</b> {project_id or 'N/A'}", body_style),
                Paragraph(f"<b>Layout:</b> Practical folder review", body_style),
            ],
        ]
        meta_table = Table(meta_rows, colWidths=[180, 180, 180])
        meta_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
                    ("PADDING", (0, 0), (-1, -1), 5),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ]
            )
        )
        elements.append(meta_table)
        elements.append(Spacer(1, 10))

        # Audited Branch Directory Hierarchy
        if branch_tree:
            elements.append(Paragraph("<b>Audited Branch Directory Hierarchy</b>", body_bold))
            elements.append(Spacer(1, 3))
            formatted_tree = _format_code_text(branch_tree)
            elements.append(Paragraph(formatted_tree, code_style))
            elements.append(Spacer(1, 10))

        # ---------------------------------------------------------
        # Section 2: Executive Summary & Architecture Verdict
        # ---------------------------------------------------------
        elements.append(Paragraph("2. Executive summary", h2_style))
        summary_reason = audit_result.summary_reason or "The folder layout was reviewed against common project-organization practices."
        elements.append(Paragraph(summary_reason, body_style))
        elements.append(Spacer(1, 10))

        # ---------------------------------------------------------
        # Section 3: Static Folder Structure Violations
        # ---------------------------------------------------------
        elements.append(Paragraph("3. Folder issues", h2_style))
        if not audit_result.static_violations:
            elements.append(
                Paragraph(
                    "The top-level folders look like a normal, well-kept project.",
                    body_style,
                )
            )
        else:
            elements.append(
                Paragraph(
                    f"We found <b>{static_violation_count}</b> folder issue(s) on branch <b>{branch}</b>:",
                    body_style,
                )
            )
            elements.append(Spacer(1, 5))

            v_table_data = [
                [
                    Paragraph("Where", table_header_style),
                    Paragraph("Priority", table_header_style),
                    Paragraph("What's going on", table_header_style),
                    Paragraph("Suggested fix", table_header_style),
                ]
            ]

            for v in audit_result.static_violations:
                sev_color = "#DC2626" if v.severity in {"critical", "high"} else "#D97706"
                sev_text = f"<font color='{sev_color}'><b>{severity_label(v.severity)}</b></font>"
                v_table_data.append(
                    [
                        Paragraph(f"<b>{v.path}</b>", table_cell_style),
                        Paragraph(sev_text, table_cell_style),
                        Paragraph(v.description, table_cell_style),
                        Paragraph(v.suggestion or "N/A", table_cell_style),
                    ]
                )

            violations_table = Table(v_table_data, colWidths=[140, 70, 180, 150])
            violations_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                        ("PADDING", (0, 0), (-1, -1), 6),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            elements.append(violations_table)

        elements.append(Spacer(1, 12))

        # ---------------------------------------------------------
        # Section 4: Unstructured Codebase Areas (LLM Semantic Audit)
        # ---------------------------------------------------------
        elements.append(Paragraph("4. Files or folders in unexpected places", h2_style))
        if not audit_result.unstructured_areas:
            elements.append(
                Paragraph(
                    "Nothing looked dumped in the wrong place.",
                    body_style,
                )
            )
        else:
            elements.append(
                Paragraph(
                    f"We found <b>{unstructured_count}</b> item(s) that would be easier to maintain in a clearer home:",
                    body_style,
                )
            )
            elements.append(Spacer(1, 5))

            u_table_data = [
                [
                    Paragraph("Where", table_header_style),
                    Paragraph("Priority", table_header_style),
                    Paragraph("What's going on", table_header_style),
                    Paragraph("Better home", table_header_style),
                ]
            ]

            for u in audit_result.unstructured_areas:
                sev_color = "#DC2626" if u.severity in {"critical", "high"} else "#D97706"
                sev_text = f"<font color='{sev_color}'><b>{severity_label(u.severity)}</b></font>"
                u_table_data.append(
                    [
                        Paragraph(f"<b>{u.path}</b>", table_cell_style),
                        Paragraph(sev_text, table_cell_style),
                        Paragraph(u.description, table_cell_style),
                        Paragraph(u.suggestion or "N/A", table_cell_style),
                    ]
                )

            u_table = Table(u_table_data, colWidths=[140, 70, 180, 150])
            u_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                        ("PADDING", (0, 0), (-1, -1), 6),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            elements.append(u_table)

        elements.append(Spacer(1, 12))

        # ---------------------------------------------------------
        # Section 5: Recommended Target Folder Blueprint
        # ---------------------------------------------------------
        elements.append(Paragraph("5. Recommended layout", h2_style))
        elements.append(
            Paragraph(
                "A practical target for where live files should live. Unused files are left out.",
                body_style,
            )
        )
        elements.append(Spacer(1, 4))
        rec_tree_formatted = _format_code_text(audit_result.recommended_structure)
        elements.append(Paragraph(rec_tree_formatted, code_style))
        elements.append(Spacer(1, 12))

        # ---------------------------------------------------------
        # Section 6: Dead Code & Unused Dependencies Audit
        # ---------------------------------------------------------
        elements.append(Paragraph("6. Unused code and leftover packages", h2_style))
        if dead_code_findings:
            elements.append(
                Paragraph(
                    f"We found <b>{dead_code_count}</b> leftover item(s):",
                    body_style,
                )
            )
            elements.append(Spacer(1, 5))

            dc_table_data = [
                [
                    Paragraph("File", table_header_style),
                    Paragraph("What looks unused", table_header_style),
                    Paragraph("Type", table_header_style),
                    Paragraph("How sure", table_header_style),
                    Paragraph("Why it matters", table_header_style),
                ]
            ]

            for d in dead_code_findings:
                conf_color = "#DC2626" if d.confidence_level == "HIGH" else "#D97706"
                conf_text = f"<font color='{conf_color}'><b>{d.confidence_level} ({d.confidence_score}%)</b></font>"
                cat_display = dead_code_category_label(d.category)
                dc_table_data.append(
                    [
                        Paragraph(d.path, table_cell_style),
                        Paragraph(f"<b>{d.symbol_name}</b>", table_cell_style),
                        Paragraph(cat_display, table_cell_style),
                        Paragraph(conf_text, table_cell_style),
                        Paragraph(f"{d.description}<br/><i>Suggestion: {d.suggestion}</i>", table_cell_style),
                    ]
                )

            dc_table = Table(dc_table_data, colWidths=[130, 95, 95, 80, 140])
            dc_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                        ("PADDING", (0, 0), (-1, -1), 6),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            elements.append(dc_table)
        else:
            elements.append(
                Paragraph(
                    "No unused code or leftover packages stood out in this review.",
                    body_style,
                )
            )

        elements.append(Spacer(1, 12))

        # ---------------------------------------------------------
        # Section 7: Security Audit
        # ---------------------------------------------------------
        elements.append(Paragraph("7. Security health check", h2_style))
        if security_findings:
            sec_score = getattr(security, "security_score", 100)
            elements.append(
                Paragraph(
                    f"We found <b>{security_count}</b> security issue(s) "
                    f"(score: <b>{sec_score}/100</b>). Secret values are hidden.",
                    body_style,
                )
            )
            elements.append(Spacer(1, 5))
            sec_table_data = [
                [
                    Paragraph("Priority", table_header_style),
                    Paragraph("What we found", table_header_style),
                    Paragraph("Where", table_header_style),
                    Paragraph("Type", table_header_style),
                    Paragraph("Why it matters", table_header_style),
                ]
            ]
            severity_colors = {
                "critical": "#DC2626",
                "high": "#EA580C",
                "medium": "#D97706",
                "low": "#2563EB",
            }
            for item in security_findings:
                sev = getattr(item, "severity", "medium")
                color = severity_colors.get(sev, "#D97706")
                location = f"{item.path} (line {item.line})" if getattr(item, "line", 0) else item.path
                evidence = _pdf_text(getattr(item, "description", "") or getattr(item, "evidence", ""))
                suggestion = _pdf_text(getattr(item, "suggestion", ""))
                if suggestion:
                    evidence = f"{evidence}<br/><i>Next step: {suggestion}</i>"
                meaning = security_category_label(getattr(item, "category", ""))
                sec_table_data.append(
                    [
                        Paragraph(f"<font color='{color}'><b>{_pdf_text(severity_label(str(sev)))}</b></font>", table_cell_style),
                        Paragraph(_pdf_text(getattr(item, "title", "") or meaning), table_cell_style),
                        Paragraph(_pdf_text(location), table_cell_style),
                        Paragraph(_pdf_text(meaning), table_cell_style),
                        Paragraph(evidence, table_cell_style),
                    ]
                )
            sec_table = Table(sec_table_data, colWidths=[70, 110, 120, 80, 160])
            sec_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                        ("PADDING", (0, 0), (-1, -1), 6),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            elements.append(sec_table)
        else:
            skipped = []
            scanners = getattr(security, "scanners", None) or []
            for scanner in scanners:
                available = getattr(scanner, "available", True)
                if not available:
                    skipped.append(getattr(scanner, "name", "scanner"))
            skip_note = " A few automatic checks could not run, so this is a partial picture." if skipped else ""
            elements.append(
                Paragraph(
                    f"No exposed secrets, known library risks, or risky coding shortcuts were reported.{skip_note}",
                    body_style,
                )
            )

        elements.append(Spacer(1, 12))

        # ---------------------------------------------------------
        # Section 8: Branch Architecture & Wiki Documentation Summary
        # ---------------------------------------------------------
        elements.append(Paragraph("8. Documentation generated for this project", h2_style))

        wiki_pages = wiki_summary.get("pages") if isinstance(wiki_summary, dict) and wiki_summary.get("pages") else []
        if wiki_pages:
            elements.append(
                Paragraph(
                    f"Generated <b>{len(wiki_pages)}</b> architectural documentation page(s) for branch <b>{branch}</b>:",
                    body_style,
                )
            )
            elements.append(Spacer(1, 5))

            wiki_table_data = [
                [
                    Paragraph("Page ID", table_header_style),
                    Paragraph("Title", table_header_style),
                    Paragraph("Architectural Content Overview", table_header_style),
                ]
            ]

            for p in wiki_pages:
                pid = str(p.get("id") or "")
                title = str(p.get("title") or "")
                content_snippet = str(p.get("content") or "").strip().replace("\n", " ")
                if len(content_snippet) > 160:
                    content_snippet = content_snippet[:157] + "..."
                wiki_table_data.append(
                    [
                        Paragraph(f"<b>{pid}</b>", table_cell_style),
                        Paragraph(title, table_cell_style),
                        Paragraph(content_snippet or "Architecture guide and module documentation.", table_cell_style),
                    ]
                )

            w_table = Table(wiki_table_data, colWidths=[110, 150, 280])
            w_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                        ("PADDING", (0, 0), (-1, -1), 6),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            elements.append(w_table)
        else:
            elements.append(
                Paragraph(
                    "Automatic architectural wiki pages generated for core modules on this branch include Folder Structure Analysis, System Design Topology, and Code Quality Insights.",
                    body_style,
                )
            )

        # Build PDF using NumberedCanvas
        doc.build(elements, canvasmaker=make_numbered_canvas(project_name, branch))
        buffer.seek(0)
        return buffer.getvalue()
