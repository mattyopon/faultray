"""CLI commands for the Chaos Regression Gate."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import app, console

gate_app = typer.Typer(
    name="gate",
    help="Chaos Regression Gate - CI/CD gate for resilience regression detection",
    no_args_is_help=True,
)
app.add_typer(gate_app, name="gate")


@gate_app.command("check")
def gate_check(
    before: Path = typer.Option(..., "--before", "-b", help="Before model file (JSON/YAML)"),
    after: Path = typer.Option(..., "--after", "-a", help="After model file (JSON/YAML)"),
    min_score: float = typer.Option(60.0, "--min-score", help="Minimum resilience score"),
    max_drop: float = typer.Option(5.0, "--max-drop", help="Maximum allowed score drop"),
    block_critical: bool = typer.Option(True, "--block-critical/--no-block-critical",
                                         help="Block on new critical findings"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON result"),
    sarif: Path | None = typer.Option(None, "--sarif", help="Export SARIF to file"),
    pr_comment: bool = typer.Option(False, "--pr-comment", help="Output as PR comment markdown"),
) -> None:
    """Compare before/after models and check for resilience regression.

    Exit code 0 = passed, 1 = blocked. Designed for CI/CD pipelines.

    Examples:
        # Basic regression check
        faultray gate check --before model-v1.json --after model-v2.json

        # With custom thresholds
        faultray gate check --before old.yaml --after new.yaml --min-score 70 --max-drop 3

        # JSON output for CI parsing
        faultray gate check --before old.json --after new.json --json

        # Export SARIF for GitHub Security tab
        faultray gate check --before old.json --after new.json --sarif results.sarif

        # Generate PR comment
        faultray gate check --before old.json --after new.json --pr-comment
    """
    from faultray.integrations.regression_gate import ChaosRegressionGate

    for path, label in [(before, "before"), (after, "after")]:
        if not path.exists():
            console.print(f"[red]{label.title()} model not found: {path}[/]")
            raise typer.Exit(1)

    gate = ChaosRegressionGate(
        min_score=min_score,
        max_score_drop=max_drop,
        block_on_new_critical=block_critical,
    )

    if not json_output and not pr_comment:
        console.print("[cyan]Running regression gate check...[/]")

    result = gate.check_from_files(before, after)

    # JSON output
    if json_output:
        data = {
            "passed": result.passed,
            "before_score": result.before_score,
            "after_score": result.after_score,
            "score_delta": result.score_delta,
            "new_critical_findings": result.new_critical_findings,
            "new_warnings": result.new_warnings,
            "resolved_findings": result.resolved_findings,
            "blocking_reason": result.blocking_reason,
            "recommendation": result.recommendation,
        }
        console.print_json(json.dumps(data, indent=2))
        if not result.passed:
            raise typer.Exit(1)
        return

    # PR comment output
    if pr_comment:
        comment = gate.generate_pr_comment(result)
        console.print(comment)
        if not result.passed:
            raise typer.Exit(1)
        return

    # SARIF export
    if sarif is not None:
        sarif_data = gate.to_sarif(result)
        sarif.parent.mkdir(parents=True, exist_ok=True)
        sarif.write_text(json.dumps(sarif_data, indent=2))
        console.print(f"[green]SARIF exported to {sarif}[/]")

    # Rich formatted output
    _print_gate_result(result, console)

    if not result.passed:
        raise typer.Exit(1)


@gate_app.command("terraform-plan")
def gate_terraform_plan(
    plan: Path = typer.Argument(..., help="Terraform plan file (JSON model)"),
    model: Path = typer.Option(..., "--model", "-m", help="Current infrastructure model"),
    min_score: float = typer.Option(60.0, "--min-score", help="Minimum resilience score"),
    max_drop: float = typer.Option(5.0, "--max-drop", help="Maximum allowed score drop"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON result"),
) -> None:
    """Evaluate a terraform plan against the current infrastructure model.

    Exit code 0 = passed, 1 = blocked.

    Examples:
        faultray gate terraform-plan plan.json --model current.json
        faultray gate terraform-plan plan.json --model current.json --min-score 70
    """
    from faultray.integrations.regression_gate import ChaosRegressionGate

    if not model.exists():
        console.print(f"[red]Current model not found: {model}[/]")
        raise typer.Exit(1)
    if not plan.exists():
        console.print(f"[red]Plan file not found: {plan}[/]")
        raise typer.Exit(1)

    gate = ChaosRegressionGate(
        min_score=min_score,
        max_score_drop=max_drop,
    )

    if not json_output:
        console.print("[cyan]Evaluating terraform plan...[/]")

    result = gate.check_terraform_plan(plan, model)

    if json_output:
        data = {
            "passed": result.passed,
            "before_score": result.before_score,
            "after_score": result.after_score,
            "score_delta": result.score_delta,
            "blocking_reason": result.blocking_reason,
            "recommendation": result.recommendation,
        }
        console.print_json(json.dumps(data, indent=2))
        if not result.passed:
            raise typer.Exit(1)
        return

    _print_gate_result(result, console)

    if not result.passed:
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _print_gate_result(result, con: Console) -> None:
    """Print a gate check result with Rich formatting."""
    if result.passed:
        status = "[bold green]PASSED[/]"
        border = "green"
    else:
        status = "[bold red]BLOCKED[/]"
        border = "red"

    delta_sign = "+" if result.score_delta >= 0 else ""
    delta_color = "green" if result.score_delta >= 0 else "red"

    summary = (
        f"[bold]Status:[/] {status}\n\n"
        f"[bold]Before Score:[/] {result.before_score:.1f}\n"
        f"[bold]After Score:[/] {result.after_score:.1f}\n"
        f"[bold]Delta:[/] [{delta_color}]{delta_sign}{result.score_delta:.1f}[/]"
    )

    if result.blocking_reason:
        summary += f"\n\n[bold red]Blocking Reason:[/] {result.blocking_reason}"

    con.print()
    con.print(Panel(summary, title="[bold]Chaos Regression Gate[/]", border_style=border))

    # Findings table
    has_findings = (
        result.new_critical_findings
        or result.new_warnings
        or result.resolved_findings
    )

    if has_findings:
        table = Table(title="Findings", show_header=True)
        table.add_column("Type", width=12, justify="center")
        table.add_column("Finding", width=60)

        for finding in result.new_critical_findings:
            table.add_row("[red]CRITICAL[/]", finding)
        for warning in result.new_warnings:
            table.add_row("[yellow]WARNING[/]", warning)
        for resolved in result.resolved_findings:
            table.add_row("[green]RESOLVED[/]", resolved)

        con.print()
        con.print(table)

    # Recommendation
    if result.recommendation:
        con.print()
        con.print(f"[bold]Recommendation:[/] {result.recommendation}")
