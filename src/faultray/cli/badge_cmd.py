# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Generate resilience score badge for README."""

from __future__ import annotations

from pathlib import Path

import typer

from faultray.cli.main import _load_graph_for_analysis, app, console


def _color(score: int) -> str:
    """Map a 0-100 resilience score to a shields.io named color."""
    if score >= 80:
        return "brightgreen"
    if score >= 60:
        return "green"
    if score >= 40:
        return "yellow"
    if score >= 20:
        return "orange"
    return "red"


def _badge_url(score: int, label: str = "resilience") -> str:
    """Build a shields.io static badge URL for the given score."""
    color = _color(score)
    return f"https://img.shields.io/badge/{label}-{score}%2F100-{color}"


@app.command("badge")
def badge(
    yaml_file: Path = typer.Argument(..., help="Infrastructure YAML or JSON model file"),
    markdown: bool = typer.Option(True, "--markdown/--url", help="Output as markdown (default) or raw URL"),
    label: str = typer.Option("resilience", "--label", "-l", help="Badge label text"),
) -> None:
    """Generate a resilience score badge for your README.

    Loads the infrastructure model, computes the resilience score, and prints
    a shields.io badge URL (or markdown snippet) that you can paste into your
    README.

    Examples:
        faultray badge infra.yaml
        faultray badge infra.yaml --url
        faultray badge infra.yaml --label "infra score"
    """
    try:
        graph = _load_graph_for_analysis(yaml_file, yaml_file)
    except (ValueError, RuntimeError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from exc
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to load infrastructure: {exc}[/]")
        raise typer.Exit(1) from exc
    score = int(round(graph.resilience_score()))
    url = _badge_url(score, label)

    if markdown:
        console.print(
            f"[![Resilience Score]({url})](https://github.com/mattyopon/faultray)"
        )
        console.print()
        console.print("[dim]Copy the line above into your README.md[/dim]")
    else:
        console.print(url)
