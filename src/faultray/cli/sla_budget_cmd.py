# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI command for SLA Budget / Error Budget Burn Rate Analysis."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console


@app.command("sla-budget")
def sla_budget(
    model: Path = typer.Argument(..., help="Infrastructure model file (YAML or JSON)"),
    incidents: int = typer.Option(
        0, "--incidents", "-i",
        help="Number of 30-min incidents assumed this month (applied to every component).",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """SLA Budget / Error Budget Burn Rate Analysis.

    Shows how much error budget remains for each component and estimates when
    the budget will be exhausted at the current burn rate.

    Budget status levels:
      HEALTHY   — >50% remaining
      WARNING   — 20-50% remaining
      CRITICAL  — 0-20% remaining
      EXHAUSTED — 0% or less remaining

    Use --incidents N to simulate a scenario where N incidents (each 30 min)
    have occurred this month for every component.

    Examples:
        faultray sla-budget examples/demo-infra.yaml
        faultray sla-budget examples/demo-infra.yaml --incidents 3
        faultray sla-budget examples/demo-infra.yaml --json
    """
    from faultray.simulator.sla_budget_analyzer import SLABudgetAnalyzer

    if json_output:
        import logging as _logging
        _logging.getLogger("faultray").setLevel(_logging.ERROR)
    graph = _load_graph_for_analysis(model, model)
    analyzer = SLABudgetAnalyzer()
    report = analyzer.analyze(graph, incidents_per_component=incidents)

    if json_output:
        console.print_json(data=report.to_dict())
        return

    # --- Status colors ---
    _status_colors: dict[str, str] = {
        "healthy": "green",
        "warning": "yellow",
        "critical": "red",
        "exhausted": "bold red",
    }

    overall_color = _status_colors.get(report.overall_status, "white")

    exhausted_count = sum(1 for b in report.budgets if b.status == "exhausted")
    critical_count = sum(1 for b in report.budgets if b.status == "critical")
    warning_count = sum(1 for b in report.budgets if b.status == "warning")
    healthy_count = sum(1 for b in report.budgets if b.status == "healthy")

    summary_text = (
        f"[bold]Overall Status:[/] [{overall_color}]{report.overall_status.upper()}[/]\n"
        f"[bold]Components:[/] {len(report.budgets)}  "
        f"[bold]Incidents assumed:[/] {incidents} × 30 min\n"
        f"[bold]Status Breakdown:[/] "
        f"[green]HEALTHY {healthy_count}[/]  "
        f"[yellow]WARNING {warning_count}[/]  "
        f"[red]CRITICAL {critical_count}[/]  "
        f"[bold red]EXHAUSTED {exhausted_count}[/]"
    )

    console.print()
    console.print(
        Panel(
            summary_text,
            title="[bold]SLA Budget Report[/]",
            border_style=overall_color,
        )
    )

    if not report.budgets:
        console.print("\n[yellow]No components found.[/]")
        return

    # --- Per-component table ---
    table = Table(title="Error Budget per Component", show_header=True, show_lines=True)
    table.add_column("Component", style="cyan", width=20)
    table.add_column("SLO %", width=8, justify="right")
    table.add_column("Allowed (min)", width=14, justify="right")
    table.add_column("Consumed (min)", width=14, justify="right")
    table.add_column("Remaining (min)", width=15, justify="right")
    table.add_column("Burn Rate", width=10, justify="right")
    table.add_column("Status", width=12)
    table.add_column("Exhaustion", width=14)

    for budget in report.budgets:
        color = _status_colors.get(budget.status, "white")
        if budget.days_until_exhaustion is None:
            exhaustion_str = "[dim]n/a[/]"
        elif budget.days_until_exhaustion <= 0:
            exhaustion_str = "[bold red]NOW[/]"
        else:
            exhaustion_str = f"{budget.days_until_exhaustion:.1f}d"

        burn_color = (
            "red" if budget.burn_rate >= 3.0
            else "yellow" if budget.burn_rate >= 1.5
            else "green"
        )

        table.add_row(
            budget.component_id,
            f"{budget.slo_target:.2f}",
            f"{budget.allowed_downtime_minutes:.1f}",
            f"{budget.consumed_downtime_minutes:.1f}",
            f"{budget.remaining_minutes:.1f}",
            f"[{burn_color}]{budget.burn_rate:.2f}x[/]",
            f"[{color}]{budget.status.upper()}[/]",
            exhaustion_str,
        )

    console.print()
    console.print(table)

    # --- Recommendations ---
    urgent = [b for b in report.budgets if b.status in ("exhausted", "critical")]
    if urgent:
        console.print()
        console.print(
            f"[bold red]{len(urgent)} component(s) at CRITICAL or EXHAUSTED status — "
            f"freeze non-critical changes and investigate reliability.[/]"
        )
