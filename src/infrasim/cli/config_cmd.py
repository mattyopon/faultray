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
    help="Manage ChaosProof configuration.",
    no_args_is_help=True,
)
app.add_typer(config_app, name="config")


@config_app.command("show")
def config_show(
    path: Path = typer.Option(
        None, "--path", "-p", help="Config file path (default: ~/.chaosproof/config.yaml)"
    ),
) -> None:
    """Show current ChaosProof configuration.

    Examples:
        # Show all configuration
        chaosproof config show

        # Show config from a custom path
        chaosproof config show --path /etc/chaosproof/config.yaml
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

    console.print(f"[bold]ChaosProof Configuration[/] ({config_path})\n")
    console.print(yaml_lib.dump(data, default_flow_style=False, sort_keys=False))


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Config key in dot notation (e.g. simulation.max_scenarios)"),
    value: str = typer.Argument(..., help="Value to set"),
    path: Path = typer.Option(
        None, "--path", "-p", help="Config file path (default: ~/.chaosproof/config.yaml)"
    ),
) -> None:
    """Set a ChaosProof configuration value.

    Examples:
        # Set max scenarios
        chaosproof config set simulation.max_scenarios 200

        # Set daemon interval
        chaosproof config set daemon.interval_seconds 1800

        # Set with custom config path
        chaosproof config set ui.theme dark --path /etc/chaosproof/config.yaml
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
