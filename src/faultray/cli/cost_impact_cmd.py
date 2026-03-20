# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""CLI command for Cost Impact Engine — quantify downtime costs."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console


@app.command("cost-report")
def cost_report_cmd(
    model_file: Path = typer.Argument(
        ...,
        help="Path to YAML/JSON infrastructure model file.",
    ),
    revenue_per_hour: float = typer.Option(
        50_000.0, "--revenue-per-hour", "-r",
        help="Revenue per hour in USD (applied to all components).",
    ),
    sla_penalty: float = typer.Option(
        10_000.0, "--sla-penalty",
        help="SLA penalty per violation in USD.",
    ),
    sla_threshold: float = typer.Option(
        43.2, "--sla-threshold",
        help="SLA downtime threshold in minutes (default: 43.2 = 99.9%% monthly).",
    ),
    engineer_rate: float = typer.Option(
        150.0, "--engineer-rate",
        help="Engineer hourly rate in USD.",
    ),
    incidents_per_year: float = typer.Option(
        12.0, "--incidents-per-year",
        help="Expected number of incidents per year.",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON.",
    ),
) -> None:
    """Quantify downtime costs, SLA penalties, and ROI of resilience improvements.

    Runs all failure scenarios on the given topology and calculates the
    business cost of each one, producing a prioritised cost report with
    annual projections.

    Examples:
        faultray cost-report infra.yaml --revenue-per-hour 50000
        faultray cost-report infra.yaml -r 100000 --sla-penalty 25000
        faultray cost-report infra.yaml -r 50000 --json
    """
    from faultray.simulator.cost_impact import (
        CostImpactEngine,
        CostProfile,
    )
    from faultray.simulator.engine import SimulationEngine

    graph = _load_graph_for_analysis(model_file, None)

    # Build default cost profile from CLI options
    default_profile = CostProfile(
        revenue_per_hour=revenue_per_hour,
        sla_penalty_per_violation=sla_penalty,
        sla_threshold_minutes=sla_threshold,
        engineer_hourly_rate=engineer_rate,
    )

    cost_engine = CostImpactEngine(default_profile=default_profile)

    if not json_output:
        console.print(
            f"[cyan]Running cost impact analysis "
            f"(revenue=${revenue_per_hour:,.0f}/hr, "
            f"{len(graph.components)} components)...[/]"
        )

    # Run static simulation to get failure scenarios
    sim_engine = SimulationEngine(graph)
    sim_results = sim_engine.run_all()

    # Calculate cost for each scenario
    breakdowns = []
    for result in sim_results:
        scenario_name = getattr(result, "scenario_name", None) or getattr(result, "name", "unknown")
        affected = getattr(result, "affected_components", None) or []
        if isinstance(affected, set):
            affected = list(affected)

        # Estimate downtime based on severity
        severity = getattr(result, "severity", 5.0)
        downtime = severity * 6  # rough mapping: severity 10 = 60 min

        cascade = getattr(result, "cascade_depth", 1) or 1

        bd = cost_engine.calculate_scenario_cost(
            scenario_name=scenario_name,
            affected_components=affected,
            downtime_minutes=downtime,
            cascade_depth=cascade,
        )
        if bd.total_cost > 0:
            breakdowns.append(bd)

    # Sort by cost descending
    breakdowns.sort(key=lambda b: b.total_cost, reverse=True)

    # Annual projection
    projection = cost_engine.calculate_annual_projection(
        breakdowns, incidents_per_year=incidents_per_year,
    )

    if json_output:
        data = {
            "revenue_per_hour": revenue_per_hour,
            "total_scenarios": len(breakdowns),
            "annual_projection": {
                "expected_annual_cost": projection.expected_annual_cost,
                "worst_case_annual_cost": projection.worst_case_annual_cost,
                "best_case_annual_cost": projection.best_case_annual_cost,
                "incidents_per_year": projection.expected_incidents_per_year,
                "cost_by_category": projection.cost_by_category,
            },
            "top_scenarios": [
                {
                    "name": bd.scenario_name,
                    "total_cost": bd.total_cost,
                    "cost_tier": bd.cost_tier.value,
                    "downtime_minutes": bd.downtime_minutes,
                    "revenue_loss": bd.revenue_loss,
                    "sla_penalty": bd.sla_penalty,
                    "recovery_cost": bd.recovery_cost,
                    "reputation_cost": bd.reputation_cost,
                    "productivity_loss": bd.productivity_loss,
                    "affected_components": bd.affected_components,
                    "recommendations": bd.recommendations,
                }
                for bd in breakdowns[:20]
            ],
        }
        console.print_json(data=data)
        return

    # ── Rich output ──

    # 1. Summary panel
    annual = projection.expected_annual_cost
    annual_color = (
        "red" if annual > 1_000_000
        else "yellow" if annual > 100_000
        else "green"
    )
    summary = (
        f"[bold]Expected Annual Cost:[/] [{annual_color}]"
        f"${annual:,.0f}[/]\n"
        f"[bold]Worst Case Annual:[/] ${projection.worst_case_annual_cost:,.0f}\n"
        f"[bold]Best Case Annual:[/] ${projection.best_case_annual_cost:,.0f}\n"
        f"[bold]Incidents/Year:[/] {projection.expected_incidents_per_year:.0f}\n"
        f"[bold]Revenue/Hour:[/] ${revenue_per_hour:,.0f}\n"
        f"[bold]Scenarios Analyzed:[/] {len(breakdowns)}"
    )
    console.print()
    console.print(Panel(
        summary,
        title="[bold]Cost Impact Report[/]",
        border_style=annual_color,
    ))

    # 2. Cost by category
    if projection.cost_by_category:
        cat_table = Table(title="Cost by Category (All Scenarios)", show_header=True)
        cat_table.add_column("Category", style="cyan", width=22)
        cat_table.add_column("Total", justify="right", width=16)

        for cat, total in sorted(
            projection.cost_by_category.items(), key=lambda x: x[1], reverse=True,
        ):
            cat_table.add_row(cat.replace("_", " ").title(), f"${total:,.2f}")
        console.print()
        console.print(cat_table)

    # 3. Top scenarios table
    if breakdowns:
        top_n = min(15, len(breakdowns))
        sc_table = Table(
            title=f"Top {top_n} Costliest Scenarios",
            show_header=True,
        )
        sc_table.add_column("Scenario", style="cyan", width=28)
        sc_table.add_column("Tier", width=14, justify="center")
        sc_table.add_column("Downtime", justify="right", width=10)
        sc_table.add_column("Revenue $", justify="right", width=12)
        sc_table.add_column("SLA $", justify="right", width=10)
        sc_table.add_column("Recovery $", justify="right", width=10)
        sc_table.add_column("Total $", justify="right", width=14)

        tier_colors = {
            "catastrophic": "bold red",
            "critical": "red",
            "high": "yellow",
            "medium": "white",
            "low": "dim",
        }

        for bd in breakdowns[:top_n]:
            color = tier_colors.get(bd.cost_tier.value, "white")
            sc_table.add_row(
                bd.scenario_name[:28],
                f"[{color}]{bd.cost_tier.value.upper()}[/]",
                f"{bd.downtime_minutes:.0f}m",
                f"${bd.revenue_loss:,.0f}",
                f"${bd.sla_penalty:,.0f}",
                f"${bd.recovery_cost:,.0f}",
                f"[{color}]${bd.total_cost:,.0f}[/]",
            )

        console.print()
        console.print(sc_table)

    # 4. Recommendations from top scenarios
    all_recs = []
    for bd in breakdowns[:5]:
        for rec in bd.recommendations:
            all_recs.append(rec)
    if all_recs:
        console.print("\n[bold]Recommendations:[/]")
        for i, rec in enumerate(all_recs[:10], 1):
            console.print(f"  {i}. {rec}")

    console.print()
