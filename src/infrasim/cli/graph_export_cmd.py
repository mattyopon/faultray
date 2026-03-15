"""CLI command for multi-format dependency graph export."""

from __future__ import annotations

from pathlib import Path

import typer

from infrasim.cli.main import (
    DEFAULT_MODEL_PATH,
    _load_graph_for_analysis,
    app,
    console,
)


@app.command(name="graph-export")
def graph_export(
    model: Path = typer.Argument(
        None,
        help="Model file path (JSON or YAML). Defaults to faultray-model.json.",
    ),
    fmt: str = typer.Option(
        "mermaid",
        "--format",
        "-f",
        help="Output format: mermaid, d2, graphviz, plantuml, ascii, json",
    ),
    output: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path. Prints to stdout if omitted.",
    ),
    direction: str = typer.Option(
        "TB",
        "--direction",
        "-d",
        help="Graph direction: TB (top-bottom), LR (left-right), BT, RL.",
    ),
    group_by_type: bool = typer.Option(
        False,
        "--group-by-type",
        help="Group components by type in subgraphs.",
    ),
    highlight_spof: bool = typer.Option(
        True,
        "--highlight-spof/--no-highlight-spof",
        help="Highlight single points of failure.",
    ),
    show_utilization: bool = typer.Option(
        False,
        "--show-utilization",
        help="Show component utilization percentages.",
    ),
    show_replicas: bool = typer.Option(
        True,
        "--show-replicas/--no-show-replicas",
        help="Show replica counts.",
    ),
    show_health: bool = typer.Option(
        True,
        "--show-health/--no-show-health",
        help="Show health status.",
    ),
    show_risk_level: bool = typer.Option(
        False,
        "--show-risk-level",
        help="Show risk level in JSON output.",
    ),
    dark_theme: bool = typer.Option(
        False,
        "--dark-theme",
        help="Use dark theme colours.",
    ),
    yaml_file: Path = typer.Option(
        None,
        "--yaml",
        "-y",
        help="Load from YAML infrastructure definition.",
    ),
) -> None:
    """Export infrastructure dependency graph as a diagram.

    Generate visual diagrams from the infrastructure model in formats
    suitable for documentation, presentations, and analysis tools.

    Examples:
        # Mermaid diagram to stdout
        faultray graph-export model.yaml --format mermaid

        # D2 diagram to file
        faultray graph-export model.yaml --format d2 --output infra.d2

        # Graphviz DOT
        faultray graph-export model.yaml --format graphviz --output infra.dot

        # PlantUML
        faultray graph-export model.yaml --format plantuml --output infra.puml

        # ASCII art to terminal
        faultray graph-export model.yaml --format ascii

        # JSON with utilisation data
        faultray graph-export model.yaml --format json --show-utilization

        # Grouped left-to-right diagram
        faultray graph-export model.yaml --format mermaid --direction LR --group-by-type
    """
    from infrasim.reporter.graph_exporter import DiagramFormat, DiagramOptions, GraphExporter

    FORMAT_MAP = {
        "mermaid": DiagramFormat.MERMAID,
        "d2": DiagramFormat.D2,
        "graphviz": DiagramFormat.GRAPHVIZ,
        "dot": DiagramFormat.GRAPHVIZ,
        "plantuml": DiagramFormat.PLANTUML,
        "puml": DiagramFormat.PLANTUML,
        "ascii": DiagramFormat.ASCII,
        "json": DiagramFormat.JSON,
    }

    diagram_format = FORMAT_MAP.get(fmt.lower())
    if diagram_format is None:
        console.print(f"[red]Unknown format: {fmt}[/]")
        console.print(
            f"[dim]Available formats: {', '.join(sorted(FORMAT_MAP.keys()))}[/]"
        )
        raise typer.Exit(1)

    if direction.upper() not in ("TB", "LR", "BT", "RL"):
        console.print(f"[red]Invalid direction: {direction}[/]")
        console.print("[dim]Valid directions: TB, LR, BT, RL[/]")
        raise typer.Exit(1)

    # Resolve model path
    if yaml_file is not None:
        resolved_model = DEFAULT_MODEL_PATH  # unused when yaml_file is set
        graph = _load_graph_for_analysis(resolved_model, yaml_file=yaml_file)
    elif model is not None:
        # Determine if it's YAML or JSON
        if model.suffix in (".yaml", ".yml"):
            graph = _load_graph_for_analysis(DEFAULT_MODEL_PATH, yaml_file=model)
        else:
            graph = _load_graph_for_analysis(model, yaml_file=None)
    else:
        graph = _load_graph_for_analysis(DEFAULT_MODEL_PATH, yaml_file=None)

    if not graph.components:
        console.print("[red]No components found in the model.[/]")
        raise typer.Exit(1)

    options = DiagramOptions(
        show_health=show_health,
        show_replicas=show_replicas,
        show_utilization=show_utilization,
        show_risk_level=show_risk_level,
        direction=direction.upper(),
        group_by_type=group_by_type,
        highlight_spof=highlight_spof,
        dark_theme=dark_theme,
    )

    exporter = GraphExporter()
    result = exporter.export(graph, diagram_format, options)

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(result, encoding="utf-8")
        console.print(f"[green]Wrote {diagram_format.value} diagram:[/] {output}")
        console.print(f"  Components: {len(graph.components)}")
        console.print(f"  Edges: {graph._graph.number_of_edges()}")
    else:
        console.print(result, end="")
