# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""CLI commands for Resilience Contracts."""

from __future__ import annotations

import json as json_mod
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import _load_graph_for_analysis, app, console


@app.command("contract-validate")
def contract_validate(
    infra_file: Path = typer.Argument(..., help="Infrastructure YAML or JSON file"),
    contract: Path = typer.Option(..., "--contract", "-c", help="Resilience contract YAML file"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON for CI/CD"),
) -> None:
    """Validate infrastructure against a resilience contract.

    Checks all rules defined in the contract YAML and reports violations.

    Exit code 0 = all rules passed, 1 = violations found.

    Examples:
        # Validate against a contract
        faultray contract-validate infra.yaml --contract contract.yaml

        # JSON output for CI/CD pipelines
        faultray contract-validate infra.yaml --contract contract.yaml --json
    """
    from faultray.contracts.engine import ContractEngine

    graph = _load_graph_for_analysis(
        model=Path("faultray-model.json"),
        yaml_file=infra_file,
    )

    engine = ContractEngine()

    if not contract.exists():
        console.print(f"[red]Contract file not found: {contract}[/]")
        raise typer.Exit(1)

    contract_obj = engine.load_contract(contract)
    result = engine.validate(graph, contract_obj)

    if json_output:
        console.print_json(json_mod.dumps(result.to_dict(), indent=2))
        if not result.passed:
            raise typer.Exit(1)
        return

    _print_contract_result(result, console)

    if not result.passed:
        raise typer.Exit(1)


@app.command("contract-generate")
def contract_generate(
    infra_file: Path = typer.Argument(..., help="Infrastructure YAML or JSON file"),
    strictness: str = typer.Option(
        "standard", "--strictness", "-s",
        help="Contract strictness: relaxed, standard, strict",
    ),
    output: Path = typer.Option(
        None, "--output", "-o",
        help="Output file path (prints to stdout if omitted)",
    ),
) -> None:
    """Auto-generate a resilience contract from current infrastructure.

    Analyzes the infrastructure and creates a baseline contract with
    appropriate rules and thresholds.

    Examples:
        # Generate a standard contract
        faultray contract-generate infra.yaml

        # Generate strict contract and save to file
        faultray contract-generate infra.yaml --strictness strict --output contract.yaml

        # Relaxed contract for development environments
        faultray contract-generate infra.yaml --strictness relaxed
    """
    from faultray.contracts.engine import ContractEngine

    if strictness not in ("relaxed", "standard", "strict"):
        console.print(f"[red]Invalid strictness '{strictness}'. Use: relaxed, standard, strict[/]")
        raise typer.Exit(1)

    graph = _load_graph_for_analysis(
        model=Path("faultray-model.json"),
        yaml_file=infra_file,
    )

    engine = ContractEngine()
    contract = engine.generate_default_contract(graph, strictness=strictness)

    if output:
        engine.save_contract(contract, output)
        console.print(f"[green]Contract saved to {output}[/]")
        console.print(f"  Name: {contract.name}")
        console.print(f"  Rules: {len(contract.rules)}")
        console.print(f"  Strictness: {strictness}")
    else:
        # Print as YAML to stdout
        import yaml
        data = {
            "name": contract.name,
            "version": contract.version,
            "description": contract.description,
            "metadata": contract.metadata,
            "rules": [
                {
                    "type": r.rule_type,
                    "target": r.target,
                    "operator": r.operator,
                    "value": r.value,
                    "severity": r.severity,
                    "description": r.description,
                }
                for r in contract.rules
            ],
        }
        console.print(yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True))


@app.command("contract-diff")
def contract_diff(
    old_contract: Path = typer.Argument(..., help="Path to the old contract YAML"),
    new_contract: Path = typer.Argument(..., help="Path to the new contract YAML"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Compare two resilience contracts and show differences.

    Useful for reviewing contract changes in pull requests.

    Examples:
        # Compare two contracts
        faultray contract-diff old-contract.yaml new-contract.yaml

        # JSON output
        faultray contract-diff old.yaml new.yaml --json
    """
    from faultray.contracts.engine import ContractEngine

    if not old_contract.exists():
        console.print(f"[red]File not found: {old_contract}[/]")
        raise typer.Exit(1)
    if not new_contract.exists():
        console.print(f"[red]File not found: {new_contract}[/]")
        raise typer.Exit(1)

    engine = ContractEngine()
    old = engine.load_contract(old_contract)
    new = engine.load_contract(new_contract)
    changes = engine.diff_contracts(old, new)

    if json_output:
        console.print_json(json_mod.dumps({"changes": changes}))
        return

    console.print()
    console.print(Panel(
        f"[bold]Old:[/] {old.name} v{old.version}\n"
        f"[bold]New:[/] {new.name} v{new.version}",
        title="[bold]Contract Diff[/]",
        border_style="cyan",
    ))

    for change in changes:
        if change.startswith("+"):
            console.print(f"  [green]{change}[/]")
        elif change.startswith("-"):
            console.print(f"  [red]{change}[/]")
        elif change.startswith("~"):
            console.print(f"  [yellow]{change}[/]")
        else:
            console.print(f"  {change}")


# ---------------------------------------------------------------------------
# Rich output helper
# ---------------------------------------------------------------------------

def _print_contract_result(result, con: Console) -> None:
    """Print contract validation result with Rich formatting."""
    contract = result.contract

    if result.passed:
        status = "[bold green]PASSED[/]"
        border = "green"
    else:
        status = "[bold red]FAILED[/]"
        border = "red"

    summary = (
        f"[bold]Contract:[/] {contract.name} v{contract.version}\n"
        f"[bold]Status:[/] {status}\n"
        f"[bold]Compliance:[/] {result.score:.1f}%\n"
        f"[bold]Errors:[/] {len(result.violations)}  "
        f"[bold]Warnings:[/] {len(result.warnings)}"
    )

    con.print()
    con.print(Panel(summary, title="[bold]Contract Validation Result[/]", border_style=border))

    # Violations table
    if result.violations:
        table = Table(title="Violations (errors)", show_header=True)
        table.add_column("Rule", style="red", width=20)
        table.add_column("Expected", justify="right", width=12)
        table.add_column("Actual", justify="right", width=12)
        table.add_column("Component", width=16)
        table.add_column("Message", width=50)

        for v in result.violations:
            table.add_row(
                v.rule.rule_type,
                str(v.rule.value),
                str(v.actual_value),
                v.component_id or "-",
                v.message[:50] + ("..." if len(v.message) > 50 else ""),
            )

        con.print()
        con.print(table)

    # Warnings table
    if result.warnings:
        table = Table(title="Warnings", show_header=True)
        table.add_column("Rule", style="yellow", width=20)
        table.add_column("Expected", justify="right", width=12)
        table.add_column("Actual", justify="right", width=12)
        table.add_column("Component", width=16)
        table.add_column("Message", width=50)

        for w in result.warnings:
            table.add_row(
                w.rule.rule_type,
                str(w.rule.value),
                str(w.actual_value),
                w.component_id or "-",
                w.message[:50] + ("..." if len(w.message) > 50 else ""),
            )

        con.print()
        con.print(table)
