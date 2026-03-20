# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""CLI commands for Chaos A/B Testing."""

from __future__ import annotations

import json as json_mod
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console
from faultray.simulator.ab_chaos import ChaosABTester


@app.command("ab-test")
def ab_test(
    variant_a: Path = typer.Option(
        ..., "--a", help="Path to variant A infrastructure YAML/JSON"
    ),
    variant_b: Path = typer.Option(
        ..., "--b", help="Path to variant B infrastructure YAML/JSON"
    ),
    name_a: str = typer.Option(
        "Current", "--name-a", help="Label for variant A"
    ),
    name_b: str = typer.Option(
        "Proposed", "--name-b", help="Label for variant B"
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output as JSON"
    ),
) -> None:
    """Compare two architecture variants under the same chaos scenarios.

    Runs identical chaos scenarios against both architectures and produces
    a comparison report showing which variant is more resilient.

    Examples:
        # Compare two architectures
        faultray ab-test --a current.yaml --b proposed.yaml

        # With custom labels
        faultray ab-test --a v1.yaml --b v2.yaml --name-a v1 --name-b v2

        # JSON output for CI/CD
        faultray ab-test --a current.yaml --b proposed.yaml --json
    """
    graph_a = _load_graph_for_analysis(
        model=Path("faultray-model.json"),
        yaml_file=variant_a,
    )
    graph_b = _load_graph_for_analysis(
        model=Path("faultray-model.json"),
        yaml_file=variant_b,
    )

    tester = ChaosABTester(graph_a, graph_b, name_a=name_a, name_b=name_b)
    report = tester.test_default()

    if json_output:
        output = {
            "variant_a": report.variant_a_name,
            "variant_b": report.variant_b_name,
            "scenarios_tested": report.scenarios_tested,
            "a_wins": report.a_wins,
            "b_wins": report.b_wins,
            "ties": report.ties,
            "overall_winner": report.overall_winner,
            "variant_a_resilience": report.variant_a_resilience,
            "variant_b_resilience": report.variant_b_resilience,
            "variant_a_avg_risk": report.variant_a_avg_risk,
            "variant_b_avg_risk": report.variant_b_avg_risk,
            "recommendation": report.recommendation,
            "results": [
                {
                    "scenario": r.scenario_name,
                    "a_score": r.variant_a_score,
                    "b_score": r.variant_b_score,
                    "winner": r.winner,
                    "difference": r.difference,
                }
                for r in report.results
            ],
        }
        console.print_json(json_mod.dumps(output, indent=2))
        return

    # --- Summary Panel ---
    if report.overall_winner == "tie":
        winner_text = "[yellow]TIE[/]"
        border_color = "yellow"
    elif report.overall_winner == "A":
        winner_text = f"[green]{report.variant_a_name}[/]"
        border_color = "green"
    else:
        winner_text = f"[green]{report.variant_b_name}[/]"
        border_color = "green"

    summary = (
        f"[bold]Variant A:[/] {report.variant_a_name}  |  "
        f"[bold]Variant B:[/] {report.variant_b_name}\n\n"
        f"[bold]Scenarios Tested:[/] {report.scenarios_tested}\n"
        f"[bold]A Wins:[/] {report.a_wins}  |  "
        f"[bold]B Wins:[/] {report.b_wins}  |  "
        f"[bold]Ties:[/] {report.ties}\n\n"
        f"[bold]Overall Winner:[/] {winner_text}\n\n"
        f"[bold]Resilience Scores:[/] "
        f"{report.variant_a_name}={report.variant_a_resilience:.1f} vs "
        f"{report.variant_b_name}={report.variant_b_resilience:.1f}\n"
        f"[bold]Avg Risk:[/] "
        f"{report.variant_a_name}={report.variant_a_avg_risk:.2f} vs "
        f"{report.variant_b_name}={report.variant_b_avg_risk:.2f}"
    )

    console.print()
    console.print(Panel(
        summary,
        title="[bold]Chaos A/B Test Report[/]",
        border_style=border_color,
    ))

    # --- Scenario Results Table ---
    if report.results:
        table = Table(
            title="Scenario Comparison",
            show_header=True,
        )
        table.add_column("Scenario", style="cyan", width=35)
        table.add_column(f"{report.variant_a_name} Risk", width=12, justify="right")
        table.add_column(f"{report.variant_b_name} Risk", width=12, justify="right")
        table.add_column("Winner", width=12, justify="center")
        table.add_column("Diff", width=8, justify="right")

        for r in report.results[:30]:  # Cap display at 30 rows
            if r.winner == "tie":
                winner_str = "[yellow]TIE[/]"
            elif r.winner == "A":
                winner_str = f"[green]{report.variant_a_name}[/]"
            else:
                winner_str = f"[green]{report.variant_b_name}[/]"

            table.add_row(
                r.scenario_name[:35],
                f"{r.variant_a_score:.2f}",
                f"{r.variant_b_score:.2f}",
                winner_str,
                f"{r.difference:.2f}",
            )

        if len(report.results) > 30:
            table.add_row(
                f"... and {len(report.results) - 30} more",
                "", "", "", "",
            )

        console.print()
        console.print(table)

    # --- Recommendation ---
    console.print()
    console.print(Panel(
        report.recommendation,
        title="[bold]Recommendation[/]",
        border_style="cyan",
    ))
    console.print()
