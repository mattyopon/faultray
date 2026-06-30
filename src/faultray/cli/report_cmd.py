# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

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
        help="Report type: executive, compliance, dora",
    ),
    model: Path | None = typer.Argument(
        None,
        help="Model file path (JSON or YAML). Defaults to faultray-model.json.",
    ),
    company: str = typer.Option(
        "Your Organization",
        "--company",
        "-c",
        help="Company / institution name for the report.",
    ),
    output: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path. Defaults to <type>-report.<ext>.",
    ),
    framework: str = typer.Option(
        None,
        "--framework",
        "-f",
        help="Compliance framework (dora, soc2, iso27001, pci_dss, nist_csf, hipaa). For compliance report only.",
    ),
    service: str = typer.Option(
        None,
        "--service",
        "-s",
        help="Critical service (component id or name) for the DORA evidence pack. Required for 'dora'.",
    ),
    rto: str = typer.Option(
        "TBD",
        "--rto",
        help="Target Recovery Time Objective to record in the DORA evidence pack (e.g. '2h').",
    ),
    rpo: str = typer.Option(
        "TBD",
        "--rpo",
        help="Target Recovery Point Objective to record in the DORA evidence pack (e.g. '15m').",
    ),
    pdf: bool = typer.Option(
        False,
        "--pdf",
        help="Also write a print-ready HTML (open in browser → Ctrl+P) for the DORA evidence pack.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output as JSON (compliance report only).",
    ),
) -> None:
    """Generate reports (executive, compliance, dora).

    Examples:
        # Generate executive report
        faultray report executive model.yaml --company "Acme Corp" --output report.html

        # Generate compliance report (all frameworks)
        faultray report compliance model.yaml --json

        # Generate compliance report (specific framework)
        faultray report compliance model.yaml --framework dora --json

        # Generate a DORA pre-audit resilience evidence pack for one service
        faultray report dora --service payments-api --company "Acme Bank" --output payments-evidence-pack.md
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
    elif report_type == "dora":
        _generate_dora_evidence_pack(
            graph, service, company, output, rto, rpo, pdf
        )
    else:
        console.print(f"[red]Unknown report type: {report_type}[/]")
        console.print("[dim]Available types: executive, compliance, dora[/]")
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


def _generate_dora_evidence_pack(
    graph,
    service: str | None,
    company: str,
    output: Path | None,
    rto: str,
    rpo: str,
    pdf: bool,
) -> None:
    """Render a DORA pre-audit resilience evidence pack for ONE critical service.

    Reuses the existing simulation engine and the shared evidence-pack template
    (docs/sales/dora-evidence-pack-template.md). Produces Markdown and,
    optionally, a print-ready HTML rendering.
    """
    from faultray.reporter.dora_evidence_pack import (
        build_evidence_pack_markdown,
        evidence_pack_to_print_html,
    )
    from faultray.simulator.engine import SimulationEngine

    if not service:
        console.print(
            "[red]The 'dora' report requires --service <component id or name>.[/]"
        )
        console.print(
            "[dim]Example: faultray report dora --service payments-api[/]"
        )
        raise typer.Exit(1)

    console.print("[bold]Running simulation for the evidence pack...[/]")
    engine = SimulationEngine(graph)
    sim_report = engine.run_all_defaults()

    console.print("[bold]Assembling DORA evidence pack...[/]")
    try:
        markdown = build_evidence_pack_markdown(
            graph,
            sim_report,
            service,
            institution=company,
            rto_target=rto,
            rpo_target=rpo,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)

    md_path = output or Path("dora-evidence-pack.md")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown, encoding="utf-8")
    console.print(f"\n[green]DORA evidence pack saved to {md_path}[/]")
    console.print(f"  Service: [cyan]{service}[/]")
    console.print(f"  Resilience Score: [bold]{sim_report.resilience_score:.1f}/100[/]")
    console.print(f"  Critical Findings: [red]{len(sim_report.critical_findings)}[/]")

    if pdf:
        html_path = md_path.with_suffix(".html")
        html_path.write_text(
            evidence_pack_to_print_html(
                markdown, title=f"DORA Evidence Pack — {service}"
            ),
            encoding="utf-8",
        )
        console.print(f"[green]Print-ready HTML saved to {html_path}[/]")
        console.print("[dim]Open in a browser and press Ctrl+P to save as PDF.[/]")

    console.print(
        "\n[dim]Decision-support evidence only — not legal advice, not a DORA "
        "certification, and not a replacement for TLPT or auditor sign-off.[/]"
    )


def _generate_compliance_report(graph, framework: str | None, output: Path | None, json_output: bool) -> None:
    """Generate a compliance monitoring report."""
    import json as json_lib

    from faultray.simulator.compliance_monitor import ComplianceFramework, ComplianceMonitor

    monitor = ComplianceMonitor()
    # Track once and reuse for every assessment/evidence package below.
    monitor.track(graph)

    # The payload that gets written to --output (when requested). Holds the
    # selected framework's package, or all frameworks when none is selected.
    output_payload: dict = {}

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

        snapshot = monitor.assess(graph, fw)
        package = monitor.generate_evidence_package(fw)
        output_payload = {fw.value: package}

        if json_output:
            console.print_json(data=package)
        else:
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
        results = monitor.assess_all(graph)
        output_payload = {
            fw.value: monitor.generate_evidence_package(fw)
            for fw in ComplianceFramework
        }

        if json_output:
            console.print_json(data=output_payload)
        else:
            console.print("\n[bold]Compliance Report (All Frameworks)[/]\n")
            for fw, snapshot in results.items():
                color = "green" if snapshot.compliance_percentage >= 80 else "yellow" if snapshot.compliance_percentage >= 50 else "red"
                console.print(
                    f"  [{color}]{fw.value.upper():10s}[/]  "
                    f"{snapshot.compliance_percentage:5.1f}%  "
                    f"({snapshot.compliant}/{snapshot.total_controls} compliant)"
                )

    # Always write the file when --output is given, regardless of --json and
    # honoring the selected framework (only that framework's package).
    if output:
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json_lib.dumps(output_payload, indent=2, default=str),
                encoding="utf-8",
            )
        except OSError as exc:
            console.print(f"[red]Failed to write {output}: {exc}[/]")
            raise typer.Exit(1)
        # In --json mode stdout must stay valid, machine-readable JSON (already
        # emitted above via print_json). Route the human-readable confirmation
        # to stderr so it doesn't corrupt the JSON contract; otherwise print it
        # normally to stdout.
        if json_output:
            from rich.console import Console

            Console(stderr=True).print(
                f"[green]Compliance report saved to {output}[/]"
            )
        else:
            console.print(f"\n[green]Compliance report saved to {output}[/]")
