# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI commands for code-level risk analysis.

Usage::

    # Analyze a PR diff
    faultray code-risk diff --base main --head feature-branch

    # Analyze a single file
    faultray code-risk file src/app/api/route.ts

    # Analyze current uncommitted changes
    faultray code-risk diff --base HEAD
"""

from __future__ import annotations

import json

import typer

from . import app

code_risk_app = typer.Typer(
    help="Code-level risk analysis — runtime cost prediction + AI hallucination detection",
)
app.add_typer(code_risk_app, name="code-risk")


@code_risk_app.command("diff")
def analyze_diff(
    base: str = typer.Option("main", "--base", "-b", help="Base ref (branch or commit)"),
    head: str = typer.Option("HEAD", "--head", "-h", help="Head ref (branch or commit)"),
    repo: str = typer.Option(".", "--repo", "-r", help="Repository path"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    threshold: float = typer.Option(0.1, "--threshold", "-t", help="Risk threshold for exit code 1"),
) -> None:
    """Analyze git diff between two refs for runtime risk and AI hallucination probability."""
    from ..simulator.code_risk_engine import CodeRiskEngine

    engine = CodeRiskEngine(repo_path=repo)
    report = engine.analyze_diff(base_ref=base, head_ref=head)

    if output_json:
        typer.echo(json.dumps(report.to_dict(), indent=2))
    else:
        _print_report(report)

    # Exit with error if risk exceeds threshold (useful as CI gate)
    if report.overall_risk_score > threshold:
        raise typer.Exit(code=1)


@code_risk_app.command("file")
def analyze_file(
    file_path: str = typer.Argument(help="Path to the file to analyze"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Analyze a single file for runtime cost and risk profile."""
    from ..simulator.code_risk_engine import CodeRiskEngine

    engine = CodeRiskEngine(repo_path=".")
    component = engine.analyze_file(file_path)

    if output_json:
        typer.echo(component.model_dump_json(indent=2))
    else:
        typer.echo(f"\n{'=' * 60}")
        typer.echo(f"  Code Risk Analysis: {component.name}")
        typer.echo(f"{'=' * 60}\n")
        typer.echo(f"  Language:           {component.language.value}")
        typer.echo(f"  Complexity:         {component.runtime_cost.complexity.value}")
        typer.echo(f"  CPU (per call):     {component.runtime_cost.estimated_cpu_ms_per_call:.2f} ms")
        typer.echo(f"  Memory (per call):  {component.runtime_cost.estimated_memory_mb_per_call:.2f} MB")
        typer.echo(f"  I/O calls:          {component.runtime_cost.estimated_io_calls_per_invocation}")
        typer.echo(f"  Network calls:      {component.runtime_cost.network_calls_per_invocation}")
        typer.echo(f"  Blocking:           {'Yes' if component.runtime_cost.is_blocking else 'No'}")
        typer.echo(f"  Holds lock:         {'Yes' if component.runtime_cost.holds_lock else 'No'}")
        typer.echo()


def _print_report(report) -> None:  # noqa: ANN001
    """Pretty-print the risk report."""

    typer.echo()
    typer.echo("╔══════════════════════════════════════════════════════╗")
    typer.echo("║  FaultRay Code Risk Analysis                        ║")
    typer.echo("╠══════════════════════════════════════════════════════╣")

    # Overall score with color
    score = report.overall_risk_score
    if score > 0.3:
        level = "🔴 HIGH"
    elif score > 0.1:
        level = "🟡 MEDIUM"
    else:
        level = "🟢 LOW"

    typer.echo(f"║  Overall Risk:  {level} ({score:.1%}){' ' * (27 - len(level))}║")
    typer.echo(f"║  AI Risk:       {report.max_hallucination_risk:.1%}{' ' * 33}║")
    typer.echo(f"║  Files:         {len(report.diff_impacts)}{' ' * (35 - len(str(len(report.diff_impacts))))}║")
    typer.echo(f"║  Regressions:   {len(report.regressions)}{' ' * (35 - len(str(len(report.regressions))))}║")
    typer.echo("╚══════════════════════════════════════════════════════╝")

    if report.diff_impacts:
        typer.echo("\n  Performance Impact:")
        typer.echo(f"    CPU:    {report.total_cpu_delta_ms:+.2f} ms/call")
        typer.echo(f"    Memory: {report.total_memory_delta_mb:+.2f} MB/call")
        typer.echo(f"    I/O:    {report.total_io_delta:+d} calls/invocation")

    if report.ai_authored_files:
        typer.echo(f"\n  AI-Authored Files ({len(report.ai_authored_files)}):")
        for f in report.ai_authored_files[:10]:
            typer.echo(f"    ⚠ {f}")

    if report.regressions:
        typer.echo(f"\n  Performance Regressions ({len(report.regressions)}):")
        for r in report.regressions[:10]:
            typer.echo(f"    ↑ {r.file_path}: +{r.cpu_delta_ms:.1f}ms CPU, +{r.memory_delta_mb:.2f}MB mem")

    if report.recommendations:
        typer.echo("\n  Recommendations:")
        for i, rec in enumerate(report.recommendations, 1):
            typer.echo(f"    {i}. {rec}")

    typer.echo()
