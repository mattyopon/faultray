# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI commands for SRE Maturity Assessment."""

from __future__ import annotations

import json as json_mod
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console
from faultray.simulator.sre_maturity import (
    MaturityDimension,
    SREMaturityEngine,
    _DIMENSION_LABELS,
    _LEVEL_LABELS,
)


_LEVEL_COLORS: dict[int, str] = {
    1: "red",
    2: "yellow",
    3: "cyan",
    4: "green",
    5: "bold green",
}


@app.command("sre-maturity")
def sre_maturity(
    yaml_file: Path = typer.Argument(..., help="Infrastructure YAML or JSON file"),
    dimension: str = typer.Option(
        "", "--dimension", "-d",
        help="Assess a single dimension (e.g., monitoring, incident_response, availability)",
    ),
    roadmap: bool = typer.Option(
        False, "--roadmap", "-r",
        help="Show improvement roadmap",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON",
    ),
) -> None:
    """Assess SRE maturity level of infrastructure configuration.

    Evaluates infrastructure across 8 dimensions and produces a maturity
    level (Level 1-5) per dimension with an overall SRE maturity score.

    Maturity Levels:
      Level 1 - Initial/Ad-hoc
      Level 2 - Managed
      Level 3 - Defined
      Level 4 - Quantitatively Managed
      Level 5 - Optimizing

    Examples:
        # Full maturity assessment
        faultray sre-maturity infra.yaml

        # Assess single dimension
        faultray sre-maturity infra.yaml --dimension monitoring

        # Show improvement roadmap
        faultray sre-maturity infra.yaml --roadmap

        # JSON output for CI/CD
        faultray sre-maturity infra.yaml --json
    """
    graph = _load_graph_for_analysis(
        model=Path("faultray-model.json"),
        yaml_file=yaml_file,
    )

    engine = SREMaturityEngine()

    # Single dimension assessment
    if dimension:
        try:
            dim = MaturityDimension(dimension)
        except ValueError:
            valid = [d.value for d in MaturityDimension]
            console.print(f"[red]Unknown dimension: {dimension}[/]")
            console.print(f"[dim]Valid dimensions: {', '.join(valid)}[/]")
            raise typer.Exit(1)

        assessment = engine.assess_dimension(graph, dim)

        if json_output:
            output = {
                "dimension": assessment.dimension.value,
                "level": assessment.level.value,
                "level_name": _LEVEL_LABELS[assessment.level.value],
                "score": assessment.score,
                "evidence": assessment.evidence,
                "gaps": assessment.gaps,
                "recommendations": assessment.recommendations,
            }
            console.print_json(json_mod.dumps(output, indent=2))
            return

        _print_dimension_assessment(assessment, console)
        return

    # Full assessment
    report = engine.assess(graph)

    if json_output:
        output = {
            "overall_level": report.overall_level.value,
            "overall_level_name": _LEVEL_LABELS[report.overall_level.value],
            "overall_score": report.overall_score,
            "dimensions": [
                {
                    "dimension": d.dimension.value,
                    "level": d.level.value,
                    "level_name": _LEVEL_LABELS[d.level.value],
                    "score": d.score,
                    "evidence": d.evidence,
                    "gaps": d.gaps,
                    "recommendations": d.recommendations,
                }
                for d in report.dimensions
            ],
            "strengths": report.strengths,
            "weaknesses": report.weaknesses,
            "radar_data": report.radar_data,
            "industry_comparison": report.industry_comparison,
        }
        if roadmap:
            output["roadmap"] = [
                {"action": r[0], "target_level": r[1], "effort": r[2]}
                for r in report.roadmap
            ]
        console.print_json(json_mod.dumps(output, indent=2))
        return

    _print_maturity_report(report, console, show_roadmap=roadmap)


def _print_dimension_assessment(
    assessment: "DimensionAssessment",  # noqa: F821
    con: Console,
) -> None:
    """Print a single dimension assessment."""
    dim_label = _DIMENSION_LABELS.get(assessment.dimension.value, assessment.dimension.value)
    level_val = assessment.level.value
    level_label = _LEVEL_LABELS[level_val]
    color = _LEVEL_COLORS.get(level_val, "white")

    con.print()
    con.print(Panel(
        f"[bold]{dim_label}[/]\n\n"
        f"[bold]Maturity Level:[/] [{color}]Level {level_val} - {level_label}[/]\n"
        f"[bold]Score:[/] {assessment.score}/100\n",
        title="[bold]SRE Maturity: Dimension Assessment[/]",
        border_style=color,
    ))

    if assessment.evidence:
        con.print("[bold cyan]Evidence:[/]")
        for e in assessment.evidence:
            con.print(f"  + {e}")

    if assessment.gaps:
        con.print("\n[bold yellow]Gaps:[/]")
        for g in assessment.gaps:
            con.print(f"  - {g}")

    if assessment.recommendations:
        con.print("\n[bold green]Recommendations:[/]")
        for r in assessment.recommendations:
            con.print(f"  -> {r}")

    con.print()


def _print_maturity_report(
    report: "MaturityReport",  # noqa: F821
    con: Console,
    show_roadmap: bool = False,
) -> None:
    """Print full maturity report with Rich formatting."""
    overall_level = report.overall_level.value
    overall_label = _LEVEL_LABELS[overall_level]
    color = _LEVEL_COLORS.get(overall_level, "white")

    # Header panel
    con.print()
    con.print(Panel(
        f"[bold]Overall SRE Maturity:[/] [{color}]Level {overall_level} - {overall_label}[/]\n"
        f"[bold]Score:[/] {report.overall_score}/100\n\n"
        f"[dim]{report.industry_comparison}[/]",
        title="[bold]SRE Maturity Assessment Report[/]",
        border_style=color,
    ))

    # Dimensions table
    dim_table = Table(title="Maturity by Dimension", show_header=True)
    dim_table.add_column("Dimension", style="cyan", width=28)
    dim_table.add_column("Level", width=8, justify="center")
    dim_table.add_column("Label", width=26)
    dim_table.add_column("Score", width=8, justify="right")
    dim_table.add_column("Visual", width=22)

    for d in sorted(report.dimensions, key=lambda x: x.score, reverse=True):
        lv = d.level.value
        lc = _LEVEL_COLORS.get(lv, "white")
        label = _LEVEL_LABELS[lv]
        dim_label = _DIMENSION_LABELS.get(d.dimension.value, d.dimension.value)

        # Visual bar
        bar_len = int(d.score / 5)
        bar = "[" + "#" * bar_len + "." * (20 - bar_len) + "]"

        dim_table.add_row(
            dim_label,
            f"[{lc}]{lv}[/]",
            f"[{lc}]{label}[/]",
            f"{d.score:.0f}",
            f"[{lc}]{bar}[/]",
        )

    con.print()
    con.print(dim_table)

    # Radar chart data (text representation)
    con.print()
    con.print("[bold]Radar Chart Data:[/]")
    max_score = max(d.score for d in report.dimensions) if report.dimensions else 100
    for d in report.dimensions:
        dim_label = _DIMENSION_LABELS.get(d.dimension.value, d.dimension.value)
        bar_width = int(d.score / max_score * 30) if max_score > 0 else 0
        lc = _LEVEL_COLORS.get(d.level.value, "white")
        con.print(f"  {dim_label:<28s} [{lc}]{'|' * bar_width}[/] {d.score:.0f}")

    # Strengths and Weaknesses
    if report.strengths:
        con.print()
        con.print("[bold green]Strengths:[/]")
        for s in report.strengths:
            con.print(f"  + {s}")

    if report.weaknesses:
        con.print()
        con.print("[bold red]Weaknesses:[/]")
        for w in report.weaknesses:
            con.print(f"  - {w}")

    # Roadmap
    if show_roadmap and report.roadmap:
        con.print()
        roadmap_table = Table(title="Improvement Roadmap", show_header=True)
        roadmap_table.add_column("Action", style="cyan", width=55)
        roadmap_table.add_column("Target", width=20)
        roadmap_table.add_column("Effort", width=10, justify="center")

        effort_colors = {"Low": "green", "Medium": "yellow", "High": "red", "None": "dim"}

        for action, target, effort in report.roadmap:
            ec = effort_colors.get(effort, "white")
            roadmap_table.add_row(action, target, f"[{ec}]{effort}[/]")

        con.print(roadmap_table)

    con.print()
