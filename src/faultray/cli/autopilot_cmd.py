# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI command: faultray autopilot

AWS全自動パイプライン:
  要件定義（テキスト/ファイル）→ トポロジー生成 → シミュレーション検証 → Terraform生成 → デプロイ（任意）

Examples:
    # テキストから全自動
    faultray autopilot "3層Webアプリ。React frontend, Node.js API, PostgreSQL DB。月間100万PV。可用性99.9%必要"

    # ファイルから
    faultray autopilot --requirements requirements.md

    # ステップバイステップ（確認付き）
    faultray autopilot --requirements requirements.md --interactive

    # Terraform出力のみ（デプロイなし）
    faultray autopilot --requirements requirements.md --terraform-only --output ./terraform/

    # 既存トポロジーからTerraform生成のみ
    faultray autopilot --from-yaml infra.yaml --terraform-only --output ./terraform/
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import app, console


@app.command(name="autopilot")
def autopilot(
    requirements_text: Optional[str] = typer.Argument(
        None,
        help="Requirements as inline text (e.g. '3層Webアプリ, 99.9%可用性, 月間100万PV')",
    ),
    requirements: Optional[Path] = typer.Option(
        None,
        "--requirements",
        "-r",
        help="Path to requirements file (Markdown or plain text)",
        exists=False,
    ),
    from_yaml: Optional[Path] = typer.Option(
        None,
        "--from-yaml",
        help="Skip requirements parsing — use existing InfraGraph YAML directly",
        exists=False,
    ),
    terraform_only: bool = typer.Option(
        True,
        "--terraform-only/--deploy",
        help="Generate Terraform only (default) or also run terraform apply",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory for Terraform files (default: ./terraform-output/)",
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive/--no-interactive",
        "-i",
        help="Pause at each step for confirmation",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output pipeline summary as JSON",
    ),
    skip_simulation: bool = typer.Option(
        False,
        "--skip-simulation",
        help="Skip simulation step (faster, less validation)",
    ),
) -> None:
    """Full autopilot pipeline: requirements → topology → simulation → Terraform.

    Provide requirements as inline text or a file path.
    """
    from faultray.autopilot.pipeline import AutopilotPipeline

    if not any([requirements_text, requirements, from_yaml]):
        console.print(
            "[red]Error:[/red] Provide requirements text, --requirements FILE, or --from-yaml FILE."
        )
        raise typer.Exit(1)

    # Default output directory
    out_dir = output or Path("terraform-output")

    pipeline = AutopilotPipeline()

    # -----------------------------------------------------------------------
    # Step banner
    # -----------------------------------------------------------------------
    if not json_output:
        console.print(
            Panel.fit(
                "[bold cyan]FaultRay Autopilot[/bold cyan]\n"
                "Requirements → Topology → Simulation → Terraform",
                border_style="cyan",
            )
        )

    # -----------------------------------------------------------------------
    # Run pipeline
    # -----------------------------------------------------------------------
    if from_yaml:
        if not json_output:
            console.print(f"\n[yellow]Step 1-3 skipped[/yellow] (using existing YAML: {from_yaml})")
        result = pipeline.run_from_yaml(from_yaml)

    elif requirements:
        if not requirements.exists():
            console.print(f"[red]Error:[/red] Requirements file not found: {requirements}")
            raise typer.Exit(1)

        if not json_output:
            console.print(f"\n[bold]Step 1:[/bold] Parsing requirements from {requirements}")
        if interactive and not typer.confirm("Continue to topology design?", default=True):
            raise typer.Abort()

        result = pipeline.run_from_file(requirements)

    else:
        if requirements_text is None:
            raise ValueError("requirements_text must not be None when no requirements file is given")
        if not json_output:
            console.print("\n[bold]Step 1:[/bold] Parsing inline requirements")
        if interactive and not typer.confirm("Continue to topology design?", default=True):
            raise typer.Abort()

        result = pipeline.run_from_text(requirements_text)

    # -----------------------------------------------------------------------
    # Handle errors
    # -----------------------------------------------------------------------
    if result.errors:
        for err in result.errors:
            console.print(f"[red]ERROR:[/red] {err}")
        raise typer.Exit(1)

    # -----------------------------------------------------------------------
    # Display results
    # -----------------------------------------------------------------------
    if json_output:
        import json as _json

        summary: dict = {
            "success": result.success,
            "app_name": result.spec.app_name if result.spec else None,
            "app_type": result.spec.app_type if result.spec else None,
            "availability_target": result.spec.availability_target if result.spec else None,
            "components": len(result.graph.components) if result.graph else 0,
            "resilience_score": result.availability_score,
            "terraform_files": list(result.terraform.files.keys()) if result.terraform else [],
            "warnings": result.warnings,
        }
        print(_json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        _print_pipeline_summary(result)

    # -----------------------------------------------------------------------
    # Write Terraform files
    # -----------------------------------------------------------------------
    if not result.terraform:
        console.print("[red]No Terraform output generated.[/red]")
        raise typer.Exit(1)

    if interactive and not typer.confirm(
        f"\nWrite {len(result.terraform.files)} Terraform files to {out_dir}?",
        default=True,
    ):
        raise typer.Abort()

    pipeline.terraform_only(result, out_dir)

    if not json_output:
        console.print(
            f"\n[green]Terraform files written to:[/green] [bold]{out_dir}[/bold]"
        )
        console.print(
            "\n[dim]Next steps:[/dim]\n"
            f"  cd {out_dir}\n"
            "  terraform init\n"
            "  terraform plan -var='terraform_state_bucket=YOUR_BUCKET'\n"
            "  terraform apply"
        )

    # -----------------------------------------------------------------------
    # Optional: run terraform apply (only if --deploy flag passed)
    # -----------------------------------------------------------------------
    if not terraform_only:
        if not json_output:
            console.print("\n[bold yellow]WARNING:[/bold yellow] --deploy flag is set. Running terraform apply...")
        _run_terraform_apply(out_dir, interactive=interactive, json_output=json_output)


def _print_pipeline_summary(result: object) -> None:
    """Display a rich summary table of the pipeline result."""
    from faultray.autopilot.pipeline import PipelineResult

    assert isinstance(result, PipelineResult)

    # Spec summary
    if result.spec:
        spec = result.spec
        table = Table(title="Requirements Parsed", show_header=False, border_style="blue")
        table.add_column("Field", style="cyan")
        table.add_column("Value")
        table.add_row("App Name", spec.app_name)
        table.add_row("App Type", spec.app_type)
        table.add_row("Availability Target", f"{spec.availability_target}%")
        table.add_row("Traffic Scale", spec.traffic_scale)
        table.add_row("Region", spec.region)
        table.add_row("Multi-AZ", "Yes" if spec.multi_az else "No")
        table.add_row(
            "Components",
            ", ".join(f"{c.role}({c.technology})" for c in spec.components),
        )
        console.print(table)

    # Graph summary
    if result.graph:
        console.print(f"\n[bold]Step 2:[/bold] Topology designed — {len(result.graph.components)} components")
        for comp in result.graph.components.values():
            replicas = f" x{comp.replicas}" if comp.replicas > 1 else ""
            autoscale = " [auto-scale]" if comp.autoscaling.enabled else ""
            failover = " [failover]" if comp.failover.enabled else ""
            console.print(
                f"  [green]+[/green] {comp.name} ({comp.type.value}){replicas}{autoscale}{failover}"
            )

    # Simulation summary
    if result.simulation:
        sim = result.simulation
        score_color = "green" if sim.resilience_score >= 70 else "yellow" if sim.resilience_score >= 50 else "red"
        console.print(
            f"\n[bold]Step 3:[/bold] Simulation complete — "
            f"resilience score: [{score_color}]{sim.resilience_score:.1f}/100[/{score_color}]"
        )
        if sim.critical_findings:
            console.print(f"  [red]Critical findings: {len(sim.critical_findings)}[/red]")
            for finding in sim.critical_findings[:3]:
                console.print(f"    - {finding.scenario.name}: risk={finding.risk_score:.1f}")
    else:
        console.print("\n[bold]Step 3:[/bold] Simulation skipped")

    # Terraform summary
    if result.terraform:
        console.print(
            f"\n[bold]Step 4:[/bold] Terraform generated — "
            f"{len(result.terraform.files)} files"
        )
        for fname in sorted(result.terraform.files.keys()):
            size = len(result.terraform.files[fname])
            console.print(f"  [green]+[/green] {fname} ({size:,} bytes)")

    # Warnings
    if result.warnings:
        console.print("\n[yellow]Warnings:[/yellow]")
        for w in result.warnings:
            console.print(f"  [yellow]![/yellow] {w}")


def _run_terraform_apply(
    tf_dir: Path, *, interactive: bool, json_output: bool
) -> None:
    """Run terraform init + plan + apply in the given directory."""
    import subprocess

    def _run(cmd: list[str]) -> int:
        proc = subprocess.run(cmd, cwd=tf_dir)
        return proc.returncode

    if not json_output:
        console.print("[bold]Running terraform init...[/bold]")
    rc = _run(["terraform", "init"])
    if rc != 0:
        console.print(f"[red]terraform init failed (exit code {rc})[/red]")
        raise typer.Exit(rc)

    if not json_output:
        console.print("[bold]Running terraform plan...[/bold]")
    rc = _run(["terraform", "plan"])
    if rc != 0:
        console.print(f"[red]terraform plan failed (exit code {rc})[/red]")
        raise typer.Exit(rc)

    if interactive and not typer.confirm("Apply the plan?", default=False):
        raise typer.Abort()

    if not json_output:
        console.print("[bold]Running terraform apply...[/bold]")
    rc = _run(["terraform", "apply", "-auto-approve"])
    if rc != 0:
        console.print(f"[red]terraform apply failed (exit code {rc})[/red]")
        raise typer.Exit(rc)

    if not json_output:
        console.print("[green]terraform apply completed.[/green]")
