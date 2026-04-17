# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI command for War Room Simulation."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console


@app.command("war-room")
def war_room(
    yaml_file: Path = typer.Argument(..., help="Infrastructure YAML or JSON file"),
    incident: str = typer.Option(
        "database_outage", "--incident", "-i",
        help="Incident type to simulate",
    ),
    team_size: int = typer.Option(
        4, "--team-size", "-t",
        help="Number of team members (1-4)",
    ),
    runbook: bool = typer.Option(
        True, "--runbook/--no-runbook",
        help="Whether the team has a documented runbook",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON result"),
    list_incidents: bool = typer.Option(
        False, "--list", "-l",
        help="List available incident types and exit",
    ),
) -> None:
    """Simulate a multi-phase incident response war room exercise.

    Models realistic detection, triage, mitigation, recovery, and
    post-mortem phases with team roles and escalation paths.

    Examples:
        # Default database outage simulation
        faultray war-room infra.yaml

        # Specific incident with small team
        faultray war-room infra.yaml --incident cascading_failure --team-size 2

        # Without runbook
        faultray war-room infra.yaml --incident security_breach --no-runbook

        # List available incidents
        faultray war-room infra.yaml --list

        # JSON output
        faultray war-room infra.yaml --json
    """
    from faultray.simulator.war_room import WarRoomSimulator

    if list_incidents:
        # Create a minimal graph just to list incidents
        from faultray.model.graph import InfraGraph
        sim = WarRoomSimulator(InfraGraph())
        incidents = sim.available_incidents()
        console.print("[bold]Available Incident Types:[/]")
        for inc in incidents:
            console.print(f"  - {inc}")
        return

    graph = _load_graph_for_analysis(yaml_file, None)

    if not json_output:
        console.print(
            f"[cyan]Simulating war room exercise: {incident} "
            f"(team: {team_size}, runbook: {runbook})...[/]"
        )

    sim = WarRoomSimulator(graph)

    try:
        report = sim.simulate(
            incident_type=incident,
            team_size=team_size,
            has_runbook=runbook,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)

    if json_output:
        data = {
            "exercise_name": report.exercise_name,
            "scenario_description": report.scenario_description,
            "total_duration_minutes": report.total_duration_minutes,
            "time_to_detect_minutes": report.time_to_detect_minutes,
            "time_to_mitigate_minutes": report.time_to_mitigate_minutes,
            "time_to_recover_minutes": report.time_to_recover_minutes,
            "score": report.score,
            "roles_involved": report.roles_involved,
            "phases": [
                {
                    "name": p.name,
                    "duration_minutes": p.duration_minutes,
                    "objectives": p.objectives,
                    "success_criteria": p.success_criteria,
                }
                for p in report.phases
            ],
            "events": [
                {
                    "time_minutes": e.time_minutes,
                    "phase": e.phase,
                    "event_type": e.event_type,
                    "description": e.description,
                    "role_involved": e.role_involved,
                    "outcome": e.outcome,
                }
                for e in report.events
            ],
            "lessons_learned": report.lessons_learned,
        }
        console.print_json(json.dumps(data, indent=2))
        return

    _print_war_room_report(report, console)


def _print_war_room_report(report, con: Console) -> None:
    """Print a war room report with Rich formatting."""
    # Score badge
    if report.score >= 80:
        score_color = "green"
    elif report.score >= 50:
        score_color = "yellow"
    else:
        score_color = "red"

    # Summary panel
    summary = (
        f"[bold]{report.scenario_description}[/]\n\n"
        f"[bold]Score:[/] [{score_color}]{report.score:.0f}/100[/]\n"
        f"[bold]Duration:[/] {report.total_duration_minutes:.0f} minutes\n"
        f"[bold]Team:[/] {', '.join(report.roles_involved)}\n\n"
        f"[bold]Time to Detect:[/] {report.time_to_detect_minutes:.1f} min\n"
        f"[bold]Time to Mitigate:[/] {report.time_to_mitigate_minutes:.1f} min\n"
        f"[bold]Time to Recover:[/] {report.time_to_recover_minutes:.1f} min"
    )

    con.print()
    con.print(Panel(
        summary,
        title=f"[bold]{report.exercise_name}[/]",
        border_style=score_color,
    ))

    # Phases table
    phase_table = Table(title="Phases", show_header=True)
    phase_table.add_column("Phase", width=14, style="cyan")
    phase_table.add_column("Duration", width=10, justify="right")
    phase_table.add_column("Objectives", width=50)

    for phase in report.phases:
        objectives = "; ".join(phase.objectives[:2])
        phase_table.add_row(
            phase.name,
            f"{phase.duration_minutes:.1f} min",
            objectives,
        )

    con.print()
    con.print(phase_table)

    # Events timeline
    if report.events:
        event_table = Table(title="Event Timeline", show_header=True)
        event_table.add_column("Time", width=8, justify="right")
        event_table.add_column("Phase", width=12)
        event_table.add_column("Type", width=14)
        event_table.add_column("Description", width=45)
        event_table.add_column("Role", width=18)
        event_table.add_column("Result", width=8, justify="center")

        type_colors = {
            "alert_fired": "red",
            "escalation": "yellow",
            "action_taken": "cyan",
            "status_update": "dim",
        }
        outcome_colors = {
            "success": "green",
            "partial": "yellow",
            "failed": "red",
        }

        for event in report.events:
            tc = type_colors.get(event.event_type, "white")
            oc = outcome_colors.get(event.outcome, "white")
            event_table.add_row(
                f"{event.time_minutes:.1f}m",
                event.phase,
                f"[{tc}]{event.event_type}[/]",
                event.description[:45],
                event.role_involved,
                f"[{oc}]{event.outcome}[/]",
            )

        con.print()
        con.print(event_table)

    # Lessons learned
    if report.lessons_learned:
        con.print()
        con.print("[bold]Lessons Learned:[/]")
        for i, lesson in enumerate(report.lessons_learned, 1):
            con.print(f"  {i}. {lesson}")
