"""CLI commands for Automated Canary Analysis."""

from __future__ import annotations

import json as json_mod
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from infrasim.cli.main import app, console


@app.command("canary-compare")
def canary_compare(
    baseline: Path = typer.Argument(..., help="Path to baseline infrastructure YAML"),
    canary: Path = typer.Argument(..., help="Path to canary infrastructure YAML"),
    strict: bool = typer.Option(
        False, "--strict",
        help="Use strict thresholds (lower tolerance for degradation)",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON for CI/CD"),
) -> None:
    """Compare resilience of two infrastructure configurations.

    Detects regressions by comparing resilience metrics between a baseline
    (before) and canary (after) infrastructure state.

    Exit codes:
        0 = pass (no regression)
        1 = fail (regression detected)
        2 = marginal (minor changes, review recommended)

    Examples:
        # Compare baseline vs canary
        faultray canary-compare baseline.yaml canary.yaml

        # Strict mode for production changes
        faultray canary-compare baseline.yaml canary.yaml --strict

        # JSON output for CI/CD
        faultray canary-compare baseline.yaml canary.yaml --json
    """
    from infrasim.simulator.canary_analysis import CanaryAnalyzer, CanaryConfig

    if not baseline.exists():
        console.print(f"[red]Baseline file not found: {baseline}[/]")
        raise typer.Exit(1)
    if not canary.exists():
        console.print(f"[red]Canary file not found: {canary}[/]")
        raise typer.Exit(1)

    config = None
    if strict:
        config = CanaryConfig(
            score_threshold=2.0,
            spof_threshold=0,
            critical_threshold=0,
            blast_radius_threshold=0.05,
            marginal_zone=1.0,
        )

    analyzer = CanaryAnalyzer()
    result = analyzer.analyze(baseline, canary, config=config)

    if json_output:
        console.print_json(json_mod.dumps(result.to_dict(), indent=2))
        _exit_with_verdict(result.overall_verdict)
        return

    _print_canary_result(result, console)
    _exit_with_verdict(result.overall_verdict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _exit_with_verdict(verdict: str) -> None:
    """Raise typer.Exit with the appropriate exit code for the verdict."""
    if verdict == "fail":
        raise typer.Exit(1)
    elif verdict == "marginal":
        raise typer.Exit(2)
    # pass -> exit 0 (implicit)


def _print_canary_result(result, con: Console) -> None:
    """Print canary analysis result with Rich formatting."""
    verdict_styles = {
        "pass": ("[bold green]PASS[/]", "green"),
        "fail": ("[bold red]FAIL[/]", "red"),
        "marginal": ("[bold yellow]MARGINAL[/]", "yellow"),
    }
    verdict_text, border = verdict_styles.get(
        result.overall_verdict, ("[bold]UNKNOWN[/]", "white"),
    )

    summary = (
        f"[bold]Verdict:[/] {verdict_text}\n"
        f"[bold]Baseline:[/] {result.baseline_file}\n"
        f"[bold]Canary:[/]   {result.canary_file}\n\n"
        f"[bold]Passed:[/] {result.passed_count}  "
        f"[bold]Failed:[/] {result.failed_count}  "
        f"[bold]Marginal:[/] {result.marginal_count}"
    )

    con.print()
    con.print(Panel(
        summary,
        title="[bold]Canary Analysis Result[/]",
        border_style=border,
    ))

    # Metrics table
    table = Table(title="Metric Comparison", show_header=True)
    table.add_column("Metric", style="cyan", width=24)
    table.add_column("Baseline", justify="right", width=10)
    table.add_column("Canary", justify="right", width=10)
    table.add_column("Delta", justify="right", width=10)
    table.add_column("Delta %", justify="right", width=8)
    table.add_column("Threshold", justify="right", width=10)
    table.add_column("Verdict", justify="center", width=10)

    verdict_colors = {"pass": "green", "fail": "red", "marginal": "yellow"}

    for m in result.metrics:
        color = verdict_colors.get(m.verdict, "white")
        delta_str = f"{m.delta:+.2f}"
        pct_str = f"{m.delta_percent:+.1f}%"
        thresh_str = f"{m.threshold:.2f}" if m.threshold != float("inf") else "info"

        table.add_row(
            m.name,
            f"{m.baseline_value:.2f}",
            f"{m.canary_value:.2f}",
            delta_str,
            pct_str,
            thresh_str,
            f"[{color}]{m.verdict.upper()}[/]",
        )

    con.print()
    con.print(table)

    # Summary
    con.print()
    con.print(f"[dim]{result.summary}[/]")

    # Recommendations
    if result.recommendations:
        con.print()
        con.print("[bold]Recommendations:[/]")
        for i, rec in enumerate(result.recommendations, 1):
            con.print(f"  {i}. {rec}")
