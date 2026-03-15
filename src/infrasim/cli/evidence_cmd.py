"""CLI commands for Compliance Evidence Auto-Generator."""

from __future__ import annotations

import json as json_mod
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from infrasim.cli.main import app, console

evidence_app = typer.Typer(
    name="evidence",
    help="Compliance Evidence — Auto-generate audit-ready evidence from simulations",
    no_args_is_help=True,
)
app.add_typer(evidence_app, name="evidence")


def _load_graph(yaml_file: Path) -> "InfraGraph":  # noqa: F821
    """Load an InfraGraph from a YAML or JSON file."""
    if not yaml_file.exists():
        console.print(f"[red]File not found: {yaml_file}[/]")
        raise typer.Exit(1)

    try:
        if str(yaml_file).endswith((".yaml", ".yml")):
            from infrasim.model.loader import load_yaml
            return load_yaml(yaml_file)
        else:
            from infrasim.model.graph import InfraGraph
            return InfraGraph.load(yaml_file)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)


@evidence_app.command("generate")
def evidence_generate(
    model: Path = typer.Argument(..., help="Infrastructure model file"),
    framework: str = typer.Option("SOC2", "--framework", "-f", help="Compliance framework (SOC2, DORA, ISO27001, PCI-DSS)"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Export CSV to this path"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
    simulate: bool = typer.Option(False, "--simulate", "-s", help="Run simulation first, then generate evidence"),
) -> None:
    """Generate compliance evidence for a framework.

    Examples:
        faultray evidence generate model.yaml --framework SOC2 --output evidence.csv
        faultray evidence generate model.yaml --framework DORA --json
        faultray evidence generate model.yaml --framework ISO27001 --simulate
    """
    from infrasim.reporter.evidence_generator import EvidenceGenerator

    graph = _load_graph(model)

    sim_report = None
    if simulate:
        from infrasim.simulator.engine import SimulationEngine
        if not json_output:
            console.print("[cyan]Running chaos simulation...[/]")
        engine = SimulationEngine(graph)
        sim_report = engine.run_all_defaults()

    gen = EvidenceGenerator(graph)

    try:
        package = gen.generate(framework, simulation_report=sim_report)
    except ValueError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)

    if output:
        gen.export_csv(package, output)
        if not json_output:
            console.print(f"[green]Evidence exported to {output}[/]")

    if json_output:
        console.print_json(data=gen.export_json(package))
        return

    # Rich output
    passed_color = "green" if package.passed == package.total_controls_tested else "yellow"
    console.print(Panel(
        f"[bold]Framework:[/] {package.framework}\n"
        f"[bold]Controls Tested:[/] {package.total_controls_tested}\n"
        f"[bold]Passed:[/] [{passed_color}]{package.passed}[/]  "
        f"[bold]Failed:[/] [red]{package.failed}[/]\n"
        f"[bold]Coverage:[/] {package.coverage_percent:.1f}%",
        title="[bold]Compliance Evidence Package[/]",
        border_style="cyan",
    ))

    table = Table(title=f"{package.framework} Evidence Items", show_header=True)
    table.add_column("Control", style="cyan", width=12)
    table.add_column("Description", width=35)
    table.add_column("Test", width=18)
    table.add_column("Result", width=8, justify="center")
    table.add_column("Detail", width=45)

    for item in package.items:
        result_color = {
            "Pass": "green",
            "Fail": "red",
            "Partial": "yellow",
        }.get(item.result, "white")
        table.add_row(
            item.control_id,
            item.control_description,
            item.test_performed,
            f"[{result_color}]{item.result}[/]",
            item.evidence_detail[:80] + ("..." if len(item.evidence_detail) > 80 else ""),
        )
    console.print()
    console.print(table)


@evidence_app.command("frameworks")
def evidence_frameworks() -> None:
    """List supported compliance frameworks.

    Examples:
        faultray evidence frameworks
    """
    from infrasim.reporter.evidence_generator import EvidenceGenerator, CONTROL_MAPPINGS

    table = Table(title="Supported Compliance Frameworks", show_header=True)
    table.add_column("Framework", style="cyan", width=15)
    table.add_column("Controls", justify="right", width=10)
    table.add_column("Control IDs", width=50)

    for fw, controls in CONTROL_MAPPINGS.items():
        ids = ", ".join(sorted(controls.keys()))
        table.add_row(fw, str(len(controls)), ids)

    console.print(table)
