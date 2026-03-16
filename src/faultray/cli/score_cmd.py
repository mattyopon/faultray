"""CLI command for Resilience Score Decomposition."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console


@app.command("score-explain")
def score_explain(
    model: Path = typer.Argument(..., help="Infrastructure model file (YAML or JSON)"),
    what_if: str = typer.Option(
        None, "--what-if",
        help="What-if analysis: component_id:fix (e.g. web-api:add-replica)",
    ),
    improvements_only: bool = typer.Option(
        False, "--improvements",
        help="Show only top improvement suggestions",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Resilience Score Decomposition — explain what drives the score.

    Shows exactly what contributes to the resilience score and what would
    change it, like a credit score breakdown.

    Examples:
        # Full score decomposition
        faultray score-explain infra.yaml

        # What-if analysis
        faultray score-explain infra.yaml --what-if web-api:add-replica

        # Show top improvements only
        faultray score-explain infra.yaml --improvements

        # JSON output
        faultray score-explain infra.yaml --json
    """
    from faultray.simulator.score_decomposition import ScoreDecomposer

    graph = _load_graph_for_analysis(model, model)
    decomposer = ScoreDecomposer()
    decomposition = decomposer.decompose(graph)

    # Handle what-if first if requested
    if what_if:
        parts = what_if.split(":", 1)
        if len(parts) != 2:
            console.print("[red]Invalid --what-if format. Use component_id:fix[/]")
            console.print("[dim]Supported fixes: add-replica, enable-failover, enable-autoscaling, reduce-utilization[/]")
            raise typer.Exit(1)

        component_id, fix = parts
        comp = graph.get_component(component_id)
        if comp is None:
            console.print(f"[red]Component '{component_id}' not found[/]")
            raise typer.Exit(1)

        current_score = decomposition.total_score
        new_score = decomposer.what_if_fix(graph, component_id, fix)
        delta = new_score - current_score

        if delta > 0:
            delta_color = "green"
            delta_sign = "+"
        elif delta < 0:
            delta_color = "red"
            delta_sign = ""
        else:
            delta_color = "yellow"
            delta_sign = ""

        console.print()
        console.print(Panel(
            f"[bold]What-If Analysis:[/] {fix} on {component_id}\n\n"
            f"Current Score: [bold]{current_score:.1f}[/]\n"
            f"New Score:     [bold]{new_score:.1f}[/]\n"
            f"Delta:         [{delta_color}]{delta_sign}{delta:.1f} points[/]",
            title="[bold]What-If Result[/]",
            border_style=delta_color,
        ))
        return

    if json_output:
        console.print_json(data=decomposition.to_dict())
        return

    # Score and grade display
    score = decomposition.total_score
    if score >= 80:
        score_color = "green"
    elif score >= 60:
        score_color = "yellow"
    else:
        score_color = "red"

    console.print()
    score_display = (
        f"[bold]Resilience Score:[/] [{score_color}]{score:.0f}/100[/]  "
        f"[bold]Grade:[/] [{score_color}]{decomposition.grade}[/]  "
        f"[bold]Percentile:[/] ~{decomposition.percentile_estimate:.0f}%\n\n"
        f"[bold]Base Score:[/] {decomposition.base_score:.0f}  "
        f"[bold]Total Penalties:[/] [red]-{decomposition.penalties_total:.1f}[/]"
    )
    console.print(Panel(score_display, title="[bold]Score Summary[/]", border_style=score_color))

    # Show improvements only if requested
    if improvements_only:
        if decomposition.improvements:
            table = Table(title="Top Improvement Suggestions", show_header=True)
            table.add_column("#", width=4)
            table.add_column("Action", width=22)
            table.add_column("Component", style="cyan", width=20)
            table.add_column("Impact", justify="right", width=10)
            table.add_column("Effort", width=10)
            table.add_column("Description", width=40)

            for i, imp in enumerate(decomposition.improvements[:10], 1):
                table.add_row(
                    str(i),
                    imp.action,
                    imp.component_id,
                    f"[green]+{imp.estimated_improvement:.1f}[/]",
                    imp.effort,
                    imp.description[:40],
                )

            console.print()
            console.print(table)
        else:
            console.print("\n[green]No improvement suggestions - infrastructure is well-configured.[/]")
        return

    # Full decomposition — Waterfall display
    console.print()
    console.print("[bold]Score Waterfall[/]")

    waterfall = decomposer.to_waterfall_data(decomposition)
    for entry in waterfall:
        name = entry["name"]
        value = entry["value"]
        running = entry["running_total"]
        category = entry["category"]

        if category == "base":
            bar_width = int(value / 2)
            bar = "[blue]" + "#" * bar_width + "[/]"
            console.print(f"  {name:<28} {bar} {value:.0f}")
        elif category == "penalty":
            bar_width = max(1, int(abs(value) / 2))
            bar = "[red]" + "-" * bar_width + "[/]"
            console.print(f"  {name:<28} {bar} {value:+.1f} (= {running:.1f})")
        elif category == "total":
            bar_width = int(value / 2)
            bar_color = "green" if value >= 80 else "yellow" if value >= 60 else "red"
            bar = f"[{bar_color}]" + "=" * bar_width + "[/]"
            console.print(f"  {name:<28} {bar} {value:.0f}")

    # Factor details
    penalties = [f for f in decomposition.factors if f.category == "penalty"]
    bonuses = [f for f in decomposition.factors if f.category in ("bonus", "neutral")]

    if penalties:
        console.print()
        table = Table(title="Penalty Factors", show_header=True)
        table.add_column("Factor", style="red", width=28)
        table.add_column("Points", justify="right", width=10)
        table.add_column("Description", width=50)
        table.add_column("Components", width=20)

        for f in penalties:
            comps = ", ".join(f.affected_components[:3])
            if len(f.affected_components) > 3:
                comps += f" (+{len(f.affected_components) - 3} more)"
            table.add_row(
                f.name,
                f"[red]{f.points:+.1f}[/]",
                f.description[:50],
                comps,
            )

        console.print(table)

    if bonuses:
        console.print()
        table = Table(title="Positive Factors", show_header=True)
        table.add_column("Factor", style="green", width=28)
        table.add_column("Description", width=60)

        for f in bonuses:
            table.add_row(f.name, f.description[:60])

        console.print(table)

    # Top improvements
    if decomposition.improvements:
        console.print()
        console.print("[bold]Top Improvements[/]")
        for i, imp in enumerate(decomposition.improvements[:5], 1):
            console.print(
                f"  {i}. [green]+{imp.estimated_improvement:.1f}[/] points: "
                f"{imp.action} on [cyan]{imp.component_id}[/] ({imp.effort} effort)"
            )
