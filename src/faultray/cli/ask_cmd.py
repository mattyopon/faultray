"""CLI command for Natural Language Query.

Usage:
    faultray ask "What happens if the database goes down?"
    faultray ask "How resilient is the system?" --model my-model.yaml
    faultray ask "What are the risks?" --json
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel

from faultray.cli.main import (
    DEFAULT_MODEL_PATH,
    _load_graph_for_analysis,
    app,
    console,
)


@app.command()
def ask(
    question: str = typer.Argument(..., help="Natural language question about infrastructure"),
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path"),
    yaml_file: Path | None = typer.Option(None, "--yaml", "-y", help="YAML model file path"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Ask natural language questions about your infrastructure.

    Uses rule-based NLP to parse questions and run appropriate simulations.
    No LLM or external API required.

    \b
    Examples:
        faultray ask "What happens if the database goes down?"
        faultray ask "How resilient is the system?"
        faultray ask "What are the biggest risks?"
        faultray ask "Can we survive a cache outage?"
        faultray ask "What is the availability?"
        faultray ask "What happens if traffic spikes 10x?"
        faultray ask "Show me the single points of failure"
    """
    graph = _load_graph_for_analysis(model, yaml_file)

    from faultray.nl_query import NaturalLanguageEngine

    engine = NaturalLanguageEngine(graph)
    result = engine.query(question)

    if json_output:
        output = {
            "query": result.query,
            "interpreted_as": result.interpreted_as,
            "query_type": result.query_type,
            "components_matched": result.components_matched,
            "answer": result.answer,
        }
        if result.result:
            output["risk_score"] = result.result.risk_score
        console.print_json(data=output)
        return

    # Display interpreted query
    console.print()
    console.print(Panel(
        f"[bold]Question:[/] {result.query}\n"
        f"[bold]Interpreted as:[/] {result.interpreted_as}",
        title="[bold cyan]FaultRay Natural Language Query[/]",
        border_style="cyan",
    ))

    # Display answer
    console.print()
    console.print(result.answer)

    # Show risk score if available
    if result.result:
        score = result.result.risk_score
        if score >= 7:
            color = "red"
        elif score >= 4:
            color = "yellow"
        else:
            color = "green"
        console.print(f"\n[{color}]Risk Score: {score:.1f}/10[/]")

    console.print()
