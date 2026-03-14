"""Backtest CLI command -- validate ChaosProof predictions against real incidents."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.table import Table

from infrasim.cli.main import (
    app,
    console,
    _load_graph_for_analysis,
)


@app.command()
def backtest(
    infra_file: Path = typer.Argument(
        ..., help="Path to infrastructure YAML or JSON model.",
    ),
    incidents: Path = typer.Option(
        ..., "--incidents", "-i",
        help="Path to incidents JSON file.",
    ),
    output_json: bool = typer.Option(
        False, "--json", "-j",
        help="Output results as JSON.",
    ),
    yaml_file: Path | None = typer.Option(
        None, "--yaml", "-y",
        help="Load from YAML instead (overrides infra_file).",
    ),
) -> None:
    """Validate ChaosProof predictions against real incidents."""
    from infrasim.simulator.backtest_engine import BacktestEngine

    # Load graph
    graph = _load_graph_for_analysis(infra_file, yaml_file)

    # Load incidents
    if not incidents.exists():
        console.print(f"[red]Incidents file not found: {incidents}[/]")
        raise typer.Exit(1)

    engine = BacktestEngine(graph)
    real_incidents = engine.load_incidents(incidents)
    results = engine.run_backtest(real_incidents)
    summary = engine.summary(results)

    if output_json:
        console.print(json.dumps(summary, indent=2))
        return

    # Rich table output
    console.print()
    console.print(
        f"[bold]ChaosProof Backtest Results[/]  "
        f"({summary['total_incidents']} incidents)"
    )
    console.print()

    table = Table(show_header=True, header_style="bold")
    table.add_column("Incident", width=12)
    table.add_column("Component", width=20)
    table.add_column("Precision", justify="right", width=10)
    table.add_column("Recall", justify="right", width=10)
    table.add_column("F1 Score", justify="right", width=10)

    for r in summary.get("results", []):
        f1 = r["f1"]
        if f1 >= 0.8:
            f1_str = f"[green]{f1:.3f}[/]"
        elif f1 >= 0.5:
            f1_str = f"[yellow]{f1:.3f}[/]"
        else:
            f1_str = f"[red]{f1:.3f}[/]"

        table.add_row(
            r["incident_id"],
            r["component"],
            f"{r['precision']:.3f}",
            f"{r['recall']:.3f}",
            f1_str,
        )

    console.print(table)
    console.print()
    console.print(
        f"  [bold]Average Precision:[/] {summary['avg_precision']:.3f}  "
        f"[bold]Recall:[/] {summary['avg_recall']:.3f}  "
        f"[bold]F1:[/] {summary['avg_f1']:.3f}"
    )
    console.print()
