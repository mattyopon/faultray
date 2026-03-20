# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""CLI commands for Team Resilience Tracker."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import app, console

team_app = typer.Typer(
    name="team",
    help="Track and compare resilience metrics across teams.",
    no_args_is_help=True,
)
app.add_typer(team_app, name="team")


def _load_graph(model: Path):
    """Load InfraGraph from a model file (YAML or JSON)."""
    suffix = model.suffix.lower()
    if suffix in (".yaml", ".yml"):
        from faultray.model.loader import load_yaml
        return load_yaml(model)
    else:
        from faultray.model.graph import InfraGraph
        return InfraGraph.load(model)


def _get_tracker():
    from faultray.simulator.team_tracker import TeamTracker
    return TeamTracker()


def _get_mapping(graph, mapping_file: Path | None = None) -> dict[str, list[str]]:
    """Get team mapping from file or auto-assign."""
    if mapping_file and mapping_file.exists():
        data = json.loads(mapping_file.read_text(encoding="utf-8"))
        return data
    from faultray.simulator.team_tracker import auto_assign_teams
    return auto_assign_teams(graph)


@team_app.command("analyze")
def team_analyze(
    model: Path = typer.Argument(
        ...,
        help="Path to infrastructure model file (YAML or JSON).",
    ),
    mapping: Path = typer.Option(
        None, "--mapping", "-m",
        help="JSON file mapping team names to component IDs. Auto-assigns if omitted.",
    ),
    output_json: bool = typer.Option(
        False, "--json", help="Output as JSON.",
    ),
) -> None:
    """Analyze resilience metrics per team.

    Example:
        faultray team analyze infra.yaml
        faultray team analyze infra.yaml --mapping teams.json
        faultray team analyze infra.yaml --json
    """
    graph = _load_graph(model)
    tracker = _get_tracker()
    team_mapping = _get_mapping(graph, mapping)

    teams = tracker.analyze_teams(graph, team_mapping)

    if output_json:
        from dataclasses import asdict
        console.print_json(json.dumps([asdict(t) for t in teams], indent=2))
        return

    if not teams:
        console.print("[yellow]No team data found.[/]")
        raise typer.Exit(0)

    console.print()
    table = Table(title="Team Resilience Analysis", show_header=True, header_style="bold")
    table.add_column("Team", style="cyan", width=14)
    table.add_column("Score", justify="right", width=8)
    table.add_column("SPOFs", justify="right", width=7)
    table.add_column("Failover %", justify="right", width=12)
    table.add_column("CB %", justify="right", width=8)
    table.add_column("Maturity", justify="right", width=10)
    table.add_column("Risk $/yr", justify="right", width=12)
    table.add_column("Components", width=8, justify="right")

    for t in teams:
        score_color = "green" if t.resilience_score >= 70 else ("yellow" if t.resilience_score >= 40 else "red")
        table.add_row(
            t.team_name,
            f"[{score_color}]{t.resilience_score:.1f}[/]",
            str(t.spof_count),
            f"{t.failover_coverage:.0f}%",
            f"{t.circuit_breaker_coverage:.0f}%",
            f"L{t.sre_maturity_level}",
            f"${t.annual_risk_estimate:,.0f}",
            str(len(t.components_owned)),
        )

    console.print(table)
    console.print()


@team_app.command("compare")
def team_compare(
    model: Path = typer.Argument(
        ...,
        help="Path to infrastructure model file.",
    ),
    mapping: Path = typer.Option(
        None, "--mapping", "-m",
        help="JSON file mapping team names to component IDs.",
    ),
) -> None:
    """Compare resilience across teams side-by-side.

    Example:
        faultray team compare infra.yaml
    """
    graph = _load_graph(model)
    tracker = _get_tracker()
    team_mapping = _get_mapping(graph, mapping)

    comparison = tracker.compare_teams(graph, team_mapping)

    if not comparison.teams:
        console.print("[yellow]No teams to compare.[/]")
        raise typer.Exit(0)

    console.print()
    console.print(Panel(
        f"[green]Leader:[/] {comparison.leader}  |  "
        f"[red]Laggard:[/] {comparison.laggard}  |  "
        f"Avg Score: {comparison.avg_score:.1f}  |  "
        f"Spread: {comparison.score_spread:.1f}",
        title="Team Comparison",
        border_style="cyan",
    ))

    # Detailed comparison table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Team", style="cyan", width=14)
    table.add_column("Score", justify="right", width=8)
    table.add_column("SPOFs", justify="right", width=7)
    table.add_column("Failover", justify="right", width=10)
    table.add_column("CB Coverage", justify="right", width=12)
    table.add_column("Maturity", justify="right", width=10)

    for t in sorted(comparison.teams, key=lambda x: x.resilience_score, reverse=True):
        marker = ""
        if t.team_name == comparison.leader:
            marker = " [green]*[/]"
        elif t.team_name == comparison.laggard:
            marker = " [red]![/]"
        table.add_row(
            f"{t.team_name}{marker}",
            f"{t.resilience_score:.1f}",
            str(t.spof_count),
            f"{t.failover_coverage:.0f}%",
            f"{t.circuit_breaker_coverage:.0f}%",
            f"L{t.sre_maturity_level}",
        )

    console.print(table)

    # Improvement areas
    if comparison.improvement_areas:
        console.print("\n[bold]Improvement Areas:[/]")
        for team_name, areas in comparison.improvement_areas.items():
            console.print(f"\n  [cyan]{team_name}:[/]")
            for area in areas:
                console.print(f"    [yellow]*[/] {area}")

    console.print()


@team_app.command("leaderboard")
def team_leaderboard(
    model: Path = typer.Argument(
        ...,
        help="Path to infrastructure model file.",
    ),
    mapping: Path = typer.Option(
        None, "--mapping", "-m",
        help="JSON file mapping team names to component IDs.",
    ),
) -> None:
    """Show team resilience rankings.

    Example:
        faultray team leaderboard infra.yaml
    """
    graph = _load_graph(model)
    tracker = _get_tracker()
    team_mapping = _get_mapping(graph, mapping)

    lb = tracker.get_leaderboard(graph, team_mapping)

    if not lb.rankings:
        console.print("[yellow]No teams to rank.[/]")
        raise typer.Exit(0)

    console.print()
    table = Table(title="Team Resilience Leaderboard", show_header=True, header_style="bold")
    table.add_column("Rank", justify="right", width=6)
    table.add_column("Team", style="cyan", width=20)
    table.add_column("Score", justify="right", width=10)
    table.add_column("Status", width=15)

    for rank, team_name, score in lb.rankings:
        medal = ""
        if rank == 1:
            medal = " [gold1]#1[/]"
        elif rank == 2:
            medal = " [grey70]#2[/]"
        elif rank == 3:
            medal = " [dark_goldenrod]#3[/]"

        status = ""
        if team_name == lb.most_improved:
            status = "[green]Most Improved[/]"
        elif team_name in lb.needs_attention:
            status = "[red]Needs Attention[/]"
        else:
            status = "[dim]OK[/]"

        score_color = "green" if score >= 70 else ("yellow" if score >= 40 else "red")
        table.add_row(
            f"{rank}{medal}",
            team_name,
            f"[{score_color}]{score:.1f}[/]",
            status,
        )

    console.print(table)

    if lb.needs_attention:
        console.print(f"\n[red]Teams needing attention:[/] {', '.join(lb.needs_attention)}")

    console.print()


@team_app.command("record")
def team_record(
    model: Path = typer.Argument(
        ...,
        help="Path to infrastructure model file.",
    ),
    mapping: Path = typer.Option(
        None, "--mapping", "-m",
        help="JSON file mapping team names to component IDs.",
    ),
) -> None:
    """Record a snapshot of team metrics for historical tracking.

    Example:
        faultray team record infra.yaml
    """
    graph = _load_graph(model)
    tracker = _get_tracker()
    team_mapping = _get_mapping(graph, mapping)

    tracker.record_snapshot(graph, team_mapping)
    console.print("[green]Team metrics snapshot recorded.[/]")
    console.print("[dim]History stored at: ~/.faultzero/team_history.jsonl[/]")


@team_app.command("history")
def team_history(
    team_name: str = typer.Argument(
        ...,
        help="Team name to view history for.",
    ),
    days: int = typer.Option(
        90, "--days", "-d",
        help="Number of days to look back.",
    ),
) -> None:
    """Show historical metrics for a team.

    Example:
        faultray team history backend
        faultray team history data --days 30
    """
    tracker = _get_tracker()
    snapshots = tracker.get_team_history(team_name, days=days)

    if not snapshots:
        console.print(f"[yellow]No history found for team '{team_name}' in the last {days} days.[/]")
        console.print("[dim]Use 'faultray team record <yaml>' to start tracking.[/]")
        raise typer.Exit(0)

    console.print()
    table = Table(title=f"History for team '{team_name}' (last {days} days)", show_header=True, header_style="bold")
    table.add_column("Timestamp", width=22)
    table.add_column("Score", justify="right", width=8)
    table.add_column("SPOFs", justify="right", width=7)
    table.add_column("Failover %", justify="right", width=12)
    table.add_column("CB %", justify="right", width=8)
    table.add_column("Maturity", justify="right", width=10)

    for snap in snapshots:
        m = snap.metrics
        score_color = "green" if m.resilience_score >= 70 else ("yellow" if m.resilience_score >= 40 else "red")
        table.add_row(
            snap.timestamp[:19],
            f"[{score_color}]{m.resilience_score:.1f}[/]",
            str(m.spof_count),
            f"{m.failover_coverage:.0f}%",
            f"{m.circuit_breaker_coverage:.0f}%",
            f"L{m.sre_maturity_level}",
        )

    console.print(table)
    console.print()
