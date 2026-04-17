# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI command for interactive HTML topology map generation.

Usage:
    faultray topology-map examples/demo-infra.yaml --output topology.html
    faultray topology-map examples/demo-infra.yaml
"""

from __future__ import annotations

from pathlib import Path

import typer

from faultray.cli.main import (
    DEFAULT_MODEL_PATH,
    _load_graph_for_analysis,
    app,
    console,
)


@app.command(name="topology-map")
def topology_map(
    model: Path = typer.Argument(
        ...,
        help="Infrastructure model file (YAML or JSON).",
    ),
    output: Path = typer.Option(
        Path("topology.html"),
        "--output",
        "-o",
        help="Output HTML file path (default: topology.html).",
    ),
) -> None:
    """Generate an interactive HTML topology map.

    Produces a standalone HTML file with a D3.js force-directed graph.
    Open the output file in any browser to explore your infrastructure:
    zoom, pan, hover for details, and search for components.

    \b
    Features:
    - Force-directed graph layout (auto-positions components)
    - Node color = component type, size = number of dependents
    - Edge color: requires=red, optional=yellow, async=gray
    - Hover to see name, type, replicas, owner, health
    - Zoom and pan with mouse/trackpad
    - Search box to filter and highlight components
    - Color legend for component types

    \b
    Examples:
        faultray topology-map examples/demo-infra.yaml
        faultray topology-map infra.yaml --output /tmp/map.html
        faultray topology-map model.json --output infra-topology.html
    """
    yaml_path = model if str(model).endswith((".yaml", ".yml")) else None
    json_path = model if yaml_path is None else None
    graph = _load_graph_for_analysis(json_path or DEFAULT_MODEL_PATH, yaml_path)

    if not graph.components:
        console.print("[red]No components found in the model.[/]")
        raise typer.Exit(1)

    from faultray.reporter.topology_html import generate_topology_html

    generate_topology_html(graph, output)

    edge_count = len(graph.all_dependency_edges())
    console.print(f"[green]Topology map written to:[/] {output}")
    console.print(f"  Components: {len(graph.components)}")
    console.print(f"  Edges:      {edge_count}")
    console.print("[dim]Open the file in your browser to explore.[/]")
