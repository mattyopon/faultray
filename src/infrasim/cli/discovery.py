"""Discovery-related CLI commands: scan, load, show, tf-import, tf-plan."""

from __future__ import annotations

import asyncio
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
from infrasim.discovery.scanner import scan_local


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
    from infrasim.discovery.terraform import load_hcl_directory, load_tf_state_cmd, load_tf_state_file

    if tf_state:
        console.print(f"[cyan]Importing from Terraform state file: {tf_state}...[/]")
        graph = load_tf_state_file(tf_state)
    elif tf_dir:
        console.print(f"[cyan]Running 'terraform show -json' in {tf_dir}...[/]")
        try:
            graph = load_tf_state_cmd(tf_dir)
        except RuntimeError:
            console.print("[yellow]terraform show failed, falling back to HCL file parsing...[/]")
            graph = load_hcl_directory(tf_dir)
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
                f"{a['attribute']}: {a['before']} \u2192 {a['after']}"
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
