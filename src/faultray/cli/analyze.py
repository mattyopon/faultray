# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Analyze and DORA report CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

from faultray.cli.main import (
    _print_ai_analysis,
    app,
    console,
)
from faultray.reporter.report import print_simulation_report
from faultray.simulator.engine import SimulationEngine


@app.command()
def analyze(
    yaml_file: Path = typer.Argument(..., help="Infrastructure YAML file"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """AI-powered analysis with recommendations (AI analysis + recommendations).

    Examples:
        # Run AI analysis on YAML model
        faultray analyze infra.yaml

        # JSON output
        faultray analyze infra.yaml --json
    """
    import json as json_mod

    from faultray.ai.analyzer import FaultRayAnalyzer
    from faultray.model.loader import load_yaml

    if not yaml_file.exists():
        console.print(f"[red]File not found: {yaml_file}[/]", err=True)
        raise typer.Exit(1)

    if not json_output:
        console.print(f"[cyan]Loading infrastructure from {yaml_file}...[/]")
    try:
        graph = load_yaml(yaml_file)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/]", err=True)
        raise typer.Exit(1)

    if not json_output:
        console.print(f"[cyan]Running chaos simulation ({len(graph.components)} components)...[/]")
    engine = SimulationEngine(graph)
    sim_report = engine.run_all_defaults()

    if not json_output:
        console.print("[cyan]Running AI analysis...[/]")
    ai_analyzer = FaultRayAnalyzer()
    ai_report = ai_analyzer.analyze(graph, sim_report)

    if json_output:
        import dataclasses

        ai_dict = dataclasses.asdict(ai_report)
        # Add simulation metrics expected by CI/CD pipelines (resilience-gate.yml)
        critical_count = sum(1 for r in sim_report.results if r.is_critical)
        warning_count = sum(1 for r in sim_report.results if r.is_warning)
        passed_count = sum(
            1 for r in sim_report.results if not r.is_critical and not r.is_warning
        )
        ci_dict = {
            "resilience_score": sim_report.resilience_score,
            "critical": critical_count,
            "warning": warning_count,
            "passed": passed_count,
            "total_scenarios": len(sim_report.results),
            **ai_dict,
        }
        print(json_mod.dumps(ci_dict, indent=2, default=str))
    else:
        print_simulation_report(sim_report, console, graph=graph)
        _print_ai_analysis(ai_report, console)


@app.command()
def dora_report(
    yaml_file: Path = typer.Argument(..., help="Infrastructure YAML file"),
    output: Path = typer.Option(Path("dora-report.html"), "--output", "-o", help="Output HTML file path"),
) -> None:
    """Generate DORA compliance report (DORA compliance report generation).

    Examples:
        # Generate DORA report
        faultray dora-report infra.yaml

        # Custom output path
        faultray dora-report infra.yaml --output my-dora-report.html
    """
    from faultray.ai.analyzer import FaultRayAnalyzer
    from faultray.model.loader import load_yaml
    from faultray.reporter.compliance import generate_dora_report

    if not yaml_file.exists():
        console.print(f"[red]File not found: {yaml_file}[/]")
        raise typer.Exit(1)

    console.print(f"[cyan]Loading infrastructure from {yaml_file}...[/]")
    try:
        graph = load_yaml(yaml_file)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)

    console.print(f"[cyan]Running chaos simulation ({len(graph.components)} components)...[/]")
    engine = SimulationEngine(graph)
    sim_report = engine.run_all_defaults()

    console.print("[cyan]Running AI analysis...[/]")
    ai_analyzer = FaultRayAnalyzer()
    ai_report = ai_analyzer.analyze(graph, sim_report)

    console.print("[cyan]Generating DORA compliance report...[/]")
    result_path = generate_dora_report(graph, sim_report, ai_report, output)
    console.print(f"\n[green]DORA compliance report saved to {result_path}[/]")


@app.command()
def executive(
    yaml_file: Path = typer.Argument(..., help="Infrastructure YAML file"),
    html: Path = typer.Option(None, "--html", help="Export executive summary HTML report"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Generate executive summary report for C-level stakeholders.

    Examples:
        # Generate executive summary
        faultray executive infra.yaml

        # Export as HTML
        faultray executive infra.yaml --html executive-summary.html

        # JSON output
        faultray executive infra.yaml --json
    """
    import dataclasses
    import json as json_mod

    from faultray.model.loader import load_yaml
    from faultray.reporter.executive_report import (
        generate_executive_summary,
        render_executive_html,
    )
    from faultray.simulator.cost_engine import CostImpactEngine

    if not yaml_file.exists():
        console.print(f"[red]File not found: {yaml_file}[/]")
        raise typer.Exit(1)

    console.print(f"[cyan]Loading infrastructure from {yaml_file}...[/]")
    try:
        graph = load_yaml(yaml_file)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)

    # Run static simulation
    console.print(f"[cyan]Running static simulation ({len(graph.components)} components)...[/]")
    engine = SimulationEngine(graph)
    static_report = engine.run_all_defaults()

    # Run cost analysis
    console.print("[cyan]Running cost impact analysis...[/]")
    cost_engine = CostImpactEngine(graph)
    cost_report = cost_engine.analyze(static_report)

    # Run compliance checks
    console.print("[cyan]Running compliance checks...[/]")
    from faultray.simulator.compliance_engine import ComplianceEngine

    compliance_engine = ComplianceEngine(graph)
    compliance_reports = compliance_engine.check_all()

    # Generate executive summary
    console.print("[cyan]Generating executive summary...[/]")
    summary = generate_executive_summary(
        graph=graph,
        static_report=static_report,
        cost_report=cost_report,
        compliance_reports=compliance_reports,
    )

    if json_output:
        summary_dict = dataclasses.asdict(summary)
        console.print_json(json_mod.dumps(summary_dict, indent=2, default=str))
    else:
        # Print Rich summary to console
        from rich.panel import Panel
        from rich.table import Table

        status_colors = {"GREEN": "green", "YELLOW": "yellow", "RED": "red"}
        overall_color = status_colors.get(summary.overall_status, "white")

        console.print()
        console.print(Panel(
            f"[bold]{summary.headline}[/]",
            title="[bold]Executive Summary[/]",
            border_style=overall_color,
        ))

        # Traffic lights
        lights_text = (
            f"  Availability: [{status_colors.get(summary.availability_status, 'white')}]"
            f"{summary.availability_status}[/]  |  "
            f"Security: [{status_colors.get(summary.security_status, 'white')}]"
            f"{summary.security_status}[/]  |  "
            f"Cost Risk: [{status_colors.get(summary.cost_risk_status, 'white')}]"
            f"{summary.cost_risk_status}[/]  |  "
            f"Compliance: [{status_colors.get(summary.compliance_status, 'white')}]"
            f"{summary.compliance_status}[/]"
        )
        console.print(lights_text)
        console.print()

        # Key metrics
        console.print(f"  Scenarios Tested: [bold]{summary.scenarios_tested}[/]")
        console.print(f"  Scenarios Passed: [bold]{summary.scenarios_passed_percent:.0f}%[/]")
        console.print(f"  Availability: [bold]{summary.availability_nines:.2f} nines[/]")
        slo_color = "green" if summary.slo_achievable else "red"
        console.print(f"  SLO Achievable: [{slo_color}]{summary.slo_achievable}[/]")
        console.print(f"  Est. Annual Risk: [bold]${summary.estimated_annual_risk:,.0f}[/]")
        console.print()

        # Top risks
        if summary.top_risks:
            console.print("[bold]Top Risks:[/]")
            for i, risk in enumerate(summary.top_risks, 1):
                console.print(f"  {i}. [bold]{risk.get('name', '')}[/]")
                console.print(f"     Impact: {risk.get('impact', '')}")
                console.print(f"     Action: {risk.get('recommendation', '')}")
            console.print()

        # ROI table
        if summary.roi_items:
            roi_table = Table(title="Investment Recommendations", show_header=True)
            roi_table.add_column("Action", width=30)
            roi_table.add_column("Annual Cost", justify="right", width=14)
            roi_table.add_column("Risk Reduction", justify="right", width=14)
            roi_table.add_column("ROI", justify="right", width=10)

            for item in summary.roi_items:
                roi_pct = item.get("roi_percent", 0)
                roi_color = "green" if roi_pct > 0 else "red"
                roi_table.add_row(
                    item.get("action", ""),
                    f"${item.get('cost', 0):,.0f}",
                    f"${item.get('risk_reduction', 0):,.0f}",
                    f"[{roi_color}]{roi_pct:+.0f}%[/]",
                )
            console.print(roi_table)

    # HTML export
    if html:
        html_content = render_executive_html(summary)
        html.parent.mkdir(parents=True, exist_ok=True)
        html.write_text(html_content, encoding="utf-8")
        console.print(f"\n[green]Executive summary HTML saved to {html}[/]")
