# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI command for Multi-Environment Resilience Comparison."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import app, console


@app.command("compare-envs")
def compare_envs(
    prod: Path = typer.Option(
        None, "--prod",
        help="Path to production YAML model.",
    ),
    staging: Path = typer.Option(
        None, "--staging",
        help="Path to staging YAML model.",
    ),
    dev: Path = typer.Option(
        None, "--dev",
        help="Path to dev YAML model.",
    ),
    parity: bool = typer.Option(
        False, "--parity",
        help="Only check if environments meet the same resilience standard.",
    ),
    tolerance: float = typer.Option(
        10.0, "--tolerance",
        help="Parity tolerance percentage (for --parity).",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON.",
    ),
) -> None:
    """Compare resilience across multiple infrastructure environments.

    Analyzes dev, staging, and production environments side-by-side to find
    resilience gaps, configuration drift, and parity issues.

    Examples:
        faultray compare-envs --prod prod.yaml --staging staging.yaml --dev dev.yaml
        faultray compare-envs --prod prod.yaml --staging staging.yaml --parity
        faultray compare-envs --prod prod.yaml --staging staging.yaml --json
    """
    from faultray.simulator.multi_env import MultiEnvAnalyzer

    # Build environment config dict
    env_configs: dict[str, Path] = {}
    if prod is not None:
        env_configs["production"] = prod
    if staging is not None:
        env_configs["staging"] = staging
    if dev is not None:
        env_configs["dev"] = dev

    if len(env_configs) < 2:
        console.print(
            "[red]At least 2 environments are required for comparison.[/]\n"
            "[dim]Use --prod, --staging, and/or --dev to specify YAML files.[/]"
        )
        raise typer.Exit(1)

    # Validate paths
    for name, path in env_configs.items():
        if not path.exists():
            console.print(f"[red]File not found for {name}: {path}[/]")
            raise typer.Exit(1)

    if not json_output:
        console.print(
            f"[cyan]Comparing {len(env_configs)} environments: "
            f"{', '.join(env_configs.keys())}...[/]"
        )

    analyzer = MultiEnvAnalyzer()

    # Parity-only mode
    if parity:
        is_parity = analyzer.check_parity(env_configs, tolerance=tolerance)
        if json_output:
            console.print_json(data={
                "parity": is_parity,
                "tolerance": tolerance,
                "environments": list(env_configs.keys()),
            })
            return

        if is_parity:
            console.print(
                f"\n[green]PARITY CHECK PASSED[/] "
                f"(tolerance: {tolerance}%)"
            )
        else:
            console.print(
                f"\n[red]PARITY CHECK FAILED[/] "
                f"(tolerance: {tolerance}%)"
            )
        return

    # Full comparison
    matrix = analyzer.compare(env_configs)

    if json_output:
        data = {
            "environments": [
                {
                    "name": ep.name,
                    "yaml_path": ep.yaml_path,
                    "resilience_score": ep.resilience_score,
                    "component_count": ep.component_count,
                    "spof_count": ep.spof_count,
                    "critical_findings": ep.critical_findings,
                    "availability_estimate": ep.availability_estimate,
                    "genome_hash": ep.genome_hash,
                }
                for ep in matrix.environments
            ],
            "weakest_environment": matrix.weakest_environment,
            "strongest_environment": matrix.strongest_environment,
            "parity_score": matrix.parity_score,
            "deltas": [
                {
                    "metric": d.metric,
                    "env_a": d.env_a_name,
                    "env_a_value": d.env_a_value,
                    "env_b": d.env_b_name,
                    "env_b_value": d.env_b_value,
                    "delta": d.delta,
                    "concern": d.concern,
                }
                for d in matrix.deltas
            ],
            "matrix_data": matrix.matrix_data,
            "recommendations": matrix.recommendations,
        }
        console.print_json(data=data)
        return

    # --- Rich output ---

    # 1. Overview Panel
    parity_color = (
        "green" if matrix.parity_score >= 80
        else "yellow" if matrix.parity_score >= 50
        else "red"
    )
    overview = (
        f"[bold]Environments:[/] {len(matrix.environments)}\n"
        f"[bold]Parity Score:[/] [{parity_color}]{matrix.parity_score:.1f}%[/]\n"
        f"[bold]Strongest:[/] [green]{matrix.strongest_environment}[/]\n"
        f"[bold]Weakest:[/] [red]{matrix.weakest_environment}[/]"
    )
    console.print()
    console.print(Panel(
        overview,
        title="[bold]Multi-Environment Comparison[/]",
        border_style=parity_color,
    ))

    # 2. Side-by-side comparison table
    comparison_table = Table(
        title="Environment Comparison",
        show_header=True,
        header_style="bold",
    )
    comparison_table.add_column("Metric", style="cyan", width=24)
    for ep in matrix.environments:
        comparison_table.add_column(ep.name.upper(), justify="right", width=14)

    # Add rows for key metrics
    metric_labels = {
        "resilience_score": "Resilience Score",
        "component_count": "Components",
        "spof_count": "SPOFs",
        "average_replicas": "Avg Replicas",
        "failover_coverage": "Failover %",
        "autoscaling_coverage": "Autoscaling %",
        "circuit_breaker_coverage": "Circuit Breaker %",
        "dependency_depth": "Max Depth",
        "blast_radius_avg": "Avg Blast Radius %",
    }

    for metric_key, label in metric_labels.items():
        row_values = [label]
        env_vals = []
        for ep in matrix.environments:
            val = matrix.matrix_data.get(ep.name, {}).get(metric_key, 0.0)
            env_vals.append(val)

        # Color based on relative values
        max_val = max(env_vals) if env_vals else 0
        min_val = min(env_vals) if env_vals else 0

        for val in env_vals:
            fmt = f"{val:.1f}"
            if metric_key in ("spof_count", "dependency_depth", "blast_radius_avg"):
                # Lower is better
                if val == min_val and max_val != min_val:
                    fmt = f"[green]{val:.1f}[/]"
                elif val == max_val and max_val != min_val:
                    fmt = f"[red]{val:.1f}[/]"
            else:
                # Higher is better
                if val == max_val and max_val != min_val:
                    fmt = f"[green]{val:.1f}[/]"
                elif val == min_val and max_val != min_val:
                    fmt = f"[red]{val:.1f}[/]"
            row_values.append(fmt)

        comparison_table.add_row(*row_values)

    # Add availability estimates
    avail_row = ["Availability Est."]
    for ep in matrix.environments:
        avail_row.append(f"{ep.availability_estimate:.2f}%")
    comparison_table.add_row(*avail_row)

    # Add critical findings
    findings_row = ["Critical Findings"]
    for ep in matrix.environments:
        color = "red" if ep.critical_findings > 0 else "green"
        findings_row.append(f"[{color}]{ep.critical_findings}[/]")
    comparison_table.add_row(*findings_row)

    console.print()
    console.print(comparison_table)

    # 3. Concerns table (significant deltas)
    concerns = [d for d in matrix.deltas if d.concern]
    if concerns:
        concern_table = Table(
            title="Significant Differences (Concerns)",
            show_header=True,
        )
        concern_table.add_column("Metric", style="cyan", width=22)
        concern_table.add_column("Environment A", width=14)
        concern_table.add_column("Value A", justify="right", width=10)
        concern_table.add_column("Environment B", width=14)
        concern_table.add_column("Value B", justify="right", width=10)
        concern_table.add_column("Delta", justify="right", width=10)

        for d in concerns:
            delta_color = "red" if abs(d.delta) > 20 else "yellow"
            concern_table.add_row(
                d.metric.replace("_", " ").title(),
                d.env_a_name,
                f"{d.env_a_value:.1f}",
                d.env_b_name,
                f"{d.env_b_value:.1f}",
                f"[{delta_color}]{d.delta:+.1f}[/]",
            )

        console.print()
        console.print(concern_table)

    # 4. Recommendations
    if matrix.recommendations:
        console.print()
        console.print("[bold]Recommendations:[/]")
        for i, rec in enumerate(matrix.recommendations, 1):
            console.print(f"  {i}. {rec}")

    console.print()
