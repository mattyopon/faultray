# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI command for multi-format IaC export."""

from __future__ import annotations

from pathlib import Path

import typer

from faultray.cli.main import (
    DEFAULT_MODEL_PATH,
    _load_graph_for_analysis,
    app,
    console,
)


@app.command(name="export")
def export_iac(
    fmt: str = typer.Argument(
        ...,
        help="Output format: terraform, cloudformation, kubernetes, docker-compose, ansible, pulumi",
    ),
    model: Path = typer.Argument(
        None,
        help="Model file path (JSON or YAML). Defaults to faultray-model.json.",
    ),
    output: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file or directory. Defaults to format-specific name.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output file list as JSON"),
) -> None:
    """Export infrastructure as IaC (Terraform, CloudFormation, K8s, etc.).

    Converts the loaded infrastructure model into production-quality
    Infrastructure-as-Code files.

    Examples:
        # Export as Terraform
        faultray export terraform model.yaml --output ./terraform/

        # Export as CloudFormation
        faultray export cloudformation model.yaml --output template.yaml

        # Export as Kubernetes manifests
        faultray export kubernetes model.yaml --output ./k8s/

        # Export as Docker Compose
        faultray export docker-compose model.yaml --output docker-compose.yml

        # Export as Ansible playbook
        faultray export ansible model.yaml --output ./playbooks/

        # Export as Pulumi (Python)
        faultray export pulumi model.yaml --output ./pulumi/
    """

    from faultray.remediation.iac_exporter import IaCExporter, IaCFormat

    # Map user-facing format names to enum
    FORMAT_MAP = {
        "terraform": IaCFormat.TERRAFORM,
        "tf": IaCFormat.TERRAFORM,
        "cloudformation": IaCFormat.CLOUDFORMATION,
        "cfn": IaCFormat.CLOUDFORMATION,
        "kubernetes": IaCFormat.KUBERNETES,
        "k8s": IaCFormat.KUBERNETES,
        "docker-compose": IaCFormat.DOCKER_COMPOSE,
        "docker_compose": IaCFormat.DOCKER_COMPOSE,
        "compose": IaCFormat.DOCKER_COMPOSE,
        "ansible": IaCFormat.ANSIBLE,
        "pulumi": IaCFormat.PULUMI_PYTHON,
        "pulumi_python": IaCFormat.PULUMI_PYTHON,
        "pulumi-python": IaCFormat.PULUMI_PYTHON,
    }

    iac_format = FORMAT_MAP.get(fmt.lower())
    if iac_format is None:
        console.print(f"[red]Unknown format: {fmt}[/]")
        console.print(
            f"[dim]Available formats: {', '.join(sorted(FORMAT_MAP.keys()))}[/]"
        )
        raise typer.Exit(1)

    # Resolve model path
    resolved_model = model if model is not None else DEFAULT_MODEL_PATH
    graph = _load_graph_for_analysis(resolved_model, yaml_file=None)

    if not graph.components:
        console.print("[red]No components found in the model.[/]")
        raise typer.Exit(1)

    exporter = IaCExporter()
    result = exporter.export(graph, iac_format)

    if json_output:
        data = {
            "format": result.format.value,
            "files": list(result.files.keys()),
            "warnings": result.warnings,
            "unsupported": result.unsupported_components,
        }
        console.print_json(data=data)
        return

    # Determine output path
    default_outputs = {
        IaCFormat.TERRAFORM: Path("terraform-output"),
        IaCFormat.CLOUDFORMATION: Path("cloudformation-output"),
        IaCFormat.KUBERNETES: Path("k8s-output"),
        IaCFormat.DOCKER_COMPOSE: Path("."),
        IaCFormat.ANSIBLE: Path("ansible-output"),
        IaCFormat.PULUMI_PYTHON: Path("pulumi-output"),
    }
    out_path = output if output is not None else default_outputs.get(iac_format, Path("."))

    # Write files
    if len(result.files) == 1 and out_path.suffix:
        # Single file output (e.g., docker-compose.yml, template.yaml)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        filename = next(iter(result.files.keys()))
        content = result.files[filename]
        out_path.write_text(content, encoding="utf-8")
        console.print(f"[green]Wrote:[/] {out_path}")
    else:
        # Multi-file output (directory)
        out_path.mkdir(parents=True, exist_ok=True)
        for filename, content in result.files.items():
            file_path = out_path / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            console.print(f"[green]Wrote:[/] {file_path}")

        # Write README
        if result.readme:
            readme_path = out_path / "README.md"
            readme_path.write_text(result.readme, encoding="utf-8")
            console.print(f"[green]Wrote:[/] {readme_path}")

    # Print summary
    console.print()
    console.print("[bold]Export complete[/]")
    console.print(f"  Format: [cyan]{result.format.value}[/]")
    console.print(f"  Files: {len(result.files)}")
    console.print(f"  Components: {len(graph.components)}")

    if result.warnings:
        console.print("\n[yellow]Warnings:[/]")
        for w in result.warnings:
            console.print(f"  - {w}")

    if result.unsupported_components:
        console.print("\n[red]Unsupported components:[/]")
        for u in result.unsupported_components:
            console.print(f"  - {u}")
