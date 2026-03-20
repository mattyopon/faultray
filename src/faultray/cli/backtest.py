# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Backtest CLI command -- validate FaultRay predictions against real incidents."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.table import Table

from faultray.cli.main import (
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
    engine: str = typer.Option(
        "cascade", "--engine", "-e",
        help="Simulation engine to use: cascade (default) or all.",
    ),
    calibrate: bool = typer.Option(
        False, "--calibrate", "-c",
        help="Show calibration recommendations.",
    ),
    report: str = typer.Option(
        "text", "--report", "-r",
        help="Output format: text (default) or json.",
    ),
) -> None:
    """Validate FaultRay predictions against real incidents.

    Examples:
        # Run backtest with incidents file
        faultray backtest infra.yaml --incidents incidents.json

        # JSON output
        faultray backtest infra.yaml --incidents incidents.json --json

        # Use YAML override
        faultray backtest model.json --yaml infra.yaml --incidents incidents.json

        # Show calibration recommendations
        faultray backtest infra.yaml --incidents incidents.json --calibrate

        # JSON report format
        faultray backtest infra.yaml --incidents incidents.json --report json
    """
    from faultray.simulator.backtest_engine import BacktestEngine

    # Load graph
    graph = _load_graph_for_analysis(infra_file, yaml_file)

    # Load incidents
    if not incidents.exists():
        console.print(f"[red]Incidents file not found: {incidents}[/]")
        raise typer.Exit(1)

    bt_engine = BacktestEngine(graph)
    real_incidents = bt_engine.load_incidents(incidents)
    results = bt_engine.run_backtest(real_incidents)
    summary_data = bt_engine.summary(results)

    # JSON output (--json flag or --report json)
    if output_json or report == "json":
        console.print(json.dumps(summary_data, indent=2))
        return

    # Rich table output
    console.print()
    console.print(
        f"[bold]FaultRay Backtest Results[/]  "
        f"({summary_data['total_incidents']} incidents, engine={engine})"
    )
    console.print()

    table = Table(show_header=True, header_style="bold")
    table.add_column("Incident", width=12)
    table.add_column("Component", width=20)
    table.add_column("Precision", justify="right", width=10)
    table.add_column("Recall", justify="right", width=10)
    table.add_column("F1 Score", justify="right", width=10)
    table.add_column("Sev Acc", justify="right", width=10)
    table.add_column("DT MAE", justify="right", width=10)
    table.add_column("Confidence", justify="right", width=10)

    for r in summary_data.get("per_incident", []):
        f1 = r["f1"]
        if f1 >= 0.8:
            f1_str = f"[green]{f1:.3f}[/]"
        elif f1 >= 0.5:
            f1_str = f"[yellow]{f1:.3f}[/]"
        else:
            f1_str = f"[red]{f1:.3f}[/]"

        conf = r["confidence"]
        if conf >= 0.7:
            conf_str = f"[green]{conf:.3f}[/]"
        elif conf >= 0.4:
            conf_str = f"[yellow]{conf:.3f}[/]"
        else:
            conf_str = f"[red]{conf:.3f}[/]"

        table.add_row(
            r["incident_id"],
            r["component"],
            f"{r['precision']:.3f}",
            f"{r['recall']:.3f}",
            f1_str,
            f"{r['severity_accuracy']:.3f}",
            f"{r['downtime_mae']:.1f}m",
            conf_str,
        )

    console.print(table)
    console.print()
    console.print(
        f"  [bold]Avg Precision:[/] {summary_data['avg_precision']:.3f}  "
        f"[bold]Recall:[/] {summary_data['avg_recall']:.3f}  "
        f"[bold]F1:[/] {summary_data['avg_f1']:.3f}"
    )
    console.print(
        f"  [bold]Avg Severity Accuracy:[/] {summary_data['avg_severity_accuracy']:.3f}  "
        f"[bold]Downtime MAE:[/] {summary_data['avg_downtime_mae_minutes']:.1f}m  "
        f"[bold]Confidence:[/] {summary_data['avg_confidence']:.3f}"
    )
    console.print()

    # Calibration output
    if calibrate:
        cal = summary_data.get("calibration", {})
        if cal:
            console.print("[bold]Calibration Recommendations:[/]")
            for key, value in cal.items():
                console.print(f"  {key}: {value}")
        else:
            console.print("[green]No calibration adjustments needed.[/]")
        console.print()
