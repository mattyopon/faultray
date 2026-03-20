# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Auto-scaling, financial risk, carbon footprint, and leaderboard CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

from faultray.cli.main import (
    _load_graph_for_analysis,
    app,
    console,
    DEFAULT_MODEL_PATH,
)
from faultray.simulator.engine import SimulationEngine


@app.command()
def autoscale(
    yaml_file: Path = typer.Argument(..., help="Infrastructure YAML or JSON model file"),
    export: str = typer.Option("k8s", "--export", "-e", help="Export format: k8s or aws"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file path"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON summary"),
) -> None:
    """Recommend auto-scaling parameters and export as K8s HPA or AWS ASG.

    Analyzes component utilization and dependency graph to recommend
    optimal auto-scaling configuration.

    Examples:
        # K8s HPA YAML (default)
        faultray autoscale infra.yaml

        # Export to file
        faultray autoscale infra.yaml --export k8s --output hpa.yaml

        # AWS Auto Scaling Group JSON
        faultray autoscale infra.yaml --export aws

        # JSON summary
        faultray autoscale infra.yaml --json
    """
    from faultray.simulator.autoscaling_engine import AutoScalingRecommendationEngine

    graph = _load_graph_for_analysis(DEFAULT_MODEL_PATH, yaml_file)

    engine = AutoScalingRecommendationEngine(graph)
    recommendations = engine.recommend()

    if json_output:
        data = [
            {
                "component_id": r.component_id,
                "component_name": r.component_name,
                "current_replicas": r.current_replicas,
                "recommended_min": r.recommended_min,
                "recommended_max": r.recommended_max,
                "target_utilization": r.target_utilization,
                "scale_up_threshold": r.scale_up_threshold,
                "cooldown_seconds": r.cooldown_seconds,
                "confidence": r.confidence,
                "reasoning": r.reasoning,
            }
            for r in recommendations
        ]
        console.print_json(data=data)
        return

    if export.lower() == "aws":
        result = engine.export_all_aws(recommendations)
    else:
        result = engine.export_all_k8s(recommendations)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(result, encoding="utf-8")
        console.print(f"[green]Auto-scaling config exported to {output}[/]")
    else:
        console.print(result)

    # Print summary
    console.print(f"\n[bold]Auto-Scaling Recommendations[/] ({len(recommendations)} components)")
    for r in recommendations:
        color = "red" if r.confidence >= 0.7 else "yellow" if r.confidence >= 0.5 else "green"
        console.print(
            f"  [{color}]{r.component_name}[/] — "
            f"replicas: {r.current_replicas} -> {r.recommended_min}-{r.recommended_max}, "
            f"confidence: {r.confidence:.0%}"
        )
        console.print(f"    {r.reasoning}")


@app.command()
def risk(
    yaml_file: Path = typer.Argument(..., help="Infrastructure YAML or JSON model file"),
    revenue: float = typer.Option(1_000_000, "--revenue", "-r", help="Annual revenue in USD"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Financial risk analysis — estimate business impact of failures.

    Calculates Value-at-Risk (VaR95), expected annual loss, and
    mitigation ROI for each failure scenario.

    Examples:
        # Basic risk analysis
        faultray risk infra.yaml

        # With custom revenue
        faultray risk infra.yaml --revenue 10000000

        # JSON output
        faultray risk infra.yaml --json
    """
    from faultray.simulator.financial_risk import FinancialRiskEngine

    graph = _load_graph_for_analysis(DEFAULT_MODEL_PATH, yaml_file)

    console.print("[cyan]Running simulation for risk analysis...[/]")
    sim_engine = SimulationEngine(graph)
    sim_report = sim_engine.run_all_defaults()

    risk_engine = FinancialRiskEngine(graph, annual_revenue=revenue)
    report = risk_engine.analyze(sim_report)

    if json_output:
        console.print_json(data=report.to_dict())
        return

    # Rich output
    from rich.panel import Panel
    from rich.table import Table

    summary = (
        f"[bold]Annual Revenue:[/] ${report.annual_revenue_usd:,.0f}\n"
        f"[bold]Expected Annual Loss:[/] [red]${report.expected_annual_loss:,.2f}[/]\n"
        f"[bold]Value at Risk (95%):[/] [red]${report.value_at_risk_95:,.2f}[/]\n"
        f"[bold]Cost per Hour of Risk:[/] ${report.cost_per_hour_of_risk:,.2f}"
    )
    console.print()
    console.print(Panel(summary, title="[bold]Financial Risk Analysis[/]", border_style="red"))

    if report.scenarios:
        table = Table(title="Risk Scenarios", show_header=True)
        table.add_column("Scenario", width=30)
        table.add_column("Probability", justify="right", width=12)
        table.add_column("Loss (USD)", justify="right", width=15)
        table.add_column("Recovery (h)", justify="right", width=12)
        table.add_column("Expected Loss", justify="right", width=15)

        for s in report.scenarios[:15]:
            expected = s.probability * s.business_loss_usd
            table.add_row(
                s.scenario_name[:30],
                f"{s.probability:.2%}",
                f"${s.business_loss_usd:,.0f}",
                f"{s.recovery_hours:.1f}",
                f"${expected:,.0f}",
            )

        console.print()
        console.print(table)

    if report.mitigation_roi:
        roi_table = Table(title="Mitigation ROI", show_header=True)
        roi_table.add_column("Action", width=40)
        roi_table.add_column("Cost", justify="right", width=12)
        roi_table.add_column("Savings", justify="right", width=12)
        roi_table.add_column("ROI", justify="right", width=10)

        for m in report.mitigation_roi[:10]:
            roi_str = f"{m['roi_percent']:.0f}%" if m['roi_percent'] != float('inf') else "INF"
            roi_table.add_row(
                m["action"][:40],
                f"${m['cost']:,.0f}",
                f"${m['savings']:,.0f}",
                roi_str,
            )

        console.print()
        console.print(roi_table)


@app.command()
def carbon(
    yaml_file: Path = typer.Argument(..., help="Infrastructure YAML or JSON model file"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Carbon footprint analysis — estimate CO2 emissions.

    Calculates annual carbon emissions by component and region,
    with green infrastructure recommendations.

    Examples:
        # Basic analysis
        faultray carbon infra.yaml

        # JSON output
        faultray carbon infra.yaml --json
    """
    from faultray.simulator.carbon_engine import CarbonEngine

    graph = _load_graph_for_analysis(DEFAULT_MODEL_PATH, yaml_file)

    engine = CarbonEngine(graph)
    report = engine.analyze()

    if json_output:
        console.print_json(data=report.to_dict())
        return

    # Rich output
    from rich.panel import Panel
    from rich.table import Table

    summary = (
        f"[bold]Total Annual CO2:[/] {report.total_annual_kg:,.1f} kg\n"
        f"[bold]Equivalent Car Driving:[/] {report.equivalent_car_km:,.0f} km\n"
        f"[bold]Sustainability Score:[/] {report.sustainability_score:.0f}/100"
    )
    console.print()
    console.print(Panel(summary, title="[bold]Carbon Footprint Analysis[/]", border_style="green"))

    if report.per_component:
        table = Table(title="Per-Component Emissions", show_header=True)
        table.add_column("Component", width=20)
        table.add_column("CO2 (kg/year)", justify="right", width=15)
        table.add_column("% of Total", justify="right", width=10)

        sorted_components = sorted(
            report.per_component.items(), key=lambda x: x[1], reverse=True
        )
        for comp_id, kg in sorted_components:
            pct = (kg / report.total_annual_kg * 100) if report.total_annual_kg > 0 else 0
            table.add_row(comp_id, f"{kg:,.2f}", f"{pct:.1f}%")

        console.print()
        console.print(table)

    if report.green_recommendations:
        console.print("\n[bold green]Green Recommendations:[/]")
        for i, rec in enumerate(report.green_recommendations[:10], 1):
            savings = rec.get("potential_savings_kg", 0)
            console.print(f"  {i}. {rec['recommendation']} (saves {savings:.1f} kg CO2/year)")


@app.command()
def leaderboard(
    yaml_file: Path | None = typer.Argument(None, help="Infrastructure YAML file (optional, for --submit)"),
    submit: bool = typer.Option(False, "--submit", help="Submit current score to leaderboard"),
    team: str = typer.Option("default", "--team", "-t", help="Team name"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Resilience leaderboard — compete for the best resilience score.

    View the leaderboard or submit your infrastructure's score.

    Examples:
        # View leaderboard
        faultray leaderboard

        # Submit score
        faultray leaderboard infra.yaml --submit --team "SRE Team Alpha"

        # JSON output
        faultray leaderboard --json
    """
    from faultray.api.leaderboard import get_leaderboard_store

    store = get_leaderboard_store()

    if submit:
        if yaml_file is None:
            console.print("[red]YAML file required for --submit[/]")
            raise typer.Exit(1)

        graph = _load_graph_for_analysis(DEFAULT_MODEL_PATH, yaml_file)

        score = graph.resilience_score()
        components = len(graph.components)

        entry = store.submit(
            team_name=team,
            score=score,
            components=components,
            graph=graph,
        )

        if json_output:
            console.print_json(data={
                "team_name": entry.team_name,
                "score": round(entry.score, 1),
                "rank": entry.rank,
                "score_delta": round(entry.score_delta, 1),
                "badges": entry.badges,
            })
            return

        console.print(f"\n[green]Score submitted for team '{entry.team_name}'[/]")
        console.print(f"  Score: [bold]{entry.score:.1f}[/]")
        console.print(f"  Rank: #{entry.rank}")
        if entry.badges:
            console.print(f"  Badges: {', '.join(entry.badges)}")
        if entry.score_delta != 0:
            delta_color = "green" if entry.score_delta > 0 else "red"
            console.print(f"  Delta: [{delta_color}]{entry.score_delta:+.1f}[/]")
        return

    # Show leaderboard
    entries = store.get_leaderboard()

    if json_output:
        data = {
            "leaderboard": [
                {
                    "rank": e.rank,
                    "team_name": e.team_name,
                    "score": round(e.score, 1),
                    "badges": e.badges,
                }
                for e in entries
            ],
        }
        console.print_json(data=data)
        return

    if not entries:
        console.print("\n[yellow]Leaderboard is empty. Submit a score with --submit[/]")
        return

    from rich.table import Table

    table = Table(title="Resilience Leaderboard", show_header=True)
    table.add_column("Rank", justify="center", width=6)
    table.add_column("Team", width=25)
    table.add_column("Score", justify="right", width=8)
    table.add_column("Delta", justify="right", width=8)
    table.add_column("Badges", width=30)

    for e in entries:
        delta_str = ""
        if e.score_delta != 0:
            delta_color = "green" if e.score_delta > 0 else "red"
            delta_str = f"[{delta_color}]{e.score_delta:+.1f}[/]"

        table.add_row(
            f"#{e.rank}",
            e.team_name,
            f"{e.score:.1f}",
            delta_str,
            ", ".join(e.badges) if e.badges else "",
        )

    console.print()
    console.print(table)
