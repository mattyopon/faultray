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
) -> None:
    """Run chaos simulation against infrastructure model."""
    if not model.exists():
        console.print(f"[red]Model file not found: {model}[/]")
        console.print("Run [cyan]infrasim scan[/] first to create a model.")
        raise typer.Exit(1)

    console.print("[cyan]Loading infrastructure model...[/]")
    graph = InfraGraph.load(model)

    console.print(f"[cyan]Running chaos simulation ({len(graph.components)} components)...[/]")
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    print_simulation_report(report, console)

    if html:
        from infrasim.reporter.html_report import save_html_report

        save_html_report(report, graph, html)
        console.print(f"\n[green]HTML report saved to {html}[/]")


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
    from infrasim.model.components import (
        Capacity,
        Component,
        ComponentType,
        Dependency,
        ResourceMetrics,
    )

    console.print("[cyan]Building demo infrastructure...[/]")

    graph = InfraGraph()

    # Build a realistic web application stack
    components = [
        Component(
            id="nginx",
            name="nginx (LB)",
            type=ComponentType.LOAD_BALANCER,
            host="web01",
            port=443,
            replicas=1,
            metrics=ResourceMetrics(cpu_percent=25, memory_percent=30, disk_percent=45),
            capacity=Capacity(max_connections=10000, max_rps=50000),
        ),
        Component(
            id="app-1",
            name="api-server-1",
            type=ComponentType.APP_SERVER,
            host="app01",
            port=8080,
            replicas=1,
            metrics=ResourceMetrics(
                cpu_percent=65, memory_percent=70, disk_percent=55, network_connections=450
            ),
            capacity=Capacity(max_connections=500, connection_pool_size=100, timeout_seconds=30),
        ),
        Component(
            id="app-2",
            name="api-server-2",
            type=ComponentType.APP_SERVER,
            host="app02",
            port=8080,
            replicas=1,
            metrics=ResourceMetrics(
                cpu_percent=60, memory_percent=68, disk_percent=55, network_connections=420
            ),
            capacity=Capacity(max_connections=500, connection_pool_size=100, timeout_seconds=30),
        ),
        Component(
            id="postgres",
            name="PostgreSQL (primary)",
            type=ComponentType.DATABASE,
            host="db01",
            port=5432,
            replicas=1,
            metrics=ResourceMetrics(
                cpu_percent=45, memory_percent=80, disk_percent=72, network_connections=90
            ),
            capacity=Capacity(max_connections=100, max_disk_gb=500),
        ),
        Component(
            id="redis",
            name="Redis (cache)",
            type=ComponentType.CACHE,
            host="cache01",
            port=6379,
            replicas=1,
            metrics=ResourceMetrics(
                cpu_percent=15, memory_percent=60, network_connections=200
            ),
            capacity=Capacity(max_connections=10000),
        ),
        Component(
            id="rabbitmq",
            name="RabbitMQ",
            type=ComponentType.QUEUE,
            host="mq01",
            port=5672,
            replicas=1,
            metrics=ResourceMetrics(
                cpu_percent=20, memory_percent=40, disk_percent=35, network_connections=50
            ),
            capacity=Capacity(max_connections=1000),
        ),
    ]

    for comp in components:
        graph.add_component(comp)

    # Dependencies
    dependencies = [
        Dependency(source_id="nginx", target_id="app-1", dependency_type="requires", weight=1.0),
        Dependency(source_id="nginx", target_id="app-2", dependency_type="requires", weight=1.0),
        Dependency(source_id="app-1", target_id="postgres", dependency_type="requires", weight=1.0),
        Dependency(source_id="app-2", target_id="postgres", dependency_type="requires", weight=1.0),
        Dependency(source_id="app-1", target_id="redis", dependency_type="optional", weight=0.7),
        Dependency(source_id="app-2", target_id="redis", dependency_type="optional", weight=0.7),
        Dependency(source_id="app-1", target_id="rabbitmq", dependency_type="async", weight=0.5),
        Dependency(source_id="app-2", target_id="rabbitmq", dependency_type="async", weight=0.5),
    ]

    for dep in dependencies:
        graph.add_dependency(dep)

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
