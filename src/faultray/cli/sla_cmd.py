"""SLA validation CLI commands."""

from __future__ import annotations

import json as json_mod
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console


@app.command("sla-validate")
def sla_validate(
    yaml_file: Path = typer.Argument(..., help="Infrastructure YAML or JSON file"),
    target: float = typer.Option(99.99, "--target", "-t", help="Target availability percentage (e.g., 99.99)"),
    window: str = typer.Option("monthly", "--window", "-w", help="Measurement window: monthly, quarterly, annual"),
    simulations: int = typer.Option(10000, "--simulations", "-s", help="Monte Carlo simulations for confidence"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Validate whether an SLA target is achievable for the infrastructure.

    Performs mathematical analysis to determine if a given availability
    target (e.g., 99.99%) is achievable with the current topology.

    Examples:
        # Validate 99.99% SLA target
        faultray sla-validate infra.yaml --target 99.99

        # With monthly measurement window
        faultray sla-validate infra.yaml --target 99.99 --window monthly

        # Quick check with fewer simulations
        faultray sla-validate infra.yaml --target 99.9 --simulations 1000

        # JSON output for CI/CD
        faultray sla-validate infra.yaml --target 99.99 --json
    """
    import math

    from faultray.simulator.sla_validator import SLATarget, SLAValidatorEngine

    # Convert percentage to nines
    if target >= 100.0:
        console.print("[red]Target must be less than 100%[/]")
        raise typer.Exit(1)
    target_nines = -math.log10(1.0 - target / 100.0)

    graph = _load_graph_for_analysis(
        model=Path("faultray-model.json"),
        yaml_file=yaml_file,
    )

    sla_target = SLATarget(
        name="System Availability",
        target_nines=target_nines,
        measurement_window=window,
    )

    if not json_output:
        console.print(f"[cyan]Validating SLA target: {target}% ({target_nines:.2f} nines)...[/]")
        console.print(f"[dim]Components: {len(graph.components)} | Window: {window} | Simulations: {simulations}[/]")

    engine = SLAValidatorEngine()
    result = engine.prove_achievability(graph, target_nines, sla_target)

    if json_output:
        output = {
            "target_nines": round(target_nines, 4),
            "target_percent": round(target, 4),
            "achievable": result.achievable,
            "calculated_availability": round(result.calculated_availability * 100, 6),
            "calculated_nines": round(result.calculated_nines, 4),
            "confidence_level": round(result.confidence_level, 4),
            "gap_nines": round(result.gap_nines, 4),
            "allowed_downtime_seconds": result.allowed_downtime.total_seconds(),
            "estimated_downtime_seconds": result.estimated_downtime.total_seconds(),
            "risk_of_breach": round(result.risk_of_breach, 4),
            "expected_penalty_cost": result.expected_penalty_cost,
            "bottleneck_components": result.bottleneck_components,
            "improvements": [
                {
                    "component": imp.component,
                    "current_availability": round(imp.current_availability * 100, 4),
                    "needed_availability": round(imp.needed_availability * 100, 4),
                    "suggestion": imp.suggestion,
                    "cost_estimate": imp.cost_estimate,
                }
                for imp in result.improvement_needed
            ],
        }
        console.print_json(json_mod.dumps(output, indent=2))
        return

    _print_sla_result(result, console)


@app.command("sla-prove")
def sla_prove(
    yaml_file: Path = typer.Argument(..., help="Infrastructure YAML or JSON file"),
    target: float = typer.Option(99.999, "--target", "-t", help="Target availability percentage"),
    window: str = typer.Option("monthly", "--window", "-w", help="Measurement window"),
) -> None:
    """Generate a full mathematical proof of SLA achievability.

    Produces a detailed step-by-step mathematical proof showing
    how the system availability is calculated from component
    availabilities, replicas, and critical path analysis.

    Examples:
        # Full proof for 99.999% target
        faultray sla-prove infra.yaml --target 99.999

        # Prove with annual window
        faultray sla-prove infra.yaml --target 99.99 --window annual
    """
    import math

    from faultray.simulator.sla_validator import SLATarget, SLAValidatorEngine

    if target >= 100.0:
        console.print("[red]Target must be less than 100%[/]")
        raise typer.Exit(1)
    target_nines = -math.log10(1.0 - target / 100.0)

    graph = _load_graph_for_analysis(
        model=Path("faultray-model.json"),
        yaml_file=yaml_file,
    )

    sla_target = SLATarget(
        name="System Availability",
        target_nines=target_nines,
        measurement_window=window,
    )

    console.print(f"[cyan]Generating mathematical proof for {target}% SLA...[/]")

    engine = SLAValidatorEngine()
    result = engine.prove_achievability(graph, target_nines, sla_target)

    # Print the full mathematical proof
    console.print()
    console.print(Panel(
        result.mathematical_proof,
        title="[bold]Mathematical Proof of SLA Achievability[/]",
        border_style="cyan" if result.achievable else "red",
    ))


@app.command("sla-improve")
def sla_improve(
    yaml_file: Path = typer.Argument(..., help="Infrastructure YAML or JSON file"),
    target: float = typer.Option(99.99, "--target", "-t", help="Target availability percentage"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show minimum infrastructure changes needed to achieve an SLA target.

    Analyzes the current topology and identifies the most cost-effective
    changes to reach the desired availability level.

    Examples:
        # Show improvements needed for 99.99%
        faultray sla-improve infra.yaml --target 99.99

        # JSON output
        faultray sla-improve infra.yaml --target 99.99 --json
    """
    import math

    from faultray.simulator.sla_validator import SLAValidatorEngine

    if target >= 100.0:
        console.print("[red]Target must be less than 100%[/]")
        raise typer.Exit(1)
    target_nines = -math.log10(1.0 - target / 100.0)

    graph = _load_graph_for_analysis(
        model=Path("faultray-model.json"),
        yaml_file=yaml_file,
    )

    console.print(f"[cyan]Finding minimum changes for {target}% SLA target...[/]")

    engine = SLAValidatorEngine()
    current_avail = engine.calculate_critical_path_availability(graph)
    improvements = engine.find_minimum_changes(graph, target_nines)

    if json_output:
        output = {
            "current_availability": round(current_avail * 100, 6),
            "current_nines": round(-math.log10(1.0 - current_avail) if current_avail < 1.0 else float("inf"), 4),
            "target_percent": round(target, 4),
            "target_nines": round(target_nines, 4),
            "already_achievable": current_avail >= (1.0 - 10.0 ** (-target_nines)),
            "improvements": [
                {
                    "component": imp.component,
                    "current_availability": round(imp.current_availability * 100, 4),
                    "needed_availability": round(imp.needed_availability * 100, 4),
                    "suggestion": imp.suggestion,
                    "cost_estimate": imp.cost_estimate,
                }
                for imp in improvements
            ],
        }
        console.print_json(json_mod.dumps(output, indent=2))
        return

    current_nines = -math.log10(1.0 - current_avail) if current_avail < 1.0 else float("inf")

    # Summary panel
    summary = (
        f"[bold]Current Availability:[/] {current_avail * 100:.4f}% ({current_nines:.2f} nines)\n"
        f"[bold]Target Availability:[/] {target}% ({target_nines:.2f} nines)\n"
    )

    if not improvements:
        summary += "\n[green]SLA target is already achievable with current infrastructure.[/]"
        console.print(Panel(summary, title="[bold]SLA Improvement Analysis[/]", border_style="green"))
        return

    summary += f"\n[yellow]{len(improvements)} improvement(s) needed:[/]"
    console.print(Panel(summary, title="[bold]SLA Improvement Analysis[/]", border_style="yellow"))

    # Improvements table
    table = Table(title="Required Improvements", show_header=True)
    table.add_column("Component", style="cyan", width=20)
    table.add_column("Current", justify="right", width=12)
    table.add_column("Needed", justify="right", width=12)
    table.add_column("Suggestion", width=50)
    table.add_column("Cost", justify="center", width=8)

    cost_colors = {"low": "green", "medium": "yellow", "high": "red"}

    for imp in improvements:
        cost_color = cost_colors.get(imp.cost_estimate, "white")
        table.add_row(
            imp.component,
            f"{imp.current_availability * 100:.4f}%",
            f"{imp.needed_availability * 100:.4f}%",
            imp.suggestion,
            f"[{cost_color}]{imp.cost_estimate.upper()}[/]",
        )

    console.print()
    console.print(table)


def _print_sla_result(result, con: Console) -> None:
    """Print SLA validation result with Rich formatting."""
    target = result.target
    achievable = result.achievable

    # Status panel
    if achievable:
        status_text = "[bold green]ACHIEVABLE[/]"
        border_color = "green"
    else:
        status_text = "[bold red]NOT ACHIEVABLE[/]"
        border_color = "red"

    summary = (
        f"[bold]SLA Target:[/] {target.name}\n"
        f"[bold]Target:[/] {target.target_percent:.4f}% ({target.target_nines:.2f} nines)\n"
        f"[bold]Calculated:[/] {result.calculated_percent:.6f}% ({result.calculated_nines:.2f} nines)\n"
        f"[bold]Status:[/] {status_text}\n"
        f"[bold]Confidence:[/] {result.confidence_level * 100:.1f}%\n"
        f"\n"
        f"[bold]Allowed Downtime ({target.measurement_window}):[/] {result.allowed_downtime}\n"
        f"[bold]Estimated Downtime ({target.measurement_window}):[/] {result.estimated_downtime}\n"
        f"[bold]Risk of Breach:[/] {result.risk_of_breach * 100:.2f}%"
    )

    if result.expected_penalty_cost > 0:
        summary += f"\n[bold]Expected Penalty Cost:[/] ${result.expected_penalty_cost:,.2f}"

    con.print()
    con.print(Panel(
        summary,
        title="[bold]SLA Validation Result[/]",
        border_style=border_color,
    ))

    # Bottleneck components
    if result.bottleneck_components:
        con.print()
        con.print("[bold]Bottleneck Components:[/] (most limiting first)")
        for i, comp_id in enumerate(result.bottleneck_components[:5], 1):
            con.print(f"  {i}. [cyan]{comp_id}[/]")

    # Improvements needed
    if result.improvement_needed:
        table = Table(title="Improvements Needed", show_header=True)
        table.add_column("Component", style="cyan", width=20)
        table.add_column("Current", justify="right", width=12)
        table.add_column("Needed", justify="right", width=12)
        table.add_column("Suggestion", width=45)
        table.add_column("Cost", justify="center", width=8)

        cost_colors = {"low": "green", "medium": "yellow", "high": "red"}

        for imp in result.improvement_needed:
            cost_color = cost_colors.get(imp.cost_estimate, "white")
            table.add_row(
                imp.component,
                f"{imp.current_availability * 100:.4f}%",
                f"{imp.needed_availability * 100:.4f}%",
                imp.suggestion,
                f"[{cost_color}]{imp.cost_estimate.upper()}[/]",
            )

        con.print()
        con.print(table)

    # Gap summary
    if result.gap_nines > 0:
        con.print()
        con.print(Panel(
            f"[bold red]Gap: {result.gap_nines:.2f} nines[/]\n"
            f"The infrastructure is {result.gap_nines:.2f} nines short of the target.\n"
            f"Review the improvements above to close this gap.",
            title="[bold]Gap Analysis[/]",
            border_style="red",
        ))
    elif result.gap_nines < 0:
        margin = abs(result.gap_nines)
        con.print()
        con.print(Panel(
            f"[bold green]Safety Margin: {margin:.2f} nines[/]\n"
            f"The infrastructure exceeds the target by {margin:.2f} nines.",
            title="[bold]Safety Margin[/]",
            border_style="green",
        ))
