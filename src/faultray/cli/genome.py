# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Chaos Genome CLI commands — Infrastructure Resilience DNA Fingerprinting."""

from __future__ import annotations

import json as json_mod
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import app, console

genome_app = typer.Typer(
    name="genome",
    help="Chaos Genome — Infrastructure Resilience DNA Fingerprinting",
    no_args_is_help=True,
)
app.add_typer(genome_app, name="genome")


def _load_graph(yaml_file: Path) -> "InfraGraph":  # noqa: F821
    """Load an InfraGraph from a YAML file with user-friendly error handling."""
    from faultray.model.loader import load_yaml

    if not yaml_file.exists():
        console.print(f"[red]File not found: {yaml_file}[/]")
        raise typer.Exit(1)

    try:
        return load_yaml(yaml_file)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)


def _grade_color(grade: str) -> str:
    """Return a Rich color string for a resilience grade."""
    if grade.startswith("A"):
        return "green"
    if grade.startswith("B"):
        return "cyan"
    if grade.startswith("C"):
        return "yellow"
    if grade.startswith("D"):
        return "red"
    return "bold red"


def _affinity_color(score: float) -> str:
    """Return a Rich color for an affinity/severity score."""
    if score >= 0.7:
        return "red"
    if score >= 0.4:
        return "yellow"
    return "green"


def _print_genome_profile(
    genome: "GenomeProfile", con: Console  # noqa: F821
) -> None:
    """Print a complete genome profile using Rich formatting."""
    from faultray.simulator.chaos_genome import TRAIT_CATEGORIES

    grade_c = _grade_color(genome.resilience_grade)

    # Summary panel
    summary = (
        f"[bold]Infrastructure ID:[/] {genome.infrastructure_id}\n"
        f"[bold]Genome Hash:[/]       {genome.genome_hash[:24]}...\n"
        f"[bold]Archetype:[/]         {genome.structural_age}\n"
        f"[bold]Resilience Grade:[/]  [{grade_c}][bold]{genome.resilience_grade}[/][/]\n"
        f"[bold]Benchmark %ile:[/]    {genome.benchmark_percentile:.1f}\n"
        f"[bold]Timestamp:[/]         {genome.timestamp:%Y-%m-%d %H:%M:%S UTC}"
    )
    con.print()
    con.print(
        Panel(summary, title="[bold]Chaos Genome Profile[/]", border_style=grade_c)
    )

    # Trait table grouped by category
    for category in TRAIT_CATEGORIES:
        cat_traits = [t for t in genome.traits if t.category == category]
        if not cat_traits:
            continue

        table = Table(
            title=f"{category.title()} Traits",
            show_header=True,
            header_style="bold",
        )
        table.add_column("Trait", style="cyan", width=30)
        table.add_column("Value", justify="right", width=8)
        table.add_column("Bar", width=22)
        table.add_column("Percentile", justify="right", width=12)

        for trait in sorted(cat_traits, key=lambda t: t.name):
            # Value bar
            bar_len = int(trait.value * 20)
            bar = "[green]" + "#" * bar_len + "[/]" + "[dim]" + "-" * (20 - bar_len) + "[/]"

            pct_str = (
                f"{trait.percentile:.0f}%"
                if trait.percentile is not None
                else "[dim]--[/]"
            )
            table.add_row(
                trait.name.replace("_", " ").title(),
                f"{trait.value:.2f}",
                bar,
                pct_str,
            )

        con.print()
        con.print(table)

    # Weakness genes
    if genome.weakness_genes:
        con.print()
        con.print("[bold red]Weakness Genes Detected:[/]")
        for gene_name in genome.weakness_genes:
            con.print(f"  [red]x[/] {gene_name}")


@genome_app.command("analyze")
def genome_analyze(
    yaml_file: Path = typer.Argument(..., help="Infrastructure YAML file"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    industry: str = typer.Option(
        "",
        "--industry",
        "-i",
        help="Industry for percentile calculation (fintech/ecommerce/healthcare/saas/media/gaming)",
    ),
) -> None:
    """Analyze infrastructure and generate its resilience DNA profile.

    Examples:
        faultray genome analyze infra.yaml
        faultray genome analyze infra.yaml --json
        faultray genome analyze infra.yaml --industry fintech
    """
    import dataclasses

    from faultray.simulator.chaos_genome import ChaosGenomeEngine

    graph = _load_graph(yaml_file)
    console.print(
        f"[cyan]Analyzing genome for {len(graph.components)} components...[/]"
    )

    engine = ChaosGenomeEngine()
    genome = engine.analyze(graph)

    # If industry specified, compute percentiles
    if industry:
        try:
            bench = engine.benchmark(genome, industry)
            # Update trait percentiles
            for trait in genome.traits:
                if trait.name in bench.trait_percentiles:
                    trait.percentile = bench.trait_percentiles[trait.name]
            genome.benchmark_percentile = bench.overall_percentile
        except ValueError as exc:
            console.print(f"[yellow]Warning: {exc}[/]")

    if json_output:
        genome_dict = dataclasses.asdict(genome)
        genome_dict["timestamp"] = str(genome.timestamp)
        console.print_json(json_mod.dumps(genome_dict, indent=2, default=str))
    else:
        _print_genome_profile(genome, console)

        # Also show weakness details and failure affinities
        weaknesses = engine.find_weakness_genes(graph)
        if weaknesses:
            table = Table(
                title="Weakness Gene Details",
                show_header=True,
                header_style="bold",
            )
            table.add_column("Gene", style="cyan", width=28)
            table.add_column("Severity", justify="center", width=10)
            table.add_column("Description", width=50)
            table.add_column("Prevalence", justify="right", width=10)

            sev_colors = {
                "critical": "bold red",
                "high": "red",
                "medium": "yellow",
                "low": "green",
            }
            for w in weaknesses:
                color = sev_colors.get(w.severity, "white")
                table.add_row(
                    w.name,
                    f"[{color}]{w.severity.upper()}[/]",
                    w.description[:80]
                    + ("..." if len(w.description) > 80 else ""),
                    f"{w.prevalence:.0%}",
                )
            console.print()
            console.print(table)

        affinities = engine.predict_failure_affinity(genome)
        if affinities:
            table = Table(
                title="Failure Affinity Predictions",
                show_header=True,
                header_style="bold",
            )
            table.add_column("Failure Type", style="cyan", width=24)
            table.add_column("Affinity", justify="right", width=10)
            table.add_column("Bar", width=22)
            table.add_column("Contributing Genes", width=30)

            for a in affinities:
                color = _affinity_color(a.affinity_score)
                bar_len = int(a.affinity_score * 20)
                bar = (
                    f"[{color}]"
                    + "#" * bar_len
                    + "[/]"
                    + "[dim]"
                    + "-" * (20 - bar_len)
                    + "[/]"
                )
                genes_str = ", ".join(a.contributing_genes) if a.contributing_genes else "[dim]none[/]"
                table.add_row(
                    a.failure_type.replace("_", " ").title(),
                    f"[{color}]{a.affinity_score:.2f}[/]",
                    bar,
                    genes_str,
                )
            console.print()
            console.print(table)


@genome_app.command("compare")
def genome_compare(
    yaml1: Path = typer.Argument(..., help="First infrastructure YAML file"),
    yaml2: Path = typer.Argument(..., help="Second infrastructure YAML file"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Compare the resilience genomes of two infrastructures.

    Examples:
        faultray genome compare infra-v1.yaml infra-v2.yaml
        faultray genome compare prod.yaml staging.yaml --json
    """
    import dataclasses

    from faultray.simulator.chaos_genome import ChaosGenomeEngine

    graph_a = _load_graph(yaml1)
    graph_b = _load_graph(yaml2)

    console.print(
        f"[cyan]Comparing genomes: {yaml1.name} ({len(graph_a.components)} components) "
        f"vs {yaml2.name} ({len(graph_b.components)} components)...[/]"
    )

    engine = ChaosGenomeEngine()
    genome_a = engine.analyze(graph_a)
    genome_b = engine.analyze(graph_b)
    comparison = engine.compare(genome_a, genome_b)

    if json_output:
        result = {
            "genome_a": dataclasses.asdict(genome_a),
            "genome_b": dataclasses.asdict(genome_b),
            "comparison": dataclasses.asdict(comparison),
        }
        console.print_json(json_mod.dumps(result, indent=2, default=str))
        return

    # Summary panel
    sim_pct = comparison.similarity_score * 100
    if sim_pct >= 80:
        sim_color = "green"
        sim_label = "Very Similar"
    elif sim_pct >= 50:
        sim_color = "yellow"
        sim_label = "Moderately Similar"
    else:
        sim_color = "red"
        sim_label = "Divergent"

    grade_a_c = _grade_color(genome_a.resilience_grade)
    grade_b_c = _grade_color(genome_b.resilience_grade)

    summary = (
        f"[bold]Similarity:[/] [{sim_color}]{sim_pct:.1f}% ({sim_label})[/]\n\n"
        f"  [bold]{yaml1.name}[/]  Grade: [{grade_a_c}]{genome_a.resilience_grade}[/]  "
        f"Score: {genome_a.benchmark_percentile:.1f}  "
        f"Archetype: {genome_a.structural_age}\n"
        f"  [bold]{yaml2.name}[/]  Grade: [{grade_b_c}]{genome_b.resilience_grade}[/]  "
        f"Score: {genome_b.benchmark_percentile:.1f}  "
        f"Archetype: {genome_b.structural_age}"
    )
    console.print()
    console.print(
        Panel(summary, title="[bold]Genome Comparison[/]", border_style=sim_color)
    )

    # Divergent traits table
    if comparison.divergent_traits:
        table = Table(
            title="Divergent Traits (diff >= 0.10)",
            show_header=True,
            header_style="bold",
        )
        table.add_column("Trait", style="cyan", width=28)
        table.add_column(yaml1.name, justify="right", width=12)
        table.add_column(yaml2.name, justify="right", width=12)
        table.add_column("Delta", justify="right", width=10)
        table.add_column("Better", justify="center", width=12)

        for trait_name, val_a, val_b in sorted(
            comparison.divergent_traits, key=lambda x: abs(x[1] - x[2]), reverse=True
        ):
            delta = val_a - val_b
            delta_color = "green" if delta > 0 else "red"
            better = yaml1.name if delta > 0 else yaml2.name
            table.add_row(
                trait_name.replace("_", " ").title(),
                f"{val_a:.2f}",
                f"{val_b:.2f}",
                f"[{delta_color}]{delta:+.2f}[/]",
                better,
            )
        console.print()
        console.print(table)

    # Strengths
    if comparison.strengths_a:
        console.print(f"\n[bold green]Strengths of {yaml1.name}:[/]")
        for s in comparison.strengths_a:
            console.print(f"  [green]+[/] {s.replace('_', ' ').title()}")
    if comparison.strengths_b:
        console.print(f"\n[bold green]Strengths of {yaml2.name}:[/]")
        for s in comparison.strengths_b:
            console.print(f"  [green]+[/] {s.replace('_', ' ').title()}")


@genome_app.command("benchmark")
def genome_benchmark(
    yaml_file: Path = typer.Argument(..., help="Infrastructure YAML file"),
    industry: str = typer.Option(
        "saas",
        "--industry",
        "-i",
        help="Industry to benchmark against (fintech/ecommerce/healthcare/saas/media/gaming)",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Benchmark infrastructure genome against industry averages.

    Examples:
        faultray genome benchmark infra.yaml --industry fintech
        faultray genome benchmark infra.yaml --industry healthcare --json
    """
    import dataclasses

    from faultray.simulator.chaos_genome import ChaosGenomeEngine

    graph = _load_graph(yaml_file)
    console.print(
        f"[cyan]Benchmarking genome against {industry} industry...[/]"
    )

    engine = ChaosGenomeEngine()
    genome = engine.analyze(graph)

    try:
        result = engine.benchmark(genome, industry)
    except ValueError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)

    if json_output:
        result_dict = dataclasses.asdict(result)
        console.print_json(json_mod.dumps(result_dict, indent=2, default=str))
        return

    # Summary panel
    pct = result.overall_percentile
    if pct >= 70:
        pct_color = "green"
    elif pct >= 40:
        pct_color = "yellow"
    else:
        pct_color = "red"

    grade_c = _grade_color(genome.resilience_grade)

    summary = (
        f"[bold]Industry:[/]    {result.industry.title()}\n"
        f"[bold]Grade:[/]       [{grade_c}]{genome.resilience_grade}[/]\n"
        f"[bold]Percentile:[/]  [{pct_color}]{pct:.1f}%[/]\n"
        f"[bold]Above Avg:[/]   {len(result.above_average)} traits\n"
        f"[bold]Below Avg:[/]   {len(result.below_average)} traits"
    )
    console.print()
    console.print(
        Panel(
            summary,
            title=f"[bold]Benchmark vs {result.industry.title()}[/]",
            border_style=pct_color,
        )
    )

    # Trait percentile table
    table = Table(
        title="Trait Percentiles vs Industry",
        show_header=True,
        header_style="bold",
    )
    table.add_column("Trait", style="cyan", width=28)
    table.add_column("Your Value", justify="right", width=12)
    table.add_column("Industry Avg", justify="right", width=12)
    table.add_column("Percentile", justify="right", width=12)
    table.add_column("Status", justify="center", width=10)

    trait_map = {t.name: t.value for t in genome.traits}
    from faultray.simulator.chaos_genome import INDUSTRY_BENCHMARKS

    bench_data = INDUSTRY_BENCHMARKS.get(industry, {})

    for trait_name in sorted(result.trait_percentiles.keys()):
        actual = trait_map.get(trait_name, 0.0)
        bench_val = bench_data.get(trait_name, 0.0)
        pct_val = result.trait_percentiles[trait_name]

        if trait_name in result.above_average:
            status = "[green]ABOVE[/]"
        else:
            status = "[red]BELOW[/]"

        pct_c = "green" if pct_val >= 50 else "red"

        table.add_row(
            trait_name.replace("_", " ").title(),
            f"{actual:.2f}",
            f"{bench_val:.2f}",
            f"[{pct_c}]{pct_val:.0f}%[/]",
            status,
        )
    console.print()
    console.print(table)

    # Recommendations
    if result.recommendations:
        console.print()
        console.print("[bold]Recommendations:[/]")
        for i, rec in enumerate(result.recommendations, 1):
            console.print(f"  {i}. {rec}")


@genome_app.command("history")
def genome_history(
    directory: Path = typer.Option(
        Path(".genome-history"),
        "--dir",
        "-d",
        help="Directory containing genome history JSON files",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show genome evolution over time from saved snapshots.

    Examples:
        faultray genome history
        faultray genome history --dir .genome-history
    """
    import dataclasses
    from datetime import datetime, timezone

    from faultray.simulator.chaos_genome import (
        ChaosGenomeEngine,
        GenomeProfile,
        GenomeTrait,
    )

    if not directory.exists():
        console.print(
            f"[yellow]No genome history found at {directory}[/]\n"
            "[dim]Run 'faultray genome analyze' to create snapshots.[/]"
        )
        raise typer.Exit(0)

    # Load history files
    history_files = sorted(directory.glob("*.json"))
    if not history_files:
        console.print(
            f"[yellow]No genome snapshots found in {directory}[/]"
        )
        raise typer.Exit(0)

    profiles: list[GenomeProfile] = []
    for hf in history_files:
        try:
            data = json_mod.loads(hf.read_text())
            traits = [GenomeTrait(**t) for t in data.get("traits", [])]
            ts = data.get("timestamp", "")
            if isinstance(ts, str):
                try:
                    timestamp = datetime.fromisoformat(ts)
                except ValueError:
                    timestamp = datetime.now(timezone.utc)
            else:
                timestamp = datetime.now(timezone.utc)

            profile = GenomeProfile(
                infrastructure_id=data.get("infrastructure_id", ""),
                traits=traits,
                genome_hash=data.get("genome_hash", ""),
                resilience_grade=data.get("resilience_grade", "?"),
                structural_age=data.get("structural_age", "unknown"),
                weakness_genes=data.get("weakness_genes", []),
                evolution_vector=data.get("evolution_vector", {}),
                benchmark_percentile=data.get("benchmark_percentile", 0.0),
                timestamp=timestamp,
            )
            profiles.append(profile)
        except Exception as exc:
            console.print(f"[yellow]Skipping {hf.name}: {exc}[/]")

    if not profiles:
        console.print("[yellow]No valid genome snapshots found.[/]")
        raise typer.Exit(0)

    engine = ChaosGenomeEngine()
    report = engine.track_evolution(profiles)

    if json_output:
        report_dict = dataclasses.asdict(report)
        console.print_json(json_mod.dumps(report_dict, indent=2, default=str))
        return

    # Summary panel
    trend_colors = {"improving": "green", "stable": "yellow", "degrading": "red"}
    trend_color = trend_colors.get(report.overall_trend, "white")

    summary = (
        f"[bold]Snapshots:[/]   {report.snapshots}\n"
        f"[bold]Time Span:[/]   {report.time_span_days:.1f} days\n"
        f"[bold]Trend:[/]       [{trend_color}]{report.overall_trend.upper()}[/]\n"
        f"[bold]Grades:[/]      {' -> '.join(report.grade_history)}"
    )
    console.print()
    console.print(
        Panel(
            summary,
            title="[bold]Genome Evolution Report[/]",
            border_style=trend_color,
        )
    )

    # Trait trends table
    if report.trait_trends:
        table = Table(
            title="Trait Trends",
            show_header=True,
            header_style="bold",
        )
        table.add_column("Trait", style="cyan", width=28)
        table.add_column("Trend", justify="center", width=12)
        table.add_column("Delta", justify="right", width=10)

        for trait_name in sorted(report.trait_trends.keys()):
            trend = report.trait_trends[trait_name]
            delta = report.evolution_vector.get(trait_name, 0.0)
            t_color = trend_colors.get(trend, "white")
            d_color = "green" if delta > 0 else ("red" if delta < 0 else "dim")

            arrow = {"improving": "^", "stable": "-", "degrading": "v"}.get(trend, "?")
            table.add_row(
                trait_name.replace("_", " ").title(),
                f"[{t_color}]{arrow} {trend}[/]",
                f"[{d_color}]{delta:+.4f}[/]",
            )
        console.print()
        console.print(table)
