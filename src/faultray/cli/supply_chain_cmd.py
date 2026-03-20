# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""CLI command for Supply Chain Risk Analysis."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console


@app.command("supply-chain")
def supply_chain(
    model: Path = typer.Argument(..., help="Infrastructure model file (YAML or JSON)"),
    vulns: Path = typer.Option(
        ..., "--vulns", "-v", help="Vulnerability report JSON (Snyk/Dependabot/Trivy format)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Supply Chain Risk Analysis — map vulnerabilities to infrastructure impact.

    Reads a vulnerability report (Snyk, Dependabot, or Trivy JSON format) and
    maps each CVE to infrastructure failure modes.

    Examples:
        # Analyze supply chain risk
        faultray supply-chain infra.yaml --vulns snyk-results.json

        # JSON output
        faultray supply-chain infra.yaml --vulns trivy-report.json --json
    """
    from faultray.simulator.supply_chain_engine import SupplyChainEngine

    graph = _load_graph_for_analysis(model, model)

    if not vulns.exists():
        console.print(f"[red]Vulnerability file not found: {vulns}[/]")
        raise typer.Exit(1)

    engine = SupplyChainEngine(graph)
    report = engine.analyze_from_file(vulns)

    if json_output:
        console.print_json(data={
            "total_vulnerabilities": report.total_vulnerabilities,
            "critical_count": report.critical_count,
            "infrastructure_risk_score": report.infrastructure_risk_score,
            "impacts": [
                {
                    "cve_id": i.cve_id,
                    "package": i.package,
                    "severity": i.severity,
                    "affected_components": i.affected_components,
                    "infrastructure_impact": i.infrastructure_impact,
                    "estimated_blast_radius": i.estimated_blast_radius,
                    "risk_score": i.risk_score,
                }
                for i in report.impacts
            ],
            "recommendations": report.recommendations,
        })
        return

    # Risk score color
    if report.infrastructure_risk_score >= 70:
        risk_color = "red"
    elif report.infrastructure_risk_score >= 40:
        risk_color = "yellow"
    else:
        risk_color = "green"

    # Summary panel
    summary = (
        f"[bold]Total Vulnerabilities:[/] {report.total_vulnerabilities}\n"
        f"[bold]Critical:[/] [red]{report.critical_count}[/]\n"
        f"[bold]Infrastructure Risk Score:[/] [{risk_color}]{report.infrastructure_risk_score:.1f}/100[/]"
    )
    console.print()
    console.print(Panel(
        summary,
        title="[bold]Supply Chain Risk Report[/]",
        border_style=risk_color,
    ))

    # Impact table
    if report.impacts:
        table = Table(title="Vulnerability Impacts", show_header=True)
        table.add_column("CVE", style="cyan", width=18)
        table.add_column("Package", width=16)
        table.add_column("Severity", width=10, justify="center")
        table.add_column("Impact", width=24)
        table.add_column("Blast Radius", justify="right", width=12)
        table.add_column("Risk", justify="right", width=6)

        sev_colors = {
            "critical": "bold red",
            "high": "red",
            "medium": "yellow",
            "low": "green",
        }

        for impact in report.impacts:
            color = sev_colors.get(impact.severity, "white")
            table.add_row(
                impact.cve_id[:18],
                impact.package[:16] if impact.package else "N/A",
                f"[{color}]{impact.severity.upper()}[/]",
                impact.infrastructure_impact,
                str(impact.estimated_blast_radius),
                f"{impact.risk_score:.1f}",
            )

        console.print()
        console.print(table)

    # Recommendations
    if report.recommendations:
        console.print()
        for i, rec in enumerate(report.recommendations, 1):
            console.print(f"  {i}. {rec}")
