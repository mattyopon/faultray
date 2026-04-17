# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI command for SLO Impact Simulator.

Calculates how quickly a component failure leads to SLO violation,
leveraging FaultRay's topology knowledge.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console


@app.command("slo-impact")
def slo_impact(
    model_file: Path = typer.Argument(
        ...,
        help="Path to YAML/JSON infrastructure model file.",
    ),
    component: Optional[str] = typer.Option(
        None, "--component", "-c",
        help="Component ID to simulate failure for.",
    ),
    all_components: bool = typer.Option(
        False, "--all", "-a",
        help="Rank all components by SLO risk.",
    ),
    slo: float = typer.Option(
        99.9, "--slo",
        help="SLO target percentage (e.g. 99.9, 99.95, 99.99).",
    ),
    budget_window: str = typer.Option(
        "30d", "--budget-window",
        help="SLO window (e.g. 30d, 7d). Only 'd' (days) suffix supported.",
    ),
    consumed: float = typer.Option(
        0.0, "--consumed",
        help="Error budget already consumed in minutes.",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON.",
    ),
) -> None:
    """Calculate SLO violation time from component failures.

    Uses FaultRay's topology knowledge to answer:
    "If this component fails, how long until we violate our SLO?"

    Examples:
        faultray slo-impact infra.yaml --component database-primary
        faultray slo-impact infra.yaml --all
        faultray slo-impact infra.yaml --all --json
        faultray slo-impact infra.yaml --slo 99.9 --budget-window 30d
        faultray slo-impact infra.yaml --component api-server --consumed 10
    """
    from faultray.simulator.slo_impact import SLOImpactSimulator

    if not component and not all_components:
        console.print(
            "[red]Specify --component <id> or --all to rank all components.[/]"
        )
        raise typer.Exit(1)

    # Parse budget window (e.g. "30d" -> 30)
    window_days = _parse_window_days(budget_window)

    graph = _load_graph_for_analysis(model_file, None)

    simulator = SLOImpactSimulator(
        graph,
        slo_target=slo,
        budget_window_days=window_days,
        current_consumed_minutes=consumed,
    )
    budget = simulator.calculate_error_budget()

    if component:
        # Single component mode
        try:
            result = simulator.simulate_component_failure(component)
        except KeyError as exc:
            console.print(f"[red]{exc}[/]")
            raise typer.Exit(1) from exc

        if json_output:
            data = {
                "slo_target": slo,
                "budget_window_days": window_days,
                "error_budget": {
                    "total_minutes": budget.total_budget_minutes,
                    "remaining_minutes": budget.remaining_budget_minutes,
                    "burn_rate": budget.burn_rate,
                },
                "component": {
                    "id": result.component_id,
                    "name": result.component_name,
                    "type": result.component_type,
                    "affected_services": result.affected_services,
                    "affected_service_count": result.affected_service_count,
                    "estimated_mttr_minutes": result.estimated_mttr_minutes,
                    "error_budget_consumption_pct": result.error_budget_consumption_pct,
                    "minutes_to_slo_violation": result.minutes_to_slo_violation,
                    "risk_level": result.risk_level,
                    "cascade_path": result.cascade_path,
                    "recommendation": result.recommendation,
                },
            }
            console.print_json(data=data)
            return

        # Human-readable single component output
        risk_color = _risk_color(result.risk_level)
        violation_text = (
            f"[{risk_color}]{result.minutes_to_slo_violation:.1f} minutes[/]"
            if result.minutes_to_slo_violation > 0
            else f"[{risk_color}]ALREADY VIOLATED[/]"
        )

        import math
        budget_consumed_text = (
            "N/A (no budget)"
            if math.isinf(result.error_budget_consumption_pct)
            else f"{result.error_budget_consumption_pct:.1f}%"
        )
        summary = (
            f"[bold]Component:[/] {result.component_name} ({result.component_id})\n"
            f"[bold]Type:[/] {result.component_type}\n"
            f"[bold]Affected Services:[/] {result.affected_service_count} "
            f"({', '.join(result.affected_services) or 'none'})\n"
            f"[bold]Estimated MTTR:[/] {result.estimated_mttr_minutes:.1f} minutes\n"
            f"[bold]Error Budget Consumed:[/] {budget_consumed_text}\n"
            f"[bold]SLO Violation In:[/] {violation_text}\n"
            f"[bold]Risk Level:[/] [{risk_color}]{result.risk_level.upper()}[/]\n\n"
            f"[bold]Recommendation:[/] {result.recommendation}"
        )

        if result.cascade_path and len(result.cascade_path) > 1:
            path_str = " → ".join(result.cascade_path)
            summary += f"\n[bold]Cascade Path:[/] {path_str}"

        console.print()
        console.print(Panel(
            summary,
            title=f"[bold]SLO Impact: {result.component_name}[/]",
            border_style=risk_color,
        ))

        # Budget context
        console.print(
            f"\n[dim]SLO: {slo}% | Window: {window_days}d | "
            f"Budget: {budget.total_budget_minutes:.1f}min total, "
            f"{budget.remaining_budget_minutes:.1f}min remaining[/]"
        )

        # One-liner summary matching spec
        if result.minutes_to_slo_violation > 0:
            console.print(
                f"\n[bold]{result.component_name}[/] failure impacts "
                f"[bold]{result.affected_service_count}[/] services. "
                f"SLO violation in [bold]{result.minutes_to_slo_violation:.0f}[/] minutes."
            )
        else:
            console.print(
                f"\n[bold]{result.component_name}[/] failure impacts "
                f"[bold]{result.affected_service_count}[/] services. "
                f"[red]SLO violation IMMEDIATE (budget exhausted).[/]"
            )

    else:
        # All components ranking mode
        if not json_output:
            console.print(
                f"[cyan]Ranking all {len(graph.components)} components by SLO risk "
                f"(SLO={slo}%, window={window_days}d)...[/]"
            )

        results = simulator.rank_all_components()

        if json_output:
            data = {
                "slo_target": slo,
                "budget_window_days": window_days,
                "error_budget": {
                    "total_minutes": budget.total_budget_minutes,
                    "remaining_minutes": budget.remaining_budget_minutes,
                    "burn_rate": budget.burn_rate,
                },
                "rankings": [
                    {
                        "rank": i + 1,
                        "component_id": r.component_id,
                        "component_name": r.component_name,
                        "component_type": r.component_type,
                        "affected_service_count": r.affected_service_count,
                        "estimated_mttr_minutes": r.estimated_mttr_minutes,
                        "error_budget_consumption_pct": r.error_budget_consumption_pct,
                        "minutes_to_slo_violation": r.minutes_to_slo_violation,
                        "risk_level": r.risk_level,
                    }
                    for i, r in enumerate(results)
                ],
            }
            console.print_json(data=data)
            return

        # Budget summary
        console.print()
        console.print(
            f"[bold]Error Budget:[/] {budget.total_budget_minutes:.1f} min total, "
            f"{budget.remaining_budget_minutes:.1f} min remaining "
            f"(burn rate: {budget.burn_rate * 100:.1f}%)"
        )
        console.print()

        # Ranking table
        table = Table(
            title=f"SLO Risk Ranking (SLO={slo}%, {window_days}d window)",
            show_header=True,
        )
        table.add_column("#", justify="right", width=4)
        table.add_column("Component", width=28)
        table.add_column("Type", width=16)
        table.add_column("Affected\nServices", justify="right", width=10)
        table.add_column("MTTR\n(min)", justify="right", width=8)
        table.add_column("Budget\nConsumed%", justify="right", width=10)
        table.add_column("Violation\nIn (min)", justify="right", width=12)
        table.add_column("Risk", width=10)

        import math as _math
        for i, r in enumerate(results, 1):
            rc = _risk_color(r.risk_level)
            violation_str = (
                f"{r.minutes_to_slo_violation:.1f}"
                if r.minutes_to_slo_violation > 0
                else "IMMEDIATE"
            )
            budget_consumed_str = (
                "N/A"
                if _math.isinf(r.error_budget_consumption_pct)
                else f"{r.error_budget_consumption_pct:.1f}%"
            )
            table.add_row(
                str(i),
                r.component_name[:28],
                r.component_type[:16],
                str(r.affected_service_count),
                f"{r.estimated_mttr_minutes:.1f}",
                budget_consumed_str,
                f"[{rc}]{violation_str}[/]",
                f"[{rc}]{r.risk_level.upper()}[/]",
            )

        console.print(table)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_window_days(window: str) -> int:
    """Parse a window string like '30d' or '7d' into an integer number of days."""
    window = window.strip().lower()
    if window.endswith("d"):
        try:
            days = int(window[:-1])
        except ValueError:
            days = None
        else:
            if days <= 0:
                raise typer.BadParameter("budget window must be positive")
            return days
    # Try plain integer
    try:
        days = int(window)
    except ValueError:
        console.print(
            f"[yellow]Warning: could not parse window '{window}', using 30d.[/]"
        )
        return 30
    if days <= 0:
        raise typer.BadParameter("budget window must be positive")
    return days


def _risk_color(risk_level: str) -> str:
    """Map risk level string to a Rich color name."""
    return {
        "critical": "red",
        "high": "yellow",
        "medium": "cyan",
        "low": "green",
    }.get(risk_level, "white")
