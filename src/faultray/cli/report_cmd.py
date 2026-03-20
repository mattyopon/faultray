# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""CLI commands for report generation."""

from __future__ import annotations

from pathlib import Path

import typer

from faultray.cli.main import (
    DEFAULT_MODEL_PATH,
    _load_graph_for_analysis,
    app,
    console,
)


@app.command(name="report")
def report_command(
    report_type: str = typer.Argument(
        ...,
        help="Report type: executive, compliance",
    ),
    model: Path = typer.Argument(
        None,
        help="Model file path (JSON or YAML). Defaults to faultray-model.json.",
    ),
    company: str = typer.Option(
        "Your Organization",
        "--company",
        "-c",
        help="Company name for the report.",
    ),
    output: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path (HTML). Defaults to <type>-report.html.",
    ),
    framework: str = typer.Option(
        None,
        "--framework",
        "-f",
        help="Compliance framework (dora, soc2, iso27001, pci_dss, nist_csf, hipaa). For compliance report only.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output as JSON (compliance report only).",
    ),
) -> None:
    """Generate reports (executive, compliance).

    Examples:
        # Generate executive report
        faultray report executive model.yaml --company "Acme Corp" --output report.html

        # Generate compliance report (all frameworks)
        faultray report compliance model.yaml --json

        # Generate compliance report (specific framework)
        faultray report compliance model.yaml --framework dora --json
    """
    resolved_model = model if model is not None else DEFAULT_MODEL_PATH
    graph = _load_graph_for_analysis(resolved_model, yaml_file=None)

    if not graph.components:
        console.print("[red]No components found in the model.[/]")
        raise typer.Exit(1)

    if report_type == "executive":
        _generate_executive_report(graph, company, output)
    elif report_type == "compliance":
        _generate_compliance_report(graph, framework, output, json_output)
    else:
        console.print(f"[red]Unknown report type: {report_type}[/]")
        console.print("[dim]Available types: executive, compliance[/]")
        raise typer.Exit(1)


def _generate_executive_report(graph, company_name: str, output: Path | None) -> None:
    """Generate the executive PDF-style HTML report."""
    from faultray.ai.analyzer import FaultRayAnalyzer
    from faultray.reporter.executive_pdf import ExecutiveReportGenerator
    from faultray.simulator.engine import SimulationEngine

    console.print("[bold]Running simulation...[/]")
    engine = SimulationEngine(graph)
    sim_report = engine.run_all_defaults()

    console.print("[bold]Running AI analysis...[/]")
    analyzer = FaultRayAnalyzer()
    ai_report = analyzer.analyze(graph, sim_report)

    console.print("[bold]Generating executive report...[/]")
    generator = ExecutiveReportGenerator()
    html_content = generator.generate(
        graph, sim_report, ai_report,
        company_name=company_name,
    )

    output_path = output or Path("executive-report.html")
    output_path.write_text(html_content, encoding="utf-8")

    console.print(f"\n[green]Executive report saved to {output_path}[/]")
    console.print(f"  Company: [cyan]{company_name}[/]")
    console.print(f"  Resilience Score: [bold]{sim_report.resilience_score:.1f}/100[/]")
    console.print(f"  Critical Findings: [red]{len(sim_report.critical_findings)}[/]")
    console.print(f"  Recommendations: {len(ai_report.recommendations)}")
    console.print("\n[dim]Open in a browser and print to PDF (Ctrl+P) for a polished document.[/]")


def _generate_compliance_report(graph, framework: str | None, output: Path | None, json_output: bool) -> None:
    """Generate a compliance monitoring report."""
    import json as json_lib

    from faultray.simulator.compliance_monitor import ComplianceFramework, ComplianceMonitor

    monitor = ComplianceMonitor()

    if framework:
        # Map user input to enum
        fw_map = {
            "dora": ComplianceFramework.DORA,
            "soc2": ComplianceFramework.SOC2,
            "iso27001": ComplianceFramework.ISO27001,
            "pci_dss": ComplianceFramework.PCI_DSS,
            "nist_csf": ComplianceFramework.NIST_CSF,
            "hipaa": ComplianceFramework.HIPAA,
        }
        fw = fw_map.get(framework.lower())
        if fw is None:
            console.print(f"[red]Unknown framework: {framework}[/]")
            console.print(f"[dim]Available: {', '.join(fw_map.keys())}[/]")
            raise typer.Exit(1)

        monitor.track(graph)
        snapshot = monitor.assess(graph, fw)
        package = monitor.generate_evidence_package(fw)

        if json_output:
            console.print_json(data=package)
            return

        # Print summary
        console.print(f"\n[bold]{fw.value.upper()} Compliance Report[/]")
        console.print(f"  Total Controls: {snapshot.total_controls}")
        console.print(f"  [green]Compliant: {snapshot.compliant}[/]")
        console.print(f"  [yellow]Partial: {snapshot.partial}[/]")
        console.print(f"  [red]Non-Compliant: {snapshot.non_compliant}[/]")
        console.print(f"  Compliance: [bold]{snapshot.compliance_percentage:.1f}%[/]")

        for ctrl in snapshot.controls:
            color = {
                "compliant": "green",
                "partial": "yellow",
                "non_compliant": "red",
                "not_applicable": "dim",
                "unknown": "dim",
            }.get(ctrl.status.value, "white")
            console.print(f"  [{color}]{ctrl.control_id}: {ctrl.title} ({ctrl.status.value})[/]")
    else:
        # All frameworks
        monitor.track(graph)
        results = monitor.assess_all(graph)

        if json_output:
            all_packages = {}
            for fw in ComplianceFramework:
                all_packages[fw.value] = monitor.generate_evidence_package(fw)
            console.print_json(data=all_packages)
            return

        console.print("\n[bold]Compliance Report (All Frameworks)[/]\n")
        for fw, snapshot in results.items():
            color = "green" if snapshot.compliance_percentage >= 80 else "yellow" if snapshot.compliance_percentage >= 50 else "red"
            console.print(
                f"  [{color}]{fw.value.upper():10s}[/]  "
                f"{snapshot.compliance_percentage:5.1f}%  "
                f"({snapshot.compliant}/{snapshot.total_controls} compliant)"
            )

    if output:
        if not json_output:
            monitor.track(graph)
            all_packages = {}
            for fw in ComplianceFramework:
                all_packages[fw.value] = monitor.generate_evidence_package(fw)
            output.write_text(
                json_lib.dumps(all_packages, indent=2, default=str),
                encoding="utf-8",
            )
            console.print(f"\n[green]Compliance report saved to {output}[/]")
