"""CLI command for the AI Architecture Advisor."""

from __future__ import annotations

import json as json_mod
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from faultray.ai.architecture_advisor import ArchitectureAdvisor, ArchitectureReport
    from faultray.model.graph import InfraGraph

from faultray.cli.main import app, console


@app.command()
def advise(
    yaml_file: Path = typer.Argument(..., help="Infrastructure YAML file"),
    target: float = typer.Option(
        4.0, "--target", "-t", help="Target availability in nines (e.g. 4.0 = 99.99%%)"
    ),
    quick_wins: bool = typer.Option(
        False, "--quick-wins", help="Show only quick wins"
    ),
    anti_patterns: bool = typer.Option(
        False, "--anti-patterns", help="Show detected anti-patterns"
    ),
    mermaid: bool = typer.Option(
        False, "--mermaid", help="Output Mermaid.js diagram"
    ),
    apply: bool = typer.Option(
        False, "--apply", help="Apply recommendations and save improved YAML"
    ),
    output: Path = typer.Option(
        None, "--output", "-o", help="Output path for improved YAML (used with --apply)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """AI Architecture Advisor - intelligent infrastructure redesign recommendations.

    Analyzes current infrastructure topology and generates concrete, actionable
    architecture redesign proposals to achieve specific resilience targets.

    Examples:
        # Full architecture advice
        faultray advise infra.yaml

        # Target specific SLA
        faultray advise infra.yaml --target 99.99

        # Show only quick wins
        faultray advise infra.yaml --quick-wins

        # Show detected anti-patterns
        faultray advise infra.yaml --anti-patterns

        # Output Mermaid diagram
        faultray advise infra.yaml --mermaid

        # Apply recommendations and save new YAML
        faultray advise infra.yaml --apply --output improved.yaml

        # JSON output
        faultray advise infra.yaml --json
    """
    from faultray.ai.architecture_advisor import ArchitectureAdvisor
    from faultray.model.loader import load_yaml

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
        f"[cyan]Running architecture analysis ({len(graph.components)} components, "
        f"target: {target} nines)...[/]"
    )

    advisor = ArchitectureAdvisor()
    report = advisor.advise(graph, target_nines=target)

    # --- Mermaid-only mode ---
    if mermaid:
        if json_output:
            console.print_json(json_mod.dumps({"mermaid": report.mermaid_diagram}))
        else:
            console.print(Panel(
                report.mermaid_diagram,
                title="[bold]Proposed Architecture (Mermaid.js)[/]",
                border_style="cyan",
            ))
        return

    # --- Quick-wins-only mode ---
    if quick_wins:
        if json_output:
            import dataclasses
            data = [dataclasses.asdict(w) for w in report.quick_wins]
            console.print_json(json_mod.dumps(data, indent=2, default=str))
        else:
            _print_quick_wins(report.quick_wins, console)
        return

    # --- Anti-patterns-only mode ---
    if anti_patterns:
        if json_output:
            data = [{"name": name, "description": desc} for name, desc in report.anti_patterns_detected]
            console.print_json(json_mod.dumps(data, indent=2))
        else:
            _print_anti_patterns(report.anti_patterns_detected, console)
        return

    # --- Apply mode ---
    if apply:
        if not report.proposals:
            console.print("[yellow]No proposals to apply.[/]")
            raise typer.Exit(0)

        # Apply the first (best) proposal
        proposal = report.proposals[0]
        console.print(f"[cyan]Applying proposal: {proposal.name}...[/]")
        modified_graph = advisor.apply_proposal(graph, proposal)

        # Compare before/after
        comparison = advisor.compare_before_after(graph, modified_graph)
        _print_comparison(comparison, console)

        # Save if output path specified
        out_path = output or Path("improved-" + yaml_file.name)
        modified_graph.save(out_path)
        console.print(f"\n[green]Improved infrastructure saved to {out_path}[/]")
        return

    # --- Full JSON output ---
    if json_output:
        import dataclasses
        report_dict = dataclasses.asdict(report)
        console.print_json(json_mod.dumps(report_dict, indent=2, default=str))
        return

    # --- Full Rich output ---
    _print_full_report(report, advisor, graph, console)


# ---------------------------------------------------------------------------
# Rich output helpers
# ---------------------------------------------------------------------------


def _print_full_report(
    report: "ArchitectureReport",
    advisor: "ArchitectureAdvisor",
    graph: "InfraGraph",
    con: Console,
) -> None:
    """Print the full architecture advisory report with Rich formatting."""

    # Assessment
    con.print()
    score_color = "green" if report.current_nines >= report.target_nines else "yellow"
    if report.current_nines < report.target_nines - 1.0:
        score_color = "red"

    con.print(Panel(
        f"[bold]{report.current_assessment}[/]",
        title="[bold]Architecture Assessment[/]",
        border_style=score_color,
    ))

    # Score summary
    con.print(
        f"  Current: [bold]{report.current_score}[/]/100 "
        f"([bold]{report.current_nines:.2f}[/] nines)  |  "
        f"Target: [bold]{report.target_nines}[/] nines"
    )
    con.print()

    # Gap analysis
    if report.gap_analysis:
        con.print(Panel(
            report.gap_analysis,
            title="[bold]Gap Analysis[/]",
            border_style="dim",
        ))

    # Anti-patterns
    if report.anti_patterns_detected:
        _print_anti_patterns(report.anti_patterns_detected, con)

    # Pattern recommendations
    if report.architecture_patterns_recommended:
        _print_pattern_recommendations(report.architecture_patterns_recommended, con)

    # Quick wins
    if report.quick_wins:
        _print_quick_wins(report.quick_wins, con)

    # Proposals
    if report.proposals:
        _print_proposals(report.proposals, con)

    # Mermaid diagram
    if report.mermaid_diagram:
        con.print()
        con.print(Panel(
            report.mermaid_diagram,
            title="[bold]Proposed Architecture (Mermaid.js)[/]",
            border_style="cyan",
        ))


def _print_quick_wins(
    wins: list, con: Console
) -> None:
    """Print quick wins table."""
    if not wins:
        con.print("[yellow]No quick wins detected.[/]")
        return

    table = Table(title="Quick Wins", show_header=True, header_style="bold green")
    table.add_column("#", width=3, justify="right")
    table.add_column("Component", width=20, style="cyan")
    table.add_column("Change", width=40)
    table.add_column("Impact", width=8, justify="right")
    table.add_column("Effort", width=8, justify="center")
    table.add_column("Cost", width=15, justify="right")
    table.add_column("Risk Reduction", width=30)

    for i, win in enumerate(wins, 1):
        impact_color = "green" if win.resilience_impact >= 5 else "yellow"
        table.add_row(
            str(i),
            win.component_id or "-",
            win.description,
            f"[{impact_color}]+{win.resilience_impact:.1f}[/]",
            win.effort,
            win.estimated_cost,
            win.risk_reduction,
        )

    con.print()
    con.print(table)


def _print_anti_patterns(
    patterns: list[tuple[str, str]], con: Console
) -> None:
    """Print detected anti-patterns."""
    if not patterns:
        con.print("[green]No anti-patterns detected.[/]")
        return

    con.print()
    con.print("[bold red]Anti-Patterns Detected:[/]")
    for name, description in patterns:
        con.print(f"\n  [bold red]{name}[/]")
        con.print(f"  {description}")


def _print_pattern_recommendations(
    patterns: list[tuple], con: Console
) -> None:
    """Print recommended architecture patterns."""
    table = Table(
        title="Recommended Architecture Patterns",
        show_header=True,
        header_style="bold blue",
    )
    table.add_column("Pattern", width=22, style="cyan")
    table.add_column("Reason", width=70)

    for pattern, reason in patterns:
        pattern_name = pattern.value.replace("_", " ").title()
        table.add_row(pattern_name, reason)

    con.print()
    con.print(table)


def _print_proposals(proposals: list, con: Console) -> None:
    """Print architecture proposals."""
    for i, proposal in enumerate(proposals, 1):
        score_delta = proposal.projected_score - proposal.current_score
        delta_color = "green" if score_delta > 0 else "yellow"

        header = (
            f"[bold]{proposal.name}[/]\n\n"
            f"{proposal.description}\n\n"
            f"Score: {proposal.current_score} -> [{delta_color}]{proposal.projected_score}[/] "
            f"([{delta_color}]+{score_delta:.1f}[/])\n"
            f"Effort: [bold]{proposal.total_effort}[/]  |  "
            f"Cost: [bold]{proposal.estimated_monthly_cost}[/]"
        )

        if proposal.patterns_applied:
            pattern_names = ", ".join(
                p.value.replace("_", " ").title() for p in proposal.patterns_applied
            )
            header += f"\nPatterns: {pattern_names}"

        con.print()
        con.print(Panel(header, title=f"[bold]Proposal {i}[/]", border_style="blue"))

        # Changes table
        if proposal.changes:
            changes_table = Table(show_header=True, header_style="bold")
            changes_table.add_column("Type", width=16)
            changes_table.add_column("Component", width=20, style="cyan")
            changes_table.add_column("Description", width=50)
            changes_table.add_column("Impact", width=8, justify="right")

            for change in proposal.changes:
                impact_color = (
                    "green" if change.resilience_impact >= 5 else "yellow"
                )
                changes_table.add_row(
                    change.change_type,
                    change.component_id or "-",
                    change.description,
                    f"[{impact_color}]+{change.resilience_impact:.1f}[/]",
                )
            con.print(changes_table)

        # Trade-offs
        if proposal.trade_offs:
            con.print("\n  [bold]Trade-offs:[/]")
            for trade_off in proposal.trade_offs:
                con.print(f"    - {trade_off}")

        # Prerequisites
        if proposal.prerequisites:
            con.print("\n  [bold]Prerequisites:[/]")
            for prereq in proposal.prerequisites:
                con.print(f"    - {prereq}")


def _print_comparison(comparison: dict, con: Console) -> None:
    """Print before/after comparison table."""
    table = Table(
        title="Before / After Comparison",
        show_header=True,
        header_style="bold",
    )
    table.add_column("Metric", width=25)
    table.add_column("Before", width=12, justify="right")
    table.add_column("After", width=12, justify="right")
    table.add_column("Change", width=12, justify="right")

    # Score
    score_delta = comparison["score_improvement"]
    delta_color = "green" if score_delta > 0 else "red"
    table.add_row(
        "Resilience Score",
        f"{comparison['original_score']}",
        f"{comparison['modified_score']}",
        f"[{delta_color}]{score_delta:+.1f}[/]",
    )

    # Nines
    nines_delta = comparison["nines_improvement"]
    nines_color = "green" if nines_delta > 0 else "red"
    table.add_row(
        "Availability (nines)",
        f"{comparison['original_nines']:.2f}",
        f"{comparison['modified_nines']:.2f}",
        f"[{nines_color}]{nines_delta:+.2f}[/]",
    )

    # Components
    comp_delta = comparison["modified_components"] - comparison["original_components"]
    table.add_row(
        "Components",
        str(comparison["original_components"]),
        str(comparison["modified_components"]),
        f"{comp_delta:+d}" if comp_delta != 0 else "0",
    )

    # Dependencies
    dep_delta = comparison["modified_dependencies"] - comparison["original_dependencies"]
    table.add_row(
        "Dependencies",
        str(comparison["original_dependencies"]),
        str(comparison["modified_dependencies"]),
        f"{dep_delta:+d}" if dep_delta != 0 else "0",
    )

    con.print()
    con.print(table)
