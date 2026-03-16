"""CLI command for diffing two simulation result files."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import app, console


@app.command(name="diff")
def diff_command(
    before: Path = typer.Argument(..., help="Path to the 'before' results JSON file"),
    after: Path = typer.Argument(..., help="Path to the 'after' results JSON file"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON summary"),
) -> None:
    """Compare two simulation result files and show differences.

    Examples:
        # Compare two result files
        faultray diff before.json after.json

        # JSON output for CI/CD
        faultray diff before.json after.json --json
    """
    if not before.exists():
        console.print(f"[red]File not found: {before}[/]")
        raise typer.Exit(1)
    if not after.exists():
        console.print(f"[red]File not found: {after}[/]")
        raise typer.Exit(1)

    from faultray.differ import SimulationDiffer

    differ = SimulationDiffer()
    result = differ.diff_files(before, after)

    if json_output:

        data = {
            "score_before": result.score_before,
            "score_after": result.score_after,
            "score_delta": result.score_delta,
            "new_critical": result.new_critical,
            "resolved_critical": result.resolved_critical,
            "new_warnings": result.new_warnings,
            "resolved_warnings": result.resolved_warnings,
            "component_changes": result.component_changes,
            "regression_detected": result.regression_detected,
        }
        console.print_json(data=data)
        return

    # Rich output
    border = "red" if result.regression_detected else "green"
    status = (
        "[bold red]REGRESSION DETECTED[/]"
        if result.regression_detected
        else "[bold green]No regression[/]"
    )

    # Format score delta
    if result.score_delta > 0:
        delta_str = f"[green]+{result.score_delta:.1f}[/]"
    elif result.score_delta < 0:
        delta_str = f"[red]{result.score_delta:.1f}[/]"
    else:
        delta_str = "[dim]0.0[/]"

    summary = (
        f"[bold]Resilience Score:[/] {result.score_before:.1f} -> {result.score_after:.1f} ({delta_str})\n"
        f"\n{status}"
    )

    console.print()
    console.print(Panel(summary, title="[bold]Simulation Diff[/]", border_style=border))

    # Details table
    table = Table(show_header=True, title="Changes")
    table.add_column("Category", style="cyan")
    table.add_column("Details")

    if result.new_critical:
        table.add_row(
            "[red]New Critical[/]",
            ", ".join(result.new_critical),
        )
    if result.resolved_critical:
        table.add_row(
            "[green]Resolved Critical[/]",
            ", ".join(result.resolved_critical),
        )
    if result.new_warnings:
        table.add_row(
            "[yellow]New Warnings[/]",
            ", ".join(result.new_warnings),
        )
    if result.resolved_warnings:
        table.add_row(
            "[green]Resolved Warnings[/]",
            ", ".join(result.resolved_warnings),
        )
    if result.component_changes:
        table.add_row(
            "Component Changes",
            ", ".join(result.component_changes),
        )

    if table.row_count > 0:
        console.print()
        console.print(table)

    if result.regression_detected:
        raise typer.Exit(1)
