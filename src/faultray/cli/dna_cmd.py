"""CLI commands for Infrastructure DNA Fingerprinting."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console


@app.command("dna")
def dna(
    action: str = typer.Argument(
        ..., help="Action: fingerprint | compare"
    ),
    file1: Path = typer.Argument(
        ..., help="Infrastructure model file (YAML or JSON)"
    ),
    file2: Path = typer.Argument(
        default=None, help="Second model file (for compare)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Infrastructure DNA Fingerprinting — compute and compare fingerprints.

    Examples:
        # Compute DNA fingerprint
        faultray dna fingerprint infra.yaml

        # Compare two infrastructures
        faultray dna compare infra-v1.yaml infra-v2.yaml

        # JSON output
        faultray dna fingerprint infra.yaml --json
    """
    from faultray.model.dna import DNAEngine

    if action == "fingerprint":
        graph = _load_graph_for_analysis(file1, file1)
        dna_result = DNAEngine.compute(graph)

        if json_output:
            console.print_json(data={
                "fingerprint": dna_result.fingerprint,
                "topology_hash": dna_result.topology_hash,
                "component_hash": dna_result.component_hash,
                "config_hash": dna_result.config_hash,
                "component_count": dna_result.component_count,
                "dependency_count": dna_result.dependency_count,
                "max_chain_depth": dna_result.max_chain_depth,
                "redundancy_pattern": dna_result.redundancy_pattern,
                "architecture_type": dna_result.architecture_type,
            })
            return

        console.print()
        console.print(Panel(
            f"[bold cyan]{dna_result.fingerprint}[/]",
            title="[bold]Infrastructure DNA Fingerprint[/]",
            border_style="cyan",
        ))

        table = Table(show_header=True, header_style="bold")
        table.add_column("Property", width=24)
        table.add_column("Value", width=40)

        table.add_row("Topology Hash", dna_result.topology_hash)
        table.add_row("Component Hash", dna_result.component_hash)
        table.add_row("Config Hash", dna_result.config_hash)
        table.add_row("Component Count", str(dna_result.component_count))
        table.add_row("Dependency Count", str(dna_result.dependency_count))
        table.add_row("Max Chain Depth", str(dna_result.max_chain_depth))
        table.add_row("Redundancy Pattern", dna_result.redundancy_pattern)
        table.add_row("Architecture Type", dna_result.architecture_type)

        console.print(table)

    elif action == "compare":
        if file2 is None:
            console.print("[red]Please provide two model files for comparison.[/]")
            raise typer.Exit(1)

        graph1 = _load_graph_for_analysis(file1, file1)
        graph2 = _load_graph_for_analysis(file2, file2)
        result = DNAEngine.compare(graph1, graph2)

        if json_output:
            console.print_json(data={
                "similarity": result.similarity,
                "matching_components": result.matching_components,
                "matching_topology": result.matching_topology,
                "architecture_match": result.architecture_match,
            })
            return

        # Color based on similarity
        if result.similarity >= 0.8:
            sim_color = "green"
        elif result.similarity >= 0.5:
            sim_color = "yellow"
        else:
            sim_color = "red"

        summary = (
            f"[bold]Similarity:[/] [{sim_color}]{result.similarity:.1%}[/]\n"
            f"[bold]Matching Components:[/] {result.matching_components}\n"
            f"[bold]Topology Similarity:[/] {result.matching_topology:.1%}\n"
            f"[bold]Architecture Match:[/] "
            + ("[green]Yes[/]" if result.architecture_match else "[red]No[/]")
        )

        console.print()
        console.print(Panel(
            summary,
            title="[bold]DNA Comparison[/]",
            border_style=sim_color,
        ))

    else:
        console.print(f"[red]Unknown action: {action}. Use fingerprint|compare[/]")
        raise typer.Exit(1)
