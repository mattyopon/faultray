# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Risk Heat Map CLI command."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import DEFAULT_MODEL_PATH, app, console


def _load_graph(model: Path):
    """Load an InfraGraph from a YAML or JSON model file."""
    if str(model).endswith((".yaml", ".yml")):
        from faultray.model.loader import load_yaml

        return load_yaml(model)
    else:
        from faultray.model.graph import InfraGraph

        return InfraGraph.load(model)


@app.command()
def heatmap(
    model: Path = typer.Option(
        DEFAULT_MODEL_PATH,
        "--model",
        "-m",
        help="Infrastructure model file (YAML or JSON)",
    ),
    hotspots_only: bool = typer.Option(
        False,
        "--hotspots",
        help="Show only the top hotspots",
    ),
    top_n: int = typer.Option(
        5,
        "--top",
        "-n",
        help="Number of hotspots to show",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output as JSON",
    ),
) -> None:
    """Show risk heat map of infrastructure components.

    Analyzes each component across multiple risk dimensions (blast radius,
    SPOF, utilization, dependency depth, recovery, security) and produces
    a color-coded risk heat map.

    Examples:
        faultray heatmap
        faultray heatmap --model infra.yaml
        faultray heatmap --hotspots
        faultray heatmap --json
        faultray heatmap --top 10
    """
    if not model.exists():
        console.print(f"[red]Model file not found: {model}[/]")
        raise typer.Exit(1)

    graph = _load_graph(model)

    from faultray.simulator.risk_heatmap import RiskHeatMapEngine

    engine = RiskHeatMapEngine()

    if hotspots_only:
        hotspots = engine.identify_hotspots(graph, top_n=top_n)
        if json_output:
            console.print_json(data=[h.to_dict() for h in hotspots])
            return
        _print_hotspots(hotspots)
        return

    data = engine.analyze(graph)

    if json_output:
        console.print_json(data=data.to_dict())
        return

    _print_heatmap(data)


def _risk_style(level: str) -> str:
    """Return Rich color style for a risk level."""
    return {
        "critical": "bold red",
        "high": "dark_orange",
        "medium": "yellow",
        "low": "green",
    }.get(level, "white")


def _risk_bar(score: float, width: int = 20) -> str:
    """Return a visual risk bar using Unicode blocks."""
    filled = int(score * width)
    empty = width - filled
    if score >= 0.75:
        color = "red"
    elif score >= 0.5:
        color = "dark_orange"
    elif score >= 0.25:
        color = "yellow"
    else:
        color = "green"
    bar = "\u2588" * filled + "\u2591" * empty
    return f"[{color}]{bar}[/] {score:.0%}"


def _print_heatmap(data) -> None:
    """Print the full heat map in the terminal."""
    # Overall summary
    overall_style = _risk_style(
        "critical" if data.overall_risk_score >= 0.75
        else "high" if data.overall_risk_score >= 0.5
        else "medium" if data.overall_risk_score >= 0.25
        else "low"
    )

    dist = data.risk_distribution
    summary = (
        f"[bold]Overall Risk Score:[/] [{overall_style}]{data.overall_risk_score:.1%}[/]\n"
        f"[red]\u25cf Critical: {dist.get('critical', 0)}[/]  "
        f"[dark_orange]\u25cf High: {dist.get('high', 0)}[/]  "
        f"[yellow]\u25cf Medium: {dist.get('medium', 0)}[/]  "
        f"[green]\u25cf Low: {dist.get('low', 0)}[/]"
    )

    console.print(Panel(
        summary,
        title="[bold]Risk Heat Map[/]",
        border_style="blue",
    ))

    # Component table
    table = Table(
        title="Component Risk Scores",
        show_lines=True,
        expand=True,
    )
    table.add_column("Component", style="bold", min_width=15)
    table.add_column("Type", min_width=10)
    table.add_column("Risk", min_width=8)
    table.add_column("Score", min_width=25)
    table.add_column("Blast", min_width=6, justify="right")
    table.add_column("SPOF", min_width=6, justify="right")
    table.add_column("Util", min_width=6, justify="right")
    table.add_column("Recovery", min_width=6, justify="right")
    table.add_column("Security", min_width=6, justify="right")

    from faultray.simulator.risk_heatmap import RiskDimension

    for p in data.components:
        style = _risk_style(p.risk_level)
        table.add_row(
            p.component_name,
            p.component_type,
            f"[{style}]{p.risk_level.upper()}[/]",
            _risk_bar(p.overall_risk),
            f"{p.risk_scores.get(RiskDimension.BLAST_RADIUS, 0):.0%}",
            f"{p.risk_scores.get(RiskDimension.SPOF, 0):.0%}",
            f"{p.risk_scores.get(RiskDimension.UTILIZATION, 0):.0%}",
            f"{p.risk_scores.get(RiskDimension.RECOVERY, 0):.0%}",
            f"{p.risk_scores.get(RiskDimension.SECURITY, 0):.0%}",
        )

    console.print(table)

    # Zones
    if data.zones:
        console.print("\n[bold]Risk Zones[/]")
        zone_table = Table(show_lines=True)
        zone_table.add_column("Zone", style="bold")
        zone_table.add_column("Components", justify="right")
        zone_table.add_column("Zone Risk", min_width=25)
        zone_table.add_column("Description")

        for zone in data.zones:
            zone_table.add_row(
                zone.name,
                str(len(zone.components)),
                _risk_bar(zone.zone_risk),
                zone.description,
            )
        console.print(zone_table)

    # Hotspots
    if data.hotspots:
        _print_hotspots(data.hotspots)


def _print_hotspots(hotspots) -> None:
    """Print the hotspots panel."""
    if not hotspots:
        console.print("[dim]No hotspots identified.[/]")
        return

    lines: list[str] = []
    for i, h in enumerate(hotspots, 1):
        style = _risk_style(h.risk_level)
        lines.append(
            f"  {i}. [{style}]{h.component_name}[/] "
            f"([dim]{h.component_type}[/]) "
            f"- [{style}]{h.overall_risk:.0%} {h.risk_level.upper()}[/]"
        )
        if h.risk_factors:
            for factor in h.risk_factors[:3]:
                lines.append(f"     [dim]\u2514 {factor}[/]")

    console.print(Panel(
        "\n".join(lines),
        title="[bold red]Hotspots[/]",
        border_style="red",
    ))
