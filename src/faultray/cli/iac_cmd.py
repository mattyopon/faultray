# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI command: faultray iac-export

Export the current FaultRay infrastructure model as-is to IaC files.
Unlike `faultray export` (remediation-focused), this command generates code
that mirrors the infrastructure exactly as it was discovered, with optional
SPOF annotations.
"""

from __future__ import annotations

from pathlib import Path

import typer

from faultray.cli.main import (
    DEFAULT_MODEL_PATH,
    _load_graph_for_analysis,
    app,
    console,
)


@app.command(name="iac-export")
def iac_export(
    model: Path = typer.Argument(
        None,
        help="Model file path (JSON or YAML). Defaults to faultray-model.json.",
    ),
    provider: str = typer.Option(
        "aws",
        "--provider",
        help="Cloud provider: aws (only 'aws' is currently supported).",
    ),
    fmt: str = typer.Option(
        "terraform",
        "--format",
        "-f",
        help="Output format: terraform, cloudformation, k8s",
    ),
    output: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file or directory. Defaults to format-specific name.",
    ),
    region: str = typer.Option(
        "us-east-1",
        "--region",
        "-r",
        help="AWS region to embed in the provider block.",
    ),
    include_comments: bool = typer.Option(
        True,
        "--include-comments/--no-include-comments",
        help="Embed FaultRay discovery metadata as comments in generated code.",
    ),
    mark_spof: bool = typer.Option(
        True,
        "--mark-spof/--no-mark-spof",
        help="Add WARNING comments to resources identified as SPOFs.",
    ),
    yaml_file: Path = typer.Option(
        None,
        "--yaml",
        "-y",
        help="Load from a YAML infrastructure definition file.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Print export summary as JSON instead of writing files.",
    ),
) -> None:
    """Export infrastructure as-is to IaC (Terraform / CloudFormation / Kubernetes).

    Converts the loaded FaultRay model into Infrastructure-as-Code files that
    represent the infrastructure exactly as discovered today.  Unlike
    `faultray export` which generates a remediation plan, this command
    produces a baseline snapshot — useful for bootstrapping IaC from an
    existing (possibly undocumented) environment.

    When --mark-spof is enabled (the default), any resource that FaultRay
    identifies as a Single Point of Failure receives an inline comment block
    with the issue description and a recommended fix.

    Examples:

      # Terraform (default)
      faultray iac-export faultray-model.json --output terraform/

      # CloudFormation
      faultray iac-export faultray-model.json \\
        --format cloudformation --output cfn/template.yaml

      # Kubernetes
      faultray iac-export faultray-model.json --format k8s --output k8s/

      # Suppress SPOF annotations
      faultray iac-export faultray-model.json --no-mark-spof

      # Read from YAML model
      faultray iac-export --yaml infra.yaml --format terraform --output tf/
    """
    from faultray import __version__
    from faultray.iac.exporter import ExportFormat, IacExporter

    # --- Format validation ---------------------------------------------------
    FORMAT_MAP: dict[str, ExportFormat] = {
        "terraform": ExportFormat.TERRAFORM,
        "tf": ExportFormat.TERRAFORM,
        "cloudformation": ExportFormat.CLOUDFORMATION,
        "cfn": ExportFormat.CLOUDFORMATION,
        "kubernetes": ExportFormat.KUBERNETES,
        "k8s": ExportFormat.KUBERNETES,
    }
    iac_format = FORMAT_MAP.get(fmt.lower())
    if iac_format is None:
        console.print(f"[red]Unknown format: {fmt}[/]")
        console.print(f"[dim]Available formats: {', '.join(sorted(FORMAT_MAP.keys()))}[/]")
        raise typer.Exit(1)

    if provider.lower() != "aws":
        console.print(f"[red]Only '--provider aws' is currently supported (got: {provider})[/]")
        raise typer.Exit(1)

    # --- Load graph ----------------------------------------------------------
    if yaml_file is not None:
        graph = _load_graph_for_analysis(DEFAULT_MODEL_PATH, yaml_file=yaml_file)
    elif model is not None:
        if model.suffix in (".yaml", ".yml"):
            graph = _load_graph_for_analysis(DEFAULT_MODEL_PATH, yaml_file=model)
        else:
            graph = _load_graph_for_analysis(model, yaml_file=None)
    else:
        graph = _load_graph_for_analysis(DEFAULT_MODEL_PATH, yaml_file=None)

    if not graph.components:
        console.print("[red]No components found in the model.[/]")
        raise typer.Exit(1)

    # --- Export --------------------------------------------------------------
    exporter = IacExporter(graph)
    result = exporter.export(
        fmt=iac_format,
        provider_region=region,
        include_comments=include_comments,
        mark_spof=mark_spof,
        version=__version__,
    )

    # --- JSON summary --------------------------------------------------------
    if json_output:
        import json as _json
        data = {
            "format": result.format.value,
            "files": list(result.files.keys()),
            "spof_components": result.spof_components,
            "warnings": result.warnings,
        }
        console.print_json(_json.dumps(data, indent=2))
        return

    # --- Default output paths ------------------------------------------------
    default_outputs: dict[ExportFormat, Path] = {
        ExportFormat.TERRAFORM: Path("terraform-iac"),
        ExportFormat.CLOUDFORMATION: Path("cfn-iac"),
        ExportFormat.KUBERNETES: Path("k8s-iac"),
    }
    out_path = output if output is not None else default_outputs[iac_format]

    # --- Write files ---------------------------------------------------------
    if len(result.files) == 1 and out_path.suffix:
        # Single-file output path given explicitly (e.g. --output template.yaml)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        filename = next(iter(result.files.keys()))
        out_path.write_text(result.files[filename], encoding="utf-8")
        console.print(f"[green]Wrote:[/] {out_path}")
    else:
        # Directory output
        out_path.mkdir(parents=True, exist_ok=True)
        for filename, content in result.files.items():
            file_path = out_path / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            console.print(f"[green]Wrote:[/] {file_path}")

    # --- Summary -------------------------------------------------------------
    console.print()
    console.print("[bold]IaC export complete[/]")
    console.print(f"  Format:     [cyan]{result.format.value}[/]")
    console.print(f"  Components: {len(graph.components)}")
    console.print(f"  Files:      {len(result.files)}")

    if result.spof_components:
        console.print()
        console.print(f"[yellow]⚠️  SPOF components annotated ({len(result.spof_components)}):[/]")
        for name in result.spof_components:
            console.print(f"  - [yellow]{name}[/]")
        console.print(
            "[dim]  Use `faultray fix` to generate remediation code for these issues.[/]"
        )

    if result.warnings:
        console.print()
        console.print("[dim]Warnings:[/]")
        for w in result.warnings:
            console.print(f"  [dim]- {w}[/]")
