# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI command for Dependency Impact Scoring.

Usage:
    faultray deps score model.yaml --top 10
    faultray deps score model.yaml --json
    faultray deps heatmap model.yaml --json
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

deps_app = typer.Typer(
    name="deps",
    help="Analyze dependency impact scores.",
    no_args_is_help=True,
)
app.add_typer(deps_app, name="deps")


@deps_app.command()
def score(
    model: Path = typer.Argument(..., help="Infrastructure model file (YAML/JSON)"),
    top: int = typer.Option(10, "--top", "-n", help="Show top N most critical dependencies"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
    show_all: bool = typer.Option(False, "--all", "-a", help="Show all dependencies"),
) -> None:
    """Score every dependency edge by impact if broken.

    \b
    For each dependency:
    1. Simulates the target going down
    2. Counts cascade effects
    3. Estimates cost from cascade
    4. Scores impact on a 0-10 scale

    \b
    Examples:
        faultray deps score infra.yaml
        faultray deps score infra.yaml --top 5
        faultray deps score model.json --json
        faultray deps score infra.yaml --all
    """
    yaml_path = model if str(model).endswith((".yaml", ".yml")) else None
    json_path = model if yaml_path is None else None
    graph = _load_graph_for_analysis(
        json_path or DEFAULT_MODEL_PATH,
        yaml_path,
    )

    from faultray.simulator.dependency_scorer import DependencyScorer

    scorer = DependencyScorer(graph)

    if show_all:
        impacts = scorer.score_all()
    else:
        impacts = scorer.most_critical(n=top)

    if json_output:
        output = {
            "total_edges": len(scorer.score_all()),
            "showing": len(impacts),
            "dependencies": [
                {
                    "source": imp.source_id,
                    "target": imp.target_id,
                    "type": imp.dependency_type,
                    "impact_score": imp.impact_score,
                    "criticality": imp.criticality,
                    "cascade_depth": imp.cascade_depth,
                    "affected_count": imp.affected_component_count,
                    "estimated_cost": imp.estimated_cost_if_broken,
                    "affected_components": imp.affected_components,
                }
                for imp in impacts
            ],
        }
        console.print_json(data=output)
        return

    # Display results
    all_impacts = scorer.score_all()
    crit_count = sum(1 for i in all_impacts if i.criticality == "critical")
    high_count = sum(1 for i in all_impacts if i.criticality == "high")
    med_count = sum(1 for i in all_impacts if i.criticality == "medium")
    low_count = sum(1 for i in all_impacts if i.criticality == "low")

    summary = (
        f"[bold]Total Dependencies:[/] {len(all_impacts)}\n"
        f"[red]Critical:[/] {crit_count}  "
        f"[yellow]High:[/] {high_count}  "
        f"[dim yellow]Medium:[/] {med_count}  "
        f"[green]Low:[/] {low_count}"
    )

    console.print()
    console.print(Panel(
        summary,
        title="[bold cyan]Dependency Impact Analysis[/]",
        border_style="cyan",
    ))

    # Impact table
    table = Table(
        title=f"Top {len(impacts)} Dependencies by Impact",
        show_header=True,
    )
    table.add_column("#", width=4, justify="right")
    table.add_column("Source", width=16, style="cyan")
    table.add_column("->", width=3, justify="center")
    table.add_column("Target", width=16, style="green")
    table.add_column("Type", width=10)
    table.add_column("Score", width=6, justify="right")
    table.add_column("Level", width=10, justify="center")
    table.add_column("Cascade", width=8, justify="right")
    table.add_column("Affected", width=8, justify="right")
    table.add_column("Cost", width=12, justify="right")

    crit_colors = {
        "critical": "red",
        "high": "yellow",
        "medium": "dim yellow",
        "low": "green",
    }

    for idx, imp in enumerate(impacts, 1):
        color = crit_colors.get(imp.criticality, "white")
        table.add_row(
            str(idx),
            imp.source_id,
            "->",
            imp.target_id,
            imp.dependency_type,
            f"[{color}]{imp.impact_score:.1f}[/]",
            f"[{color}]{imp.criticality.upper()}[/]",
            f"depth={imp.cascade_depth}",
            str(imp.affected_component_count),
            f"${imp.estimated_cost_if_broken:,.0f}",
        )

    console.print()
    console.print(table)
    console.print()


@deps_app.command()
def heatmap(
    model: Path = typer.Argument(..., help="Infrastructure model file (YAML/JSON)"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Output JSON heatmap data"),
) -> None:
    """Generate dependency heatmap data for visualization.

    \b
    Outputs JSON data with edge scores and colors suitable for
    rendering in visualization tools.

    \b
    Examples:
        faultray deps heatmap infra.yaml
        faultray deps heatmap model.json --json
    """
    yaml_path = model if str(model).endswith((".yaml", ".yml")) else None
    json_path = model if yaml_path is None else None
    graph = _load_graph_for_analysis(
        json_path or DEFAULT_MODEL_PATH,
        yaml_path,
    )

    from faultray.simulator.dependency_scorer import DependencyScorer

    scorer = DependencyScorer(graph)
    data = scorer.dependency_heatmap_data()

    console.print_json(data=data)
