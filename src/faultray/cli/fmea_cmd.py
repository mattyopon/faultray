# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""CLI command for FMEA (Failure Mode & Effects Analysis)."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console


@app.command()
def fmea(
    model_file: Path = typer.Argument(
        ...,
        help="Path to YAML/JSON infrastructure model file.",
    ),
    component: str = typer.Option(
        None, "--component", "-c",
        help="Analyze a single component by ID.",
    ),
    min_rpn: int = typer.Option(
        0, "--min-rpn",
        help="Only show failure modes with RPN >= this value.",
    ),
    csv_output: bool = typer.Option(
        False, "--csv",
        help="Export as CSV.",
    ),
    output_file: str = typer.Option(
        None, "--output", "-o",
        help="Output file path (used with --csv).",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON.",
    ),
) -> None:
    """FMEA (Failure Mode & Effects Analysis) for infrastructure.

    Systematic engineering methodology to identify potential failure modes,
    their causes, effects, and risk priority numbers (RPN = S x O x D).

    Examples:
        faultray fmea infra.yaml
        faultray fmea infra.yaml --component web-api
        faultray fmea infra.yaml --min-rpn 200
        faultray fmea infra.yaml --csv --output fmea.csv
        faultray fmea infra.yaml --json
    """
    from faultray.simulator.fmea_engine import FMEAEngine

    graph = _load_graph_for_analysis(model_file, None)
    engine = FMEAEngine()

    if component:
        comp = graph.get_component(component)
        if comp is None:
            console.print(f"[red]Component '{component}' not found.[/]")
            raise typer.Exit(1)
        modes = engine.analyze_component(graph, component)
        # Build a mini report from the single component
        report = engine._build_report(modes)
    else:
        report = engine.analyze(graph)

    # Apply min-rpn filter
    if min_rpn > 0:
        report.failure_modes = [fm for fm in report.failure_modes if fm.rpn >= min_rpn]
        report.top_risks = [fm for fm in report.top_risks if fm.rpn >= min_rpn]

    # --- CSV output ---
    if csv_output:
        rows = engine.to_spreadsheet_format(report)
        if min_rpn > 0:
            rows = [r for r in rows if r["RPN"] >= min_rpn]

        if output_file:
            with open(output_file, "w", newline="") as f:
                if rows:
                    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)
            console.print(f"[green]FMEA report exported to {output_file}[/]")
        else:
            buf = io.StringIO()
            if rows:
                writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            console.print(buf.getvalue())
        return

    # --- JSON output ---
    if json_output:
        data = {
            "total_rpn": report.total_rpn,
            "average_rpn": report.average_rpn,
            "high_risk_count": report.high_risk_count,
            "medium_risk_count": report.medium_risk_count,
            "low_risk_count": report.low_risk_count,
            "failure_modes": [
                {
                    "id": fm.id,
                    "component_id": fm.component_id,
                    "component_name": fm.component_name,
                    "mode": fm.mode,
                    "cause": fm.cause,
                    "effect_local": fm.effect_local,
                    "effect_system": fm.effect_system,
                    "severity": fm.severity,
                    "occurrence": fm.occurrence,
                    "detection": fm.detection,
                    "rpn": fm.rpn,
                    "current_controls": fm.current_controls,
                    "recommended_actions": fm.recommended_actions,
                    "responsible": fm.responsible,
                }
                for fm in report.failure_modes
            ],
            "rpn_by_component": report.rpn_by_component,
            "rpn_by_failure_mode": report.rpn_by_failure_mode,
            "improvement_priority": [
                {"component": c, "action": a, "rpn": r}
                for c, a, r in report.improvement_priority
            ],
        }
        console.print_json(json.dumps(data))
        return

    # --- Rich table output ---
    scope = f"component '{component}'" if component else f"{len(graph.components)} components"
    console.print(Panel(
        f"[bold cyan]FMEA Analysis[/] — {scope}\n\n"
        f"Total RPN: [bold]{report.total_rpn}[/]  |  "
        f"Average RPN: [bold]{report.average_rpn:.1f}[/]\n"
        f"[red]High Risk (>200):[/] {report.high_risk_count}  |  "
        f"[yellow]Medium Risk (100-200):[/] {report.medium_risk_count}  |  "
        f"[green]Low Risk (<=100):[/] {report.low_risk_count}",
        title="FMEA Report",
        border_style="cyan",
    ))

    table = Table(title="Failure Modes (sorted by RPN)", show_lines=True)
    table.add_column("Component", style="bold", max_width=15)
    table.add_column("Failure Mode", max_width=20)
    table.add_column("Cause", max_width=20)
    table.add_column("S", justify="center", width=3)
    table.add_column("O", justify="center", width=3)
    table.add_column("D", justify="center", width=3)
    table.add_column("RPN", justify="center", width=5)
    table.add_column("Controls", max_width=25)
    table.add_column("Actions", max_width=30)

    sorted_modes = sorted(report.failure_modes, key=lambda fm: fm.rpn, reverse=True)
    for fm in sorted_modes:
        if fm.rpn > 200:
            rpn_style = "bold red"
        elif fm.rpn > 100:
            rpn_style = "bold yellow"
        else:
            rpn_style = "green"

        controls_str = "\n".join(fm.current_controls[:2]) if fm.current_controls else "-"
        actions_str = "\n".join(fm.recommended_actions[:2]) if fm.recommended_actions else "-"

        table.add_row(
            fm.component_name,
            fm.mode,
            fm.cause,
            str(fm.severity),
            str(fm.occurrence),
            str(fm.detection),
            f"[{rpn_style}]{fm.rpn}[/{rpn_style}]",
            controls_str,
            actions_str,
        )

    console.print(table)

    # Improvement priorities
    if report.improvement_priority:
        prio_table = Table(title="Improvement Priority (Top 10)")
        prio_table.add_column("#", width=3)
        prio_table.add_column("Component")
        prio_table.add_column("Action")
        prio_table.add_column("RPN", justify="center")

        for idx, (comp_id, action, rpn) in enumerate(report.improvement_priority[:10], 1):
            prio_table.add_row(str(idx), comp_id, action, str(rpn))

        console.print(prio_table)
