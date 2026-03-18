"""Dedicated CLI commands for DORA Resilience Evidence Generator.

Provides the ``faultray dora`` subcommand group:

    faultray dora assess <infra.yaml> [--json] [--html]
    faultray dora evidence <infra.yaml> --output <dir> [--signed] [--framework ...]
    faultray dora gap-analysis <infra.yaml> [--json] [--remediation]
    faultray dora register <infra.yaml> [--output register.json]
    faultray dora report <infra.yaml> --output report.html [--signed]

The key market gap addressed: GRC tools generate documentation but cannot run
tests; chaos tools run tests but do not produce regulatory-formatted output.
FaultRay bridges both.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import app, console

dora_app = typer.Typer(
    name="dora",
    help="DORA Resilience Evidence Generator — regulator-ready audit packages",
    no_args_is_help=True,
)
app.add_typer(dora_app, name="dora")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _load_graph(yaml_file: Path) -> "InfraGraph":  # noqa: F821
    """Load an InfraGraph from a YAML or JSON file."""
    if not yaml_file.exists():
        console.print(f"[red]File not found: {yaml_file}[/]")
        raise typer.Exit(1)

    try:
        if str(yaml_file).endswith((".yaml", ".yml")):
            from faultray.model.loader import load_yaml
            return load_yaml(yaml_file)
        else:
            from faultray.model.graph import InfraGraph
            return InfraGraph.load(yaml_file)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)


def _status_color(status: str) -> str:
    return {
        "compliant": "green",
        "partially_compliant": "yellow",
        "non_compliant": "red",
        "not_applicable": "dim",
    }.get(status, "white")


def _severity_color(severity: str) -> str:
    return {
        "critical": "bold red",
        "high": "red",
        "medium": "yellow",
        "low": "green",
    }.get(severity, "white")


# ---------------------------------------------------------------------------
# dora assess
# ---------------------------------------------------------------------------


@dora_app.command("assess")
def dora_assess(
    model: Annotated[Path, typer.Argument(help="Infrastructure model file (.yaml/.json)")],
    json_output: Annotated[bool, typer.Option("--json", help="Output raw JSON")] = False,
    html: Annotated[bool, typer.Option("--html", help="(reserved) Output HTML summary")] = False,
    entity: Annotated[str, typer.Option("--entity", help="Reporting entity name")] = "Financial Institution",
) -> None:
    """Quick DORA compliance status check.

    Evaluates the infrastructure model against all 24 DORA controls and
    reports overall status, per-article results, and key gaps.

    Examples:
        faultray dora assess infra.yaml
        faultray dora assess infra.yaml --json
        faultray dora assess infra.yaml --entity "Acme Bank"
    """
    from faultray.reporter.dora_audit_report import DORAuditReportGenerator

    graph = _load_graph(model)
    gen = DORAuditReportGenerator()
    report = gen.generate_full_report(graph, reporting_entity=entity)

    if json_output:
        import json
        out = {
            "report_id": report.report_id,
            "overall_status": report.overall_status.value,
            "compliance_rate_percent": round(
                report.compliant_count / max(report.total_controls, 1) * 100, 1
            ),
            "article_statuses": {k: v.value for k, v in report.article_statuses.items()},
            "total_controls": report.total_controls,
            "compliant": report.compliant_count,
            "non_compliant": report.non_compliant_count,
            "partially_compliant": report.partially_compliant_count,
            "not_applicable": report.not_applicable_count,
        }
        console.print_json(data=out)
        return

    compliance_rate = round(
        report.compliant_count / max(report.total_controls, 1) * 100, 1
    )
    status_val = report.overall_status.value
    status_color = _status_color(status_val)

    console.print(Panel(
        f"[bold]Report ID:[/] {report.report_id}\n"
        f"[bold]Entity:[/] {report.reporting_entity}\n"
        f"[bold]Overall Status:[/] [{status_color}]{status_val.upper()}[/]\n"
        f"[bold]Compliance Rate:[/] {compliance_rate}%\n\n"
        f"[bold]Controls:[/] {report.total_controls} total | "
        f"[green]{report.compliant_count} compliant[/] | "
        f"[yellow]{report.partially_compliant_count} partial[/] | "
        f"[red]{report.non_compliant_count} non-compliant[/] | "
        f"[dim]{report.not_applicable_count} N/A[/]\n\n"
        f"[dim]{report.tlpt_disclaimer}[/]",
        title="[bold]DORA Compliance Assessment[/]",
        border_style=status_color,
    ))

    # Per-article table
    art_table = Table(title="Article-Level Results", show_header=True)
    art_table.add_column("Article", style="cyan", width=18)
    art_table.add_column("Status", width=22, justify="center")

    article_labels = {
        "article_11": "Art. 11 — ICT Risk Mgmt",
        "article_24": "Art. 24 — Testing",
        "article_25": "Art. 25 — TLPT",
        "article_26": "Art. 26 — Tester Requirements",
        "article_28": "Art. 28 — Third-Party Risk",
    }
    for art_key, status in report.article_statuses.items():
        label = article_labels.get(art_key, art_key)
        color = _status_color(status.value)
        art_table.add_row(label, f"[{color}]{status.value.upper()}[/]")

    console.print()
    console.print(art_table)

    # Top gaps
    critical_gaps = [
        g for g in report.gap_analyses
        if g.status.value == "non_compliant" and g.gaps
    ]
    if critical_gaps:
        console.print()
        console.print("[bold red]Non-Compliant Controls:[/]")
        for gap in critical_gaps[:5]:
            console.print(f"  [red]• {gap.control_id}[/]: {gap.gaps[0] if gap.gaps else 'See gap analysis'}")
        if len(critical_gaps) > 5:
            console.print(f"  [dim]... and {len(critical_gaps) - 5} more. Run 'faultray dora gap-analysis' for details.[/]")


# ---------------------------------------------------------------------------
# dora evidence
# ---------------------------------------------------------------------------


@dora_app.command("evidence")
def dora_evidence(
    model: Annotated[Path, typer.Argument(help="Infrastructure model file (.yaml/.json)")],
    output: Annotated[Path, typer.Option("--output", "-o", help="Output directory for evidence package")],
    signed: Annotated[bool, typer.Option("--signed", help="Include cryptographic integrity hashes")] = False,
    framework: Annotated[str, typer.Option(
        "--framework",
        help="DORA article scope: article-24 | article-25 | article-28 | all",
    )] = "all",
    simulate: Annotated[bool, typer.Option("--simulate", "-s", help="Run chaos simulation first")] = False,
    entity: Annotated[str, typer.Option("--entity", help="Reporting entity name")] = "Financial Institution",
) -> None:
    """Generate full regulatory evidence package.

    Exports a complete folder with executive summary, article-specific
    evidence files, gap analysis, remediation plan, and signed audit trail.

    Examples:
        faultray dora evidence infra.yaml --output ./dora-evidence/
        faultray dora evidence infra.yaml --output ./dora-evidence/ --signed
        faultray dora evidence infra.yaml --output ./dora-evidence/ --framework article-24
        faultray dora evidence infra.yaml --output ./dora-evidence/ --simulate
    """
    from faultray.reporter.dora_audit_report import DORAuditReportGenerator

    valid_frameworks = {"article-24", "article-25", "article-28", "all"}
    if framework not in valid_frameworks:
        console.print(f"[red]Invalid framework '{framework}'. Choose from: {', '.join(sorted(valid_frameworks))}[/]")
        raise typer.Exit(1)

    graph = _load_graph(model)

    sim_results: list[dict] = []
    if simulate:
        console.print("[cyan]Running chaos simulation...[/]")
        from faultray.simulator.engine import SimulationEngine
        engine = SimulationEngine(graph)
        sim_report = engine.run_all_defaults()
        for result in sim_report.results:
            sim_results.append({
                "name": result.scenario.name,
                "result": "fail" if result.is_critical else ("partial" if result.is_warning else "pass"),
                "severity": "critical" if result.is_critical else ("high" if result.is_warning else "low"),
                "description": result.scenario.description,
            })

    console.print("[cyan]Generating DORA evidence package...[/]")
    gen = DORAuditReportGenerator()
    report = gen.generate_full_report(
        graph,
        simulation_results=sim_results,
        reporting_entity=entity,
    )
    pkg = gen.export_regulatory_package(report, output_dir=output, sign=signed)

    status_val = report.overall_status.value
    status_color = _status_color(status_val)
    compliance_rate = round(
        report.compliant_count / max(report.total_controls, 1) * 100, 1
    )

    console.print(Panel(
        f"[bold]Evidence package exported to:[/] {output}\n"
        f"[bold]Files written:[/] {len(pkg.files_written)}\n"
        f"[bold]Overall Status:[/] [{status_color}]{status_val.upper()}[/]\n"
        f"[bold]Compliance Rate:[/] {compliance_rate}%\n"
        f"[bold]Signed:[/] {'Yes' if signed else 'No'}\n\n"
        + "\n".join(f"  [dim]• {f}[/]" for f in pkg.files_written),
        title="[bold]DORA Regulatory Package[/]",
        border_style="cyan",
    ))

    if report.non_compliant_count > 0:
        console.print(
            f"\n[yellow]Attention:[/] {report.non_compliant_count} non-compliant control(s) detected. "
            "Review remediation-plan.json for prioritised actions."
        )


# ---------------------------------------------------------------------------
# dora gap-analysis
# ---------------------------------------------------------------------------


@dora_app.command("gap-analysis")
def dora_gap_analysis(
    model: Annotated[Path, typer.Argument(help="Infrastructure model file (.yaml/.json)")],
    json_output: Annotated[bool, typer.Option("--json", help="Output raw JSON")] = False,
    remediation: Annotated[bool, typer.Option("--remediation", help="Include remediation recommendations")] = False,
    entity: Annotated[str, typer.Option("--entity", help="Reporting entity name")] = "Financial Institution",
) -> None:
    """Identify DORA compliance gaps with remediation recommendations.

    Analyses all 24 DORA controls and reports gaps, risk scores, and
    optionally the full prioritised remediation plan.

    Examples:
        faultray dora gap-analysis infra.yaml
        faultray dora gap-analysis infra.yaml --json
        faultray dora gap-analysis infra.yaml --remediation
    """
    from faultray.reporter.dora_audit_report import DORAuditReportGenerator

    graph = _load_graph(model)
    gen = DORAuditReportGenerator()
    report = gen.generate_full_report(graph, reporting_entity=entity)

    if json_output:
        import json
        out = {
            "report_id": report.report_id,
            "gap_analyses": [
                {
                    "control_id": g.control_id,
                    "status": g.status.value,
                    "risk_score": g.risk_score,
                    "gaps": g.gaps,
                    "recommendations": g.recommendations,
                }
                for g in report.gap_analyses
            ],
        }
        if remediation:
            from dataclasses import asdict
            out["remediation_items"] = [asdict(r) for r in report.remediation_items]
        console.print_json(data=out)
        return

    gap_table = Table(title="DORA Gap Analysis", show_header=True)
    gap_table.add_column("Control", style="cyan", width=14)
    gap_table.add_column("Status", width=22, justify="center")
    gap_table.add_column("Risk", width=6, justify="right")
    gap_table.add_column("Key Gap", width=45)
    gap_table.add_column("Recommendation", width=45)

    for gap in report.gap_analyses:
        color = _status_color(gap.status.value)
        key_gap = gap.gaps[0] if gap.gaps else "—"
        key_rec = gap.recommendations[0] if gap.recommendations else "—"
        risk_str = f"{gap.risk_score:.2f}"
        gap_table.add_row(
            gap.control_id,
            f"[{color}]{gap.status.value.upper()}[/]",
            f"[{'red' if gap.risk_score >= 0.5 else 'yellow' if gap.risk_score > 0 else 'green'}]{risk_str}[/]",
            key_gap[:80] + ("..." if len(key_gap) > 80 else ""),
            key_rec[:80] + ("..." if len(key_rec) > 80 else ""),
        )

    console.print()
    console.print(gap_table)

    if remediation and report.remediation_items:
        console.print()
        rem_table = Table(title="Prioritised Remediation Plan", show_header=True)
        rem_table.add_column("ID", style="dim", width=10)
        rem_table.add_column("Control", style="cyan", width=12)
        rem_table.add_column("Severity", width=10, justify="center")
        rem_table.add_column("Effort", width=8, justify="center")
        rem_table.add_column("Action", width=60)
        rem_table.add_column("Deadline", width=12)

        for item in sorted(
            report.remediation_items,
            key=lambda x: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(x.severity, 4),
        )[:20]:
            sev_color = _severity_color(item.severity)
            rem_table.add_row(
                item.item_id,
                item.control_id,
                f"[{sev_color}]{item.severity.upper()}[/]",
                item.effort,
                item.title[:80] + ("..." if len(item.title) > 80 else ""),
                item.remediation_deadline,
            )
        console.print(rem_table)
        if len(report.remediation_items) > 20:
            console.print(
                f"[dim]... and {len(report.remediation_items) - 20} more items. "
                "Use --json for full list.[/]"
            )


# ---------------------------------------------------------------------------
# dora register
# ---------------------------------------------------------------------------


@dora_app.command("register")
def dora_register(
    model: Annotated[Path, typer.Argument(help="Infrastructure model file (.yaml/.json)")],
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Write register to JSON file")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Print register as JSON")] = False,
) -> None:
    """Generate DORA Article 28 Register of Information.

    Identifies all ICT third-party service providers from the infrastructure
    model and builds the structured register required by DORA Article 28.

    Examples:
        faultray dora register infra.yaml
        faultray dora register infra.yaml --output register.json
        faultray dora register infra.yaml --json
    """
    import json
    from dataclasses import asdict
    from faultray.reporter.dora_audit_report import DORAuditReportGenerator

    graph = _load_graph(model)
    gen = DORAuditReportGenerator()
    entries = gen.generate_register_of_information(graph)

    register_data = {
        "regulatory_reference": "DORA Article 28, EU 2022/2554",
        "total_providers": len(entries),
        "entries": [asdict(e) for e in entries],
    }

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(register_data, indent=2, default=str), encoding="utf-8")
        if not json_output:
            console.print(f"[green]Register of Information exported to {output}[/]")

    if json_output:
        console.print_json(data=register_data)
        return

    if not entries:
        console.print(Panel(
            "[dim]No external API (third-party ICT) components detected in the infrastructure model.\n\n"
            "DORA Article 28 Register of Information is not required when there are no "
            "ICT third-party service providers.[/]",
            title="[bold]DORA Art. 28 — Register of Information[/]",
            border_style="dim",
        ))
        return

    reg_table = Table(
        title=f"DORA Article 28 — Register of Information ({len(entries)} provider(s))",
        show_header=True,
    )
    reg_table.add_column("Provider ID", style="cyan", width=14)
    reg_table.add_column("Name", width=22)
    reg_table.add_column("Criticality", width=12, justify="center")
    reg_table.add_column("Dependents", width=10, justify="right")
    reg_table.add_column("Concentration Risk", width=18, justify="center")
    reg_table.add_column("Exit Strategy", width=14, justify="center")

    for entry in entries:
        crit_color = {
            "critical": "bold red",
            "important": "yellow",
            "standard": "green",
        }.get(entry.criticality, "white")
        reg_table.add_row(
            entry.provider_id,
            entry.provider_name,
            f"[{crit_color}]{entry.criticality.upper()}[/]",
            str(len(entry.dependent_functions)),
            "[red]YES[/]" if entry.concentration_risk else "[green]No[/]",
            "[green]Yes[/]" if entry.exit_strategy_documented else "[red]No[/]",
        )

    console.print()
    console.print(reg_table)

    if any(e.concentration_risk for e in entries):
        console.print(
            "\n[yellow]Warning:[/] Concentration risk detected. "
            "DORA Article 28 requires active management of third-party concentration."
        )
    providers_without_exit = [e.provider_name for e in entries if not e.exit_strategy_documented]
    if providers_without_exit:
        console.print(
            f"\n[yellow]Warning:[/] {len(providers_without_exit)} provider(s) lack documented exit strategies: "
            + ", ".join(providers_without_exit[:3])
            + (f" (+{len(providers_without_exit) - 3} more)" if len(providers_without_exit) > 3 else "")
        )


# ---------------------------------------------------------------------------
# dora report
# ---------------------------------------------------------------------------


@dora_app.command("report")
def dora_report(
    model: Annotated[Path, typer.Argument(help="Infrastructure model file (.yaml/.json)")],
    output: Annotated[Path, typer.Option("--output", "-o", help="Output HTML report path")],
    signed: Annotated[bool, typer.Option("--signed", help="Include signed audit trail")] = False,
    simulate: Annotated[bool, typer.Option("--simulate", "-s", help="Run chaos simulation first")] = False,
    entity: Annotated[str, typer.Option("--entity", help="Reporting entity name")] = "Financial Institution",
) -> None:
    """Generate a comprehensive HTML DORA compliance report.

    Produces a single-file HTML report with executive summary, article-level
    results, gap analysis, evidence tables, and remediation plan.

    Examples:
        faultray dora report infra.yaml --output dora-report.html
        faultray dora report infra.yaml --output dora-report.html --signed
        faultray dora report infra.yaml --output dora-report.html --simulate
    """
    import html as html_lib
    from faultray.reporter.dora_audit_report import DORAuditReportGenerator, TLPT_DISCLAIMER

    graph = _load_graph(model)

    sim_results: list[dict] = []
    if simulate:
        console.print("[cyan]Running chaos simulation...[/]")
        from faultray.simulator.engine import SimulationEngine
        engine = SimulationEngine(graph)
        sim_report = engine.run_all_defaults()
        for result in sim_report.results:
            sim_results.append({
                "name": result.scenario.name,
                "result": "fail" if result.is_critical else ("partial" if result.is_warning else "pass"),
                "severity": "critical" if result.is_critical else ("high" if result.is_warning else "low"),
                "description": result.scenario.description,
            })

    gen = DORAuditReportGenerator()
    report = gen.generate_full_report(
        graph,
        simulation_results=sim_results,
        reporting_entity=entity,
    )

    # Build audit trail section
    if signed:
        audit_section = gen._build_audit_trail(report, sign=True)
    else:
        audit_section = gen._build_audit_trail(report, sign=False)

    pdf_data = gen.export_pdf_data(report)

    def _esc(text: str) -> str:
        return html_lib.escape(str(text))

    def _status_badge(status: str) -> str:
        colors = {
            "compliant": "#28a745",
            "partially_compliant": "#ffc107",
            "non_compliant": "#dc3545",
            "not_applicable": "#6c757d",
        }
        color = colors.get(status, "#6c757d")
        return (
            f'<span style="background:{color};color:#fff;padding:2px 8px;'
            f'border-radius:4px;font-size:0.85em;">{_esc(status.upper())}' + "</span>"
        )

    def _severity_badge(severity: str) -> str:
        colors = {
            "critical": "#dc3545",
            "high": "#fd7e14",
            "medium": "#ffc107",
            "low": "#28a745",
        }
        color = colors.get(severity, "#6c757d")
        return (
            f'<span style="background:{color};color:#fff;padding:2px 8px;'
            f'border-radius:4px;font-size:0.85em;">{_esc(severity.upper())}' + "</span>"
        )

    # Article summary rows
    art_rows = ""
    article_labels = {
        "article_11": "Art. 11 — ICT Risk Management",
        "article_24": "Art. 24 — Testing Programme",
        "article_25": "Art. 25 — TLPT",
        "article_26": "Art. 26 — Tester Requirements",
        "article_28": "Art. 28 — Third-Party Risk",
    }
    for art_key, status in report.article_statuses.items():
        label = article_labels.get(art_key, art_key)
        art_rows += f"<tr><td>{_esc(label)}</td><td>{_status_badge(status.value)}</td></tr>"

    # Gap analysis rows
    gap_rows = ""
    for gap in report.gap_analyses:
        key_gap = gap.gaps[0] if gap.gaps else "—"
        key_rec = gap.recommendations[0] if gap.recommendations else "—"
        gap_rows += (
            f"<tr><td>{_esc(gap.control_id)}</td>"
            f"<td>{_status_badge(gap.status.value)}</td>"
            f"<td>{gap.risk_score:.2f}</td>"
            f"<td>{_esc(key_gap)}</td>"
            f"<td>{_esc(key_rec)}</td></tr>"
        )

    # Evidence rows
    ev_rows = ""
    for item in pdf_data.get("evidence_table", []):
        ev_rows += (
            f"<tr><td>{_esc(item['control_id'])}</td>"
            f"<td>{_esc(str(item['test_timestamp'])[:19])}</td>"
            f"<td>{_esc(item['test_type'])}</td>"
            f"<td>{_esc(item['result'])}</td>"
            f"<td>{_severity_badge(item['severity'])}</td>"
            f"<td>{'Yes' if item['remediation_required'] else 'No'}</td>"
            f"<td>{_esc(item['sign_off_status'])}</td></tr>"
        )

    # Remediation rows
    rem_rows = ""
    for item in pdf_data.get("remediation_plan", []):
        rem_rows += (
            f"<tr><td>{_esc(item['item_id'])}</td>"
            f"<td>{_esc(item['control_id'])}</td>"
            f"<td>{_severity_badge(item['severity'])}</td>"
            f"<td>{_esc(item['title'][:80])}</td>"
            f"<td>{_esc(item['effort'])}</td>"
            f"<td>{_esc(item['remediation_deadline'])}</td></tr>"
        )

    # Register rows
    reg_rows = ""
    for entry in pdf_data.get("register_of_information", []):
        reg_rows += (
            f"<tr><td>{_esc(entry['provider_name'])}</td>"
            f"<td>{_esc(entry['criticality'].upper())}</td>"
            f"<td>{len(entry.get('dependent_functions', []))}</td>"
            f"<td>{'Yes' if entry['concentration_risk'] else 'No'}</td>"
            f"<td>{'Yes' if entry['exit_strategy_documented'] else 'No'}</td></tr>"
        )

    exec_summary = pdf_data["executive_summary"]
    compliance_rate = exec_summary["compliance_rate_percent"]
    overall = exec_summary["overall_status"]
    overall_colors = {
        "compliant": "#28a745",
        "partially_compliant": "#ffc107",
        "non_compliant": "#dc3545",
        "not_applicable": "#6c757d",
    }
    overall_color = overall_colors.get(overall, "#6c757d")
    ts = report.generated_at[:19].replace("T", " ") + " UTC"

    report_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DORA Resilience Evidence Report — {_esc(entity)}</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      line-height: 1.6; color: #333; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }}
    .header {{ background: linear-gradient(135deg, #1a237e, #283593); color: white;
      padding: 30px; border-radius: 8px; margin-bottom: 24px; }}
    .header h1 {{ font-size: 24px; margin-bottom: 8px; }}
    .header p {{ opacity: 0.9; font-size: 14px; }}
    .section {{ background: white; border-radius: 8px; padding: 24px; margin-bottom: 20px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
    .section h2 {{ font-size: 18px; color: #1a237e; border-bottom: 2px solid #e8eaf6;
      padding-bottom: 8px; margin-bottom: 16px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 13px; }}
    th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #eee; }}
    th {{ background: #f5f5f5; font-weight: 600; color: #555; }}
    tr:hover {{ background: #fafafa; }}
    .metric-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 16px; margin-bottom: 16px; }}
    .metric-card {{ background: #f8f9fa; border-radius: 6px; padding: 16px; text-align: center; }}
    .metric-card .value {{ font-size: 28px; font-weight: bold; color: #1a237e; }}
    .metric-card .label {{ font-size: 12px; color: #666; margin-top: 4px; }}
    .disclaimer {{ background: #fff3cd; border-left: 4px solid #ffc107;
      padding: 12px 16px; border-radius: 0 4px 4px 0; margin: 12px 0; font-size: 13px; }}
    .status-pill {{ display: inline-block; background: {overall_color}; color: white;
      padding: 4px 12px; border-radius: 16px; font-weight: bold; font-size: 1.1em; }}
    .footer {{ text-align: center; color: #999; font-size: 12px; padding: 20px 0; }}
  </style>
</head>
<body>
<div class="header">
  <h1>DORA Resilience Evidence Report</h1>
  <p>Digital Operational Resilience Act (EU 2022/2554) | {_esc(entity)}</p>
  <p>Generated: {_esc(ts)} | FaultRay DORA Evidence Generator | Report ID: {_esc(report.report_id)}</p>
</div>

<div class="section">
  <h2>Executive Summary</h2>
  <p>Overall compliance status: <span class="status-pill">{_esc(overall.upper())}</span>
     &nbsp; Compliance rate: <strong>{compliance_rate}%</strong></p>
  <br>
  <div class="metric-grid">
    <div class="metric-card"><div class="value">{exec_summary['total_controls']}</div>
      <div class="label">Total Controls</div></div>
    <div class="metric-card"><div class="value" style="color:#28a745;">{exec_summary['compliant']}</div>
      <div class="label">Compliant</div></div>
    <div class="metric-card"><div class="value" style="color:#ffc107;">{exec_summary['partially_compliant']}</div>
      <div class="label">Partial</div></div>
    <div class="metric-card"><div class="value" style="color:#dc3545;">{exec_summary['non_compliant']}</div>
      <div class="label">Non-Compliant</div></div>
    <div class="metric-card"><div class="value" style="color:#6c757d;">{exec_summary['not_applicable']}</div>
      <div class="label">Not Applicable</div></div>
  </div>
  <div class="disclaimer">{_esc(TLPT_DISCLAIMER)}</div>
  <h3 style="margin-top:16px;">Article-Level Results</h3>
  <table>
    <thead><tr><th>Article</th><th>Status</th></tr></thead>
    <tbody>{art_rows}</tbody>
  </table>
</div>

<div class="section">
  <h2>Gap Analysis — All 24 DORA Controls</h2>
  <table>
    <thead><tr><th>Control</th><th>Status</th><th>Risk</th><th>Key Gap</th><th>Recommendation</th></tr></thead>
    <tbody>{gap_rows}</tbody>
  </table>
</div>

{"" if not ev_rows else f'''<div class="section">
  <h2>Evidence Records</h2>
  <table>
    <thead><tr><th>Control</th><th>Timestamp</th><th>Test Type</th><th>Result</th>
      <th>Severity</th><th>Remediation Req.</th><th>Sign-off</th></tr></thead>
    <tbody>{ev_rows}</tbody>
  </table>
</div>'''}

{"" if not rem_rows else f'''<div class="section">
  <h2>Remediation Plan</h2>
  <table>
    <thead><tr><th>ID</th><th>Control</th><th>Severity</th><th>Action</th>
      <th>Effort</th><th>Deadline</th></tr></thead>
    <tbody>{rem_rows}</tbody>
  </table>
</div>'''}

{"" if not reg_rows else f'''<div class="section">
  <h2>Article 28 — Register of Information</h2>
  <table>
    <thead><tr><th>Provider</th><th>Criticality</th><th>Dependents</th>
      <th>Concentration Risk</th><th>Exit Strategy</th></tr></thead>
    <tbody>{reg_rows}</tbody>
  </table>
</div>'''}

{"" if not audit_section.get("chain") else f'''<div class="section">
  <h2>Audit Trail</h2>
  <p>Total evidence items: <strong>{audit_section["total_evidence_items"]}</strong>
     &nbsp; Signed: <strong>{"Yes" if signed else "No"}</strong></p>
</div>'''}

<div class="footer">
  Generated by FaultRay DORA Evidence Generator | {_esc(ts)}
</div>
</body>
</html>"""

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report_html, encoding="utf-8")

    compliance_rate_val = round(
        report.compliant_count / max(report.total_controls, 1) * 100, 1
    )
    status_color = _status_color(report.overall_status.value)
    console.print(Panel(
        f"[bold]Report:[/] {output}\n"
        f"[bold]Entity:[/] {report.reporting_entity}\n"
        f"[bold]Overall Status:[/] [{status_color}]{report.overall_status.value.upper()}[/]\n"
        f"[bold]Compliance Rate:[/] {compliance_rate_val}%\n"
        f"[bold]Controls:[/] {report.total_controls} | "
        f"[green]{report.compliant_count} ✓[/] | "
        f"[yellow]{report.partially_compliant_count} ~[/] | "
        f"[red]{report.non_compliant_count} ✗[/]",
        title="[bold]DORA HTML Report Generated[/]",
        border_style="cyan",
    ))
