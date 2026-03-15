"""Config CLI commands: config show, config set."""

from __future__ import annotations

from pathlib import Path

import typer

from infrasim.cli.main import app, console
from infrasim.config import (
    DEFAULT_CONFIG_PATH,
    load_config,
    save_config,
    set_nested_value,
)


config_app = typer.Typer(
    name="config",
    help="Manage FaultZero configuration.",
    no_args_is_help=True,
)
app.add_typer(config_app, name="config")


@config_app.command("show")
def config_show(
    path: Path = typer.Option(
        None, "--path", "-p", help="Config file path (default: ~/.faultzero/config.yaml)"
    ),
) -> None:
    """Show current FaultZero configuration.

    Examples:
        # Show all configuration
        faultzero config show

        # Show config from a custom path
        faultzero config show --path /etc/faultzero/config.yaml
    """
    import yaml as yaml_lib

    config_path = path or DEFAULT_CONFIG_PATH
    config = load_config(config_path)

    # Save on first access to create the file
    if not config_path.exists():
        save_config(config, config_path)
        console.print(f"[dim]Created default config at {config_path}[/]\n")

    data = {
        "simulation": config.simulation,
        "cost_model": config.cost_model,
        "daemon": config.daemon,
        "notifications": config.notifications,
        "ui": config.ui,
    }

    console.print(f"[bold]FaultZero Configuration[/] ({config_path})\n")
    console.print(yaml_lib.dump(data, default_flow_style=False, sort_keys=False))


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Config key in dot notation (e.g. simulation.max_scenarios)"),
    value: str = typer.Argument(..., help="Value to set"),
    path: Path = typer.Option(
        None, "--path", "-p", help="Config file path (default: ~/.faultzero/config.yaml)"
    ),
) -> None:
    """Set a FaultZero configuration value.

    Examples:
        # Set max scenarios
        faultzero config set simulation.max_scenarios 200

        # Set daemon interval
        faultzero config set daemon.interval_seconds 1800

        # Set with custom config path
        faultzero config set ui.theme dark --path /etc/faultzero/config.yaml
    """
    config_path = path or DEFAULT_CONFIG_PATH
    config = load_config(config_path)

    try:
        set_nested_value(config, key, value)
    except ValueError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)

    save_config(config, config_path)
    console.print(f"[green]Set {key} = {value}[/]")
