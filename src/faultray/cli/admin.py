# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Admin CLI commands: demo, serve, report, plan, quickstart."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from faultray.simulator.planner import RemediationPlan, RemediationPlanner

from faultray.cli.main import (
    DEFAULT_MODEL_PATH,
    InfraGraph,
    _load_graph_for_analysis,
    app,
    console,
)
from faultray.reporter.report import print_infrastructure_summary, print_simulation_report
from faultray.simulator.engine import SimulationEngine


@app.command()
def demo(
    web: bool = typer.Option(False, "--web", "-w", help="Launch web dashboard after building demo"),
    host: str = typer.Option("0.0.0.0", "--host", help="Web dashboard bind host"),
    port: int = typer.Option(8080, "--port", "-p", help="Web dashboard bind port"),
) -> None:
    """Run simulation with a demo infrastructure (no scanning required).

    Examples:
        # Run demo simulation
        faultray demo

        # Run demo and launch web dashboard
        faultray demo --web

        # Demo with custom port
        faultray demo --web --port 3000
    """
    from faultray.model.demo import create_demo_graph

    console.print("[cyan]Building demo infrastructure...[/]")

    graph = create_demo_graph()

    # Show infrastructure
    print_infrastructure_summary(graph, console)

    # Run simulation
    console.print("\n[cyan]Running chaos simulation...[/]")
    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()

    print_simulation_report(report, console, graph=graph)

    # Launch web dashboard if requested
    if web:
        import uvicorn

        from faultray.api.server import set_graph

        set_graph(graph)
        console.print(f"\n[green]Starting FaultRay dashboard at http://{host}:{port}[/]")
        uvicorn.run("faultray.api.server:app", host=host, port=port, log_level="info")


@app.command()
def serve(
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path"),
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host"),
    port: int = typer.Option(8080, "--port", "-p", help="Bind port"),
    prometheus_url: str | None = typer.Option(None, "--prometheus-url", help="Prometheus URL for continuous monitoring"),
    prometheus_interval: int = typer.Option(60, "--prometheus-interval", help="Prometheus polling interval in seconds"),
) -> None:
    """Launch web dashboard.

    Examples:
        # Start dashboard on default port
        faultray serve

        # Use a specific model
        faultray serve --model my-model.json

        # Custom host and port
        faultray serve --host 127.0.0.1 --port 3000

        # Enable Prometheus continuous monitoring
        faultray serve --prometheus-url http://prometheus:9090 --prometheus-interval 30
    """
    import os

    import uvicorn

    from faultray.api.server import set_graph

    if model.exists():
        console.print(f"[cyan]Loading model from {model}...[/]")
        graph = InfraGraph.load(model)
        set_graph(graph)
    else:
        console.print("[yellow]No model file found. Visit /demo in the browser to load demo data.[/]")

    # Pass Prometheus settings via env vars so the FastAPI lifespan can pick them up
    if prometheus_url:
        os.environ["FAULTRAY_PROMETHEUS_URL"] = prometheus_url
        os.environ["FAULTRAY_PROMETHEUS_INTERVAL"] = str(prometheus_interval)
        console.print(
            f"[cyan]Prometheus monitoring enabled: {prometheus_url} "
            f"(interval={prometheus_interval}s)[/]"
        )

    console.print(f"[green]Starting FaultRay dashboard at http://{host}:{port}[/]")
    uvicorn.run("faultray.api.server:app", host=host, port=port, log_level="info")


@app.command()
def report(
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path"),
    output: Path = typer.Option(Path("report.html"), "--output", "-o", help="Output HTML file path"),
) -> None:
    """Generate an HTML report from a saved model (runs simulation automatically).

    Examples:
        # Generate report with default model
        faultray report

        # Custom model and output path
        faultray report --model my-model.json --output results.html
    """
    from faultray.reporter.html_report import save_html_report

    if not model.exists():
        console.print(f"[red]Model file not found: {model}[/]")
        console.print("Run [cyan]faultray scan[/] or [cyan]faultray load[/] first.")
        raise typer.Exit(1)

    console.print("[cyan]Loading infrastructure model...[/]")
    graph = InfraGraph.load(model)

    console.print(f"[cyan]Running chaos simulation ({len(graph.components)} components)...[/]")
    engine = SimulationEngine(graph)
    sim_report = engine.run_all_defaults()

    print_simulation_report(sim_report, console, graph=graph)

    save_html_report(sim_report, graph, output)
    console.print(f"\n[green]HTML report saved to {output}[/]")


@app.command()
def plan(
    model: Path = typer.Argument(
        None,
        help="Model file (JSON or YAML) to generate a remediation plan for",
    ),
    model_opt: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path (alternative to positional arg)"),
    target_score: float = typer.Option(90.0, "--target-score", "-t", help="Target resilience score (0-100)"),
    budget: float | None = typer.Option(None, "--budget", "-b", help="Maximum budget limit in $"),
    json_output: bool = typer.Option(False, "--json", help="Output plan as JSON"),
    html: Path | None = typer.Option(None, "--html", help="Export plan as HTML report"),
) -> None:
    """Generate a phased remediation plan with timeline, team requirements, and ROI.

    Examples:
        # Generate plan for default model
        faultray plan

        # Plan for a specific model
        faultray plan my-model.json

        # Set target score and budget
        faultray plan --target-score 95 --budget 50000

        # JSON output for automation
        faultray plan --json

        # Export plan as HTML
        faultray plan --html plan-report.html
    """
    from rich.panel import Panel
    from rich.table import Table

    from faultray.simulator.planner import RemediationPlanner

    # Resolve model path: positional arg takes precedence
    resolved_model = model if model is not None else model_opt
    graph = _load_graph_for_analysis(resolved_model, yaml_file=None)

    if not json_output:
        console.print(f"[cyan]Analyzing infrastructure ({len(graph.components)} components)...[/]")

    planner = RemediationPlanner(graph)
    remediation_plan = planner.plan(target_score=target_score, budget_limit=budget)

    if json_output:
        console.print_json(data=planner.plan_to_dict(remediation_plan))
        return

    # Rich output
    # Summary panel
    score_color = "green" if remediation_plan.current_score >= 80 else (
        "yellow" if remediation_plan.current_score >= 50 else "red"
    )
    roi_str = (
        f"{remediation_plan.overall_roi:.0f}%"
        if remediation_plan.overall_roi != float("inf")
        else "infinite"
    )

    summary_text = (
        f"[bold]Current Score:[/] [{score_color}]{remediation_plan.current_score:.1f}/100[/]\n"
        f"[bold]Target Score:[/] {remediation_plan.target_score:.1f}/100\n"
        f"[bold]Timeline:[/] {remediation_plan.total_weeks} weeks\n"
        f"[bold]Total Budget:[/] ${remediation_plan.total_budget:,.0f}\n"
        f"[bold]Annual Risk Reduction:[/] ${remediation_plan.total_risk_reduction:,.0f}\n"
        f"[bold]Overall ROI:[/] {roi_str}"
    )

    console.print()
    console.print(Panel(
        summary_text,
        title="[bold]FaultRay Remediation Plan[/]",
        border_style="cyan",
    ))

    # Phase details
    for phase in remediation_plan.phases:
        console.print(
            f"\n[bold cyan]Phase {phase.phase_number}: {phase.name}[/] "
            f"({phase.estimated_weeks} weeks, team of {phase.team_size})"
        )
        console.print(
            f"  Score: {phase.score_before:.1f} -> {phase.score_after:.1f} "
            f"| Cost: ${phase.phase_cost:,.0f}"
        )

        # Tasks table
        task_table = Table(show_header=True, header_style="bold", padding=(0, 1))
        task_table.add_column("ID", width=5)
        task_table.add_column("Title", width=35, style="cyan")
        task_table.add_column("Priority", width=10, justify="center")
        task_table.add_column("Role", width=15)
        task_table.add_column("Hours", width=6, justify="right")
        task_table.add_column("Monthly $", width=10, justify="right")
        task_table.add_column("ROI", width=10, justify="right")

        priority_colors = {
            "critical": "bold red",
            "high": "red",
            "medium": "yellow",
            "low": "green",
        }

        for task in phase.tasks:
            color = priority_colors.get(task.priority, "white")
            roi_display = (
                f"{task.roi_percent:.0f}%"
                if task.roi_percent != float("inf")
                else "inf"
            )
            task_table.add_row(
                task.id,
                task.title[:35],
                f"[{color}]{task.priority.upper()}[/]",
                task.required_role,
                f"{task.estimated_hours:.0f}",
                f"${task.monthly_cost_increase:,.0f}",
                roi_display,
            )

        console.print(task_table)

    # HTML export
    if html:
        _export_plan_html(html, remediation_plan, planner)
        console.print(f"\n[green]Plan report saved to {html}[/]")


def _export_plan_html(path: Path, plan: "RemediationPlan", planner: "RemediationPlanner") -> None:
    """Generate an HTML report for the remediation plan."""

    roi_str = (
        f"{plan.overall_roi:.0f}%"
        if plan.overall_roi != float("inf")
        else "infinite"
    )

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>FaultRay Remediation Plan</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       margin: 2em auto; max-width: 900px; color: #333; }}
h1 {{ border-bottom: 3px solid #3498db; padding-bottom: 0.3em; }}
h2 {{ color: #2c3e50; margin-top: 1.5em; }}
.summary {{ background: #f8f9fa; border-radius: 8px; padding: 1em; margin: 1em 0;
            border-left: 4px solid #3498db; }}
.metric {{ display: inline-block; margin: 0.3em 1em 0.3em 0;
           padding: 0.4em 0.8em; background: #fff; border-radius: 4px;
           border: 1px solid #ddd; }}
table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
th, td {{ border: 1px solid #ddd; padding: 0.5em; text-align: left; }}
th {{ background: #f8f9fa; }}
.critical {{ color: #e74c3c; font-weight: bold; }}
.high {{ color: #e67e22; }}
.medium {{ color: #f39c12; }}
.low {{ color: #27ae60; }}
</style>
</head>
<body>
<h1>FaultRay Remediation Plan</h1>
<div class="summary">
  <div class="metric">Current Score: <strong>{plan.current_score:.1f}/100</strong></div>
  <div class="metric">Target Score: <strong>{plan.target_score:.1f}/100</strong></div>
  <div class="metric">Timeline: <strong>{plan.total_weeks} weeks</strong></div>
  <div class="metric">Budget: <strong>${plan.total_budget:,.0f}</strong></div>
  <div class="metric">Annual Risk Reduction: <strong>${plan.total_risk_reduction:,.0f}</strong></div>
  <div class="metric">Overall ROI: <strong>{roi_str}</strong></div>
</div>
"""

    for phase in plan.phases:
        html_content += f"""
<h2>Phase {phase.phase_number}: {phase.name}</h2>
<p>{phase.estimated_weeks} weeks | Team of {phase.team_size} |
   Score: {phase.score_before:.1f} &rarr; {phase.score_after:.1f} |
   Cost: ${phase.phase_cost:,.0f}</p>
<table>
<tr><th>ID</th><th>Title</th><th>Priority</th><th>Role</th><th>Hours</th>
    <th>Monthly Cost</th><th>ROI</th></tr>
"""
        for task in phase.tasks:
            roi_display = (
                f"{task.roi_percent:.0f}%"
                if task.roi_percent != float("inf")
                else "infinite"
            )
            html_content += (
                f"<tr><td>{task.id}</td>"
                f"<td>{task.title}</td>"
                f'<td class="{task.priority}">{task.priority.upper()}</td>'
                f"<td>{task.required_role}</td>"
                f"<td>{task.estimated_hours:.0f}</td>"
                f"<td>${task.monthly_cost_increase:,.0f}</td>"
                f"<td>{roi_display}</td></tr>\n"
            )

        html_content += "</table>\n"

    html_content += """
<hr>
<p><em>Generated by FaultRay Remediation Planner</em></p>
</body>
</html>"""

    path.write_text(html_content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Quickstart command
# ---------------------------------------------------------------------------

# Architecture templates for quickstart
_TEMPLATES: dict[str, dict] = {
    "web-app": {
        "description": "Web Application (frontend + API + database)",
        "components": [
            {"id": "lb", "name": "Load Balancer", "type": "load_balancer", "port": 443},
            {"id": "app", "name": "API Server", "type": "app_server", "port": 8080, "replicas": 2},
            {"id": "db", "name": "Database", "type": "database", "port": 5432},
        ],
        "dependencies": [
            {"source": "lb", "target": "app", "type": "requires"},
            {"source": "app", "target": "db", "type": "requires"},
        ],
    },
    "microservices": {
        "description": "Microservices (multiple services + message queue)",
        "components": [
            {"id": "lb", "name": "Load Balancer", "type": "load_balancer", "port": 443},
            {"id": "api", "name": "API Gateway", "type": "app_server", "port": 8080, "replicas": 2},
            {"id": "svc-users", "name": "User Service", "type": "app_server", "port": 8081, "replicas": 2},
            {"id": "svc-orders", "name": "Order Service", "type": "app_server", "port": 8082, "replicas": 2},
            {"id": "db", "name": "Database", "type": "database", "port": 5432},
            {"id": "queue", "name": "Message Queue", "type": "queue", "port": 5672},
        ],
        "dependencies": [
            {"source": "lb", "target": "api", "type": "requires"},
            {"source": "api", "target": "svc-users", "type": "requires"},
            {"source": "api", "target": "svc-orders", "type": "requires"},
            {"source": "svc-users", "target": "db", "type": "requires"},
            {"source": "svc-orders", "target": "db", "type": "requires"},
            {"source": "svc-orders", "target": "queue", "type": "async"},
        ],
    },
    "data-pipeline": {
        "description": "Data Pipeline (ingestion + processing + storage)",
        "components": [
            {"id": "ingestion", "name": "Data Ingestion", "type": "app_server", "port": 8080},
            {"id": "queue", "name": "Message Queue", "type": "queue", "port": 9092},
            {"id": "processor", "name": "Stream Processor", "type": "app_server", "port": 8081, "replicas": 3},
            {"id": "db", "name": "Data Store", "type": "database", "port": 5432},
            {"id": "storage", "name": "Object Storage", "type": "storage", "port": 443},
        ],
        "dependencies": [
            {"source": "ingestion", "target": "queue", "type": "requires"},
            {"source": "processor", "target": "queue", "type": "requires"},
            {"source": "processor", "target": "db", "type": "requires"},
            {"source": "processor", "target": "storage", "type": "async"},
        ],
    },
}

# Database port mapping
_DB_PORTS: dict[str, int] = {
    "postgres": 5432,
    "mysql": 3306,
    "mongodb": 27017,
    "dynamodb": 443,
}

_DB_NAMES: dict[str, str] = {
    "postgres": "PostgreSQL/Aurora",
    "mysql": "MySQL",
    "mongodb": "MongoDB",
    "dynamodb": "DynamoDB",
}


def _build_yaml_from_answers(
    template: str,
    api_replicas: int,
    database: str | None,
    cache: bool,
    queue: str | None,
    cdn: bool,
    lb: bool,
) -> str:
    """Build a YAML infrastructure definition from quickstart answers."""
    import yaml

    _TEMPLATES.get(template, _TEMPLATES["web-app"])

    # Start with template components and customize
    components: list[dict] = []
    dependencies: list[dict] = []

    # Load balancer
    if lb:
        components.append({
            "id": "lb",
            "name": "Load Balancer",
            "type": "load_balancer",
            "port": 443,
            "replicas": 1,
            "metrics": {"cpu_percent": 20, "memory_percent": 30},
            "capacity": {"max_connections": 10000, "max_rps": 50000},
        })

    # API servers
    components.append({
        "id": "app",
        "name": "API Server",
        "type": "app_server",
        "port": 8080,
        "replicas": api_replicas,
        "metrics": {"cpu_percent": 40, "memory_percent": 50},
        "capacity": {"max_connections": 1000},
    })

    if lb:
        dependencies.append({"source": "lb", "target": "app", "type": "requires"})

    # Database
    if database and database.lower() != "none":
        db_key = database.lower()
        db_port = _DB_PORTS.get(db_key, 5432)
        db_name = _DB_NAMES.get(db_key, database)
        components.append({
            "id": "db",
            "name": db_name,
            "type": "database",
            "port": db_port,
            "replicas": 1,
            "metrics": {"cpu_percent": 35, "memory_percent": 60},
            "capacity": {"max_connections": 200},
        })
        dependencies.append({"source": "app", "target": "db", "type": "requires"})

    # Cache
    if cache:
        components.append({
            "id": "cache",
            "name": "Redis Cache",
            "type": "cache",
            "port": 6379,
            "replicas": 1,
            "metrics": {"cpu_percent": 15, "memory_percent": 45},
            "capacity": {"max_connections": 10000},
        })
        dependencies.append({"source": "app", "target": "cache", "type": "optional"})

    # Message queue
    if queue and queue.lower() != "none":
        queue_name = queue
        queue_port = 5672
        if queue.lower() == "kafka":
            queue_port = 9092
        elif queue.lower() == "sqs":
            queue_port = 443
            queue_name = "SQS"
        elif queue.lower() == "rabbitmq":
            queue_port = 5672
            queue_name = "RabbitMQ"

        components.append({
            "id": "queue",
            "name": queue_name,
            "type": "queue",
            "port": queue_port,
            "replicas": 1,
            "metrics": {"cpu_percent": 20, "memory_percent": 40},
            "capacity": {"max_connections": 1000},
        })
        dependencies.append({"source": "app", "target": "queue", "type": "async"})

    # CDN
    if cdn:
        components.append({
            "id": "cdn",
            "name": "CloudFront CDN",
            "type": "load_balancer",
            "port": 443,
            "replicas": 1,
            "metrics": {"cpu_percent": 5, "memory_percent": 10},
            "capacity": {"max_connections": 100000},
        })
        target = "lb" if lb else "app"
        dependencies.append({"source": "cdn", "target": target, "type": "requires"})

    # For microservices template, add extra services
    if template == "microservices":
        components = []  # rebuild from scratch
        dependencies = []

        if lb:
            components.append({
                "id": "lb",
                "name": "Load Balancer",
                "type": "load_balancer",
                "port": 443,
                "replicas": 1,
                "metrics": {"cpu_percent": 20, "memory_percent": 30},
                "capacity": {"max_connections": 10000},
            })

        components.append({
            "id": "api",
            "name": "API Gateway",
            "type": "app_server",
            "port": 8080,
            "replicas": api_replicas,
            "metrics": {"cpu_percent": 30, "memory_percent": 40},
            "capacity": {"max_connections": 2000},
        })

        components.append({
            "id": "svc-users",
            "name": "User Service",
            "type": "app_server",
            "port": 8081,
            "replicas": api_replicas,
            "metrics": {"cpu_percent": 40, "memory_percent": 50},
            "capacity": {"max_connections": 1000},
        })

        components.append({
            "id": "svc-orders",
            "name": "Order Service",
            "type": "app_server",
            "port": 8082,
            "replicas": api_replicas,
            "metrics": {"cpu_percent": 40, "memory_percent": 50},
            "capacity": {"max_connections": 1000},
        })

        if lb:
            dependencies.append({"source": "lb", "target": "api", "type": "requires"})
        dependencies.append({"source": "api", "target": "svc-users", "type": "requires"})
        dependencies.append({"source": "api", "target": "svc-orders", "type": "requires"})

        if database and database.lower() != "none":
            db_key = database.lower()
            db_port = _DB_PORTS.get(db_key, 5432)
            db_name = _DB_NAMES.get(db_key, database)
            components.append({
                "id": "db",
                "name": db_name,
                "type": "database",
                "port": db_port,
                "replicas": 1,
                "metrics": {"cpu_percent": 35, "memory_percent": 60},
                "capacity": {"max_connections": 200},
            })
            dependencies.append({"source": "svc-users", "target": "db", "type": "requires"})
            dependencies.append({"source": "svc-orders", "target": "db", "type": "requires"})

        if cache:
            components.append({
                "id": "cache",
                "name": "Redis Cache",
                "type": "cache",
                "port": 6379,
                "replicas": 1,
                "metrics": {"cpu_percent": 15, "memory_percent": 45},
                "capacity": {"max_connections": 10000},
            })
            dependencies.append({"source": "svc-users", "target": "cache", "type": "optional"})

        if queue and queue.lower() != "none":
            queue_name = queue
            queue_port = 5672
            if queue.lower() == "kafka":
                queue_port = 9092
            elif queue.lower() == "sqs":
                queue_port = 443
                queue_name = "SQS"
            components.append({
                "id": "queue",
                "name": queue_name,
                "type": "queue",
                "port": queue_port,
                "replicas": 1,
                "metrics": {"cpu_percent": 20, "memory_percent": 40},
                "capacity": {"max_connections": 1000},
            })
            dependencies.append({"source": "svc-orders", "target": "queue", "type": "async"})

        if cdn:
            components.append({
                "id": "cdn",
                "name": "CloudFront CDN",
                "type": "load_balancer",
                "port": 443,
                "replicas": 1,
                "metrics": {"cpu_percent": 5, "memory_percent": 10},
                "capacity": {"max_connections": 100000},
            })
            target = "lb" if lb else "api"
            dependencies.append({"source": "cdn", "target": target, "type": "requires"})

    elif template == "data-pipeline":
        components = []
        dependencies = []

        components.append({
            "id": "ingestion",
            "name": "Data Ingestion",
            "type": "app_server",
            "port": 8080,
            "replicas": api_replicas,
            "metrics": {"cpu_percent": 50, "memory_percent": 40},
            "capacity": {"max_connections": 2000},
        })

        q_name = queue if queue and queue.lower() != "none" else "Kafka"
        q_port = 9092
        if q_name.lower() == "sqs":
            q_port = 443
        elif q_name.lower() == "rabbitmq":
            q_port = 5672
        components.append({
            "id": "queue",
            "name": q_name,
            "type": "queue",
            "port": q_port,
            "replicas": 1,
            "metrics": {"cpu_percent": 30, "memory_percent": 50},
            "capacity": {"max_connections": 5000},
        })

        components.append({
            "id": "processor",
            "name": "Stream Processor",
            "type": "app_server",
            "port": 8081,
            "replicas": max(api_replicas, 3),
            "metrics": {"cpu_percent": 60, "memory_percent": 55},
            "capacity": {"max_connections": 1000},
        })

        if database and database.lower() != "none":
            db_key = database.lower()
            db_port = _DB_PORTS.get(db_key, 5432)
            db_name = _DB_NAMES.get(db_key, database)
            components.append({
                "id": "db",
                "name": db_name,
                "type": "database",
                "port": db_port,
                "replicas": 1,
                "metrics": {"cpu_percent": 40, "memory_percent": 65},
                "capacity": {"max_connections": 200},
            })

        components.append({
            "id": "storage",
            "name": "Object Storage",
            "type": "storage",
            "port": 443,
            "replicas": 1,
            "metrics": {"cpu_percent": 5, "memory_percent": 10},
            "capacity": {"max_connections": 100000},
        })

        dependencies.append({"source": "ingestion", "target": "queue", "type": "requires"})
        dependencies.append({"source": "processor", "target": "queue", "type": "requires"})
        if database and database.lower() != "none":
            dependencies.append({"source": "processor", "target": "db", "type": "requires"})
        dependencies.append({"source": "processor", "target": "storage", "type": "async"})

    data = {"components": components, "dependencies": dependencies}
    return yaml.dump(data, default_flow_style=False, sort_keys=False)


@app.command()
def quickstart(
    template: str | None = typer.Option(None, "--template", help="Architecture template: web-app, microservices, data-pipeline"),
    api_replicas: int | None = typer.Option(None, "--api-replicas", help="Number of API server replicas"),
    database: str | None = typer.Option(None, "--database", help="Database type: postgres, mysql, mongodb, dynamodb, none"),
    cache: str | None = typer.Option(None, "--cache", help="Cache: redis, none"),
    queue: str | None = typer.Option(None, "--queue", help="Message queue: kafka, sqs, rabbitmq, none"),
    cdn: str | None = typer.Option(None, "--cdn", help="CDN: cloudfront, none"),
    output: Path = typer.Option(Path("faultray-model.yaml"), "--output", "-o", help="Output YAML file path"),
) -> None:
    """Interactive infrastructure builder for new users.

    Generates a YAML model, runs a quick simulation, and shows a summary.
    Use --template for non-interactive mode.
    """
    from rich.panel import Panel

    console.print("\n[bold cyan]Welcome to FaultRay![/] Let's build your infrastructure model.\n")

    # Determine if running interactively or with flags
    is_non_interactive = template is not None

    if is_non_interactive:
        # Non-interactive mode
        selected_template = template if template in _TEMPLATES else "web-app"
        selected_replicas = api_replicas if api_replicas is not None else 2
        selected_db = database if database else "postgres"
        use_cache = cache is not None and cache.lower() != "none"
        selected_queue = queue if queue else None
        use_cdn = cdn is not None and cdn.lower() != "none"
        use_lb = selected_template != "data-pipeline"
    else:
        # Interactive mode
        console.print("[bold]What type of application?[/]")
        console.print("  1) Web Application (frontend + API + database)")
        console.print("  2) Microservices (multiple services + message queue)")
        console.print("  3) Data Pipeline (ingestion + processing + storage)")

        choice = typer.prompt("Choose (1-3)", default="1")
        template_map = {"1": "web-app", "2": "microservices", "3": "data-pipeline"}
        selected_template = template_map.get(choice, "web-app")

        use_lb = True
        if selected_template != "data-pipeline":
            use_lb = typer.confirm("Do you use a load balancer?", default=True)

        selected_replicas = typer.prompt(
            "How many API server replicas?",
            default=2,
            type=int,
        )

        console.print("\n[bold]What database?[/]")
        console.print("  1) PostgreSQL/Aurora")
        console.print("  2) MySQL")
        console.print("  3) MongoDB")
        console.print("  4) DynamoDB")
        console.print("  5) None")

        db_choice = typer.prompt("Choose (1-5)", default="1")
        db_map = {"1": "postgres", "2": "mysql", "3": "mongodb", "4": "dynamodb", "5": "none"}
        selected_db = db_map.get(db_choice, "postgres")

        use_cache = typer.confirm("Do you use Redis/Memcached?", default=True)

        queue_input = typer.prompt(
            "Do you use a message queue? (kafka/sqs/rabbitmq/none)",
            default="none",
        )
        selected_queue = queue_input if queue_input.lower() != "none" else None

        cdn_input = typer.prompt(
            "Do you have CDN? (cloudfront/none)",
            default="none",
        )
        use_cdn = cdn_input.lower() != "none"

    # Generate YAML
    console.print("\n[cyan]Generating infrastructure model...[/]")
    yaml_content = _build_yaml_from_answers(
        template=selected_template,
        api_replicas=selected_replicas,
        database=selected_db if selected_db != "none" else None,
        cache=use_cache,
        queue=selected_queue,
        cdn=use_cdn,
        lb=use_lb if selected_template != "data-pipeline" else False,
    )

    output.write_text(yaml_content, encoding="utf-8")

    # Load and simulate
    from faultray.model.loader import load_yaml

    graph = load_yaml(output)
    num_components = len(graph.components)
    num_deps = len(graph.all_dependency_edges())

    console.print(
        f"[green]Saved to {output} "
        f"({num_components} components, {num_deps} dependencies)[/]"
    )

    console.print("\n[cyan]Running chaos simulation...[/]")
    engine = SimulationEngine(graph)
    sim_report = engine.run_all_defaults()

    # Quick report
    v2 = graph.resilience_score_v2()
    score = v2["score"]
    critical = len(sim_report.critical_findings)
    warnings = len(sim_report.warnings)

    # Find top risk
    top_risk = "No critical risks detected"
    if sim_report.critical_findings:
        top_scenario = sim_report.critical_findings[0].scenario
        top_risk = top_scenario.name

    score_color = "green" if score >= 80 else ("yellow" if score >= 50 else "red")

    report_text = (
        f"[bold]Resilience:[/] [{score_color}]{score:.0f}/100[/]\n"
        f"[red]Critical: {critical}[/]  [yellow]Warning: {warnings}[/]\n"
        f"[bold]Top risk:[/] {top_risk}"
    )

    console.print()
    console.print(Panel(
        report_text,
        title="[bold]FaultRay Quick Report[/]",
        border_style="cyan",
    ))

    console.print("\nRun [cyan]faultray plan[/] to see improvement recommendations.")
