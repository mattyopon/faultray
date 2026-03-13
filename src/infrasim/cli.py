"""CLI interface for InfraSim."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console

from infrasim.discovery.scanner import scan_local
from infrasim.model.graph import InfraGraph
from infrasim.reporter.report import print_infrastructure_summary, print_simulation_report
from infrasim.simulator.engine import SimulationEngine

app = typer.Typer(
    name="infrasim",
    help="Virtual infrastructure chaos engineering simulator",
    no_args_is_help=True,
)
console = Console()

DEFAULT_MODEL_PATH = Path("infrasim-model.json")


@app.command()
def scan(
    output: Path = typer.Option(DEFAULT_MODEL_PATH, "--output", "-o", help="Output model file path"),
    hostname: str | None = typer.Option(None, "--hostname", help="Override hostname"),
    prometheus_url: str | None = typer.Option(
        None, "--prometheus-url", help="Prometheus server URL (e.g. http://localhost:9090)"
    ),
) -> None:
    """Scan local system and build infrastructure model."""
    if prometheus_url:
        from infrasim.discovery.prometheus import PrometheusClient

        console.print(f"[cyan]Discovering infrastructure from Prometheus at {prometheus_url}...[/]")
        client = PrometheusClient(url=prometheus_url)
        graph = asyncio.run(client.discover_components())
    else:
        console.print("[cyan]Scanning local infrastructure...[/]")
        graph = scan_local(hostname=hostname)

    print_infrastructure_summary(graph, console)

    graph.save(output)
    console.print(f"\n[green]Model saved to {output}[/]")


@app.command()
def simulate(
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path"),
    html: Path | None = typer.Option(None, "--html", help="Export HTML report to this path"),
    dynamic: bool = typer.Option(False, "--dynamic", "-d", help="Run dynamic time-stepped simulation"),
) -> None:
    """Run chaos simulation against infrastructure model."""
    if not model.exists():
        console.print(f"[red]Model file not found: {model}[/]")
        console.print("Run [cyan]infrasim scan[/] first to create a model.")
        raise typer.Exit(1)

    console.print("[cyan]Loading infrastructure model...[/]")
    graph = InfraGraph.load(model)

    if dynamic:
        from infrasim.simulator.dynamic_engine import DynamicSimulationEngine

        console.print(f"[cyan]Running dynamic simulation ({len(graph.components)} components)...[/]")
        dyn_engine = DynamicSimulationEngine(graph)
        report = dyn_engine.run_all_dynamic_defaults()
        # report is a DynamicSimulationReport; extract .results list
        results = getattr(report, "results", report) if not isinstance(report, list) else report
        _print_dynamic_results(results, console)
        return

    console.print(f"[cyan]Running chaos simulation ({len(graph.components)} components)...[/]")
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    print_simulation_report(report, console)

    if html:
        from infrasim.reporter.html_report import save_html_report

        save_html_report(report, graph, html)
        console.print(f"\n[green]HTML report saved to {html}[/]")


def _print_dynamic_results(results: list, con: Console) -> None:
    """Print a summary of dynamic simulation results to the console."""
    total = len(results)
    critical = sum(1 for r in results if getattr(r, "peak_severity", "") == "critical")
    warning = sum(1 for r in results if getattr(r, "peak_severity", "") == "warning")
    passed = total - critical - warning

    con.print(f"\n[bold]Dynamic Simulation Results[/]")
    con.print(
        f"  Total: [bold]{total}[/]  "
        f"[red]Critical: {critical}[/]  "
        f"[yellow]Warning: {warning}[/]  "
        f"[green]Passed: {passed}[/]\n"
    )

    for r in results:
        severity = getattr(r, "peak_severity", "passed")
        if severity not in ("critical", "warning"):
            continue

        color = "red" if severity == "critical" else "yellow"
        name = getattr(r, "scenario_name", getattr(r, "name", "unknown"))
        peak_time = getattr(r, "peak_severity_time", None)
        recovery = getattr(r, "recovery_time_seconds", None)
        autoscale = getattr(r, "autoscaling_events", [])
        failover = getattr(r, "failover_events", [])

        con.print(f"  [{color}]{severity.upper()}[/] {name}")
        if peak_time is not None:
            con.print(f"    Peak severity at: t={peak_time}s")
        if recovery is not None:
            con.print(f"    Recovery time: {recovery}s")
        else:
            con.print(f"    Recovery time: [red]no recovery[/]")
        con.print(f"    Autoscaling events: {len(autoscale)}")
        con.print(f"    Failover events: {len(failover)}")
        con.print()


@app.command()
def dynamic(
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path"),
    html: Path | None = typer.Option(None, "--html", help="Export HTML report to this path"),
    duration: int = typer.Option(300, "--duration", help="Simulation duration in seconds"),
    step: int = typer.Option(5, "--step", help="Time step interval in seconds"),
) -> None:
    """Run dynamic time-stepped chaos simulation with realistic traffic patterns."""
    if not model.exists():
        console.print(f"[red]Model file not found: {model}[/]")
        console.print("Run [cyan]infrasim scan[/] first to create a model.")
        raise typer.Exit(1)

    console.print("[cyan]Loading infrastructure model...[/]")
    graph = InfraGraph.load(model)

    from infrasim.simulator.dynamic_engine import DynamicSimulationEngine

    console.print(
        f"[cyan]Running dynamic simulation "
        f"({len(graph.components)} components, "
        f"duration={duration}s, step={step}s)...[/]"
    )
    engine = DynamicSimulationEngine(graph)
    results = engine.run_all_dynamic_defaults(duration=duration, step=step)
    _print_dynamic_results(results, console)

    if html:
        from infrasim.reporter.html_report import save_html_report

        save_html_report(results, graph, html)
        console.print(f"\n[green]HTML report saved to {html}[/]")


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
) -> None:
    """Run long-running operational simulation with SLO tracking."""
    yaml_file = yaml_pos or yaml_file
    from infrasim.model.components import SLOTarget
    from infrasim.simulator.ops_engine import OpsScenario, OpsSimulationEngine

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

    # Load model
    graph: InfraGraph
    slos: list[SLOTarget] = []
    ops_config: dict = {}

    if yaml_file is not None:
        from infrasim.model.loader import load_yaml_with_ops

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
            from infrasim.model.loader import load_yaml_with_ops

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
        console.print("Run [cyan]infrasim scan[/] or [cyan]infrasim load[/] first.")
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
        console.print(
            f"[cyan]Running all default operational simulations "
            f"({len(graph.components)} components)...[/]"
        )
        results = engine.run_default_ops_scenarios()
        for result in results:
            _print_ops_results(result, console)
            console.print()
    else:
        from infrasim.simulator.traffic import create_diurnal_weekly, create_growth_trend

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

        console.print(
            f"[cyan]Running operational simulation "
            f"({len(graph.components)} components, "
            f"{days} days, step={step})...[/]"
        )
        result = engine.run_ops_scenario(scenario)
        _print_ops_results(result, console)

    if html:
        console.print(f"\n[dim]HTML export for ops-sim is not yet implemented.[/]")


def _print_ops_results(result: "OpsSimulationResult", con: Console) -> None:  # noqa: F821
    """Print operational simulation results using Rich formatting."""
    from rich.panel import Panel
    from rich.table import Table

    scenario = result.scenario

    # ---- 1. Simulation Summary Box ----------------------------------------
    # Use average availability for color (min_availability is too volatile
    # due to brief deploy-induced dips) — still display min in the output.
    avg_avail_for_color = 100.0
    if result.sli_timeline:
        avg_avail_for_color = sum(p.availability_percent for p in result.sli_timeline) / len(result.sli_timeline)
    avail = result.min_availability
    if avg_avail_for_color >= 99.9:
        avail_color = "green"
    elif avg_avail_for_color >= 99.0:
        avail_color = "yellow"
    else:
        avail_color = "red"

    total_events = len(result.events)
    downtime_min = result.total_downtime_seconds / 60.0
    num_steps = len(result.sli_timeline)

    # Calculate average availability from SLI timeline
    avg_avail = 100.0
    if result.sli_timeline:
        avg_avail = sum(p.availability_percent for p in result.sli_timeline) / len(result.sli_timeline)

    summary_text = (
        f"[bold]Scenario:[/] {scenario.name}\n"
        f"[bold]Duration:[/] {scenario.duration_days} days  "
        f"[bold]Steps:[/] {num_steps:,}\n\n"
        f"[bold]Avg Availability:[/] [{avail_color}]{avg_avail:.4f}%[/]  "
        f"[bold]Min Availability:[/] {avail:.2f}%\n"
        f"[bold]Total Downtime:[/] {downtime_min:.1f} min  "
        f"[bold]Peak Utilization:[/] {result.peak_utilization:.1f}%\n"
        f"[bold]Deploys:[/] {result.total_deploys}  "
        f"[bold]Failures:[/] {result.total_failures}  "
        f"[bold]Degradation Events:[/] {result.total_degradation_events}\n"
        f"[bold]Total Events:[/] {total_events}"
    )

    con.print()
    con.print(Panel(
        summary_text,
        title="[bold]InfraSim Operational Simulation Report[/]",
        border_style=avail_color,
    ))

    # ---- 2. Error Budget Table --------------------------------------------
    if result.error_budget_statuses:
        budget_table = Table(title="Error Budget Status", show_header=True)
        budget_table.add_column("SLO", style="cyan", width=22)
        budget_table.add_column("Component", width=16)
        budget_table.add_column("Total", width=10, justify="right")
        budget_table.add_column("Consumed", width=10, justify="right")
        budget_table.add_column("Remaining", width=10, justify="right")
        budget_table.add_column("Remaining %", width=12, justify="right")
        budget_table.add_column("Burn 1h", width=8, justify="right")
        budget_table.add_column("Burn 6h", width=8, justify="right")
        budget_table.add_column("Status", width=10, justify="center")

        for eb in result.error_budget_statuses:
            pct = eb.budget_remaining_percent
            if pct >= 50:
                pct_color = "green"
            elif pct >= 20:
                pct_color = "yellow"
            else:
                pct_color = "red"

            status = "[bold red]EXHAUSTED[/]" if eb.is_budget_exhausted else f"[{pct_color}]OK[/]"

            budget_table.add_row(
                eb.slo.name or eb.slo.metric,
                eb.component_id or "system",
                f"{eb.budget_total_minutes:.1f}m",
                f"{eb.budget_consumed_minutes:.1f}m",
                f"{eb.budget_remaining_minutes:.1f}m",
                f"[{pct_color}]{pct:.1f}%[/]",
                f"{eb.burn_rate_1h:.2f}x",
                f"{eb.burn_rate_6h:.2f}x",
                status,
            )

        con.print()
        con.print(budget_table)

    # ---- 3. Incident Timeline (top 10 events) ----------------------------
    if result.events:
        # Show last 10 events
        recent = result.events[-10:]
        event_table = Table(title=f"Event Timeline (last {len(recent)} of {total_events})", show_header=True)
        event_table.add_column("Time", style="dim", width=12)
        event_table.add_column("Type", width=18)
        event_table.add_column("Component", style="cyan", width=20)
        event_table.add_column("Description", width=50)

        for ev in recent:
            hours = ev.time_seconds / 3600
            day = int(hours // 24) + 1
            hour = int(hours % 24)
            time_str = f"Day {day} {hour:02d}:00"

            etype = ev.event_type.value
            if etype in ("random_failure", "memory_leak_oom", "disk_full", "conn_pool_exhaustion"):
                type_style = f"[red]{etype}[/]"
            elif etype == "deploy":
                type_style = f"[yellow]{etype}[/]"
            else:
                type_style = f"[dim]{etype}[/]"

            event_table.add_row(
                time_str,
                type_style,
                ev.target_component_id,
                (ev.description or "")[:50],
            )

        con.print()
        con.print(event_table)

    # ---- 4. Summary -------------------------------------------------------
    if result.summary:
        con.print()
        con.print(f"[dim]{result.summary}[/]")


@app.command()
def show(
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path"),
) -> None:
    """Show infrastructure model summary."""
    if not model.exists():
        console.print(f"[red]Model file not found: {model}[/]")
        raise typer.Exit(1)

    graph = InfraGraph.load(model)
    print_infrastructure_summary(graph, console)

    console.print("\n[bold]Components:[/]")
    for comp in graph.components.values():
        deps = graph.get_dependencies(comp.id)
        dep_str = f" -> {', '.join(d.name for d in deps)}" if deps else ""
        util = comp.utilization()
        if util > 80:
            util_color = "red"
        elif util > 60:
            util_color = "yellow"
        else:
            util_color = "green"
        console.print(
            f"  [{util_color}]{comp.name}[/] ({comp.type.value}) "
            f"[dim]replicas={comp.replicas} util={util:.0f}%{dep_str}[/]"
        )


@app.command()
def load(
    yaml_file: Path = typer.Argument(..., help="Path to YAML infrastructure definition"),
    output: Path = typer.Option(DEFAULT_MODEL_PATH, "--output", "-o", help="Output model file path"),
) -> None:
    """Load infrastructure model from a YAML file."""
    from infrasim.model.loader import load_yaml

    console.print(f"[cyan]Loading infrastructure from {yaml_file}...[/]")

    try:
        graph = load_yaml(yaml_file)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)
    except ValueError as exc:
        console.print(f"[red]Invalid YAML: {exc}[/]")
        raise typer.Exit(1)

    print_infrastructure_summary(graph, console)

    graph.save(output)
    console.print(f"\n[green]Model saved to {output}[/]")


@app.command()
def tf_import(
    tf_state: Path = typer.Option(
        None, "--state", "-s", help="Path to terraform.tfstate file"
    ),
    tf_dir: Path = typer.Option(
        None, "--dir", "-d", help="Terraform project directory (runs 'terraform show -json')"
    ),
    output: Path = typer.Option(DEFAULT_MODEL_PATH, "--output", "-o", help="Output model file path"),
) -> None:
    """Import infrastructure from Terraform state."""
    from infrasim.discovery.terraform import load_tf_state_cmd, load_tf_state_file

    if tf_state:
        console.print(f"[cyan]Importing from Terraform state file: {tf_state}...[/]")
        graph = load_tf_state_file(tf_state)
    elif tf_dir:
        console.print(f"[cyan]Running 'terraform show -json' in {tf_dir}...[/]")
        try:
            graph = load_tf_state_cmd(tf_dir)
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/]")
            raise typer.Exit(1)
    else:
        console.print("[cyan]Running 'terraform show -json' in current directory...[/]")
        try:
            graph = load_tf_state_cmd()
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/]")
            raise typer.Exit(1)

    print_infrastructure_summary(graph, console)

    graph.save(output)
    console.print(f"\n[green]Model saved to {output}[/]")
    console.print(f"Run [cyan]infrasim simulate -m {output}[/] to analyze risks.")


@app.command()
def tf_plan(
    plan_file: Path = typer.Argument(..., help="Path to Terraform plan file (terraform plan -out=plan.out)"),
    tf_dir: Path = typer.Option(
        None, "--dir", "-d", help="Terraform project directory"
    ),
    html: Path | None = typer.Option(None, "--html", help="Export HTML report to this path"),
) -> None:
    """Analyze a Terraform plan for change impact and cascade risks.

    Usage:
      terraform plan -out=plan.out
      infrasim tf-plan plan.out
    """
    from infrasim.discovery.terraform import load_tf_plan_cmd

    console.print(f"[cyan]Analyzing Terraform plan: {plan_file}...[/]")

    try:
        result = load_tf_plan_cmd(plan_file=plan_file, tf_dir=tf_dir)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)

    changes = result["changes"]
    after_graph = result["after"]

    # Show changes
    if changes:
        console.print(f"\n[bold]Terraform Changes ({len(changes)}):[/]\n")
        from rich.table import Table

        table = Table(show_header=True)
        table.add_column("Risk", style="bold", width=6)
        table.add_column("Action", width=10)
        table.add_column("Resource", style="cyan")
        table.add_column("Changed Attributes")

        for change in changes:
            risk = change["risk_level"]
            if risk >= 8:
                risk_str = f"[bold red]{risk}/10[/]"
            elif risk >= 5:
                risk_str = f"[yellow]{risk}/10[/]"
            else:
                risk_str = f"[green]{risk}/10[/]"

            actions = "+".join(change["actions"])
            attrs = ", ".join(
                f"{a['attribute']}: {a['before']} → {a['after']}"
                for a in change["changed_attributes"][:3]
            )
            if len(change["changed_attributes"]) > 3:
                attrs += f" (+{len(change['changed_attributes']) - 3} more)"

            table.add_row(risk_str, actions, change["address"], attrs)

        console.print(table)
    else:
        console.print("[green]No changes detected in plan.[/]")
        return

    # Run simulation on the "after" state
    if len(after_graph.components) > 0:
        console.print(f"\n[cyan]Simulating chaos on planned infrastructure ({len(after_graph.components)} components)...[/]")
        engine = SimulationEngine(after_graph)
        sim_report = engine.run_all_defaults()
        print_simulation_report(sim_report, console)

        if html:
            from infrasim.reporter.html_report import save_html_report

            save_html_report(sim_report, after_graph, html)
            console.print(f"\n[green]HTML report saved to {html}[/]")


@app.command()
def report(
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path"),
    output: Path = typer.Option(Path("report.html"), "--output", "-o", help="Output HTML file path"),
) -> None:
    """Generate an HTML report from a saved model (runs simulation automatically)."""
    from infrasim.reporter.html_report import save_html_report

    if not model.exists():
        console.print(f"[red]Model file not found: {model}[/]")
        console.print("Run [cyan]infrasim scan[/] or [cyan]infrasim load[/] first.")
        raise typer.Exit(1)

    console.print("[cyan]Loading infrastructure model...[/]")
    graph = InfraGraph.load(model)

    console.print(f"[cyan]Running chaos simulation ({len(graph.components)} components)...[/]")
    engine = SimulationEngine(graph)
    sim_report = engine.run_all_defaults()

    print_simulation_report(sim_report, console)

    save_html_report(sim_report, graph, output)
    console.print(f"\n[green]HTML report saved to {output}[/]")


@app.command()
def serve(
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path"),
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host"),
    port: int = typer.Option(8080, "--port", "-p", help="Bind port"),
) -> None:
    """Launch web dashboard."""
    import uvicorn

    from infrasim.api.server import set_graph

    if model.exists():
        console.print(f"[cyan]Loading model from {model}...[/]")
        graph = InfraGraph.load(model)
        set_graph(graph)
    else:
        console.print("[yellow]No model file found. Visit /demo in the browser to load demo data.[/]")

    console.print(f"[green]Starting InfraSim dashboard at http://{host}:{port}[/]")
    uvicorn.run("infrasim.api.server:app", host=host, port=port, log_level="info")


@app.command()
def demo(
    web: bool = typer.Option(False, "--web", "-w", help="Launch web dashboard after building demo"),
    host: str = typer.Option("0.0.0.0", "--host", help="Web dashboard bind host"),
    port: int = typer.Option(8080, "--port", "-p", help="Web dashboard bind port"),
) -> None:
    """Run simulation with a demo infrastructure (no scanning required)."""
    from infrasim.model.demo import create_demo_graph

    console.print("[cyan]Building demo infrastructure...[/]")

    graph = create_demo_graph()

    # Show infrastructure
    print_infrastructure_summary(graph, console)

    # Run simulation
    console.print("\n[cyan]Running chaos simulation...[/]")
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    print_simulation_report(report, console)

    # Launch web dashboard if requested
    if web:
        import uvicorn

        from infrasim.api.server import set_graph

        set_graph(graph)
        console.print(f"\n[green]Starting InfraSim dashboard at http://{host}:{port}[/]")
        uvicorn.run("infrasim.api.server:app", host=host, port=port, log_level="info")


# ---------------------------------------------------------------------------
# Feed commands - auto-update scenarios from security news
# ---------------------------------------------------------------------------


@app.command()
def feed_update(
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file for component-aware scenario generation"),
    timeout: float = typer.Option(15.0, "--timeout", "-t", help="HTTP timeout per feed (seconds)"),
) -> None:
    """Fetch security news feeds and generate new chaos scenarios.

    Fetches articles from security news RSS/Atom feeds, analyzes them for
    infrastructure incident patterns, and generates chaos scenarios that are
    stored locally for future simulations.
    """
    from infrasim.feeds.analyzer import analyze_articles, incidents_to_scenarios
    from infrasim.feeds.fetcher import fetch_all_feeds
    from infrasim.feeds.sources import get_enabled_sources
    from infrasim.feeds.store import save_feed_scenarios

    sources = get_enabled_sources()
    console.print(f"[cyan]Fetching {len(sources)} security news feeds...[/]")

    # Fetch all feeds
    articles = asyncio.run(fetch_all_feeds(sources, timeout=timeout))
    console.print(f"  Fetched [bold]{len(articles)}[/] articles from {len(sources)} sources")

    if not articles:
        console.print("[yellow]No articles fetched. Check network connection.[/]")
        return

    # Analyze articles for incident patterns
    console.print("[cyan]Analyzing articles for incident patterns...[/]")
    incidents = analyze_articles(articles)
    console.print(f"  Matched [bold]{len(incidents)}[/] incident patterns")

    if not incidents:
        console.print("[green]No new incident patterns detected.[/]")
        return

    # Show matched patterns
    from rich.table import Table

    table = Table(title="Detected Incident Patterns", show_header=True)
    table.add_column("Pattern", style="cyan", width=30)
    table.add_column("Source", width=20)
    table.add_column("Confidence", width=10)
    table.add_column("Keywords", style="dim")

    for inc in incidents[:20]:  # Show top 20
        conf = inc.confidence
        if conf > 0.7:
            conf_str = f"[green]{conf:.0%}[/]"
        elif conf > 0.4:
            conf_str = f"[yellow]{conf:.0%}[/]"
        else:
            conf_str = f"[dim]{conf:.0%}[/]"

        table.add_row(
            inc.pattern.name,
            inc.article.source_name,
            conf_str,
            ", ".join(inc.matched_keywords[:3]),
        )

    console.print(table)

    # Generate scenarios
    component_ids: list[str] = []
    components = None
    if model.exists():
        graph = InfraGraph.load(model)
        component_ids = list(graph.components.keys())
        components = graph.components
        console.print(f"[cyan]Mapping to infrastructure model ({len(component_ids)} components)...[/]")
    else:
        console.print("[yellow]No model file found. Generating generic scenarios.[/]")
        component_ids = ["generic-target"]

    scenarios = incidents_to_scenarios(incidents, component_ids, components)

    # Save to store
    articles_meta = [
        {
            "title": inc.article.title,
            "link": inc.article.link,
            "source": inc.article.source_name,
            "published": inc.article.published,
            "pattern": inc.pattern.id,
            "confidence": inc.confidence,
        }
        for inc in incidents
    ]
    store_path = save_feed_scenarios(scenarios, articles_meta)

    console.print(f"\n[green]Generated {len(scenarios)} new scenarios from security feeds[/]")
    console.print(f"[dim]Store: {store_path}[/]")
    console.print(f"\nRun [cyan]infrasim simulate[/] to include feed scenarios in simulation.")


@app.command()
def feed_list() -> None:
    """Show stored feed-generated scenarios and statistics."""
    from infrasim.feeds.store import get_store_stats, load_store_raw

    stats = get_store_stats()
    raw = load_store_raw()

    if not stats["last_updated"]:
        console.print("[yellow]No feed data yet. Run [cyan]infrasim feed-update[/] first.[/]")
        return

    console.print(f"\n[bold]Feed Scenario Store[/]")
    console.print(f"  Last updated: [cyan]{stats['last_updated']}[/]")
    console.print(f"  Scenarios: [bold]{stats['scenario_count']}[/]")
    console.print(f"  Source articles: [bold]{stats['article_count']}[/]")
    console.print(f"  Store path: [dim]{stats['store_path']}[/]")

    # Show scenarios
    scenarios_data = raw.get("scenarios", [])
    if scenarios_data:
        from rich.table import Table

        table = Table(title="\nStored Scenarios", show_header=True)
        table.add_column("Name", style="cyan", width=35)
        table.add_column("Faults", width=8)
        table.add_column("Traffic", width=8)
        table.add_column("ID", style="dim", width=16)

        for s in scenarios_data:
            traffic = s.get("traffic_multiplier", 1.0)
            traffic_str = f"{traffic}x" if traffic > 1.0 else "normal"
            table.add_row(
                s["name"],
                str(len(s.get("faults", []))),
                traffic_str,
                s["id"][:16],
            )

        console.print(table)

    # Show recent articles
    articles = raw.get("articles", [])
    if articles:
        console.print(f"\n[bold]Recent Source Articles ({len(articles)}):[/]")
        for art in articles[:10]:
            conf = art.get("confidence", 0)
            console.print(
                f"  [{art.get('source', '?')}] {art.get('title', '?')[:70]} "
                f"[dim]({conf:.0%} match)[/]"
            )
        if len(articles) > 10:
            console.print(f"  [dim]... and {len(articles) - 10} more[/]")


@app.command()
def feed_sources() -> None:
    """Show configured feed sources."""
    from infrasim.feeds.sources import DEFAULT_SOURCES

    from rich.table import Table

    table = Table(title="Security News Feed Sources", show_header=True)
    table.add_column("Name", style="cyan", width=25)
    table.add_column("Type", width=6)
    table.add_column("Status", width=8)
    table.add_column("Tags", style="dim")
    table.add_column("URL", style="dim", width=50)

    for src in DEFAULT_SOURCES:
        status = "[green]ON[/]" if src.enabled else "[red]OFF[/]"
        table.add_row(
            src.name,
            src.feed_type,
            status,
            ", ".join(src.tags),
            src.url[:50],
        )

    console.print(table)
    console.print(f"\n[dim]{len(DEFAULT_SOURCES)} sources configured[/]")


@app.command()
def feed_clear() -> None:
    """Clear all stored feed-generated scenarios."""
    from infrasim.feeds.store import clear_store, get_store_stats

    stats = get_store_stats()
    if not stats["last_updated"]:
        console.print("[yellow]Store is already empty.[/]")
        return

    clear_store()
    console.print(f"[green]Cleared {stats['scenario_count']} feed scenarios.[/]")


# ---------------------------------------------------------------------------
# What-if Analysis & Capacity Planning commands (v4.0)
# ---------------------------------------------------------------------------


def _load_graph_for_analysis(
    model: Path,
    yaml_file: Path | None,
) -> InfraGraph:
    """Load an InfraGraph from model JSON or YAML for analysis commands."""
    if yaml_file is not None:
        from infrasim.model.loader import load_yaml

        if not yaml_file.exists():
            console.print(f"[red]YAML file not found: {yaml_file}[/]")
            raise typer.Exit(1)
        return load_yaml(yaml_file)

    if not model.exists():
        console.print(f"[red]Model file not found: {model}[/]")
        console.print("Run [cyan]infrasim scan[/] or [cyan]infrasim load[/] first.")
        raise typer.Exit(1)

    if str(model).endswith((".yaml", ".yml")):
        from infrasim.model.loader import load_yaml

        return load_yaml(model)

    return InfraGraph.load(model)


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
    """Run what-if analysis by sweeping infrastructure parameters."""
    resolved_yaml = yaml_pos or yaml_file
    try:
        from infrasim.simulator.whatif_engine import WhatIfEngine
    except ImportError:
        console.print("[red]What-if engine not available. Install infrasim with what-if support.[/]")
        raise typer.Exit(1)

    graph = _load_graph_for_analysis(model, resolved_yaml)
    engine = WhatIfEngine(graph)

    if multi is not None:
        from infrasim.simulator.whatif_engine import MultiWhatIfScenario

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
        from infrasim.simulator.whatif_engine import WhatIfScenario

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


def _print_whatif_result(result: object, con: Console) -> None:
    """Print a single what-if analysis result using Rich formatting."""
    from rich.panel import Panel
    from rich.table import Table

    param_name = getattr(result, "parameter", "Unknown")
    values = getattr(result, "values", [])
    avg_availabilities = getattr(result, "avg_availabilities", [])
    min_availabilities = getattr(result, "min_availabilities", [])
    total_failures = getattr(result, "total_failures", [])
    total_downtimes = getattr(result, "total_downtimes", [])
    slo_pass = getattr(result, "slo_pass", [])
    breakpoint_val = getattr(result, "breakpoint_value", None)

    display_name = param_name.replace("_", " ").title()

    table = Table(show_header=True, header_style="bold")
    table.add_column("Factor", justify="right", width=8)
    table.add_column("Avg Avail", justify="right", width=10)
    table.add_column("Min Avail", justify="right", width=10)
    table.add_column("Failures", justify="right", width=10)
    table.add_column("Downtime(s)", justify="right", width=12)
    table.add_column("SLO", justify="center", width=6)

    for i, value in enumerate(values):
        avg_avail = avg_availabilities[i] if i < len(avg_availabilities) else 0.0
        min_avail = min_availabilities[i] if i < len(min_availabilities) else 0.0
        failures = total_failures[i] if i < len(total_failures) else 0
        downtime = total_downtimes[i] if i < len(total_downtimes) else 0.0
        passed = slo_pass[i] if i < len(slo_pass) else True

        slo_str = "[green]PASS[/]" if passed else "[red]FAIL[/]"
        table.add_row(
            f"{value:.2f}",
            f"{avg_avail:.4f}%",
            f"{min_avail:.2f}%",
            str(failures),
            f"{downtime:.1f}",
            slo_str,
        )

    con.print(Panel(
        table,
        title=f"[bold]What-if Analysis: {display_name}[/]",
        subtitle=f"Breakpoint: factor {breakpoint_val:.2f}" if breakpoint_val is not None else None,
    ))


def _print_multi_whatif_result(result: object, con: Console) -> None:
    """Print a multi-parameter what-if analysis result using Rich formatting."""
    from rich.panel import Panel
    from rich.table import Table

    parameters = getattr(result, "parameters", {})
    avg_avail = getattr(result, "avg_availability", 0.0)
    min_avail = getattr(result, "min_availability", 0.0)
    total_fail = getattr(result, "total_failures", 0)
    downtime = getattr(result, "total_downtime_seconds", 0)
    slo_passed = getattr(result, "slo_pass", True)
    description = getattr(result, "summary", "").split("\n")[0] if getattr(result, "summary", "") else ""

    # Title from description or parameters
    if description.startswith("Analysis: "):
        title = description[len("Analysis: "):]
    else:
        title = ", ".join(f"{k}={v}" for k, v in parameters.items())

    table = Table(show_header=True, header_style="bold")
    table.add_column("Parameter", width=24)
    table.add_column("Value", justify="right", width=8)

    for param, value in parameters.items():
        table.add_row(param, f"{value:.2f}")

    table.add_section()
    table.add_row("Avg Availability", f"{avg_avail:.4f}%")
    table.add_row("Min Availability", f"{min_avail:.2f}%")
    table.add_row("Total Failures", str(total_fail))
    table.add_row("Total Downtime (s)", str(downtime))

    slo_str = "[green]PASS[/]" if slo_passed else "[red]FAIL[/]"
    table.add_row("SLO (99.9%)", slo_str)

    con.print(Panel(table, title=f"[bold]Multi What-if: {title}[/]"))


@app.command()
def capacity(
    yaml_pos: Path | None = typer.Argument(None, help="YAML file path (positional)"),
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Path to model JSON"),
    yaml_file: Path | None = typer.Option(None, "--yaml", help="Path to YAML (alternative to model)"),
    growth: float = typer.Option(0.10, "--growth", help="Monthly growth rate (default: 0.10 = 10%)"),
    slo: float = typer.Option(99.9, "--slo", help="SLO target (default: 99.9)"),
    simulate: bool = typer.Option(False, "--simulate", help="Run ops simulation to get actual burn rate"),
) -> None:
    """Run capacity planning analysis with growth forecasting."""
    resolved_yaml = yaml_pos or yaml_file
    try:
        from infrasim.simulator.capacity_engine import CapacityPlanningEngine
    except ImportError:
        console.print("[red]Capacity planning engine not available. Install infrasim with capacity support.[/]")
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
