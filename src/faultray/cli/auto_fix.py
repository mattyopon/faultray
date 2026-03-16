"""CLI command for auto-remediation pipeline."""

from __future__ import annotations

from pathlib import Path

import typer

from faultray.cli.main import (
    DEFAULT_MODEL_PATH,
    _load_graph_for_analysis,
    app,
    console,
)


@app.command(name="auto-fix")
def auto_fix(
    model: Path = typer.Argument(
        None,
        help="Model file path (JSON or YAML). Defaults to faultray-model.json.",
    ),
    target_score: float = typer.Option(
        90.0, "--target-score", "-t", help="Target resilience score (0-100)"
    ),
    dry_run: bool = typer.Option(
        True, "--dry-run/--apply", help="Preview changes (--dry-run) or write files (--apply)"
    ),
    output_dir: Path = typer.Option(
        Path("remediation-output"),
        "--output",
        "-o",
        help="Output directory for generated files",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON summary"),
) -> None:
    """Auto-fix infrastructure issues by generating remediation IaC code.

    Runs the full pipeline: evaluate -> generate fixes -> validate -> apply.
    Dry-run by default (safe preview mode).

    Examples:
        # Preview remediation plan (dry-run, safe)
        faultray auto-fix model.yaml --target-score 90

        # Apply remediations (writes files to disk)
        faultray auto-fix model.yaml --target-score 90 --apply

        # JSON output for automation
        faultray auto-fix model.yaml --json

        # Custom output directory
        faultray auto-fix model.yaml --apply --output ./fixes/
    """
    from rich.panel import Panel
    from rich.table import Table

    from faultray.remediation.auto_pipeline import AutoRemediationPipeline

    # Resolve model path
    resolved_model = model if model is not None else DEFAULT_MODEL_PATH
    graph = _load_graph_for_analysis(resolved_model, yaml_file=None)

    if not json_output:
        mode = "[yellow]DRY RUN[/] (preview only)" if dry_run else "[red]APPLY[/] (writing files)"
        console.print(
            f"\n[cyan]Auto-Fix Pipeline[/]\n"
            f"  Model: [bold]{resolved_model}[/]\n"
            f"  Target Score: {target_score:.0f}/100\n"
            f"  Mode: {mode}\n"
        )

    pipeline = AutoRemediationPipeline(graph, output_dir=output_dir)
    result = pipeline.run(target_score=target_score, dry_run=dry_run)

    if json_output:
        console.print_json(data=result.to_dict())
        return

    # Step results table
    table = Table(title="Pipeline Steps", show_header=True)
    table.add_column("Step", width=30)
    table.add_column("Status", width=10, justify="center")
    table.add_column("Duration", width=10, justify="right")
    table.add_column("Details", width=50)

    status_styles = {
        "passed": "[green]PASSED[/]",
        "failed": "[red]FAILED[/]",
        "skipped": "[dim]SKIPPED[/]",
        "running": "[yellow]RUNNING[/]",
        "pending": "[dim]PENDING[/]",
    }

    for step in result.steps:
        status_text = status_styles.get(step.status, step.status)
        duration = f"{step.duration_seconds:.2f}s" if step.duration_seconds > 0 else "-"
        output_text = step.output[:80] + ("..." if len(step.output) > 80 else "")
        table.add_row(step.name, status_text, duration, output_text)

    console.print(table)

    # Score summary
    score_delta = result.score_after - result.score_before
    if score_delta > 0:
        delta_color = "green"
        delta_text = f"+{score_delta:.1f}"
    elif score_delta < 0:
        delta_color = "red"
        delta_text = f"{score_delta:.1f}"
    else:
        delta_color = "dim"
        delta_text = "0"

    summary = (
        f"[bold]Score:[/] {result.score_before:.1f} -> {result.score_after:.1f} "
        f"([{delta_color}]{delta_text}[/])\n"
        f"[bold]Files Generated:[/] {result.files_generated}\n"
        f"[bold]Mode:[/] {'Dry Run (no files written)' if result.dry_run else 'Applied'}\n"
        f"[bold]Result:[/] {'[green]SUCCESS[/]' if result.success else '[red]FAILED[/]'}"
    )

    border_color = "green" if result.success else "red"
    console.print()
    console.print(Panel(
        summary,
        title="[bold]Auto-Fix Pipeline Result[/]",
        border_style=border_color,
    ))

    # Show diff preview if available
    diff_text = pipeline.get_diff_preview()
    if diff_text and not json_output:
        console.print()
        console.print("[bold]Diff Preview:[/]")
        for line in diff_text.split("\n"):
            if line.startswith("+"):
                console.print(f"  [green]{line}[/]")
            elif line.startswith("#"):
                console.print(f"  [cyan]{line}[/]")
            elif line.startswith("---"):
                console.print(f"  [bold]{line}[/]")
            else:
                console.print(f"  {line}")

    if dry_run and result.files_generated > 0:
        console.print(
            f"\n[dim]To apply these changes, run:[/]\n"
            f"  faultray auto-fix {resolved_model} --target-score {target_score:.0f} --apply\n"
        )
