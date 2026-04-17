# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI commands for the Resilience Timeline Tracker."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import app, console, _load_graph_for_analysis, DEFAULT_MODEL_PATH

if TYPE_CHECKING:
    from faultray.simulator.resilience_timeline import ResilienceTimeline


@app.command(name="timeline")
def timeline(
    action: str = typer.Argument(
        "show",
        help="Action: show, trends, milestones, export, record, reset",
    ),
    days: int = typer.Option(90, "--days", "-d", help="Number of days to display"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output path for export"),
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file for 'record' action"),
    yaml_file: Path | None = typer.Option(None, "--yaml", "-y", help="YAML model file for 'record' action"),
    event: str | None = typer.Option(None, "--event", "-e", help="Event description for 'record' action"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    width: int = typer.Option(40, "--width", "-w", help="Sparkline width"),
) -> None:
    """Track and visualize infrastructure resilience evolution over time.

    Like 'git log' for your resilience scores.

    Actions:
        show       - Show timeline with sparkline (default)
        trends     - Show trend analysis for 7d/30d/90d
        milestones - Show milestone events
        export     - Export timeline to CSV (requires --output)
        record     - Manually record a snapshot from a model file
        reset      - Clear all timeline data

    Examples:
        # Show last 90 days of timeline
        faultray timeline

        # Show last 30 days
        faultray timeline show --days 30

        # Show trend analysis
        faultray timeline trends

        # Show milestones
        faultray timeline milestones

        # Export to CSV
        faultray timeline export --output timeline.csv

        # Record a snapshot from a model
        faultray timeline record --yaml infra.yaml --event "Added Redis cluster"

        # Reset timeline data
        faultray timeline reset
    """
    from faultray.simulator.resilience_timeline import ResilienceTimeline

    tl = ResilienceTimeline()

    if action == "show":
        _show_timeline(tl, days, json_output, width)
    elif action == "trends":
        _show_trends(tl, json_output)
    elif action == "milestones":
        _show_milestones(tl, json_output)
    elif action == "export":
        _export_timeline(tl, output)
    elif action == "record":
        _record_snapshot(tl, model, yaml_file, event, json_output)
    elif action == "reset":
        _reset_timeline(tl)
    else:
        console.print(f"[red]Unknown action: {action}[/]")
        console.print("[dim]Valid actions: show, trends, milestones, export, record, reset[/]")
        raise typer.Exit(1)


def _show_timeline(
    tl: "ResilienceTimeline",
    days: int,
    json_output: bool,
    width: int,
) -> None:
    """Display the timeline with a Rich table and sparkline."""

    report = tl.generate_report()
    snapshots = tl.get_history(days=days)

    if json_output:
        data = {
            "current_score": report.current_score,
            "all_time_high": report.all_time_high,
            "all_time_low": report.all_time_low,
            "days_tracked": report.days_tracked,
            "total_snapshots": report.total_snapshots,
            "sparkline": report.sparkline,
            "snapshots": [s.to_dict() for s in snapshots],
        }
        console.print_json(data=data)
        return

    if not snapshots:
        console.print(
            "\n[yellow]No timeline data found.[/]\n"
            "[dim]Run 'faultray simulate' or 'faultray timeline record' to start tracking.[/]"
        )
        return

    # Sparkline
    scores = [s.resilience_score for s in snapshots]
    from faultray.simulator.resilience_timeline import _generate_sparkline

    sparkline = _generate_sparkline(scores, width=width)

    # Summary panel
    score = report.current_score
    if score >= 80:
        score_color = "green"
    elif score >= 60:
        score_color = "yellow"
    else:
        score_color = "red"

    summary = (
        f"[bold]Current Score:[/] [{score_color}]{score:.1f}[/]\n"
        f"[bold]All-Time High:[/] {report.all_time_high:.1f}  |  "
        f"[bold]All-Time Low:[/] {report.all_time_low:.1f}\n"
        f"[bold]Days Tracked:[/] {report.days_tracked}  |  "
        f"[bold]Snapshots:[/] {report.total_snapshots}\n"
        f"[bold]Regressions:[/] {len(report.regressions)}\n\n"
        f"[bold]Score History:[/] {sparkline}"
    )

    console.print()
    console.print(Panel(
        summary,
        title=f"[bold]Resilience Timeline ({days} days)[/]",
        border_style=score_color,
    ))

    # Snapshot table
    table = Table(
        title=f"Snapshots ({len(snapshots)} entries)",
        show_header=True,
    )
    table.add_column("Date", style="dim", width=20)
    table.add_column("Score", justify="right", width=8)
    table.add_column("Components", justify="right", width=12)
    table.add_column("SPOFs", justify="right", width=8)
    table.add_column("Critical", justify="right", width=10)
    table.add_column("Warnings", justify="right", width=10)
    table.add_column("Event", width=30)

    # Show last 25 entries
    display_entries = snapshots[-25:]
    if len(snapshots) > 25:
        console.print(
            f"\n[dim]Showing last 25 of {len(snapshots)} entries[/]"
        )

    for snap in display_entries:
        s = snap.resilience_score
        if s >= 80:
            s_color = "green"
        elif s >= 60:
            s_color = "yellow"
        else:
            s_color = "red"

        crit_style = "red" if snap.critical_findings > 0 else "dim"
        warn_style = "yellow" if snap.warning_count > 0 else "dim"
        spof_style = "red" if snap.spof_count > 0 else "dim"

        table.add_row(
            snap.timestamp[:19],
            f"[{s_color}]{s:.1f}[/]",
            str(snap.component_count),
            f"[{spof_style}]{snap.spof_count}[/]",
            f"[{crit_style}]{snap.critical_findings}[/]",
            f"[{warn_style}]{snap.warning_count}[/]",
            (snap.event or "")[:30],
        )

    console.print()
    console.print(table)
    console.print()


def _show_trends(tl: "ResilienceTimeline", json_output: bool) -> None:
    """Display trend analysis for multiple time periods."""

    trends = tl.get_trends()

    if json_output:
        data = {}
        for period, trend in trends.items():
            data[period] = {
                "start_score": trend.start_score,
                "end_score": trend.end_score,
                "delta": trend.delta,
                "trend": trend.trend,
                "avg_score": trend.avg_score,
                "min_score": trend.min_score,
                "max_score": trend.max_score,
                "volatility": trend.volatility,
                "snapshots_count": trend.snapshots_count,
            }
        console.print_json(data=data)
        return

    # Check if any data exists
    has_data = any(t.snapshots_count > 0 for t in trends.values())
    if not has_data:
        console.print(
            "\n[yellow]No timeline data found for trend analysis.[/]\n"
            "[dim]Run simulations to start tracking.[/]"
        )
        return

    table = Table(title="Resilience Trend Analysis", show_header=True)
    table.add_column("Period", width=8)
    table.add_column("Trend", width=22)
    table.add_column("Start", justify="right", width=8)
    table.add_column("End", justify="right", width=8)
    table.add_column("Delta", justify="right", width=8)
    table.add_column("Avg", justify="right", width=8)
    table.add_column("Min", justify="right", width=8)
    table.add_column("Max", justify="right", width=8)
    table.add_column("Volatility", justify="right", width=10)
    table.add_column("Count", justify="right", width=7)

    trend_colors = {
        "improving": "green",
        "stable": "yellow",
        "degrading": "red",
        "critical_degradation": "bold red",
    }
    trend_arrows = {
        "improving": "^ IMPROVING",
        "stable": "- STABLE",
        "degrading": "v DEGRADING",
        "critical_degradation": "v CRITICAL",
    }

    for period in ("7d", "30d", "90d"):
        trend = trends.get(period)
        if trend is None or trend.snapshots_count == 0:
            continue

        color = trend_colors.get(trend.trend, "white")
        arrow = trend_arrows.get(trend.trend, "?")

        delta_color = "green" if trend.delta >= 0 else "red"
        delta_sign = "+" if trend.delta >= 0 else ""

        table.add_row(
            period,
            f"[{color}]{arrow}[/]",
            f"{trend.start_score:.1f}",
            f"{trend.end_score:.1f}",
            f"[{delta_color}]{delta_sign}{trend.delta:.1f}[/]",
            f"{trend.avg_score:.1f}",
            f"{trend.min_score:.1f}",
            f"{trend.max_score:.1f}",
            f"{trend.volatility:.2f}",
            str(trend.snapshots_count),
        )

    console.print()
    console.print(table)
    console.print()


def _show_milestones(tl: "ResilienceTimeline", json_output: bool) -> None:
    """Display milestone events."""

    milestones = tl.get_milestones()

    if json_output:
        data = [m.to_dict() for m in milestones]
        console.print_json(data=data)
        return

    if not milestones:
        console.print(
            "\n[yellow]No milestones achieved yet.[/]\n"
            "[dim]Keep running simulations to track progress.[/]"
        )
        return

    table = Table(title="Resilience Milestones", show_header=True)
    table.add_column("Date", style="dim", width=20)
    table.add_column("Type", width=18)
    table.add_column("Description", width=45)
    table.add_column("Score", justify="right", width=8)

    type_colors = {
        "score_threshold": "green",
        "zero_critical": "cyan",
        "nines_achieved": "bold green",
        "regression": "red",
    }

    for m in milestones:
        color = type_colors.get(m.milestone_type, "white")
        table.add_row(
            m.timestamp[:19],
            f"[{color}]{m.milestone_type}[/]",
            m.description,
            f"{m.score_at_milestone:.1f}",
        )

    console.print()
    console.print(table)
    console.print()


def _export_timeline(tl: "ResilienceTimeline", output: Path | None) -> None:
    """Export timeline data to CSV."""
    if output is None:
        console.print("[red]Error: --output is required for export[/]")
        console.print("[dim]Usage: faultray timeline export --output timeline.csv[/]")
        raise typer.Exit(1)

    path = tl.export_csv(output)
    console.print(f"\n[green]Timeline exported to {path}[/]")


def _record_snapshot(
    tl: "ResilienceTimeline",
    model: Path,
    yaml_file: Path | None,
    event: str | None,
    json_output: bool,
) -> None:
    """Manually record a timeline snapshot from a model file."""
    graph = _load_graph_for_analysis(model, yaml_file)

    snapshot = tl.record(graph, event=event)

    if json_output:
        console.print_json(data=snapshot.to_dict())
        return

    score = snapshot.resilience_score
    if score >= 80:
        color = "green"
    elif score >= 60:
        color = "yellow"
    else:
        color = "red"

    console.print(
        f"\n[green]Snapshot recorded:[/] "
        f"Score=[{color}]{score:.1f}[/]  "
        f"Components={snapshot.component_count}  "
        f"SPOFs={snapshot.spof_count}"
    )
    if event:
        console.print(f"  Event: {event}")
    console.print()


def _reset_timeline(tl: "ResilienceTimeline") -> None:
    """Clear all timeline data."""
    tl.reset()
    console.print("\n[green]Timeline data has been reset.[/]\n")
