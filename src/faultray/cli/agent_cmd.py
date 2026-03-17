"""CLI commands for AI Agent resilience features (ADOPT, MANAGE, scenarios)."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import app, console

agent_app = typer.Typer(
    name="agent",
    help="AI Agent resilience — risk assessment, monitoring, and scenario generation",
    no_args_is_help=True,
)
app.add_typer(agent_app, name="agent")


@agent_app.command("assess")
def agent_assess(
    topology: Path = typer.Argument(..., help="Topology YAML file"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Run ADOPT risk assessment for AI agents in the topology.

    Evaluates blast radius, failsafes, hallucination impact, and generates
    actionable recommendations for each agent component.

    Examples:
        faultray agent assess infra.yaml
        faultray agent assess infra.yaml --json
    """
    from faultray.model.loader import load_yaml
    from faultray.simulator.adoption_engine import AdoptionEngine

    if not topology.exists():
        console.print(f"[red]Topology file not found: {topology}[/]")
        raise typer.Exit(1)

    try:
        graph = load_yaml(topology)
    except Exception as exc:
        console.print(f"[red]Failed to load topology: {exc}[/]")
        raise typer.Exit(1)

    engine = AdoptionEngine(graph)
    reports = engine.assess_all_agents()

    if not reports:
        console.print("[yellow]No agent components found in topology.[/]")
        console.print("[dim]Add components with type: ai_agent or agent_orchestrator.[/]")
        raise typer.Exit(0)

    if json_output:
        data = [
            {
                "agent_id": r.agent_id,
                "agent_name": r.agent_name,
                "risk_score": r.risk_score,
                "risk_level": r.risk_level.value,
                "max_blast_radius": r.max_blast_radius,
                "hallucination_impact": r.hallucination_impact,
                "safe_to_deploy": r.safe_to_deploy,
                "failsafes": [
                    {"name": f.name, "present": f.present, "description": f.description}
                    for f in r.failsafes
                ],
                "recommendations": r.recommendations,
            }
            for r in reports
        ]
        console.print_json(data=data)
        return

    for report in reports:
        # Risk level colors
        level_colors = {
            "low": "green",
            "medium": "yellow",
            "high": "red",
            "critical": "bold red",
        }
        color = level_colors.get(report.risk_level.value, "white")

        # Summary panel
        summary = (
            f"[bold]Agent:[/] {report.agent_name} ({report.agent_id})\n"
            f"[bold]Risk Score:[/] [{color}]{report.risk_score}/10[/]  "
            f"[bold]Risk Level:[/] [{color}]{report.risk_level.value.upper()}[/]\n"
            f"[bold]Blast Radius:[/] {report.max_blast_radius} components  "
            f"[bold]Safe to Deploy:[/] {'[green]Yes[/]' if report.safe_to_deploy else '[red]No[/]'}\n\n"
            f"[bold]Hallucination Impact:[/] {report.hallucination_impact}"
        )
        console.print()
        console.print(Panel(summary, title="[bold]ADOPT Risk Assessment[/]", border_style=color))

        # Failsafes table
        if report.failsafes:
            fs_table = Table(title="Failsafe Mechanisms", show_header=True)
            fs_table.add_column("Failsafe", width=28)
            fs_table.add_column("Status", width=10, justify="center")
            fs_table.add_column("Description", width=50)

            for fs in report.failsafes:
                status = "[green]PRESENT[/]" if fs.present else "[red]MISSING[/]"
                fs_table.add_row(fs.name, status, fs.description)

            console.print(fs_table)

        # Recommendations
        if report.recommendations:
            console.print("\n[bold]Recommendations:[/]")
            for i, rec in enumerate(report.recommendations, 1):
                console.print(f"  {i}. {rec}")
            console.print()


@agent_app.command("monitor")
def agent_monitor(
    topology: Path = typer.Argument(..., help="Topology YAML file"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Generate MANAGE monitoring plan for agent infrastructure.

    Creates monitoring rules with thresholds, metrics, and recommended
    actions for detecting pre-failure conditions in agent systems.

    Examples:
        faultray agent monitor infra.yaml
        faultray agent monitor infra.yaml --json
    """
    from faultray.model.loader import load_yaml
    from faultray.simulator.agent_monitor import AgentMonitorEngine

    if not topology.exists():
        console.print(f"[red]Topology file not found: {topology}[/]")
        raise typer.Exit(1)

    try:
        graph = load_yaml(topology)
    except Exception as exc:
        console.print(f"[red]Failed to load topology: {exc}[/]")
        raise typer.Exit(1)

    engine = AgentMonitorEngine(graph)
    plan = engine.generate_monitoring_plan()

    if not plan.rules:
        console.print("[yellow]No monitoring rules generated.[/]")
        console.print("[dim]Add agent components (ai_agent, llm_endpoint, tool_service) to generate rules.[/]")
        raise typer.Exit(0)

    if json_output:
        data = {
            "total_components_monitored": plan.total_components_monitored,
            "coverage_percent": plan.coverage_percent,
            "rules": [
                {
                    "rule_id": r.rule_id,
                    "name": r.name,
                    "component_id": r.component_id,
                    "metric": r.metric,
                    "threshold": r.threshold,
                    "operator": r.operator,
                    "predicted_fault": r.predicted_fault.value,
                    "severity": r.severity.value,
                    "recommended_action": r.recommended_action,
                }
                for r in plan.rules
            ],
        }
        console.print_json(data=data)
        return

    # Coverage summary
    console.print()
    console.print(Panel(
        f"[bold]Components Monitored:[/] {plan.total_components_monitored}  "
        f"[bold]Coverage:[/] {plan.coverage_percent}%",
        title="[bold]MANAGE Monitoring Plan[/]",
        border_style="cyan",
    ))

    # Rules table
    rules_table = Table(title="Monitoring Rules", show_header=True)
    rules_table.add_column("Rule", style="cyan", width=20)
    rules_table.add_column("Component", width=16)
    rules_table.add_column("Metric", width=22)
    rules_table.add_column("Threshold", justify="right", width=12)
    rules_table.add_column("Severity", width=10, justify="center")
    rules_table.add_column("Predicted Fault", width=22)
    rules_table.add_column("Action", width=30)

    sev_colors = {
        "info": "dim",
        "warning": "yellow",
        "critical": "red",
    }

    for rule in plan.rules:
        sev_color = sev_colors.get(rule.severity.value, "white")
        op_symbol = {"gt": ">", "lt": "<", "gte": ">=", "lte": "<="}.get(rule.operator, rule.operator)
        rules_table.add_row(
            rule.name[:20],
            rule.component_id,
            rule.metric,
            f"{op_symbol} {rule.threshold:.1f}",
            f"[{sev_color}]{rule.severity.value.upper()}[/]",
            rule.predicted_fault.value.replace("_", " ").title(),
            rule.recommended_action[:30],
        )

    console.print()
    console.print(rules_table)


@agent_app.command("scenarios")
def agent_scenarios(
    topology: Path = typer.Argument(..., help="Topology YAML file"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List agent-specific chaos scenarios for the topology.

    Generates scenarios including single agent failures, cross-layer
    failures, prompt injection, and cascading failure chains.

    Examples:
        faultray agent scenarios infra.yaml
        faultray agent scenarios infra.yaml --json
    """
    from faultray.model.loader import load_yaml
    from faultray.simulator.agent_scenarios import generate_agent_scenarios

    if not topology.exists():
        console.print(f"[red]Topology file not found: {topology}[/]")
        raise typer.Exit(1)

    try:
        graph = load_yaml(topology)
    except Exception as exc:
        console.print(f"[red]Failed to load topology: {exc}[/]")
        raise typer.Exit(1)

    scenarios = generate_agent_scenarios(graph)

    if not scenarios:
        console.print("[yellow]No agent-specific scenarios generated.[/]")
        console.print("[dim]Add agent components (ai_agent, llm_endpoint, tool_service) to generate scenarios.[/]")
        raise typer.Exit(0)

    if json_output:
        data = [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "faults": [
                    {"target": f.target_component_id, "type": f.fault_type.value}
                    for f in s.faults
                ],
            }
            for s in scenarios
        ]
        console.print_json(data=data)
        return

    # Summary
    console.print()
    console.print(Panel(
        f"[bold]Total Scenarios:[/] {len(scenarios)}",
        title="[bold]Agent Chaos Scenarios[/]",
        border_style="cyan",
    ))

    # Scenarios table
    sc_table = Table(title="Generated Scenarios", show_header=True)
    sc_table.add_column("ID", style="dim", width=32)
    sc_table.add_column("Name", style="cyan", width=36)
    sc_table.add_column("Faults", justify="right", width=6)
    sc_table.add_column("Description", width=50)

    for sc in scenarios:
        sc_table.add_row(
            sc.id,
            sc.name,
            str(len(sc.faults)),
            sc.description[:50] + ("..." if len(sc.description) > 50 else ""),
        )

    console.print()
    console.print(sc_table)
