# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""CLI commands for Runbook Validation and Generation.

Usage:
    faultray runbook validate model.yaml --runbook runbook.yaml
    faultray runbook validate model.yaml --runbook runbook.yaml --json
    faultray runbook generate --model infra.yaml --output ./runbooks/
    faultray runbook list --model infra.yaml
    faultray runbook coverage --model infra.yaml
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import (
    DEFAULT_MODEL_PATH,
    _load_graph_for_analysis,
    app,
    console,
)

runbook_app = typer.Typer(
    name="runbook",
    help="Validate and auto-generate incident response runbooks.",
    no_args_is_help=True,
)
app.add_typer(runbook_app, name="runbook")


def _load_graph_from_model(model: Path):
    """Load an InfraGraph from a YAML or JSON model file."""
    if str(model).endswith((".yaml", ".yml")):
        from faultray.model.loader import load_yaml
        return load_yaml(model)
    else:
        from faultray.model.graph import InfraGraph
        return InfraGraph.load(model)


@runbook_app.command()
def validate(
    model: Path = typer.Argument(..., help="Infrastructure model file (YAML/JSON)"),
    runbook: Path = typer.Option(..., "--runbook", "-r", help="Runbook YAML file"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Validate a runbook by simulating each step against the infrastructure model.

    \b
    Injects the trigger fault specified in the runbook, then executes each step
    and verifies recovery. Reports which steps pass, fail, or timeout.

    \b
    Examples:
        faultray runbook validate infra.yaml --runbook db-failover.yaml
        faultray runbook validate model.json --runbook runbook.yaml --json
    """
    # Load infrastructure model
    yaml_path = model if str(model).endswith((".yaml", ".yml")) else None
    json_path = model if yaml_path is None else None
    graph = _load_graph_for_analysis(
        json_path or DEFAULT_MODEL_PATH,
        yaml_path,
    )

    from faultray.simulator.runbook_validator import RunbookValidator

    validator = RunbookValidator(graph)

    # Parse runbook
    try:
        steps, initial_fault, runbook_name = validator.parse_runbook_yaml(runbook)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error parsing runbook: {e}[/]")
        raise typer.Exit(1)

    if not steps:
        console.print("[yellow]Runbook has no steps to validate.[/]")
        raise typer.Exit(0)

    # Validate runbook
    report = validator.validate(steps, initial_fault, runbook_name=runbook_name)

    if json_output:
        output = {
            "runbook_name": report.runbook_name,
            "overall": report.overall,
            "total_steps": report.total_steps,
            "passed": report.passed,
            "failed": report.failed,
            "skipped": report.skipped,
            "estimated_recovery_minutes": round(report.estimated_recovery_minutes, 2),
            "initial_fault": report.initial_fault,
            "steps": [
                {
                    "step_number": r.step_number,
                    "action": r.action,
                    "target": r.target,
                    "result": r.result,
                    "actual_state": r.actual_state,
                    "expected_state": r.expected_state,
                    "time_elapsed_seconds": r.time_elapsed_seconds,
                    "details": r.details,
                }
                for r in report.step_results
            ],
            "improvements": report.improvements,
        }
        console.print_json(data=output)
        return

    # Display report
    overall_color = {
        "VALID": "green",
        "PARTIAL": "yellow",
        "INVALID": "red",
    }.get(report.overall, "white")

    summary = (
        f"[bold]Runbook:[/] {report.runbook_name}\n"
        f"[bold]Initial Fault:[/] {report.initial_fault}\n"
        f"[bold]Overall:[/] [{overall_color}]{report.overall}[/]\n"
        f"[bold]Steps:[/] {report.passed} passed, {report.failed} failed, "
        f"{report.skipped} skipped (of {report.total_steps})\n"
        f"[bold]Estimated Recovery:[/] {report.estimated_recovery_minutes:.1f} minutes"
    )

    console.print()
    console.print(Panel(
        summary,
        title="[bold cyan]Runbook Validation Report[/]",
        border_style=overall_color,
    ))

    # Step results table
    table = Table(title="Step Results", show_header=True)
    table.add_column("#", width=4, justify="right")
    table.add_column("Action", width=18)
    table.add_column("Target", width=16, style="cyan")
    table.add_column("Expected", width=12)
    table.add_column("Actual", width=12)
    table.add_column("Result", width=8, justify="center")
    table.add_column("Time", width=8, justify="right")
    table.add_column("Details", width=40)

    result_colors = {
        "PASS": "green",
        "FAIL": "red",
        "TIMEOUT": "yellow",
        "SKIP": "dim",
    }

    for r in report.step_results:
        color = result_colors.get(r.result, "white")
        table.add_row(
            str(r.step_number),
            r.action,
            r.target,
            r.expected_state,
            r.actual_state,
            f"[{color}]{r.result}[/]",
            f"{r.time_elapsed_seconds:.0f}s",
            r.details[:40] + ("..." if len(r.details) > 40 else ""),
        )

    console.print()
    console.print(table)

    # Improvements
    if report.improvements:
        console.print()
        console.print("[bold]Suggested Improvements:[/]")
        for i, improvement in enumerate(report.improvements, 1):
            console.print(f"  {i}. {improvement}")

    console.print()


# ---------------------------------------------------------------------------
# Auto-generate runbooks from simulation results
# ---------------------------------------------------------------------------


@runbook_app.command("generate")
def runbook_generate(
    model: Path = typer.Option(
        DEFAULT_MODEL_PATH,
        "--model",
        "-m",
        help="Infrastructure model file (YAML or JSON)",
    ),
    output: Path = typer.Option(
        Path("./runbooks"),
        "--output",
        "-o",
        help="Output directory for generated runbooks",
    ),
    component: str | None = typer.Option(
        None,
        "--component",
        "-c",
        help="Generate runbook for a specific component ID",
    ),
    format: str = typer.Option(
        "markdown",
        "--format",
        "-f",
        help="Output format: markdown or html",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output runbook data as JSON (no file export)",
    ),
) -> None:
    """Auto-generate incident response runbooks from simulation results.

    \b
    Runs a simulation, then generates detailed runbooks for each critical
    and warning scenario. Each runbook includes detection, diagnosis,
    mitigation, recovery, and post-incident steps plus communication
    templates.

    \b
    Examples:
        faultray runbook generate
        faultray runbook generate --model infra.yaml --output ./runbooks/
        faultray runbook generate --component web-api
        faultray runbook generate --format html
        faultray runbook generate --json
    """
    if not model.exists():
        console.print(f"[red]Model file not found: {model}[/]")
        raise typer.Exit(1)

    graph = _load_graph_from_model(model)

    from faultray.remediation.runbook_generator import RunbookGenerator
    from faultray.simulator.engine import SimulationEngine

    generator = RunbookGenerator()

    if component:
        comp = graph.get_component(component)
        if comp is None:
            console.print(f"[red]Component not found: {component}[/]")
            raise typer.Exit(1)

        if not json_output:
            console.print(f"[cyan]Generating runbook for component: {component}...[/]")

        rb = generator.generate_for_component(graph, component)

        if json_output:
            console.print_json(data=rb.to_dict())
            return

        if format == "html":
            content = generator.to_html(rb)
            ext = ".html"
        else:
            content = generator.to_markdown(rb)
            ext = ".md"

        output.mkdir(parents=True, exist_ok=True)
        out_path = output / f"{rb.id}{ext}"
        out_path.write_text(content, encoding="utf-8")
        console.print(f"[green]Runbook saved to {out_path}[/]")
        _print_runbook_summary(rb)
        return

    if not json_output:
        console.print(f"[cyan]Running simulation ({len(graph.components)} components)...[/]")

    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    if not json_output:
        console.print(
            f"[cyan]Generating runbooks for "
            f"{len(report.critical_findings)} critical + "
            f"{len(report.warnings)} warning scenarios...[/]"
        )

    library = generator.generate(graph, report)

    if json_output:
        console.print_json(data=library.to_dict())
        return

    generator.export_library(library, output, format=format)
    console.print(f"\n[green]Generated {len(library.runbooks)} runbooks in {output}[/]")
    _print_library_summary(library)


@runbook_app.command("list")
def runbook_list_cmd(
    model: Path = typer.Option(
        DEFAULT_MODEL_PATH,
        "--model",
        "-m",
        help="Infrastructure model file (YAML or JSON)",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output as JSON",
    ),
) -> None:
    """List what runbooks would be generated for a model.

    \b
    Examples:
        faultray runbook list
        faultray runbook list --model infra.yaml
        faultray runbook list --json
    """
    if not model.exists():
        console.print(f"[red]Model file not found: {model}[/]")
        raise typer.Exit(1)

    graph = _load_graph_from_model(model)

    from faultray.simulator.engine import SimulationEngine

    console.print("[cyan]Running simulation to identify scenarios...[/]")
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    actionable = report.critical_findings + report.warnings

    if json_output:
        data = [
            {
                "scenario": r.scenario.name,
                "severity": "critical" if r.is_critical else "warning",
                "risk_score": r.risk_score,
                "affected": len(r.cascade.effects),
            }
            for r in actionable
        ]
        console.print_json(data=data)
        return

    if not actionable:
        console.print("[green]No critical or warning scenarios found. No runbooks needed.[/]")
        return

    list_table = Table(title="Runbooks to Generate", show_lines=True)
    list_table.add_column("#", justify="right", style="dim")
    list_table.add_column("Scenario", style="bold")
    list_table.add_column("Severity", min_width=10)
    list_table.add_column("Risk Score", justify="right")
    list_table.add_column("Affected", justify="right")

    for i, r in enumerate(actionable, 1):
        sev = "critical" if r.is_critical else "warning"
        sev_style = "bold red" if sev == "critical" else "yellow"
        list_table.add_row(
            str(i),
            r.scenario.name,
            f"[{sev_style}]{sev.upper()}[/]",
            f"{r.risk_score:.1f}",
            str(len(r.cascade.effects)),
        )

    console.print(list_table)
    console.print(
        f"\n[bold]Total:[/] {len(actionable)} runbooks "
        f"({len(report.critical_findings)} critical, {len(report.warnings)} warning)"
    )


@runbook_app.command("coverage")
def runbook_coverage(
    model: Path = typer.Option(
        DEFAULT_MODEL_PATH,
        "--model",
        "-m",
        help="Infrastructure model file (YAML or JSON)",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output as JSON",
    ),
) -> None:
    """Show runbook coverage for the infrastructure model.

    \b
    Examples:
        faultray runbook coverage
        faultray runbook coverage --model infra.yaml
        faultray runbook coverage --json
    """
    if not model.exists():
        console.print(f"[red]Model file not found: {model}[/]")
        raise typer.Exit(1)

    graph = _load_graph_from_model(model)

    from faultray.remediation.runbook_generator import RunbookGenerator
    from faultray.simulator.engine import SimulationEngine

    console.print("[cyan]Running simulation and generating runbooks...[/]")

    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    generator = RunbookGenerator()
    library = generator.generate(graph, report)

    if json_output:
        console.print_json(data={
            "total_scenarios": len(report.results),
            "actionable_scenarios": len(report.critical_findings) + len(report.warnings),
            "runbooks_generated": len(library.runbooks),
            "coverage_percentage": library.coverage_percentage,
            "uncovered_scenarios": library.uncovered_scenarios,
        })
        return

    total = len(report.results)
    actionable = len(report.critical_findings) + len(report.warnings)

    coverage_color = (
        "green" if library.coverage_percentage >= 90
        else "yellow" if library.coverage_percentage >= 70
        else "red"
    )

    summary = (
        f"[bold]Total Scenarios:[/] {total}\n"
        f"[bold]Actionable (Critical + Warning):[/] {actionable}\n"
        f"[bold]Runbooks Generated:[/] {len(library.runbooks)}\n"
        f"[bold]Coverage:[/] [{coverage_color}]{library.coverage_percentage:.1f}%[/]"
    )

    if library.uncovered_scenarios:
        summary += "\n\n[bold yellow]Uncovered Scenarios:[/]"
        for s in library.uncovered_scenarios:
            summary += f"\n  [dim]\u2514 {s}[/]"

    console.print(Panel(
        summary,
        title="[bold]Runbook Coverage[/]",
        border_style="blue",
    ))


# ---------------------------------------------------------------------------
# Display helpers for generated runbooks
# ---------------------------------------------------------------------------


def _print_runbook_summary(rb) -> None:
    """Print a summary of a single generated runbook."""
    sev_style = "bold red" if rb.severity == "critical" else "yellow"
    phases = {}
    for step in rb.steps:
        phases.setdefault(step.phase, []).append(step)

    summary_lines = [
        f"[bold]Title:[/] {rb.title}",
        f"[bold]Severity:[/] [{sev_style}]{rb.severity.upper()}[/]",
        f"[bold]Blast Radius:[/] {rb.blast_radius} components",
        f"[bold]Recovery Time:[/] {rb.estimated_recovery_time}",
        f"[bold]Steps:[/] {len(rb.steps)}",
    ]

    phase_counts = []
    for phase_name, phase_steps in phases.items():
        phase_counts.append(f"{phase_name}: {len(phase_steps)}")
    summary_lines.append(f"[bold]Phases:[/] {', '.join(phase_counts)}")

    if rb.communication_templates:
        channels = {t.channel for t in rb.communication_templates}
        summary_lines.append(f"[bold]Communication:[/] {', '.join(channels)}")

    console.print(Panel(
        "\n".join(summary_lines),
        title=f"[bold]{rb.title}[/]",
        border_style="blue",
    ))


def _print_library_summary(library) -> None:
    """Print a summary of the runbook library."""
    lib_table = Table(title="Generated Runbooks", show_lines=True)
    lib_table.add_column("ID", style="dim")
    lib_table.add_column("Title", style="bold")
    lib_table.add_column("Severity")
    lib_table.add_column("Blast", justify="right")
    lib_table.add_column("Steps", justify="right")
    lib_table.add_column("Recovery")

    for rb in library.runbooks:
        sev_style = "bold red" if rb.severity == "critical" else "yellow"
        lib_table.add_row(
            rb.id,
            rb.title,
            f"[{sev_style}]{rb.severity.upper()}[/]",
            str(rb.blast_radius),
            str(len(rb.steps)),
            rb.estimated_recovery_time,
        )

    console.print(lib_table)

    coverage_color = (
        "green" if library.coverage_percentage >= 90
        else "yellow" if library.coverage_percentage >= 70
        else "red"
    )
    console.print(
        f"\n[bold]Coverage:[/] [{coverage_color}]{library.coverage_percentage:.1f}%[/] "
        f"({library.total_scenarios_covered} scenarios covered)"
    )
