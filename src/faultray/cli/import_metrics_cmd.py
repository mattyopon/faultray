# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""CLI command for the Observability Integration Hub."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console


@app.command("import-metrics")
def import_metrics(
    model_file: Path = typer.Argument(
        ...,
        help="Path to YAML/JSON infrastructure model file.",
    ),
    datadog: bool = typer.Option(
        False, "--datadog",
        help="Import from Datadog.",
    ),
    newrelic: bool = typer.Option(
        False, "--newrelic",
        help="Import from New Relic.",
    ),
    grafana: bool = typer.Option(
        False, "--grafana",
        help="Import from Grafana.",
    ),
    json_file: str = typer.Option(
        "", "--json-file",
        help="Path to JSON metrics file for import.",
    ),
    api_key: str = typer.Option(
        "", "--api-key",
        help="API key for the monitoring platform.",
    ),
    app_key: str = typer.Option(
        "", "--app-key",
        help="Application key (Datadog only).",
    ),
    account_id: str = typer.Option(
        "", "--account-id",
        help="Account ID (New Relic only).",
    ),
    grafana_url: str = typer.Option(
        "", "--grafana-url",
        help="Grafana base URL.",
    ),
    dashboard_uid: str = typer.Option(
        "", "--dashboard-uid",
        help="Grafana dashboard UID.",
    ),
    hours: int = typer.Option(
        24, "--hours",
        help="Hours of historical data to import.",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON.",
    ),
) -> None:
    """Import metrics from monitoring platforms to calibrate simulations.

    Imports real metrics from Datadog, New Relic, Grafana, or a JSON file
    and applies them to the infrastructure model for more accurate
    simulation results.

    Examples:
        faultray import-metrics infra.yaml --datadog --api-key <key> --app-key <key>
        faultray import-metrics infra.yaml --newrelic --api-key <key> --account-id <id>
        faultray import-metrics infra.yaml --grafana --grafana-url http://grafana:3000 --api-key <key> --dashboard-uid abc123
        faultray import-metrics infra.yaml --json-file metrics.json
    """
    from faultray.integrations.observability import ObservabilityHub

    graph = _load_graph_for_analysis(model_file, None)
    hub = ObservabilityHub(graph)

    if datadog:
        if not api_key or not app_key:
            console.print("[red]--api-key and --app-key are required for Datadog[/]")
            raise typer.Exit(1)

        if not json_output:
            console.print(f"[cyan]Importing metrics from Datadog (last {hours}h)...[/]")

        result = hub.import_from_datadog(api_key, app_key, hours=hours)

    elif newrelic:
        if not api_key or not account_id:
            console.print("[red]--api-key and --account-id are required for New Relic[/]")
            raise typer.Exit(1)

        if not json_output:
            console.print(f"[cyan]Importing metrics from New Relic (last {hours}h)...[/]")

        result = hub.import_from_newrelic(api_key, account_id, hours=hours)

    elif grafana:
        if not api_key or not grafana_url or not dashboard_uid:
            console.print("[red]--api-key, --grafana-url, and --dashboard-uid are required for Grafana[/]")
            raise typer.Exit(1)

        if not json_output:
            console.print("[cyan]Importing metrics from Grafana...[/]")

        result = hub.import_from_grafana(grafana_url, api_key, dashboard_uid)

    elif json_file:
        json_path = Path(json_file)
        if not json_path.exists():
            console.print(f"[red]JSON file not found: {json_file}[/]")
            raise typer.Exit(1)

        if not json_output:
            console.print(f"[cyan]Importing metrics from {json_file}...[/]")

        result = hub.import_from_json(json_path)

    else:
        console.print("[red]Specify a source: --datadog, --newrelic, --grafana, or --json-file[/]")
        raise typer.Exit(1)

    if json_output:
        data = {
            "source": result.source,
            "components_updated": result.components_updated,
            "metrics_imported": result.metrics_imported,
            "calibration_applied": result.calibration_applied,
            "errors": result.errors,
            "details": result.details,
        }
        console.print_json(data=data)
        return

    # Rich output
    status_color = "green" if result.calibration_applied else "yellow"
    summary = (
        f"[bold]Source:[/] {result.source}\n"
        f"[bold]Components Updated:[/] [{status_color}]{result.components_updated}[/]\n"
        f"[bold]Metrics Imported:[/] [{status_color}]{result.metrics_imported}[/]\n"
        f"[bold]Calibration Applied:[/] [{status_color}]{result.calibration_applied}[/]"
    )

    console.print()
    console.print(Panel(
        summary,
        title="[bold]Metric Import Results[/]",
        border_style=status_color,
    ))

    if result.details:
        detail_table = Table(title="Imported Metrics", show_header=True)
        detail_table.add_column("Component", style="cyan", width=20)
        detail_table.add_column("Metric", width=20)
        detail_table.add_column("Value", justify="right", width=12)

        for d in result.details:
            detail_table.add_row(
                d.get("component_id", ""),
                d.get("metric", ""),
                f"{d.get('value', 0):.2f}",
            )

        console.print()
        console.print(detail_table)

    if result.errors:
        console.print()
        console.print("[bold yellow]Warnings/Errors:[/]")
        for err in result.errors:
            console.print(f"  [yellow]- {err}[/]")
