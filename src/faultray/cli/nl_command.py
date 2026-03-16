"""Natural Language infrastructure definition CLI command.

Provides the ``nl`` subcommand for converting plain-text infrastructure
descriptions into FaultRay YAML definitions.

Usage:
  faultray nl parse "3 web servers behind ALB, connected to Aurora"
  faultray nl parse --interactive
  faultray nl parse --output infra.yaml
  faultray nl parse --simulate
  faultray nl parse --lang ja
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

if TYPE_CHECKING:
    from faultray.ai.nl_to_infra import NLInfraParser, ParsedInfrastructure

from faultray.cli.main import app, console


@app.command()
def nl(
    description: str = typer.Argument(
        None,
        help="Natural language infrastructure description. "
        "Example: '3 web servers behind ALB, connected to Aurora with 2 read replicas'",
    ),
    interactive: bool = typer.Option(
        False, "--interactive", "-i",
        help="Interactive mode: enter multi-line description (end with empty line).",
    ),
    output: Path = typer.Option(
        None, "--output", "-o",
        help="Save generated YAML to file.",
    ),
    simulate: bool = typer.Option(
        False, "--simulate", "-s",
        help="Parse and immediately run simulation on generated infrastructure.",
    ),
    lang: str = typer.Option(
        None, "--lang", "-l",
        help="Force language parsing (en/ja). Auto-detected if not specified.",
    ),
    show_graph: bool = typer.Option(
        False, "--graph", "-g",
        help="Show parsed component and relationship summary.",
    ),
) -> None:
    """Convert natural language infrastructure descriptions to YAML.

    Describe your infrastructure in plain English or Japanese and get a
    FaultRay YAML definition automatically generated. No LLM API required.

    \b
    自然言語からインフラ定義(YAML)を自動生成します。
    英語・日本語の両方に対応。外部APIは不要です。

    \b
    Examples:
      faultray nl "3 web servers behind ALB connected to Aurora with 2 read replicas"
      faultray nl "ALBの後ろにEC2が3台、Auroraに接続、Redis キャッシュあり"
      faultray nl --interactive
      faultray nl "2 app servers with Redis cache" --output infra.yaml --simulate
    """
    from faultray.ai.nl_to_infra import NLInfraParser

    # Get text input
    text = _get_input_text(description, interactive)
    if not text:
        console.print("[red]No input provided. Use --interactive or pass a description.[/]")
        raise typer.Exit(1)

    # Parse
    parser = NLInfraParser()

    try:
        parsed = parser.parse(text)
    except ValueError as e:
        console.print(f"[red]Parse error:[/] {e}")
        raise typer.Exit(1)

    # Show header
    console.print()
    console.print(Panel(
        f"[bold]Input:[/] {text}",
        title="[bold cyan]FaultRay NL-to-Infrastructure Converter[/]",
        border_style="cyan",
    ))

    # Show parsed components summary
    if show_graph:
        _print_parsed_summary(parsed, console)

    # Generate YAML
    yaml_output = parser.to_yaml(parsed)

    # Display YAML
    console.print()
    console.print("[bold green]Generated YAML:[/]")
    syntax = Syntax(yaml_output, "yaml", theme="monokai", line_numbers=True)
    console.print(syntax)

    # Component count summary
    comp_count = len(parsed.components)
    dep_count = len(parsed.relationships)
    console.print(
        f"\n[bold]Summary:[/] {comp_count} components, {dep_count} dependencies"
    )

    # Save to file
    if output:
        output.write_text(yaml_output, encoding="utf-8")
        console.print(f"[green]Saved to:[/] {output}")

    # Simulate
    if simulate:
        _run_simulation(parser, parsed, console)


def _get_input_text(description: str | None, interactive: bool) -> str:
    """Get input text from arguments or interactive mode."""
    if interactive:
        console.print(
            "[cyan]Enter your infrastructure description "
            "(press Enter twice to finish):[/]\n"
        )
        lines: list[str] = []
        try:
            while True:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    # Double empty line = done
                    break
                lines.append(line)
        except EOFError:
            pass

        return " ".join(line for line in lines if line)

    return description or ""


def _print_parsed_summary(parsed: "ParsedInfrastructure", con: "Console") -> None:
    """Print a table summarizing parsed components and relationships."""
    # Components table
    comp_table = Table(title="Parsed Components", show_header=True)
    comp_table.add_column("ID", style="cyan", width=20)
    comp_table.add_column("Type", width=15)
    comp_table.add_column("Replicas", justify="right", width=8)
    comp_table.add_column("Properties", width=40)

    for comp in parsed.components:
        props_str = ", ".join(
            f"{k}={v}" for k, v in comp.properties.items()
            if k not in ("port", "max_connections", "max_rps")
        )
        comp_table.add_row(
            comp.name,
            comp.component_type.value,
            str(comp.replicas),
            props_str or "-",
        )

    con.print()
    con.print(comp_table)

    # Relationships table
    if parsed.relationships:
        rel_table = Table(title="Parsed Relationships", show_header=True)
        rel_table.add_column("Source", style="cyan", width=20)
        rel_table.add_column("->", width=3, justify="center")
        rel_table.add_column("Target", style="green", width=20)
        rel_table.add_column("Type", width=10)

        for rel in parsed.relationships:
            rel_table.add_row(
                rel.source,
                "->",
                rel.target,
                rel.relationship_type,
            )

        con.print()
        con.print(rel_table)


def _run_simulation(
    parser: "NLInfraParser",
    parsed: "ParsedInfrastructure",
    con: "Console",
) -> None:
    """Run simulation on parsed infrastructure."""
    from faultray.reporter.report import print_simulation_report
    from faultray.simulator.engine import SimulationEngine

    con.print("\n[bold yellow]Running simulation...[/]\n")

    graph = parser.to_graph(parsed)
    engine = SimulationEngine(graph)
    report = engine.run()

    print_simulation_report(report, graph)
