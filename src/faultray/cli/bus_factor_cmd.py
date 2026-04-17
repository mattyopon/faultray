# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI command for Bus Factor (Organizational Risk) Analysis."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console


@app.command("bus-factor")
def bus_factor(
    model: Path = typer.Argument(..., help="Infrastructure model file (YAML or JSON)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Bus Factor / Organizational Risk Analysis.

    Identifies which people are critical single points of failure in your
    infrastructure operations.  For each owner, calculates how many
    components they manage and what fraction of the system would be at risk
    if they left.

    Risk levels:
      CRITICAL — owner's departure affects >50% of the system
      HIGH     — owner's departure affects >25% of the system
      MEDIUM   — owner's departure affects >10% of the system
      LOW      — limited impact

    Examples:
        faultray bus-factor examples/shadow-it-sample.yaml
        faultray bus-factor examples/shadow-it-sample.yaml --json
    """
    from faultray.simulator.bus_factor_analyzer import BusFactorAnalyzer

    if json_output:
        import logging as _logging
        _logging.getLogger("faultray").setLevel(_logging.ERROR)
    graph = _load_graph_for_analysis(model, model)
    analyzer = BusFactorAnalyzer()
    report = analyzer.analyze(graph)

    if json_output:
        console.print_json(data=report.to_dict())
        return

    # --- Summary panel ---
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

    critical_count = sum(1 for p in report.people_risks if p.risk_level == "critical")
    high_count = sum(1 for p in report.people_risks if p.risk_level == "high")

    summary_text = (
        f"[bold]Risk Score:[/] [{score_color}]{score:.1f}/100[/] ({score_label})\n"
        f"[bold]Bus Factor:[/] [{'red' if report.bus_factor <= 1 else 'yellow' if report.bus_factor <= 2 else 'green'}]{report.bus_factor}[/] "
        f"(min people whose exit makes system unmanageable)\n"
        f"[bold]Owners:[/] {len(report.people_risks)}  "
        f"[bold]Unowned:[/] {len(report.unowned_components)}  "
        f"[bold]Single-owner components:[/] {len(report.single_owner_components)}\n"
        f"[bold]People Risks:[/] "
        f"[red]CRITICAL {critical_count}[/]  "
        f"[yellow]HIGH {high_count}[/]"
    )
    console.print()
    console.print(
        Panel(
            summary_text,
            title="[bold]Bus Factor Report[/]",
            border_style=score_color,
        )
    )

    if not report.people_risks:
        console.print("\n[yellow]No owned components found. Assign owners to enable bus factor analysis.[/]")
        return

    # --- Per-person risk table ---
    _risk_colors = {
        "critical": "bold red",
        "high": "yellow",
        "medium": "blue",
        "low": "dim",
    }

    table = Table(title="Personnel Risk Breakdown", show_header=True, show_lines=True)
    table.add_column("Owner", style="cyan", width=30)
    table.add_column("Components", width=10, justify="right")
    table.add_column("Dependents at Risk", width=18, justify="right")
    table.add_column("Impact if Leaves", width=16, justify="right")
    table.add_column("Risk Level", width=12)
    table.add_column("Managed Components", width=40)

    for person in report.people_risks:
        color = _risk_colors.get(person.risk_level, "white")
        comp_list = ", ".join(person.components[:4])
        if len(person.components) > 4:
            comp_list += f" +{len(person.components) - 4} more"
        table.add_row(
            person.owner,
            str(len(person.components)),
            str(person.total_dependents),
            f"{person.impact_if_leaves:.1f}%",
            f"[{color}]{person.risk_level.upper()}[/]",
            comp_list,
        )

    console.print()
    console.print(table)

    # --- Unowned components ---
    if report.unowned_components:
        console.print()
        console.print(
            f"[yellow]Unowned components ({len(report.unowned_components)}): "
            f"{', '.join(report.unowned_components)}[/]"
        )

    # --- Single-owner warning ---
    if report.single_owner_components:
        console.print()
        console.print(
            f"[red]Single-owner components ({len(report.single_owner_components)}) — "
            f"only one person knows these:[/] "
            f"{', '.join(report.single_owner_components)}"
        )
