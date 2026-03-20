# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""PDF-compatible report generation using HTML print and Markdown export."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from faultray.model.components import HealthStatus
from faultray.model.graph import InfraGraph
from faultray.reporter.html_report import generate_html_report
from faultray.simulator.engine import SimulationReport


# ---------------------------------------------------------------------------
# Print-optimised HTML (for PDF via browser Ctrl+P or wkhtmltopdf)
# ---------------------------------------------------------------------------

_PRINT_CSS = """\
<style>
  @media print {
    @page { margin: 1.5cm; size: A4; }
    body { background: white !important; color: black !important; padding: 0 !important; }
    .container { max-width: 100% !important; }
    .header { page-break-after: avoid; }
    h2 { page-break-after: avoid; }
    .finding-card { page-break-inside: avoid; }
    nav, .no-print { display: none !important; }
  }
</style>
"""


def generate_pdf_ready_html(report: SimulationReport, graph: InfraGraph) -> str:
    """Generate a print-optimised HTML report suitable for PDF conversion.

    The returned HTML includes ``@media print`` CSS rules so that opening the
    file in a browser and pressing Ctrl+P (or using *wkhtmltopdf* /
    *weasyprint* on the command line) produces a clean PDF.
    """
    html = generate_html_report(report, graph)
    # Inject print-optimised CSS just before </head>
    html = html.replace("</head>", _PRINT_CSS + "\n</head>")
    return html


def save_pdf_ready_html(
    report: SimulationReport,
    graph: InfraGraph,
    output_path: Path,
) -> Path:
    """Write a print-ready HTML report to *output_path*.

    Returns the resolved output path.
    """
    html = generate_pdf_ready_html(report, graph)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path.resolve()


# ---------------------------------------------------------------------------
# Markdown export
# ---------------------------------------------------------------------------

def _health_label(health: HealthStatus) -> str:
    return {
        HealthStatus.HEALTHY: "OK",
        HealthStatus.DEGRADED: "WARN",
        HealthStatus.OVERLOADED: "OVERLOAD",
        HealthStatus.DOWN: "DOWN",
    }.get(health, "?")


def _risk_label(score: float) -> str:
    if score >= 7.0:
        return "CRITICAL"
    if score >= 4.0:
        return "WARNING"
    return "LOW"


def export_markdown(
    report: SimulationReport,
    graph: InfraGraph,
    output_path: Path | None = None,
) -> str:
    """Export a simulation report as a Markdown document.

    If *output_path* is given the Markdown is also written to disk.

    Returns the Markdown string.
    """
    lines: list[str] = []

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    score = report.resilience_score

    # -- Title & summary ---------------------------------------------------
    lines.append("# FaultRay Chaos Simulation Report")
    lines.append("")
    lines.append(f"**Generated:** {generated_at}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Resilience Score | {score:.0f}/100 |")
    lines.append(f"| Total Components | {len(graph.components)} |")
    lines.append(f"| Scenarios Tested | {len(report.results)} |")
    lines.append(f"| Critical Findings | {len(report.critical_findings)} |")
    lines.append(f"| Warnings | {len(report.warnings)} |")
    lines.append(f"| Passed | {len(report.passed)} |")
    lines.append("")

    # -- Critical findings -------------------------------------------------
    if report.critical_findings:
        lines.append("## Critical Findings")
        lines.append("")
        for result in report.critical_findings:
            lines.append(f"### {result.scenario.name}")
            lines.append("")
            lines.append(f"**Risk Score:** {result.risk_score:.1f}/10 ({_risk_label(result.risk_score)})")
            lines.append("")
            lines.append(f"> {result.scenario.description}")
            lines.append("")
            if result.cascade.effects:
                lines.append("**Cascade Path:**")
                lines.append("")
                lines.append("| Component | Status | Reason | Time |")
                lines.append("|-----------|--------|--------|------|")
                prev_time = 0
                for eff in result.cascade.effects:
                    time_str = ""
                    if eff.estimated_time_seconds > 0:
                        delta = eff.estimated_time_seconds - prev_time
                        time_str = f"+{delta}s"
                        prev_time = eff.estimated_time_seconds
                    lines.append(
                        f"| {eff.component_name} "
                        f"| {_health_label(eff.health)} "
                        f"| {eff.reason} "
                        f"| {time_str} |"
                    )
                lines.append("")

    # -- Warnings ----------------------------------------------------------
    if report.warnings:
        lines.append("## Warnings")
        lines.append("")
        for result in report.warnings:
            lines.append(f"### {result.scenario.name}")
            lines.append("")
            lines.append(f"**Risk Score:** {result.risk_score:.1f}/10 ({_risk_label(result.risk_score)})")
            lines.append("")
            lines.append(f"> {result.scenario.description}")
            lines.append("")
            if result.cascade.effects:
                lines.append("**Cascade Path:**")
                lines.append("")
                lines.append("| Component | Status | Reason | Time |")
                lines.append("|-----------|--------|--------|------|")
                prev_time = 0
                for eff in result.cascade.effects:
                    time_str = ""
                    if eff.estimated_time_seconds > 0:
                        delta = eff.estimated_time_seconds - prev_time
                        time_str = f"+{delta}s"
                        prev_time = eff.estimated_time_seconds
                    lines.append(
                        f"| {eff.component_name} "
                        f"| {_health_label(eff.health)} "
                        f"| {eff.reason} "
                        f"| {time_str} |"
                    )
                lines.append("")

    # -- Passed summary ----------------------------------------------------
    if report.passed:
        lines.append("## Passed Scenarios")
        lines.append("")
        lines.append(f"{len(report.passed)} scenarios passed with low risk.")
        lines.append("")

    # -- Components --------------------------------------------------------
    lines.append("## Components")
    lines.append("")
    lines.append("| Name | Type | Host | Port | Replicas | CPU% | Mem% | Disk% | Util% |")
    lines.append("|------|------|------|------|----------|------|------|-------|-------|")
    for comp in graph.components.values():
        util = comp.utilization()
        lines.append(
            f"| {comp.name} "
            f"| {comp.type.value} "
            f"| {comp.host} "
            f"| {comp.port} "
            f"| {comp.replicas} "
            f"| {comp.metrics.cpu_percent:.0f} "
            f"| {comp.metrics.memory_percent:.0f} "
            f"| {comp.metrics.disk_percent:.0f} "
            f"| {util:.0f} |"
        )
    lines.append("")

    lines.append("---")
    lines.append("*Report generated by FaultRay*")

    md = "\n".join(lines)

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(md, encoding="utf-8")

    return md
