"""Simulate and dynamic simulation CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

from infrasim.cli.main import (
    DEFAULT_MODEL_PATH,
    InfraGraph,
    SimulationEngine,
    _print_ai_analysis,
    _print_dynamic_results,
    app,
    console,
    print_simulation_report,
)


@app.command()
def simulate(
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path"),
    html: Path | None = typer.Option(None, "--html", help="Export HTML report to this path"),
    pdf: Path | None = typer.Option(None, "--pdf", help="Export print-ready HTML report (open in browser → Ctrl+P for PDF)"),
    md: Path | None = typer.Option(None, "--md", help="Export Markdown report to this path"),
    dynamic: bool = typer.Option(False, "--dynamic", "-d", help="Run dynamic time-stepped simulation"),
    analyze_flag: bool = typer.Option(False, "--analyze", "-a", help="Run AI analysis after simulation"),
    plugins_dir: Path | None = typer.Option(None, "--plugins-dir", help="Directory of plugin .py files to load"),
    slack_webhook: str | None = typer.Option(None, "--slack-webhook", help="Slack webhook URL for notifications"),
    pagerduty_key: str | None = typer.Option(None, "--pagerduty-key", help="PagerDuty routing key for critical alerts"),
) -> None:
    """Run chaos simulation against infrastructure model."""
    if not model.exists():
        console.print(f"[red]Model file not found: {model}[/]")
        console.print("Run [cyan]infrasim scan[/] first to create a model.")
        raise typer.Exit(1)

    # Load plugins if a directory is specified
    if plugins_dir is not None:
        from infrasim.plugins.registry import PluginRegistry

        console.print(f"[cyan]Loading plugins from {plugins_dir}...[/]")
        PluginRegistry.load_plugins_from_dir(plugins_dir)

    console.print("[cyan]Loading infrastructure model...[/]")
    graph = InfraGraph.load(model)

    if dynamic:
        from infrasim.simulator.dynamic_engine import DynamicSimulationEngine

        console.print(f"[cyan]Running dynamic simulation ({len(graph.components)} components)...[/]")
        dyn_engine = DynamicSimulationEngine(graph)
        report = dyn_engine.run_all_dynamic_defaults()
        # report is a DynamicSimulationReport; extract .results list
        results = getattr(report, "results", report) if not isinstance(report, list) else report
        _print_dynamic_results(results, console)
        return

    console.print(f"[cyan]Running chaos simulation ({len(graph.components)} components)...[/]")
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    print_simulation_report(report, console)

    if analyze_flag:
        from infrasim.ai.analyzer import InfraSimAnalyzer

        console.print("\n[cyan]Running AI analysis...[/]")
        ai_analyzer = InfraSimAnalyzer()
        ai_report = ai_analyzer.analyze(graph, report)
        _print_ai_analysis(ai_report, console)

    if html:
        from infrasim.reporter.html_report import save_html_report

        save_html_report(report, graph, html)
        console.print(f"\n[green]HTML report saved to {html}[/]")

    if pdf:
        from infrasim.reporter.pdf_report import save_pdf_ready_html

        save_pdf_ready_html(report, graph, pdf)
        console.print(f"\n[green]Print-ready HTML report saved to {pdf}[/]")
        console.print("[dim]Open in a browser and press Ctrl+P to save as PDF.[/]")

    if md:
        from infrasim.reporter.pdf_report import export_markdown

        export_markdown(report, graph, md)
        console.print(f"\n[green]Markdown report saved to {md}[/]")

    # Webhook notifications
    if slack_webhook or pagerduty_key:
        import asyncio

        from infrasim.api.server import _report_to_dict

        report_dict = _report_to_dict(report)

        async def _send_notifications():
            if slack_webhook:
                from infrasim.integrations.webhooks import send_slack_notification

                ok = await send_slack_notification(slack_webhook, report_dict)
                if ok:
                    console.print("[green]Slack notification sent.[/]")
                else:
                    console.print("[yellow]Slack notification failed.[/]")
            if pagerduty_key:
                from infrasim.integrations.webhooks import send_pagerduty_event

                ok = await send_pagerduty_event(pagerduty_key, report_dict)
                if ok:
                    console.print("[green]PagerDuty event sent.[/]")
                else:
                    console.print("[dim]PagerDuty: no critical findings, event skipped.[/]")

        try:
            asyncio.run(_send_notifications())
        except Exception as exc:
            console.print(f"[yellow]Webhook notification error: {exc}[/]")


@app.command()
def dynamic(
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path"),
    html: Path | None = typer.Option(None, "--html", help="Export HTML report to this path"),
    duration: int = typer.Option(300, "--duration", help="Simulation duration in seconds"),
    step: int = typer.Option(5, "--step", help="Time step interval in seconds"),
) -> None:
    """Run dynamic time-stepped chaos simulation with realistic traffic patterns."""
    if not model.exists():
        console.print(f"[red]Model file not found: {model}[/]")
        console.print("Run [cyan]infrasim scan[/] first to create a model.")
        raise typer.Exit(1)

    console.print("[cyan]Loading infrastructure model...[/]")
    graph = InfraGraph.load(model)

    from infrasim.simulator.dynamic_engine import DynamicSimulationEngine

    console.print(
        f"[cyan]Running dynamic simulation "
        f"({len(graph.components)} components, "
        f"duration={duration}s, step={step}s)...[/]"
    )
    engine = DynamicSimulationEngine(graph)
    report = engine.run_all_dynamic_defaults(duration=duration, step=step)
    # report is a DynamicSimulationReport; extract .results list
    results = getattr(report, "results", report) if not isinstance(report, list) else report
    _print_dynamic_results(results, console)

    if html:
        from infrasim.reporter.html_report import save_html_report

        save_html_report(results, graph, html)
        console.print(f"\n[green]HTML report saved to {html}[/]")
