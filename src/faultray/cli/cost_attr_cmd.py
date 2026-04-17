# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI command for Failure Cost Attribution."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console


@app.command("cost-attribution")
def cost_attribution_cmd(
    model_file: Path = typer.Argument(
        ...,
        help="Path to YAML/JSON infrastructure model file.",
    ),
    revenue: float = typer.Option(
        10_000.0, "--revenue",
        help="Revenue per hour in USD.",
    ),
    incidents: float = typer.Option(
        50_000.0, "--incidents",
        help="Average cost per incident (people, reputation).",
    ),
    sla_penalty: float = typer.Option(
        0.0, "--sla-penalty",
        help="SLA breach penalty rate per hour.",
    ),
    by_team: bool = typer.Option(
        False, "--by-team",
        help="Group results by owning team.",
    ),
    roi: bool = typer.Option(
        False, "--roi",
        help="Show ROI ranking for improvements.",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON.",
    ),
) -> None:
    """Attribute failure costs to teams, services, and components.

    Calculates the financial risk of each component and team, helping answer:
    "Which team owns the most risk?" and "What's the ROI of improving X?"

    Examples:
        faultray cost-attribution infra.yaml --revenue 1000000
        faultray cost-attribution infra.yaml --revenue 1000000 --by-team
        faultray cost-attribution infra.yaml --revenue 1000000 --roi
        faultray cost-attribution infra.yaml --revenue 1000000 --json
    """
    from faultray.simulator.cost_attribution import CostAttributionEngine, CostModel

    graph = _load_graph_for_analysis(model_file, None)

    cost_model = CostModel(
        revenue_per_hour=revenue,
        cost_per_incident=incidents,
        sla_penalty_per_hour=sla_penalty,
    )

    if not json_output:
        console.print(
            f"[cyan]Running cost attribution analysis "
            f"(revenue=${revenue:,.0f}/hr, "
            f"{len(graph.components)} components)...[/]"
        )

    engine = CostAttributionEngine()
    report = engine.analyze(graph, cost_model)

    if json_output:
        data = {
            "total_annual_risk": report.total_annual_risk,
            "currency": cost_model.currency,
            "components": [
                {
                    "id": p.component_id,
                    "name": p.component_name,
                    "team": p.owner_team,
                    "annual_failure_probability": p.annual_failure_probability,
                    "estimated_downtime_hours": p.estimated_downtime_hours,
                    "direct_cost": p.direct_cost,
                    "cascade_cost": p.cascade_cost,
                    "total_annual_risk": p.total_annual_risk,
                    "percentage_of_total_risk": p.percentage_of_total_risk,
                    "improvement_roi": p.improvement_roi,
                }
                for p in report.component_profiles
            ],
            "teams": [
                {
                    "name": t.team_name,
                    "owned_components": t.owned_components,
                    "total_annual_risk": t.total_annual_risk,
                    "highest_risk_component": t.highest_risk_component,
                    "percentage_of_total_risk": t.percentage_of_total_risk,
                    "recommended_budget": t.recommended_budget,
                }
                for t in report.team_profiles
            ],
            "cost_reduction_opportunities": [
                {"component": opp[0], "savings": opp[1], "action": opp[2]}
                for opp in report.cost_reduction_opportunities
            ],
            "budget_allocation": report.budget_allocation,
        }
        console.print_json(data=data)
        return

    # --- Rich output ---

    # 1. Summary Panel
    risk_color = (
        "green" if report.total_annual_risk < 100_000
        else "yellow" if report.total_annual_risk < 1_000_000
        else "red"
    )
    summary = (
        f"[bold]Total Annual Risk:[/] [{risk_color}]"
        f"${report.total_annual_risk:,.2f}[/]\n"
        f"[bold]Components Analyzed:[/] {len(report.component_profiles)}\n"
        f"[bold]Teams:[/] {len(report.team_profiles)}\n"
        f"[bold]Revenue/hr:[/] ${revenue:,.0f}"
    )
    console.print()
    console.print(Panel(
        summary,
        title="[bold]Failure Cost Attribution[/]",
        border_style=risk_color,
    ))

    if by_team:
        _print_team_view(report, console)
    elif roi:
        _print_roi_view(report, console)
    else:
        _print_component_view(report, console)

    # 4. Cost reduction opportunities
    if report.cost_reduction_opportunities:
        opp_table = Table(
            title="Cost Reduction Opportunities",
            show_header=True,
        )
        opp_table.add_column("Component", style="cyan", width=20)
        opp_table.add_column("Est. Savings", justify="right", width=14)
        opp_table.add_column("Action", width=40)

        for comp_id, savings, action in report.cost_reduction_opportunities[:5]:
            opp_table.add_row(
                comp_id,
                f"${savings:,.2f}",
                action,
            )

        console.print()
        console.print(opp_table)

    console.print()


def _print_component_view(report, con) -> None:
    """Print component-level cost attribution table."""
    comp_table = Table(
        title="Component Risk Attribution",
        show_header=True,
    )
    comp_table.add_column("Component", style="cyan", width=20)
    comp_table.add_column("Team", width=12)
    comp_table.add_column("Fail Prob", justify="right", width=10)
    comp_table.add_column("Downtime", justify="right", width=10)
    comp_table.add_column("Direct $", justify="right", width=12)
    comp_table.add_column("Cascade $", justify="right", width=12)
    comp_table.add_column("Annual Risk", justify="right", width=14)
    comp_table.add_column("% Risk", justify="right", width=8)

    for p in report.component_profiles:
        risk_color = (
            "red" if p.percentage_of_total_risk > 30
            else "yellow" if p.percentage_of_total_risk > 15
            else "white"
        )
        comp_table.add_row(
            p.component_id[:20],
            p.owner_team,
            f"{p.annual_failure_probability:.4f}",
            f"{p.estimated_downtime_hours:.2f}h",
            f"${p.direct_cost:,.0f}",
            f"${p.cascade_cost:,.0f}",
            f"[{risk_color}]${p.total_annual_risk:,.0f}[/]",
            f"[{risk_color}]{p.percentage_of_total_risk:.1f}%[/]",
        )

    con.print()
    con.print(comp_table)


def _print_team_view(report, con) -> None:
    """Print team-level risk attribution table."""
    team_table = Table(
        title="Team Risk Attribution",
        show_header=True,
    )
    team_table.add_column("Team", style="cyan", width=16)
    team_table.add_column("Components", justify="right", width=12)
    team_table.add_column("Annual Risk", justify="right", width=16)
    team_table.add_column("% Risk", justify="right", width=10)
    team_table.add_column("Highest Risk", width=20)
    team_table.add_column("Budget", justify="right", width=14)

    for t in report.team_profiles:
        risk_color = (
            "red" if t.percentage_of_total_risk > 40
            else "yellow" if t.percentage_of_total_risk > 20
            else "white"
        )
        team_table.add_row(
            t.team_name,
            str(len(t.owned_components)),
            f"[{risk_color}]${t.total_annual_risk:,.0f}[/]",
            f"[{risk_color}]{t.percentage_of_total_risk:.1f}%[/]",
            t.highest_risk_component[:20],
            f"${t.recommended_budget:,.0f}",
        )

    con.print()
    con.print(team_table)

    # Budget allocation summary
    if report.budget_allocation:
        budget_total = sum(report.budget_allocation.values())
        con.print(
            f"\n[bold]Total Recommended Budget:[/] "
            f"${budget_total:,.0f}/year"
        )


def _print_roi_view(report, con) -> None:
    """Print ROI ranking table."""
    roi_table = Table(
        title="Improvement ROI Ranking",
        show_header=True,
    )
    roi_table.add_column("Rank", justify="right", width=6)
    roi_table.add_column("Component", style="cyan", width=20)
    roi_table.add_column("Team", width=12)
    roi_table.add_column("Current Risk", justify="right", width=14)
    roi_table.add_column("ROI", justify="right", width=10)
    roi_table.add_column("Priority", justify="center", width=10)

    ranked = sorted(
        report.component_profiles,
        key=lambda p: p.improvement_roi,
        reverse=True,
    )

    for i, p in enumerate(ranked[:10], 1):
        if p.improvement_roi <= 0:
            continue
        priority_color = (
            "red" if p.improvement_roi > 5.0
            else "yellow" if p.improvement_roi > 1.0
            else "green"
        )
        priority_label = (
            "CRITICAL" if p.improvement_roi > 5.0
            else "HIGH" if p.improvement_roi > 1.0
            else "NORMAL"
        )
        roi_table.add_row(
            str(i),
            p.component_id[:20],
            p.owner_team,
            f"${p.total_annual_risk:,.0f}",
            f"{p.improvement_roi:.2f}x",
            f"[{priority_color}]{priority_label}[/]",
        )

    con.print()
    con.print(roi_table)
