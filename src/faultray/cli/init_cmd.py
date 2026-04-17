# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Interactive infrastructure definition wizard (faultray init)."""

from __future__ import annotations

from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from faultray.cli.main import app, console

# ---------------------------------------------------------------------------
# Component presets for the wizard
# ---------------------------------------------------------------------------

_LB_PRESETS: dict[str, dict] = {
    "F5 BIG-IP": {"host": "f5-lb.internal", "port": 443},
    "Nginx": {"host": "nginx-lb.internal", "port": 443},
    "HAProxy": {"host": "haproxy.internal", "port": 443},
}

_APP_PRESETS: dict[str, dict] = {
    "Tomcat": {"host": "tomcat.internal", "port": 8080},
    "IIS": {"host": "iis.internal", "port": 443},
    "Node.js": {"host": "node-app.internal", "port": 3000},
}

_DB_PRESETS: dict[str, dict] = {
    "Oracle": {"host": "oracle.internal", "port": 1521},
    "MySQL": {"host": "mysql.internal", "port": 3306},
    "PostgreSQL": {"host": "postgres.internal", "port": 5432},
    "SQL Server": {"host": "mssql.internal", "port": 1433},
}

_CACHE_PRESETS: dict[str, dict] = {
    "Redis": {"host": "redis.internal", "port": 6379},
    "Memcached": {"host": "memcached.internal", "port": 11211},
}

_QUEUE_PRESETS: dict[str, dict] = {
    "RabbitMQ": {"host": "rabbitmq.internal", "port": 5672},
    "ActiveMQ": {"host": "activemq.internal", "port": 61616},
    "Kafka": {"host": "kafka.internal", "port": 9092},
}

_STORAGE_PRESETS: dict[str, dict] = {
    "NAS": {"host": "nas.internal", "port": 2049},
    "SAN": {"host": "san.internal", "port": 3260},
    "NFS": {"host": "nfs.internal", "port": 2049},
}

_CLOUD_LB_PRESETS: dict[str, dict[str, dict]] = {
    "aws": {"ALB": {"host": "alb.us-east-1.elb.amazonaws.com", "port": 443}},
    "gcp": {"Cloud Load Balancer": {"host": "lb.googleapis.com", "port": 443}},
    "azure": {"Azure LB": {"host": "lb.azure.com", "port": 443}},
}

_CLOUD_APP_PRESETS: dict[str, dict[str, dict]] = {
    "aws": {"EC2": {"host": "ec2-app.internal", "port": 8080}},
    "gcp": {"GCE": {"host": "gce-app.internal", "port": 8080}},
    "azure": {"Azure VM": {"host": "vm-app.internal", "port": 8080}},
}

_CLOUD_DB_PRESETS: dict[str, dict[str, dict]] = {
    "aws": {
        "RDS PostgreSQL": {"host": "rds.us-east-1.rds.amazonaws.com", "port": 5432},
        "RDS MySQL": {"host": "rds-mysql.us-east-1.rds.amazonaws.com", "port": 3306},
        "Aurora": {"host": "aurora.us-east-1.rds.amazonaws.com", "port": 5432},
    },
    "gcp": {
        "Cloud SQL PostgreSQL": {"host": "cloudsql.googleapis.com", "port": 5432},
        "Cloud SQL MySQL": {"host": "cloudsql-mysql.googleapis.com", "port": 3306},
    },
    "azure": {
        "Azure SQL": {"host": "sql.database.azure.com", "port": 1433},
        "Azure PostgreSQL": {"host": "postgres.database.azure.com", "port": 5432},
    },
}

_CLOUD_CACHE_PRESETS: dict[str, dict[str, dict]] = {
    "aws": {"ElastiCache Redis": {"host": "redis.cache.amazonaws.com", "port": 6379}},
    "gcp": {"Memorystore Redis": {"host": "redis.memorystore.googleapis.com", "port": 6379}},
    "azure": {"Azure Cache Redis": {"host": "redis.cache.windows.net", "port": 6379}},
}

_CONNECTIVITY_PRESETS: dict[str, dict] = {
    "VPN": {"host": "vpn-endpoint.amazonaws.com", "port": 443},
    "DirectConnect": {"host": "dx-endpoint.amazonaws.com", "port": 443},
    "Internet": {"host": "internet-gateway", "port": 443},
}


def _choose_from(label: str, options: list[str], con: Console) -> str:
    """Present a numbered list and return the user's choice."""
    for idx, opt in enumerate(options, 1):
        con.print(f"  [cyan]{idx}[/]. {opt}")
    choice = Prompt.ask(f"Select {label}", default="1")
    try:
        return options[int(choice) - 1]
    except (ValueError, IndexError):
        return options[0]


def _ask_component(
    label: str,
    comp_type: str,
    presets: dict[str, dict],
    prefix: str,
    region: str,
    con: Console,
) -> dict | None:
    """Ask whether to include a component type and collect details."""
    if not Confirm.ask(f"  Include {label}?", default=True, console=con):
        return None

    con.print(f"\n  [bold]{label} configuration:[/]")
    options = list(presets.keys())
    product = _choose_from(label, options, con)
    preset = presets[product]

    replicas = IntPrompt.ask("  Number of instances", default=2, console=con)
    if replicas < 1:
        replicas = 1

    ha = Confirm.ask("  Enable failover / HA?", default=True, console=con)

    comp_id = f"{prefix}_{comp_type}"
    comp: dict = {
        "id": comp_id,
        "name": f"{product} ({label})",
        "type": comp_type if comp_type != "lb" else "load_balancer",
        "host": preset["host"],
        "port": preset["port"],
        "replicas": replicas,
        "region": {"region": region},
    }
    if ha:
        comp["failover"] = {"enabled": True, "promotion_time_seconds": 30}

    return comp


def _build_dependencies(components: list[dict]) -> list[dict]:
    """Generate dependency edges based on component types present."""
    comp_by_type: dict[str, list[str]] = {}
    for c in components:
        ctype = c["type"]
        comp_by_type.setdefault(ctype, []).append(c["id"])

    deps: list[dict] = []
    lb_ids = comp_by_type.get("load_balancer", [])
    app_ids = comp_by_type.get("app_server", [])
    db_ids = comp_by_type.get("database", [])
    cache_ids = comp_by_type.get("cache", [])
    queue_ids = comp_by_type.get("queue", [])
    storage_ids = comp_by_type.get("storage", [])
    ext_ids = comp_by_type.get("external_api", [])

    # LB -> App
    for lb in lb_ids:
        for a in app_ids:
            deps.append({"source": lb, "target": a, "type": "requires"})

    # App -> DB
    for a in app_ids:
        for db in db_ids:
            deps.append({"source": a, "target": db, "type": "requires"})

    # App -> Cache (optional)
    for a in app_ids:
        for ca in cache_ids:
            deps.append({"source": a, "target": ca, "type": "optional", "weight": 0.7})

    # App -> Queue (async)
    for a in app_ids:
        for q in queue_ids:
            deps.append({"source": a, "target": q, "type": "async", "weight": 0.5})

    # App -> Storage (optional)
    for a in app_ids:
        for st in storage_ids:
            deps.append({"source": a, "target": st, "type": "optional", "weight": 0.5})

    # Cross-env VPN connections: cloud apps -> vpn -> onprem dbs (and vice versa)
    for ext in ext_ids:
        # Connect cloud apps to VPN
        for a in app_ids:
            if _is_cloud_id(a) and not _is_cloud_id(ext):
                continue
            if _is_cloud_id(a):
                deps.append({"source": a, "target": ext, "type": "requires"})
        # Connect VPN to on-prem DBs
        for db in db_ids:
            if not _is_cloud_id(db):
                deps.append({"source": ext, "target": db, "type": "requires"})

    return deps


def _is_cloud_id(comp_id: str) -> bool:
    """Heuristic: cloud component IDs start with cloud_ prefix."""
    return comp_id.startswith("cloud_")


@app.command()
def init(
    output: Path = typer.Option(
        Path("infra.yaml"),
        "--output",
        "-o",
        help="Output path for the generated YAML file.",
    ),
) -> None:
    """Interactive wizard to define your infrastructure and generate a YAML file.

    Walks you through selecting environment type, components, and connectivity
    to produce a FaultRay-compatible infrastructure definition.

    Examples:
        faultray init
        faultray init --output my-hybrid-infra.yaml
    """
    console.print(
        Panel(
            "[bold cyan]FaultRay Init Wizard[/]\n\n"
            "Define your infrastructure interactively.\n"
            "Answer the prompts to generate a ready-to-simulate YAML file.",
            border_style="cyan",
        )
    )

    # ---- 1. Environment type -------------------------------------------------
    console.print("\n[bold]Step 1: Environment Type[/]\n")
    env_options = ["cloud_only", "onprem_only", "hybrid"]
    for idx, opt in enumerate(env_options, 1):
        labels = {
            "cloud_only": "Cloud Only",
            "onprem_only": "On-Premise Only",
            "hybrid": "Hybrid (On-Premise + Cloud)",
        }
        console.print(f"  [cyan]{idx}[/]. {labels[opt]}")

    env_choice = Prompt.ask("Select environment type", default="3")
    try:
        env_type = env_options[int(env_choice) - 1]
    except (ValueError, IndexError):
        env_type = "hybrid"

    console.print(f"  [green]Selected:[/] {env_type}\n")

    # ---- 2. Cloud provider (hybrid / cloud_only) -----------------------------
    cloud_provider: str | None = None
    if env_type in ("cloud_only", "hybrid"):
        console.print("[bold]Step 2: Cloud Provider[/]\n")
        providers = ["aws", "gcp", "azure"]
        for idx, p in enumerate(providers, 1):
            labels = {"aws": "AWS", "gcp": "Google Cloud (GCP)", "azure": "Microsoft Azure"}
            console.print(f"  [cyan]{idx}[/]. {labels[p]}")
        provider_choice = Prompt.ask("Select cloud provider", default="1")
        try:
            cloud_provider = providers[int(provider_choice) - 1]
        except (ValueError, IndexError):
            cloud_provider = "aws"
        console.print(f"  [green]Selected:[/] {cloud_provider}\n")

    # ---- 3. On-premise components --------------------------------------------
    onprem_components: list[dict] = []
    if env_type in ("onprem_only", "hybrid"):
        console.print("[bold]Step 3: On-Premise Components[/]\n")
        region = "onprem-dc1"

        comp = _ask_component("Load Balancer", "load_balancer", _LB_PRESETS, "onprem", region, console)
        if comp:
            onprem_components.append(comp)

        comp = _ask_component("App Server", "app_server", _APP_PRESETS, "onprem", region, console)
        if comp:
            onprem_components.append(comp)

        comp = _ask_component("Database", "database", _DB_PRESETS, "onprem", region, console)
        if comp:
            onprem_components.append(comp)

        comp = _ask_component("Cache", "cache", _CACHE_PRESETS, "onprem", region, console)
        if comp:
            onprem_components.append(comp)

        comp = _ask_component("Message Queue", "queue", _QUEUE_PRESETS, "onprem", region, console)
        if comp:
            onprem_components.append(comp)

        comp = _ask_component("Storage", "storage", _STORAGE_PRESETS, "onprem", region, console)
        if comp:
            onprem_components.append(comp)

        console.print()

    # ---- 4. Cloud components -------------------------------------------------
    cloud_components: list[dict] = []
    if env_type in ("cloud_only", "hybrid") and cloud_provider:
        step = "4" if env_type == "hybrid" else "3"
        console.print(f"[bold]Step {step}: Cloud Components ({cloud_provider.upper()})[/]\n")

        region_defaults = {"aws": "us-east-1", "gcp": "us-central1", "azure": "eastus"}
        region = Prompt.ask("  Cloud region", default=region_defaults.get(cloud_provider, "us-east-1"))

        lb_presets = _CLOUD_LB_PRESETS.get(cloud_provider, {})
        if lb_presets:
            comp = _ask_component("Cloud Load Balancer", "load_balancer", lb_presets, "cloud", region, console)
            if comp:
                cloud_components.append(comp)

        app_presets = _CLOUD_APP_PRESETS.get(cloud_provider, {})
        if app_presets:
            comp = _ask_component("Cloud App Server", "app_server", app_presets, "cloud", region, console)
            if comp:
                if Confirm.ask("  Enable autoscaling?", default=True, console=console):
                    min_r = IntPrompt.ask("  Min replicas", default=2, console=console)
                    max_r = IntPrompt.ask("  Max replicas", default=8, console=console)
                    comp["autoscaling"] = {
                        "enabled": True,
                        "min_replicas": max(1, min_r),
                        "max_replicas": max(max_r, min_r),
                    }
                cloud_components.append(comp)

        db_presets = _CLOUD_DB_PRESETS.get(cloud_provider, {})
        if db_presets:
            comp = _ask_component("Cloud Database", "database", db_presets, "cloud", region, console)
            if comp:
                cloud_components.append(comp)

        cache_presets = _CLOUD_CACHE_PRESETS.get(cloud_provider, {})
        if cache_presets:
            comp = _ask_component("Cloud Cache", "cache", cache_presets, "cloud", region, console)
            if comp:
                cloud_components.append(comp)

        console.print()

    # ---- 5. Connectivity (hybrid only) ---------------------------------------
    connectivity_component: dict | None = None
    if env_type == "hybrid":
        console.print("[bold]Step 5: Cross-Environment Connectivity[/]\n")
        conn_options = list(_CONNECTIVITY_PRESETS.keys())
        conn_type = _choose_from("connectivity method", conn_options, console)
        preset = _CONNECTIVITY_PRESETS[conn_type]
        connectivity_component = {
            "id": "vpn_connection",
            "name": f"{conn_type} Gateway",
            "type": "external_api",
            "host": preset["host"],
            "port": preset["port"],
            "replicas": 2,
            "region": {"region": cloud_provider or "us-east-1"},
            "network": {"rtt_ms": 20.0, "packet_loss_rate": 0.001, "jitter_ms": 5.0},
            "failover": {"enabled": True, "promotion_time_seconds": 15},
        }
        console.print(f"  [green]Selected:[/] {conn_type}\n")

    # ---- 6. Assemble YAML ----------------------------------------------------
    all_components = onprem_components + cloud_components
    if connectivity_component:
        all_components.append(connectivity_component)

    if not all_components:
        console.print("[red]No components selected. Aborting.[/]")
        raise typer.Exit(1)

    dependencies = _build_dependencies(all_components)

    yaml_data: dict = {
        "schema_version": "3.0",
        "components": all_components,
        "dependencies": dependencies,
    }

    # ---- 7. Preview and confirm ----------------------------------------------
    console.print("[bold]Infrastructure Summary[/]\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", style="cyan", width=22)
    table.add_column("Name", width=32)
    table.add_column("Type", width=16)
    table.add_column("Region", width=14)
    table.add_column("Replicas", justify="right", width=10)

    for c in all_components:
        r = c.get("region", {})
        region_str = r.get("region", "") if isinstance(r, dict) else ""
        table.add_row(c["id"], c["name"], c["type"], region_str, str(c.get("replicas", 1)))

    console.print(table)
    console.print(f"\n  Components: [bold]{len(all_components)}[/]  |  Dependencies: [bold]{len(dependencies)}[/]\n")

    if not Confirm.ask("Generate YAML file?", default=True, console=console):
        console.print("[yellow]Aborted.[/]")
        raise typer.Exit(0)

    # ---- 8. Write file -------------------------------------------------------
    if output.exists():
        if not Confirm.ask(f"{output} already exists. Overwrite?", default=True, console=console):
            console.print("[yellow]Aborted.[/]")
            raise typer.Exit(0)

    output.write_text(yaml.dump(yaml_data, default_flow_style=False, sort_keys=False, allow_unicode=True), encoding="utf-8")
    console.print(f"\n[green]Created:[/] {output}")
    console.print(
        f"\n[dim]Next steps:[/]\n"
        f"  1. Edit [cyan]{output}[/] to fine-tune capacity, metrics, and failover settings\n"
        f"  2. Run [cyan]faultray simulate {output}[/] for chaos simulation\n"
        f"  3. Run [cyan]faultray serve[/] to open the web dashboard\n"
    )


# Public alias for external imports
init_wizard = init
