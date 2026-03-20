# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Typer app creation, common imports, and shared helpers for the CLI."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from faultray.model.graph import InfraGraph

app = typer.Typer(
    name="faultray",
    help="FaultRay — Zero-risk infrastructure chaos engineering simulator",
    no_args_is_help=True,
)
console = Console()

DEFAULT_MODEL_PATH = Path("faultray-model.json")


def _version_callback(value: bool) -> None:
    if value:
        from faultray import __version__

        print(f"FaultRay v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V", callback=_version_callback, is_eager=True,
        help="Show version and exit.",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v",
        help="Enable verbose logging (INFO level).",
    ),
    debug: bool = typer.Option(
        False, "--debug",
        help="Enable debug logging (DEBUG level).",
    ),
) -> None:
    """FaultRay — Zero-risk infrastructure chaos engineering simulator."""
    if debug or verbose:
        from faultray.log_config import setup_logging

        level = "DEBUG" if debug else "INFO"
        setup_logging(level=level)


def _print_dynamic_results(results: list, con: Console) -> None:
    """Print a summary of dynamic simulation results to the console."""
    if not results:
        con.print("\n[yellow]No dynamic scenarios to report.[/]")
        return

    total = len(results)
    critical = sum(1 for r in results if getattr(r, "is_critical", False))
    warning = sum(1 for r in results if getattr(r, "is_warning", False))
    passed = total - critical - warning

    con.print("\n[bold]Dynamic Simulation Results[/]")
    con.print(
        f"  Total: [bold]{total}[/]  "
        f"[red]Critical: {critical}[/]  "
        f"[yellow]Warning: {warning}[/]  "
        f"[green]Passed: {passed}[/]\n"
    )

    for r in results:
        is_critical = getattr(r, "is_critical", False)
        is_warning = getattr(r, "is_warning", False)
        if not is_critical and not is_warning:
            continue

        color = "red" if is_critical else "yellow"
        label = "CRITICAL" if is_critical else "WARNING"
        name = getattr(r, "scenario", None)
        name = getattr(name, "name", "unknown") if name else "unknown"
        peak_time = getattr(r, "peak_time_seconds", None)
        peak_sev = getattr(r, "peak_severity", 0.0)
        recovery = getattr(r, "recovery_time_seconds", None)
        autoscale = getattr(r, "autoscaling_events", [])
        failover = getattr(r, "failover_events", [])

        con.print(f"  [{color}]{label}[/] {name} (severity: {peak_sev:.1f})")
        if peak_time is not None:
            con.print(f"    Peak severity at: t={peak_time}s")
        if recovery is not None:
            con.print(f"    Recovery time: {recovery}s")
        else:
            con.print("    Recovery time: [red]no recovery[/]")
        con.print(f"    Autoscaling events: {len(autoscale)}")
        con.print(f"    Failover events: {len(failover)}")
        con.print()


def _print_ai_analysis(ai_report: "AIAnalysisReport", con: Console) -> None:  # noqa: F821
    """Print AI analysis results with Rich formatting."""
    from rich.panel import Panel
    from rich.table import Table

    # Summary panel
    con.print()
    con.print(Panel(
        f"[bold]{ai_report.summary}[/]",
        title="[bold]AI Analysis Summary[/]",
        border_style="cyan",
    ))

    # Top risks
    if ai_report.top_risks:
        con.print("\n[bold cyan]Top Risks:[/]")
        for i, risk in enumerate(ai_report.top_risks, 1):
            con.print(f"  {i}. {risk}")

    # Availability assessment
    con.print(f"\n[bold]Availability:[/] {ai_report.availability_assessment}")
    con.print(
        f"  Estimated: [bold]{ai_report.estimated_current_nines:.1f}[/] nines "
        f"| Potential: [bold]{ai_report.theoretical_max_nines:.1f}[/] nines"
    )

    # Recommendations table
    if ai_report.recommendations:
        rec_table = Table(title="Recommendations", show_header=True)
        rec_table.add_column("Sev", width=9, justify="center")
        rec_table.add_column("Category", width=10)
        rec_table.add_column("Title", style="cyan", width=30)
        rec_table.add_column("Remediation", width=40)
        rec_table.add_column("Impact", width=20)
        rec_table.add_column("Effort", width=8, justify="center")

        sev_colors = {
            "critical": "bold red",
            "high": "red",
            "medium": "yellow",
            "low": "green",
        }
        for rec in ai_report.recommendations:
            color = sev_colors.get(rec.severity, "white")
            rec_table.add_row(
                f"[{color}]{rec.severity.upper()}[/]",
                rec.category,
                rec.title,
                rec.remediation[:80] + ("..." if len(rec.remediation) > 80 else ""),
                rec.estimated_impact,
                rec.effort,
            )

        con.print()
        con.print(rec_table)

    # Upgrade path
    if ai_report.upgrade_path:
        con.print()
        con.print(Panel(
            ai_report.upgrade_path,
            title="[bold]Upgrade Path[/]",
            border_style="green",
        ))


def _print_ops_results(result: "OpsSimulationResult", con: Console) -> None:  # noqa: F821
    """Print operational simulation results using Rich formatting."""
    from rich.panel import Panel
    from rich.table import Table

    scenario = result.scenario

    # ---- 1. Simulation Summary Box ----------------------------------------
    # Use average availability for color (min_availability is too volatile
    # due to brief deploy-induced dips) --- still display min in the output.
    avg_avail_for_color = 100.0
    if result.sli_timeline:
        avg_avail_for_color = sum(p.availability_percent for p in result.sli_timeline) / len(result.sli_timeline)
    avail = result.min_availability
    if avg_avail_for_color >= 99.9:
        avail_color = "green"
    elif avg_avail_for_color >= 99.0:
        avail_color = "yellow"
    else:
        avail_color = "red"

    total_events = len(result.events)
    downtime_min = result.total_downtime_seconds / 60.0
    num_steps = len(result.sli_timeline)

    # Calculate average availability from SLI timeline
    avg_avail = 100.0
    if result.sli_timeline:
        avg_avail = sum(p.availability_percent for p in result.sli_timeline) / len(result.sli_timeline)

    summary_text = (
        f"[bold]Scenario:[/] {scenario.name}\n"
        f"[bold]Duration:[/] {scenario.duration_days} days  "
        f"[bold]Steps:[/] {num_steps:,}\n\n"
        f"[bold]Avg Availability:[/] [{avail_color}]{avg_avail:.4f}%[/]  "
        f"[bold]Min Availability:[/] {avail:.2f}%\n"
        f"[bold]Total Downtime:[/] {downtime_min:.1f} min  "
        f"[bold]Peak Utilization:[/] {result.peak_utilization:.1f}%\n"
        f"[bold]Deploys:[/] {result.total_deploys}  "
        f"[bold]Failures:[/] {result.total_failures}  "
        f"[bold]Degradation Events:[/] {result.total_degradation_events}\n"
        f"[bold]Total Events:[/] {total_events}"
    )

    con.print()
    con.print(Panel(
        summary_text,
        title="[bold]FaultRay Operational Simulation Report[/]",
        border_style=avail_color,
    ))

    # ---- 2. Error Budget Table --------------------------------------------
    if result.error_budget_statuses:
        budget_table = Table(title="Error Budget Status", show_header=True)
        budget_table.add_column("SLO", style="cyan", width=22)
        budget_table.add_column("Component", width=16)
        budget_table.add_column("Total", width=10, justify="right")
        budget_table.add_column("Consumed", width=10, justify="right")
        budget_table.add_column("Remaining", width=10, justify="right")
        budget_table.add_column("Remaining %", width=12, justify="right")
        budget_table.add_column("Burn 1h", width=8, justify="right")
        budget_table.add_column("Burn 6h", width=8, justify="right")
        budget_table.add_column("Status", width=10, justify="center")

        for eb in result.error_budget_statuses:
            pct = eb.budget_remaining_percent
            if pct >= 50:
                pct_color = "green"
            elif pct >= 20:
                pct_color = "yellow"
            else:
                pct_color = "red"

            status = "[bold red]EXHAUSTED[/]" if eb.is_budget_exhausted else f"[{pct_color}]OK[/]"

            budget_table.add_row(
                eb.slo.name or eb.slo.metric,
                eb.component_id or "system",
                f"{eb.budget_total_minutes:.1f}m",
                f"{eb.budget_consumed_minutes:.1f}m",
                f"{eb.budget_remaining_minutes:.1f}m",
                f"[{pct_color}]{pct:.1f}%[/]",
                f"{eb.burn_rate_1h:.2f}x",
                f"{eb.burn_rate_6h:.2f}x",
                status,
            )

        con.print()
        con.print(budget_table)

    # ---- 3. Incident Timeline (last 25 events) ---------------------------
    if result.events:
        # Show last 25 events
        recent = result.events[-25:]
        event_table = Table(title=f"Event Timeline (last {len(recent)} of {total_events})", show_header=True)
        event_table.add_column("Time", style="dim", width=12)
        event_table.add_column("Type", width=18)
        event_table.add_column("Component", style="cyan", width=20)
        event_table.add_column("Description", width=50)

        for ev in recent:
            hours = ev.time_seconds / 3600
            day = int(hours // 24) + 1
            hour = int(hours % 24)
            time_str = f"Day {day} {hour:02d}:00"

            etype = ev.event_type.value
            if etype in ("random_failure", "memory_leak_oom", "disk_full", "conn_pool_exhaustion"):
                type_style = f"[red]{etype}[/]"
            elif etype == "deploy":
                type_style = f"[yellow]{etype}[/]"
            else:
                type_style = f"[dim]{etype}[/]"

            event_table.add_row(
                time_str,
                type_style,
                ev.target_component_id,
                (ev.description or "")[:50],
            )

        con.print()
        con.print(event_table)

    # ---- 4. Summary -------------------------------------------------------
    if result.summary:
        con.print()
        con.print(f"[dim]{result.summary}[/]")


def _print_whatif_result(result: object, con: Console) -> None:
    """Print a single what-if analysis result using Rich formatting."""
    from rich.panel import Panel
    from rich.table import Table

    param_name = getattr(result, "parameter", "Unknown")
    values = getattr(result, "values", [])
    avg_availabilities = getattr(result, "avg_availabilities", [])
    min_availabilities = getattr(result, "min_availabilities", [])
    total_failures = getattr(result, "total_failures", [])
    total_downtimes = getattr(result, "total_downtimes", [])
    slo_pass = getattr(result, "slo_pass", [])
    breakpoint_val = getattr(result, "breakpoint_value", None)

    display_name = param_name.replace("_", " ").title()

    table = Table(show_header=True, header_style="bold")
    table.add_column("Factor", justify="right", width=8)
    table.add_column("Avg Avail", justify="right", width=10)
    table.add_column("Min Avail", justify="right", width=10)
    table.add_column("Failures", justify="right", width=10)
    table.add_column("Downtime(s)", justify="right", width=12)
    table.add_column("SLO", justify="center", width=6)

    for i, value in enumerate(values):
        avg_avail = avg_availabilities[i] if i < len(avg_availabilities) else 0.0
        min_avail = min_availabilities[i] if i < len(min_availabilities) else 0.0
        failures = total_failures[i] if i < len(total_failures) else 0
        downtime = total_downtimes[i] if i < len(total_downtimes) else 0.0
        passed = slo_pass[i] if i < len(slo_pass) else True

        slo_str = "[green]PASS[/]" if passed else "[red]FAIL[/]"
        table.add_row(
            f"{value:.2f}",
            f"{avg_avail:.4f}%",
            f"{min_avail:.2f}%",
            str(failures),
            f"{downtime:.1f}",
            slo_str,
        )

    con.print(Panel(
        table,
        title=f"[bold]What-if Analysis: {display_name}[/]",
        subtitle=f"Breakpoint: factor {breakpoint_val:.2f}" if breakpoint_val is not None else None,
    ))


def _print_multi_whatif_result(result: object, con: Console) -> None:
    """Print a multi-parameter what-if analysis result using Rich formatting."""
    from rich.panel import Panel
    from rich.table import Table

    parameters = getattr(result, "parameters", {})
    avg_avail = getattr(result, "avg_availability", 0.0)
    min_avail = getattr(result, "min_availability", 0.0)
    total_fail = getattr(result, "total_failures", 0)
    downtime = getattr(result, "total_downtime_seconds", 0)
    slo_passed = getattr(result, "slo_pass", True)
    description = getattr(result, "summary", "").split("\n")[0] if getattr(result, "summary", "") else ""

    # Title from description or parameters
    if description.startswith("Analysis: "):
        title = description[len("Analysis: "):]
    else:
        title = ", ".join(f"{k}={v}" for k, v in parameters.items())

    table = Table(show_header=True, header_style="bold")
    table.add_column("Parameter", width=24)
    table.add_column("Value", justify="right", width=8)

    for param, value in parameters.items():
        table.add_row(param, f"{value:.2f}")

    table.add_section()
    table.add_row("Avg Availability", f"{avg_avail:.4f}%")
    table.add_row("Min Availability", f"{min_avail:.2f}%")
    table.add_row("Total Failures", str(total_fail))
    table.add_row("Total Downtime (s)", str(downtime))

    slo_str = "[green]PASS[/]" if slo_passed else "[red]FAIL[/]"
    table.add_row("SLO (99.9%)", slo_str)

    con.print(Panel(table, title=f"[bold]Multi What-if: {title}[/]"))


def _load_graph_for_analysis(
    model: Path,
    yaml_file: Path | None,
) -> InfraGraph:
    """Load an InfraGraph from model JSON or YAML for analysis commands."""
    if yaml_file is not None:
        from faultray.model.loader import load_yaml

        if not yaml_file.exists():
            console.print(f"[red]Model file not found: {yaml_file}[/]")
            console.print("[dim]Try: faultray scan --aws  (auto-discover)[/]")
            console.print("[dim]Or:  faultray quickstart  (interactive builder)[/]")
            console.print("[dim]Or:  faultray demo        (demo infrastructure)[/]")
            raise typer.Exit(1)
        return load_yaml(yaml_file)

    if not model.exists():
        console.print(f"[red]Model file not found: {model}[/]")
        console.print("[dim]Try: faultray scan --aws  (auto-discover)[/]")
        console.print("[dim]Or:  faultray quickstart  (interactive builder)[/]")
        console.print("[dim]Or:  faultray demo        (demo infrastructure)[/]")
        raise typer.Exit(1)

    if str(model).endswith((".yaml", ".yml")):
        from faultray.model.loader import load_yaml

        return load_yaml(model)

    return InfraGraph.load(model)
