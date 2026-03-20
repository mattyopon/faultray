# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""CLI commands for Dependency Drift Detection.

Provides commands to save baselines, detect drift, and continuously
monitor infrastructure for resilience degradation.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console

if TYPE_CHECKING:
    from faultray.simulator.drift_detector import DriftDetector, DriftReport


@app.command("drift")
def drift(
    action: str = typer.Argument(
        ...,
        help="Action: baseline | detect | watch",
    ),
    file1: Path = typer.Argument(
        ...,
        help="YAML/JSON infrastructure file (for baseline) or baseline JSON file (for detect/watch)",
    ),
    file2: Path = typer.Argument(
        default=None,
        help="Current infrastructure YAML/JSON file (for detect/watch)",
    ),
    output: Path = typer.Option(
        None, "--output", "-o",
        help="Output path for baseline JSON file (baseline action)",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON (for CI/CD integration)",
    ),
    interval: int = typer.Option(
        3600, "--interval", "-i",
        help="Watch interval in seconds (watch action)",
    ),
) -> None:
    """Dependency Drift Detection — detect resilience degradation over time.

    Save a golden baseline of your infrastructure, then detect when
    configuration drifts away from the designed resilience posture.

    Examples:
        # Save current state as baseline
        faultray drift baseline infra.yaml --output baseline.json

        # Detect drift against baseline
        faultray drift detect baseline.json infra-current.yaml

        # JSON output for CI/CD
        faultray drift detect baseline.json infra-current.yaml --json

        # Continuous monitoring
        faultray drift watch baseline.json infra.yaml --interval 3600
    """
    from faultray.simulator.drift_detector import DriftDetector

    detector = DriftDetector()

    if action == "baseline":
        _do_baseline(detector, file1, output, json_output)
    elif action == "detect":
        _do_detect(detector, file1, file2, json_output)
    elif action == "watch":
        _do_watch(detector, file1, file2, interval, json_output)
    else:
        console.print(
            f"[red]Unknown action: '{action}'. "
            "Use 'baseline', 'detect', or 'watch'.[/]"
        )
        raise typer.Exit(1)


def _do_baseline(
    detector: "DriftDetector",
    yaml_file: Path,
    output: Path | None,
    json_output: bool,
) -> None:
    """Save current infrastructure state as a golden baseline."""
    graph = _load_graph_for_analysis(yaml_file, yaml_file)

    if output is None:
        output = Path("drift-baseline.json")

    baseline = detector.save_baseline(graph, output)

    if json_output:
        data = {
            "action": "baseline_saved",
            "infrastructure_id": baseline.infrastructure_id,
            "timestamp": baseline.timestamp.isoformat(),
            "resilience_score": baseline.resilience_score,
            "components": len(baseline.components),
            "edges": len(baseline.edges),
            "output_path": str(output),
        }
        console.print_json(data=data)
        return

    summary = (
        f"[bold]Infrastructure ID:[/] {baseline.infrastructure_id}\n"
        f"[bold]Timestamp:[/] {baseline.timestamp.isoformat()}\n"
        f"[bold]Resilience Score:[/] {baseline.resilience_score:.1f}\n"
        f"[bold]Components:[/] {len(baseline.components)}\n"
        f"[bold]Dependencies:[/] {len(baseline.edges)}\n"
        f"\n[bold green]Baseline saved to:[/] {output}"
    )
    console.print()
    console.print(Panel(summary, title="[bold]Drift Baseline Saved[/]", border_style="green"))


def _do_detect(
    detector: "DriftDetector",
    baseline_path: Path,
    current_path: Path | None,
    json_output: bool,
) -> None:
    """Detect drift between baseline and current infrastructure."""
    if current_path is None:
        console.print(
            "[red]Missing current infrastructure file. "
            "Usage: faultray drift detect <baseline.json> <current.yaml>[/]"
        )
        raise typer.Exit(1)

    if not baseline_path.exists():
        console.print(f"[red]Baseline file not found: {baseline_path}[/]")
        raise typer.Exit(1)
    if not current_path.exists():
        console.print(f"[red]Infrastructure file not found: {current_path}[/]")
        raise typer.Exit(1)

    report = detector.detect_from_file(baseline_path, current_path)

    if json_output:
        console.print_json(data=report.to_dict())
        if report.critical_drifts > 0:
            raise typer.Exit(1)
        return

    _print_drift_report(report)

    if report.critical_drifts > 0:
        raise typer.Exit(1)


def _do_watch(
    detector: "DriftDetector",
    baseline_path: Path,
    current_path: Path | None,
    interval: int,
    json_output: bool,
) -> None:
    """Continuously monitor for drift at a given interval."""
    if current_path is None:
        console.print(
            "[red]Missing current infrastructure file. "
            "Usage: faultray drift watch <baseline.json> <current.yaml> "
            "--interval 3600[/]"
        )
        raise typer.Exit(1)

    if not baseline_path.exists():
        console.print(f"[red]Baseline file not found: {baseline_path}[/]")
        raise typer.Exit(1)

    console.print(
        f"[bold]Watching for drift every {interval}s...[/] "
        f"(baseline: {baseline_path}, current: {current_path})"
    )
    console.print("[dim]Press Ctrl+C to stop[/]\n")

    try:
        while True:
            if not current_path.exists():
                console.print(
                    f"[yellow]Infrastructure file not found: {current_path}, "
                    f"retrying in {interval}s...[/]"
                )
                time.sleep(interval)
                continue

            report = detector.detect_from_file(baseline_path, current_path)

            if report.total_drifts > 0:
                if json_output:
                    console.print_json(data=report.to_dict())
                else:
                    _print_drift_report(report)
            else:
                console.print(
                    f"[green][{report.current_timestamp.isoformat()}] "
                    f"No drift detected. Score: "
                    f"{report.current_resilience_score:.1f}[/]"
                )

            time.sleep(interval)

    except KeyboardInterrupt:
        console.print("\n[bold]Watch stopped.[/]")


def _print_drift_report(report: "DriftReport") -> None:
    """Print a drift report using Rich formatting."""
    from faultray.simulator.drift_detector import DriftSeverity

    # Determine border color based on risk trend
    trend_colors = {
        "improving": "green",
        "stable": "green",
        "degrading": "yellow",
        "critical_degradation": "red",
    }
    border = trend_colors.get(report.risk_trend, "white")

    # Score delta formatting
    if report.score_delta > 0:
        delta_str = f"[green]+{report.score_delta:.1f}[/]"
    elif report.score_delta < 0:
        delta_str = f"[red]{report.score_delta:.1f}[/]"
    else:
        delta_str = "[dim]0.0[/]"

    # Risk trend formatting
    trend_styles = {
        "improving": "[bold green]IMPROVING[/]",
        "stable": "[bold green]STABLE[/]",
        "degrading": "[bold yellow]DEGRADING[/]",
        "critical_degradation": "[bold red]CRITICAL DEGRADATION[/]",
    }
    trend_str = trend_styles.get(report.risk_trend, report.risk_trend)

    summary = (
        f"[bold]Resilience Score:[/] "
        f"{report.baseline_resilience_score:.1f} -> "
        f"{report.current_resilience_score:.1f} ({delta_str})\n"
        f"[bold]Total Drifts:[/] {report.total_drifts}  "
        f"[red]Critical: {report.critical_drifts}[/]  "
        f"[yellow]High: {report.high_drifts}[/]\n"
        f"[bold]Drift Velocity:[/] {report.drift_velocity:.1f} drifts/day\n"
        f"[bold]Risk Trend:[/] {trend_str}\n"
        f"\n[dim]{report.summary}[/]"
    )

    console.print()
    console.print(Panel(
        summary,
        title="[bold]Drift Detection Report[/]",
        border_style=border,
    ))

    if not report.events:
        return

    # Events table
    table = Table(show_header=True, title="Drift Events")
    table.add_column("Severity", width=10, justify="center")
    table.add_column("Type", style="cyan", width=22)
    table.add_column("Component", width=18)
    table.add_column("Field", width=20)
    table.add_column("Change", width=24)
    table.add_column("Impact", width=7, justify="right")

    severity_colors = {
        DriftSeverity.CRITICAL: "bold red",
        DriftSeverity.HIGH: "red",
        DriftSeverity.MEDIUM: "yellow",
        DriftSeverity.LOW: "dim",
        DriftSeverity.INFO: "dim cyan",
    }

    for event in report.events:
        color = severity_colors.get(event.severity, "white")
        sev_str = f"[{color}]{event.severity.value.upper()}[/]"

        # Format the change
        b_val = _format_val(event.baseline_value)
        c_val = _format_val(event.current_value)
        if event.baseline_value is None:
            change = f"(new) -> {c_val}"
        elif event.current_value is None:
            change = f"{b_val} -> (removed)"
        else:
            change = f"{b_val} -> {c_val}"

        impact_str = f"{event.resilience_impact:+.1f}"
        if event.resilience_impact < 0:
            impact_str = f"[red]{impact_str}[/]"
        elif event.resilience_impact > 0:
            impact_str = f"[green]{impact_str}[/]"
        else:
            impact_str = f"[dim]{impact_str}[/]"

        table.add_row(
            sev_str,
            event.drift_type.value,
            event.component_name,
            event.field,
            change,
            impact_str,
        )

    console.print()
    console.print(table)

    # Remediation suggestions for critical/high events
    critical_high = [
        e for e in report.events
        if e.severity in (DriftSeverity.CRITICAL, DriftSeverity.HIGH)
    ]
    if critical_high:
        console.print()
        console.print("[bold]Remediation Steps:[/]")
        for i, event in enumerate(critical_high, 1):
            color = "red" if event.severity == DriftSeverity.CRITICAL else "yellow"
            console.print(
                f"  {i}. [{color}]{event.severity.value.upper()}[/] "
                f"{event.component_name}: {event.remediation}"
            )
        console.print()


def _format_val(val: object) -> str:
    """Format a value for display in the change column."""
    if val is None:
        return "None"
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, float):
        return f"{val:.1f}"
    return str(val)
