"""CLI command for Statistical Anomaly Detection."""

from __future__ import annotations

import json as json_mod
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import app, console


@app.command()
def anomaly(
    yaml_file: Path = typer.Argument(..., help="Infrastructure YAML file"),
    anomaly_type: str = typer.Option(
        None, "--type", "-t", help="Filter by anomaly type (e.g. replica_outlier, utilization_outlier)"
    ),
    severity: str = typer.Option(
        None, "--severity", "-s", help="Filter by severity (critical, warning, info)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Statistical anomaly detection - find unusual infrastructure patterns.

    Analyzes infrastructure configurations to detect statistical outliers
    and anti-patterns using z-score and IQR methods.

    Examples:
        # Full anomaly report
        faultray anomaly infra.yaml

        # Filter by type
        faultray anomaly infra.yaml --type replica_outlier

        # Filter by severity
        faultray anomaly infra.yaml --severity critical

        # JSON output
        faultray anomaly infra.yaml --json
    """
    from faultray.model.loader import load_yaml
    from faultray.simulator.anomaly_detector import AnomalyDetector, AnomalyType

    if not yaml_file.exists():
        console.print(f"[red]File not found: {yaml_file}[/]")
        raise typer.Exit(1)

    console.print(f"[cyan]Loading infrastructure from {yaml_file}...[/]")
    try:
        graph = load_yaml(yaml_file)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)

    console.print(
        f"[cyan]Running anomaly detection ({len(graph.components)} components)...[/]"
    )

    detector = AnomalyDetector()
    report = detector.detect(graph)

    # Apply filters
    filtered_anomalies = report.anomalies

    if anomaly_type:
        try:
            target_type = AnomalyType(anomaly_type)
            filtered_anomalies = [
                a for a in filtered_anomalies if a.anomaly_type == target_type
            ]
        except ValueError:
            valid_types = [t.value for t in AnomalyType]
            console.print(f"[red]Unknown anomaly type: {anomaly_type}[/]")
            console.print(f"[dim]Valid types: {', '.join(valid_types)}[/]")
            raise typer.Exit(1)

    if severity:
        if severity not in ("critical", "warning", "info"):
            console.print(f"[red]Unknown severity: {severity}. Use critical, warning, or info.[/]")
            raise typer.Exit(1)
        filtered_anomalies = [
            a for a in filtered_anomalies if a.severity == severity
        ]

    if json_output:
        data = {
            "total_components_analyzed": report.total_components_analyzed,
            "anomaly_rate": report.anomaly_rate,
            "critical_count": report.critical_count,
            "warning_count": report.warning_count,
            "healthiest_components": report.healthiest_components,
            "most_anomalous_components": report.most_anomalous_components,
            "anomalies": [
                {
                    "type": a.anomaly_type.value,
                    "component_id": a.component_id,
                    "component_name": a.component_name,
                    "severity": a.severity,
                    "description": a.description,
                    "expected_value": a.expected_value,
                    "actual_value": a.actual_value,
                    "z_score": a.z_score,
                    "recommendation": a.recommendation,
                    "confidence": a.confidence,
                }
                for a in filtered_anomalies
            ],
        }
        console.print_json(json_mod.dumps(data, indent=2, default=str))
        return

    _print_anomaly_report(report, filtered_anomalies, console)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _severity_color(severity: str) -> str:
    """Get Rich color for severity level."""
    if severity == "critical":
        return "bold red"
    elif severity == "warning":
        return "yellow"
    return "dim"


def _print_anomaly_report(report, anomalies: list, con: Console) -> None:
    """Print the full anomaly report with Rich formatting."""
    # Summary
    total = report.total_components_analyzed
    rate_color = "green" if report.anomaly_rate < 20 else "yellow"
    if report.anomaly_rate > 50:
        rate_color = "red"

    summary = (
        f"[bold]Components Analyzed:[/] {total}\n"
        f"[bold]Anomaly Rate:[/] [{rate_color}]{report.anomaly_rate:.1f}%[/]\n"
        f"[bold]Critical:[/] [red]{report.critical_count}[/]  |  "
        f"[bold]Warning:[/] [yellow]{report.warning_count}[/]  |  "
        f"[bold]Info:[/] {len(anomalies) - report.critical_count - report.warning_count}"
    )

    if report.healthiest_components:
        summary += f"\n[bold]Healthiest:[/] {', '.join(report.healthiest_components[:3])}"
    if report.most_anomalous_components:
        summary += f"\n[bold]Most Issues:[/] {', '.join(report.most_anomalous_components[:3])}"

    con.print()
    con.print(Panel(summary, title="[bold]Anomaly Detection Summary[/]", border_style="cyan"))

    if not anomalies:
        con.print("\n[green]No anomalies detected. Infrastructure looks healthy![/]")
        return

    # Anomalies table
    table = Table(
        title="Detected Anomalies",
        show_header=True,
        header_style="bold",
    )
    table.add_column("#", width=3, justify="right")
    table.add_column("Severity", width=10)
    table.add_column("Type", width=22)
    table.add_column("Component", width=18, style="cyan")
    table.add_column("Description", width=50)
    table.add_column("Z-Score", width=8, justify="right")

    for i, a in enumerate(anomalies, 1):
        sev_color = _severity_color(a.severity)
        z_str = f"{a.z_score:.2f}" if a.z_score is not None else "-"

        table.add_row(
            str(i),
            f"[{sev_color}]{a.severity.upper()}[/]",
            a.anomaly_type.value,
            a.component_name,
            a.description[:80] + ("..." if len(a.description) > 80 else ""),
            z_str,
        )

    con.print()
    con.print(table)

    # Detailed findings for critical anomalies
    critical = [a for a in anomalies if a.severity == "critical"]
    if critical:
        con.print()
        con.print("[bold red]Critical Findings:[/]")
        for a in critical:
            con.print(f"\n  [bold red]{a.component_name}[/] ({a.anomaly_type.value})")
            con.print(f"  {a.description}")
            con.print(f"  [dim]Expected: {a.expected_value} | Actual: {a.actual_value}[/]")
            if a.recommendation:
                con.print(f"  [green]Recommendation: {a.recommendation}[/]")
