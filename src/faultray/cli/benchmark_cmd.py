# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI commands for Industry Resilience Benchmarking."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import app, console, _load_graph_for_analysis, DEFAULT_MODEL_PATH

if TYPE_CHECKING:
    from faultray.model.graph import InfraGraph
    from faultray.simulator.benchmarking import BenchmarkEngine


@app.command(name="benchmark")
def benchmark(
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path"),
    yaml_file: Path | None = typer.Option(None, "--yaml", "-y", help="YAML model file"),
    industry: str | None = typer.Option(None, "--industry", "-i", help="Industry to benchmark against"),
    all_industries: bool = typer.Option(False, "--all-industries", "-a", help="Compare across all industries"),
    list_flag: bool = typer.Option(False, "--list", "-l", help="List available industries"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Benchmark infrastructure resilience against industry peers.

    Compare your infrastructure's resilience score, redundancy, isolation,
    recovery, and diversity against anonymized industry benchmarks.

    Examples:
        # Benchmark against fintech industry
        faultray benchmark --yaml infra.yaml --industry fintech

        # Compare across all industries
        faultray benchmark --yaml infra.yaml --all-industries

        # List available industries
        faultray benchmark --list

        # JSON output for CI/CD integration
        faultray benchmark --yaml infra.yaml --industry saas --json
    """
    from faultray.simulator.benchmarking import BenchmarkEngine

    engine = BenchmarkEngine()

    if list_flag:
        _list_industries(engine, json_output)
        return

    # Load graph for benchmarking
    graph = _load_graph_for_analysis(model, yaml_file)

    # Normalize aliases: "banking" is an alias for "fintech"
    _INDUSTRY_ALIASES: dict[str, str] = {
        "banking": "fintech",
    }
    if industry:
        industry = _INDUSTRY_ALIASES.get(industry, industry)

    if all_industries:
        _compare_all_industries(engine, graph, json_output)
    elif industry:
        _benchmark_single(engine, graph, industry, json_output)
    else:
        console.print("[red]Error: specify --industry <name> or --all-industries[/]")
        console.print("[dim]Use --list to see available industries.[/]")
        raise typer.Exit(1)


def _list_industries(engine: "BenchmarkEngine", json_output: bool) -> None:
    """List available industry profiles."""
    profiles = engine.list_industries()

    if json_output:
        data = [
            {
                "industry": p.industry,
                "display_name": p.display_name,
                "avg_score": p.avg_resilience_score,
                "median_score": p.median_resilience_score,
                "sample_size": p.sample_size,
                "regulatory": p.regulatory_requirements,
            }
            for p in profiles
        ]
        console.print_json(data=data)
        return

    table = Table(title="Available Industry Benchmarks", show_header=True)
    table.add_column("Industry", style="cyan", width=20)
    table.add_column("Display Name", width=28)
    table.add_column("Avg Score", justify="right", width=10)
    table.add_column("Median", justify="right", width=8)
    table.add_column("Sample", justify="right", width=8)
    table.add_column("Regulatory", width=30)

    for p in sorted(profiles, key=lambda x: x.avg_resilience_score, reverse=True):
        table.add_row(
            p.industry,
            p.display_name,
            f"{p.avg_resilience_score:.1f}",
            f"{p.median_resilience_score:.1f}",
            str(p.sample_size),
            ", ".join(p.regulatory_requirements[:3]),
        )

    console.print()
    console.print(table)
    console.print()


def _benchmark_single(
    engine: "BenchmarkEngine",
    graph: "InfraGraph",
    industry: str,
    json_output: bool,
) -> None:
    """Benchmark against a single industry."""
    try:
        result = engine.benchmark(graph, industry)
    except ValueError as exc:
        console.print(f"[red]Error: {exc}[/]")
        raise typer.Exit(1)

    if json_output:
        radar_data = engine.generate_radar_chart_data(result)
        data = {
            "your_score": result.your_score,
            "industry": result.industry,
            "percentile": result.percentile,
            "rank": result.rank_description,
            "comparison": {
                k: {"yours": v[0], "industry_avg": v[1]}
                for k, v in result.comparison.items()
            },
            "strengths": result.strengths,
            "weaknesses": result.weaknesses,
            "improvement_priority": result.improvement_priority,
            "radar_chart": radar_data,
        }
        console.print_json(data=data)
        return

    profile = engine.get_industry_profile(industry)

    # Score color
    score = result.your_score
    if score >= 80:
        score_color = "green"
    elif score >= 60:
        score_color = "yellow"
    else:
        score_color = "red"

    # Percentile color
    pct = result.percentile
    if pct >= 75:
        pct_color = "green"
    elif pct >= 50:
        pct_color = "yellow"
    else:
        pct_color = "red"

    # Summary panel
    summary = (
        f"[bold]Your Score:[/] [{score_color}]{score:.1f}[/]\n"
        f"[bold]Industry:[/] {profile.display_name} (n={profile.sample_size})\n"
        f"[bold]Percentile:[/] [{pct_color}]{pct:.0f}th percentile[/] ({result.rank_description})\n"
        f"[bold]Industry Avg:[/] {profile.avg_resilience_score:.1f}  |  "
        f"[bold]Median:[/] {profile.median_resilience_score:.1f}  |  "
        f"[bold]P90:[/] {profile.p90_score:.1f}"
    )

    console.print()
    console.print(Panel(
        summary,
        title=f"[bold]Benchmark: {profile.display_name}[/]",
        border_style=score_color,
    ))

    # Comparison chart
    console.print()
    console.print(Panel(
        result.peer_comparison_chart,
        title="[bold]Metric Comparison[/]",
        border_style="blue",
    ))

    # Strengths and weaknesses
    if result.strengths:
        console.print("\n[bold green]Strengths:[/]")
        for s in result.strengths:
            console.print(f"  [green]+[/] {s}")

    if result.weaknesses:
        console.print("\n[bold red]Weaknesses:[/]")
        for w in result.weaknesses:
            console.print(f"  [red]-[/] {w}")

    # Improvement priorities
    if result.improvement_priority:
        console.print("\n[bold]Improvement Priority:[/]")
        for i, item in enumerate(result.improvement_priority, 1):
            console.print(f"  {i}. {item}")

    # Common industry weaknesses
    if profile.common_weaknesses:
        console.print(f"\n[bold]Common {profile.display_name} Weaknesses:[/]")
        for w in profile.common_weaknesses:
            console.print(f"  [dim]-[/] {w}")

    # Regulatory requirements
    if profile.regulatory_requirements:
        console.print(f"\n[bold]Regulatory Requirements:[/] {', '.join(profile.regulatory_requirements)}")

    console.print()


def _compare_all_industries(
    engine: "BenchmarkEngine",
    graph: "InfraGraph",
    json_output: bool,
) -> None:
    """Compare against all industries."""
    results = engine.compare_across_industries(graph)

    if json_output:
        data = {}
        for industry, result in results.items():
            data[industry] = {
                "your_score": result.your_score,
                "percentile": result.percentile,
                "rank": result.rank_description,
                "strengths": len(result.strengths),
                "weaknesses": len(result.weaknesses),
            }
        console.print_json(data=data)
        return

    table = Table(title="Cross-Industry Benchmark", show_header=True)
    table.add_column("Industry", style="cyan", width=22)
    table.add_column("Your Score", justify="right", width=12)
    table.add_column("Avg Score", justify="right", width=10)
    table.add_column("Percentile", justify="right", width=12)
    table.add_column("Rank", width=18)
    table.add_column("Strengths", justify="right", width=10)
    table.add_column("Weaknesses", justify="right", width=10)

    # Sort by percentile descending (best fit first)
    sorted_results = sorted(
        results.items(),
        key=lambda x: x[1].percentile,
        reverse=True,
    )

    for industry, result in sorted_results:
        profile = engine.get_industry_profile(industry)

        # Percentile color
        pct = result.percentile
        if pct >= 75:
            pct_color = "green"
        elif pct >= 50:
            pct_color = "yellow"
        else:
            pct_color = "red"

        # Score color
        s = result.your_score
        if s >= 80:
            s_color = "green"
        elif s >= 60:
            s_color = "yellow"
        else:
            s_color = "red"

        table.add_row(
            profile.display_name,
            f"[{s_color}]{s:.1f}[/]",
            f"{profile.avg_resilience_score:.1f}",
            f"[{pct_color}]{pct:.0f}th[/]",
            result.rank_description,
            f"[green]{len(result.strengths)}[/]",
            f"[red]{len(result.weaknesses)}[/]",
        )

    console.print()
    console.print(table)
    console.print()
