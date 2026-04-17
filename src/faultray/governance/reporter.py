# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Governance report generation — Rich terminal, JSON, and optional PDF output."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.console import Console

from faultray.governance.assessor import AssessmentResult, MATURITY_LABELS
from faultray.governance.frameworks import (
    CROSS_MAPPING,
    GovernanceFramework,
    METI_CATEGORIES,
    ISO_CLAUSES,
    ACT_CHAPTERS,
    all_meti_requirements,
    all_iso_requirements,
    all_act_requirements,
)

logger = logging.getLogger(__name__)


class GovernanceReporter:
    """Generate governance assessment reports in multiple formats."""

    def __init__(self, result: AssessmentResult | None = None) -> None:
        self._result = result

    def set_result(self, result: AssessmentResult) -> None:
        """Set assessment result for reporting."""
        self._result = result

    # ------------------------------------------------------------------
    # Rich terminal output
    # ------------------------------------------------------------------

    def print_rich(self, framework: GovernanceFramework | None = None) -> None:
        """Print governance report to terminal using Rich."""
        from rich.console import Console

        con = Console()

        if framework == GovernanceFramework.METI_V1_1 or framework is None:
            self._print_meti_rich(con)
        if framework == GovernanceFramework.ISO42001 or framework is None:
            self._print_iso_rich(con)
        if framework == GovernanceFramework.AI_PROMOTION or framework is None:
            self._print_act_rich(con)

        if self._result is not None:
            self._print_assessment_rich(con)

    def _print_meti_rich(self, con: "Console") -> None:
        from rich.table import Table

        table = Table(title="METI AI事業者ガイドライン v1.1 — 10原則・28要件", show_header=True)
        table.add_column("原則", width=30, style="cyan")
        table.add_column("要件数", width=8, justify="center")
        table.add_column("説明", width=50)

        for cat in METI_CATEGORIES:
            table.add_row(cat.title, str(len(cat.requirements)), cat.description[:50] + "...")

        con.print()
        con.print(table)

    def _print_iso_rich(self, con: "Console") -> None:
        from rich.table import Table

        table = Table(title="ISO/IEC 42001:2023 AIMS — 7条項・25要求事項", show_header=True)
        table.add_column("条項", width=40, style="cyan")
        table.add_column("要求事項数", width=10, justify="center")

        for clause in ISO_CLAUSES:
            table.add_row(f"{clause.clause_id}. {clause.title}", str(len(clause.requirements)))

        con.print()
        con.print(table)

    def _print_act_rich(self, con: "Console") -> None:
        from rich.table import Table

        table = Table(title="AI推進法 — 6章・15要件", show_header=True)
        table.add_column("章", width=30, style="cyan")
        table.add_column("要件数", width=8, justify="center")
        table.add_column("義務/努力義務", width=20)

        for ch in ACT_CHAPTERS:
            mandatory = sum(1 for r in ch.requirements if r.obligation_type == "mandatory")
            effort = len(ch.requirements) - mandatory
            table.add_row(
                f"{ch.chapter_id}. {ch.title}",
                str(len(ch.requirements)),
                f"義務{mandatory} / 努力{effort}",
            )

        con.print()
        con.print(table)

    def _print_assessment_rich(self, con: "Console") -> None:
        from rich.panel import Panel
        from rich.table import Table

        result = self._result
        if result is None:
            return

        maturity_label = MATURITY_LABELS.get(result.maturity_level, "Unknown")
        score_color = "green" if result.overall_score >= 70 else "yellow" if result.overall_score >= 40 else "red"

        # Summary panel
        summary = (
            f"[bold]Overall Score:[/] [{score_color}]{result.overall_score:.1f}%[/]\n"
            f"[bold]Maturity Level:[/] {result.maturity_level}/5 ({maturity_label})\n"
        )
        if result.framework_coverage:
            summary += "\n[bold]Framework Coverage:[/]\n"
            for fw, pct in result.framework_coverage.items():
                fc = "green" if pct >= 70 else "yellow" if pct >= 40 else "red"
                summary += f"  {fw}: [{fc}]{pct:.1f}%[/]\n"

        con.print()
        con.print(Panel(summary, title="[bold]AI Governance Assessment[/]", border_style=score_color))

        # Category scores table
        cat_table = Table(title="Category Scores", show_header=True)
        cat_table.add_column("Category", width=35, style="cyan")
        cat_table.add_column("Score", width=8, justify="right")
        cat_table.add_column("Maturity", width=10, justify="center")
        cat_table.add_column("Questions", width=10, justify="center")

        for cs in result.category_scores:
            sc = "green" if cs.score_percent >= 70 else "yellow" if cs.score_percent >= 40 else "red"
            cat_table.add_row(
                cs.category_title,
                f"[{sc}]{cs.score_percent:.0f}%[/]",
                f"{cs.maturity_level}/5",
                str(cs.question_count),
            )

        con.print()
        con.print(cat_table)

        # Top gaps
        if result.top_gaps:
            con.print("\n[bold red]Top Gaps:[/]")
            for i, gap in enumerate(result.top_gaps[:5], 1):
                con.print(f"  {i}. {gap}")

        # Top recommendations
        if result.top_recommendations:
            con.print("\n[bold cyan]Top Recommendations:[/]")
            for i, rec in enumerate(result.top_recommendations[:5], 1):
                con.print(f"  {i}. {rec}")

        con.print()

    # ------------------------------------------------------------------
    # Cross-mapping display
    # ------------------------------------------------------------------

    def print_cross_mapping(self) -> None:
        """Print cross-framework mapping table."""
        from rich.console import Console
        from rich.table import Table

        con = Console()

        table = Table(title="Cross-Framework Mapping (METI / ISO42001 / AI推進法)", show_header=True)
        table.add_column("Theme", width=25, style="cyan")
        table.add_column("METI", width=20)
        table.add_column("ISO 42001", width=25)
        table.add_column("AI推進法", width=15)

        for entry in CROSS_MAPPING:
            table.add_row(
                entry.theme,
                ", ".join(entry.meti_ids) or "-",
                ", ".join(entry.iso_ids) or "-",
                ", ".join(entry.act_ids) or "-",
            )

        con.print()
        con.print(table)
        con.print()

    # ------------------------------------------------------------------
    # JSON export
    # ------------------------------------------------------------------

    def to_json(self, path: Path | None = None) -> str:
        """Export assessment result as JSON.

        If path is given, write to file. Always returns the JSON string.
        """
        data: dict = {}

        if self._result is not None:
            data["assessment"] = {
                "overall_score": self._result.overall_score,
                "maturity_level": self._result.maturity_level,
                "maturity_label": MATURITY_LABELS.get(self._result.maturity_level, ""),
                "framework_coverage": self._result.framework_coverage,
                "categories": [
                    {
                        "category_id": cs.category_id,
                        "title": cs.category_title,
                        "score_percent": cs.score_percent,
                        "maturity_level": cs.maturity_level,
                        "gaps": cs.gaps,
                        "recommendations": cs.recommendations,
                    }
                    for cs in self._result.category_scores
                ],
                "top_gaps": self._result.top_gaps,
                "top_recommendations": self._result.top_recommendations,
            }

        data["frameworks"] = {
            "meti_v1_1": {
                "principles": len(METI_CATEGORIES),
                "requirements": len(all_meti_requirements()),
            },
            "iso42001": {
                "clauses": len(ISO_CLAUSES),
                "requirements": len(all_iso_requirements()),
            },
            "ai_promotion": {
                "chapters": len(ACT_CHAPTERS),
                "requirements": len(all_act_requirements()),
            },
        }

        data["cross_mapping"] = [
            {
                "theme_id": e.theme_id,
                "theme": e.theme,
                "meti_ids": e.meti_ids,
                "iso_ids": e.iso_ids,
                "act_ids": e.act_ids,
            }
            for e in CROSS_MAPPING
        ]

        json_str = json.dumps(data, ensure_ascii=False, indent=2)

        if path is not None:
            path.write_text(json_str, encoding="utf-8")
            logger.info("Governance report written to %s", path)

        return json_str

    # ------------------------------------------------------------------
    # PDF export (optional, requires fpdf2)
    # ------------------------------------------------------------------

    def to_pdf(self, path: Path) -> bool:
        """Export governance report as PDF. Returns False if fpdf2 is not available."""
        try:
            from fpdf import FPDF  # type: ignore[import-untyped]
        except ImportError:
            logger.warning("fpdf2 not installed — PDF export skipped. Install with: pip install fpdf2")
            return False

        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        # Title
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, "AI Governance Assessment Report", new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(5)

        if self._result is not None:
            maturity_label = MATURITY_LABELS.get(self._result.maturity_level, "")

            pdf.set_font("Helvetica", "B", 12)
            pdf.cell(0, 8, f"Overall Score: {self._result.overall_score:.1f}%", new_x="LMARGIN", new_y="NEXT")
            pdf.cell(0, 8, f"Maturity: {self._result.maturity_level}/5 ({maturity_label})", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(5)

            # Category table
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(80, 8, "Category", border=1)
            pdf.cell(30, 8, "Score", border=1, align="C")
            pdf.cell(30, 8, "Maturity", border=1, align="C", new_x="LMARGIN", new_y="NEXT")

            pdf.set_font("Helvetica", "", 9)
            for cs in self._result.category_scores:
                title = cs.category_title
                # Truncate for ASCII-safe PDF rendering
                if len(title) > 35:
                    title = title[:32] + "..."
                pdf.cell(80, 7, title, border=1)
                pdf.cell(30, 7, f"{cs.score_percent:.0f}%", border=1, align="C")
                pdf.cell(30, 7, f"{cs.maturity_level}/5", border=1, align="C", new_x="LMARGIN", new_y="NEXT")

            pdf.ln(5)

            # Recommendations
            if self._result.top_recommendations:
                pdf.set_font("Helvetica", "B", 11)
                pdf.cell(0, 8, "Top Recommendations:", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Helvetica", "", 9)
                for i, rec in enumerate(self._result.top_recommendations[:5], 1):
                    safe_rec = rec.encode("ascii", "replace").decode("ascii")
                    pdf.cell(0, 6, f"  {i}. {safe_rec}", new_x="LMARGIN", new_y="NEXT")

        pdf.output(str(path))
        logger.info("PDF report written to %s", path)
        return True
