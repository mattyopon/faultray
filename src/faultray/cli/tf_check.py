# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI commands for Terraform provider, custom scoring, and incident correlation."""

from __future__ import annotations

from pathlib import Path

import typer

from faultray.cli.main import (
    DEFAULT_MODEL_PATH,
    _load_graph_for_analysis,
    app,
    console,
)


@app.command("tf-check")
def tf_check(
    plan_file: Path = typer.Argument(..., help="Path to terraform plan JSON file"),
    fail_on_regression: bool = typer.Option(
        False, "--fail-on-regression",
        help="Exit with code 1 if resilience score decreases",
    ),
    min_score: float = typer.Option(
        60.0, "--min-score",
        help="Minimum resilience score threshold",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON summary"),
    financial: bool = typer.Option(
        False, "--financial",
        help="Show financial impact of the Terraform change.",
    ),
) -> None:
    """Analyze a Terraform plan for resilience impact.

    Parses the terraform plan, builds before/after infrastructure graphs,
    runs FaultRay simulation on both, and compares resilience scores.

    Examples:
        # Basic analysis
        faultray tf-check plan.json

        # Fail CI if resilience drops
        faultray tf-check plan.json --fail-on-regression

        # Set minimum score threshold
        faultray tf-check plan.json --min-score 70

        # JSON output for CI/CD
        faultray tf-check plan.json --json

        # Show financial impact of the change
        faultray tf-check plan.json --financial
    """
    from faultray.integrations.terraform_provider import TerraformFaultRayProvider

    if not plan_file.exists():
        console.print(f"[red]Plan file not found: {plan_file}[/]")
        raise typer.Exit(1)

    if not json_output:
        console.print(f"[cyan]Analyzing Terraform plan: {plan_file}...[/]")

    provider = TerraformFaultRayProvider()

    try:
        analysis = provider.analyze_plan(plan_file)
    except Exception as exc:
        console.print(f"[red]Failed to analyze plan: {exc}[/]")
        raise typer.Exit(1)

    if json_output:
        console.print_json(data={
            "plan_file": analysis.plan_file,
            "resources_added": analysis.resources_added,
            "resources_changed": analysis.resources_changed,
            "resources_destroyed": analysis.resources_destroyed,
            "score_before": analysis.score_before,
            "score_after": analysis.score_after,
            "score_delta": analysis.score_delta,
            "new_risks": analysis.new_risks,
            "resolved_risks": analysis.resolved_risks,
            "recommendation": analysis.recommendation,
        })
    else:
        _print_tf_analysis(analysis)

    # Financial impact comparison (when --financial is set)
    if financial and not json_output:
        try:
            from faultray.simulator.financial_impact import calculate_financial_impact

            # Build before/after graphs from the provider analysis
            before_graph = getattr(analysis, "before_graph", None)
            after_graph = getattr(analysis, "after_graph", None)

            if before_graph is not None and after_graph is not None:
                before_fin = calculate_financial_impact(before_graph)
                after_fin = calculate_financial_impact(after_graph)

                before_loss = before_fin.total_annual_loss
                after_loss = after_fin.total_annual_loss
                delta_loss = after_loss - before_loss

                if delta_loss > 0:
                    delta_msg = f"This change [red]increases[/] annual risk by ${delta_loss:,.0f}"
                elif delta_loss < 0:
                    f"[green]-${abs(delta_loss):,.0f}[/]"
                    delta_msg = f"This change [green]reduces[/] annual risk by ${abs(delta_loss):,.0f}"
                else:
                    delta_msg = "No change in financial risk"

                from rich.panel import Panel
                console.print()
                console.print(Panel(
                    f"Score Before: [bold]{analysis.score_before:.0f}/100[/] "
                    f"(${before_loss:,.0f}/year risk)\n"
                    f"Score After:  [bold]{analysis.score_after:.0f}/100[/] "
                    f"(${after_loss:,.0f}/year risk)\n"
                    f"{delta_msg}",
                    title="[bold]Financial Impact of Change[/]",
                    border_style="red" if delta_loss > 0 else "green",
                ))
            else:
                console.print(
                    "[dim]Financial impact comparison requires before/after "
                    "graphs from the Terraform provider.[/]"
                )
        except Exception as exc:
            console.print(f"[dim]Financial impact unavailable: {exc}[/]")

    # Check for regression
    exit_code = 0
    if fail_on_regression and analysis.score_delta < 0:
        if not json_output:
            console.print(
                f"\n[red]REGRESSION DETECTED: resilience score dropped by "
                f"{abs(analysis.score_delta):.1f} points[/]"
            )
        exit_code = 1

    # Check minimum score
    if analysis.score_after < min_score:
        if not json_output:
            console.print(
                f"\n[red]POLICY VIOLATION: resilience score {analysis.score_after:.1f} "
                f"is below minimum {min_score:.1f}[/]"
            )
        exit_code = 1

    if exit_code:
        raise typer.Exit(exit_code)


@app.command("score-custom")
def score_custom(
    model: Path = typer.Argument(
        DEFAULT_MODEL_PATH, help="Model file path (JSON or YAML)"
    ),
    policy: Path = typer.Option(
        ..., "--policy", "-p",
        help="Path to scoring policy YAML file",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON summary"),
) -> None:
    """Evaluate infrastructure against custom scoring rules.

    Define your own scoring criteria in a YAML policy file.

    Examples:
        # Evaluate with a custom policy
        faultray score-custom my-model.json --policy scoring-policy.yaml

        # JSON output
        faultray score-custom my-model.json --policy scoring-policy.yaml --json
    """
    from faultray.scoring import CustomScoringEngine

    graph = _load_graph_for_analysis(model, yaml_file=None)

    if not policy.exists():
        console.print(f"[red]Policy file not found: {policy}[/]")
        raise typer.Exit(1)

    if not json_output:
        console.print(f"[cyan]Loading scoring policy from {policy}...[/]")

    try:
        engine = CustomScoringEngine.from_yaml(graph, policy)
    except (ValueError, Exception) as exc:
        console.print(f"[red]Failed to load policy: {exc}[/]")
        raise typer.Exit(1)

    result = engine.evaluate()

    if json_output:
        console.print_json(data={
            "model_name": result.model_name,
            "total_score": result.total_score,
            "weighted_score": result.weighted_score,
            "rules": result.rules,
        })
    else:
        _print_scoring_result(result)


@app.command("correlate")
def correlate(
    model: Path = typer.Argument(
        DEFAULT_MODEL_PATH, help="Model file path (JSON or YAML)"
    ),
    incidents: Path | None = typer.Option(
        None, "--incidents", "-i",
        help="Path to incidents CSV file",
    ),
    pagerduty_key: str | None = typer.Option(
        None, "--pagerduty-key",
        help="PagerDuty API key for incident import",
    ),
    days: int = typer.Option(
        90, "--days",
        help="Number of days to look back for PagerDuty incidents",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON summary"),
) -> None:
    """Correlate real incidents with FaultRay simulation scenarios.

    Validates simulation accuracy by checking which real incidents were
    predicted by FaultRay's chaos scenarios.

    Examples:
        # From CSV file
        faultray correlate my-model.json --incidents incidents.csv

        # From PagerDuty
        faultray correlate my-model.json --pagerduty-key <key> --days 90

        # JSON output
        faultray correlate my-model.json --incidents incidents.csv --json
    """
    from faultray.integrations.incident_correlator import IncidentCorrelator

    if incidents is None and pagerduty_key is None:
        console.print("[red]Must provide either --incidents or --pagerduty-key[/]")
        raise typer.Exit(1)

    graph = _load_graph_for_analysis(model, yaml_file=None)

    if not json_output:
        console.print("[cyan]Running simulation for correlation...[/]")

    correlator = IncidentCorrelator(graph)

    # Import incidents
    incident_records = []
    if incidents is not None:
        if not incidents.exists():
            console.print(f"[red]Incidents file not found: {incidents}[/]")
            raise typer.Exit(1)
        if not json_output:
            console.print(f"[cyan]Loading incidents from {incidents}...[/]")
        incident_records = correlator.import_from_csv(incidents)
    elif pagerduty_key is not None:
        if not json_output:
            console.print(f"[cyan]Importing incidents from PagerDuty (last {days} days)...[/]")
        try:
            incident_records = correlator.import_from_pagerduty(pagerduty_key, days=days)
        except Exception as exc:
            console.print(f"[red]Failed to import from PagerDuty: {exc}[/]")
            raise typer.Exit(1)

    if not incident_records:
        console.print("[yellow]No incidents found.[/]")
        raise typer.Exit(0)

    if not json_output:
        console.print(
            f"[cyan]Correlating {len(incident_records)} incidents against simulation...[/]"
        )

    report = correlator.correlate(incident_records)

    if json_output:
        console.print_json(data={
            "total_incidents": report.total_incidents,
            "predicted_count": report.predicted_count,
            "prediction_rate": report.prediction_rate,
            "severity_accuracy": report.severity_accuracy,
            "unpredicted_count": len(report.unpredicted_incidents),
            "recommendations": report.recommendations,
        })
    else:
        _print_correlation_report(report)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _print_tf_analysis(analysis) -> None:
    """Print Terraform plan analysis with Rich formatting."""
    from rich.panel import Panel
    from rich.table import Table

    # Score comparison
    delta = analysis.score_delta
    if delta > 0:
        delta_str = f"[green]+{delta:.1f}[/]"
    elif delta < 0:
        delta_str = f"[red]{delta:.1f}[/]"
    else:
        delta_str = "[dim]0.0[/]"

    # Recommendation color
    rec_colors = {
        "safe to apply": "green",
        "review recommended": "yellow",
        "high risk": "red",
    }
    rec_color = rec_colors.get(analysis.recommendation, "white")

    summary = (
        f"[bold]Terraform Plan Analysis[/]\n\n"
        f"  Resources Added:     [green]+{analysis.resources_added}[/]\n"
        f"  Resources Changed:   [yellow]{analysis.resources_changed}[/]\n"
        f"  Resources Destroyed: [red]-{analysis.resources_destroyed}[/]\n\n"
        f"  Score Before: [bold]{analysis.score_before:.1f}[/]\n"
        f"  Score After:  [bold]{analysis.score_after:.1f}[/] ({delta_str})\n\n"
        f"  Recommendation: [{rec_color}][bold]{analysis.recommendation.upper()}[/bold][/]"
    )

    console.print()
    console.print(Panel(
        summary,
        title="[bold]FaultRay Terraform Check[/]",
        border_style=rec_color,
    ))

    # New risks
    if analysis.new_risks:
        console.print("\n[bold red]New Risks:[/]")
        for risk in analysis.new_risks:
            console.print(f"  [red]-[/] {risk}")

    # Resolved risks
    if analysis.resolved_risks:
        console.print("\n[bold green]Resolved Risks:[/]")
        for risk in analysis.resolved_risks:
            console.print(f"  [green]+[/] {risk}")

    # Changes table
    if analysis.changes:
        table = Table(title="Resource Changes", show_header=True)
        table.add_column("Address", style="cyan", width=35)
        table.add_column("Actions", width=15)
        table.add_column("Risk", justify="center", width=6)

        for change in analysis.changes[:20]:
            actions = ", ".join(change.get("actions", []))
            risk = change.get("risk_level", 0)
            if risk >= 8:
                risk_str = f"[red]{risk}[/]"
            elif risk >= 5:
                risk_str = f"[yellow]{risk}[/]"
            else:
                risk_str = f"[green]{risk}[/]"
            table.add_row(
                change.get("address", ""),
                actions,
                risk_str,
            )

        console.print()
        console.print(table)


def _print_scoring_result(result) -> None:
    """Print custom scoring result with Rich formatting."""
    from rich.panel import Panel
    from rich.table import Table

    # Overall score color
    if result.total_score >= 80:
        score_color = "green"
    elif result.total_score >= 50:
        score_color = "yellow"
    else:
        score_color = "red"

    summary = (
        f"[bold]Custom Scoring: {result.model_name}[/]\n\n"
        f"  Total Score: [{score_color}][bold]{result.total_score:.1f}/100[/bold][/]\n"
        f"  Weighted Score: {result.weighted_score:.1f}"
    )

    console.print()
    console.print(Panel(summary, border_style=score_color))

    # Rules table
    table = Table(title="Scoring Rules", show_header=True)
    table.add_column("Rule", style="cyan", width=30)
    table.add_column("Score", justify="right", width=8)
    table.add_column("Weight", justify="right", width=8)
    table.add_column("Status", justify="center", width=8)

    for rule in result.rules:
        score = rule.get("score", 0)
        passed = rule.get("passed", False)
        status = "[green]PASS[/]" if passed else "[red]FAIL[/]"
        table.add_row(
            rule.get("name", ""),
            f"{score:.1f}",
            f"{rule.get('weight', 1.0):.1f}",
            status,
        )

    console.print(table)


def _print_correlation_report(report) -> None:
    """Print incident correlation report with Rich formatting."""
    from rich.panel import Panel
    from rich.table import Table

    # Prediction rate color
    rate = report.prediction_rate
    if rate >= 0.8:
        rate_color = "green"
    elif rate >= 0.5:
        rate_color = "yellow"
    else:
        rate_color = "red"

    summary = (
        f"[bold]Incident Correlation Report[/]\n\n"
        f"  Total Incidents:    {report.total_incidents}\n"
        f"  Predicted:          [{rate_color}]{report.predicted_count}[/] "
        f"({rate * 100:.1f}%)\n"
        f"  Unpredicted:        {len(report.unpredicted_incidents)}\n"
        f"  Severity Accuracy:  {report.severity_accuracy * 100:.1f}%"
    )

    console.print()
    console.print(Panel(summary, border_style=rate_color))

    # Unpredicted incidents
    if report.unpredicted_incidents:
        table = Table(title="Unpredicted Incidents", show_header=True)
        table.add_column("ID", width=10)
        table.add_column("Title", style="cyan", width=30)
        table.add_column("Severity", width=10)
        table.add_column("Gap", width=35)

        for cr in report.unpredicted_incidents[:20]:
            sev_color = {"critical": "red", "major": "yellow"}.get(
                cr.incident.severity, "dim"
            )
            table.add_row(
                cr.incident.id,
                cr.incident.title[:30],
                f"[{sev_color}]{cr.incident.severity}[/]",
                (cr.coverage_gap or "")[:35],
            )

        console.print()
        console.print(table)

    # Recommendations
    if report.recommendations:
        console.print("\n[bold]Recommendations:[/]")
        for rec in report.recommendations:
            console.print(f"  - {rec}")
