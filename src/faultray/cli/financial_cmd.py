# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI command for Financial Impact Report."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console


def _format_dollars(amount: float) -> str:
    """Format a dollar amount with K/M suffix for readability."""
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:,.1f}M"
    if amount >= 1_000:
        return f"${amount / 1_000:,.0f}K"
    return f"${amount:,.0f}"


def _print_financial_report(report: object) -> None:
    """Render a FinancialImpactReport using Rich."""
    from faultray.simulator.financial_impact import FinancialImpactReport

    assert isinstance(report, FinancialImpactReport)

    # Determine border colour based on total annual loss
    if report.total_annual_loss >= 1_000_000:
        border = "red"
    elif report.total_annual_loss >= 100_000:
        border = "yellow"
    else:
        border = "green"

    # Summary panel
    lines = [
        f"[bold]Resilience Score:[/] {report.resilience_score:.0f}/100",
        "",
        f"[bold]Estimated Annual Downtime:[/] {report.total_downtime_hours:,.1f} hours",
        f"[bold]Estimated Annual Loss:[/]     [{border}]"
        f"${report.total_annual_loss:,.0f}[/]",
    ]

    # Top risks
    if report.top_risks:
        lines.append("")
        lines.append("[bold]Top Risks by Financial Impact:[/]")
        for i, risk in enumerate(report.top_risks[:5], 1):
            lines.append(
                f"  {i}. {risk.component_id} ({risk.component_type}) "
                f"-> {_format_dollars(risk.annual_loss)}/year "
                f"({risk.annual_downtime_hours:.1f}h downtime)"
            )

    # Recommended fixes
    if report.recommended_fixes:
        lines.append("")
        lines.append("[bold]Recommended Fixes (by ROI):[/]")
        for i, fix in enumerate(report.recommended_fixes[:5], 1):
            lines.append(
                f"  {i}. {fix.description} "
                f"-> {_format_dollars(fix.annual_cost)}/yr "
                f"-> saves {_format_dollars(fix.annual_savings)} "
                f"({fix.roi:.0f}x ROI)"
            )

    # Totals
    if report.recommended_fixes:
        lines.append("")
        lines.append(f"[bold]Total Fix Cost:[/]  {_format_dollars(report.total_fix_cost)}/year")
        lines.append(f"[bold]Total Savings:[/]   {_format_dollars(report.total_savings)}/year")
        lines.append(f"[bold]Overall ROI:[/]     {report.roi:.0f}x")

    console.print()
    console.print(Panel(
        "\n".join(lines),
        title="[bold]FaultRay Financial Impact Report[/]",
        border_style=border,
    ))

    # Detailed component table
    if report.component_impacts:
        table = Table(
            title="Component Financial Impact (all components)",
            show_header=True,
        )
        table.add_column("Component", style="cyan", width=20)
        table.add_column("Type", width=16)
        table.add_column("Avail %", justify="right", width=10)
        table.add_column("Downtime/yr", justify="right", width=12)
        table.add_column("$/Hour", justify="right", width=10)
        table.add_column("Loss/yr", justify="right", width=14)
        table.add_column("Risk", width=30)

        for impact in report.component_impacts:
            avail_pct = impact.availability * 100
            if avail_pct >= 99.99:
                avail_color = "green"
            elif avail_pct >= 99.9:
                avail_color = "yellow"
            else:
                avail_color = "red"

            loss_color = (
                "red" if impact.annual_loss >= 100_000
                else "yellow" if impact.annual_loss >= 10_000
                else "dim"
            )

            table.add_row(
                impact.component_id,
                impact.component_type,
                f"[{avail_color}]{avail_pct:.4f}%[/]",
                f"{impact.annual_downtime_hours:.2f}h",
                f"${impact.cost_per_hour:,.0f}",
                f"[{loss_color}]${impact.annual_loss:,.0f}[/]",
                (impact.risk_description[:30]
                 if len(impact.risk_description) > 30
                 else impact.risk_description),
            )

        console.print()
        console.print(table)

    console.print()


def _report_to_dict(report: object) -> dict:
    """Convert FinancialImpactReport to a JSON-serialisable dict."""
    from faultray.simulator.financial_impact import FinancialImpactReport

    assert isinstance(report, FinancialImpactReport)
    return {
        "resilience_score": report.resilience_score,
        "total_annual_loss": report.total_annual_loss,
        "total_downtime_hours": report.total_downtime_hours,
        "total_fix_cost": report.total_fix_cost,
        "total_savings": report.total_savings,
        "roi": report.roi,
        "top_risks": [
            {
                "component_id": r.component_id,
                "component_type": r.component_type,
                "annual_downtime_hours": r.annual_downtime_hours,
                "annual_loss": r.annual_loss,
                "risk_description": r.risk_description,
            }
            for r in report.top_risks
        ],
        "recommended_fixes": [
            {
                "component_id": f.component_id,
                "description": f.description,
                "annual_cost": f.annual_cost,
                "annual_savings": f.annual_savings,
                "roi": f.roi,
            }
            for f in report.recommended_fixes
        ],
        "component_impacts": [
            {
                "component_id": c.component_id,
                "component_type": c.component_type,
                "availability": c.availability,
                "annual_downtime_hours": c.annual_downtime_hours,
                "annual_loss": c.annual_loss,
                "cost_per_hour": c.cost_per_hour,
                "risk_description": c.risk_description,
            }
            for c in report.component_impacts
        ],
    }


@app.command("financial")
def financial_cmd(
    model_file: Path = typer.Argument(
        ...,
        help="Path to YAML/JSON infrastructure model file.",
    ),
    cost_per_hour: float | None = typer.Option(
        None, "--cost-per-hour", "-c",
        help="Override default cost-per-hour for all components (USD).",
    ),
    output_format: str = typer.Option(
        "rich", "--output", "-o",
        help="Output format: rich (default), json, html.",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Shorthand for --output json.",
    ),
) -> None:
    """Generate a Financial Impact Report for your infrastructure.

    Translates resilience scores into estimated dollar amounts, showing
    annual downtime cost per component, top financial risks, and
    recommended fixes ranked by ROI.

    Default cost estimates are conservative. Override with --cost-per-hour
    or set cost_profile.revenue_per_minute in your YAML model.

    Examples:
        faultray financial infra.yaml
        faultray financial infra.yaml --cost-per-hour 10000
        faultray financial infra.yaml --output json
        faultray financial infra.yaml --json
    """
    from faultray.simulator.financial_impact import calculate_financial_impact

    graph = _load_graph_for_analysis(model_file, None)

    effective_format = "json" if json_output else output_format

    if effective_format not in ("rich", "json", "html"):
        console.print(f"[red]Unknown output format: {effective_format}. Use rich, json, or html.[/]")
        raise typer.Exit(1)

    if effective_format == "rich":
        console.print(
            f"[cyan]Calculating financial impact "
            f"({len(graph.components)} components)...[/]"
        )

    report = calculate_financial_impact(
        graph,
        cost_per_hour_override=cost_per_hour,
    )

    if effective_format == "json":
        console.print_json(data=_report_to_dict(report))
    elif effective_format == "html":
        # Minimal HTML output
        data = _report_to_dict(report)
        html_content = _render_html(data)
        console.print(html_content)
    else:
        _print_financial_report(report)


def _render_html(data: dict) -> str:
    """Render a minimal HTML financial report."""
    risks_rows = ""
    for r in data.get("top_risks", []):
        risks_rows += (
            f"<tr><td>{r['component_id']}</td>"
            f"<td>{r['component_type']}</td>"
            f"<td>${r['annual_loss']:,.0f}</td>"
            f"<td>{r['annual_downtime_hours']:.1f}h</td>"
            f"<td>{r['risk_description']}</td></tr>\n"
        )

    fixes_rows = ""
    for f in data.get("recommended_fixes", []):
        fixes_rows += (
            f"<tr><td>{f['component_id']}</td>"
            f"<td>{f['description']}</td>"
            f"<td>${f['annual_cost']:,.0f}</td>"
            f"<td>${f['annual_savings']:,.0f}</td>"
            f"<td>{f['roi']:.0f}x</td></tr>\n"
        )

    return f"""<!DOCTYPE html>
<html>
<head><title>FaultRay Financial Impact Report</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 900px; margin: 2em auto; }}
table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background: #f5f5f5; }}
.summary {{ background: #f8f9fa; padding: 1.5em; border-radius: 8px; margin: 1em 0; }}
h1 {{ color: #333; }}
</style></head>
<body>
<h1>FaultRay Financial Impact Report</h1>
<div class="summary">
<p><strong>Resilience Score:</strong> {data['resilience_score']:.0f}/100</p>
<p><strong>Estimated Annual Downtime:</strong> {data['total_downtime_hours']:,.1f} hours</p>
<p><strong>Estimated Annual Loss:</strong> ${data['total_annual_loss']:,.0f}</p>
<p><strong>Total Fix Cost:</strong> ${data['total_fix_cost']:,.0f}/year</p>
<p><strong>Total Savings:</strong> ${data['total_savings']:,.0f}/year</p>
<p><strong>Overall ROI:</strong> {data['roi']:.0f}x</p>
</div>
<h2>Top Risks</h2>
<table>
<tr><th>Component</th><th>Type</th><th>Annual Loss</th><th>Downtime</th><th>Risk</th></tr>
{risks_rows}
</table>
<h2>Recommended Fixes</h2>
<table>
<tr><th>Component</th><th>Fix</th><th>Cost/yr</th><th>Savings/yr</th><th>ROI</th></tr>
{fixes_rows}
</table>
</body></html>"""
