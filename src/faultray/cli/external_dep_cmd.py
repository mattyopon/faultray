# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI command for External SaaS Dependency Impact Simulation.

Usage:
    faultray external-impact examples/saas-dependencies.yaml
    faultray external-impact examples/saas-dependencies.yaml --json
    faultray external-impact examples/saas-dependencies.yaml --service stripe
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import (
    DEFAULT_MODEL_PATH,
    _load_graph_for_analysis,
    app,
    console,
)

_RISK_COLORS: dict[str, str] = {
    "critical": "red",
    "high": "yellow",
    "medium": "dim yellow",
    "low": "green",
}


@app.command(name="external-impact")
def external_impact(
    model: Path = typer.Argument(
        ...,
        help="Infrastructure model file (YAML or JSON).",
    ),
    service: str = typer.Option(
        None,
        "--service",
        "-s",
        help="Filter to a specific external service (e.g. 'stripe').",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output machine-readable JSON.",
    ),
) -> None:
    """Simulate the impact of an external SaaS service outage.

    Answers questions like "What happens if Stripe goes down?" or
    "How bad is an AWS S3 outage?" by tracing cascade effects through
    your infrastructure model.

    \b
    Examples:
        faultray external-impact examples/saas-dependencies.yaml
        faultray external-impact infra.yaml --json
        faultray external-impact infra.yaml --service stripe
        faultray external-impact infra.yaml --service s3 --json
    """
    if json_output:
        import logging as _logging
        _logging.getLogger("faultray").setLevel(_logging.ERROR)
    # Load graph
    yaml_path = model if str(model).endswith((".yaml", ".yml")) else None
    json_path = model if yaml_path is None else None
    graph = _load_graph_for_analysis(json_path or DEFAULT_MODEL_PATH, yaml_path)

    from faultray.simulator.external_dependency_analyzer import ExternalDependencyAnalyzer

    analyzer = ExternalDependencyAnalyzer(graph)
    report = analyzer.analyze(service_filter=service)

    if json_output:
        output = {
            "total_external_deps": report.total_external_deps,
            "unprotected_count": report.unprotected_count,
            "risk_score": report.risk_score,
            "summary": report.summary,
            "impacts": [
                {
                    "external_service": imp.external_service,
                    "component_id": imp.component_id,
                    "affected_components": imp.affected_components,
                    "blast_radius_percent": imp.blast_radius_percent,
                    "estimated_downtime_minutes": imp.estimated_downtime_minutes,
                    "business_impact": imp.business_impact,
                    "mitigation": imp.mitigation,
                    "has_fallback": imp.has_fallback,
                    "risk_level": imp.risk_level,
                }
                for imp in report.impacts
            ],
        }
        console.print_json(data=output)
        return

    # --- Rich terminal output ---
    console.print()

    # Summary panel
    critical = sum(1 for i in report.impacts if i.risk_level == "critical")
    high = sum(1 for i in report.impacts if i.risk_level == "high")
    medium = sum(1 for i in report.impacts if i.risk_level == "medium")
    low = sum(1 for i in report.impacts if i.risk_level == "low")

    summary_text = (
        f"[bold]External Services:[/] {report.total_external_deps}  "
        f"[red]Unprotected:[/] {report.unprotected_count}\n"
        f"[bold]Risk Score:[/] {report.risk_score:.1f}/100  "
        f"[red]Critical:[/] {critical}  "
        f"[yellow]High:[/] {high}  "
        f"[dim yellow]Medium:[/] {medium}  "
        f"[green]Low:[/] {low}\n"
        f"[dim]{report.summary}[/]"
    )
    console.print(Panel(
        summary_text,
        title="[bold cyan]External SaaS Dependency Impact[/]",
        border_style="cyan",
    ))

    if not report.impacts:
        console.print(
            "[dim]No external_api components found. Add components with "
            "type: external_api to your model.[/]"
        )
        return

    # Impact table
    table = Table(
        title="External Service Outage Impact",
        show_header=True,
        show_lines=True,
    )
    table.add_column("Service", style="cyan", no_wrap=True)
    table.add_column("Risk", width=10, justify="center")
    table.add_column("Blast %", width=8, justify="right")
    table.add_column("Downtime", width=10, justify="right")
    table.add_column("Fallback", width=8, justify="center")
    table.add_column("Affected", width=8, justify="right")
    table.add_column("Business Impact", min_width=30)

    for imp in report.impacts:
        color = _RISK_COLORS.get(imp.risk_level, "white")
        fallback_icon = "[green]YES[/]" if imp.has_fallback else "[red]NO[/]"
        downtime_str = (
            f"{imp.estimated_downtime_minutes:.0f}m"
            if imp.estimated_downtime_minutes > 0
            else "[green]0m[/]"
        )
        table.add_row(
            imp.external_service,
            f"[{color}]{imp.risk_level.upper()}[/]",
            f"[{color}]{imp.blast_radius_percent:.0f}%[/]",
            downtime_str,
            fallback_icon,
            str(len(imp.affected_components)),
            imp.business_impact,
        )

    console.print()
    console.print(table)

    # Detail panels for critical/high risk items
    for imp in report.impacts:
        if imp.risk_level not in ("critical", "high"):
            continue
        color = _RISK_COLORS[imp.risk_level]
        affected_str = (
            ", ".join(imp.affected_components[:5])
            + (" ..." if len(imp.affected_components) > 5 else "")
        ) if imp.affected_components else "(none)"
        detail = (
            f"[bold]Blast Radius:[/] {imp.blast_radius_percent:.1f}% "
            f"({len(imp.affected_components)} components)\n"
            f"[bold]Affected:[/] {affected_str}\n"
            f"[bold]Est. Downtime:[/] {imp.estimated_downtime_minutes:.0f} minutes\n"
            f"[bold]Business Impact:[/] {imp.business_impact}\n"
            f"[bold]Mitigation:[/] {imp.mitigation}"
        )
        console.print()
        console.print(Panel(
            detail,
            title=f"[{color}]{imp.risk_level.upper()}[/] — {imp.external_service}",
            border_style=color,
        ))

    console.print()
