# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

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
        envvar="FAULTRAY_API_KEY",
        help="API key for the monitoring platform (or set FAULTRAY_API_KEY to avoid passing it on the CLI).",
    ),
    app_key: str = typer.Option(
        "", "--app-key",
        envvar="FAULTRAY_APP_KEY",
        help="Application key, Datadog only (or set FAULTRAY_APP_KEY to avoid passing it on the CLI).",
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

    # Exactly one source may be active at a time; elif precedence would
    # otherwise silently ignore the others.
    active_sources = sum(bool(s) for s in (datadog, newrelic, grafana, json_file))
    if active_sources > 1:
        console.print(
            "[red]Specify only one source: --datadog, --newrelic, --grafana, or --json-file.[/]"
        )
        raise typer.Exit(1)

    try:
        result = _dispatch_import(
            hub,
            datadog=datadog,
            newrelic=newrelic,
            grafana=grafana,
            json_file=json_file,
            api_key=api_key,
            app_key=app_key,
            account_id=account_id,
            grafana_url=grafana_url,
            dashboard_uid=dashboard_uid,
            hours=hours,
            json_output=json_output,
        )
    except typer.Exit:
        # Validation errors inside the dispatch already printed a clean message.
        raise
    except (OSError, ValueError) as exc:
        console.print(f"[red]Metric import failed: {exc}[/]")
        raise typer.Exit(1)
    except Exception as exc:  # noqa: BLE001 - surface HTTP/client errors cleanly
        console.print(f"[red]Metric import failed: {type(exc).__name__}: {exc}[/]")
        raise typer.Exit(1)

    _render_import_result(result, json_output)


def _dispatch_import(
    hub,
    *,
    datadog: bool,
    newrelic: bool,
    grafana: bool,
    json_file: str,
    api_key: str,
    app_key: str,
    account_id: str,
    grafana_url: str,
    dashboard_uid: str,
    hours: int,
    json_output: bool,
):
    """Resolve the requested source and import metrics from it."""
    if datadog:
        if not api_key or not app_key:
            console.print("[red]--api-key and --app-key are required for Datadog[/]")
            raise typer.Exit(1)

        if not json_output:
            console.print(f"[cyan]Importing metrics from Datadog (last {hours}h)...[/]")

        return hub.import_from_datadog(api_key, app_key, hours=hours)

    elif newrelic:
        if not api_key or not account_id:
            console.print("[red]--api-key and --account-id are required for New Relic[/]")
            raise typer.Exit(1)

        if not json_output:
            console.print(f"[cyan]Importing metrics from New Relic (last {hours}h)...[/]")

        return hub.import_from_newrelic(api_key, account_id, hours=hours)

    elif grafana:
        if not api_key or not grafana_url or not dashboard_uid:
            console.print("[red]--api-key, --grafana-url, and --dashboard-uid are required for Grafana[/]")
            raise typer.Exit(1)

        if not json_output:
            console.print("[cyan]Importing metrics from Grafana...[/]")

        return hub.import_from_grafana(grafana_url, api_key, dashboard_uid)

    elif json_file:
        json_path = Path(json_file)
        if not json_path.exists():
            console.print(f"[red]JSON file not found: {json_file}[/]")
            raise typer.Exit(1)

        if not json_output:
            console.print(f"[cyan]Importing metrics from {json_file}...[/]")

        return hub.import_from_json(json_path)

    else:
        console.print("[red]Specify a source: --datadog, --newrelic, --grafana, or --json-file[/]")
        raise typer.Exit(1)


def _render_import_result(result, json_output: bool) -> None:
    """Render an import result as JSON or a Rich summary."""
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
            raw_value = d.get("value")
            value = float(raw_value) if isinstance(raw_value, (int, float)) else 0.0
            detail_table.add_row(
                d.get("component_id", ""),
                d.get("metric", ""),
                f"{value:.2f}",
            )

        console.print()
        console.print(detail_table)

    if result.errors:
        console.print()
        console.print("[bold yellow]Warnings/Errors:[/]")
        for err in result.errors:
            console.print(f"  [yellow]- {err}[/]")
