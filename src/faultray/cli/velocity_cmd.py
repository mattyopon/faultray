"""CLI command for Change Velocity Impact Analysis."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console


@app.command("velocity")
def velocity(
    model_file: Path = typer.Argument(
        ...,
        help="Path to YAML/JSON infrastructure model file.",
    ),
    deploys_per_week: float = typer.Option(
        10.0, "--deploys-per-week", "-d",
        help="Number of deployments per week.",
    ),
    cfr: float = typer.Option(
        5.0, "--cfr",
        help="Change failure rate (percentage of deploys causing incidents).",
    ),
    mttr: float = typer.Option(
        60.0, "--mttr",
        help="Mean time to recovery in minutes.",
    ),
    lead_time: float = typer.Option(
        24.0, "--lead-time",
        help="Lead time from commit to production in hours.",
    ),
    sweep: bool = typer.Option(
        False, "--sweep",
        help="Run velocity sweep across multiple deploy frequencies.",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON.",
    ),
) -> None:
    """Analyze how deployment velocity affects infrastructure stability.

    Uses the DORA metrics framework to classify deployment performance
    and estimate the impact of change velocity on system availability.

    Examples:
        faultray velocity infra.yaml --deploys-per-week 10 --cfr 5
        faultray velocity infra.yaml --deploys-per-week 50 --cfr 3 --mttr 15 --json
        faultray velocity infra.yaml --sweep --json
    """
    from faultray.simulator.change_velocity import ChangeVelocityAnalyzer

    graph = _load_graph_for_analysis(model_file, None)
    analyzer = ChangeVelocityAnalyzer(graph)

    if sweep:
        if not json_output:
            console.print("[cyan]Running velocity sweep analysis...[/]")

        results = analyzer.simulate_velocity_sweep(
            change_failure_rate=cfr,
            mttr_minutes=mttr,
            lead_time_hours=lead_time,
        )

        if json_output:
            console.print_json(data=results)
            return

        sweep_table = Table(title="Velocity Sweep Analysis", show_header=True)
        sweep_table.add_column("Deploys/Week", justify="right", width=14)
        sweep_table.add_column("DORA Class", width=10)
        sweep_table.add_column("Stability", justify="right", width=10)
        sweep_table.add_column("Est. Downtime", justify="right", width=14)
        sweep_table.add_column("Optimal Freq", justify="right", width=12)

        for r in results:
            dora = r["dora_classification"]
            dora_colors = {
                "Elite": "bold green", "High": "green",
                "Medium": "yellow", "Low": "red",
            }
            dc = dora_colors.get(dora, "white")

            stability = r["stability_impact"]
            sc = "green" if stability >= 70 else "yellow" if stability >= 50 else "red"

            sweep_table.add_row(
                f"{r['deploys_per_week']:.0f}",
                f"[{dc}]{dora}[/]",
                f"[{sc}]{stability:.1f}[/]",
                f"{r['estimated_downtime_minutes_per_week']:.1f}min",
                f"{r['optimal_deploy_frequency']:.1f}",
            )

        console.print()
        console.print(sweep_table)
        console.print()
        return

    # Single analysis
    if not json_output:
        console.print(
            f"[cyan]Analyzing change velocity "
            f"({deploys_per_week} deploys/week, {cfr}% CFR, "
            f"{mttr}min MTTR, {lead_time}h lead time)...[/]"
        )

    report = analyzer.analyze(
        deploys_per_week=deploys_per_week,
        change_failure_rate=cfr,
        mttr_minutes=mttr,
        lead_time_hours=lead_time,
    )

    if json_output:
        data = {
            "current_velocity": {
                "deploys_per_week": report.current_velocity.deploys_per_week,
                "change_failure_rate": report.current_velocity.change_failure_rate,
                "mttr_minutes": report.current_velocity.mttr_minutes,
                "lead_time_hours": report.current_velocity.lead_time_hours,
            },
            "dora_classification": report.dora_classification,
            "dora_scores": report.dora_scores,
            "stability_impact": report.stability_impact,
            "optimal_deploy_frequency": report.optimal_deploy_frequency,
            "estimated_downtime_minutes_per_week": report.estimated_downtime_minutes_per_week,
            "recommendations": report.recommendations,
            "architecture_risk_factors": report.architecture_risk_factors,
        }
        console.print_json(data=data)
        return

    # Rich output
    dora_colors = {
        "Elite": "bold green", "High": "green",
        "Medium": "yellow", "Low": "red",
    }
    dora_color = dora_colors.get(report.dora_classification, "white")

    stability = report.stability_impact
    if stability >= 70:
        stability_color = "green"
    elif stability >= 50:
        stability_color = "yellow"
    else:
        stability_color = "red"

    summary = (
        f"[bold]DORA Classification:[/] [{dora_color}]{report.dora_classification}[/]\n\n"
        f"[bold]Deploys/Week:[/] {report.current_velocity.deploys_per_week}\n"
        f"[bold]Change Failure Rate:[/] {report.current_velocity.change_failure_rate}%\n"
        f"[bold]MTTR:[/] {report.current_velocity.mttr_minutes} minutes\n"
        f"[bold]Lead Time:[/] {report.current_velocity.lead_time_hours} hours\n\n"
        f"[bold]Stability Impact:[/] [{stability_color}]{stability:.1f}/100[/]\n"
        f"[bold]Est. Weekly Downtime:[/] {report.estimated_downtime_minutes_per_week:.1f} minutes\n"
        f"[bold]Optimal Deploy Frequency:[/] {report.optimal_deploy_frequency:.1f} deploys/week"
    )

    console.print()
    console.print(Panel(
        summary,
        title="[bold]Change Velocity Impact Analysis[/]",
        border_style=dora_color,
    ))

    # DORA scores breakdown
    if report.dora_scores:
        dora_table = Table(title="DORA Metric Scores", show_header=True)
        dora_table.add_column("Metric", style="cyan", width=25)
        dora_table.add_column("Classification", width=12, justify="center")

        for metric, classification in report.dora_scores.items():
            mc = dora_colors.get(classification, "white")
            dora_table.add_row(
                metric.replace("_", " ").title(),
                f"[{mc}]{classification}[/]",
            )

        console.print()
        console.print(dora_table)

    # Architecture risk factors
    if report.architecture_risk_factors:
        console.print()
        console.print("[bold yellow]Architecture Risk Factors:[/]")
        for risk in report.architecture_risk_factors:
            console.print(f"  [yellow]- {risk}[/]")

    # Recommendations
    if report.recommendations:
        console.print()
        console.print("[bold green]Recommendations:[/]")
        for rec in report.recommendations:
            console.print(f"  -> {rec}")

    console.print()
