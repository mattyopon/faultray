"""CLI commands for Continuous Compliance Monitor."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel

from faultray.cli.main import app, console


@app.command("compliance-monitor")
def compliance_monitor(
    yaml_file: Path = typer.Argument(
        ...,
        help="Path to infrastructure YAML model.",
    ),
    framework: str = typer.Option(
        "all", "--framework", "-f",
        help="Compliance framework: soc2, iso27001, pci_dss, nist_csf, dora, hipaa, or 'all'.",
    ),
    snapshot: bool = typer.Option(
        False, "--snapshot",
        help="Take a compliance snapshot and store it.",
    ),
    trend: bool = typer.Option(
        False, "--trend",
        help="Show compliance trend over time.",
    ),
    days: int = typer.Option(
        90, "--days",
        help="Number of days for trend analysis.",
    ),
    store: Path = typer.Option(
        None, "--store",
        help="Path to SQLite store for persistent history (default: compliance_history.db).",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON.",
    ),
) -> None:
    """Continuous compliance monitoring with snapshot tracking and trend analysis.

    Examples:
        faultray compliance-monitor infra.yaml --framework soc2 --snapshot
        faultray compliance-monitor infra.yaml --trend --days 90
        faultray compliance-monitor infra.yaml --framework dora --snapshot --store compliance.db
    """
    from faultray.model.loader import load_yaml
    from faultray.simulator.compliance_monitor import (
        ComplianceFramework,
        ComplianceMonitor,
    )

    if not yaml_file.exists():
        console.print(f"[red]File not found: {yaml_file}[/]")
        raise typer.Exit(1)

    graph = load_yaml(yaml_file)
    store_path = store or Path("compliance_history.db")
    monitor = ComplianceMonitor(store_path=store_path)

    # Resolve frameworks
    if framework == "all":
        frameworks = list(ComplianceFramework)
    else:
        try:
            frameworks = [ComplianceFramework(framework)]
        except ValueError:
            console.print(
                f"[red]Unknown framework: '{framework}'[/]\n"
                f"[dim]Valid: soc2, iso27001, pci_dss, nist_csf, dora, hipaa, all[/]"
            )
            raise typer.Exit(1)

    if snapshot:
        monitor.track(graph)
        if not json_output:
            console.print(f"[green]Compliance snapshot recorded to {store_path}[/]")

        for fw in frameworks:
            snap = monitor.assess(graph, fw)
            if json_output:
                data = {
                    "framework": fw.value,
                    "timestamp": snap.timestamp.isoformat(),
                    "compliance_percentage": snap.compliance_percentage,
                    "total_controls": snap.total_controls,
                    "compliant": snap.compliant,
                    "partial": snap.partial,
                    "non_compliant": snap.non_compliant,
                }
                console.print_json(data=data)
            else:
                _print_snapshot(snap)

    elif trend:
        for fw in frameworks:
            t = monitor.get_trends(fw)
            if json_output:
                data = {
                    "framework": fw.value,
                    "trend": t.trend,
                    "current_percentage": t.current_percentage,
                    "delta_30d": t.delta_30d,
                    "snapshot_count": len(t.snapshots),
                    "risk_areas": t.risk_areas,
                }
                console.print_json(data=data)
            else:
                _print_trend(t, fw)

    else:
        # Default: assess and show results
        for fw in frameworks:
            snap = monitor.assess(graph, fw)
            if json_output:
                data = {
                    "framework": fw.value,
                    "compliance_percentage": snap.compliance_percentage,
                    "total_controls": snap.total_controls,
                    "compliant": snap.compliant,
                    "partial": snap.partial,
                    "non_compliant": snap.non_compliant,
                }
                console.print_json(data=data)
            else:
                _print_snapshot(snap)


def _print_snapshot(snap) -> None:
    """Print a compliance snapshot in Rich format."""
    pct = snap.compliance_percentage
    color = "green" if pct >= 80 else "yellow" if pct >= 50 else "red"

    overview = (
        f"[bold]Framework:[/] {snap.framework.value.upper()}\n"
        f"[bold]Compliance:[/] [{color}]{pct:.1f}%[/]\n"
        f"[bold]Controls:[/] {snap.total_controls} total | "
        f"[green]{snap.compliant} pass[/] | "
        f"[yellow]{snap.partial} partial[/] | "
        f"[red]{snap.non_compliant} fail[/]"
    )
    console.print()
    console.print(Panel(overview, title=f"[bold]{snap.framework.value.upper()} Compliance[/]", border_style=color))


def _print_trend(t, fw) -> None:
    """Print a compliance trend in Rich format."""
    trend_color = {"improving": "green", "stable": "yellow", "degrading": "red"}.get(t.trend, "white")

    overview = (
        f"[bold]Framework:[/] {fw.value.upper()}\n"
        f"[bold]Trend:[/] [{trend_color}]{t.trend.upper()}[/]\n"
        f"[bold]Current:[/] {t.current_percentage:.1f}%\n"
        f"[bold]30-day Delta:[/] {t.delta_30d:+.1f}%\n"
        f"[bold]Snapshots:[/] {len(t.snapshots)}"
    )
    console.print()
    console.print(Panel(overview, title=f"[bold]{fw.value.upper()} Trend[/]", border_style=trend_color))

    if t.risk_areas:
        console.print("[bold]Risk Areas:[/]")
        for r in t.risk_areas:
            console.print(f"  [red]- {r}[/]")
    console.print()
