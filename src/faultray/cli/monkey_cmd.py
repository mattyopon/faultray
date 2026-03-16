"""CLI command for Chaos Monkey mode."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console


@app.command(name="chaos-monkey")
def chaos_monkey(
    model_file: Path = typer.Argument(
        ...,
        help="Path to YAML/JSON infrastructure model file.",
    ),
    level: str = typer.Option(
        "monkey", "--level", "-l",
        help="Chaos level: monkey (single), gorilla (same-type group), kong (massive), army (progressive).",
    ),
    rounds: int = typer.Option(
        10, "--rounds", "-r",
        help="Number of experiment rounds.",
    ),
    seed: int = typer.Option(
        None, "--seed", "-s",
        help="RNG seed for reproducibility.",
    ),
    find_weakest: bool = typer.Option(
        False, "--find-weakest",
        help="Find the weakest component (most damage when killed).",
    ),
    stress_test: bool = typer.Option(
        False, "--stress-test",
        help="Progressive stress test (increase failures until breaking point).",
    ),
    max_failures: int = typer.Option(
        5, "--max-failures",
        help="Maximum simultaneous failures for stress test.",
    ),
    exclude: str = typer.Option(
        None, "--exclude", "-e",
        help="Comma-separated component IDs to exclude.",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON.",
    ),
) -> None:
    """Chaos Monkey - Netflix-style random failure injection simulation.

    Randomly kill components and observe how the system responds.

    Examples:
        faultray chaos-monkey infra.yaml
        faultray chaos-monkey infra.yaml --level gorilla --rounds 20
        faultray chaos-monkey infra.yaml --level army
        faultray chaos-monkey infra.yaml --seed 42
        faultray chaos-monkey infra.yaml --find-weakest
        faultray chaos-monkey infra.yaml --stress-test
        faultray chaos-monkey infra.yaml --json
    """
    from faultray.simulator.chaos_monkey import ChaosLevel, ChaosMonkey, ChaosMonkeyConfig

    graph = _load_graph_for_analysis(model_file, None)
    monkey = ChaosMonkey()

    # --- Find weakest ---
    if find_weakest:
        if not json_output:
            console.print("[cyan]Searching for the weakest component...[/]")
        weakest = monkey.find_weakest_point(graph, rounds=max(rounds, 50), seed=seed)
        if json_output:
            console.print_json(json.dumps({"weakest_component": weakest}))
        else:
            comp = graph.get_component(weakest)
            name = comp.name if comp else weakest
            console.print(Panel(
                f"[bold red]Weakest Component:[/] {name} ({weakest})\n\n"
                "This component causes the most damage when it fails.\n"
                "Prioritize adding redundancy and failover here.",
                title="Weakest Point Analysis",
                border_style="red",
            ))
        return

    # --- Stress test ---
    if stress_test:
        if not json_output:
            console.print(
                f"[cyan]Running stress test (up to {max_failures} simultaneous failures)...[/]"
            )
        experiments = monkey.stress_test(graph, max_failures=max_failures, seed=seed)

        if json_output:
            data = {
                "stress_test": [
                    _experiment_to_dict(e) for e in experiments
                ],
            }
            console.print_json(json.dumps(data))
        else:
            _print_stress_test(experiments)
        return

    # --- Normal run ---
    try:
        chaos_level = ChaosLevel(level)
    except ValueError:
        console.print(f"[red]Invalid level '{level}'. Choose from: monkey, gorilla, kong, army[/]")
        raise typer.Exit(1)

    exclude_list = [x.strip() for x in exclude.split(",")] if exclude else []

    config = ChaosMonkeyConfig(
        level=chaos_level,
        rounds=rounds,
        seed=seed,
        exclude_components=exclude_list,
    )

    if not json_output:
        console.print(
            f"[cyan]Unleashing Chaos {chaos_level.value.title()} "
            f"({rounds} rounds, seed={seed})...[/]"
        )

    report = monkey.run(graph, config)

    if json_output:
        data = _report_to_dict(report)
        console.print_json(json.dumps(data))
        return

    _print_report(report)


def _experiment_to_dict(exp: object) -> dict:
    """Convert a MonkeyExperiment to a dict."""
    return {
        "round": exp.round_number,
        "failed_components": exp.failed_components,
        "level": exp.level.value if hasattr(exp.level, "value") else str(exp.level),
        "survived": exp.survived,
        "cascade_depth": exp.cascade_depth,
        "affected_count": exp.affected_count,
        "resilience_during": exp.resilience_during,
        "recovery_possible": exp.recovery_possible,
    }


def _report_to_dict(report: object) -> dict:
    """Convert a ChaosMonkeyReport to a dict."""
    return {
        "total_rounds": report.total_rounds,
        "survival_rate": report.survival_rate,
        "avg_cascade_depth": report.avg_cascade_depth,
        "avg_affected": report.avg_affected,
        "most_dangerous_component": report.most_dangerous_component,
        "safest_component": report.safest_component,
        "mean_time_to_impact": report.mean_time_to_impact,
        "resilience_score_range": list(report.resilience_score_range),
        "recommendations": report.recommendations,
        "experiments": [_experiment_to_dict(e) for e in report.experiments],
        "worst_experiment": (
            _experiment_to_dict(report.worst_experiment)
            if report.worst_experiment else None
        ),
        "best_experiment": (
            _experiment_to_dict(report.best_experiment)
            if report.best_experiment else None
        ),
    }


def _print_report(report: object) -> None:
    """Print a rich-formatted Chaos Monkey report."""
    survival_pct = report.survival_rate * 100
    if survival_pct >= 80:
        survival_style = "bold green"
    elif survival_pct >= 50:
        survival_style = "bold yellow"
    else:
        survival_style = "bold red"

    console.print(Panel(
        f"[bold cyan]Chaos Monkey Report[/]\n\n"
        f"Level: [bold]{report.config.level.value.title()}[/]  |  "
        f"Rounds: [bold]{report.total_rounds}[/]  |  "
        f"Seed: [bold]{report.config.seed}[/]\n\n"
        f"Survival Rate: [{survival_style}]{survival_pct:.1f}%[/{survival_style}]\n"
        f"Avg Cascade Depth: [bold]{report.avg_cascade_depth:.1f}[/]  |  "
        f"Avg Affected: [bold]{report.avg_affected:.1f}[/]\n"
        f"Resilience Range: [bold]{report.resilience_score_range[0]:.1f} - "
        f"{report.resilience_score_range[1]:.1f}[/]\n"
        f"Most Dangerous: [bold red]{report.most_dangerous_component}[/]  |  "
        f"Safest: [bold green]{report.safest_component}[/]",
        title="Chaos Monkey Summary",
        border_style="cyan",
    ))

    # Experiments table
    table = Table(title="Experiments")
    table.add_column("Round", justify="center", width=6)
    table.add_column("Failed", max_width=30)
    table.add_column("Survived", justify="center", width=9)
    table.add_column("Cascade", justify="center", width=8)
    table.add_column("Affected", justify="center", width=9)
    table.add_column("Resilience", justify="center", width=11)

    for exp in report.experiments:
        survived_str = "[green]YES[/]" if exp.survived else "[red]NO[/]"
        failed_str = ", ".join(exp.failed_components[:3])
        if len(exp.failed_components) > 3:
            failed_str += f" (+{len(exp.failed_components) - 3})"

        table.add_row(
            str(exp.round_number),
            failed_str,
            survived_str,
            str(exp.cascade_depth),
            str(exp.affected_count),
            f"{exp.resilience_during:.1f}",
        )

    console.print(table)

    # Recommendations
    if report.recommendations:
        rec_panel = "\n".join(f"  * {r}" for r in report.recommendations)
        console.print(Panel(rec_panel, title="Recommendations", border_style="yellow"))


def _print_stress_test(experiments: list) -> None:
    """Print stress test results."""
    console.print(Panel(
        "[bold cyan]Stress Test Results[/]\n\n"
        "Progressive failure injection - how many simultaneous failures\n"
        "can the system handle before breaking?",
        title="Stress Test",
        border_style="cyan",
    ))

    table = Table(title="Progressive Failures")
    table.add_column("Failures", justify="center", width=9)
    table.add_column("Survived", justify="center", width=9)
    table.add_column("Affected", justify="center", width=9)
    table.add_column("Cascade", justify="center", width=8)
    table.add_column("Resilience", justify="center", width=11)

    breaking_point = None
    for exp in experiments:
        survived_str = "[green]YES[/]" if exp.survived else "[red]NO[/]"
        table.add_row(
            str(len(exp.failed_components)),
            survived_str,
            str(exp.affected_count),
            str(exp.cascade_depth),
            f"{exp.resilience_during:.1f}",
        )
        if not exp.survived and breaking_point is None:
            breaking_point = len(exp.failed_components)

    console.print(table)

    if breaking_point:
        console.print(Panel(
            f"[bold red]Breaking point: {breaking_point} simultaneous failures[/]\n\n"
            "The system cannot sustain this many concurrent failures.",
            border_style="red",
        ))
    else:
        console.print(Panel(
            "[bold green]System survived all failure levels![/]\n\n"
            "The infrastructure shows strong resilience.",
            border_style="green",
        ))
