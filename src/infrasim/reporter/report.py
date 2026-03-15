"""Report generator - formats simulation results for display."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from infrasim.model.components import HealthStatus
from infrasim.model.graph import InfraGraph
from infrasim.simulator.engine import SimulationReport, ScenarioResult


def _health_color(health: HealthStatus) -> str:
    return {
        HealthStatus.HEALTHY: "green",
        HealthStatus.DEGRADED: "yellow",
        HealthStatus.OVERLOADED: "red",
        HealthStatus.DOWN: "bold red",
    }.get(health, "white")


def _health_icon(health: HealthStatus) -> str:
    return {
        HealthStatus.HEALTHY: "[green]OK[/]",
        HealthStatus.DEGRADED: "[yellow]WARN[/]",
        HealthStatus.OVERLOADED: "[red]OVERLOAD[/]",
        HealthStatus.DOWN: "[bold red]DOWN[/]",
    }.get(health, "?")


def _risk_label(score: float) -> str:
    if score >= 7.0:
        return f"[bold red]{score:.1f}/10 CRITICAL[/]"
    if score >= 4.0:
        return f"[yellow]{score:.1f}/10 WARNING[/]"
    return f"[green]{score:.1f}/10 LOW[/]"


def print_infrastructure_summary(graph: InfraGraph, console: Console | None = None) -> None:
    """Print infrastructure overview."""
    console = console or Console()
    summary = graph.summary()

    table = Table(title="Infrastructure Overview", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Components", str(summary["total_components"]))
    table.add_row("Dependencies", str(summary["total_dependencies"]))
    for comp_type, count in summary["component_types"].items():
        table.add_row(f"  {comp_type}", str(count))

    score = summary["resilience_score"]
    if score >= 80:
        score_str = f"[green]{score}/100[/]"
    elif score >= 60:
        score_str = f"[yellow]{score}/100[/]"
    else:
        score_str = f"[red]{score}/100[/]"
    table.add_row("Resilience Score", score_str)

    console.print(table)


def print_simulation_report(report: SimulationReport, console: Console | None = None) -> None:
    """Print full simulation report."""
    console = console or Console()

    # Header
    score = report.resilience_score
    if score >= 80:
        color = "green"
    elif score >= 60:
        color = "yellow"
    else:
        color = "red"

    console.print()
    console.print(Panel(
        f"[bold]Resilience Score: [{color}]{score:.0f}/100[/][/]\n\n"
        f"Scenarios tested: {len(report.results)}\n"
        f"[bold red]Critical: {len(report.critical_findings)}[/]  "
        f"[yellow]Warning: {len(report.warnings)}[/]  "
        f"[green]Passed: {len(report.passed)}[/]",
        title="[bold]FaultZero Chaos Simulation Report[/]",
        border_style=color,
    ))

    # Critical findings
    if report.critical_findings:
        console.print()
        console.print("[bold red]CRITICAL FINDINGS[/]")
        console.print()
        for result in report.critical_findings:
            _print_scenario_result(result, console)

    # Warnings
    if report.warnings:
        console.print()
        console.print("[yellow]WARNINGS[/]")
        console.print()
        for result in report.warnings:
            _print_scenario_result(result, console)

    # Passed (summary only)
    if report.passed:
        console.print()
        console.print(f"[green]{len(report.passed)} scenarios passed with low risk[/]")

    # Score context: explain structural score vs scenario results
    if score < 70 and not report.critical_findings and not report.warnings:
        console.print()
        console.print(
            "[dim]  \u2139 Score reflects structural vulnerabilities "
            "(SPOFs, chain depth).\n"
            "    All scenarios passed = good runtime resilience "
            "despite architectural gaps.[/]"
        )


def _print_scenario_result(result: ScenarioResult, console: Console) -> None:
    """Print a single scenario result with cascade tree."""
    risk = _risk_label(result.risk_score)
    console.print(f"  {risk}  {result.scenario.name}")
    console.print(f"    {result.scenario.description}")

    if result.cascade.effects:
        tree = Tree(f"  [dim]Cascade path:[/]")
        prev_time = 0
        for effect in result.cascade.effects:
            time_str = ""
            if effect.estimated_time_seconds > 0:
                delta = effect.estimated_time_seconds - prev_time
                time_str = f" [dim](+{delta}s)[/]"
                prev_time = effect.estimated_time_seconds

            icon = _health_icon(effect.health)
            tree.add(f"{icon} {effect.component_name}{time_str}\n"
                     f"      [dim]{effect.reason}[/]")
        console.print(tree)
    console.print()
