# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI command for historical trend tracking."""

from __future__ import annotations

from pathlib import Path

import typer

from faultray.cli.main import app, console


@app.command(name="history")
def history(
    days: int = typer.Option(90, "--days", "-d", help="Number of days to show"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    db_path: Path | None = typer.Option(None, "--db", help="Path to history database"),
) -> None:
    """Show resilience score trend over time.

    Examples:
        # Show 90-day trend (default)
        faultray history

        # Show 30-day trend
        faultray history --days 30

        # Export as JSON
        faultray history --json

        # Use custom database path
        faultray history --db ./my-history.db
    """
    from rich.panel import Panel
    from rich.table import Table

    from faultray.history import HistoryTracker

    tracker = HistoryTracker(db_path=db_path)

    if json_output:
        console.print(tracker.to_json(days=days))
        return

    trend = tracker.analyze_trend(days=days)

    if not trend.entries:
        console.print(
            "\n[yellow]No history data found.[/]\n"
            "[dim]Run 'faultray evaluate' or 'faultray simulate' to start tracking.[/]"
        )
        return

    # Trend summary
    trend_colors = {
        "improving": "green",
        "stable": "yellow",
        "degrading": "red",
    }
    trend_arrows = {
        "improving": "^",
        "stable": "-",
        "degrading": "v",
    }
    color = trend_colors.get(trend.score_trend, "white")
    arrow = trend_arrows.get(trend.score_trend, "?")

    latest = trend.entries[-1]

    summary = (
        f"[bold]Trend:[/] [{color}]{trend.score_trend.upper()} {arrow}[/]\n"
        f"[bold]Current Score:[/] {latest.resilience_score:.0f}/100\n"
        f"[bold]30-Day Change:[/] [{color}]{trend.score_change_30d:+.1f}[/]\n"
        f"[bold]Best:[/] {trend.best_score:.0f}  |  "
        f"[bold]Worst:[/] {trend.worst_score:.0f}\n"
        f"[bold]Regressions:[/] {len(trend.regression_dates)}"
    )

    console.print()
    console.print(Panel(
        summary,
        title=f"[bold]FaultRay Score Trend ({days} days)[/]",
        border_style=color,
    ))

    # History table
    table = Table(
        title=f"Score History ({len(trend.entries)} entries)",
        show_header=True,
    )
    table.add_column("Date", style="dim", width=20)
    table.add_column("Score", justify="right", width=8)
    table.add_column("v2", justify="right", width=8)
    table.add_column("Critical", justify="right", width=10)
    table.add_column("Warning", justify="right", width=10)
    table.add_column("Components", justify="right", width=12)

    # Show last 20 entries to keep output manageable
    display_entries = trend.entries[-20:]
    if len(trend.entries) > 20:
        console.print(
            f"\n[dim]Showing last 20 of {len(trend.entries)} entries[/]"
        )

    for entry in display_entries:
        s = entry.resilience_score
        if s >= 80:
            s_color = "green"
        elif s >= 60:
            s_color = "yellow"
        else:
            s_color = "red"

        crit_style = "red" if entry.critical_count > 0 else "dim"
        warn_style = "yellow" if entry.warning_count > 0 else "dim"

        table.add_row(
            entry.timestamp[:19],
            f"[{s_color}]{s:.0f}[/]",
            f"{entry.resilience_score_v2:.0f}",
            f"[{crit_style}]{entry.critical_count}[/]",
            f"[{warn_style}]{entry.warning_count}[/]",
            str(entry.component_count),
        )

    console.print()
    console.print(table)

    # Recommendation
    if trend.recommendation:
        console.print(f"\n[bold]Recommendation:[/] {trend.recommendation}")

    console.print()
