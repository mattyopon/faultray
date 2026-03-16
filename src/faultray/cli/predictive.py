"""CLI commands for P2 engines: predict, markov, bayesian, gameday."""

from __future__ import annotations

import json as json_lib
from pathlib import Path

import typer

from faultray.cli.main import (
    app,
    console,
)


@app.command()
def predict(
    yaml_file: Path = typer.Argument(..., help="Infrastructure YAML file"),
    horizon: int = typer.Option(90, "--horizon", help="Prediction horizon in days"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Predict future failures from degradation trends and MTBF data.

    Examples:
        # Default 90-day prediction
        faultray predict infra.yaml

        # Predict over 180 days
        faultray predict infra.yaml --horizon 180

        # JSON output
        faultray predict infra.yaml --json
    """
    from faultray.model.loader import load_yaml
    from faultray.simulator.predictive_engine import PredictiveEngine

    if not yaml_file.exists():
        console.print(f"[red]File not found: {yaml_file}[/]")
        raise typer.Exit(1)

    try:
        graph = load_yaml(yaml_file)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)

    engine = PredictiveEngine(graph)
    report = engine.predict(horizon_days=horizon)

    if json_output:
        import dataclasses

        data = dataclasses.asdict(report)
        console.print_json(json_lib.dumps(data, indent=2, default=str))
        return

    # Rich output
    from rich.panel import Panel
    from rich.table import Table

    console.print()
    console.print(Panel(
        report.summary,
        title=f"[bold]Predictive Analysis (horizon={horizon}d)[/]",
        border_style="cyan",
    ))

    if report.exhaustion_predictions:
        table = Table(title="Resource Exhaustion Predictions", show_header=True)
        table.add_column("Component", style="cyan", width=16)
        table.add_column("Resource", width=12)
        table.add_column("Current %", justify="right", width=10)
        table.add_column("Rate/hr", justify="right", width=10)
        table.add_column("Days Left", justify="right", width=10)
        table.add_column("Action", width=40)

        for p in report.exhaustion_predictions:
            days_color = "red" if p.days_to_exhaustion <= 7 else (
                "yellow" if p.days_to_exhaustion <= 30 else "green"
            )
            table.add_row(
                p.component_id,
                p.resource,
                f"{p.current_usage_percent:.1f}%",
                f"{p.growth_rate_per_hour:.4f}%",
                f"[{days_color}]{p.days_to_exhaustion:.1f}[/]",
                p.recommended_action[:40],
            )
        console.print(table)

    if report.failure_forecasts:
        table = Table(title="Failure Probability Forecast", show_header=True)
        table.add_column("Component", style="cyan", width=16)
        table.add_column("MTBF (h)", justify="right", width=10)
        table.add_column("P(7d)", justify="right", width=10)
        table.add_column("P(30d)", justify="right", width=10)
        table.add_column("P(90d)", justify="right", width=10)

        for f in report.failure_forecasts:
            table.add_row(
                f.component_id,
                f"{f.mtbf_hours:.0f}",
                f"{f.probability_7d:.4f}",
                f"{f.probability_30d:.4f}",
                f"{f.probability_90d:.4f}",
            )
        console.print()
        console.print(table)

    console.print(f"\n[dim]{report.recommended_maintenance_window}[/]")


@app.command()
def markov(
    yaml_file: Path = typer.Argument(..., help="Infrastructure YAML file"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Compute Markov chain steady-state availability for each component.

    Examples:
        # Run Markov analysis
        faultray markov infra.yaml

        # JSON output
        faultray markov infra.yaml --json
    """
    from faultray.model.loader import load_yaml
    from faultray.simulator.markov_model import compute_system_markov

    if not yaml_file.exists():
        console.print(f"[red]File not found: {yaml_file}[/]")
        raise typer.Exit(1)

    try:
        graph = load_yaml(yaml_file)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)

    results = compute_system_markov(graph)

    if json_output:
        import dataclasses

        data = {
            comp_id: dataclasses.asdict(result)
            for comp_id, result in results.items()
        }
        console.print_json(json_lib.dumps(data, indent=2, default=str))
        return

    from rich.table import Table

    table = Table(title="Markov Chain Availability Analysis", show_header=True)
    table.add_column("Component", style="cyan", width=16)
    table.add_column("P(HEALTHY)", justify="right", width=12)
    table.add_column("P(DEGRADED)", justify="right", width=12)
    table.add_column("P(DOWN)", justify="right", width=12)
    table.add_column("Availability", justify="right", width=12)
    table.add_column("Nines", justify="right", width=8)

    for comp_id, result in results.items():
        avail_color = "green" if result.nines >= 3 else (
            "yellow" if result.nines >= 2 else "red"
        )
        table.add_row(
            comp_id,
            f"{result.steady_state.get('HEALTHY', 0):.6f}",
            f"{result.steady_state.get('DEGRADED', 0):.6f}",
            f"{result.steady_state.get('DOWN', 0):.6f}",
            f"[{avail_color}]{result.availability:.6f}[/]",
            f"[{avail_color}]{result.nines:.2f}[/]",
        )

    console.print()
    console.print(table)


@app.command()
def bayesian(
    yaml_file: Path = typer.Argument(..., help="Infrastructure YAML file"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Compute Bayesian conditional failure probabilities.

    Examples:
        # Run Bayesian analysis
        faultray bayesian infra.yaml

        # JSON output
        faultray bayesian infra.yaml --json
    """
    from faultray.model.loader import load_yaml
    from faultray.simulator.bayesian_model import BayesianEngine

    if not yaml_file.exists():
        console.print(f"[red]File not found: {yaml_file}[/]")
        raise typer.Exit(1)

    try:
        graph = load_yaml(yaml_file)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)

    engine = BayesianEngine(graph)
    results = engine.analyze()

    if json_output:
        import dataclasses

        data = [dataclasses.asdict(r) for r in results]
        console.print_json(json_lib.dumps(data, indent=2, default=str))
        return

    from rich.table import Table

    table = Table(title="Bayesian Failure Probability Analysis", show_header=True)
    table.add_column("Component", style="cyan", width=16)
    table.add_column("P(fail) prior", justify="right", width=14)
    table.add_column("P(fail|deps)", justify="right", width=14)
    table.add_column("Critical Dep", width=16)
    table.add_column("Impact", width=30)

    for r in results:
        impact_str = ", ".join(
            f"{k}={v:.4f}" for k, v in list(r.conditional_impacts.items())[:3]
        ) if r.conditional_impacts else "-"

        table.add_row(
            r.component_id,
            f"{r.prior_failure_prob:.6f}",
            f"{r.posterior_given_deps:.6f}",
            r.most_critical_dependency or "-",
            impact_str,
        )

    console.print()
    console.print(table)


@app.command()
def gameday(
    yaml_file: Path = typer.Argument(..., help="Infrastructure YAML file"),
    plan: Path = typer.Option(..., "--plan", "-p", help="Game Day plan YAML file"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Execute a Game Day exercise against an infrastructure model.

    Examples:
        # Run a game day exercise
        faultray gameday infra.yaml --plan gameday-plan.yaml

        # JSON output
        faultray gameday infra.yaml --plan gameday-plan.yaml --json
    """
    import yaml

    from faultray.model.loader import load_yaml
    from faultray.simulator.gameday_engine import (
        GameDayEngine,
        GameDayPlan,
        GameDayStep,
    )
    from faultray.simulator.scenarios import Fault, FaultType

    if not yaml_file.exists():
        console.print(f"[red]Infrastructure file not found: {yaml_file}[/]")
        raise typer.Exit(1)

    if not plan.exists():
        console.print(f"[red]Game Day plan not found: {plan}[/]")
        raise typer.Exit(1)

    try:
        graph = load_yaml(yaml_file)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)

    # Parse game day plan
    raw = yaml.safe_load(plan.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        console.print("[red]Game Day plan must be a YAML mapping.[/]")
        raise typer.Exit(1)

    steps: list[GameDayStep] = []
    for raw_step in raw.get("steps", []):
        fault = None
        if "fault" in raw_step and raw_step["fault"]:
            fault_data = raw_step["fault"]
            fault = Fault(
                target_component_id=fault_data["target_component_id"],
                fault_type=FaultType(fault_data["fault_type"]),
                severity=fault_data.get("severity", 1.0),
                duration_seconds=fault_data.get("duration_seconds", 300),
            )
        steps.append(GameDayStep(
            time_offset_seconds=raw_step.get("time_offset_seconds", 0),
            action=raw_step.get("action", "manual_check"),
            fault=fault,
            expected_outcome=raw_step.get("expected_outcome", ""),
            runbook_step=raw_step.get("runbook_step", ""),
        ))

    gameday_plan = GameDayPlan(
        name=raw.get("name", "Unnamed Game Day"),
        description=raw.get("description", ""),
        steps=steps,
        success_criteria=raw.get("success_criteria", []),
        rollback_plan=raw.get("rollback_plan", ""),
    )

    engine = GameDayEngine(graph)
    report = engine.execute(gameday_plan)

    if json_output:
        import dataclasses

        data = dataclasses.asdict(report)
        console.print_json(json_lib.dumps(data, indent=2, default=str))
        return

    from rich.panel import Panel
    from rich.table import Table

    overall_color = "green" if report.overall == "PASS" else "red"
    console.print()
    console.print(Panel(
        f"[bold]Plan:[/] {report.plan_name}\n"
        f"[bold]Steps:[/] {len(report.steps)} total, "
        f"[green]{report.passed} passed[/], "
        f"[red]{report.failed} failed[/]\n"
        f"[bold]Overall:[/] [{overall_color}]{report.overall}[/]",
        title="[bold]Game Day Report[/]",
        border_style=overall_color,
    ))

    table = Table(title="Step Results", show_header=True)
    table.add_column("Step", width=6, justify="right")
    table.add_column("Time", width=8, justify="right")
    table.add_column("Action", width=16)
    table.add_column("Outcome", width=8, justify="center")
    table.add_column("Details", width=50)

    for r in report.steps:
        outcome_color = (
            "green" if r.outcome == "PASS" else
            "red" if r.outcome == "FAIL" else "yellow"
        )
        table.add_row(
            str(r.step_index),
            f"T+{r.time_seconds}s",
            r.action,
            f"[{outcome_color}]{r.outcome}[/]",
            r.details[:50],
        )

    console.print(table)

    if report.timeline_summary:
        console.print(f"\n[dim]{report.timeline_summary}[/]")
