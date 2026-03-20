# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Ops-related CLI commands: ops-sim, whatif, capacity."""

from __future__ import annotations

from pathlib import Path

import typer

from faultray.cli.main import (
    DEFAULT_MODEL_PATH,
    InfraGraph,
    _load_graph_for_analysis,
    _print_multi_whatif_result,
    _print_ops_results,
    _print_whatif_result,
    app,
    console,
)


def _ops_result_to_json(result: object) -> dict:
    """Convert an OpsSimulationResult to a JSON-serialisable dict."""
    scenario = getattr(result, "scenario", None)
    sli_timeline = getattr(result, "sli_timeline", [])

    avg_avail = 100.0
    if sli_timeline:
        avg_avail = sum(p.availability_percent for p in sli_timeline) / len(sli_timeline)

    return {
        "scenario": getattr(scenario, "name", "unknown") if scenario else "unknown",
        "duration_days": getattr(scenario, "duration_days", 0) if scenario else 0,
        "avg_availability": round(avg_avail, 4),
        "min_availability": round(getattr(result, "min_availability", 100.0), 2),
        "total_downtime_seconds": round(getattr(result, "total_downtime_seconds", 0.0), 1),
        "total_events": len(getattr(result, "events", [])),
        "total_deploys": getattr(result, "total_deploys", 0),
        "total_failures": getattr(result, "total_failures", 0),
        "total_degradation_events": getattr(result, "total_degradation_events", 0),
        "peak_utilization": round(getattr(result, "peak_utilization", 0.0), 1),
    }


@app.command()
def ops_sim(
    yaml_pos: Path | None = typer.Argument(None, help="YAML file path (positional)"),
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path (JSON or YAML)"),
    yaml_file: Path | None = typer.Option(None, "--yaml", "-y", help="YAML file with ops config"),
    days: int = typer.Option(7, "--days", help="Simulation duration in days (1-30)"),
    step: str = typer.Option("5min", "--step", help="Time step: 1min, 5min, 1hour"),
    html: Path | None = typer.Option(None, "--html", help="Export HTML report"),
    growth: float = typer.Option(0.0, "--growth", help="Monthly traffic growth rate (0.1 = 10%)"),
    diurnal_peak: float = typer.Option(3.0, "--diurnal-peak", help="Diurnal peak multiplier"),
    weekend_factor: float = typer.Option(0.6, "--weekend-factor", help="Weekend traffic reduction"),
    deploy_days: str | None = typer.Option(None, "--deploy-days", help="Deploy days (e.g., 'tue,thu')"),
    deploy_hour: int = typer.Option(14, "--deploy-hour", help="Deploy hour (0-23)"),
    no_random: bool = typer.Option(False, "--no-random-failures", help="Disable random failures"),
    no_degradation: bool = typer.Option(False, "--no-degradation", help="Disable degradation"),
    no_maintenance: bool = typer.Option(False, "--no-maintenance", help="Disable maintenance windows"),
    defaults: bool = typer.Option(False, "--defaults", help="Run all default ops scenarios"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON summary"),
) -> None:
    """Run long-running operational simulation with SLO tracking.

    Examples:
        # Run with all default scenarios
        faultray ops-sim infra.yaml --defaults

        # Custom 14-day simulation
        faultray ops-sim --yaml infra.yaml --days 14

        # Fine-grained time steps
        faultray ops-sim infra.yaml --step 1min --days 3

        # Customize traffic pattern
        faultray ops-sim infra.yaml --diurnal-peak 5.0 --weekend-factor 0.4

        # Custom deploy schedule
        faultray ops-sim infra.yaml --deploy-days mon,wed,fri --deploy-hour 10

        # Disable random failures for deterministic output
        faultray ops-sim infra.yaml --no-random-failures --no-degradation

        # Add traffic growth
        faultray ops-sim infra.yaml --growth 0.15

        # JSON output
        faultray ops-sim infra.yaml --json
    """
    yaml_file = yaml_pos or yaml_file
    from faultray.model.components import SLOTarget
    from faultray.simulator.ops_engine import OpsScenario, OpsSimulationEngine

    # Resolve time step to seconds
    step_map = {"1min": 60, "5min": 300, "1hour": 3600}
    step_seconds = step_map.get(step)
    if step_seconds is None:
        console.print(f"[red]Invalid step '{step}'. Use: 1min, 5min, 1hour[/]")
        raise typer.Exit(1)

    # Validate days
    if days < 1 or days > 30:
        console.print("[red]--days must be between 1 and 30[/]")
        raise typer.Exit(1)

    if diurnal_peak < 1.0:
        console.print("[red]--diurnal-peak must be >= 1.0[/]")
        raise typer.Exit(1)

    if deploy_hour < 0 or deploy_hour > 23:
        console.print("[red]--deploy-hour must be between 0 and 23[/]")
        raise typer.Exit(1)

    # Load model
    graph: InfraGraph
    slos: list[SLOTarget] = []
    ops_config: dict = {}

    if yaml_file is not None:
        from faultray.model.loader import load_yaml_with_ops

        if not yaml_file.exists():
            console.print(f"[red]YAML file not found: {yaml_file}[/]")
            raise typer.Exit(1)

        console.print(f"[cyan]Loading infrastructure from YAML: {yaml_file}...[/]")
        try:
            graph, ops_config = load_yaml_with_ops(yaml_file)
        except (FileNotFoundError, ValueError) as exc:
            console.print(f"[red]{exc}[/]")
            raise typer.Exit(1)
        slos = ops_config.get("slos", [])
    elif model.exists():
        if str(model).endswith((".yaml", ".yml")):
            from faultray.model.loader import load_yaml_with_ops

            console.print(f"[cyan]Loading infrastructure from YAML: {model}...[/]")
            try:
                graph, ops_config = load_yaml_with_ops(model)
            except (FileNotFoundError, ValueError) as exc:
                console.print(f"[red]{exc}[/]")
                raise typer.Exit(1)
            slos = ops_config.get("slos", [])
        else:
            console.print(f"[cyan]Loading infrastructure model from {model}...[/]")
            graph = InfraGraph.load(model)
    else:
        console.print(f"[red]Model file not found: {model}[/]")
        console.print("Run [cyan]faultray scan[/] or [cyan]faultray load[/] first.")
        raise typer.Exit(1)

    # Collect SLOs from components if not from YAML global section
    if not slos:
        for comp in graph.components.values():
            slos.extend(comp.slo_targets)
    if not slos:
        slos = [
            SLOTarget(name="Availability", metric="availability", target=99.9, unit="percent"),
            SLOTarget(name="Error Rate", metric="error_rate", target=0.1, unit="percent"),
        ]

    engine = OpsSimulationEngine(graph)

    if defaults:
        from faultray.simulator.ops_engine import TimeUnit
        step_unit_map = {"1min": TimeUnit.MINUTE, "5min": TimeUnit.FIVE_MINUTES, "1hour": TimeUnit.HOUR}
        time_unit_override = step_unit_map.get(step)
        if not json_output:
            console.print(
                f"[cyan]Running all default operational simulations "
                f"({len(graph.components)} components)...[/]"
            )
        results = engine.run_default_ops_scenarios(time_unit_override=time_unit_override if step != "5min" else None)
        if json_output:
            console.print_json(data={"scenarios": [_ops_result_to_json(r) for r in results]})
            return
        for result in results:
            _print_ops_results(result, console)
            console.print()
    else:
        from faultray.simulator.traffic import create_diurnal_weekly, create_growth_trend

        # Parse deploy days into day_of_week integers (0=Mon)
        day_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
        parsed_deploy_days: list[int] = []
        if deploy_days is not None:
            for d in deploy_days.split(","):
                d = d.strip().lower()
                if d in day_map:
                    parsed_deploy_days.append(day_map[d])
        else:
            parsed_deploy_days = [1, 3]  # Tue, Thu

        # Build deploy schedule for app_server components
        deploy_targets = [
            cid for cid, c in graph.components.items()
            if c.type.value in ("app_server", "web_server")
        ]
        if not deploy_targets:
            deploy_targets = list(graph.components.keys())[:2]

        scheduled_deploys = []
        for dow in parsed_deploy_days:
            for comp_id in deploy_targets:
                scheduled_deploys.append({
                    "component_id": comp_id,
                    "day_of_week": dow,
                    "hour": deploy_hour,
                    "downtime_seconds": 30,
                })

        # Build traffic patterns
        duration_seconds = days * 86400
        traffic_patterns = [
            create_diurnal_weekly(peak=diurnal_peak, duration=duration_seconds, weekend_factor=weekend_factor),
        ]
        if growth > 0:
            traffic_patterns.append(create_growth_trend(monthly_rate=growth, duration=duration_seconds))

        scenario = OpsScenario(
            id=f"ops-custom-{days}d",
            name=f"Custom ({days}d, step={step})",
            duration_days=days,
            traffic_patterns=traffic_patterns,
            scheduled_deploys=scheduled_deploys,
            enable_random_failures=not no_random,
            enable_degradation=not no_degradation,
            enable_maintenance=not no_maintenance,
        )

        if not json_output:
            console.print(
                f"[cyan]Running operational simulation "
                f"({len(graph.components)} components, "
                f"{days} days, step={step})...[/]"
            )
        result = engine.run_ops_scenario(scenario)
        if json_output:
            console.print_json(data=_ops_result_to_json(result))
            return
        _print_ops_results(result, console)

    if html:
        console.print("\n[dim]HTML export for ops-sim is not yet implemented.[/]")


@app.command()
def whatif(
    yaml_pos: Path | None = typer.Argument(None, help="YAML file path (positional)"),
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Path to model JSON"),
    yaml_file: Path | None = typer.Option(None, "--yaml", help="Path to YAML (alternative to model)"),
    parameter: str | None = typer.Option(
        None, "--parameter", help="Parameter to sweep (mttr_factor, mtbf_factor, traffic_factor, replica_factor, maint_duration_factor)"
    ),
    values: str | None = typer.Option(None, "--values", help="Comma-separated values (e.g., '0.5,1.0,2.0')"),
    defaults: bool = typer.Option(False, "--defaults", help="Run all 5 default what-if analyses"),
    multi: str | None = typer.Option(
        None, "--multi", help="Multi-parameter what-if (e.g., 'mttr_factor=2.0,traffic_factor=3.0')"
    ),
) -> None:
    """Run what-if analysis by sweeping infrastructure parameters.

    Examples:
        # Run all default what-if analyses
        faultray whatif infra.yaml --defaults

        # Sweep a single parameter
        faultray whatif infra.yaml --parameter mttr_factor --values 0.5,1.0,2.0,5.0

        # Multi-parameter what-if
        faultray whatif infra.yaml --multi "mttr_factor=2.0,traffic_factor=3.0"

        # Run default multi-parameter combinations
        faultray whatif infra.yaml --multi defaults
    """
    resolved_yaml = yaml_pos or yaml_file
    try:
        from faultray.simulator.whatif_engine import WhatIfEngine
    except ImportError:
        console.print("[red]What-if engine not available. Install faultray with what-if support.[/]")
        raise typer.Exit(1)

    graph = _load_graph_for_analysis(model, resolved_yaml)
    engine = WhatIfEngine(graph)

    if multi is not None:
        from faultray.simulator.whatif_engine import MultiWhatIfScenario

        if multi.lower() == "defaults":
            # --multi defaults: run default combinations
            console.print(f"[cyan]Running default multi-parameter what-if analyses ({len(graph.components)} components)...[/]")
            multi_results = engine.run_default_multi_whatifs()
            for mresult in multi_results:
                _print_multi_whatif_result(mresult, console)
                console.print()
        else:
            # Parse "mttr_factor=2.0,traffic_factor=3.0" into dict
            params: dict[str, float] = {}
            for pair in multi.split(","):
                pair = pair.strip()
                if "=" not in pair:
                    console.print(f"[red]Invalid parameter format: '{pair}'. Expected 'name=value'.[/]")
                    raise typer.Exit(1)
                key, val = pair.split("=", 1)
                params[key.strip()] = float(val.strip())

            console.print(f"[cyan]Running multi-parameter what-if: {params}...[/]")
            scenario = MultiWhatIfScenario(
                base_scenario=engine._create_default_base_scenario(),
                parameters=params,
                description=f"Custom multi what-if: {params}",
            )
            mresult = engine.run_multi_whatif(scenario)
            _print_multi_whatif_result(mresult, console)
    elif defaults:
        console.print(f"[cyan]Running all default what-if analyses ({len(graph.components)} components)...[/]")
        all_results = engine.run_default_whatifs()
        for result in all_results:
            _print_whatif_result(result, console)
            console.print()
    elif parameter and values:
        from faultray.simulator.whatif_engine import WhatIfScenario

        parsed_values = [float(v.strip()) for v in values.split(",")]
        console.print(f"[cyan]Running what-if analysis: {parameter} = {parsed_values}...[/]")
        scenario = WhatIfScenario(
            base_scenario=engine._create_default_base_scenario(),
            parameter=parameter,
            values=parsed_values,
            description=f"Custom sweep: {parameter}",
        )
        result = engine.run_whatif(scenario)
        _print_whatif_result(result, console)
    else:
        console.print("[red]Specify --defaults, --multi, or both --parameter and --values.[/]")
        raise typer.Exit(1)


@app.command()
def capacity(
    yaml_pos: Path | None = typer.Argument(None, help="YAML file path (positional)"),
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Path to model JSON"),
    yaml_file: Path | None = typer.Option(None, "--yaml", help="Path to YAML (alternative to model)"),
    growth: float = typer.Option(0.10, "--growth", help="Monthly growth rate (default: 0.10 = 10%)"),
    slo: float = typer.Option(99.9, "--slo", help="SLO target (default: 99.9)"),
    simulate: bool = typer.Option(False, "--simulate", help="Run ops simulation to get actual burn rate"),
) -> None:
    """Run capacity planning analysis with growth forecasting.

    Examples:
        # Basic capacity forecast
        faultray capacity infra.yaml

        # Custom growth rate (20% monthly)
        faultray capacity infra.yaml --growth 0.20

        # Stricter SLO target
        faultray capacity infra.yaml --slo 99.99

        # Include ops simulation for actual burn rate
        faultray capacity infra.yaml --simulate

        # Use JSON model
        faultray capacity --model model.json
    """
    resolved_yaml = yaml_pos or yaml_file

    # Validate --growth is between -1.0 and 10.0
    if growth < -1.0 or growth > 10.0:
        console.print("[red]Error: --growth must be between -1.0 and 10.0[/]")
        raise typer.Exit(1)

    # Validate --slo is between 0 and 100
    if slo < 0 or slo > 100:
        console.print("[red]Error: --slo must be between 0 and 100[/]")
        raise typer.Exit(1)

    try:
        from faultray.simulator.capacity_engine import CapacityPlanningEngine
    except ImportError:
        console.print("[red]Capacity planning engine not available. Install faultray with capacity support.[/]")
        raise typer.Exit(1)

    graph = _load_graph_for_analysis(model, resolved_yaml)

    from rich.panel import Panel
    from rich.table import Table

    console.print(f"[cyan]Running capacity planning ({len(graph.components)} components, growth={growth:.0%}/mo, SLO={slo}%)...[/]")
    engine = CapacityPlanningEngine(graph)

    if simulate:
        report = engine.forecast_with_simulation(
            monthly_growth_rate=growth, slo_target=slo,
        )
    else:
        report = engine.forecast(
            monthly_growth_rate=growth, slo_target=slo,
        )

    # ---- Component Forecasts ----
    forecasts = report.forecasts
    if forecasts:
        fc_table = Table(title="Component Forecasts", show_header=True)
        fc_table.add_column("Component", style="cyan", width=20)
        fc_table.add_column("Type", width=12)
        fc_table.add_column("Util", justify="right", width=6)
        fc_table.add_column("Mo\u219280%", justify="right", width=8)
        fc_table.add_column("Now", justify="right", width=5)
        fc_table.add_column("3mo", justify="right", width=5)
        fc_table.add_column("6mo", justify="right", width=5)
        fc_table.add_column("12mo", justify="right", width=5)
        fc_table.add_column("Urgency", justify="center", width=10)

        for fc in forecasts:
            import math
            months_str = f"{fc.months_to_capacity:.1f}" if math.isfinite(fc.months_to_capacity) else "\u221e"
            if fc.scaling_urgency == "healthy":
                urg_str = "[green]healthy[/]"
            elif fc.scaling_urgency == "warning":
                urg_str = "[yellow]warning[/]"
            else:
                urg_str = f"[red]{fc.scaling_urgency}[/]"

            fc_table.add_row(
                fc.component_id, fc.component_type,
                f"{fc.current_utilization:.0f}%", months_str,
                str(fc.current_replicas),
                str(fc.recommended_replicas_3m),
                str(fc.recommended_replicas_6m),
                str(fc.recommended_replicas_12m),
                urg_str,
            )

        console.print()
        console.print(fc_table)

    # ---- Right-Size Opportunities ----
    over_provisioned = [
        fc for fc in forecasts
        if fc.recommended_replicas_3m < fc.current_replicas
    ] if forecasts else []
    if over_provisioned:
        rs_table = Table(title="Right-Size Opportunities", show_header=True)
        rs_table.add_column("Component", style="cyan", width=20)
        rs_table.add_column("Type", width=12)
        rs_table.add_column("Util", justify="right", width=6)
        rs_table.add_column("Current", justify="right", width=8)
        rs_table.add_column("Recommended", justify="right", width=12)
        rs_table.add_column("Savings", justify="right", width=8)

        for fc in over_provisioned:
            diff = fc.current_replicas - fc.recommended_replicas_3m
            rs_table.add_row(
                fc.component_id,
                fc.component_type,
                f"{fc.current_utilization:.0f}%",
                str(fc.current_replicas),
                str(fc.recommended_replicas_3m),
                f"[green]-{diff}[/]",
            )

        console.print()
        console.print(rs_table)

    # ---- Error Budget Forecast ----
    eb = report.error_budget
    status_color = {"healthy": "green", "warning": "yellow", "critical": "red", "exhausted": "red"}.get(eb.status, "white")
    days_str = f"{eb.days_to_exhaustion:.1f} days" if eb.days_to_exhaustion is not None else "N/A"

    eb_text = (
        f"SLO Target: {eb.slo_target}%\n"
        f"Budget: {eb.budget_total_minutes:.1f} min | Consumed: {eb.budget_consumed_minutes:.1f} min ({eb.budget_consumed_percent:.1f}%)\n"
        f"Burn Rate: {eb.burn_rate_per_day:.2f} min/day\n"
        f"Projected Monthly: {eb.projected_monthly_consumption:.1f}%\n"
        f"Days to Exhaustion: {days_str}\n"
        f"Status: [{status_color}]{eb.status}[/]"
    )
    console.print()
    console.print(Panel(eb_text, title="[bold]Error Budget Forecast[/]"))

    # ---- Bottlenecks ----
    bottlenecks = report.bottleneck_components
    if bottlenecks:
        console.print("\n[bold]Bottlenecks (first to hit capacity):[/]")
        for i, comp_id in enumerate(bottlenecks[:10], 1):
            console.print(f"  {i}. {comp_id}")

    # ---- Recommendations ----
    recommendations = report.scaling_recommendations
    if recommendations:
        console.print("\n[bold]Recommendations:[/]")
        for rec in recommendations:
            console.print(f"  \u2022 {rec}")

    # ---- Cost ----
    console.print(f"\n[bold]Estimated 3-month cost increase:[/] {report.estimated_monthly_cost_increase:.1f}%")

    # ---- Summary ----
    console.print(f"\n{report.summary}")


@app.command()
def advise(
    yaml_pos: Path | None = typer.Argument(None, help="YAML file path (positional)"),
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path (JSON or YAML)"),
    yaml_file: Path | None = typer.Option(None, "--yaml", "-y", help="YAML file with infrastructure definition"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON summary"),
) -> None:
    """Auto-recommend chaos tests based on infrastructure topology analysis.

    Examples:
        # Get recommendations from YAML
        faultray advise infra.yaml

        # JSON output for integration
        faultray advise infra.yaml --json

        # Use a JSON model
        faultray advise --model model.json
    """
    from rich.panel import Panel
    from rich.table import Table

    from faultray.simulator.advisor_engine import ChaosAdvisorEngine

    resolved_yaml = yaml_pos or yaml_file
    graph = _load_graph_for_analysis(model, resolved_yaml)

    engine = ChaosAdvisorEngine(graph)
    report = engine.analyze()

    if json_output:
        import dataclasses

        data = {
            "total_recommendations": report.total_recommendations,
            "critical_count": report.critical_count,
            "coverage_score": report.coverage_score,
            "topology_insights": report.topology_insights,
            "recommendations": [
                dataclasses.asdict(r) for r in report.recommendations
            ],
        }
        console.print_json(data=data)
        return

    # Summary panel
    if report.coverage_score >= 80:
        score_color = "green"
    elif report.coverage_score >= 50:
        score_color = "yellow"
    else:
        score_color = "red"

    summary_text = (
        f"[bold]Recommendations:[/] {report.total_recommendations}\n"
        f"[bold]Critical:[/] [red]{report.critical_count}[/]\n"
        f"[bold]Coverage Score:[/] [{score_color}]{report.coverage_score:.1f}%[/]"
    )
    console.print()
    console.print(Panel(summary_text, title="[bold]Chaos Advisor Report[/]", border_style="cyan"))

    # Topology insights
    insights = report.topology_insights
    if insights:
        insight_text = (
            f"[bold]Nodes:[/] {insights.get('num_nodes', 0)}  "
            f"[bold]Edges:[/] {insights.get('num_edges', 0)}  "
            f"[bold]Density:[/] {insights.get('density', 0):.4f}\n"
            f"[bold]Longest Path:[/] {' -> '.join(insights.get('longest_path', []))}\n"
            f"[bold]Most Connected:[/] {insights.get('most_connected_component', 'N/A')} "
            f"(degree: {insights.get('most_connected_degree', 0)})"
        )
        console.print(Panel(insight_text, title="[bold]Topology Insights[/]", border_style="dim"))

    # Recommendations table
    if report.recommendations:
        table = Table(title="Recommended Chaos Tests", show_header=True)
        table.add_column("#", justify="right", width=4)
        table.add_column("Priority", justify="center", width=10)
        table.add_column("Scenario", style="cyan", width=35)
        table.add_column("Targets", width=20)
        table.add_column("Blast", justify="right", width=6)
        table.add_column("Reasoning", width=50)

        priority_colors = {
            "critical": "bold red",
            "high": "red",
            "medium": "yellow",
            "low": "green",
        }

        for idx, rec in enumerate(report.recommendations, 1):
            color = priority_colors.get(rec.priority, "white")
            table.add_row(
                str(idx),
                f"[{color}]{rec.priority.upper()}[/]",
                rec.scenario_name[:35],
                ", ".join(rec.target_components)[:20],
                str(rec.estimated_blast_radius),
                rec.reasoning[:50] + ("..." if len(rec.reasoning) > 50 else ""),
            )

        console.print()
        console.print(table)


@app.command(name="monte-carlo")
def monte_carlo_cmd(
    yaml_pos: Path | None = typer.Argument(None, help="YAML file path (positional)"),
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Path to model JSON or YAML"),
    yaml_file: Path | None = typer.Option(None, "--yaml", "-y", help="Path to YAML (alternative to model)"),
    n_trials: int = typer.Option(10000, "-n", "--trials", help="Number of Monte Carlo trials"),
    seed: int = typer.Option(42, "--seed", help="Random seed for reproducibility"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON summary"),
) -> None:
    """Run Monte Carlo availability simulation with stochastic MTBF/MTTR sampling.

    Examples:
        # Default 10,000 trials
        faultray monte-carlo infra.yaml

        # More trials for higher precision
        faultray monte-carlo infra.yaml --trials 100000

        # Custom random seed
        faultray monte-carlo infra.yaml --seed 123

        # JSON output
        faultray monte-carlo infra.yaml --json

        # Use JSON model
        faultray monte-carlo --model model.json
    """
    resolved_yaml = yaml_pos or yaml_file
    graph = _load_graph_for_analysis(model, resolved_yaml)

    from faultray.simulator.monte_carlo import run_monte_carlo

    if not json_output:
        console.print(
            f"[cyan]Running Monte Carlo simulation "
            f"({len(graph.components)} components, {n_trials:,} trials, seed={seed})...[/]"
        )

    result = run_monte_carlo(graph, n_trials=n_trials, seed=seed)

    if json_output:

        data = {
            "n_trials": result.n_trials,
            "availability_p50": round(result.availability_p50 * 100, 6),
            "availability_p95": round(result.availability_p95 * 100, 6),
            "availability_p99": round(result.availability_p99 * 100, 6),
            "availability_mean": round(result.availability_mean * 100, 6),
            "availability_std": round(result.availability_std * 100, 6),
            "annual_downtime_p50_seconds": round(result.annual_downtime_p50_seconds, 1),
            "annual_downtime_p95_seconds": round(result.annual_downtime_p95_seconds, 1),
            "confidence_interval_95_lower": round(result.confidence_interval_95[0] * 100, 6),
            "confidence_interval_95_upper": round(result.confidence_interval_95[1] * 100, 6),
        }
        console.print_json(data=data)
        return

    from rich.panel import Panel
    from rich.table import Table

    # Main results table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Metric", style="cyan", width=32)
    table.add_column("Value", justify="right", width=20)

    table.add_row("Trials", f"{result.n_trials:,}")
    table.add_row("Mean Availability", f"{result.availability_mean * 100:.6f}%")
    table.add_row("Std Deviation", f"{result.availability_std * 100:.6f}%")

    table.add_section()
    table.add_row("P50 (median)", f"{result.availability_p50 * 100:.6f}%")
    table.add_row("P95", f"{result.availability_p95 * 100:.6f}%")
    table.add_row("P99", f"{result.availability_p99 * 100:.6f}%")

    table.add_section()
    table.add_row("95% CI (lower)", f"{result.confidence_interval_95[0] * 100:.6f}%")
    table.add_row("95% CI (upper)", f"{result.confidence_interval_95[1] * 100:.6f}%")

    table.add_section()
    dt_p50_min = result.annual_downtime_p50_seconds / 60.0
    dt_p95_min = result.annual_downtime_p95_seconds / 60.0
    table.add_row("Annual Downtime (P50)", f"{result.annual_downtime_p50_seconds:.1f}s ({dt_p50_min:.1f}m)")
    table.add_row("Annual Downtime (P95)", f"{result.annual_downtime_p95_seconds:.1f}s ({dt_p95_min:.1f}m)")

    console.print()
    console.print(Panel(
        table,
        title=f"[bold]Monte Carlo Availability Simulation (n={result.n_trials:,})[/]",
        border_style="cyan",
    ))


@app.command()
def cost(
    yaml_pos: Path | None = typer.Argument(None, help="YAML file path (positional)"),
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path (JSON or YAML)"),
    yaml_file: Path | None = typer.Option(None, "--yaml", "-y", help="YAML file with infrastructure definition"),
    top: int = typer.Option(10, "--top", "-n", help="Number of top scenarios to display"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON summary"),
) -> None:
    """Estimate business cost impact of failure scenarios.

    Examples:
        # Cost analysis from YAML
        faultray cost infra.yaml

        # Show top 20 scenarios
        faultray cost infra.yaml --top 20

        # JSON output
        faultray cost infra.yaml --json

        # Use JSON model
        faultray cost --model model.json
    """
    from rich.panel import Panel
    from rich.table import Table

    from faultray.simulator.cost_engine import CostImpactEngine
    from faultray.simulator.engine import SimulationEngine

    resolved_yaml = yaml_pos or yaml_file
    graph = _load_graph_for_analysis(model, resolved_yaml)

    if not json_output:
        console.print(f"[cyan]Running cost impact analysis ({len(graph.components)} components)...[/]")

    # Run static simulation first.
    engine = SimulationEngine(graph)
    sim_report = engine.run_all_defaults()

    # Run cost engine on simulation results.
    cost_engine = CostImpactEngine(graph)
    cost_report = cost_engine.analyze(sim_report)

    if json_output:
        data = {
            "total_annual_risk": cost_report.total_annual_risk,
            "highest_impact_scenario": cost_report.highest_impact_scenario,
            "summary": cost_report.summary,
            "impacts": [
                {
                    "scenario_name": i.scenario_name,
                    "scenario_id": i.scenario_id,
                    "severity": i.severity,
                    "downtime_minutes": i.downtime_minutes,
                    "business_loss": i.business_loss,
                    "sla_penalty": i.sla_penalty,
                    "recovery_cost": i.recovery_cost,
                    "total_impact": i.total_impact,
                }
                for i in cost_report.impacts[:top]
            ],
        }
        console.print_json(data=data)
        return

    # ---- Summary Panel ----
    summary_text = (
        f"[bold]Scenarios analyzed:[/] {len(cost_report.impacts)}\n"
        f"[bold]Highest impact:[/] {cost_report.highest_impact_scenario}\n"
        f"[bold]Estimated annual risk:[/] ${cost_report.total_annual_risk:,.2f}\n\n"
        f"{cost_report.summary}"
    )
    console.print()
    console.print(Panel(summary_text, title="[bold]Cost Impact Analysis[/]", border_style="cyan"))

    # ---- Top N Scenarios Table ----
    display_impacts = cost_report.impacts[:top]
    if display_impacts:
        table = Table(
            title=f"Top {min(top, len(display_impacts))} Scenarios by Cost Impact",
            show_header=True,
        )
        table.add_column("#", justify="right", width=4)
        table.add_column("Scenario", style="cyan", width=35)
        table.add_column("Sev", justify="right", width=5)
        table.add_column("Downtime", justify="right", width=10)
        table.add_column("Biz Loss", justify="right", width=12)
        table.add_column("SLA Pen.", justify="right", width=12)
        table.add_column("Recovery", justify="right", width=10)
        table.add_column("Total", justify="right", width=14, style="bold")

        for idx, impact in enumerate(display_impacts, 1):
            # Color by severity.
            if impact.total_impact > 10000:
                total_str = f"[red]${impact.total_impact:,.2f}[/]"
            elif impact.total_impact > 1000:
                total_str = f"[yellow]${impact.total_impact:,.2f}[/]"
            else:
                total_str = f"[green]${impact.total_impact:,.2f}[/]"

            table.add_row(
                str(idx),
                impact.scenario_name[:35],
                f"{impact.severity:.1f}",
                f"{impact.downtime_minutes:.1f}m",
                f"${impact.business_loss:,.2f}",
                f"${impact.sla_penalty:,.2f}",
                f"${impact.recovery_cost:,.2f}",
                total_str,
            )

        console.print()
        console.print(table)


@app.command()
def compliance(
    yaml_pos: Path | None = typer.Argument(None, help="YAML file path (positional)"),
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path (JSON or YAML)"),
    yaml_file: Path | None = typer.Option(None, "--yaml", "-y", help="YAML file with infrastructure definition"),
    framework: str | None = typer.Option(None, "--framework", "-f", help="Framework to check: soc2, iso27001, pci_dss, nist_csf"),
    all_frameworks: bool = typer.Option(False, "--all", help="Check all frameworks"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON summary"),
) -> None:
    """Check infrastructure compliance against regulatory frameworks.

    Examples:
        # Check SOC 2 compliance
        faultray compliance infra.yaml --framework soc2

        # Check all frameworks
        faultray compliance infra.yaml --all

        # Check PCI DSS compliance
        faultray compliance infra.yaml --framework pci_dss

        # JSON output
        faultray compliance infra.yaml --json --all
    """
    from rich.panel import Panel
    from rich.table import Table

    from faultray.simulator.compliance_engine import ComplianceEngine

    resolved_yaml = yaml_pos or yaml_file
    graph = _load_graph_for_analysis(model, resolved_yaml)

    engine = ComplianceEngine(graph)

    valid_frameworks = {"soc2", "iso27001", "pci_dss", "nist_csf"}

    if all_frameworks:
        reports = engine.check_all()
    elif framework:
        if framework not in valid_frameworks:
            console.print(f"[red]Unknown framework '{framework}'. Valid: {sorted(valid_frameworks)}[/]")
            raise typer.Exit(1)
        check_method = getattr(engine, f"check_{framework}")
        reports = {framework: check_method()}
    else:
        console.print("[red]Specify --framework <name> or --all[/]")
        raise typer.Exit(1)

    if json_output:

        data: dict = {}
        for fw_name, report in reports.items():
            data[fw_name] = {
                "framework": report.framework,
                "total_checks": report.total_checks,
                "passed": report.passed,
                "failed": report.failed,
                "partial": report.partial,
                "compliance_percent": report.compliance_percent,
                "checks": [
                    {
                        "control_id": c.control_id,
                        "description": c.description,
                        "status": c.status,
                        "evidence": c.evidence,
                        "recommendation": c.recommendation,
                    }
                    for c in report.checks
                ],
            }
        console.print_json(data=data)
        return

    for fw_name, report in reports.items():
        # Framework summary
        if report.compliance_percent >= 80:
            pct_color = "green"
        elif report.compliance_percent >= 50:
            pct_color = "yellow"
        else:
            pct_color = "red"

        summary_text = (
            f"[bold]Framework:[/] {report.framework.upper()}\n"
            f"[bold]Compliance:[/] [{pct_color}]{report.compliance_percent:.1f}%[/]\n"
            f"[bold]Passed:[/] {report.passed}  "
            f"[bold]Failed:[/] {report.failed}  "
            f"[bold]Partial:[/] {report.partial}  "
            f"[bold]Total:[/] {report.total_checks}"
        )
        console.print()
        console.print(Panel(summary_text, title=f"[bold]Compliance: {report.framework.upper()}[/]", border_style=pct_color))

        # Checks table
        table = Table(show_header=True, header_style="bold")
        table.add_column("Control", style="cyan", width=12)
        table.add_column("Description", width=40)
        table.add_column("Status", justify="center", width=8)
        table.add_column("Evidence", width=40)
        table.add_column("Recommendation", width=35)

        for check in report.checks:
            if check.status == "pass":
                status_str = "[green]PASS[/]"
            elif check.status == "fail":
                status_str = "[red]FAIL[/]"
            elif check.status == "partial":
                status_str = "[yellow]PARTIAL[/]"
            else:
                status_str = "[dim]N/A[/]"

            table.add_row(
                check.control_id,
                check.description,
                status_str,
                check.evidence[:60],
                check.recommendation[:55] if check.recommendation else "",
            )

        console.print(table)


@app.command()
def dr(
    yaml_pos: Path | None = typer.Argument(None, help="YAML file path (positional)"),
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path (JSON or YAML)"),
    yaml_file: Path | None = typer.Option(None, "--yaml", "-y", help="YAML file with infrastructure definition"),
    scenario: str | None = typer.Option(None, "--scenario", "-s", help="Scenario: az-failure, region-failure, network-partition"),
    az: str | None = typer.Option(None, "--az", help="Availability zone for az-failure scenario"),
    region_name: str | None = typer.Option(None, "--region", "-r", help="Region for region-failure scenario"),
    region_a: str | None = typer.Option(None, "--region-a", help="First region for network-partition"),
    region_b: str | None = typer.Option(None, "--region-b", help="Second region for network-partition"),
    all_scenarios: bool = typer.Option(False, "--all", help="Run all DR scenarios"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON summary"),
) -> None:
    """Simulate disaster recovery scenarios (AZ failure, region failure, network partition).

    Examples:
        # Run all DR scenarios
        faultray dr infra.yaml --all

        # Simulate AZ failure
        faultray dr infra.yaml --scenario az-failure --az us-east-1a

        # Simulate region failure
        faultray dr infra.yaml --scenario region-failure --region us-east-1

        # Simulate network partition between regions
        faultray dr infra.yaml --scenario network-partition --region-a us-east-1 --region-b eu-west-1

        # JSON output
        faultray dr infra.yaml --json --all
    """
    from rich.panel import Panel
    from rich.table import Table

    from faultray.simulator.dr_engine import DREngine

    resolved_yaml = yaml_pos or yaml_file
    graph = _load_graph_for_analysis(model, resolved_yaml)

    engine = DREngine(graph)
    results: list = []

    if all_scenarios:
        results = engine.simulate_all()
        if not results:
            console.print("[yellow]No regions or AZs found in the infrastructure model. "
                          "Add 'region' configuration to components.[/]")
            return
    elif scenario == "az-failure":
        if not az:
            console.print("[red]--az is required for az-failure scenario[/]")
            raise typer.Exit(1)
        results = [engine.simulate_az_failure(az)]
    elif scenario == "region-failure":
        if not region_name:
            console.print("[red]--region is required for region-failure scenario[/]")
            raise typer.Exit(1)
        results = [engine.simulate_region_failure(region_name)]
    elif scenario == "network-partition":
        if not region_a or not region_b:
            console.print("[red]--region-a and --region-b are required for network-partition scenario[/]")
            raise typer.Exit(1)
        results = [engine.simulate_network_partition(region_a, region_b)]
    else:
        console.print("[red]Specify --scenario <type> or --all[/]")
        raise typer.Exit(1)

    if json_output:
        data = [
            {
                "scenario": r.scenario,
                "affected_components": r.affected_components,
                "surviving_components": r.surviving_components,
                "rpo_met": r.rpo_met,
                "rto_met": r.rto_met,
                "estimated_data_loss_seconds": r.estimated_data_loss_seconds,
                "estimated_recovery_seconds": r.estimated_recovery_seconds,
                "availability_during_dr": r.availability_during_dr,
            }
            for r in results
        ]
        console.print_json(data={"dr_results": data})
        return

    for result in results:
        # Color by availability
        if result.availability_during_dr >= 80:
            avail_color = "green"
        elif result.availability_during_dr >= 50:
            avail_color = "yellow"
        else:
            avail_color = "red"

        rpo_str = "[green]MET[/]" if result.rpo_met else "[red]VIOLATED[/]"
        rto_str = "[green]MET[/]" if result.rto_met else "[red]VIOLATED[/]"

        summary_text = (
            f"[bold]Scenario:[/] {result.scenario}\n"
            f"[bold]Availability:[/] [{avail_color}]{result.availability_during_dr:.1f}%[/]\n"
            f"[bold]Affected:[/] {len(result.affected_components)} components  "
            f"[bold]Surviving:[/] {len(result.surviving_components)} components\n"
            f"[bold]RPO:[/] {rpo_str}  "
            f"[bold]RTO:[/] {rto_str}\n"
            f"[bold]Est. Data Loss:[/] {result.estimated_data_loss_seconds:.0f}s  "
            f"[bold]Est. Recovery:[/] {result.estimated_recovery_seconds:.0f}s"
        )
        console.print()
        console.print(Panel(summary_text, title=f"[bold]DR Scenario: {result.scenario}[/]", border_style=avail_color))

        if result.affected_components:
            table = Table(title="Affected Components", show_header=True)
            table.add_column("Component ID", style="red", width=30)
            for cid in result.affected_components:
                table.add_row(cid)
            console.print(table)

        if result.surviving_components:
            table = Table(title="Surviving Components", show_header=True)
            table.add_column("Component ID", style="green", width=30)
            for cid in result.surviving_components:
                table.add_row(cid)
            console.print(table)


@app.command()
def security(
    yaml_pos: Path | None = typer.Argument(None, help="YAML file path (positional)"),
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path (JSON or YAML)"),
    yaml_file: Path | None = typer.Option(None, "--yaml", "-y", help="YAML file with infrastructure definition"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON summary"),
) -> None:
    """Simulate security attacks and evaluate resilience.

    Examples:
        # Run all attack simulations
        faultray security infra.yaml

        # JSON output
        faultray security infra.yaml --json

        # Use JSON model
        faultray security --model model.json
    """
    from rich.panel import Panel
    from rich.table import Table

    from faultray.simulator.security_engine import SecurityResilienceEngine

    resolved_yaml = yaml_pos or yaml_file
    graph = _load_graph_for_analysis(model, resolved_yaml)

    engine = SecurityResilienceEngine(graph)
    report = engine.simulate_all_attacks()

    if json_output:
        data = {
            "security_resilience_score": report.security_resilience_score,
            "total_attacks_simulated": report.total_attacks_simulated,
            "attacks_fully_mitigated": report.attacks_fully_mitigated,
            "attacks_partially_mitigated": report.attacks_partially_mitigated,
            "attacks_unmitigated": report.attacks_unmitigated,
            "worst_case_blast_radius": report.worst_case_blast_radius,
            "score_breakdown": report.score_breakdown,
            "results": [
                {
                    "attack_type": r.attack_type.value,
                    "entry_point": r.entry_point,
                    "blast_radius": r.blast_radius,
                    "defense_effectiveness": r.defense_effectiveness,
                    "estimated_downtime_minutes": r.estimated_downtime_minutes,
                    "data_at_risk": r.data_at_risk,
                    "compromised_components": r.compromised_components,
                    "mitigation_recommendations": r.mitigation_recommendations,
                }
                for r in report.results
            ],
        }
        console.print_json(data=data)
        return

    # ---- Summary Panel ----
    score = report.security_resilience_score
    if score >= 80:
        score_color = "green"
    elif score >= 50:
        score_color = "yellow"
    else:
        score_color = "red"

    summary_text = (
        f"[bold]Security Resilience Score:[/] [{score_color}]{score:.1f}/100[/]\n"
        f"[bold]Attacks Simulated:[/] {report.total_attacks_simulated}\n"
        f"[bold]Fully Mitigated:[/] [green]{report.attacks_fully_mitigated}[/]  "
        f"[bold]Partially:[/] [yellow]{report.attacks_partially_mitigated}[/]  "
        f"[bold]Unmitigated:[/] [red]{report.attacks_unmitigated}[/]\n"
        f"[bold]Worst-Case Blast Radius:[/] {report.worst_case_blast_radius} component(s)"
    )
    console.print()
    console.print(Panel(summary_text, title="[bold]Security Resilience Report[/]", border_style=score_color))

    # ---- Score Breakdown ----
    if report.score_breakdown:
        bd_table = Table(title="Score Breakdown (each 0-20)", show_header=True)
        bd_table.add_column("Category", style="cyan", width=20)
        bd_table.add_column("Score", justify="right", width=8)
        for cat, val in report.score_breakdown.items():
            color = "green" if val >= 15 else ("yellow" if val >= 8 else "red")
            bd_table.add_row(cat.replace("_", " ").title(), f"[{color}]{val:.1f}[/]")
        console.print()
        console.print(bd_table)

    # ---- Attack Results Table ----
    if report.results:
        atk_table = Table(title="Attack Simulation Results", show_header=True)
        atk_table.add_column("Attack", style="cyan", width=22)
        atk_table.add_column("Entry Point", width=18)
        atk_table.add_column("Blast", justify="right", width=6)
        atk_table.add_column("Defense", justify="right", width=8)
        atk_table.add_column("Downtime", justify="right", width=10)
        atk_table.add_column("Data Risk", justify="center", width=9)

        for r in report.results:
            def_color = "green" if r.defense_effectiveness >= 0.8 else (
                "yellow" if r.defense_effectiveness >= 0.3 else "red"
            )
            risk_str = "[red]YES[/]" if r.data_at_risk else "[green]no[/]"
            atk_table.add_row(
                r.attack_type.value,
                r.entry_point[:18],
                str(r.blast_radius),
                f"[{def_color}]{r.defense_effectiveness:.0%}[/]",
                f"{r.estimated_downtime_minutes:.0f}m",
                risk_str,
            )
        console.print()
        console.print(atk_table)

    # ---- Top Recommendations ----
    all_recs: list[str] = []
    seen_recs: set[str] = set()
    for r in report.results:
        for rec in r.mitigation_recommendations:
            if rec not in seen_recs:
                seen_recs.add(rec)
                all_recs.append(rec)

    if all_recs:
        console.print("\n[bold]Top Recommendations:[/]")
        for i, rec in enumerate(all_recs[:10], 1):
            console.print(f"  {i}. {rec}")


@app.command()
def fix(
    yaml_pos: Path | None = typer.Argument(None, help="YAML file path (positional)"),
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path (JSON or YAML)"),
    yaml_file: Path | None = typer.Option(None, "--yaml", "-y", help="YAML file with infrastructure definition"),
    output: Path = typer.Option(Path("./remediation"), "--output", "-o", help="Output directory for IaC files"),
    target_score: float = typer.Option(90.0, "--target-score", "-t", help="Target resilience score (0-100)"),
    json_output: bool = typer.Option(False, "--json", help="Output plan as JSON instead of writing files"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show diff preview without writing files"),
) -> None:
    """Generate IaC remediation code (Terraform/Kubernetes) to fix infrastructure issues.

    Examples:
        # Generate remediation code
        faultray fix infra.yaml

        # Set target resilience score
        faultray fix infra.yaml --target-score 95

        # Preview changes without writing files
        faultray fix infra.yaml --dry-run

        # Output plan as JSON
        faultray fix infra.yaml --json

        # Custom output directory
        faultray fix infra.yaml --output ./my-remediation/
    """

    from rich.panel import Panel
    from rich.table import Table

    from faultray.remediation.iac_generator import IaCGenerator

    resolved_yaml = yaml_pos or yaml_file
    graph = _load_graph_for_analysis(model, resolved_yaml)

    generator = IaCGenerator(graph)
    plan = generator.generate(target_score=target_score)

    if dry_run:
        preview = generator.dry_run(plan)
        console.print(preview)
        return

    if json_output:
        console.print_json(data=plan.to_dict())
        return

    if not plan.files:
        console.print("[green]No issues found. Infrastructure meets the target score.[/]")
        return

    # Summary panel
    score_before = plan.expected_score_before
    score_after = plan.expected_score_after
    if score_after >= 90:
        score_color = "green"
    elif score_after >= 70:
        score_color = "yellow"
    else:
        score_color = "red"

    summary_text = (
        f"[bold]Resilience Score:[/] {score_before:.1f} -> [{score_color}]{score_after:.1f}[/]\n"
        f"[bold]Risk Reduction:[/] {plan.risk_reduction_percent:.1f}%\n"
        f"[bold]Monthly Cost:[/] ${plan.total_monthly_cost:,.2f}\n"
        f"[bold]ROI:[/] {plan.roi_percent:.1f} score-points per $100/mo\n"
        f"[bold]Phases:[/] {plan.total_phases}  [bold]Files:[/] {len(plan.files)}"
    )
    console.print()
    console.print(Panel(summary_text, title="[bold]FaultRay Remediation Plan[/]", border_style=score_color))

    # Files table
    table = Table(title="Remediation Files", show_header=True)
    table.add_column("Phase", justify="center", width=6)
    table.add_column("File", style="cyan", width=45)
    table.add_column("Category", width=12)
    table.add_column("Impact", justify="right", width=8)
    table.add_column("Cost/mo", justify="right", width=10)
    table.add_column("Description", width=40)

    for f in plan.files:
        table.add_row(
            str(f.phase),
            f.path,
            f.category,
            f"+{f.impact_score_delta:.1f}",
            f"${f.monthly_cost:,.2f}",
            f.description[:40],
        )

    console.print()
    console.print(table)

    # Write files
    generator.write_to_directory(plan, output)
    console.print(f"\n[green]Remediation files written to: {output}[/]")
    console.print(f"[dim]See {output / 'README.md'} for application instructions.[/]")
