"""Interactive quickstart command for ChaosProof."""

from __future__ import annotations

import shutil
from pathlib import Path

import typer
from rich.panel import Panel

from infrasim.cli.main import app, console


# Map user-friendly names to example YAML files
_INFRA_TEMPLATES: dict[str, dict[str, str]] = {
    "fintech": {
        "file": "fintech-banking.yaml",
        "label": "Fintech / Banking (DORA)",
        "description": "API Gateway, Core Banking APIs, PostgreSQL HA, Kafka, Redis, KMS",
    },
    "ecommerce": {
        "file": "ecommerce-platform.yaml",
        "label": "E-Commerce Platform (PCI DSS)",
        "description": "ALB, Web Frontends, Cart/Payment APIs, Product/Order DBs, Elasticsearch",
    },
    "healthcare": {
        "file": "healthcare-ehr.yaml",
        "label": "Healthcare EHR (HIPAA)",
        "description": "API Gateway, Auth, Patient APIs, EHR DB with DR, FHIR, S3 Medical Images",
    },
    "saas": {
        "file": "saas-multi-tenant.yaml",
        "label": "SaaS Multi-Tenant (SOC2)",
        "description": "CloudFront, Tenant Router, API Servers, PostgreSQL HA, Kafka, Workers",
    },
    "web-app": {
        "file": "demo-infra.yaml",
        "label": "Simple Web App (Demo)",
        "description": "Nginx LB, App Servers, PostgreSQL, Redis, RabbitMQ",
    },
}


@app.command()
def quickstart(
    output: Path = typer.Option(
        Path("infra.yaml"),
        "--output", "-o",
        help="Output path for the generated YAML file.",
    ),
    template: str = typer.Option(
        "",
        "--template", "-t",
        help="Template name (fintech/ecommerce/healthcare/saas/web-app). Skips interactive prompt.",
    ),
    run_sim: bool = typer.Option(
        True,
        "--simulate/--no-simulate",
        help="Run a simulation after generating the YAML.",
    ),
    web: bool = typer.Option(
        False,
        "--web",
        help="Open the web dashboard after simulation.",
    ),
) -> None:
    """Interactive quickstart -- generate infrastructure YAML and run first simulation."""
    console.print(Panel(
        "[bold cyan]ChaosProof Quickstart[/]\n\n"
        "This wizard helps you get started with ChaosProof in seconds.\n"
        "Choose an industry template, run your first chaos simulation,\n"
        "and explore the results in the web dashboard.",
        border_style="cyan",
    ))

    # ---- 1. Select template --------------------------------------------------
    if template and template in _INFRA_TEMPLATES:
        selected = template
    else:
        console.print("\n[bold]Available infrastructure templates:[/]\n")
        keys = list(_INFRA_TEMPLATES.keys())
        for idx, key in enumerate(keys, 1):
            t = _INFRA_TEMPLATES[key]
            console.print(f"  [cyan]{idx}[/]. {t['label']}")
            console.print(f"     {t['description']}\n")

        choice = typer.prompt(
            "Select a template (1-5)",
            default="5",
        )
        try:
            selected = keys[int(choice) - 1]
        except (ValueError, IndexError):
            selected = "web-app"

    tmpl = _INFRA_TEMPLATES[selected]
    console.print(f"\n[green]Selected:[/] {tmpl['label']}")

    # ---- 2. Copy template YAML -----------------------------------------------
    examples_dir = Path(__file__).resolve().parents[3] / "examples"
    if not examples_dir.exists():
        # Fallback: installed package — look relative to CWD
        examples_dir = Path.cwd() / "examples"

    src = examples_dir / tmpl["file"]
    if not src.exists():
        console.print(f"[red]Template file not found: {src}[/]")
        raise typer.Exit(1)

    if output.exists():
        overwrite = typer.confirm(f"{output} already exists. Overwrite?", default=True)
        if not overwrite:
            console.print("[yellow]Aborted.[/]")
            raise typer.Exit(0)

    shutil.copy2(src, output)
    console.print(f"[green]Created:[/] {output}")

    # ---- 3. Run simulation ---------------------------------------------------
    if run_sim:
        console.print("\n[bold]Running chaos simulation...[/]\n")

        from infrasim.model.loader import load_yaml
        from infrasim.simulator.engine import SimulationEngine
        from infrasim.reporter.report import print_infrastructure_summary, print_simulation_report

        graph = load_yaml(output)
        print_infrastructure_summary(graph, console)

        engine = SimulationEngine(graph)
        results = engine.run()
        print_simulation_report(results, console)

        console.print(
            f"\n[bold green]Simulation complete![/] "
            f"{len(graph.components)} components, "
            f"{len(results)} scenarios evaluated."
        )

    # ---- 4. Optionally open web dashboard ------------------------------------
    if web:
        console.print("\n[bold]Starting web dashboard...[/]")
        console.print("[dim]Press Ctrl+C to stop.[/]\n")

        try:
            import uvicorn
            uvicorn.run(
                "infrasim.api.server:app",
                host="0.0.0.0",
                port=8000,
                log_level="info",
            )
        except ImportError:
            console.print("[yellow]uvicorn not installed. Install with: pip install uvicorn[/]")

    if not web:
        console.print(
            "\n[dim]Next steps:[/]\n"
            f"  1. Edit [cyan]{output}[/] to customize your infrastructure\n"
            "  2. Run [cyan]chaosproof simulate {output}[/] for detailed analysis\n"
            "  3. Run [cyan]chaosproof serve[/] to open the web dashboard\n"
        )
