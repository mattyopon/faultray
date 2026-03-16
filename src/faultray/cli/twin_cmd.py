"""CLI commands for the Digital Twin / Live Shadow feature."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import app, console

twin_app = typer.Typer(
    name="twin",
    help="Digital Twin — Live shadow simulation predicting failures before they happen",
    no_args_is_help=True,
)
app.add_typer(twin_app, name="twin")


def _load_graph(yaml_file: Path) -> "InfraGraph":  # noqa: F821
    """Load an InfraGraph from a YAML or JSON file."""
    if not yaml_file.exists():
        console.print(f"[red]File not found: {yaml_file}[/]")
        raise typer.Exit(1)

    try:
        if str(yaml_file).endswith((".yaml", ".yml")):
            from faultray.model.loader import load_yaml
            return load_yaml(yaml_file)
        else:
            from faultray.model.graph import InfraGraph
            return InfraGraph.load(yaml_file)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)


@twin_app.command("predict")
def twin_predict(
    model: Path = typer.Argument(..., help="Infrastructure model file (YAML or JSON)"),
    horizon: int = typer.Option(60, "--horizon", "-h", help="Prediction horizon in minutes"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Predict system state and potential failures.

    Examples:
        faultray twin predict model.yaml --horizon 60
        faultray twin predict model.yaml --json
    """
    from faultray.simulator.digital_twin import DigitalTwin

    graph = _load_graph(model)
    twin = DigitalTwin(graph, prediction_horizon_minutes=horizon)
    snapshot = twin.predict()
    report = twin.report()

    if json_output:
        data = {
            "horizon_minutes": horizon,
            "predicted_availability": snapshot.predicted_availability,
            "total_warnings": report.total_warnings,
            "critical_warnings": report.critical_warnings,
            "warnings": [
                {
                    "component_id": w.component_id,
                    "metric": w.metric,
                    "current_value": round(w.current_value, 2),
                    "predicted_value": round(w.predicted_value, 2),
                    "threshold": w.threshold,
                    "time_to_threshold_minutes": (
                        round(w.time_to_threshold_minutes, 1)
                        if w.time_to_threshold_minutes != float("inf")
                        else None
                    ),
                    "severity": w.severity,
                    "recommended_action": w.recommended_action,
                }
                for w in snapshot.warnings
            ],
            "component_states": {
                cid: {k: round(v, 2) for k, v in state.items()}
                for cid, state in snapshot.component_states.items()
            },
            "auto_scale_suggestions": report.auto_scale_suggestions,
        }
        console.print_json(data=data)
        return

    # Rich output
    console.print(Panel(
        f"[bold]Prediction Horizon:[/] {horizon} minutes\n"
        f"[bold]Predicted Availability:[/] {snapshot.predicted_availability}%\n"
        f"[bold]Warnings:[/] {report.total_warnings} total, "
        f"{report.critical_warnings} critical",
        title="[bold]Digital Twin Prediction[/]",
        border_style="cyan",
    ))

    if snapshot.warnings:
        table = Table(title="Prediction Warnings", show_header=True)
        table.add_column("Component", style="cyan", width=20)
        table.add_column("Metric", width=16)
        table.add_column("Current", justify="right", width=10)
        table.add_column("Predicted", justify="right", width=10)
        table.add_column("Threshold", justify="right", width=10)
        table.add_column("TTT (min)", justify="right", width=10)
        table.add_column("Severity", width=10)
        table.add_column("Action", width=30)

        for w in snapshot.warnings:
            sev_color = "red" if w.severity == "critical" else "yellow"
            ttt = (
                f"{w.time_to_threshold_minutes:.1f}"
                if w.time_to_threshold_minutes != float("inf")
                else "stable"
            )
            table.add_row(
                w.component_id,
                w.metric,
                f"{w.current_value:.1f}%",
                f"{w.predicted_value:.1f}%",
                f"{w.threshold:.0f}%",
                ttt,
                f"[{sev_color}]{w.severity.upper()}[/]",
                w.recommended_action,
            )
        console.print()
        console.print(table)
    else:
        console.print("\n[green]No warnings. System looks healthy within the prediction horizon.[/]")

    if report.auto_scale_suggestions:
        console.print("\n[bold]Auto-Scale Suggestions:[/]")
        for s in report.auto_scale_suggestions:
            console.print(f"  - {s['suggestion']} (metric: {s['metric']})")
