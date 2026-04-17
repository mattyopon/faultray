# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""DORA Audit Report PDF Renderer.

Renders the structured dict returned by ``DORAuditReportGenerator.export_pdf_data()``
into a regulator-ready, audit-quality PDF using fpdf2.

Usage::

    from faultray.reporter.dora_pdf_report import DORAuditPDFRenderer
    renderer = DORAuditPDFRenderer(pdf_data)
    renderer.render(Path("dora-report.pdf"))
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# fpdf2 is an optional dependency.  Import lazily so that the rest of
# FaultRay works when it is not installed.
try:
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    _FPDF2_AVAILABLE = True
except ImportError:  # pragma: no cover
    _FPDF2_AVAILABLE = False
    # Provide a stub base class so the subclass definition below
    # does not raise NameError when fpdf2 is not installed.
    FPDF = object  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Colour palette (RGB tuples)
# ---------------------------------------------------------------------------

_COLOR_PRIMARY = (26, 35, 126)      # #1a237e - deep navy
_COLOR_SECONDARY = (40, 53, 147)    # #283593
_COLOR_SUCCESS = (40, 167, 69)      # #28a745
_COLOR_WARNING = (255, 193, 7)      # #ffc107
_COLOR_DANGER = (220, 53, 69)       # #dc3545
_COLOR_GREY = (108, 117, 125)       # #6c757d
_COLOR_LIGHT = (245, 245, 245)      # #f5f5f5
_COLOR_WHITE = (255, 255, 255)
_COLOR_TEXT = (51, 51, 51)          # #333

_STATUS_COLORS: dict[str, tuple[int, int, int]] = {
    "compliant": _COLOR_SUCCESS,
    "partially_compliant": _COLOR_WARNING,
    "non_compliant": _COLOR_DANGER,
    "not_applicable": _COLOR_GREY,
    "green": _COLOR_SUCCESS,
    "amber": _COLOR_WARNING,
    "red": _COLOR_DANGER,
    "grey": _COLOR_GREY,
}

_SEVERITY_COLORS: dict[str, tuple[int, int, int]] = {
    "critical": _COLOR_DANGER,
    "high": (253, 126, 20),          # #fd7e14 orange
    "medium": _COLOR_WARNING,
    "low": _COLOR_SUCCESS,
}

# ---------------------------------------------------------------------------
# DORA glossary and methodology text
# ---------------------------------------------------------------------------

_GLOSSARY = [
    (
        "DORA",
        "Digital Operational Resilience Act - EU Regulation 2022/2554 on digital "
        "operational resilience for the financial sector.",
    ),
    ("ICT", "Information and Communication Technology."),
    (
        "TLPT",
        "Threat-Led Penetration Testing - advanced adversarial testing based on real "
        "threat intelligence (Article 25).",
    ),
    (
        "BIA",
        "Business Impact Analysis - systematic process for determining the potential "
        "impacts of disruptions.",
    ),
    (
        "RTO",
        "Recovery Time Objective - the targeted duration of time within which a "
        "process must be restored.",
    ),
    (
        "RPO",
        "Recovery Point Objective - the maximum acceptable amount of data loss "
        "measured in time.",
    ),
    (
        "Gap Analysis",
        "Assessment of the difference between the current compliance posture and "
        "required standards.",
    ),
    (
        "Evidence Record",
        "Documented test result demonstrating the operational resilience of a specific control.",
    ),
    (
        "Register of Information",
        "Article 28 mandated register of all ICT third-party service providers.",
    ),
    (
        "Concentration Risk",
        "Risk arising from excessive reliance on a single ICT third-party provider.",
    ),
    (
        "Control ID",
        "Unique identifier for a specific DORA compliance control within FaultRay's test framework.",
    ),
]

_METHODOLOGY_TEXT = (
    "FaultRay evaluates DORA compliance through a multi-layer evidence collection framework. "
    "Infrastructure graphs are analysed against 52 control points across DORA Articles 5-30 and 45. "
    "Each control is assessed by one or more of the following test types: "
    "scenario-based chaos simulation, configuration audit, dependency graph analysis, "
    "third-party risk scoring, and continuous monitoring telemetry.\n\n"
    "Risk scores are calculated on a 0-10 scale where 0 represents full compliance and 10 represents "
    "critical non-compliance. Scores above 7.0 trigger automatic remediation items with Critical severity.\n\n"
    "Evidence records are generated at test execution time, timestamped, and optionally signed with "
    "HMAC-SHA256 to form a tamper-evident audit chain. The chain hash is included in each exported "
    "package to support regulatory integrity verification.\n\n"
    "This report covers Article 24 scenario-based testing. Article 25 TLPT requires live production "
    "testing by qualified external testers and is outside the scope of automated FaultRay assessment."
)

_ARTICLE_LABELS: dict[str, str] = {
    "article_5": "Art. 5 - ICT Risk Mgmt Framework",
    "article_6": "Art. 6 - ICT Risk Mgmt Governance",
    "article_7": "Art. 7 - ICT Systems & Tools",
    "article_8": "Art. 8 - Identification",
    "article_9": "Art. 9 - Protection & Prevention",
    "article_10": "Art. 10 - Detection",
    "article_11": "Art. 11 - Response & Recovery",
    "article_12": "Art. 12 - Backup & Recovery",
    "article_13": "Art. 13 - Learning & Evolving",
    "article_14": "Art. 14 - Communication",
    "article_15": "Art. 15 - Simplified ICT Risk Mgmt",
    "article_16": "Art. 16 - RTS Harmonisation",
    "article_17": "Art. 17 - Incident Mgmt Process",
    "article_18": "Art. 18 - Incident Classification",
    "article_19": "Art. 19 - Incident Reporting",
    "article_20": "Art. 20 - Reporting Templates",
    "article_21": "Art. 21 - Centralised Reporting",
    "article_22": "Art. 22 - Supervisory Feedback",
    "article_23": "Art. 23 - Payment Incidents",
    "article_24": "Art. 24 - Testing Programme",
    "article_25": "Art. 25 - TLPT",
    "article_26": "Art. 26 - Tester Requirements",
    "article_27": "Art. 27 - Mutual Recognition",
    "article_28": "Art. 28 - Third-Party Risk",
    "article_29": "Art. 29 - Concentration Risk",
    "article_30": "Art. 30 - Contractual Provisions",
    "article_45": "Art. 45 - Info Sharing",
}


# ---------------------------------------------------------------------------
# Internal FPDF subclass with header / footer
# ---------------------------------------------------------------------------


class _DORAuditFPDF(FPDF):  # type: ignore[misc]
    """fpdf2 subclass with custom header and footer for audit reports."""

    def __init__(self, reporting_entity: str, report_id: str, generated_at: str) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.reporting_entity = reporting_entity[:50]
        self.report_id = report_id
        self.generated_at = generated_at[:19].replace("T", " ") + " UTC"
        self.set_margins(left=15, top=20, right=15)
        self.set_auto_page_break(auto=True, margin=20)

    def header(self) -> None:
        # Skip header on the cover page (page 1)
        if self.page == 1:
            return
        self.set_font("Helvetica", "B", 7)
        self.set_text_color(*_COLOR_PRIMARY)
        col_w = (self.w - 30) / 3
        self.set_x(15)
        self.cell(col_w, 6, self.reporting_entity, border=0, align="L",
                  new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.cell(col_w, 6, "DORA Compliance Audit Report", border=0, align="C",
                  new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.cell(col_w, 6, "CONFIDENTIAL", border=0, align="R",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*_COLOR_PRIMARY)
        self.set_line_width(0.3)
        self.line(15, self.get_y(), self.w - 15, self.get_y())
        self.ln(2)

    def footer(self) -> None:
        if self.page == 1:
            return
        self.set_y(-15)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*_COLOR_GREY)
        col_w = (self.w - 30) / 3
        self.set_x(15)
        self.cell(col_w, 5, f"Page {self.page_no()}/{{nb}}", border=0, align="L",
                  new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.cell(col_w, 5, self.generated_at, border=0, align="C",
                  new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.cell(col_w, 5, f"Report ID: {self.report_id[:24]}", border=0, align="R",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)


# ---------------------------------------------------------------------------
# DORAuditPDFRenderer
# ---------------------------------------------------------------------------


class DORAuditPDFRenderer:
    """Renders a DORA audit report PDF from structured export data.

    Args:
        pdf_data: Dict returned by ``DORAuditReportGenerator.export_pdf_data()``.
        config: Optional rendering configuration overrides (currently unused).
    """

    def __init__(self, pdf_data: dict[str, Any], config: dict[str, Any] | None = None) -> None:
        if not _FPDF2_AVAILABLE:
            raise ImportError(
                "fpdf2 is required to generate PDF reports. "
                "Install it with: pip install 'faultray[pdf]'"
            )
        self._data = pdf_data
        self._config = config or {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(self, output_path: Path) -> Path:
        """Render the PDF to *output_path* and return the resolved path.

        Args:
            output_path: Destination ``.pdf`` file path.

        Returns:
            The resolved absolute path of the written PDF.
        """
        meta = self._data.get("meta", {})
        exec_sum = self._data.get("executive_summary", {})

        reporting_entity = self._safe(meta.get("reporting_entity", "Financial Institution"))
        report_id = self._safe(meta.get("report_id", "UNKNOWN"))
        generated_at = meta.get("generated_at", "")

        pdf = _DORAuditFPDF(
            reporting_entity=reporting_entity,
            report_id=report_id,
            generated_at=generated_at,
        )
        pdf.alias_nb_pages()

        # Collect TOC link targets — filled after sections are created
        toc_links: list[tuple[Any, str]] = []

        # Cover page (page 1, no header/footer)
        pdf.add_page()
        self._render_cover(pdf, meta, exec_sum)

        # Table of Contents placeholder (page 2)
        toc_page_link = pdf.add_link()
        pdf.add_page()
        pdf.set_link(toc_page_link)
        self._section_heading(pdf, "Table of Contents")
        toc_section_entries = [
            "1. Executive Summary",
            "2. Gap Analysis",
            "3. Evidence Records",
            "4. Remediation Plan",
            "5. Register of Information",
            "6. Audit Trail",
            "Appendix A: Glossary",
            "Appendix B: Methodology",
        ]
        toc_row_links: list[Any] = []
        for entry in toc_section_entries:
            link = pdf.add_link()
            toc_row_links.append(link)
            pdf.set_font("Helvetica", "", 11)
            pdf.set_text_color(*_COLOR_PRIMARY)
            pdf.set_x(15)
            pdf.cell(0, 8, entry, border="B", align="L", link=link,
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Section: Executive Summary
        exec_link = pdf.add_link()
        toc_links.append((exec_link, "1. Executive Summary"))
        pdf.add_page()
        pdf.set_link(exec_link)
        self._render_executive_summary(pdf, exec_sum, meta)

        # Section: Gap Analysis
        gap_link = pdf.add_link()
        toc_links.append((gap_link, "2. Gap Analysis"))
        pdf.add_page()
        pdf.set_link(gap_link)
        self._render_gap_analysis(pdf, self._data.get("gap_analysis_table", []))

        # Section: Evidence Records
        ev_link = pdf.add_link()
        toc_links.append((ev_link, "3. Evidence Records"))
        pdf.add_page()
        pdf.set_link(ev_link)
        self._render_evidence_records(pdf, self._data.get("evidence_table", []))

        # Section: Remediation Plan
        rem_link = pdf.add_link()
        toc_links.append((rem_link, "4. Remediation Plan"))
        pdf.add_page()
        pdf.set_link(rem_link)
        self._render_remediation_plan(pdf, self._data.get("remediation_plan", []))

        # Section: Register of Information
        reg_link = pdf.add_link()
        toc_links.append((reg_link, "5. Register of Information"))
        pdf.add_page()
        pdf.set_link(reg_link)
        self._render_register_of_information(pdf, self._data.get("register_of_information", []))

        # Section: Audit Trail
        trail_link = pdf.add_link()
        toc_links.append((trail_link, "6. Audit Trail"))
        pdf.add_page()
        pdf.set_link(trail_link)
        self._render_audit_trail(pdf, meta)

        # Appendix A: Glossary
        gloss_link = pdf.add_link()
        toc_links.append((gloss_link, "Appendix A: Glossary"))
        pdf.add_page()
        pdf.set_link(gloss_link)
        self._render_glossary(pdf)

        # Appendix B: Methodology
        method_link = pdf.add_link()
        toc_links.append((method_link, "Appendix B: Methodology"))
        pdf.add_page()
        pdf.set_link(method_link)
        self._render_methodology(pdf)

        # Patch TOC row links to point to actual section pages
        for row_link, (section_link, _title) in zip(toc_row_links, toc_links):
            info = pdf.links[section_link]
            pdf.set_link(row_link, y=info.top, page=info.page_number)

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pdf.output(str(output_path))
        return output_path.resolve()

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe(text: str) -> str:
        """Replace characters outside latin-1 with ASCII approximations.

        fpdf2's built-in Helvetica uses latin-1 encoding.  Data arriving from
        the infrastructure model may contain Unicode characters (en-dash, smart
        quotes, etc.) that would raise ``FPDFUnicodeEncodingException``.  This
        helper normalises the most common offenders before they reach fpdf2.
        """
        replacements = {
            "\u2014": "-",    # em dash
            "\u2013": "-",    # en dash
            "\u2018": "'",    # left single quote
            "\u2019": "'",    # right single quote
            "\u201c": '"',    # left double quote
            "\u201d": '"',    # right double quote
            "\u2026": "...",  # ellipsis
            "\u00b7": ".",    # middle dot
        }
        for char, replacement in replacements.items():
            text = text.replace(char, replacement)
        return text.encode("latin-1", errors="replace").decode("latin-1")

    # ------------------------------------------------------------------
    # Rendering utilities
    # ------------------------------------------------------------------

    def _section_heading(
        self,
        pdf: _DORAuditFPDF,
        title: str,
        level: int = 1,
    ) -> None:
        """Render a section heading with a coloured underline."""
        if level == 1:
            pdf.set_font("Helvetica", "B", 14)
            pdf.set_text_color(*_COLOR_PRIMARY)
            pdf.cell(0, 10, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_draw_color(*_COLOR_PRIMARY)
            pdf.set_line_width(0.5)
            pdf.line(15, pdf.get_y(), pdf.w - 15, pdf.get_y())
            pdf.ln(3)
        else:
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(*_COLOR_SECONDARY)
            pdf.cell(0, 8, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
        pdf.set_text_color(*_COLOR_TEXT)

    def _body_text(self, pdf: _DORAuditFPDF, text: str) -> None:
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*_COLOR_TEXT)
        pdf.multi_cell(0, 5, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)

    def _status_label(self, status: str) -> str:
        labels = {
            "compliant": "COMPLIANT",
            "partially_compliant": "PARTIAL",
            "non_compliant": "NON-COMPLIANT",
            "not_applicable": "N/A",
        }
        return labels.get(status, status.upper())

    def _color_for_status(self, status: str) -> tuple[int, int, int]:
        return _STATUS_COLORS.get(status, _COLOR_GREY)

    def _color_for_severity(self, severity: str) -> tuple[int, int, int]:
        return _SEVERITY_COLORS.get(severity.lower(), _COLOR_GREY)

    def _metric_box(
        self,
        pdf: _DORAuditFPDF,
        x: float,
        y: float,
        w: float,
        h: float,
        value: str,
        label: str,
        color: tuple[int, int, int],
    ) -> None:
        pdf.set_fill_color(*_COLOR_LIGHT)
        pdf.rect(x, y, w, h, style="F")
        pdf.set_font("Helvetica", "B", 18)
        pdf.set_text_color(*color)
        pdf.set_xy(x, y + 4)
        pdf.cell(w, 10, value, align="C", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*_COLOR_GREY)
        pdf.set_xy(x, y + 15)
        pdf.cell(w, 5, label, align="C", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_text_color(*_COLOR_TEXT)

    def _table_header(
        self,
        pdf: _DORAuditFPDF,
        columns: list[tuple[str, float]],
    ) -> None:
        pdf.set_fill_color(*_COLOR_PRIMARY)
        pdf.set_text_color(*_COLOR_WHITE)
        pdf.set_font("Helvetica", "B", 8)
        for label, w in columns:
            pdf.cell(w, 6, label, border=1, align="C", fill=True,
                     new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.ln(6)
        pdf.set_text_color(*_COLOR_TEXT)

    # ------------------------------------------------------------------
    # Cover page
    # ------------------------------------------------------------------

    def _render_cover(
        self,
        pdf: _DORAuditFPDF,
        meta: dict[str, Any],
        exec_sum: dict[str, Any],
    ) -> None:
        reporting_entity = self._safe(meta.get("reporting_entity", "Financial Institution"))
        report_id = self._safe(meta.get("report_id", "UNKNOWN"))
        generated_at = meta.get("generated_at", "")[:19].replace("T", " ") + " UTC"
        report_period = self._safe(meta.get("report_period", ""))
        faultray_version = self._safe(meta.get("faultray_version", ""))
        overall_status = meta.get("overall_status", exec_sum.get("overall_status", ""))
        compliance_rate = exec_sum.get("compliance_rate_percent", 0.0)

        # Dark background banner
        pdf.set_fill_color(*_COLOR_PRIMARY)
        pdf.rect(0, 0, pdf.w, 90, style="F")

        # FaultRay logo text
        pdf.set_xy(15, 18)
        pdf.set_font("Helvetica", "B", 22)
        pdf.set_text_color(*_COLOR_WHITE)
        pdf.cell(0, 12, "FaultRay", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_x(15)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(180, 190, 220)
        pdf.cell(0, 6, "Digital Operational Resilience Platform", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Main title
        pdf.set_xy(15, 48)
        pdf.set_font("Helvetica", "B", 18)
        pdf.set_text_color(*_COLOR_WHITE)
        pdf.cell(0, 10, "DORA Compliance Audit Report", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_x(15)
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(200, 210, 240)
        pdf.cell(
            0, 7,
            "EU Regulation 2022/2554 - Digital Operational Resilience Act",
            new_x=XPos.LMARGIN, new_y=YPos.NEXT,
        )

        # CONFIDENTIAL badge
        pdf.set_fill_color(*_COLOR_DANGER)
        pdf.rect(pdf.w - 65, 10, 50, 10, style="F")
        pdf.set_xy(pdf.w - 65, 12)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*_COLOR_WHITE)
        pdf.cell(50, 6, "CONFIDENTIAL", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Entity and metadata
        pdf.set_text_color(*_COLOR_TEXT)
        pdf.set_xy(15, 98)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(*_COLOR_PRIMARY)
        pdf.cell(0, 8, reporting_entity, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_x(15)
        pdf.set_font("Helvetica", "", 9)
        for label, value in [
            ("Report ID", report_id),
            ("Generated", generated_at),
            ("Report Period", report_period),
            ("FaultRay Version", faultray_version),
        ]:
            if value:
                pdf.set_text_color(*_COLOR_GREY)
                pdf.cell(40, 6, f"{label}:", new_x=XPos.RIGHT, new_y=YPos.TOP)
                pdf.set_text_color(*_COLOR_TEXT)
                pdf.cell(0, 6, str(value), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.set_x(15)

        # Status summary box
        status_color = self._color_for_status(exec_sum.get("overall_status_color", overall_status))
        pdf.set_xy(15, 155)
        pdf.set_fill_color(*status_color)
        pdf.rect(15, 155, pdf.w - 30, 22, style="F")
        pdf.set_xy(15, 158)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*_COLOR_WHITE)
        status_label = self._status_label(exec_sum.get("overall_status", ""))
        pdf.cell(
            pdf.w - 30, 7,
            f"Overall Status: {status_label}   |   Compliance Rate: {compliance_rate:.1f}%",
            align="C",
            new_x=XPos.LMARGIN, new_y=YPos.NEXT,
        )
        pdf.set_x(15)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(
            pdf.w - 30, 7,
            (
                f"Total Controls: {exec_sum.get('total_controls', 0)}  "
                f"| Compliant: {exec_sum.get('compliant', 0)}  "
                f"| Non-Compliant: {exec_sum.get('non_compliant', 0)}  "
                f"| Partial: {exec_sum.get('partially_compliant', 0)}"
            ),
            align="C",
            new_x=XPos.LMARGIN, new_y=YPos.NEXT,
        )

        # TLPT disclaimer
        pdf.set_xy(15, 220)
        pdf.set_fill_color(255, 243, 205)
        pdf.rect(15, 220, pdf.w - 30, 18, style="F")
        pdf.set_xy(17, 222)
        pdf.set_font("Helvetica", "I", 7)
        pdf.set_text_color(133, 100, 4)
        disclaimer = self._safe(meta.get("tlpt_disclaimer", ""))
        pdf.multi_cell(pdf.w - 34, 4, disclaimer, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(*_COLOR_TEXT)

    # ------------------------------------------------------------------
    # Executive Summary
    # ------------------------------------------------------------------

    def _render_executive_summary(
        self,
        pdf: _DORAuditFPDF,
        exec_sum: dict[str, Any],
        meta: dict[str, Any],
    ) -> None:
        self._section_heading(pdf, "1. Executive Summary")

        overall_status = exec_sum.get("overall_status", "")
        overall_status_color = exec_sum.get("overall_status_color", "grey")
        compliance_rate = exec_sum.get("compliance_rate_percent", 0.0)
        total = exec_sum.get("total_controls", 0)
        compliant = exec_sum.get("compliant", 0)
        non_compliant = exec_sum.get("non_compliant", 0)
        partial = exec_sum.get("partially_compliant", 0)
        na = exec_sum.get("not_applicable", 0)

        # Overall status
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(52, 7, "Overall Compliance Status:", new_x=XPos.RIGHT, new_y=YPos.TOP)
        status_color = self._color_for_status(overall_status_color)
        badge_w = 42.0
        x_badge, y_badge = pdf.get_x(), pdf.get_y()
        pdf.set_fill_color(*status_color)
        pdf.rect(x_badge, y_badge, badge_w, 7, style="F")
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*_COLOR_WHITE)
        pdf.set_xy(x_badge, y_badge)
        pdf.cell(badge_w, 7, self._status_label(overall_status), align="C",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(*_COLOR_TEXT)
        pdf.ln(2)

        pdf.set_font("Helvetica", "", 10)
        pdf.cell(52, 7, "Compliance Rate:", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 7, f"{compliance_rate:.1f}%", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(4)

        # Metric boxes
        box_w = (pdf.w - 30) / 5
        box_h = 26.0
        y0 = pdf.get_y()
        metrics = [
            (str(total), "Total Controls", _COLOR_PRIMARY),
            (str(compliant), "Compliant", _COLOR_SUCCESS),
            (str(partial), "Partial", _COLOR_WARNING),
            (str(non_compliant), "Non-Compliant", _COLOR_DANGER),
            (str(na), "Not Applicable", _COLOR_GREY),
        ]
        for i, (val, label, color) in enumerate(metrics):
            self._metric_box(pdf, 15.0 + i * box_w, y0, box_w - 2, box_h, val, label, color)
        pdf.set_y(y0 + box_h + 6)

        # TLPT disclaimer
        disclaimer = self._safe(meta.get("tlpt_disclaimer", ""))
        y_disc = pdf.get_y()
        disc_h = 14.0
        pdf.set_fill_color(255, 243, 205)
        pdf.rect(15, y_disc, pdf.w - 30, disc_h, style="F")
        pdf.set_xy(17, y_disc + 2)
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(133, 100, 4)
        pdf.multi_cell(pdf.w - 34, 4, disclaimer, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(*_COLOR_TEXT)
        pdf.ln(4)

        # Article-level status table
        self._section_heading(pdf, "Article-Level Compliance Status", level=2)
        col_article = 120.0
        col_status = pdf.w - 30 - col_article
        self._table_header(pdf, [("Article", col_article), ("Status", col_status)])

        article_statuses = exec_sum.get("article_statuses", {})
        for i, (key, info) in enumerate(article_statuses.items()):
            label = _ARTICLE_LABELS.get(key, key)
            if isinstance(info, dict):
                status_val = str(info.get("status", ""))
                color_key: str = str(info.get("color", "grey"))
            else:
                status_val = str(info)
                color_key = "grey"

            shaded = (i % 2 == 0)
            fill_bg = _COLOR_LIGHT if shaded else _COLOR_WHITE
            y_before = pdf.get_y()

            if y_before + 7 > pdf.h - pdf.b_margin:
                pdf.add_page()
                self._table_header(pdf, [("Article", col_article), ("Status", col_status)])
                y_before = pdf.get_y()

            pdf.set_fill_color(*fill_bg)
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(*_COLOR_TEXT)
            pdf.set_xy(15, y_before)
            pdf.cell(col_article, 6, label, border=1, fill=True,
                     new_x=XPos.RIGHT, new_y=YPos.TOP)

            badge_color = self._color_for_status(color_key)
            pdf.set_fill_color(*badge_color)
            pdf.set_text_color(*_COLOR_WHITE)
            pdf.set_font("Helvetica", "B", 7)
            pdf.set_xy(15 + col_article, y_before)
            pdf.cell(col_status, 6, self._status_label(status_val),
                     border=1, fill=True, align="C",
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(*_COLOR_TEXT)

    # ------------------------------------------------------------------
    # Gap Analysis
    # ------------------------------------------------------------------

    def _render_gap_analysis(
        self,
        pdf: _DORAuditFPDF,
        gap_rows: list[dict[str, Any]],
    ) -> None:
        self._section_heading(pdf, "2. Gap Analysis")
        self._body_text(
            pdf,
            "The following table presents all identified compliance gaps across DORA controls, "
            "grouped by risk severity. Each entry includes the key gap identified and the primary "
            "recommendation for remediation.",
        )

        if not gap_rows:
            self._body_text(pdf, "No gap analysis data available.")
            return

        col_widths = [22.0, 26.0, 16.0, 62.0, 54.0]
        cols = list(zip(
            ["Control ID", "Status", "Risk Score", "Key Gap", "Recommendation"],
            col_widths,
        ))
        self._table_header(pdf, cols)

        for i, row in enumerate(gap_rows):
            control_id = self._safe(str(row.get("control_id", "")))
            status = self._safe(str(row.get("status", "")))
            risk_score = float(row.get("risk_score", 0.0))
            gaps = row.get("gaps", [])
            recs = row.get("recommendations", [])
            key_gap = self._safe(gaps[0] if gaps else "-")
            key_rec = self._safe(recs[0] if recs else "-")
            key_gap = key_gap[:90]
            key_rec = key_rec[:80]

            shaded = (i % 2 == 0)
            fill_bg = _COLOR_LIGHT if shaded else _COLOR_WHITE
            y_before = pdf.get_y()

            if y_before + 12 > pdf.h - pdf.b_margin:
                pdf.add_page()
                self._table_header(pdf, cols)
                y_before = pdf.get_y()

            x_start = 15.0

            # Control ID
            pdf.set_fill_color(*fill_bg)
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(*_COLOR_TEXT)
            pdf.set_xy(x_start, y_before)
            pdf.cell(col_widths[0], 6, control_id, border=1, fill=True,
                     new_x=XPos.RIGHT, new_y=YPos.TOP)
            x_start += col_widths[0]

            # Status badge
            badge_color = self._color_for_status(status)
            pdf.set_fill_color(*badge_color)
            pdf.set_text_color(*_COLOR_WHITE)
            pdf.set_font("Helvetica", "B", 7)
            pdf.set_xy(x_start, y_before)
            pdf.cell(col_widths[1], 6, self._status_label(status),
                     border=1, fill=True, align="C",
                     new_x=XPos.RIGHT, new_y=YPos.TOP)
            x_start += col_widths[1]

            # Risk score (colour-coded)
            risk_color: tuple[int, int, int] = (
                _COLOR_DANGER if risk_score >= 7.0 else
                _COLOR_WARNING if risk_score >= 4.0 else
                _COLOR_SUCCESS
            )
            pdf.set_fill_color(*fill_bg)
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(*risk_color)
            pdf.set_xy(x_start, y_before)
            pdf.cell(col_widths[2], 6, f"{risk_score:.2f}",
                     border=1, fill=True, align="C",
                     new_x=XPos.RIGHT, new_y=YPos.TOP)
            x_start += col_widths[2]

            # Key gap (multi-cell)
            pdf.set_fill_color(*fill_bg)
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(*_COLOR_TEXT)
            pdf.set_xy(x_start, y_before)
            lines_gap = pdf.multi_cell(col_widths[3], 3, key_gap, border=0, split_only=True)
            pdf.multi_cell(col_widths[3], 3, key_gap, border=1, fill=True,
                           new_x=XPos.RIGHT, new_y=YPos.TOP)
            x_start += col_widths[3]
            h_gap = len(lines_gap) * 3

            # Recommendation (multi-cell)
            pdf.set_xy(x_start, y_before)
            lines_rec = pdf.multi_cell(col_widths[4], 3, key_rec, border=0, split_only=True)
            pdf.multi_cell(col_widths[4], 3, key_rec, border=1, fill=True,
                           new_x=XPos.LMARGIN, new_y=YPos.TOP)
            h_rec = len(lines_rec) * 3

            pdf.set_y(y_before + max(6.0, float(h_gap), float(h_rec)))

    # ------------------------------------------------------------------
    # Evidence Records
    # ------------------------------------------------------------------

    def _render_evidence_records(
        self,
        pdf: _DORAuditFPDF,
        evidence_rows: list[dict[str, Any]],
    ) -> None:
        self._section_heading(pdf, "3. Evidence Records")
        self._body_text(
            pdf,
            "Evidence records document the outcome of each automated test executed against "
            "DORA controls. Each record includes the test type, result, severity rating, "
            "and sign-off status required for regulatory submission.",
        )

        if not evidence_rows:
            self._body_text(pdf, "No evidence records available.")
            return

        col_widths = [22.0, 30.0, 25.0, 18.0, 22.0, 18.0, 25.0]
        headers = ["Control", "Timestamp", "Test Type", "Result", "Severity", "Remediation", "Sign-off"]
        cols = list(zip(headers, col_widths))
        self._table_header(pdf, cols)

        for i, row in enumerate(evidence_rows):
            control_id = self._safe(str(row.get("control_id", "")))[:20]
            timestamp = self._safe(str(row.get("test_timestamp", "")))[:19]
            test_type = self._safe(str(row.get("test_type", "")))[:24]
            result = self._safe(str(row.get("result", "")))[:16]
            severity = self._safe(str(row.get("severity", ""))).lower()
            remediation = "Yes" if row.get("remediation_required") else "No"
            sign_off = self._safe(str(row.get("sign_off_status", "")))[:22]

            shaded = (i % 2 == 0)
            fill_bg = _COLOR_LIGHT if shaded else _COLOR_WHITE
            y_before = pdf.get_y()

            if y_before + 7 > pdf.h - pdf.b_margin:
                pdf.add_page()
                self._table_header(pdf, cols)
                y_before = pdf.get_y()

            x_start = 15.0
            sev_color = self._color_for_severity(severity)
            cells_spec: list[tuple[str, float, tuple[int, int, int], tuple[int, int, int], bool, str]] = [
                (control_id, col_widths[0], fill_bg, _COLOR_TEXT, False, "L"),
                (timestamp, col_widths[1], fill_bg, _COLOR_TEXT, False, "L"),
                (test_type, col_widths[2], fill_bg, _COLOR_TEXT, False, "L"),
                (result, col_widths[3], fill_bg, _COLOR_TEXT, False, "L"),
                (severity.upper(), col_widths[4], sev_color, _COLOR_WHITE, True, "C"),
                (remediation, col_widths[5], fill_bg, _COLOR_TEXT, False, "C"),
                (sign_off, col_widths[6], fill_bg, _COLOR_TEXT, False, "L"),
            ]
            for text, w, bg, fg, bold, align in cells_spec:
                pdf.set_fill_color(*bg)
                pdf.set_text_color(*fg)
                pdf.set_font("Helvetica", "B" if bold else "", 7)
                pdf.set_xy(x_start, y_before)
                pdf.cell(w, 6, text, border=1, fill=True, align=align,
                         new_x=XPos.RIGHT, new_y=YPos.TOP)
                x_start += w
            pdf.set_y(y_before + 6)
            pdf.set_x(15)

    # ------------------------------------------------------------------
    # Remediation Plan
    # ------------------------------------------------------------------

    def _render_remediation_plan(
        self,
        pdf: _DORAuditFPDF,
        remediation_rows: list[dict[str, Any]],
    ) -> None:
        self._section_heading(pdf, "4. Remediation Plan")
        self._body_text(
            pdf,
            "Remediation items are prioritised by severity and expected effort. "
            "Each item is linked to the failing control and DORA article. "
            "Deadlines are calculated from the report generation date based on severity.",
        )

        if not remediation_rows:
            self._body_text(pdf, "No remediation items identified.")
            return

        col_widths = [18.0, 22.0, 16.0, 24.0, 55.0, 18.0, 27.0]
        headers = ["Item ID", "Control", "Severity", "Article", "Action Title", "Effort", "Deadline"]
        cols = list(zip(headers, col_widths))
        self._table_header(pdf, cols)

        for i, row in enumerate(remediation_rows):
            item_id = self._safe(str(row.get("item_id", "")))[:16]
            control_id = self._safe(str(row.get("control_id", "")))[:20]
            severity = self._safe(str(row.get("severity", ""))).lower()
            article = self._safe(str(row.get("article", "")))[:22]
            title = self._safe(str(row.get("title", "")))[:52]
            effort = self._safe(str(row.get("effort", "")))[:16]
            deadline = self._safe(str(row.get("remediation_deadline", "")))[:25]

            shaded = (i % 2 == 0)
            fill_bg = _COLOR_LIGHT if shaded else _COLOR_WHITE
            y_before = pdf.get_y()

            if y_before + 7 > pdf.h - pdf.b_margin:
                pdf.add_page()
                self._table_header(pdf, cols)
                y_before = pdf.get_y()

            x_start = 15.0
            sev_color = self._color_for_severity(severity)
            cells_spec2: list[tuple[str, float, tuple[int, int, int], tuple[int, int, int], bool, str]] = [
                (item_id, col_widths[0], fill_bg, _COLOR_TEXT, False, "L"),
                (control_id, col_widths[1], fill_bg, _COLOR_TEXT, False, "L"),
                (severity.upper(), col_widths[2], sev_color, _COLOR_WHITE, True, "C"),
                (article, col_widths[3], fill_bg, _COLOR_TEXT, False, "L"),
                (title, col_widths[4], fill_bg, _COLOR_TEXT, False, "L"),
                (effort, col_widths[5], fill_bg, _COLOR_TEXT, False, "C"),
                (deadline, col_widths[6], fill_bg, _COLOR_TEXT, False, "L"),
            ]
            for text, w, bg, fg, bold, align in cells_spec2:
                pdf.set_fill_color(*bg)
                pdf.set_text_color(*fg)
                pdf.set_font("Helvetica", "B" if bold else "", 7)
                pdf.set_xy(x_start, y_before)
                pdf.cell(w, 6, text, border=1, fill=True, align=align,
                         new_x=XPos.RIGHT, new_y=YPos.TOP)
                x_start += w
            pdf.set_y(y_before + 6)
            pdf.set_x(15)

    # ------------------------------------------------------------------
    # Register of Information (Art. 28)
    # ------------------------------------------------------------------

    def _render_register_of_information(
        self,
        pdf: _DORAuditFPDF,
        register_rows: list[dict[str, Any]],
    ) -> None:
        self._section_heading(pdf, "5. Register of Information")
        self._body_text(
            pdf,
            "Article 28 of DORA requires financial entities to maintain a comprehensive "
            "register of all ICT third-party service providers. The following table lists "
            "all identified providers, their criticality, dependency count, and risk flags.",
        )

        if not register_rows:
            self._body_text(pdf, "No third-party providers registered.")
            return

        col_widths = [40.0, 25.0, 28.0, 20.0, 22.0, 25.0]
        headers = ["Provider", "Criticality", "Type", "Dependents", "Concentration Risk", "Exit Strategy"]
        cols = list(zip(headers, col_widths))
        self._table_header(pdf, cols)

        for i, entry in enumerate(register_rows):
            provider_name = self._safe(str(entry.get("provider_name", "")))[:38]
            criticality = self._safe(str(entry.get("criticality", ""))).upper()[:22]
            provider_type = self._safe(str(entry.get("provider_type", "")))[:26]
            dependents = str(len(entry.get("dependent_functions", [])))
            concentration = "Yes" if entry.get("concentration_risk") else "No"
            exit_strategy = "Yes" if entry.get("exit_strategy_documented") else "No"

            shaded = (i % 2 == 0)
            fill_bg = _COLOR_LIGHT if shaded else _COLOR_WHITE
            y_before = pdf.get_y()

            if y_before + 7 > pdf.h - pdf.b_margin:
                pdf.add_page()
                self._table_header(pdf, cols)
                y_before = pdf.get_y()

            crit_color: tuple[int, int, int] = (
                _COLOR_DANGER if criticality.lower() == "critical" else
                _COLOR_WARNING if criticality.lower() == "important" else
                _COLOR_SUCCESS
            )
            x_start = 15.0
            cells_spec3: list[tuple[str, float, tuple[int, int, int], tuple[int, int, int], bool, str]] = [
                (provider_name, col_widths[0], fill_bg, _COLOR_TEXT, False, "L"),
                (criticality, col_widths[1], crit_color, _COLOR_WHITE, True, "C"),
                (provider_type, col_widths[2], fill_bg, _COLOR_TEXT, False, "L"),
                (dependents, col_widths[3], fill_bg, _COLOR_TEXT, False, "C"),
                (
                    concentration, col_widths[4],
                    _COLOR_DANGER if concentration == "Yes" else fill_bg,
                    _COLOR_WHITE if concentration == "Yes" else _COLOR_TEXT,
                    concentration == "Yes", "C",
                ),
                (
                    exit_strategy, col_widths[5],
                    _COLOR_SUCCESS if exit_strategy == "Yes" else fill_bg,
                    _COLOR_WHITE if exit_strategy == "Yes" else _COLOR_TEXT,
                    exit_strategy == "Yes", "C",
                ),
            ]
            for text, w, bg, fg, bold, align in cells_spec3:
                pdf.set_fill_color(*bg)
                pdf.set_text_color(*fg)
                pdf.set_font("Helvetica", "B" if bold else "", 7)
                pdf.set_xy(x_start, y_before)
                pdf.cell(w, 6, text, border=1, fill=True, align=align,
                         new_x=XPos.RIGHT, new_y=YPos.TOP)
                x_start += w
            pdf.set_y(y_before + 6)
            pdf.set_x(15)

    # ------------------------------------------------------------------
    # Audit Trail
    # ------------------------------------------------------------------

    def _render_audit_trail(
        self,
        pdf: _DORAuditFPDF,
        meta: dict[str, Any],
    ) -> None:
        self._section_heading(pdf, "6. Audit Trail")
        self._body_text(
            pdf,
            "The audit trail records the provenance of this compliance report, "
            "including generation metadata and chain integrity information.",
        )

        report_id = self._safe(meta.get("report_id", ""))
        generated_at = meta.get("generated_at", "")
        reporting_entity = self._safe(meta.get("reporting_entity", ""))
        report_period = self._safe(meta.get("report_period", ""))
        faultray_version = self._safe(meta.get("faultray_version", ""))

        items = [
            ("Report ID", report_id),
            ("Reporting Entity", reporting_entity),
            ("Generated At", generated_at),
            ("Report Period", report_period),
            ("FaultRay Version", faultray_version),
            ("Document Classification", "CONFIDENTIAL - Regulatory Evidence"),
            ("Report Standard", "EU Regulation 2022/2554 (DORA)"),
            ("Evidence Format", "Structured JSON + PDF"),
            ("Chain Integrity", "HMAC-SHA256 evidence signing available (--signed flag)"),
        ]

        col_label = 70.0
        col_value = pdf.w - 30 - col_label
        for i, (label, value) in enumerate(items):
            shaded = (i % 2 == 0)
            fill_bg = _COLOR_LIGHT if shaded else _COLOR_WHITE
            pdf.set_fill_color(*fill_bg)
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(*_COLOR_PRIMARY)
            pdf.cell(col_label, 7, label, border=1, fill=True,
                     new_x=XPos.RIGHT, new_y=YPos.TOP)
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(*_COLOR_TEXT)
            pdf.cell(col_value, 7, str(value)[:80], border=1, fill=True,
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ------------------------------------------------------------------
    # Glossary
    # ------------------------------------------------------------------

    def _render_glossary(self, pdf: _DORAuditFPDF) -> None:
        self._section_heading(pdf, "Appendix A: Glossary")
        self._body_text(pdf, "Key terms used in this DORA compliance audit report.")

        col_term = 38.0
        col_def = pdf.w - 30 - col_term
        for i, (term, definition) in enumerate(_GLOSSARY):
            shaded = (i % 2 == 0)
            fill_bg = _COLOR_LIGHT if shaded else _COLOR_WHITE
            y_before = pdf.get_y()

            if y_before + 12 > pdf.h - pdf.b_margin:
                pdf.add_page()
                y_before = pdf.get_y()

            pdf.set_fill_color(*fill_bg)
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(*_COLOR_PRIMARY)
            pdf.set_xy(15, y_before)
            lines_term = pdf.multi_cell(col_term, 4, term, border=0, split_only=True)
            pdf.multi_cell(col_term, 4, term, border=1, fill=True,
                           new_x=XPos.RIGHT, new_y=YPos.TOP)
            h_term = len(lines_term) * 4

            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(*_COLOR_TEXT)
            pdf.set_xy(15 + col_term, y_before)
            lines_def = pdf.multi_cell(col_def, 4, definition, border=0, split_only=True)
            pdf.multi_cell(col_def, 4, definition, border=1, fill=True,
                           new_x=XPos.LMARGIN, new_y=YPos.TOP)
            h_def = len(lines_def) * 4

            pdf.set_y(y_before + max(float(h_term), float(h_def), 6.0))

    # ------------------------------------------------------------------
    # Methodology
    # ------------------------------------------------------------------

    def _render_methodology(self, pdf: _DORAuditFPDF) -> None:
        self._section_heading(pdf, "Appendix B: Methodology")
        self._body_text(
            pdf,
            "This appendix describes the assessment methodology used by FaultRay "
            "to generate the evidence in this report.",
        )
        self._body_text(pdf, _METHODOLOGY_TEXT)

        self._section_heading(pdf, "Test Type Reference", level=2)
        test_types = [
            (
                "scenario_simulation",
                "Automated chaos scenarios injected into the infrastructure graph "
                "to validate resilience behaviour.",
            ),
            (
                "configuration_audit",
                "Static analysis of infrastructure configuration against DORA control requirements.",
            ),
            (
                "dependency_analysis",
                "Graph-based analysis of service dependencies and single-point-of-failure detection.",
            ),
            (
                "third_party_risk",
                "Assessment of ICT third-party provider risk based on Article 28 criteria.",
            ),
            (
                "availability_test",
                "Continuous availability measurement and SLA compliance verification.",
            ),
            (
                "backup_verification",
                "Validation of backup and recovery procedures against RTO/RPO requirements.",
            ),
        ]
        col_type = 50.0
        col_desc = pdf.w - 30 - col_type
        self._table_header(pdf, [("Test Type", col_type), ("Description", col_desc)])
        for i, (ttype, desc) in enumerate(test_types):
            shaded = (i % 2 == 0)
            fill_bg = _COLOR_LIGHT if shaded else _COLOR_WHITE
            y_before = pdf.get_y()
            pdf.set_fill_color(*fill_bg)
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(*_COLOR_PRIMARY)
            pdf.set_xy(15, y_before)
            pdf.cell(col_type, 6, ttype, border=1, fill=True,
                     new_x=XPos.RIGHT, new_y=YPos.TOP)
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(*_COLOR_TEXT)
            pdf.set_xy(15 + col_type, y_before)
            lines = pdf.multi_cell(col_desc, 4, desc, border=0, split_only=True)
            pdf.multi_cell(col_desc, 4, desc, border=1, fill=True,
                           new_x=XPos.LMARGIN, new_y=YPos.TOP)
            pdf.set_y(y_before + max(6.0, len(lines) * 4.0))
