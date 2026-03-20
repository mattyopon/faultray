# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""CLI command for Failure Budget Allocation."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console


@app.command("budget")
def budget(
    model_file: Path = typer.Argument(
        ...,
        help="Path to YAML/JSON infrastructure model file.",
    ),
    subcommand: str = typer.Argument(
        "allocate",
        help="Subcommand: 'allocate' (default).",
    ),
    slo: float = typer.Option(
        99.9, "--slo",
        help="SLO target percentage (e.g. 99.9, 99.95, 99.99).",
    ),
    window: int = typer.Option(
        30, "--window", "-w",
        help="SLO window in days.",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON.",
    ),
) -> None:
    """Allocate error budget across teams and services.

    Distributes error budget proportionally based on service criticality,
    dependency graph topology, and component types.

    Examples:
        faultray budget infra.yaml allocate --slo 99.9 --window 30
        faultray budget infra.yaml allocate --slo 99.95 --json
        faultray budget infra.yaml --json
    """
    from faultray.simulator.failure_budget import FailureBudgetAllocator

    graph = _load_graph_for_analysis(model_file, None)

    allocator = FailureBudgetAllocator(graph, slo_target=slo, window_days=window)

    if not json_output:
        console.print(
            f"[cyan]Allocating error budget "
            f"(SLO={slo}%, window={window}d, "
            f"{len(graph.components)} services)...[/]"
        )

    report = allocator.allocate()

    if json_output:
        data = {
            "slo_target": report.slo_target,
            "window_days": report.window_days,
            "total_budget_minutes": report.total_budget_minutes,
            "allocations": [
                {
                    "service_id": a.service_id,
                    "service_name": a.service_name,
                    "team": a.team,
                    "budget_total_minutes": a.budget_total_minutes,
                    "budget_consumed_minutes": a.budget_consumed_minutes,
                    "budget_remaining_minutes": a.budget_remaining_minutes,
                    "budget_remaining_percent": a.budget_remaining_percent,
                    "risk_weight": a.risk_weight,
                }
                for a in report.allocations
            ],
            "over_budget_services": report.over_budget_services,
            "under_utilized_services": report.under_utilized_services,
            "rebalance_suggestions": report.rebalance_suggestions,
        }
        console.print_json(data=data)
        return

    # Budget summary panel
    summary = (
        f"[bold]SLO Target:[/] {report.slo_target}%\n"
        f"[bold]Window:[/] {report.window_days} days\n"
        f"[bold]Total Error Budget:[/] {report.total_budget_minutes:.1f} minutes\n\n"
        f"[bold]Services:[/] {len(report.allocations)}\n"
        f"[bold]Over Budget:[/] [red]{len(report.over_budget_services)}[/]\n"
        f"[bold]Under Utilized:[/] [green]{len(report.under_utilized_services)}[/]"
    )

    border_color = "red" if report.over_budget_services else "green"
    console.print()
    console.print(Panel(
        summary,
        title="[bold]Failure Budget Allocation[/]",
        border_style=border_color,
    ))

    # Allocations table
    if report.allocations:
        alloc_table = Table(title="Budget Allocations", show_header=True)
        alloc_table.add_column("Service", style="cyan", width=20)
        alloc_table.add_column("Team", width=12)
        alloc_table.add_column("Weight", justify="right", width=8)
        alloc_table.add_column("Budget", justify="right", width=10)
        alloc_table.add_column("Consumed", justify="right", width=10)
        alloc_table.add_column("Remaining", justify="right", width=10)
        alloc_table.add_column("Remaining %", justify="right", width=12)

        for a in sorted(report.allocations, key=lambda x: x.risk_weight, reverse=True):
            pct = a.budget_remaining_percent
            if pct >= 50:
                pct_color = "green"
            elif pct >= 20:
                pct_color = "yellow"
            else:
                pct_color = "red"

            alloc_table.add_row(
                a.service_name,
                a.team,
                f"{a.risk_weight:.2f}",
                f"{a.budget_total_minutes:.1f}m",
                f"{a.budget_consumed_minutes:.1f}m",
                f"{a.budget_remaining_minutes:.1f}m",
                f"[{pct_color}]{pct:.1f}%[/]",
            )

        console.print()
        console.print(alloc_table)

    # Rebalance suggestions
    if report.rebalance_suggestions:
        console.print()
        console.print("[bold yellow]Rebalance Suggestions:[/]")
        for s in report.rebalance_suggestions:
            console.print(f"  - {s.get('reason', '')}")

    console.print()
