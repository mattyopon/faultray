"""CLI commands for the Chaos Calendar feature."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import app, console

calendar_app = typer.Typer(
    name="calendar",
    help="Chaos Calendar — Schedule experiments with learning from results",
    no_args_is_help=True,
)
app.add_typer(calendar_app, name="calendar")


def _load_graph(yaml_file: Path) -> "InfraGraph":  # noqa: F821
    """Load an InfraGraph from a YAML or JSON file."""
    if not yaml_file.exists():
        console.print(f"[red]File not found: {yaml_file}[/]")
        raise typer.Exit(1)

    try:
        if str(yaml_file).endswith((".yaml", ".yml")):
            from faultray.model.loader import load_yaml
            return load_yaml(yaml_file)
        else:
            from faultray.model.graph import InfraGraph
            return InfraGraph.load(yaml_file)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)


@calendar_app.command("schedule")
def calendar_schedule(
    model: Path = typer.Argument(..., help="Infrastructure model file"),
    add: str | None = typer.Option(None, "--add", help="Cron expression for new window"),
    name: str | None = typer.Option(None, "--name", help="Name for the chaos window"),
    max_blast: float = typer.Option(0.5, "--max-blast", help="Max blast radius (0-1)"),
    max_duration: int = typer.Option(60, "--max-duration", help="Max duration in minutes"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """View or add chaos experiment windows.

    Examples:
        faultray calendar schedule model.yaml --add "0 2 * * THU" --name "Weekly chaos"
        faultray calendar schedule model.yaml --json
    """
    from faultray.simulator.chaos_calendar import ChaosCalendar, ChaosWindow

    graph = _load_graph(model)
    cal = ChaosCalendar(graph)

    if add:
        window_name = name or f"window-{add.replace(' ', '-')}"
        window = ChaosWindow(
            name=window_name,
            cron_expression=add,
            max_blast_radius=max_blast,
            max_duration_minutes=max_duration,
        )
        cal.add_window(window)
        if not json_output:
            console.print(f"[green]Added chaos window: {window_name} ({add})[/]")

    schedule = cal.get_schedule()
    cal.close()

    if json_output:
        console.print_json(data={"windows": schedule})
        return

    if not schedule:
        console.print("[yellow]No chaos windows scheduled. Use --add to create one.[/]")
        return

    table = Table(title="Chaos Windows", show_header=True)
    table.add_column("Name", style="cyan", width=20)
    table.add_column("Cron", width=18)
    table.add_column("Max Blast", justify="right", width=10)
    table.add_column("Categories", width=20)
    table.add_column("Duration (min)", justify="right", width=14)

    for w in schedule:
        table.add_row(
            w["name"],
            w["cron_expression"],
            f"{w['max_blast_radius']:.1f}",
            ", ".join(w["allowed_categories"]),
            str(w["max_duration_minutes"]),
        )
    console.print(table)


@calendar_app.command("forecast")
def calendar_forecast(
    model: Path = typer.Argument(..., help="Infrastructure model file"),
    days: int = typer.Option(30, "--days", help="Forecast horizon in days"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Forecast risk of critical incidents.

    Examples:
        faultray calendar forecast model.yaml --days 30
        faultray calendar forecast model.yaml --json
    """
    from faultray.simulator.chaos_calendar import ChaosCalendar

    graph = _load_graph(model)
    cal = ChaosCalendar(graph)
    forecast = cal.risk_forecast(horizon_days=days)
    cal.close()

    if json_output:
        console.print_json(data={
            "horizon_days": forecast.horizon_days,
            "critical_incident_probability": forecast.critical_incident_probability,
            "component_risks": forecast.component_risks,
            "recommendation": forecast.recommendation,
        })
        return

    prob = forecast.critical_incident_probability
    if prob > 0.8:
        prob_color = "red"
    elif prob > 0.4:
        prob_color = "yellow"
    else:
        prob_color = "green"

    console.print(Panel(
        f"[bold]Horizon:[/] {forecast.horizon_days} days\n"
        f"[bold]Critical Incident Probability:[/] [{prob_color}]{prob:.1%}[/]\n\n"
        f"[bold]Recommendation:[/] {forecast.recommendation}",
        title="[bold]Risk Forecast[/]",
        border_style=prob_color,
    ))

    if forecast.component_risks:
        table = Table(title="Per-Component Risk", show_header=True)
        table.add_column("Component", style="cyan", width=25)
        table.add_column("Failure Probability", justify="right", width=20)

        for comp_id, prob_val in sorted(
            forecast.component_risks.items(),
            key=lambda x: x[1],
            reverse=True,
        ):
            color = "red" if prob_val > 0.7 else ("yellow" if prob_val > 0.3 else "green")
            table.add_row(comp_id, f"[{color}]{prob_val:.1%}[/]")
        console.print()
        console.print(table)


@calendar_app.command("suggest")
def calendar_suggest(
    model: Path = typer.Argument(..., help="Infrastructure model file"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Suggest chaos experiments for the infrastructure.

    Examples:
        faultray calendar suggest model.yaml
        faultray calendar suggest model.yaml --json
    """
    from faultray.simulator.chaos_calendar import ChaosCalendar

    graph = _load_graph(model)
    cal = ChaosCalendar(graph)
    suggestions = cal.suggest_experiments()
    cal.close()

    if json_output:
        console.print_json(data={"suggestions": suggestions})
        return

    if not suggestions:
        console.print("[green]No experiments to suggest. Infrastructure looks well-tested.[/]")
        return

    table = Table(title="Suggested Experiments", show_header=True)
    table.add_column("Component", style="cyan", width=20)
    table.add_column("Priority", justify="right", width=10)
    table.add_column("Reasons", width=35)
    table.add_column("Scenario", width=30)

    for s in suggestions[:15]:
        prio = s["priority"]
        color = "red" if prio >= 5 else ("yellow" if prio >= 3 else "green")
        table.add_row(
            s["component_name"],
            f"[{color}]{prio:.1f}[/]",
            ", ".join(s["reasons"]),
            s["suggested_scenario"],
        )
    console.print(table)


# ---------------------------------------------------------------------------
# Scheduler-based calendar commands
# ---------------------------------------------------------------------------


@calendar_app.command("show")
def calendar_show(
    days: int = typer.Option(7, "--days", help="Number of days to show"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Show upcoming experiments.

    Examples:
        faultray calendar show
        faultray calendar show --days 14 --json
    """
    from faultray.scheduler.chaos_calendar import ChaosCalendar

    cal = ChaosCalendar()
    upcoming = cal.get_upcoming(days=days)

    if json_output:
        console.print_json(data={"upcoming": [e.to_dict() for e in upcoming]})
        return

    if not upcoming:
        console.print(f"[yellow]No experiments scheduled in the next {days} days.[/]")
        return

    table = Table(title=f"Upcoming Experiments (next {days} days)", show_header=True)
    table.add_column("ID", style="dim", width=10)
    table.add_column("Name", style="cyan", width=30)
    table.add_column("Scheduled", width=20)
    table.add_column("Status", width=12)
    table.add_column("Owner", width=15)
    table.add_column("Targets", width=20)

    for exp in upcoming:
        status_color = {
            "scheduled": "blue", "running": "yellow", "completed": "green",
            "failed": "red", "cancelled": "dim", "skipped": "dim",
        }.get(exp.status.value, "white")
        table.add_row(
            exp.id,
            exp.name,
            exp.scheduled_time.strftime("%Y-%m-%d %H:%M"),
            f"[{status_color}]{exp.status.value}[/]",
            exp.owner or "-",
            ", ".join(exp.target_components) or "-",
        )
    console.print(table)


@calendar_app.command("auto-schedule")
def calendar_auto_schedule(
    model: Path = typer.Argument(..., help="Infrastructure model file (YAML/JSON)"),
    frequency: str = typer.Option("weekly", "--frequency", help="Recurrence pattern (once/daily/weekly/biweekly/monthly/quarterly)"),
    owner: str = typer.Option("auto-scheduler", "--owner", help="Owner name for auto-scheduled experiments"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Auto-schedule chaos experiments based on risk analysis.

    Examples:
        faultray calendar auto-schedule model.yaml --frequency weekly
        faultray calendar auto-schedule model.yaml --owner sre-team --json
    """
    from faultray.scheduler.chaos_calendar import ChaosCalendar, RecurrencePattern

    graph = _load_graph(model)
    cal = ChaosCalendar()

    freq = RecurrencePattern(frequency)
    experiments = cal.auto_schedule(graph, frequency=freq, owner=owner)

    if json_output:
        console.print_json(data={
            "scheduled": len(experiments),
            "experiments": [e.to_dict() for e in experiments],
        })
        return

    console.print(f"[green]Auto-scheduled {len(experiments)} experiments.[/]\n")

    table = Table(title="Auto-Scheduled Experiments", show_header=True)
    table.add_column("ID", style="dim", width=10)
    table.add_column("Name", style="cyan", width=35)
    table.add_column("Scheduled", width=20)
    table.add_column("Target", width=15)

    for exp in experiments:
        table.add_row(
            exp.id,
            exp.name,
            exp.scheduled_time.strftime("%Y-%m-%d %H:%M"),
            ", ".join(exp.target_components),
        )
    console.print(table)


@calendar_app.command("history")
def calendar_history(
    days: int = typer.Option(90, "--days", help="Number of days of history"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Show past experiment results.

    Examples:
        faultray calendar history
        faultray calendar history --days 30 --json
    """
    from faultray.scheduler.chaos_calendar import ChaosCalendar

    cal = ChaosCalendar()
    history = cal.get_history(days=days)

    if json_output:
        console.print_json(data={"history": [e.to_dict() for e in history]})
        return

    if not history:
        console.print(f"[yellow]No experiments completed in the last {days} days.[/]")
        return

    table = Table(title=f"Experiment History (last {days} days)", show_header=True)
    table.add_column("ID", style="dim", width=10)
    table.add_column("Name", style="cyan", width=30)
    table.add_column("Completed", width=20)
    table.add_column("Status", width=12)
    table.add_column("Targets", width=20)

    for exp in history:
        status_color = "green" if exp.status.value == "completed" else "red"
        table.add_row(
            exp.id,
            exp.name,
            exp.updated_at.strftime("%Y-%m-%d %H:%M"),
            f"[{status_color}]{exp.status.value}[/]",
            ", ".join(exp.target_components) or "-",
        )
    console.print(table)


@calendar_app.command("coverage")
def calendar_coverage(
    model: Path = typer.Argument(..., help="Infrastructure model file"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Show which components have been tested recently.

    Examples:
        faultray calendar coverage model.yaml
        faultray calendar coverage model.yaml --json
    """
    from faultray.scheduler.chaos_calendar import ChaosCalendar

    graph = _load_graph(model)
    cal = ChaosCalendar()
    coverage = cal.get_coverage(graph)

    if json_output:
        console.print_json(data={"coverage": coverage})
        return

    tested = sum(1 for v in coverage.values() if v)
    total = len(coverage)
    pct = (tested / total * 100) if total > 0 else 0

    pct_color = "green" if pct >= 80 else ("yellow" if pct >= 50 else "red")
    console.print(Panel(
        f"[bold]Coverage:[/] [{pct_color}]{pct:.0f}%[/] ({tested}/{total} components tested in last 30 days)",
        title="[bold]Chaos Test Coverage[/]",
        border_style=pct_color,
    ))

    table = Table(show_header=True)
    table.add_column("Component", style="cyan", width=25)
    table.add_column("Tested (30d)", justify="center", width=15)

    for comp_id, tested_flag in sorted(coverage.items()):
        icon = "[green]Yes[/]" if tested_flag else "[red]No[/]"
        table.add_row(comp_id, icon)
    console.print(table)


@calendar_app.command("blackout")
def calendar_blackout(
    start: str = typer.Option(..., "--start", help="Blackout start (ISO 8601, e.g. 2025-03-25)"),
    end: str = typer.Option(..., "--end", help="Blackout end (ISO 8601, e.g. 2025-03-27)"),
    reason: str = typer.Option("", "--reason", help="Reason for blackout"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Add a blackout window (no experiments during this period).

    Examples:
        faultray calendar blackout --start 2025-03-25 --end 2025-03-27 --reason "Release freeze"
    """
    from datetime import datetime, timezone

    from faultray.scheduler.chaos_calendar import BlackoutWindow, ChaosCalendar

    start_dt = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    end_dt = datetime.fromisoformat(end).replace(tzinfo=timezone.utc)

    cal = ChaosCalendar()
    bw = BlackoutWindow(start=start_dt, end=end_dt, reason=reason)
    cal.add_blackout(bw)

    if json_output:
        console.print_json(data={"blackout": bw.to_dict()})
        return

    console.print(f"[green]Added blackout window: {start} to {end}[/]")
    if reason:
        console.print(f"  Reason: {reason}")


@calendar_app.command("export")
def calendar_export(
    output: Path = typer.Option("chaos-calendar.ics", "--output", "-o", help="Output .ics file path"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON instead of .ics"),
) -> None:
    """Export calendar as iCalendar (.ics) file.

    Examples:
        faultray calendar export --output chaos.ics
        faultray calendar export --json
    """
    from faultray.scheduler.chaos_calendar import ChaosCalendar

    cal = ChaosCalendar()

    if json_output:
        view = cal.get_calendar_view()
        console.print_json(data={
            "experiments": [e.to_dict() for e in view.experiments],
            "blackout_windows": [b.to_dict() for b in view.blackout_windows],
        })
        return

    ical = cal.export_ical()
    output.write_text(ical)
    console.print(f"[green]Exported calendar to {output}[/]")
