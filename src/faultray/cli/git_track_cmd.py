# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI command for Architecture Git Diff Tracking.

Usage:
    faultray git-track model.yaml --commits 20
    faultray git-track model.yaml --find-regression
    faultray git-track model.yaml --json
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import app, console


@app.command(name="git-track")
def git_track(
    model_file: str = typer.Argument(
        "faultray-model.yaml",
        help="Path to the infrastructure model file (relative to repo root)",
    ),
    commits: int = typer.Option(20, "--commits", "-n", help="Number of commits to analyze"),
    find_regression: bool = typer.Option(
        False, "--find-regression", help="Find the commit that caused the biggest score drop"
    ),
    repo: Path = typer.Option(".", "--repo", "-r", help="Git repository path"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Track infrastructure architecture changes across git history.

    \b
    Analyzes how the infrastructure model file changes across commits,
    computing resilience score deltas and identifying regressions.

    \b
    Examples:
        faultray git-track faultray-model.yaml
        faultray git-track faultray-model.yaml --commits 50
        faultray git-track faultray-model.yaml --find-regression
        faultray git-track model.json --repo /path/to/repo --json
    """
    from faultray.integrations.git_tracker import GitArchitectureTracker

    try:
        tracker = GitArchitectureTracker(repo_path=repo, model_file=model_file)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)

    if find_regression:
        regression = tracker.find_regression_commit()
        if regression is None:
            if json_output:
                console.print_json(data={"regression_found": False})
            else:
                console.print("[green]No regressions found in recent history.[/]")
            return

        if json_output:
            console.print_json(data={
                "regression_found": True,
                "commit": regression.commit_hash,
                "date": regression.commit_date,
                "message": regression.commit_message,
                "score_before": regression.score_before,
                "score_after": regression.score_after,
                "score_delta": regression.score_delta,
                "components_added": regression.components_added,
                "components_removed": regression.components_removed,
            })
            return

        console.print()
        console.print(Panel(
            f"[bold]Commit:[/] {regression.commit_hash[:12]}\n"
            f"[bold]Date:[/] {regression.commit_date}\n"
            f"[bold]Message:[/] {regression.commit_message}\n\n"
            f"[bold]Score:[/] {regression.score_before:.1f} -> "
            f"[red]{regression.score_after:.1f}[/] "
            f"([red]{regression.score_delta:+.1f}[/])\n"
            f"[bold]Components Added:[/] {', '.join(regression.components_added) or 'none'}\n"
            f"[bold]Components Removed:[/] {', '.join(regression.components_removed) or 'none'}",
            title="[bold red]Regression Found[/]",
            border_style="red",
        ))
        console.print()
        return

    # Track full history
    changes = tracker.track_history(commits=commits)

    if not changes:
        if json_output:
            console.print_json(data={"changes": [], "total": 0})
        else:
            console.print(
                f"[yellow]No commits found that modify '{model_file}'.[/]"
            )
        return

    if json_output:
        output = {
            "total": len(changes),
            "changes": [
                {
                    "commit": c.commit_hash,
                    "date": c.commit_date,
                    "message": c.commit_message,
                    "score_before": c.score_before,
                    "score_after": c.score_after,
                    "score_delta": c.score_delta,
                    "regression": c.regression,
                    "components_added": c.components_added,
                    "components_removed": c.components_removed,
                    "dependencies_added": c.dependencies_added,
                    "dependencies_removed": c.dependencies_removed,
                    "component_count": c.component_count,
                    "dependency_count": c.dependency_count,
                }
                for c in changes
            ],
        }
        console.print_json(data=output)
        return

    # Display history
    regressions = sum(1 for c in changes if c.regression)
    latest = changes[0] if changes else None
    current_score = latest.score_after if latest else 0

    summary = (
        f"[bold]Model File:[/] {model_file}\n"
        f"[bold]Commits Analyzed:[/] {len(changes)}\n"
        f"[bold]Current Score:[/] {current_score:.1f}/100\n"
        f"[bold]Regressions:[/] {'[red]' + str(regressions) + '[/]' if regressions > 0 else '[green]0[/]'}"
    )

    console.print()
    console.print(Panel(
        summary,
        title="[bold cyan]Architecture Change History[/]",
        border_style="cyan",
    ))

    # Change history table
    table = Table(title="Change History", show_header=True)
    table.add_column("Commit", width=12)
    table.add_column("Date", width=20)
    table.add_column("Message", width=30)
    table.add_column("Score", width=12, justify="right")
    table.add_column("Delta", width=8, justify="right")
    table.add_column("Components", width=14)
    table.add_column("Deps", width=10)

    for c in changes:
        delta_str = f"{c.score_delta:+.1f}"
        if c.regression:
            delta_color = "red"
        elif c.score_delta > 0:
            delta_color = "green"
        else:
            delta_color = "dim"

        comp_changes = []
        if c.components_added:
            comp_changes.append(f"+{len(c.components_added)}")
        if c.components_removed:
            comp_changes.append(f"-{len(c.components_removed)}")
        comp_str = ", ".join(comp_changes) if comp_changes else "-"

        dep_changes = []
        if c.dependencies_added:
            dep_changes.append(f"+{c.dependencies_added}")
        if c.dependencies_removed:
            dep_changes.append(f"-{c.dependencies_removed}")
        dep_str = ", ".join(dep_changes) if dep_changes else "-"

        table.add_row(
            c.commit_hash[:12],
            c.commit_date[:19] if c.commit_date else "",
            (c.commit_message[:28] + "..." if len(c.commit_message) > 28 else c.commit_message),
            f"{c.score_after:.1f}",
            f"[{delta_color}]{delta_str}[/]",
            comp_str,
            dep_str,
        )

    console.print()
    console.print(table)
    console.print()
