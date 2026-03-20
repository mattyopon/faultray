# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""CLI command for visual topology diff between two YAML files."""

from __future__ import annotations

import json as json_mod
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import app, console


@app.command(name="topo-diff")
def topo_diff_command(
    before: Path = typer.Argument(..., help="Path to the 'before' YAML topology file"),
    after: Path = typer.Argument(..., help="Path to the 'after' YAML topology file"),
    html: bool = typer.Option(False, "--html", help="Generate HTML report"),
    output: Path = typer.Option(None, "--output", "-o", help="Output file path (for HTML/JSON)"),
    mermaid: bool = typer.Option(False, "--mermaid", help="Output Mermaid diagram"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON summary"),
) -> None:
    """Compare two infrastructure YAML files and show topology differences.

    Like 'git diff' but for infrastructure topologies. Highlights additions,
    removals, and modifications between two versions.

    Examples:
        # Terminal diff
        faultray topo-diff before.yaml after.yaml

        # HTML report
        faultray topo-diff before.yaml after.yaml --html --output diff.html

        # Mermaid diagram
        faultray topo-diff before.yaml after.yaml --mermaid

        # JSON output
        faultray topo-diff before.yaml after.yaml --json
    """
    if not before.exists():
        console.print(f"[red]File not found: {before}[/]")
        raise typer.Exit(1)
    if not after.exists():
        console.print(f"[red]File not found: {after}[/]")
        raise typer.Exit(1)

    from faultray.reporter.topology_diff import TopologyDiffer

    differ = TopologyDiffer()
    result = differ.diff_files(before, after)

    # JSON output
    if json_output:
        data = result.to_dict()
        if output:
            output.write_text(json_mod.dumps(data, indent=2, default=str))
            console.print(f"[green]JSON written to {output}[/]")
        else:
            console.print_json(data=data)
        return

    # Mermaid output
    if mermaid:
        mermaid_text = differ.to_mermaid(result)
        if output:
            output.write_text(mermaid_text)
            console.print(f"[green]Mermaid diagram written to {output}[/]")
        else:
            console.print(mermaid_text)
        return

    # HTML output
    if html:
        html_text = differ.to_html(result)
        out_path = output or Path("topology-diff.html")
        out_path.write_text(html_text)
        console.print(f"[green]HTML report written to {out_path}[/]")
        return

    # Default: unified diff in terminal
    _print_terminal_diff(result, differ)


def _print_terminal_diff(result, differ) -> None:
    """Print a rich terminal diff."""
    # Score comparison
    if result.score_delta > 0:
        delta_str = f"[green]+{result.score_delta}[/]"
        border = "green"
    elif result.score_delta < 0:
        delta_str = f"[red]{result.score_delta}[/]"
        border = "red"
    else:
        delta_str = "[dim]0.0[/]"
        border = "blue"

    summary = (
        f"[bold]Resilience Score:[/] {result.score_before} -> {result.score_after} ({delta_str})\n"
        f"[bold]Risk Assessment:[/] {result.risk_assessment}\n"
        f"\n{result.summary}"
    )

    console.print()
    console.print(Panel(summary, title="[bold]Topology Diff[/]", border_style=border))

    # Changes table
    table = Table(show_header=True, title="Component Changes")
    table.add_column("ID", style="cyan", width=20)
    table.add_column("Name", width=20)
    table.add_column("Change", width=12)
    table.add_column("Details", width=50)

    for comp in result.components_added:
        table.add_row(comp.component_id, comp.component_name, "[green]Added[/]", "New component")

    for comp in result.components_removed:
        table.add_row(comp.component_id, comp.component_name, "[red]Removed[/]", "Component removed")

    for comp in result.components_modified:
        details = "; ".join(f"{ch.field}: {ch.old_value} -> {ch.new_value}" for ch in comp.changes)
        table.add_row(comp.component_id, comp.component_name, "[yellow]Modified[/]", details)

    if table.row_count > 0:
        console.print()
        console.print(table)

    # Edge changes
    if result.edges_added or result.edges_removed:
        edge_table = Table(show_header=True, title="Edge Changes")
        edge_table.add_column("Source", style="cyan", width=20)
        edge_table.add_column("Target", style="cyan", width=20)
        edge_table.add_column("Change", width=12)
        edge_table.add_column("Type", width=15)

        for edge in result.edges_added:
            edge_table.add_row(edge.source, edge.target, "[green]Added[/]", edge.new_type or "")

        for edge in result.edges_removed:
            edge_table.add_row(edge.source, edge.target, "[red]Removed[/]", edge.old_type or "")

        console.print()
        console.print(edge_table)

    # Unified diff preview
    console.print()
    unified = differ.to_unified_diff(result)
    for line in unified.split("\n"):
        if line.startswith("+"):
            console.print(f"[green]{line}[/]")
        elif line.startswith("-"):
            console.print(f"[red]{line}[/]")
        elif line.startswith("~"):
            console.print(f"[yellow]{line}[/]")
        elif line.startswith("@@"):
            console.print(f"[cyan]{line}[/]")
        else:
            console.print(f"[dim]{line}[/]")
