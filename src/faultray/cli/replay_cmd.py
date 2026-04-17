# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI commands for the Incident Replay Engine."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console

replay_app = typer.Typer(
    name="replay",
    help="Replay historical cloud outages against your infrastructure.",
    no_args_is_help=True,
)
app.add_typer(replay_app, name="replay")


def _severity_color(severity: str) -> str:
    """Map severity strings to Rich color names."""
    return {
        "critical": "bold red",
        "major": "yellow",
        "minor": "green",
    }.get(severity, "white")


def _grade_color(grade: str) -> str:
    """Map resilience grades to Rich color names."""
    return {
        "A": "bold green",
        "B": "green",
        "C": "yellow",
        "D": "red",
        "F": "bold red",
    }.get(grade, "white")


def _health_color(health_str: str) -> str:
    """Map HealthStatus values to Rich color names."""
    return {
        "healthy": "green",
        "degraded": "yellow",
        "overloaded": "red",
        "down": "bold red",
    }.get(health_str, "white")


def _format_timedelta(td) -> str:
    """Format a timedelta into a human-readable string."""
    total_seconds = int(td.total_seconds())
    if total_seconds < 60:
        return f"{total_seconds}s"
    if total_seconds < 3600:
        return f"{total_seconds // 60}m"
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    if minutes == 0:
        return f"{hours}h"
    return f"{hours}h {minutes}m"


# ---------------------------------------------------------------------------
# replay list
# ---------------------------------------------------------------------------

@replay_app.command("list")
def replay_list(
    provider: str | None = typer.Option(
        None, "--provider", "-p",
        help="Filter by cloud provider (aws, azure, gcp, cloudflare, generic).",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON.",
    ),
) -> None:
    """List all available historical incidents for replay.

    Examples:
        faultray replay list
        faultray replay list --provider aws
        faultray replay list --json
    """
    from faultray.simulator.incident_replay import IncidentReplayEngine

    engine = IncidentReplayEngine()
    incidents = engine.list_incidents(provider=provider)

    if not incidents:
        console.print("[yellow]No incidents found.[/]")
        raise typer.Exit()

    if json_output:
        data = [
            {
                "id": inc.id,
                "name": inc.name,
                "provider": inc.provider,
                "date": inc.date.isoformat(),
                "duration_hours": inc.duration.total_seconds() / 3600,
                "severity": inc.severity,
                "affected_services": inc.affected_services,
                "affected_regions": inc.affected_regions,
                "root_cause": inc.root_cause,
            }
            for inc in incidents
        ]
        console.print_json(data=data)
        return

    table = Table(
        title="Historical Incidents Database",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("ID", style="cyan", width=25)
    table.add_column("Name", width=40)
    table.add_column("Provider", width=12)
    table.add_column("Date", width=12)
    table.add_column("Duration", width=10, justify="right")
    table.add_column("Severity", width=10, justify="center")
    table.add_column("Services", width=30)

    for inc in incidents:
        sev_color = _severity_color(inc.severity)
        table.add_row(
            inc.id,
            inc.name,
            inc.provider.upper(),
            inc.date.strftime("%Y-%m-%d"),
            _format_timedelta(inc.duration),
            f"[{sev_color}]{inc.severity.upper()}[/]",
            ", ".join(inc.affected_services[:4])
            + ("..." if len(inc.affected_services) > 4 else ""),
        )

    console.print()
    console.print(table)
    console.print(f"\n[dim]{len(incidents)} incidents available. "
                  f"Use 'faultray replay run <yaml> --incident <id>' to replay.[/]")


# ---------------------------------------------------------------------------
# replay run
# ---------------------------------------------------------------------------

@replay_app.command("run")
def replay_run(
    model_file: Path = typer.Argument(
        ...,
        help="Path to YAML/JSON infrastructure model file.",
    ),
    incident: str | None = typer.Option(
        None, "--incident", "-i",
        help="Incident ID to replay (e.g., aws-us-east-1-2021-12).",
    ),
    all_incidents: bool = typer.Option(
        False, "--all", "-a",
        help="Replay ALL historical incidents.",
    ),
    vulnerable: bool = typer.Option(
        False, "--vulnerable", "-V",
        help="Only replay incidents you are vulnerable to.",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON.",
    ),
) -> None:
    """Replay historical incidents against your infrastructure.

    Examples:
        faultray replay run infra.yaml --incident aws-us-east-1-2021-12
        faultray replay run infra.yaml --all
        faultray replay run infra.yaml --vulnerable
        faultray replay run infra.yaml --incident crowdstrike-2024-07 --json
    """
    from faultray.simulator.incident_replay import IncidentReplayEngine

    graph = _load_graph_for_analysis(model_file, None)
    engine = IncidentReplayEngine()

    if incident:
        # Single incident replay
        try:
            inc = engine.get_incident(incident)
        except KeyError as e:
            console.print(f"[red]{e}[/]")
            raise typer.Exit(1)

        if not json_output:
            console.print(f"\n[cyan]Replaying: {inc.name}...[/]")

        result = engine.replay(graph, inc)

        if json_output:
            console.print_json(data=_result_to_dict(result))
        else:
            _print_replay_result(result, console)

    elif all_incidents:
        # Replay all incidents
        incidents = engine.list_incidents()
        if not json_output:
            console.print(f"\n[cyan]Replaying {len(incidents)} incidents...[/]")

        results = []
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Replaying...", total=len(incidents))
            for inc in incidents:
                progress.update(task, description=f"Replaying: {inc.name[:50]}...")
                result = engine.replay(graph, inc)
                results.append(result)
                progress.advance(task)

        if json_output:
            console.print_json(data=[_result_to_dict(r) for r in results])
        else:
            _print_summary_table(results, console)

    elif vulnerable:
        # Only replay incidents the infra is vulnerable to
        if not json_output:
            console.print("\n[cyan]Scanning for vulnerable incidents...[/]")

        vuln_incidents = engine.find_vulnerable_incidents(graph)
        if not vuln_incidents:
            console.print("[green]No vulnerabilities found! Your infrastructure "
                          "appears resilient to all known incidents.[/]")
            raise typer.Exit()

        if not json_output:
            console.print(f"[yellow]Found {len(vuln_incidents)} incidents "
                          f"you may be vulnerable to. Replaying...[/]")

        results = []
        for inc, score in vuln_incidents:
            result = engine.replay(graph, inc)
            results.append(result)

        if json_output:
            console.print_json(data=[_result_to_dict(r) for r in results])
        else:
            _print_summary_table(results, console)

    else:
        console.print("[red]Specify --incident <id>, --all, or --vulnerable[/]")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# replay report
# ---------------------------------------------------------------------------

@replay_app.command("report")
def replay_report(
    model_file: Path = typer.Argument(
        ...,
        help="Path to YAML/JSON infrastructure model file.",
    ),
    output: Path = typer.Option(
        Path("incident-replay-report.html"), "--output", "-o",
        help="Output path for the HTML report.",
    ),
) -> None:
    """Generate an HTML report of all incident replays.

    Examples:
        faultray replay report infra.yaml
        faultray replay report infra.yaml --output my-report.html
    """
    from faultray.simulator.incident_replay import IncidentReplayEngine

    graph = _load_graph_for_analysis(model_file, None)
    engine = IncidentReplayEngine()
    incidents = engine.list_incidents()

    console.print(f"\n[cyan]Replaying {len(incidents)} incidents for report...[/]")

    results = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Replaying...", total=len(incidents))
        for inc in incidents:
            progress.update(task, description=f"Replaying: {inc.name[:50]}...")
            result = engine.replay(graph, inc)
            results.append(result)
            progress.advance(task)

    html = _generate_html_report(results, graph)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    console.print(f"\n[green]HTML report saved to {output}[/]")


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _result_to_dict(result) -> dict:
    """Convert a ReplayResult to a JSON-serializable dict."""
    return {
        "incident_id": result.incident.id,
        "incident_name": result.incident.name,
        "survived": result.survived,
        "impact_score": result.impact_score,
        "resilience_grade": result.resilience_grade_during_incident,
        "downtime_estimate_minutes": result.downtime_estimate.total_seconds() / 60,
        "revenue_impact_estimate": result.revenue_impact_estimate,
        "affected_components": [
            {
                "id": ac.component_id,
                "name": ac.component_name,
                "impact_type": ac.impact_type,
                "health": ac.health_during_incident.value,
                "recovery_time_minutes": (
                    ac.recovery_time.total_seconds() / 60
                    if ac.recovery_time else None
                ),
                "reason": ac.reason,
            }
            for ac in result.affected_components
        ],
        "survival_factors": result.survival_factors,
        "vulnerability_factors": result.vulnerability_factors,
        "recommendations": result.recommendations,
    }


def _print_replay_result(result, con: Console) -> None:
    """Print a single replay result with Rich formatting."""
    inc = result.incident
    grade_c = _grade_color(result.resilience_grade_during_incident)
    verdict = "[green]SURVIVED[/]" if result.survived else "[bold red]WOULD HAVE FAILED[/]"

    # Summary panel
    summary = (
        f"[bold]Incident:[/] {inc.name}\n"
        f"[bold]Provider:[/] {inc.provider.upper()}  "
        f"[bold]Date:[/] {inc.date.strftime('%Y-%m-%d')}  "
        f"[bold]Duration:[/] {_format_timedelta(inc.duration)}\n"
        f"[bold]Root Cause:[/] {inc.root_cause[:120]}...\n\n"
        f"[bold]Verdict:[/] {verdict}\n"
        f"[bold]Impact Score:[/] {result.impact_score}/10  "
        f"[bold]Grade:[/] [{grade_c}]{result.resilience_grade_during_incident}[/]\n"
        f"[bold]Estimated Downtime:[/] {_format_timedelta(result.downtime_estimate)}"
    )
    if result.revenue_impact_estimate is not None:
        summary += f"  [bold]Revenue Impact:[/] ${result.revenue_impact_estimate:,.0f}"

    border = "green" if result.survived else "red"
    con.print()
    con.print(Panel(summary, title="[bold]Incident Replay Result[/]", border_style=border))

    # Affected components table
    if result.affected_components:
        comp_table = Table(
            title="Affected Components",
            show_header=True,
            header_style="bold",
        )
        comp_table.add_column("Component", style="cyan", width=20)
        comp_table.add_column("Impact", width=10, justify="center")
        comp_table.add_column("Health", width=10, justify="center")
        comp_table.add_column("Recovery", width=10, justify="right")
        comp_table.add_column("Reason", width=50)

        for ac in result.affected_components:
            h_color = _health_color(ac.health_during_incident.value)
            recovery_str = (
                _format_timedelta(ac.recovery_time) if ac.recovery_time else "-"
            )
            comp_table.add_row(
                ac.component_name,
                ac.impact_type,
                f"[{h_color}]{ac.health_during_incident.value.upper()}[/]",
                recovery_str,
                ac.reason[:80],
            )

        con.print()
        con.print(comp_table)

    # Survival factors
    if result.survival_factors:
        con.print("\n[bold green]Survival Factors:[/]")
        for sf in result.survival_factors:
            con.print(f"  [green]+[/] {sf}")

    # Vulnerability factors
    if result.vulnerability_factors:
        con.print("\n[bold red]Vulnerability Factors:[/]")
        for vf in result.vulnerability_factors:
            con.print(f"  [red]-[/] {vf}")

    # Recommendations
    if result.recommendations:
        con.print("\n[bold cyan]Recommendations:[/]")
        for i, rec in enumerate(result.recommendations, 1):
            con.print(f"  {i}. {rec}")


def _print_summary_table(results: list, con: Console) -> None:
    """Print a summary table of all replay results."""
    survived_count = sum(1 for r in results if r.survived)
    failed_count = len(results) - survived_count
    avg_score = sum(r.impact_score for r in results) / len(results) if results else 0

    # Overall summary
    overall = (
        f"[bold]Total Incidents Replayed:[/] {len(results)}\n"
        f"[bold]Survived:[/] [green]{survived_count}[/]  "
        f"[bold]Failed:[/] [red]{failed_count}[/]\n"
        f"[bold]Average Impact Score:[/] {avg_score:.1f}/10"
    )
    border = "green" if failed_count == 0 else ("yellow" if survived_count > failed_count else "red")
    con.print()
    con.print(Panel(overall, title="[bold]Incident Replay Summary[/]", border_style=border))

    # Results table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Incident", style="cyan", width=40)
    table.add_column("Verdict", width=12, justify="center")
    table.add_column("Score", width=8, justify="right")
    table.add_column("Grade", width=6, justify="center")
    table.add_column("Downtime", width=10, justify="right")
    table.add_column("Affected", width=10, justify="right")

    for r in sorted(results, key=lambda x: x.impact_score, reverse=True):
        verdict = "[green]SURVIVED[/]" if r.survived else "[red]FAILED[/]"
        grade_c = _grade_color(r.resilience_grade_during_incident)
        affected_count = sum(
            1 for ac in r.affected_components
            if ac.health_during_incident.value in ("down", "degraded", "overloaded")
        )
        table.add_row(
            r.incident.name[:40],
            verdict,
            f"{r.impact_score:.1f}",
            f"[{grade_c}]{r.resilience_grade_during_incident}[/]",
            _format_timedelta(r.downtime_estimate),
            str(affected_count),
        )

    con.print()
    con.print(table)

    # Top recommendations (from the worst incidents)
    worst = sorted(results, key=lambda x: x.impact_score, reverse=True)[:3]
    all_recs: list[str] = []
    for r in worst:
        all_recs.extend(r.recommendations[:2])
    unique_recs = list(dict.fromkeys(all_recs))[:5]

    if unique_recs:
        con.print("\n[bold cyan]Top Recommendations:[/]")
        for i, rec in enumerate(unique_recs, 1):
            con.print(f"  {i}. {rec}")


def _generate_html_report(results: list, graph) -> str:
    """Generate a simple HTML report for incident replay results."""
    survived = sum(1 for r in results if r.survived)
    failed = len(results) - survived
    avg_score = sum(r.impact_score for r in results) / len(results) if results else 0

    rows = ""
    for r in sorted(results, key=lambda x: x.impact_score, reverse=True):
        verdict_class = "survived" if r.survived else "failed"
        verdict_text = "SURVIVED" if r.survived else "FAILED"
        affected_count = sum(
            1 for ac in r.affected_components
            if ac.health_during_incident.value in ("down", "degraded", "overloaded")
        )
        rows += f"""
        <tr class="{verdict_class}">
            <td>{r.incident.name}</td>
            <td>{r.incident.provider.upper()}</td>
            <td class="verdict-{verdict_class}">{verdict_text}</td>
            <td>{r.impact_score:.1f}</td>
            <td>{r.resilience_grade_during_incident}</td>
            <td>{_format_timedelta(r.downtime_estimate)}</td>
            <td>{affected_count}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FaultRay Incident Replay Report</title>
    <style>
        body {{ font-family: -apple-system, system-ui, sans-serif; margin: 2rem; background: #0d1117; color: #c9d1d9; }}
        h1 {{ color: #58a6ff; }}
        .summary {{ display: flex; gap: 2rem; margin: 1.5rem 0; }}
        .card {{ background: #161b22; padding: 1.5rem; border-radius: 8px; border: 1px solid #30363d; min-width: 150px; }}
        .card h3 {{ margin: 0 0 0.5rem 0; color: #8b949e; font-size: 0.9rem; }}
        .card .value {{ font-size: 2rem; font-weight: bold; }}
        .survived .value {{ color: #3fb950; }}
        .failed .value {{ color: #f85149; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 1.5rem; }}
        th {{ background: #161b22; color: #58a6ff; padding: 12px; text-align: left; border-bottom: 2px solid #30363d; }}
        td {{ padding: 10px 12px; border-bottom: 1px solid #21262d; }}
        tr:hover {{ background: #161b22; }}
        .verdict-survived {{ color: #3fb950; font-weight: bold; }}
        .verdict-failed {{ color: #f85149; font-weight: bold; }}
        footer {{ margin-top: 2rem; color: #8b949e; font-size: 0.85rem; }}
    </style>
</head>
<body>
    <h1>FaultRay Incident Replay Report</h1>
    <p>Replayed {len(results)} historical cloud outages against your infrastructure
       ({len(graph.components)} components).</p>

    <div class="summary">
        <div class="card survived">
            <h3>Survived</h3>
            <div class="value">{survived}</div>
        </div>
        <div class="card failed">
            <h3>Failed</h3>
            <div class="value">{failed}</div>
        </div>
        <div class="card">
            <h3>Avg Impact Score</h3>
            <div class="value" style="color: {'#3fb950' if avg_score < 3 else '#f0883e' if avg_score < 6 else '#f85149'}">{avg_score:.1f}</div>
        </div>
        <div class="card">
            <h3>Incidents Tested</h3>
            <div class="value" style="color: #58a6ff">{len(results)}</div>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th>Incident</th>
                <th>Provider</th>
                <th>Verdict</th>
                <th>Impact</th>
                <th>Grade</th>
                <th>Downtime</th>
                <th>Affected</th>
            </tr>
        </thead>
        <tbody>{rows}
        </tbody>
    </table>

    <footer>Generated by FaultRay Incident Replay Engine</footer>
</body>
</html>"""
