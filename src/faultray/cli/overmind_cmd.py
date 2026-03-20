# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""CLI commands for Overmind integration.

Provides two sub-commands under ``faultray overmind``:

enrich
    Takes Overmind's blast-radius JSON, optionally maps it to a FaultRay
    infrastructure model, runs cascade simulation, and outputs a combined
    report showing both Overmind risks and FaultRay cascade analysis.

compare
    Compares Overmind blast-radius items against a FaultRay simulation
    YAML model and shows which resources are covered vs uncovered.

Examples::

    # Enrich Overmind output with FaultRay cascade analysis
    faultray overmind enrich overmind.json --model infra.yaml
    faultray overmind enrich overmind.json --json
    faultray overmind enrich overmind.json --html report.html

    # Compare Overmind blast radius to a FaultRay model
    faultray overmind compare overmind.json infra.yaml --json
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import app, console

overmind_app = typer.Typer(
    name="overmind",
    help="Overmind integration — enrich blast-radius analysis with FaultRay cascade simulation",
    no_args_is_help=True,
)
app.add_typer(overmind_app, name="overmind")


# ---------------------------------------------------------------------------
# enrich command
# ---------------------------------------------------------------------------


@overmind_app.command("enrich")
def overmind_enrich(
    overmind_json: Path = typer.Argument(
        ..., help="Path to Overmind JSON output file"
    ),
    model: Path = typer.Option(
        Path("faultray-model.json"),
        "--model", "-m",
        help="FaultRay model file (JSON or YAML).  Optional: if omitted, cascade "
             "simulation runs on a minimal graph derived from Overmind's blast radius.",
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output combined report as JSON"
    ),
    html_report: Path | None = typer.Option(
        None, "--html", help="Write an HTML report to this path"
    ),
) -> None:
    """Enrich Overmind blast-radius data with FaultRay cascade simulation.

    Parses Overmind's JSON output, maps the affected resources to FaultRay
    infrastructure components, runs cascade simulation, and produces a combined
    report showing:

    - Overmind risks (severity, title, description)
    - Per-change blast radius (direct + indirect resources)
    - FaultRay cascade severity for each affected component
    - Unified recommendations

    Examples:

        faultray overmind enrich overmind.json

        faultray overmind enrich overmind.json --model infra.yaml

        faultray overmind enrich overmind.json --json

        faultray overmind enrich overmind.json --html report.html
    """
    from faultray.integrations.overmind_bridge import OvermindBridge

    if not overmind_json.exists():
        console.print(f"[red]Overmind JSON file not found: {overmind_json}[/]")
        raise typer.Exit(1)

    # Load Overmind JSON
    try:
        raw_data = json.loads(overmind_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        console.print(f"[red]Failed to read Overmind JSON: {exc}[/]")
        raise typer.Exit(1)

    # Parse Overmind output
    try:
        analysis = OvermindBridge.from_overmind_json(raw_data)
    except Exception as exc:
        console.print(f"[red]Failed to parse Overmind data: {exc}[/]")
        raise typer.Exit(1)

    # Load FaultRay graph (optional)
    graph = _load_graph_optional(model, quiet=json_output)

    # Run cascade enrichment
    bridge = OvermindBridge(graph=graph)
    if not json_output:
        console.print("[cyan]Running FaultRay cascade simulation...[/]")

    try:
        enriched = bridge.enrich_with_cascade(analysis, graph)
    except Exception as exc:
        console.print(f"[red]Cascade simulation failed: {exc}[/]")
        raise typer.Exit(1)

    # Generate combined report
    report = bridge.generate_combined_report(enriched)

    if json_output:
        console.print_json(data=report)
        return

    if html_report is not None:
        _write_html_report(report, html_report)
        console.print(f"[green]HTML report written to: {html_report}[/]")
        return

    _print_enriched_report(report, enriched)


# ---------------------------------------------------------------------------
# compare command
# ---------------------------------------------------------------------------


@overmind_app.command("compare")
def overmind_compare(
    overmind_json: Path = typer.Argument(
        ..., help="Path to Overmind JSON output file"
    ),
    faultray_yaml: Path = typer.Argument(
        ..., help="Path to FaultRay infrastructure YAML model"
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output comparison as JSON"
    ),
) -> None:
    """Compare Overmind blast radius against a FaultRay model.

    Shows which Overmind-affected resources ARE represented in the FaultRay
    model (covered) and which are NOT (uncovered / unmapped).  Use this to
    identify gaps in FaultRay coverage before running cascade simulations.

    Examples:

        faultray overmind compare overmind.json infra.yaml

        faultray overmind compare overmind.json infra.yaml --json
    """
    from faultray.integrations.overmind_bridge import OvermindBridge

    for path in (overmind_json, faultray_yaml):
        if not path.exists():
            console.print(f"[red]File not found: {path}[/]")
            raise typer.Exit(1)

    # Load files
    try:
        raw_data = json.loads(overmind_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        console.print(f"[red]Failed to read Overmind JSON: {exc}[/]")
        raise typer.Exit(1)

    graph = _load_graph_optional(faultray_yaml, quiet=json_output)

    # Parse and enrich (to determine unmapped)
    analysis = OvermindBridge.from_overmind_json(raw_data)
    bridge = OvermindBridge(graph=graph)
    enriched = bridge.enrich_with_cascade(analysis, graph)

    blast_items = analysis.all_blast_radius_items
    unmapped = set(enriched.unmapped_resources)
    mapped = [item for item in blast_items if item not in unmapped]

    coverage_pct = (len(mapped) / len(blast_items) * 100) if blast_items else 100.0

    if json_output:
        console.print_json(data={
            "overmind_json": str(overmind_json),
            "faultray_model": str(faultray_yaml),
            "total_blast_radius_items": len(blast_items),
            "mapped_count": len(mapped),
            "unmapped_count": len(unmapped),
            "coverage_percent": round(coverage_pct, 1),
            "mapped": mapped,
            "unmapped": sorted(unmapped),
        })
        return

    _print_comparison(blast_items, mapped, sorted(unmapped), coverage_pct)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _load_graph_optional(model: Path, *, quiet: bool = False):
    """Load a FaultRay InfraGraph if the model file exists; return empty graph otherwise."""
    from faultray.model.graph import InfraGraph

    if not model.exists():
        if not quiet:
            console.print(
                f"[yellow]Model file not found: {model}  "
                "(cascade simulation will run on empty graph)[/]"
            )
            console.print(
                "[dim]Tip: run 'faultray scan --aws' to auto-discover components, "
                "then rerun with --model[/]"
            )
        return InfraGraph()

    try:
        if str(model).endswith((".yaml", ".yml")):
            from faultray.model.loader import load_yaml
            return load_yaml(model)
        return InfraGraph.load(model)
    except Exception as exc:
        if not quiet:
            console.print(f"[yellow]Could not load model ({exc}), using empty graph.[/]")
        return InfraGraph()


def _print_enriched_report(report: dict, enriched) -> None:
    """Print the combined Overmind + FaultRay report using Rich."""
    summary = report["summary"]

    # -- Summary panel --
    sev = summary["highest_risk_severity"]
    sev_colors = {"critical": "red", "high": "red", "medium": "yellow", "low": "green", "info": "dim"}
    sev_color = sev_colors.get(sev, "white")

    cascade_sev = summary["faultray_max_cascade_severity"]
    if cascade_sev >= 7.0:
        cs_color = "red"
    elif cascade_sev >= 4.0:
        cs_color = "yellow"
    else:
        cs_color = "green"

    summary_text = (
        f"[bold]Overmind + FaultRay Combined Analysis[/]\n\n"
        f"  Overmind Risks:          {summary['overmind_risks']}  "
        f"(highest: [{sev_color}]{sev.upper()}[/])\n"
        f"  Overmind Changes:        {summary['overmind_changes']}\n"
        f"  Blast Radius Items:      {summary['blast_radius_items']}\n\n"
        f"  FaultRay Components:     {summary['faultray_components_simulated']}\n"
        f"  Cascade Affected:        {summary['faultray_total_cascade_affected']}\n"
        f"  Max Cascade Severity:    [{cs_color}]{cascade_sev:.1f}/10[/]\n"
    )
    if summary["faultray_unmapped_resources"] > 0:
        summary_text += (
            f"  Unmapped Resources:      "
            f"[yellow]{summary['faultray_unmapped_resources']}[/]\n"
        )

    console.print()
    console.print(Panel(summary_text, title="[bold]FaultRay x Overmind[/]", border_style=sev_color))

    # -- Overmind risks table --
    risks = report["overmind"]["risks"]
    if risks:
        risk_table = Table(title="Overmind Risks", show_header=True)
        risk_table.add_column("Severity", width=10, justify="center")
        risk_table.add_column("Title", style="cyan", width=40)
        risk_table.add_column("Description", width=55)

        for risk in risks[:15]:
            r_sev = risk["severity"]
            r_color = sev_colors.get(r_sev, "white")
            risk_table.add_row(
                f"[{r_color}]{r_sev.upper()}[/]",
                risk["title"][:40],
                (risk["description"] or "")[:55],
            )

        console.print()
        console.print(risk_table)

    # -- Cascade impacts table --
    impacts = report["cascade_analysis"]["impacts"]
    if impacts:
        cascade_table = Table(title="FaultRay Cascade Impacts", show_header=True)
        cascade_table.add_column("Component", style="cyan", width=25)
        cascade_table.add_column("Triggered By", width=35)
        cascade_table.add_column("Cascade Severity", width=17, justify="center")
        cascade_table.add_column("Downstream Affected", width=20, justify="right")

        for impact in impacts[:20]:
            c_sev = impact["cascade_severity"]
            if c_sev >= 7.0:
                c_color = "red"
            elif c_sev >= 4.0:
                c_color = "yellow"
            else:
                c_color = "green"

            cascade_table.add_row(
                impact["component_name"][:25],
                impact["triggered_by"][:35],
                f"[{c_color}]{c_sev:.1f}/10[/]",
                str(len(impact["affected_downstream"])),
            )

        console.print()
        console.print(cascade_table)

    # -- Recommendations --
    recs = report.get("recommendations", [])
    if recs:
        console.print("\n[bold]Recommendations:[/]")
        for rec in recs:
            console.print(f"  [bold yellow]-[/] {rec}")

    # -- Unmapped warning --
    unmapped = report["cascade_analysis"]["unmapped_resources"]
    if unmapped:
        console.print(
            f"\n[dim]Note: {len(unmapped)} resource(s) could not be mapped to FaultRay "
            f"components: {', '.join(unmapped[:5])}"
            + (" ..." if len(unmapped) > 5 else "") + "[/]"
        )


def _print_comparison(
    blast_items: list[str],
    mapped: list[str],
    unmapped: list[str],
    coverage_pct: float,
) -> None:
    """Print Overmind vs FaultRay coverage comparison."""
    if coverage_pct >= 80:
        cov_color = "green"
    elif coverage_pct >= 50:
        cov_color = "yellow"
    else:
        cov_color = "red"

    summary_text = (
        f"[bold]Overmind vs FaultRay Coverage[/]\n\n"
        f"  Total Blast Radius Items: {len(blast_items)}\n"
        f"  Mapped to FaultRay:       [green]{len(mapped)}[/]\n"
        f"  Unmapped:                 [{'red' if unmapped else 'green'}]{len(unmapped)}[/]\n"
        f"  Coverage:                 [{cov_color}]{coverage_pct:.1f}%[/]"
    )

    console.print()
    console.print(Panel(summary_text, border_style=cov_color))

    if mapped:
        m_table = Table(title="Mapped Resources (covered by FaultRay)", show_header=False)
        m_table.add_column("Resource", style="green")
        for item in mapped[:30]:
            m_table.add_row(item)
        console.print()
        console.print(m_table)

    if unmapped:
        u_table = Table(title="Unmapped Resources (not in FaultRay model)", show_header=False)
        u_table.add_column("Resource", style="red")
        for item in unmapped[:30]:
            u_table.add_row(item)
        console.print()
        console.print(u_table)
        console.print(
            "\n[yellow]Tip:[/] Run [bold]faultray scan --aws[/] to auto-discover these "
            "resources and add them to your FaultRay model."
        )


def _write_html_report(report: dict, output_path: Path) -> None:
    """Write a minimal HTML report from the combined JSON report."""
    summary = report["summary"]
    risks = report["overmind"]["risks"]
    impacts = report["cascade_analysis"]["impacts"]
    recs = report.get("recommendations", [])

    sev_css = {
        "critical": "#c0392b",
        "high": "#e74c3c",
        "medium": "#f39c12",
        "low": "#27ae60",
        "info": "#7f8c8d",
    }

    def sev_badge(sev: str) -> str:
        color = sev_css.get(sev, "#7f8c8d")
        return (
            f'<span style="background:{color};color:#fff;padding:2px 8px;'
            f'border-radius:4px;font-size:0.85em">{sev.upper()}</span>'
        )

    risks_html = "\n".join(
        f"<tr><td>{sev_badge(r['severity'])}</td>"
        f"<td>{r['title']}</td>"
        f"<td>{r['description'][:120]}</td></tr>"
        for r in risks[:50]
    )

    impacts_html = "\n".join(
        f"<tr><td>{i['component_name']}</td>"
        f"<td>{i['triggered_by']}</td>"
        f"<td>{i['cascade_severity']:.1f}/10</td>"
        f"<td>{len(i['affected_downstream'])}</td></tr>"
        for i in impacts[:50]
    )

    recs_html = "\n".join(f"<li>{rec}</li>" for rec in recs)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>FaultRay x Overmind Report</title>
<style>
  body {{ font-family: sans-serif; max-width: 1100px; margin: 40px auto; color: #222; }}
  h1 {{ color: #2c3e50; }}
  h2 {{ color: #34495e; border-bottom: 1px solid #ecf0f1; padding-bottom: 4px; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 24px; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
  th {{ background: #f4f6f7; }}
  .summary-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }}
  .card {{ background: #f9f9f9; border: 1px solid #ddd; border-radius: 6px; padding: 16px; }}
  .card h3 {{ margin: 0 0 8px; font-size: 1em; color: #555; }}
  .card .value {{ font-size: 2em; font-weight: bold; color: #2c3e50; }}
  ul {{ padding-left: 20px; }}
  li {{ margin: 6px 0; }}
  .generated {{ color: #999; font-size: 0.85em; }}
</style>
</head>
<body>
<h1>FaultRay x Overmind Combined Report</h1>
<p class="generated">Generated: {report['generated_at']}</p>

<div class="summary-grid">
  <div class="card">
    <h3>Overmind Risks</h3>
    <div class="value">{summary['overmind_risks']}</div>
    <p>Highest: {sev_badge(summary['highest_risk_severity'])}</p>
  </div>
  <div class="card">
    <h3>Blast Radius</h3>
    <div class="value">{summary['blast_radius_items']}</div>
    <p>across {summary['overmind_changes']} change(s)</p>
  </div>
  <div class="card">
    <h3>FaultRay Cascade Severity</h3>
    <div class="value">{summary['faultray_max_cascade_severity']:.1f}/10</div>
    <p>{summary['faultray_total_cascade_affected']} component(s) affected by cascades</p>
  </div>
  <div class="card">
    <h3>FaultRay Coverage</h3>
    <div class="value">{summary['faultray_components_simulated']}</div>
    <p>components simulated
    ({summary['faultray_unmapped_resources']} unmapped)</p>
  </div>
</div>

<h2>Recommendations</h2>
<ul>{recs_html}</ul>

<h2>Overmind Risks</h2>
<table>
<thead><tr><th>Severity</th><th>Title</th><th>Description</th></tr></thead>
<tbody>{risks_html}</tbody>
</table>

<h2>FaultRay Cascade Impacts</h2>
<table>
<thead><tr><th>Component</th><th>Triggered By</th><th>Cascade Severity</th><th>Downstream Affected</th></tr></thead>
<tbody>{impacts_html}</tbody>
</table>

</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")
