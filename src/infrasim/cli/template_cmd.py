"""CLI commands for Scenario Templates Library."""

from __future__ import annotations

import shutil
from pathlib import Path

import typer
from rich.table import Table

from infrasim.cli.main import app, console

template_app = typer.Typer(
    name="template",
    help="Manage pre-built infrastructure scenario templates.",
    no_args_is_help=True,
)
app.add_typer(template_app, name="template")


@template_app.command("list")
def template_list() -> None:
    """List all available scenario templates.

    Example:
        infrasim template list
    """
    from infrasim.templates import list_templates

    templates = list_templates()

    table = Table(title="Available Templates", show_header=True, header_style="bold")
    table.add_column("Name", style="cyan", width=18)
    table.add_column("File", width=28)
    table.add_column("Path", style="dim", width=60)

    for t in templates:
        table.add_row(t["name"], t["file"], t["path"])

    console.print()
    console.print(table)
    console.print(f"\n[dim]Use: infrasim template use <name> --output my-infra.yaml[/]")
    console.print()


@template_app.command("use")
def template_use(
    name: str = typer.Argument(
        ...,
        help="Template name (e.g. 'web-app', 'microservices', 'ecommerce').",
    ),
    output: Path = typer.Option(
        None, "--output", "-o",
        help="Output path for the generated YAML file.",
    ),
) -> None:
    """Copy a scenario template to a local file for customisation.

    Example:
        infrasim template use ecommerce --output my-infra.yaml
        infrasim template use fintech -o fintech-setup.yaml
    """
    from infrasim.templates import TEMPLATES, get_template_path

    if name not in TEMPLATES:
        console.print(f"[red]Unknown template: '{name}'[/]")
        console.print(f"[dim]Available: {', '.join(TEMPLATES.keys())}[/]")
        raise typer.Exit(1)

    src = get_template_path(name)
    if not src.exists():
        console.print(f"[red]Template file missing: {src}[/]")
        raise typer.Exit(1)

    if output is None:
        output = Path(f"{name.replace('-', '_')}.yaml")

    shutil.copy2(src, output)
    console.print(f"[green]Template '{name}' written to {output}[/]")
    console.print(f"[dim]Load with: infrasim load {output}[/]")
