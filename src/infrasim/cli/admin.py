"""Admin CLI commands: demo, serve, report."""

from __future__ import annotations

from pathlib import Path

import typer

from infrasim.cli.main import (
    DEFAULT_MODEL_PATH,
    InfraGraph,
    SimulationEngine,
    app,
    console,
    print_infrastructure_summary,
    print_simulation_report,
)


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


@app.command()
def serve(
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path"),
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host"),
    port: int = typer.Option(8080, "--port", "-p", help="Bind port"),
    prometheus_url: str | None = typer.Option(None, "--prometheus-url", help="Prometheus URL for continuous monitoring"),
    prometheus_interval: int = typer.Option(60, "--prometheus-interval", help="Prometheus polling interval in seconds"),
) -> None:
    """Launch web dashboard."""
    import os

    import uvicorn

    from infrasim.api.server import set_graph

    if model.exists():
        console.print(f"[cyan]Loading model from {model}...[/]")
        graph = InfraGraph.load(model)
        set_graph(graph)
    else:
        console.print("[yellow]No model file found. Visit /demo in the browser to load demo data.[/]")

    # Pass Prometheus settings via env vars so the FastAPI lifespan can pick them up
    if prometheus_url:
        os.environ["INFRASIM_PROMETHEUS_URL"] = prometheus_url
        os.environ["INFRASIM_PROMETHEUS_INTERVAL"] = str(prometheus_interval)
        console.print(
            f"[cyan]Prometheus monitoring enabled: {prometheus_url} "
            f"(interval={prometheus_interval}s)[/]"
        )

    console.print(f"[green]Starting InfraSim dashboard at http://{host}:{port}[/]")
    uvicorn.run("infrasim.api.server:app", host=host, port=port, log_level="info")


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
