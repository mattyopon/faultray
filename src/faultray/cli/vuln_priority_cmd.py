# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI command for vulnerability × impact-range priority matrix.

Usage:
    faultray vuln-priority examples/demo-infra.yaml
    faultray vuln-priority examples/demo-infra.yaml --json
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from faultray.cli.main import app, console


@app.command(name="vuln-priority")
def vuln_priority_command(
    infra_file: Annotated[
        Path,
        typer.Argument(help="Infrastructure YAML or JSON model file."),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output results as JSON."),
    ] = False,
    top_n: Annotated[
        int,
        typer.Option(
            "--top",
            help="Show only the top N components. 0 = show all.",
        ),
    ] = 0,
) -> None:
    """Show which components need security patches first.

    Ranks each component by vulnerability score x blast radius so you
    can triage security work by actual risk rather than CVE score alone.

    Examples:

        faultray vuln-priority examples/demo-infra.yaml

        faultray vuln-priority examples/demo-infra.yaml --json

        faultray vuln-priority examples/demo-infra.yaml --top 5
    """
    if not infra_file.exists():
        console.print(f"[red]File not found: {infra_file}[/]")
        raise typer.Exit(1)

    if json_output:
        import logging as _logging
        _logging.getLogger("faultray").setLevel(_logging.ERROR)

    try:
        if str(infra_file).endswith((".yaml", ".yml")):
            from faultray.model.loader import load_yaml
            graph = load_yaml(infra_file)
        else:
            from faultray.model.graph import InfraGraph
            graph = InfraGraph.load(infra_file)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to load model: {exc}[/]")
        raise typer.Exit(1)

    if not graph.components:
        console.print("[red]No components found in the model.[/]")
        raise typer.Exit(1)

    from faultray.simulator.vulnerability_priority import VulnerabilityPriorityEngine

    engine = VulnerabilityPriorityEngine(graph)
    report = engine.analyze()

    priorities = report.priorities
    if top_n > 0:
        priorities = priorities[:top_n]

    if json_output:

        data = {
            "summary": report.summary,
            "critical_count": report.critical_count,
            "high_count": report.high_count,
            "risk_score": report.risk_score,
            "priorities": [
                {
                    "rank": p.priority_rank,
                    "component_id": p.component_id,
                    "component_name": p.component_name,
                    "vulnerability_score": p.vulnerability_score,
                    "blast_radius": p.blast_radius,
                    "priority_score": p.priority_score,
                    "risk_factors": p.risk_factors,
                    "recommendation": p.recommendation,
                }
                for p in priorities
            ],
        }
        console.print_json(data=data)
        return

    # Rich table output.
    console.print(f"\n[bold]Vulnerability Priority Matrix[/] — {infra_file.name}")
    console.print(f"  [dim]{report.summary}[/]\n")

    table = Table(show_header=True, header_style="bold dim")
    table.add_column("#", style="dim", width=4)
    table.add_column("Component", min_width=18)
    table.add_column("Vuln Score", justify="right", width=12)
    table.add_column("Blast Radius", justify="right", width=13)
    table.add_column("Priority", justify="right", width=10)
    table.add_column("Risk Factors", min_width=28)
    table.add_column("Recommendation", min_width=36)

    for p in priorities:
        if p.priority_score >= 70.0:
            rank_style = "bold red"
        elif p.priority_score >= 40.0:
            rank_style = "yellow"
        else:
            rank_style = "green"

        table.add_row(
            f"[{rank_style}]{p.priority_rank}[/]",
            p.component_name,
            f"[{rank_style}]{p.vulnerability_score:.1f}/10[/]",
            f"{p.blast_radius:.1f}%",
            f"[{rank_style}]{p.priority_score:.1f}[/]",
            ", ".join(p.risk_factors) or "—",
            p.recommendation,
        )

    console.print(table)

    # Summary counts.
    console.print(
        f"\n[bold red]Critical (>=70):[/] {report.critical_count}  "
        f"[bold yellow]High (>=40):[/] {report.high_count}  "
        f"Risk Score: [bold]{report.risk_score:.1f}/100[/]"
    )
