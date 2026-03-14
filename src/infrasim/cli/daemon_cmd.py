"""CLI command for running the monitoring daemon."""

from __future__ import annotations

import re
from pathlib import Path

import typer

from infrasim.cli.main import DEFAULT_MODEL_PATH, app, console


def _parse_interval(interval_str: str) -> int:
    """Parse a human-readable interval string to seconds.

    Supports formats like: '1h', '30m', '3600', '1h30m', '90s'.
    """
    # If it's just a number, treat as seconds
    try:
        return int(interval_str)
    except ValueError:
        pass

    total = 0
    pattern = re.compile(r"(\d+)\s*([hms])", re.IGNORECASE)
    matches = pattern.findall(interval_str)
    if not matches:
        raise ValueError(
            f"Invalid interval format: '{interval_str}'. "
            "Use formats like '1h', '30m', '3600', '1h30m', '90s'."
        )

    for value, unit in matches:
        value = int(value)
        if unit.lower() == "h":
            total += value * 3600
        elif unit.lower() == "m":
            total += value * 60
        elif unit.lower() == "s":
            total += value

    return total


@app.command(name="daemon")
def daemon_command(
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path"),
    interval: str = typer.Option("1h", "--interval", "-i", help="Scan interval (e.g. 1h, 30m, 3600)"),
    slack_webhook: str | None = typer.Option(None, "--slack-webhook", help="Slack webhook URL"),
    pagerduty_key: str | None = typer.Option(None, "--pagerduty-key", help="PagerDuty routing key"),
    teams_webhook: str | None = typer.Option(None, "--teams-webhook", help="Microsoft Teams webhook URL"),
) -> None:
    """Run continuous monitoring daemon that scans infrastructure on interval."""
    if not model.exists():
        console.print(f"[red]Model file not found: {model}[/]")
        console.print("Run [cyan]infrasim scan[/] first to create a model.")
        raise typer.Exit(1)

    try:
        interval_seconds = _parse_interval(interval)
    except ValueError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)

    if interval_seconds < 1:
        console.print("[red]Interval must be at least 1 second.[/]")
        raise typer.Exit(1)

    # Build notification config
    notification_config: dict = {}
    if slack_webhook:
        notification_config["slack_webhook"] = slack_webhook
    if pagerduty_key:
        notification_config["pagerduty_key"] = pagerduty_key
    if teams_webhook:
        notification_config["teams_webhook"] = teams_webhook

    console.print(f"[cyan]Starting ChaosProof daemon...[/]")
    console.print(f"  Model: {model}")
    console.print(f"  Interval: {interval} ({interval_seconds}s)")
    console.print(f"  Notifications: {list(notification_config.keys()) or ['none']}")
    console.print(f"  Press Ctrl+C to stop.\n")

    from infrasim.daemon import ChaosProofDaemon

    daemon = ChaosProofDaemon(
        model_path=model,
        interval_seconds=interval_seconds,
        notification_config=notification_config,
    )
    daemon.start()

    console.print("[green]Daemon stopped.[/]")
