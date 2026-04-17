# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI commands for Incident Post-Mortem generation."""

from __future__ import annotations

import json as json_mod
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console
from faultray.reporter.postmortem_generator import PostMortemGenerator
from faultray.simulator.engine import SimulationEngine


@app.command("postmortem-generate")
def postmortem_generate(
    yaml_file: Path = typer.Argument(..., help="Infrastructure YAML or JSON file"),
    output: Path = typer.Option(
        Path("./postmortems"),
        "--output", "-o",
        help="Output directory for generated post-mortems",
    ),
    fmt: str = typer.Option(
        "md",
        "--format", "-f",
        help="Output format: md or html",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output summary as JSON (does not write files)",
    ),
) -> None:
    """Generate incident post-mortem documents from simulation results.

    Runs the full chaos simulation and auto-generates blameless post-mortem
    documents for each critical or warning scenario. Each post-mortem follows
    the industry-standard format with timeline, root cause analysis,
    action items, and lessons learned.

    Examples:
        # Generate post-mortems in markdown (default)
        faultray postmortem-generate infra.yaml

        # Generate in HTML format
        faultray postmortem-generate infra.yaml --format html

        # Custom output directory
        faultray postmortem-generate infra.yaml --output ./reports/postmortems

        # JSON summary (no files written)
        faultray postmortem-generate infra.yaml --json
    """
    if fmt not in ("md", "html"):
        console.print(f"[red]Invalid format: {fmt}. Use 'md' or 'html'.[/]")
        raise typer.Exit(1)

    graph = _load_graph_for_analysis(
        model=Path("faultray-model.json"),
        yaml_file=yaml_file,
    )

    if not json_output:
        console.print(f"[cyan]Running simulation on {len(graph.components)} components...[/]")

    # Run simulation
    engine = SimulationEngine(graph)
    sim_report = engine.run_all_defaults(include_feed=False, include_plugins=False)

    # Generate post-mortems
    generator = PostMortemGenerator()
    library = generator.generate(graph, sim_report)

    if json_output:
        output_data = {
            "total_postmortems": len(library.postmortems),
            "critical_postmortems": library.critical_postmortems,
            "total_action_items": library.total_action_items,
            "common_themes": library.common_themes,
            "postmortems": [
                {
                    "incident_id": pm.incident_id,
                    "title": pm.title,
                    "severity": pm.severity,
                    "blast_radius": pm.blast_radius,
                    "affected_components": pm.affected_components,
                    "action_items_count": len(pm.action_items),
                    "duration_estimate": pm.duration_estimate,
                }
                for pm in library.postmortems
            ],
        }
        console.print_json(json_mod.dumps(output_data, indent=2))
        return

    if not library.postmortems:
        console.print("[green]No critical or warning scenarios found. No post-mortems to generate.[/]")
        return

    # Export files
    paths = generator.export_library(library, output, fmt=fmt)

    console.print()
    console.print(Panel(
        f"[bold]Post-Mortems Generated:[/] {len(library.postmortems)}\n"
        f"[bold]Critical (SEV1/SEV2):[/] {library.critical_postmortems}\n"
        f"[bold]Total Action Items:[/] {library.total_action_items}\n"
        f"[bold]Output Directory:[/] {output}\n"
        f"[bold]Files Written:[/] {len(paths)}",
        title="[bold]Post-Mortem Generation Complete[/]",
        border_style="cyan",
    ))

    if library.common_themes:
        console.print("\n[bold]Common Themes:[/]")
        for theme in library.common_themes:
            console.print(f"  - {theme}")

    # Show file list
    console.print("\n[bold]Generated Files:[/]")
    for p in paths:
        console.print(f"  {p}")

    console.print()


@app.command("postmortem-list")
def postmortem_list(
    yaml_file: Path = typer.Argument(..., help="Infrastructure YAML or JSON file"),
) -> None:
    """Preview what post-mortems would be generated.

    Runs a simulation and shows a summary of which scenarios would
    produce post-mortem documents, without writing any files.

    Examples:
        faultray postmortem-list infra.yaml
    """
    graph = _load_graph_for_analysis(
        model=Path("faultray-model.json"),
        yaml_file=yaml_file,
    )

    console.print(f"[cyan]Running simulation on {len(graph.components)} components...[/]")

    engine = SimulationEngine(graph)
    sim_report = engine.run_all_defaults(include_feed=False, include_plugins=False)

    generator = PostMortemGenerator()
    library = generator.generate(graph, sim_report)

    if not library.postmortems:
        console.print("[green]No critical or warning scenarios. No post-mortems would be generated.[/]")
        return

    table = Table(title="Post-Mortems Preview", show_header=True)
    table.add_column("Incident ID", style="cyan", width=14)
    table.add_column("Severity", width=8, justify="center")
    table.add_column("Title", width=50)
    table.add_column("Blast", width=7, justify="right")
    table.add_column("Actions", width=8, justify="right")

    sev_colors = {"SEV1": "bold red", "SEV2": "red", "SEV3": "yellow", "SEV4": "green"}

    for pm in library.postmortems:
        sc = sev_colors.get(pm.severity, "white")
        table.add_row(
            pm.incident_id,
            f"[{sc}]{pm.severity}[/]",
            pm.title[:50],
            str(pm.blast_radius),
            str(len(pm.action_items)),
        )

    console.print()
    console.print(table)
    console.print(
        f"\n[dim]Total: {len(library.postmortems)} post-mortems, "
        f"{library.total_action_items} action items[/]"
    )
    console.print()


@app.command("postmortem-summary")
def postmortem_summary(
    yaml_file: Path = typer.Argument(..., help="Infrastructure YAML or JSON file"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show action items summary from simulated post-mortems.

    Aggregates all action items across post-mortems, grouped by priority,
    showing the most critical improvements needed.

    Examples:
        faultray postmortem-summary infra.yaml
        faultray postmortem-summary infra.yaml --json
    """
    graph = _load_graph_for_analysis(
        model=Path("faultray-model.json"),
        yaml_file=yaml_file,
    )

    if not json_output:
        console.print("[cyan]Running simulation and generating post-mortems...[/]")

    engine = SimulationEngine(graph)
    sim_report = engine.run_all_defaults(include_feed=False, include_plugins=False)

    generator = PostMortemGenerator()
    library = generator.generate(graph, sim_report)

    if json_output:
        all_items = [
            {
                "id": ai.id,
                "description": ai.description,
                "owner": ai.owner,
                "priority": ai.priority,
                "category": ai.category,
                "due_date": ai.due_date,
                "from_incident": pm.incident_id,
            }
            for pm in library.postmortems
            for ai in pm.action_items
        ]
        output = {
            "total_postmortems": len(library.postmortems),
            "total_action_items": len(all_items),
            "action_items_by_priority": {
                p: [ai for ai in all_items if ai["priority"] == p]
                for p in ("P0", "P1", "P2", "P3")
            },
            "common_themes": library.common_themes,
        }
        console.print_json(json_mod.dumps(output, indent=2))
        return

    if not library.postmortems:
        console.print("[green]No post-mortems generated. Infrastructure looks resilient.[/]")
        return

    # Collect all action items
    all_items = [
        (pm, ai) for pm in library.postmortems for ai in pm.action_items
    ]

    # Summary panel
    console.print()
    console.print(Panel(
        f"[bold]Post-Mortems Analyzed:[/] {len(library.postmortems)}\n"
        f"[bold]Total Action Items:[/] {len(all_items)}\n"
        f"[bold]P0 (Critical):[/] {sum(1 for _, ai in all_items if ai.priority == 'P0')}\n"
        f"[bold]P1 (High):[/] {sum(1 for _, ai in all_items if ai.priority == 'P1')}\n"
        f"[bold]P2 (Medium):[/] {sum(1 for _, ai in all_items if ai.priority == 'P2')}\n"
        f"[bold]P3 (Low):[/] {sum(1 for _, ai in all_items if ai.priority == 'P3')}",
        title="[bold]Action Items Summary[/]",
        border_style="cyan",
    ))

    # Action items table
    for priority, color in [("P0", "bold red"), ("P1", "red"), ("P2", "yellow"), ("P3", "green")]:
        p_items = [(pm, ai) for pm, ai in all_items if ai.priority == priority]
        if not p_items:
            continue

        table = Table(title=f"{priority} Action Items ({len(p_items)})", show_header=True)
        table.add_column("ID", style="cyan", width=16)
        table.add_column("Description", width=45)
        table.add_column("Owner", width=16)
        table.add_column("Category", width=12)
        table.add_column("Due", width=10)

        for pm, ai in p_items:
            table.add_row(
                ai.id,
                ai.description[:45],
                ai.owner,
                ai.category,
                ai.due_date,
            )

        console.print()
        console.print(table)

    if library.common_themes:
        console.print()
        console.print("[bold]Common Themes:[/]")
        for theme in library.common_themes:
            console.print(f"  - {theme}")

    console.print()
