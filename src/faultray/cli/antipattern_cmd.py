# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI commands for Architecture Anti-Pattern Detector."""

from __future__ import annotations

import json as json_mod
from pathlib import Path

import typer
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console
from faultray.simulator.antipattern_detector import AntiPatternDetector


_SEVERITY_COLORS = {
    "critical": "bold red",
    "high": "red",
    "medium": "yellow",
}


@app.command("antipatterns")
def antipatterns(
    yaml_file: Path = typer.Argument(..., help="Infrastructure YAML or JSON file"),
    min_severity: str = typer.Option(
        "medium", "--min-severity", "-s",
        help="Minimum severity to report (critical, high, medium)",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON",
    ),
) -> None:
    """Detect architecture anti-patterns in infrastructure configuration.

    Checks for common anti-patterns including:
      - God Component (>50% coupling)
      - Circular Dependencies
      - Missing Circuit Breakers on critical paths
      - Database Direct Access (no connection pooling)
      - Single Availability Zone
      - Load Balancers without health checks
      - Thundering Herd risk
      - N+1 Dependencies (no load balancer)

    Examples:
        # Detect all anti-patterns
        faultray antipatterns infra.yaml

        # Only critical and high severity
        faultray antipatterns infra.yaml --min-severity high

        # JSON output for CI/CD
        faultray antipatterns infra.yaml --json
    """
    graph = _load_graph_for_analysis(
        model=Path("faultray-model.json"),
        yaml_file=yaml_file,
    )

    detector = AntiPatternDetector(graph)
    patterns = detector.detect_by_severity(min_severity)

    if json_output:
        output = {
            "total_patterns": len(patterns),
            "min_severity": min_severity,
            "patterns": [
                {
                    "id": p.id,
                    "name": p.name,
                    "severity": p.severity,
                    "description": p.description,
                    "affected_components": p.affected_components,
                    "recommendation": p.recommendation,
                    "reference": p.reference,
                }
                for p in patterns
            ],
        }
        console.print_json(json_mod.dumps(output, indent=2))
        return

    # Rich table output
    if not patterns:
        console.print(
            f"\n[bold green]No anti-patterns detected "
            f"(min severity: {min_severity})[/]\n"
        )
        return

    console.print()
    table = Table(
        title=f"Architecture Anti-Patterns ({len(patterns)} found)",
        show_header=True,
    )
    table.add_column("Severity", width=10, justify="center")
    table.add_column("Pattern", style="cyan", width=30)
    table.add_column("Description", width=50)
    table.add_column("Affected", width=20)

    for p in patterns:
        sev_color = _SEVERITY_COLORS.get(p.severity, "white")
        affected_str = ", ".join(p.affected_components[:3])
        if len(p.affected_components) > 3:
            affected_str += f" (+{len(p.affected_components) - 3})"

        table.add_row(
            f"[{sev_color}]{p.severity.upper()}[/]",
            p.name,
            p.description[:100] + ("..." if len(p.description) > 100 else ""),
            affected_str,
        )

    console.print(table)

    # Print recommendations
    console.print()
    console.print("[bold]Recommendations:[/]")
    seen_ids: set[str] = set()
    for p in patterns:
        if p.id not in seen_ids and p.recommendation:
            seen_ids.add(p.id)
            sev_color = _SEVERITY_COLORS.get(p.severity, "white")
            console.print(
                f"  [{sev_color}]{p.severity.upper()}[/] "
                f"[cyan]{p.name}[/]: {p.recommendation}"
            )

    console.print()
