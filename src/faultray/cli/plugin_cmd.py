# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI commands for managing FaultRay plugins."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from faultray.cli.main import app

console = Console()

plugin_app = typer.Typer(
    name="plugin",
    help="Manage FaultRay plugins (discover, load, enable/disable, scaffold).",
    no_args_is_help=True,
)
app.add_typer(plugin_app, name="plugin")


def _get_manager():
    """Create a fresh PluginManager."""
    from faultray.plugins.plugin_manager import PluginManager

    return PluginManager()


@plugin_app.command("list")
def plugin_list() -> None:
    """List all discovered plugins."""
    manager = _get_manager()
    metas = manager.list_plugins()

    if not metas:
        console.print("[yellow]No plugins found.[/]")
        console.print(
            "Place .py files in ~/.faultzero/plugins/ or install packages "
            "with the 'faultzero.plugins' entry point."
        )
        return

    table = Table(title="FaultRay Plugins", show_lines=True)
    table.add_column("Name", style="cyan")
    table.add_column("Version")
    table.add_column("Type", style="magenta")
    table.add_column("Source")
    table.add_column("Enabled", justify="center")
    table.add_column("Description")

    for meta in sorted(metas, key=lambda m: m.name):
        enabled_str = "[green]yes[/]" if meta.enabled else "[red]no[/]"
        table.add_row(
            meta.name,
            meta.version,
            meta.plugin_type.value,
            meta.source,
            enabled_str,
            meta.description[:60],
        )

    console.print(table)


@plugin_app.command("info")
def plugin_info(name: str = typer.Argument(..., help="Plugin name")) -> None:
    """Show detailed information about a specific plugin."""
    manager = _get_manager()
    metas = {m.name: m for m in manager.list_plugins()}
    meta = metas.get(name)

    if meta is None:
        console.print(f"[red]Plugin '{name}' not found.[/]")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]{meta.name}[/] v{meta.version}")
    console.print(f"  Author:      {meta.author}")
    console.print(f"  Type:        {meta.plugin_type.value}")
    console.print(f"  Source:      {meta.source}")
    console.print(f"  Enabled:     {'yes' if meta.enabled else 'no'}")
    console.print(f"  Entry point: {meta.entry_point}")
    console.print(f"  Description: {meta.description}")
    if meta.dependencies:
        console.print(f"  Dependencies: {', '.join(meta.dependencies)}")
    if meta.config_schema:
        console.print(f"  Config schema: {meta.config_schema}")
    console.print()


@plugin_app.command("enable")
def plugin_enable(name: str = typer.Argument(..., help="Plugin name")) -> None:
    """Enable a plugin."""
    manager = _get_manager()
    manager.enable(name)
    console.print(f"[green]Plugin '{name}' enabled.[/]")


@plugin_app.command("disable")
def plugin_disable(name: str = typer.Argument(..., help="Plugin name")) -> None:
    """Disable a plugin."""
    manager = _get_manager()
    manager.disable(name)
    console.print(f"[yellow]Plugin '{name}' disabled.[/]")


@plugin_app.command("create")
def plugin_create(
    name: str = typer.Argument(..., help="Plugin name (kebab-case)"),
    ptype: str = typer.Option(
        "scenario_generator",
        "--type", "-t",
        help="Plugin type: scenario_generator, analyzer, reporter, discovery, "
             "notification, compliance, transformer",
    ),
    output: str = typer.Option(
        "",
        "--output", "-o",
        help="Output directory (defaults to ~/.faultzero/plugins/)",
    ),
) -> None:
    """Scaffold a new plugin from a template."""
    from faultray.plugins.plugin_manager import PluginType

    try:
        plugin_type = PluginType(ptype)
    except ValueError:
        valid = [t.value for t in PluginType]
        console.print(f"[red]Invalid plugin type '{ptype}'. Valid: {valid}[/]")
        raise typer.Exit(1)

    output_dir = Path(output) if output else None
    manager = _get_manager()
    path = manager.create_plugin_template(name, plugin_type, output_dir)
    console.print(f"[green]Created plugin template: {path}[/]")
    console.print("Edit the file to implement your plugin logic, then run:")
    console.print("  faultray plugin list")


@plugin_app.command("reload")
def plugin_reload(name: str = typer.Argument(..., help="Plugin name")) -> None:
    """Hot-reload a file-based plugin."""
    manager = _get_manager()
    try:
        manager.load(name)
        manager.reload(name)
        console.print(f"[green]Plugin '{name}' reloaded successfully.[/]")
    except KeyError:
        console.print(f"[red]Plugin '{name}' not found.[/]")
        raise typer.Exit(1)
    except RuntimeError as e:
        console.print(f"[red]Cannot reload: {e}[/]")
        raise typer.Exit(1)
