# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI command for the Infrastructure Pareto Optimizer."""

from __future__ import annotations

import json as json_mod
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import app, console


@app.command()
def optimize(
    yaml_file: Path = typer.Argument(..., help="Infrastructure YAML file"),
    budget: float = typer.Option(
        None, "--budget", "-b", help="Maximum monthly budget in dollars"
    ),
    target_score: float = typer.Option(
        None, "--target-score", "-t", help="Target resilience score (0-100)"
    ),
    steps: int = typer.Option(
        20, "--steps", "-s", help="Number of points on the Pareto frontier"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Pareto optimizer - find the optimal cost vs. resilience trade-off.

    Generates a Pareto frontier showing all non-dominated solutions
    between infrastructure cost and resilience score.

    Examples:
        # Show full Pareto frontier
        faultray optimize infra.yaml

        # Best configuration for a budget
        faultray optimize infra.yaml --budget 5000

        # Cheapest way to reach score 90
        faultray optimize infra.yaml --target-score 90

        # JSON output
        faultray optimize infra.yaml --json
    """
    from faultray.model.loader import load_yaml
    from faultray.simulator.pareto_optimizer import ParetoOptimizer

    if not yaml_file.exists():
        console.print(f"[red]File not found: {yaml_file}[/]")
        raise typer.Exit(1)

    console.print(f"[cyan]Loading infrastructure from {yaml_file}...[/]")
    try:
        graph = load_yaml(yaml_file)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)

    console.print(
        f"[cyan]Running Pareto optimization ({len(graph.components)} components)...[/]"
    )

    optimizer = ParetoOptimizer()

    if budget is not None:
        console.print(f"[cyan]Budget constraint: ${budget:,.0f}/mo[/]")
        solution = optimizer.find_best_for_budget(graph, budget)
        if json_output:
            console.print_json(_solution_to_json(solution))
        else:
            _print_single_solution(solution, "Best Solution for Budget", console)
        return

    if target_score is not None:
        console.print(f"[cyan]Target score: {target_score}[/]")
        solution = optimizer.find_cheapest_for_score(graph, target_score)
        if json_output:
            console.print_json(_solution_to_json(solution))
        else:
            _print_single_solution(solution, "Cheapest Solution for Target", console)
        return

    # Full frontier
    frontier = optimizer.generate_frontier(graph, steps=steps)

    if json_output:
        data = {
            "solutions": [
                {
                    "resilience_score": s.resilience_score,
                    "estimated_monthly_cost": s.estimated_monthly_cost,
                    "availability_nines": s.availability_nines,
                    "spof_count": s.spof_count,
                    "is_current": s.is_current,
                    "improvements": s.improvements_from_current,
                    "variables": s.variables,
                }
                for s in frontier.solutions
            ],
            "current": {
                "resilience_score": frontier.current_solution.resilience_score,
                "estimated_monthly_cost": frontier.current_solution.estimated_monthly_cost,
                "availability_nines": frontier.current_solution.availability_nines,
            },
            "cost_to_next_nine": frontier.cost_to_next_nine,
        }
        console.print_json(json_mod.dumps(data, indent=2, default=str))
        return

    _print_frontier(frontier, console)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _solution_to_json(solution) -> str:
    """Convert a ParetoSolution to JSON string."""
    import json
    return json.dumps({
        "resilience_score": solution.resilience_score,
        "estimated_monthly_cost": solution.estimated_monthly_cost,
        "availability_nines": solution.availability_nines,
        "spof_count": solution.spof_count,
        "is_current": solution.is_current,
        "improvements": solution.improvements_from_current,
        "variables": solution.variables,
    }, indent=2, default=str)


def _print_single_solution(solution, title: str, con: Console) -> None:
    """Print a single solution with details."""
    score_color = "green" if solution.resilience_score >= 80 else "yellow"
    if solution.resilience_score < 50:
        score_color = "red"

    header = (
        f"[bold]Resilience Score:[/] [{score_color}]{solution.resilience_score}[/]/100\n"
        f"[bold]Availability:[/] {solution.availability_nines} nines\n"
        f"[bold]Monthly Cost:[/] ${solution.estimated_monthly_cost:,.0f}\n"
        f"[bold]SPOFs:[/] {solution.spof_count}"
    )

    con.print()
    con.print(Panel(header, title=f"[bold]{title}[/]", border_style="cyan"))

    if solution.improvements_from_current:
        con.print("\n[bold]Changes from current configuration:[/]")
        for imp in solution.improvements_from_current:
            con.print(f"  [green]+[/] {imp}")
    elif solution.is_current:
        con.print("\n[dim]This is the current configuration.[/]")


def _print_frontier(frontier, con: Console) -> None:
    """Print the full Pareto frontier with a table and summary."""
    # Summary panel
    current = frontier.current_solution
    best = frontier.most_resilient_solution
    cheapest = frontier.cheapest_solution
    best_value = frontier.best_value_solution

    summary = (
        f"[bold]Current:[/] Score {current.resilience_score} | "
        f"${current.estimated_monthly_cost:,.0f}/mo | "
        f"{current.availability_nines} nines\n"
        f"[bold]Best Resilience:[/] Score {best.resilience_score} | "
        f"${best.estimated_monthly_cost:,.0f}/mo | "
        f"{best.availability_nines} nines\n"
        f"[bold]Cheapest:[/] Score {cheapest.resilience_score} | "
        f"${cheapest.estimated_monthly_cost:,.0f}/mo | "
        f"{cheapest.availability_nines} nines\n"
        f"[bold]Best Value:[/] Score {best_value.resilience_score} | "
        f"${best_value.estimated_monthly_cost:,.0f}/mo | "
        f"{best_value.availability_nines} nines"
    )

    if frontier.cost_to_next_nine > 0:
        summary += f"\n\n[bold]Cost to add 1 nine:[/] ${frontier.cost_to_next_nine:,.0f}/mo"

    con.print()
    con.print(Panel(summary, title="[bold]Pareto Optimization Summary[/]", border_style="cyan"))

    # Frontier table
    table = Table(
        title="Pareto Frontier (Cost vs. Resilience)",
        show_header=True,
        header_style="bold green",
    )
    table.add_column("#", width=3, justify="right")
    table.add_column("Score", width=8, justify="right")
    table.add_column("Nines", width=7, justify="right")
    table.add_column("Cost/mo", width=12, justify="right")
    table.add_column("SPOFs", width=6, justify="right")
    table.add_column("Key Changes", width=50)
    table.add_column("", width=4)

    for i, sol in enumerate(frontier.solutions, 1):
        score_color = "green" if sol.resilience_score >= 80 else "yellow"
        if sol.resilience_score < 50:
            score_color = "red"

        marker = ""
        if sol.is_current:
            marker = "[bold cyan]<<[/]"
        elif sol is frontier.best_value_solution:
            marker = "[bold green]**[/]"

        changes_str = ", ".join(sol.improvements_from_current[:3])
        if len(sol.improvements_from_current) > 3:
            changes_str += f" (+{len(sol.improvements_from_current) - 3} more)"
        if sol.is_current:
            changes_str = "(current)"

        table.add_row(
            str(i),
            f"[{score_color}]{sol.resilience_score}[/]",
            f"{sol.availability_nines}",
            f"${sol.estimated_monthly_cost:,.0f}",
            str(sol.spof_count),
            changes_str or "-",
            marker,
        )

    con.print()
    con.print(table)
    con.print()
    con.print("[dim]<< = current config  |  ** = best value[/]")
