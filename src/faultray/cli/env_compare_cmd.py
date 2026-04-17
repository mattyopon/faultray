# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI command for Multi-Environment Comparison (env_comparator)."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import app, console


@app.command("env-compare")
def env_compare(
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
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON.",
    ),
) -> None:
    """Compare resilience/security/cost across dev, staging, and prod environments.

    Detects configuration drift, security posture gaps, and cost differences.

    Examples:
        faultray env-compare --prod prod.yaml --staging staging.yaml --dev dev.yaml
        faultray env-compare --prod prod.yaml --staging staging.yaml --json
    """
    from faultray.model.loader import load_yaml
    from faultray.simulator.env_comparator import EnvironmentComparator

    # Build environment dict
    envs = {}
    paths_map = {}
    if prod is not None:
        paths_map["prod"] = prod
    if staging is not None:
        paths_map["staging"] = staging
    if dev is not None:
        paths_map["dev"] = dev

    if len(paths_map) < 2:
        console.print(
            "[red]At least 2 environments are required.[/]\n"
            "[dim]Use --prod, --staging, and/or --dev to specify YAML files.[/]"
        )
        raise typer.Exit(1)

    for name, p in paths_map.items():
        if not p.exists():
            console.print(f"[red]File not found for {name}: {p}[/]")
            raise typer.Exit(1)
        envs[name] = load_yaml(p)

    comparator = EnvironmentComparator()
    result = comparator.compare(envs)

    if json_output:
        data = {
            "environments": [
                {
                    "name": ep.name,
                    "resilience_score": ep.resilience_score,
                    "security_score": ep.security_score,
                    "cost_monthly": ep.cost_monthly,
                    "component_count": ep.component_count,
                }
                for ep in result.environments
            ],
            "drift_detected": result.drift_detected,
            "drift_details": result.drift_details,
            "parity_score": result.parity_score,
            "recommendations": result.recommendations,
        }
        console.print_json(data=data)
        return

    # Rich output
    parity_color = (
        "green" if result.parity_score >= 80
        else "yellow" if result.parity_score >= 50
        else "red"
    )
    overview = (
        f"[bold]Environments:[/] {len(result.environments)}\n"
        f"[bold]Parity Score:[/] [{parity_color}]{result.parity_score:.1f}%[/]\n"
        f"[bold]Drift Detected:[/] {'[red]YES[/]' if result.drift_detected else '[green]NO[/]'}"
    )
    console.print()
    console.print(Panel(
        overview,
        title="[bold]Environment Comparison[/]",
        border_style=parity_color,
    ))

    # Comparison table
    table = Table(title="Environment Profiles", show_header=True, header_style="bold")
    table.add_column("Metric", style="cyan", width=20)
    for ep in result.environments:
        table.add_column(ep.name.upper(), justify="right", width=14)

    for metric, accessor in [
        ("Resilience Score", lambda ep: f"{ep.resilience_score:.1f}"),
        ("Security Score", lambda ep: f"{ep.security_score:.1f}"),
        ("Monthly Cost", lambda ep: f"${ep.cost_monthly:,.2f}"),
        ("Components", lambda ep: str(ep.component_count)),
    ]:
        row = [metric] + [accessor(ep) for ep in result.environments]
        table.add_row(*row)

    console.print()
    console.print(table)

    # Drift details
    if result.drift_details:
        drift_table = Table(title="Configuration Drift", show_header=True)
        drift_table.add_column("Component", style="cyan", width=18)
        drift_table.add_column("Field", width=22)
        for ep in result.environments:
            drift_table.add_column(ep.name.upper(), width=16)

        for d in result.drift_details[:20]:
            row = [d["component"], d["field"]]
            for ep in result.environments:
                key = f"{ep.name}_value"
                row.append(str(d.get(key, "-")))
            drift_table.add_row(*row)

        console.print()
        console.print(drift_table)

    # Recommendations
    if result.recommendations:
        console.print()
        console.print("[bold]Recommendations:[/]")
        for i, rec in enumerate(result.recommendations, 1):
            console.print(f"  {i}. {rec}")

    console.print()
