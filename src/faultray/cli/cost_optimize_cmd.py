"""CLI command for the Infrastructure Cost Optimizer."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console


@app.command("cost-optimize")
def cost_optimize(
    yaml_file: Path = typer.Argument(..., help="Infrastructure YAML or JSON file"),
    min_score: float = typer.Option(
        70.0, "--min-score", "-s",
        help="Minimum acceptable resilience score after optimization",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON result"),
) -> None:
    """Find cost savings while maintaining minimum resilience.

    Analyzes each component for optimization opportunities (reduce replicas,
    spot instances, consolidation, downsizing) and calculates the resilience
    impact of each suggestion.

    Examples:
        # Basic cost optimization
        faultray cost-optimize infra.yaml

        # With custom minimum score
        faultray cost-optimize infra.yaml --min-score 80

        # JSON output
        faultray cost-optimize infra.yaml --json
    """
    from faultray.simulator.cost_optimizer import CostOptimizer

    graph = _load_graph_for_analysis(yaml_file, None)

    if not json_output:
        console.print(
            f"[cyan]Running cost optimization "
            f"({len(graph.components)} components, "
            f"min score: {min_score})...[/]"
        )

    optimizer = CostOptimizer(graph, min_resilience_score=min_score)
    report = optimizer.optimize()

    if json_output:
        data = {
            "current_monthly_cost": report.current_monthly_cost,
            "optimized_monthly_cost": report.optimized_monthly_cost,
            "total_savings_monthly": report.total_savings_monthly,
            "savings_percent": report.savings_percent,
            "resilience_before": report.resilience_before,
            "resilience_after": report.resilience_after,
            "suggestions": [
                {
                    "action": s.action,
                    "component_id": s.component_id,
                    "current_cost_monthly": s.current_cost_monthly,
                    "optimized_cost_monthly": s.optimized_cost_monthly,
                    "savings_monthly": s.savings_monthly,
                    "resilience_impact": s.resilience_impact,
                    "risk_level": s.risk_level,
                    "description": s.description,
                }
                for s in report.suggestions
            ],
            "pareto_frontier": report.pareto_frontier,
        }
        console.print_json(json.dumps(data, indent=2))
        return

    _print_optimization_report(report, console)


def _print_optimization_report(report, con: Console) -> None:
    """Print the cost optimization report with Rich formatting."""
    savings_color = "green" if report.total_savings_monthly > 0 else "dim"

    summary = (
        f"[bold]Current Monthly Cost:[/] ${report.current_monthly_cost:,.0f}\n"
        f"[bold]Optimized Monthly Cost:[/] ${report.optimized_monthly_cost:,.0f}\n"
        f"[bold]Savings:[/] [{savings_color}]${report.total_savings_monthly:,.0f}/mo "
        f"({report.savings_percent:.1f}%)[/]\n\n"
        f"[bold]Resilience Before:[/] {report.resilience_before:.1f}\n"
        f"[bold]Resilience After:[/] {report.resilience_after:.1f}"
    )

    con.print()
    con.print(Panel(
        summary,
        title="[bold]Cost Optimization Summary[/]",
        border_style="cyan",
    ))

    # Suggestions table
    if report.suggestions:
        table = Table(title="Optimization Suggestions", show_header=True)
        table.add_column("Risk", width=10, justify="center")
        table.add_column("Action", width=16)
        table.add_column("Component", width=16, style="cyan")
        table.add_column("Savings/mo", width=12, justify="right")
        table.add_column("Score Impact", width=12, justify="right")
        table.add_column("Description", width=40)

        risk_colors = {
            "safe": "green",
            "moderate": "yellow",
            "risky": "red",
        }

        for s in report.suggestions:
            rc = risk_colors.get(s.risk_level, "white")
            impact_str = f"{s.resilience_impact:+.1f}" if s.resilience_impact != 0 else "0.0"
            impact_color = "red" if s.resilience_impact < 0 else "green"

            table.add_row(
                f"[{rc}]{s.risk_level.upper()}[/]",
                s.action,
                s.component_id,
                f"[green]${s.savings_monthly:,.0f}[/]",
                f"[{impact_color}]{impact_str}[/]",
                s.description[:40],
            )

        con.print()
        con.print(table)

    # Pareto frontier
    if report.pareto_frontier and len(report.pareto_frontier) > 1:
        pareto_table = Table(title="Cost vs. Resilience Frontier", show_header=True)
        pareto_table.add_column("#", width=3, justify="right")
        pareto_table.add_column("Monthly Cost", width=14, justify="right")
        pareto_table.add_column("Resilience", width=12, justify="right")

        for i, point in enumerate(report.pareto_frontier, 1):
            score_color = "green" if point["resilience"] >= 80 else "yellow"
            if point["resilience"] < 50:
                score_color = "red"

            pareto_table.add_row(
                str(i),
                f"${point['cost']:,.0f}",
                f"[{score_color}]{point['resilience']:.1f}[/]",
            )

        con.print()
        con.print(pareto_table)

    if not report.suggestions:
        con.print()
        con.print("[dim]No optimization suggestions - infrastructure is already cost-efficient.[/]")
