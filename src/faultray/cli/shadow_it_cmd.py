# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI command for Shadow IT / Orphaned System Detection."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console


@app.command("shadow-it")
def shadow_it(
    model: Path = typer.Argument(..., help="Infrastructure model file (YAML or JSON)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Shadow IT / Orphaned System Detection.

    Scans infrastructure components for ownership gaps, stale systems,
    missing documentation, and unmanaged automation / serverless / scheduled jobs.

    Risk levels:
      CRITICAL — automation/serverless/scheduled job with no owner
      HIGH     — any component with no owner, or creator no longer assigned
      MEDIUM   — stale (>1 year), possibly dead, unknown lifecycle status
      LOW      — undocumented component

    Examples:
        faultray shadow-it examples/shadow-it-sample.yaml
        faultray shadow-it examples/shadow-it-sample.yaml --json
    """
    from faultray.simulator.shadow_it_analyzer import ShadowITAnalyzer

    if json_output:
        import logging as _logging
        _logging.getLogger("faultray").setLevel(_logging.ERROR)
    graph = _load_graph_for_analysis(model, model)
    analyzer = ShadowITAnalyzer()
    report = analyzer.analyze(graph)

    if json_output:
        console.print_json(data=report.to_dict())
        return

    # Summary panel
    score = report.risk_score
    if score >= 60:
        score_color = "red"
        score_label = "High Risk"
    elif score >= 30:
        score_color = "yellow"
        score_label = "Moderate Risk"
    else:
        score_color = "green"
        score_label = "Low Risk"

    critical_count = sum(1 for f in report.findings if f.risk_level == "critical")
    high_count = sum(1 for f in report.findings if f.risk_level == "high")
    medium_count = sum(1 for f in report.findings if f.risk_level == "medium")
    low_count = sum(1 for f in report.findings if f.risk_level == "low")

    summary_text = (
        f"[bold]Risk Score:[/] [{score_color}]{score:.1f}/100[/] ({score_label})\n"
        f"[bold]Total Components:[/] {report.total_components}\n"
        f"[bold]Orphaned:[/] {report.orphaned_count}  "
        f"[bold]Stale:[/] {report.stale_count}  "
        f"[bold]Undocumented:[/] {report.undocumented_count}\n"
        f"[bold]Findings:[/] "
        f"[red]CRITICAL {critical_count}[/]  "
        f"[yellow]HIGH {high_count}[/]  "
        f"[blue]MEDIUM {medium_count}[/]  "
        f"[dim]LOW {low_count}[/]"
    )
    console.print()
    console.print(
        Panel(
            summary_text,
            title="[bold]Shadow IT Report[/]",
            border_style=score_color,
        )
    )

    if not report.findings:
        console.print("\n[green]No shadow IT findings detected.[/]")
        return

    # Findings table
    _risk_colors = {
        "critical": "bold red",
        "high": "yellow",
        "medium": "blue",
        "low": "dim",
    }

    table = Table(title="Findings", show_header=True, show_lines=True)
    table.add_column("Component", style="cyan", width=28)
    table.add_column("Type", width=14)
    table.add_column("Risk", width=10)
    table.add_column("Category", width=16)
    table.add_column("Detail", width=46)
    table.add_column("Recommendation", width=46)

    # Sort: critical first, then high, medium, low
    _order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_findings = sorted(report.findings, key=lambda f: _order.get(f.risk_level, 9))

    for finding in sorted_findings:
        color = _risk_colors.get(finding.risk_level, "white")
        table.add_row(
            finding.component_name,
            finding.component_type,
            f"[{color}]{finding.risk_level.upper()}[/]",
            finding.category,
            finding.detail,
            finding.recommendation,
        )

    console.print()
    console.print(table)
