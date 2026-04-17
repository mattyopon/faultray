# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI commands for the autonomous remediation agent.

Provides: run, pending, approve, history, report subcommands.
"""

from __future__ import annotations

import json

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import DEFAULT_MODEL_PATH, app, console

remediate_app = typer.Typer(
    name="remediate",
    help="Autonomous remediation agent — detect, plan, simulate, execute, verify",
    no_args_is_help=True,
)
app.add_typer(remediate_app, name="remediate")


# ---------------------------------------------------------------------------
# Common options
# ---------------------------------------------------------------------------

_MODEL_OPT = typer.Option(
    str(DEFAULT_MODEL_PATH),
    "--model",
    "-m",
    help="Model file path (JSON or YAML)",
)
_OUTPUT_DIR_OPT = typer.Option(
    "~/.faultray/remediation/",
    "--output-dir",
    "-o",
    help="Output directory for cycles and reports",
)


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


@remediate_app.command("run")
def remediate_run(
    model: str = _MODEL_OPT,
    auto_approve: bool = typer.Option(
        False,
        "--auto-approve",
        help="Skip human approval step",
    ),
    max_risk: str = typer.Option(
        "medium",
        "--max-risk",
        help="Maximum risk level to auto-execute: low, medium, high",
    ),
    apply: bool = typer.Option(
        False,
        "--apply/--dry-run",
        help="Execute for real (--apply) or preview only (--dry-run)",
    ),
    cloud: str | None = typer.Option(
        None,
        "--cloud",
        help="Cloud provider for auto-discovery (aws, gcp, azure)",
    ),
    region: str | None = typer.Option(
        None,
        "--region",
        help="Cloud region for auto-discovery",
    ),
    terraform_dir: str | None = typer.Option(
        None,
        "--terraform-dir",
        help="Directory for terraform execution",
    ),
    output_dir: str = _OUTPUT_DIR_OPT,
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output JSON instead of rich formatting",
    ),
) -> None:
    """Run one full autonomous remediation cycle.

    Dry-run by default (safe preview mode). Use --apply to execute for real.

    Examples:
        # Preview remediation plan (dry-run)
        faultray remediate run

        # Auto-approve and execute
        faultray remediate run --auto-approve --max-risk medium

        # Execute for real
        faultray remediate run --apply --auto-approve

        # With cloud auto-discovery
        faultray remediate run --cloud aws --region ap-northeast-1
    """
    from faultray.remediation.autonomous_agent import (
        AutonomousRemediationAgent,
    )

    agent = AutonomousRemediationAgent(
        model_path=model,
        auto_approve=auto_approve,
        max_risk_level=max_risk,
        dry_run=not apply,
        output_dir=output_dir,
        cloud_provider=cloud,
        terraform_dir=terraform_dir,
    )

    try:
        cycle = agent.run_cycle()
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from None
    except Exception as exc:
        console.print(f"[red]Remediation failed: {exc}[/]")
        raise typer.Exit(1) from None

    if json_output:
        console.print_json(json.dumps(cycle.to_dict()))
        return

    _print_cycle_summary(cycle)


# ---------------------------------------------------------------------------
# pending
# ---------------------------------------------------------------------------


@remediate_app.command("pending")
def remediate_pending(
    model: str = _MODEL_OPT,
    output_dir: str = _OUTPUT_DIR_OPT,
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """List remediation cycles awaiting approval.

    Example:
        faultray remediate pending
    """
    from faultray.remediation.autonomous_agent import (
        AutonomousRemediationAgent,
    )

    agent = AutonomousRemediationAgent(
        model_path=model, output_dir=output_dir
    )
    pending = agent.list_pending()

    if json_output:
        console.print_json(
            json.dumps([c.to_dict() for c in pending])
        )
        return

    if not pending:
        console.print("[dim]No pending approvals.[/]")
        return

    table = Table(title="Pending Approvals")
    table.add_column("Cycle ID", style="bold cyan")
    table.add_column("Started")
    table.add_column("Score")
    table.add_column("Issues")
    table.add_column("Est. Cost")

    for c in pending:
        table.add_row(
            c.id,
            c.started_at[:19],
            f"{c.initial_score:.1f}",
            str(len(c.issues_found)),
            c.estimated_cost,
        )

    console.print(table)
    console.print(
        "\n[dim]To approve: faultray remediate approve <cycle-id>[/]"
    )


# ---------------------------------------------------------------------------
# approve
# ---------------------------------------------------------------------------


@remediate_app.command("approve")
def remediate_approve(
    cycle_id: str = typer.Argument(help="Cycle ID to approve and execute"),
    model: str = _MODEL_OPT,
    output_dir: str = _OUTPUT_DIR_OPT,
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Approve a pending remediation cycle and execute it.

    Example:
        faultray remediate approve abc123def456
    """
    from faultray.remediation.autonomous_agent import (
        AutonomousRemediationAgent,
    )

    agent = AutonomousRemediationAgent(
        model_path=model, output_dir=output_dir
    )

    try:
        cycle = agent.approve_and_execute(cycle_id)
    except FileNotFoundError:
        console.print(f"[red]Cycle not found: {cycle_id}[/]")
        raise typer.Exit(1) from None
    except ValueError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from None

    if json_output:
        console.print_json(json.dumps(cycle.to_dict()))
        return

    _print_cycle_summary(cycle)


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------


@remediate_app.command("history")
def remediate_history(
    model: str = _MODEL_OPT,
    output_dir: str = _OUTPUT_DIR_OPT,
    limit: int = typer.Option(20, "--limit", "-n", help="Max entries"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """View history of remediation cycles.

    Example:
        faultray remediate history --limit 10
    """
    from faultray.remediation.autonomous_agent import (
        AutonomousRemediationAgent,
    )

    agent = AutonomousRemediationAgent(
        model_path=model, output_dir=output_dir
    )
    history = agent.list_history()[:limit]

    if json_output:
        console.print_json(
            json.dumps([c.to_dict() for c in history])
        )
        return

    if not history:
        console.print("[dim]No remediation history.[/]")
        return

    table = Table(title="Remediation History")
    table.add_column("Cycle ID", style="bold cyan")
    table.add_column("Status")
    table.add_column("Started")
    table.add_column("Score Before")
    table.add_column("Score After")
    table.add_column("Improvement")
    table.add_column("Issues")

    for c in history:
        status_style = {
            "completed": "green",
            "failed": "red",
            "rolled_back": "yellow",
            "awaiting_approval": "blue",
        }.get(c.status, "white")
        final = c.final_score if c.final_score is not None else c.simulated_score
        imp = c.improvement_achieved if c.improvement_achieved is not None else 0.0
        table.add_row(
            c.id,
            f"[{status_style}]{c.status}[/]",
            c.started_at[:19],
            f"{c.initial_score:.1f}",
            f"{final:.1f}",
            f"+{imp:.1f}",
            str(len(c.issues_found)),
        )

    console.print(table)


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


@remediate_app.command("report")
def remediate_report(
    model: str = _MODEL_OPT,
    output_dir: str = _OUTPUT_DIR_OPT,
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """View the latest remediation report.

    Example:
        faultray remediate report
        faultray remediate report --json
    """
    from faultray.remediation.autonomous_agent import (
        AutonomousRemediationAgent,
    )

    agent = AutonomousRemediationAgent(
        model_path=model, output_dir=output_dir
    )

    if json_output:
        data = agent.get_latest_report_json()
        if data is None:
            console.print("[dim]No reports found.[/]")
            raise typer.Exit(1)
        console.print_json(json.dumps(data))
        return

    report = agent.get_latest_report()
    if report is None:
        console.print("[dim]No reports found.[/]")
        raise typer.Exit(1)

    from rich.markdown import Markdown

    console.print(Markdown(report))


# ---------------------------------------------------------------------------
# Shared display helper
# ---------------------------------------------------------------------------


def _print_cycle_summary(cycle: object) -> None:
    """Print a rich summary of a remediation cycle."""
    from faultray.remediation.autonomous_agent import RemediationCycle

    c: RemediationCycle = cycle  # type: ignore[assignment]

    status_color = {
        "completed": "green",
        "failed": "red",
        "rolled_back": "yellow",
        "awaiting_approval": "blue",
        "detecting": "cyan",
        "planning": "cyan",
        "simulating": "cyan",
        "executing": "cyan",
        "verifying": "cyan",
    }.get(c.status, "white")

    final = c.final_score if c.final_score is not None else c.simulated_score
    improvement = c.improvement_achieved if c.improvement_achieved is not None else 0.0

    # Summary panel
    summary = Table.grid(padding=(0, 2))
    summary.add_column(style="bold")
    summary.add_column()
    summary.add_row("Cycle ID", c.id)
    summary.add_row("Status", f"[{status_color}]{c.status}[/]")
    summary.add_row("Score", f"{c.initial_score:.1f} -> {final:.1f} (+{improvement:.1f})")
    summary.add_row("Issues Found", str(len(c.issues_found)))
    summary.add_row("Est. Cost", c.estimated_cost)

    if c.ratchet_state:
        level = c.ratchet_state.get("final_level", "N/A")
        perms = c.ratchet_state.get("remaining_permissions", [])
        summary.add_row("Ratchet Level", level)
        summary.add_row("Permissions", ", ".join(perms))

    console.print(Panel(summary, title="Remediation Cycle", border_style=status_color))

    # Issues table
    if c.issues_found:
        issues_table = Table(title="Issues Detected")
        issues_table.add_column("#", style="dim")
        issues_table.add_column("Description")
        issues_table.add_column("Priority")
        issues_table.add_column("Components")

        for i, issue in enumerate(c.issues_found, 1):
            pri = issue.get("priority", "")
            pri_color = {"immediate": "red", "urgent": "yellow", "planned": "blue"}.get(
                pri, "white"
            )
            issues_table.add_row(
                str(i),
                issue.get("description", ""),
                f"[{pri_color}]{pri}[/]",
                ", ".join(issue.get("affected_components", [])),
            )
        console.print(issues_table)

    # Execution log
    if c.execution_log:
        exec_table = Table(title="Execution Log")
        exec_table.add_column("Step")
        exec_table.add_column("Status")
        exec_table.add_column("Details", max_width=60)

        for entry in c.execution_log:
            status = entry.get("status", "")
            st_color = {
                "success": "green",
                "dry_run": "blue",
                "blocked": "yellow",
                "failed": "red",
            }.get(status, "white")
            detail = entry.get("output", entry.get("reason", ""))
            exec_table.add_row(
                entry.get("step", ""),
                f"[{st_color}]{status}[/]",
                str(detail)[:60] if detail else "",
            )
        console.print(exec_table)

    # Report summary
    if c.report_summary:
        console.print(f"\n[bold]{c.report_summary}[/]")

    if c.status == "awaiting_approval":
        console.print(
            f"\n[yellow]Cycle awaiting approval. Run:[/] "
            f"[bold]faultray remediate approve {c.id}[/]"
        )
