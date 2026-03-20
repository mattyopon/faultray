# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""CLI command for the Infrastructure Replay Engine (JSON timeline replay)."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console


@app.command("replay-timeline")
def replay_timeline(
    model_file: Path = typer.Argument(
        ...,
        help="Path to YAML/JSON infrastructure model file.",
    ),
    incident: Path = typer.Option(
        ..., "--incident", "-i",
        help="Path to incident timeline JSON file.",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON.",
    ),
) -> None:
    """Replay a past incident by converting a JSON timeline to a simulation.

    The incident JSON should contain an 'events' array with entries like:
        {"timestamp_offset_seconds": 0, "event_type": "component_down",
         "component_id": "db-primary", "details": "Disk full"}

    Examples:
        faultray replay-timeline infra.yaml --incident incident.json
        faultray replay-timeline infra.yaml --incident incident.json --json
    """
    from faultray.simulator.replay_engine import ReplayEngine

    graph = _load_graph_for_analysis(model_file, None)

    if not incident.exists():
        console.print(f"[red]Incident file not found: {incident}[/]")
        raise typer.Exit(1)

    engine = ReplayEngine(graph)
    timeline = engine.import_timeline_from_json(incident)

    if not json_output:
        console.print(
            f"[cyan]Replaying incident: {timeline.title} "
            f"({len(timeline.events)} events, "
            f"{timeline.duration_minutes:.0f}min)...[/]"
        )

    result = engine.replay(timeline)

    if json_output:
        data = {
            "incident_id": result.incident_id,
            "simulation_matches_reality": result.simulation_matches_reality,
            "predicted_severity": result.predicted_severity,
            "actual_severity": result.actual_severity,
            "divergence_point_seconds": result.divergence_point_seconds,
            "lessons": result.lessons,
            "counterfactuals": [
                {
                    "description": cf.description,
                    "modified_parameter": cf.modified_parameter,
                    "original_value": cf.original_value,
                    "modified_value": cf.modified_value,
                    "original_severity": cf.original_severity,
                    "counterfactual_severity": cf.counterfactual_severity,
                    "improvement": cf.improvement,
                }
                for cf in result.counterfactuals
            ],
        }
        console.print_json(data=data)
        return

    # Summary panel
    match_str = (
        "[green]YES[/]" if result.simulation_matches_reality
        else "[yellow]NO[/]"
    )
    border = "green" if result.simulation_matches_reality else "yellow"

    summary = (
        f"[bold]Incident:[/] {timeline.title} ({result.incident_id})\n"
        f"[bold]Duration:[/] {timeline.duration_minutes:.0f} minutes\n"
        f"[bold]Root Cause:[/] {timeline.root_cause or 'N/A'}\n\n"
        f"[bold]Simulation matches reality:[/] {match_str}\n"
        f"[bold]Predicted severity:[/] {result.predicted_severity:.1f}/10\n"
        f"[bold]Actual severity:[/] {result.actual_severity:.1f}/10"
    )
    if result.divergence_point_seconds is not None:
        summary += (
            f"\n[bold]Divergence at:[/] t={result.divergence_point_seconds}s"
        )

    console.print()
    console.print(Panel(
        summary,
        title="[bold]Incident Replay Result[/]",
        border_style=border,
    ))

    # Lessons
    if result.lessons:
        console.print("\n[bold cyan]Lessons Learned:[/]")
        for i, lesson in enumerate(result.lessons, 1):
            console.print(f"  {i}. {lesson}")

    # Counterfactuals table
    if result.counterfactuals:
        cf_table = Table(
            title="Counterfactual Analysis (What-If)",
            show_header=True,
        )
        cf_table.add_column("What-If", width=50)
        cf_table.add_column("Param", width=20)
        cf_table.add_column("Original", width=10, justify="right")
        cf_table.add_column("Modified", width=10, justify="right")
        cf_table.add_column("Improvement", width=12, justify="right")

        for cf in result.counterfactuals:
            imp_color = "green" if cf.improvement > 0 else "red"
            cf_table.add_row(
                cf.description[:50],
                cf.modified_parameter,
                cf.original_value,
                cf.modified_value,
                f"[{imp_color}]{cf.improvement:+.1f}[/]",
            )

        console.print()
        console.print(cf_table)
