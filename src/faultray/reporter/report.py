# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Report generator - formats simulation results for display."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from faultray.i18n import t
from faultray.model.components import HealthStatus
from faultray.model.graph import InfraGraph
from faultray.reporter.style import (
    HEALTH_LABELS,
    iter_effects_with_delta,
    risk_bucket,
    score_bucket,
)
from faultray.simulator.engine import SimulationReport, ScenarioResult


def _health_color(health: HealthStatus) -> str:
    return {
        HealthStatus.HEALTHY: "green",
        HealthStatus.DEGRADED: "yellow",
        HealthStatus.OVERLOADED: "red",
        HealthStatus.DOWN: "bold red",
    }.get(health, "white")


def _health_icon(health: HealthStatus) -> str:
    label = HEALTH_LABELS.get(health)
    if label is None:
        return "?"
    return f"[{_health_color(health)}]{label}[/]"


_RISK_MARKUP = {
    "critical": "[bold red]{score:.1f}/10 CRITICAL[/]",
    "warning": "[yellow]{score:.1f}/10 WARNING[/]",
    "low": "[green]{score:.1f}/10 LOW[/]",
}

_SCORE_RICH_COLORS = {"good": "green", "fair": "yellow", "poor": "red"}


def _risk_label(score: float) -> str:
    return _RISK_MARKUP[risk_bucket(score)].format(score=score)


def print_infrastructure_summary(graph: InfraGraph, console: Console | None = None) -> None:
    """Print infrastructure overview."""
    console = console or Console()
    summary = graph.summary()

    table = Table(title=t("infrastructure_overview"), show_header=True)
    table.add_column(t("metric"), style="cyan")
    table.add_column(t("value"), style="white")

    table.add_row(t("components"), str(summary["total_components"]))
    table.add_row(t("dependencies"), str(summary["total_dependencies"]))
    for comp_type, count in summary["component_types"].items():
        table.add_row(f"  {comp_type}", str(count))

    score = summary["resilience_score"]
    color = _SCORE_RICH_COLORS[score_bucket(score)]
    table.add_row(t("resilience_score"), f"[{color}]{score}/100[/]")

    console.print(table)


def print_simulation_report(
    report: SimulationReport,
    console: Console | None = None,
    graph: InfraGraph | None = None,
) -> None:
    """Print full simulation report."""
    console = console or Console()

    # Header
    score = report.resilience_score
    color = _SCORE_RICH_COLORS[score_bucket(score)]

    console.print()
    console.print(Panel(
        f"[bold]{t('resilience_score')}: [{color}]{score:.0f}/100[/][/]\n\n"
        f"{t('scenarios_tested')}: {len(report.results)}\n"
        f"[bold red]{t('critical')}: {len(report.critical_findings)}[/]  "
        f"[yellow]{t('warning')}: {len(report.warnings)}[/]  "
        f"[green]{t('passed')}: {len(report.passed)}[/]",
        title=f"[bold]{t('report_title')}[/]",
        border_style=color,
    ))

    # Critical findings
    if report.critical_findings:
        console.print()
        console.print(f"[bold red]{t('critical_findings').upper()}[/]")
        console.print()
        for result in report.critical_findings:
            _print_scenario_result(result, console)

    # Warnings
    if report.warnings:
        console.print()
        console.print(f"[yellow]{t('warning_findings').upper()}[/]")
        console.print()
        for result in report.warnings:
            _print_scenario_result(result, console)

    # Passed (summary only)
    if report.passed:
        console.print()
        console.print(f"[green]{t('passed_with_low_risk', count=len(report.passed))}[/]")

    # Agent resilience section
    if graph is not None:
        _print_agent_section(report, graph, console)

    # Score context: explain structural score vs scenario results
    if score < 70 and not report.critical_findings and not report.warnings:
        console.print()
        console.print(
            "[dim]  \u2139 Score reflects structural vulnerabilities "
            "(SPOFs, chain depth).\n"
            "    All scenarios passed = good runtime resilience "
            "despite architectural gaps.[/]"
        )


def _print_agent_section(report: SimulationReport, graph: InfraGraph, console: Console) -> None:
    """Print agent resilience section if agent components exist."""
    from faultray.simulator.adoption_engine import AdoptionEngine
    from faultray.simulator.agent_cascade import (
        AGENT_COMPONENT_TYPES,
        calculate_cross_layer_hallucination_risk,
    )
    agents = [c for c in graph.components.values() if c.type in AGENT_COMPONENT_TYPES]
    if not agents:
        return

    console.print()
    console.print("[bold]AGENT RESILIENCE[/]")
    console.print()

    engine = AdoptionEngine(graph)
    assessments = engine.assess_all_agents()

    if assessments:
        table = Table(show_header=True)
        table.add_column("Agent", style="cyan")
        table.add_column("Risk", justify="right")
        table.add_column("Level")
        table.add_column("Blast Radius", justify="right")
        table.add_column("Safe to Deploy")

        for a in assessments:
            level_color = {"low": "green", "medium": "yellow", "high": "red", "critical": "bold red"}.get(a.risk_level.value, "white")
            safe_str = "[green]Yes[/]" if a.safe_to_deploy else "[bold red]No[/]"
            table.add_row(
                a.agent_name,
                f"{a.risk_score:.1f}/10",
                f"[{level_color}]{a.risk_level.value.upper()}[/]",
                str(a.max_blast_radius),
                safe_str,
            )
        console.print(table)

    # Cross-layer hallucination risks for DOWN components
    down_components = [
        c for c in graph.components.values()
        if c.health == HealthStatus.DOWN
    ]
    for result in report.results:
        for effect in result.cascade.effects:
            if effect.health == HealthStatus.DOWN:
                comp = graph.get_component(effect.component_id)
                if comp and comp not in down_components:
                    down_components.append(comp)

    hallucination_risks: list[tuple[str, float, str]] = []
    seen = set()
    for comp in down_components:
        for agent_id, prob, reason in calculate_cross_layer_hallucination_risk(graph, comp.id):
            if (agent_id, comp.id) not in seen:
                seen.add((agent_id, comp.id))
                hallucination_risks.append((agent_id, prob, reason))

    if hallucination_risks:
        console.print()
        console.print("[yellow]Cross-Layer Hallucination Risks:[/]")
        for agent_id, prob, reason in hallucination_risks:
            console.print(f"  [yellow]{prob:.0%}[/] {reason}")


def _print_scenario_result(result: ScenarioResult, console: Console) -> None:
    """Print a single scenario result with cascade tree."""
    risk = _risk_label(result.risk_score)
    console.print(f"  {risk}  {result.scenario.name}")
    console.print(f"    {result.scenario.description}")

    if result.cascade.effects:
        tree = Tree(f"  [dim]{t('cascade_path')}[/]")
        for effect, delta in iter_effects_with_delta(result.cascade.effects):
            time_str = f" [dim](+{delta}s)[/]" if delta is not None else ""
            icon = _health_icon(effect.health)
            tree.add(f"{icon} {effect.component_name}{time_str}\n"
                     f"      [dim]{effect.reason}[/]")
        console.print(tree)
    console.print()
