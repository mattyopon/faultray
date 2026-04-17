# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI command for generating printable compliance evidence HTML reports.

Usage:
    faultray compliance-report examples/demo-infra.yaml \\
        --output compliance-evidence.html

    faultray compliance-report examples/demo-infra.yaml \\
        --framework soc2 --output soc2-report.html
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from faultray.cli.main import app, console

_SUPPORTED_FRAMEWORKS = ["soc2", "iso27001", "dora", "fisc", "pci_dss", "nist_csf"]
_ALL_FRAMEWORKS = _SUPPORTED_FRAMEWORKS


@app.command(name="compliance-report")
def compliance_report_command(
    infra_file: Annotated[
        Path,
        typer.Argument(help="Infrastructure YAML or JSON model file."),
    ],
    framework: Annotated[
        str | None,
        typer.Option(
            "--framework",
            "-f",
            help=(
                "Compliance framework to include. "
                "Choices: soc2, iso27001, dora, fisc, pci_dss, nist_csf. "
                "Omit to include all frameworks."
            ),
        ),
    ] = None,
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Output path for the HTML report.",
        ),
    ] = Path("compliance-evidence.html"),
    org_name: Annotated[
        str,
        typer.Option(
            "--org",
            help="Organisation name shown in the report header.",
        ),
    ] = "Your Organization",
) -> None:
    """Generate a printable HTML compliance evidence report.

    The HTML report can be opened in any browser and printed to PDF
    via the browser's Print dialog (Ctrl+P -> Save as PDF).

    Examples:

        faultray compliance-report examples/demo-infra.yaml \\
            --output compliance-evidence.html

        faultray compliance-report examples/demo-infra.yaml \\
            --framework soc2 --output soc2-report.html

        faultray compliance-report examples/demo-infra.yaml \\
            --framework iso27001 --org "Acme Corp" --output iso27001.html
    """
    # Validate framework choice.
    if framework is not None:
        fw_lower = framework.lower()
        if fw_lower not in _SUPPORTED_FRAMEWORKS:
            console.print(
                f"[red]Unknown framework: {framework}[/]\n"
                f"[dim]Supported: {', '.join(_SUPPORTED_FRAMEWORKS)}[/]"
            )
            raise typer.Exit(1)
        frameworks_to_run = [fw_lower]
    else:
        frameworks_to_run = list(_ALL_FRAMEWORKS)

    # Load the infrastructure graph.
    if not infra_file.exists():
        console.print(f"[red]File not found: {infra_file}[/]")
        raise typer.Exit(1)

    try:
        if str(infra_file).endswith((".yaml", ".yml")):
            from faultray.model.loader import load_yaml
            graph = load_yaml(infra_file)
        else:
            from faultray.model.graph import InfraGraph
            graph = InfraGraph.load(infra_file)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to load model: {exc}[/]")
        raise typer.Exit(1)

    if not graph.components:
        console.print("[red]No components found in the model.[/]")
        raise typer.Exit(1)

    console.print(
        f"[bold]Generating compliance report[/] "
        f"[dim]({len(graph.components)} components, "
        f"frameworks: {', '.join(frameworks_to_run)})[/]"
    )

    from faultray.reporter.compliance_pdf import generate_compliance_html

    generate_compliance_html(
        graph=graph,
        frameworks=frameworks_to_run,
        output_path=output,
        org_name=org_name,
    )

    console.print(f"\n[green]Compliance report saved to:[/] [bold]{output}[/]")
    console.print(
        "[dim]Open in a browser and print to PDF (Ctrl+P -> Save as PDF) "
        "to produce a regulator-ready document.[/]"
    )
