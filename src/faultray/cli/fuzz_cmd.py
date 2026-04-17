# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI command for the Chaos Fuzzer."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console


@app.command()
def fuzz(
    model_file: Path = typer.Argument(
        ...,
        help="Path to YAML/JSON infrastructure model file.",
    ),
    iterations: int = typer.Option(
        100, "--iterations", "-n",
        help="Number of fuzzing iterations.",
    ),
    seed: int = typer.Option(
        42, "--seed", "-s",
        help="RNG seed for reproducibility.",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON.",
    ),
) -> None:
    """AFL-inspired fuzzing to discover unknown failure patterns.

    Randomly mutates chaos scenarios to explore the failure space and
    discover novel failure modes in your infrastructure.

    Examples:
        faultray fuzz infra.yaml
        faultray fuzz infra.yaml --iterations 500
        faultray fuzz infra.yaml --iterations 200 --seed 123
        faultray fuzz infra.yaml --iterations 500 --json
    """
    from faultray.simulator.chaos_fuzzer import ChaosFuzzer

    graph = _load_graph_for_analysis(model_file, None)

    if not json_output:
        console.print(
            f"[cyan]Fuzzing {len(graph.components)} components "
            f"for {iterations} iterations (seed={seed})...[/]"
        )

    fuzzer = ChaosFuzzer(graph, seed=seed)
    report = fuzzer.fuzz(iterations=iterations)

    if json_output:
        data = {
            "total_iterations": report.total_iterations,
            "novel_failures_found": report.novel_failures_found,
            "highest_risk_score": report.highest_risk_score,
            "coverage": round(report.coverage, 3),
            "mutation_effectiveness": {
                k: round(v, 3) for k, v in report.mutation_effectiveness.items()
            },
            "novel_scenarios": [
                {
                    "iteration": r.iteration,
                    "risk_score": r.risk_score,
                    "mutation_type": r.mutation_type,
                    "scenario_name": r.scenario.name,
                    "faults": [
                        {
                            "target": f.target_component_id,
                            "type": f.fault_type.value,
                            "severity": f.severity,
                        }
                        for f in r.scenario.faults
                    ],
                }
                for r in report.novel_scenarios[:20]
            ],
        }
        console.print_json(data=data)
        return

    # Summary panel
    cov_pct = report.coverage * 100
    summary = (
        f"[bold]Iterations:[/] {report.total_iterations}\n"
        f"[bold]Novel failures found:[/] {report.novel_failures_found}\n"
        f"[bold]Highest risk score:[/] {report.highest_risk_score:.1f}\n"
        f"[bold]Component coverage:[/] {cov_pct:.1f}%"
    )
    border = "green" if report.highest_risk_score < 5.0 else (
        "yellow" if report.highest_risk_score < 7.0 else "red"
    )
    console.print()
    console.print(Panel(summary, title="[bold]Chaos Fuzzer Report[/]", border_style=border))

    # Mutation effectiveness table
    if report.mutation_effectiveness:
        mut_table = Table(title="Mutation Effectiveness", show_header=True)
        mut_table.add_column("Mutation Type", style="cyan", width=20)
        mut_table.add_column("Discovery Rate", justify="right", width=15)

        for mt, rate in sorted(
            report.mutation_effectiveness.items(),
            key=lambda x: x[1],
            reverse=True,
        ):
            color = "green" if rate > 0.3 else ("yellow" if rate > 0.1 else "dim")
            mut_table.add_row(mt, f"[{color}]{rate:.1%}[/]")

        console.print()
        console.print(mut_table)

    # Top novel scenarios
    if report.novel_scenarios:
        novel_table = Table(
            title=f"Top Novel Failure Scenarios (showing {min(len(report.novel_scenarios), 10)})",
            show_header=True,
        )
        novel_table.add_column("#", width=5, justify="right")
        novel_table.add_column("Risk", width=6, justify="right")
        novel_table.add_column("Mutation", width=16)
        novel_table.add_column("Scenario", width=30)
        novel_table.add_column("Faults", width=40)

        for idx, r in enumerate(report.novel_scenarios[:10], 1):
            risk_color = (
                "red" if r.risk_score >= 7.0
                else "yellow" if r.risk_score >= 4.0
                else "green"
            )
            fault_desc = ", ".join(
                f"{f.target_component_id}:{f.fault_type.value}"
                for f in r.scenario.faults[:3]
            )
            if len(r.scenario.faults) > 3:
                fault_desc += f" +{len(r.scenario.faults) - 3} more"
            novel_table.add_row(
                str(idx),
                f"[{risk_color}]{r.risk_score:.1f}[/]",
                r.mutation_type,
                r.scenario.name[:30],
                fault_desc[:40],
            )

        console.print()
        console.print(novel_table)
