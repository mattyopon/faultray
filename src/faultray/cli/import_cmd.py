# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""``faultray import`` — bring topology in from external sources.

Currently supports Terraform (``terraform show -json`` state/plan output or
a raw terraform.tfstate).  The output is an editable topology YAML that
plugs straight into ``faultray simulate -m <file>``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import typer

from faultray.cli.main import app, console

if TYPE_CHECKING:
    from faultray.discovery.terraform_import import TerraformImportResult

import_app = typer.Typer(
    name="import",
    help="Import topology from external sources (terraform, ...)",
    no_args_is_help=True,
)
app.add_typer(import_app, name="import")


@import_app.command("terraform")
def import_terraform_cmd(
    input_file: Path = typer.Argument(
        ...,
        help="Terraform JSON: 'terraform show -json [planfile]' output or terraform.tfstate",
    ),
    output: Path = typer.Option(
        Path("terraform-topology.yaml"),
        "--output",
        "-o",
        help="Topology YAML output path",
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite the output file if it exists"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON summary"),
) -> None:
    """Convert Terraform state/plan JSON into a FaultRay topology YAML.

    Dependency edges are derived only from evidence in the input (explicit
    references, depends_on, ARN/endpoint cross-references, ALB/Lambda/ECS
    wiring). Unknown dependency semantics default to 'requires'
    (conservative). Review the generated YAML before relying on results.

    Examples:
        # From a state snapshot
        terraform show -json > state.json
        faultray import terraform state.json

        # From a plan (includes resources not yet applied)
        terraform plan -out=plan.tfplan
        terraform show -json plan.tfplan > plan.json
        faultray import terraform plan.json -o topology.yaml

        # Then simulate
        faultray simulate -m terraform-topology.yaml
    """
    from faultray.discovery.terraform_import import (
        load_terraform_file,
        topology_yaml,
    )

    try:
        result = load_terraform_file(input_file)
    except ValueError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)

    if not result.graph.components:
        console.print(
            "[red]No mappable AWS resources found in the input.[/] "
            "[dim]Supported: ALB/ELB, EC2, ECS, EKS, Lambda, RDS, DynamoDB, "
            "ElastiCache, SQS/SNS/MQ, S3/EFS, Route53, API Gateway, CloudFront.[/]"
        )
        raise typer.Exit(1)

    if output.exists() and not force:
        console.print(
            f"[red]Output file already exists: {output}[/] "
            "[dim](use --force to overwrite)[/]"
        )
        raise typer.Exit(1)

    output.write_text(topology_yaml(result), encoding="utf-8")

    isolated = result.isolated_component_ids
    if json_output:
        type_counts: dict[str, int] = {}
        for comp in result.graph.components.values():
            type_counts[comp.type.value] = type_counts.get(comp.type.value, 0) + 1
        console.print_json(data={
            "source_format": result.source_format,
            "output": str(output),
            "components": len(result.graph.components),
            "component_types": type_counts,
            "dependencies": len(result.edges),
            "isolated_components": isolated,
            "skipped_resource_types": result.skipped_types,
            "warnings": result.warnings,
        })
        return

    _print_import_summary(result, output)


def _print_import_summary(result: TerraformImportResult, output: Path) -> None:
    from rich.table import Table

    console.print(
        f"\n[green]Imported {len(result.graph.components)} components and "
        f"{len(result.edges)} dependencies[/] "
        f"[dim](source: terraform {result.source_format} JSON)[/]"
    )

    table = Table(title="Components", show_header=True)
    table.add_column("ID", style="cyan", width=44)
    table.add_column("Type", width=14)
    table.add_column("Replicas", justify="right", width=8)
    for comp_id in sorted(result.graph.components):
        comp = result.graph.components[comp_id]
        table.add_row(comp_id, comp.type.value, str(comp.replicas))
    console.print(table)

    if result.edges:
        dep_table = Table(title="Dependencies (evidence-based)", show_header=True)
        dep_table.add_column("Source", style="cyan", width=34)
        dep_table.add_column("Target", style="cyan", width=34)
        dep_table.add_column("Type", width=8)
        dep_table.add_column("Evidence", width=40)
        for edge in sorted(result.edges, key=lambda e: (e.source, e.target)):
            dep_table.add_row(edge.source, edge.target, edge.dep_type, edge.evidence)
        console.print(dep_table)

    if result.skipped_types:
        skipped_str = ", ".join(
            f"{t} ({n})" for t, n in result.skipped_types.items()
        )
        console.print(f"[dim]Skipped resource types: {skipped_str}[/]")

    isolated = result.isolated_component_ids
    if isolated:
        console.print(
            f"\n[yellow]{len(isolated)} component(s) have no inferred "
            f"dependencies — review and wire them manually:[/]"
        )
        for comp_id in isolated:
            console.print(f"  [yellow]-[/] {comp_id}")

    for warning in result.warnings:
        console.print(f"[yellow]Warning: {warning}[/]")

    console.print(
        f"\n[green]Topology written to {output}[/]\n"
        f"Review/edit the YAML, then run "
        f"[cyan]faultray simulate -m {output}[/] or "
        f"[cyan]faultray evaluate -m {output}[/]."
    )
