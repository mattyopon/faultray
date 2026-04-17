# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI command for Attack Surface Analysis."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console


@app.command("attack-surface")
def attack_surface(
    model: Path = typer.Argument(..., help="Infrastructure model file (YAML or JSON)"),
    entry_points: bool = typer.Option(False, "--entry-points", help="Show only entry points"),
    lateral_paths: bool = typer.Option(False, "--lateral-paths", help="Show lateral movement paths"),
    targets: bool = typer.Option(False, "--targets", help="Show high-value targets"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Attack Surface Analysis — map entry points, lateral paths, and targets.

    Analyses infrastructure from an attacker's perspective to identify
    external entry points, lateral movement paths, and high-value targets.

    Examples:
        # Full analysis
        faultray attack-surface infra.yaml

        # Show only entry points
        faultray attack-surface infra.yaml --entry-points

        # JSON output
        faultray attack-surface infra.yaml --json
    """
    from faultray.simulator.attack_surface import AttackSurfaceAnalyzer

    graph = _load_graph_for_analysis(model, model)
    analyzer = AttackSurfaceAnalyzer()
    report = analyzer.analyze(graph)

    if json_output:
        console.print_json(data=report.to_dict())
        return

    show_all = not (entry_points or lateral_paths or targets)

    # Summary panel
    score = report.total_attack_surface_score
    if score >= 70:
        score_color = "red"
        score_label = "High Risk"
    elif score >= 40:
        score_color = "yellow"
        score_label = "Moderate Risk"
    else:
        score_color = "green"
        score_label = "Low Risk"

    summary = (
        f"[bold]Attack Surface Score:[/] [{score_color}]{score:.1f}/100[/] ({score_label}) "
        f"[dim](lower is better)[/]\n"
        f"[bold]External Exposure:[/] {report.external_exposure} internet-facing component(s)\n"
        f"[bold]Entry Points:[/] {len(report.entry_points)}\n"
        f"[bold]Lateral Paths:[/] {len(report.lateral_paths)}\n"
        f"[bold]High-Value Targets:[/] {len(report.high_value_targets)}\n"
        f"[bold]Attack Chains:[/] {len(report.attack_chains)}\n"
        f"[bold]Avg Defense Depth:[/] {report.avg_defense_depth:.1f}"
    )
    console.print()
    console.print(Panel(
        summary,
        title="[bold]Attack Surface Report[/]",
        border_style=score_color,
    ))

    # Entry Points
    if show_all or entry_points:
        if report.entry_points:
            table = Table(title="Entry Points", show_header=True)
            table.add_column("Component", style="cyan", width=20)
            table.add_column("Exposure", width=16)
            table.add_column("Protocol", width=10)
            table.add_column("Attack Vectors", width=36)
            table.add_column("Defense", justify="right", width=8)

            for ep in report.entry_points:
                defense_color = "green" if ep.defense_score >= 0.6 else "yellow" if ep.defense_score >= 0.3 else "red"
                table.add_row(
                    ep.component_name,
                    ep.exposure_type,
                    ep.protocol,
                    ", ".join(ep.attack_vectors[:3]),
                    f"[{defense_color}]{ep.defense_score:.0%}[/]",
                )

            console.print()
            console.print(table)

    # Lateral Movement Paths
    if show_all or lateral_paths:
        if report.lateral_paths:
            # Show top 15 paths sorted by difficulty (easiest first)
            difficulty_order = {"trivial": 0, "easy": 1, "moderate": 2, "hard": 3, "very_hard": 4}
            sorted_paths = sorted(
                report.lateral_paths,
                key=lambda p: (difficulty_order.get(p.difficulty, 99), -p.hops),
            )[:15]

            table = Table(title="Lateral Movement Paths (top 15 by ease)", show_header=True)
            table.add_column("Source", style="cyan", width=16)
            table.add_column("Target", width=16)
            table.add_column("Hops", justify="right", width=6)
            table.add_column("Barriers", justify="right", width=10)
            table.add_column("Difficulty", width=12)

            diff_colors = {
                "trivial": "bold red",
                "easy": "red",
                "moderate": "yellow",
                "hard": "green",
                "very_hard": "bold green",
            }

            for lp in sorted_paths:
                source_comp = graph.get_component(lp.source)
                target_comp = graph.get_component(lp.target)
                color = diff_colors.get(lp.difficulty, "white")
                table.add_row(
                    source_comp.name if source_comp else lp.source,
                    target_comp.name if target_comp else lp.target,
                    str(lp.hops),
                    str(lp.defense_barriers),
                    f"[{color}]{lp.difficulty.upper()}[/]",
                )

            console.print()
            console.print(table)

    # High-Value Targets
    if show_all or targets:
        if report.high_value_targets:
            table = Table(title="High-Value Targets", show_header=True)
            table.add_column("Component", style="cyan", width=20)
            table.add_column("Type", width=14)
            table.add_column("Risk Score", justify="right", width=12)
            table.add_column("Reachable From", justify="right", width=14)
            table.add_column("Min Hops", justify="right", width=10)
            table.add_column("Defense Depth", justify="right", width=14)

            for ht in sorted(report.high_value_targets, key=lambda t: -t.risk_score):
                risk_color = "red" if ht.risk_score >= 7 else "yellow" if ht.risk_score >= 4 else "green"
                table.add_row(
                    ht.component_name,
                    ht.value_type,
                    f"[{risk_color}]{ht.risk_score:.1f}/10[/]",
                    str(len(ht.reachable_from)),
                    str(ht.min_hops),
                    str(ht.defense_depth),
                )

            console.print()
            console.print(table)

    # Attack Chains
    if show_all and report.attack_chains:
        console.print()
        console.print("[bold]Attack Chains[/]")
        for chain in report.attack_chains:
            impact_color = {"critical": "red", "high": "yellow", "medium": "blue", "low": "green"}.get(chain.impact, "white")
            console.print(f"\n  [bold]{chain.name}[/] (likelihood: {chain.likelihood}, impact: [{impact_color}]{chain.impact}[/])")
            for i, (comp, action) in enumerate(chain.steps, 1):
                console.print(f"    {i}. [{comp}] {action}")
            if chain.mitigations:
                console.print(f"    [dim]Mitigations: {'; '.join(chain.mitigations[:2])}[/]")

    # Recommendations
    if show_all and report.recommendations:
        console.print()
        console.print("[bold]Recommendations[/]")
        for i, rec in enumerate(report.recommendations, 1):
            console.print(f"  {i}. {rec}")
