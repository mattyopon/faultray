"""CLI command for the SLO Budget Simulator."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from infrasim.cli.main import _load_graph_for_analysis, app, console


@app.command("slo-budget")
def slo_budget(
    model_file: Path = typer.Argument(
        ...,
        help="Path to YAML/JSON infrastructure model file.",
    ),
    slo: float = typer.Option(
        99.9, "--slo",
        help="SLO target percentage (e.g. 99.9, 99.95, 99.99).",
    ),
    consumed: float = typer.Option(
        0.0, "--consumed", "-c",
        help="Minutes of error budget already consumed.",
    ),
    window: int = typer.Option(
        30, "--window", "-w",
        help="SLO window in days.",
    ),
    max_scenarios: int = typer.Option(
        0, "--max-scenarios",
        help="Max scenarios to test (0 = engine default).",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON.",
    ),
) -> None:
    """Simulate how much chaos risk you can take given remaining SLO error budget.

    Runs the full simulation suite and classifies each scenario as
    within-budget or exceeding-budget based on the remaining error budget.

    Examples:
        infrasim slo-budget infra.yaml
        infrasim slo-budget infra.yaml --slo 99.9 --consumed 10
        infrasim slo-budget infra.yaml --slo 99.95 --window 7
        infrasim slo-budget infra.yaml --slo 99.9 --consumed 10 --json
    """
    from infrasim.simulator.engine import SimulationEngine
    from infrasim.simulator.slo_budget import SLOBudgetSimulator

    graph = _load_graph_for_analysis(model_file, None)

    if not json_output:
        console.print(
            f"[cyan]Running SLO budget analysis "
            f"(SLO={slo}%, consumed={consumed:.1f}min, "
            f"window={window}d, {len(graph.components)} components)...[/]"
        )

    engine = SimulationEngine(graph)
    report = engine.run_all_defaults(max_scenarios=max_scenarios)

    simulator = SLOBudgetSimulator(graph, slo_target=slo, window_days=window)
    result = simulator.simulate(report, current_consumed_minutes=consumed)

    if json_output:
        data = {
            "slo_target": result.slo_target,
            "window_days": result.window_days,
            "budget_total_minutes": result.budget_total_minutes,
            "budget_remaining_minutes": result.current_budget_remaining_minutes,
            "risk_appetite": result.risk_appetite,
            "max_safe_blast_radius": result.max_safe_blast_radius,
            "scenarios_within_budget": len(result.scenarios_within_budget),
            "scenarios_exceeding_budget": len(result.scenarios_exceeding_budget),
            "safe_scenarios": result.scenarios_within_budget,
            "unsafe_scenarios": result.scenarios_exceeding_budget,
            "scenario_details": result.scenario_details,
        }
        console.print_json(data=data)
        return

    # Budget summary panel
    appetite_color = {
        "aggressive": "green",
        "moderate": "yellow",
        "conservative": "red",
    }.get(result.risk_appetite, "white")

    summary = (
        f"[bold]SLO Target:[/] {result.slo_target}%\n"
        f"[bold]Window:[/] {result.window_days} days\n"
        f"[bold]Total Budget:[/] {result.budget_total_minutes:.1f} minutes\n"
        f"[bold]Consumed:[/] {consumed:.1f} minutes\n"
        f"[bold]Remaining:[/] {result.current_budget_remaining_minutes:.1f} minutes\n\n"
        f"[bold]Risk Appetite:[/] [{appetite_color}]{result.risk_appetite.upper()}[/]\n"
        f"[bold]Max Safe Blast Radius:[/] {result.max_safe_blast_radius:.1%}\n\n"
        f"[bold]Scenarios Within Budget:[/] [green]{len(result.scenarios_within_budget)}[/]\n"
        f"[bold]Scenarios Exceeding Budget:[/] [red]{len(result.scenarios_exceeding_budget)}[/]"
    )

    border = appetite_color
    console.print()
    console.print(Panel(
        summary, title="[bold]SLO Budget Analysis[/]", border_style=border,
    ))

    # Unsafe scenarios table (if any)
    if result.scenarios_exceeding_budget:
        unsafe_table = Table(
            title="Scenarios Exceeding Budget (UNSAFE to run)",
            show_header=True,
        )
        unsafe_table.add_column("Scenario", style="red", width=50)
        unsafe_table.add_column("Est. Downtime", justify="right", width=15)
        unsafe_table.add_column("Risk Score", justify="right", width=10)

        # Find details for unsafe scenarios
        for detail in result.scenario_details:
            if not detail["within_budget"]:
                unsafe_table.add_row(
                    detail["scenario_name"][:50],
                    f"{detail['estimated_downtime_minutes']:.1f}min",
                    f"{detail['risk_score']:.1f}",
                )

        console.print()
        console.print(unsafe_table)

    # Safe scenarios summary
    if result.scenarios_within_budget:
        safe_count = len(result.scenarios_within_budget)
        console.print(
            f"\n[green]{safe_count} scenarios are safe to run "
            f"within the remaining {result.current_budget_remaining_minutes:.1f}min budget.[/]"
        )
