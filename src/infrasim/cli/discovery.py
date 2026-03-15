"""Discovery-related CLI commands: scan, load, show, tf-import, tf-plan."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from infrasim.cli.main import (
    DEFAULT_MODEL_PATH,
    InfraGraph,
    SimulationEngine,
    app,
    console,
    print_infrastructure_summary,
    print_simulation_report,
)
from infrasim.discovery.scanner import scan_local


@app.command()
def scan(
    output: Path = typer.Option(DEFAULT_MODEL_PATH, "--output", "-o", help="Output model file path"),
    hostname: str | None = typer.Option(None, "--hostname", help="Override hostname"),
    prometheus_url: str | None = typer.Option(
        None, "--prometheus-url", help="Prometheus server URL (e.g. http://localhost:9090)"
    ),
    aws: bool = typer.Option(False, "--aws", help="Scan AWS infrastructure via boto3"),
    gcp: bool = typer.Option(False, "--gcp", help="Scan GCP infrastructure via google-cloud libraries"),
    azure: bool = typer.Option(False, "--azure", help="Scan Azure infrastructure via azure-mgmt libraries"),
    k8s: bool = typer.Option(False, "--k8s", help="Scan Kubernetes cluster via kubernetes client"),
    region: str = typer.Option("ap-northeast-1", "--region", help="AWS region (used with --aws)"),
    profile: str | None = typer.Option(None, "--profile", help="AWS profile name (used with --aws)"),
    project: str | None = typer.Option(None, "--project", help="GCP project ID (used with --gcp)"),
    subscription: str | None = typer.Option(None, "--subscription", help="Azure subscription ID (used with --azure)"),
    resource_group: str | None = typer.Option(None, "--resource-group", help="Azure resource group (used with --azure)"),
    context: str | None = typer.Option(None, "--context", help="Kubernetes context (used with --k8s)"),
    namespace: str | None = typer.Option(None, "--namespace", help="Kubernetes namespace (used with --k8s)"),
    save_yaml: Path | None = typer.Option(
        None, "--save-yaml", help="Export discovered model as YAML to this path"
    ),
) -> None:
    """Discover infrastructure and build model.

    Examples:
        # Auto-discover AWS infrastructure
        faultzero scan --aws --region us-east-1

        # Scan AWS with a named profile
        faultzero scan --aws --profile prod --region ap-northeast-1

        # Scan Kubernetes cluster
        faultzero scan --k8s --context prod --namespace default

        # Scan GCP project
        faultzero scan --gcp --project my-project

        # Scan Azure subscription
        faultzero scan --azure --subscription SUB_ID --resource-group my-rg

        # Discover from Prometheus
        faultzero scan --prometheus-url http://localhost:9090

        # Local system scan with custom output
        faultzero scan --output model.json

        # Scan and export as YAML
        faultzero scan --aws --save-yaml infra.yaml
    """
    if aws:
        from infrasim.discovery.aws_scanner import AWSScanner

        console.print(f"[cyan]Scanning AWS infrastructure in {region}...[/]")
        try:
            scanner = AWSScanner(region=region, profile=profile)
            result = scanner.scan()
        except RuntimeError as exc:
            console.print(f"[red]AWS credentials not found.[/]")
            console.print(f"[dim]Try: aws configure[/]")
            console.print(f"[dim]Or: export AWS_PROFILE=myprofile[/]")
            console.print(f"[dim]Error detail: {exc}[/]")
            raise typer.Exit(1)

        graph = result.graph
        console.print(
            f"[green]Discovered {result.components_found} components, "
            f"{result.dependencies_inferred} dependencies "
            f"in {result.scan_duration_seconds:.1f}s[/]"
        )
        if result.warnings:
            for w in result.warnings:
                console.print(f"[yellow]Warning: {w}[/]")
    elif gcp:
        from infrasim.discovery.gcp_scanner import GCPScanner

        if not project:
            console.print("[red]--project is required with --gcp[/]")
            raise typer.Exit(1)

        console.print(f"[cyan]Scanning GCP infrastructure in project {project}...[/]")
        try:
            scanner = GCPScanner(project_id=project)
            result = scanner.scan()
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/]")
            raise typer.Exit(1)

        graph = result.graph
        console.print(
            f"[green]Discovered {result.components_found} components, "
            f"{result.dependencies_inferred} dependencies "
            f"in {result.scan_duration_seconds:.1f}s[/]"
        )
        if result.warnings:
            for w in result.warnings:
                console.print(f"[yellow]Warning: {w}[/]")
    elif azure:
        from infrasim.discovery.azure_scanner import AzureScanner

        if not subscription:
            console.print("[red]--subscription is required with --azure[/]")
            raise typer.Exit(1)

        console.print(f"[cyan]Scanning Azure infrastructure in subscription {subscription}...[/]")
        try:
            scanner = AzureScanner(
                subscription_id=subscription,
                resource_group=resource_group,
            )
            result = scanner.scan()
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/]")
            raise typer.Exit(1)

        graph = result.graph
        console.print(
            f"[green]Discovered {result.components_found} components, "
            f"{result.dependencies_inferred} dependencies "
            f"in {result.scan_duration_seconds:.1f}s[/]"
        )
        if result.warnings:
            for w in result.warnings:
                console.print(f"[yellow]Warning: {w}[/]")
    elif k8s:
        from infrasim.discovery.k8s_scanner import K8sScanner

        ctx_msg = f" (context: {context})" if context else ""
        ns_msg = f" (namespace: {namespace})" if namespace else ""
        console.print(f"[cyan]Scanning Kubernetes cluster{ctx_msg}{ns_msg}...[/]")
        try:
            scanner = K8sScanner(context=context, namespace=namespace)
            result = scanner.scan()
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/]")
            raise typer.Exit(1)

        graph = result.graph
        console.print(
            f"[green]Discovered {result.components_found} components, "
            f"{result.dependencies_inferred} dependencies "
            f"in {result.scan_duration_seconds:.1f}s[/]"
        )
        if result.warnings:
            for w in result.warnings:
                console.print(f"[yellow]Warning: {w}[/]")
    elif prometheus_url:
        from infrasim.discovery.prometheus import PrometheusClient

        console.print(f"[cyan]Discovering infrastructure from Prometheus at {prometheus_url}...[/]")
        client = PrometheusClient(url=prometheus_url)
        graph = asyncio.run(client.discover_components())
    else:
        console.print("[cyan]Scanning local infrastructure...[/]")
        graph = scan_local(hostname=hostname)

    print_infrastructure_summary(graph, console)

    graph.save(output)
    console.print(f"\n[green]Model saved to {output}[/]")

    if save_yaml:
        from infrasim.discovery.aws_scanner import export_yaml

        export_yaml(graph, save_yaml)
        console.print(f"[green]YAML exported to {save_yaml}[/]")


@app.command()
def load(
    yaml_file: Path = typer.Argument(..., help="Path to YAML infrastructure definition"),
    output: Path = typer.Option(DEFAULT_MODEL_PATH, "--output", "-o", help="Output model file path"),
) -> None:
    """Load infrastructure model from a YAML file.

    Examples:
        # Load from YAML
        faultzero load infra.yaml

        # Load and save to custom output path
        faultzero load infra.yaml --output custom-model.json
    """
    from infrasim.model.loader import load_yaml

    console.print(f"[cyan]Loading infrastructure from {yaml_file}...[/]")

    try:
        graph = load_yaml(yaml_file)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)
    except ValueError as exc:
        console.print(f"[red]Invalid YAML: {exc}[/]")
        raise typer.Exit(1)

    print_infrastructure_summary(graph, console)

    graph.save(output)
    console.print(f"\n[green]Model saved to {output}[/]")


@app.command()
def show(
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path"),
) -> None:
    """Show infrastructure model summary.

    Examples:
        # Show default model
        faultzero show

        # Show a specific model file
        faultzero show --model my-model.json
    """
    if not model.exists():
        console.print(f"[red]Model file not found: {model}[/]")
        console.print("[dim]Try: infrasim scan --aws  (auto-discover)[/]")
        console.print("[dim]Or:  infrasim quickstart  (interactive builder)[/]")
        console.print("[dim]Or:  infrasim demo        (demo infrastructure)[/]")
        raise typer.Exit(1)

    graph = InfraGraph.load(model)
    print_infrastructure_summary(graph, console)

    console.print("\n[bold]Components:[/]")
    for comp in graph.components.values():
        deps = graph.get_dependencies(comp.id)
        dep_str = f" -> {', '.join(d.name for d in deps)}" if deps else ""
        util = comp.utilization()
        if util > 80:
            util_color = "red"
        elif util > 60:
            util_color = "yellow"
        else:
            util_color = "green"
        console.print(
            f"  [{util_color}]{comp.name}[/] ({comp.type.value}) "
            f"[dim]replicas={comp.replicas} util={util:.0f}%{dep_str}[/]"
        )


@app.command()
def tf_import(
    tf_state: Path = typer.Option(
        None, "--state", "-s", help="Path to terraform.tfstate file"
    ),
    tf_dir: Path = typer.Option(
        None, "--dir", "-d", help="Terraform project directory (runs 'terraform show -json')"
    ),
    output: Path = typer.Option(DEFAULT_MODEL_PATH, "--output", "-o", help="Output model file path"),
) -> None:
    """Import infrastructure from Terraform state.

    Examples:
        # Import from Terraform state file
        faultzero tf-import --state terraform.tfstate

        # Import by running terraform show in a directory
        faultzero tf-import --dir ./terraform/

        # Import from current directory
        faultzero tf-import

        # Import and save to custom output
        faultzero tf-import --state terraform.tfstate -o my-model.json
    """
    from infrasim.discovery.terraform import load_hcl_directory, load_tf_state_cmd, load_tf_state_file

    if tf_state:
        console.print(f"[cyan]Importing from Terraform state file: {tf_state}...[/]")
        graph = load_tf_state_file(tf_state)
    elif tf_dir:
        console.print(f"[cyan]Running 'terraform show -json' in {tf_dir}...[/]")
        try:
            graph = load_tf_state_cmd(tf_dir)
        except RuntimeError:
            console.print("[yellow]terraform show failed, falling back to HCL file parsing...[/]")
            graph = load_hcl_directory(tf_dir)
    else:
        console.print("[cyan]Running 'terraform show -json' in current directory...[/]")
        try:
            graph = load_tf_state_cmd()
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/]")
            raise typer.Exit(1)

    print_infrastructure_summary(graph, console)

    graph.save(output)
    console.print(f"\n[green]Model saved to {output}[/]")
    console.print(f"Run [cyan]infrasim simulate -m {output}[/] to analyze risks.")


@app.command()
def calibrate(
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file path"),
    prometheus: str | None = typer.Option(None, "--prometheus", help="Prometheus URL (e.g. http://prometheus:9090)"),
    cloudwatch: bool = typer.Option(False, "--cloudwatch", help="Calibrate from AWS CloudWatch metrics"),
    region: str = typer.Option("ap-northeast-1", "--region", help="AWS region (used with --cloudwatch)"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Save calibrated model to this path"),
    yaml_file: Path | None = typer.Option(None, "--yaml", "-y", help="YAML file with infrastructure definition"),
) -> None:
    """Calibrate simulation models using real-world metrics from Prometheus or CloudWatch.

    Examples:
        # Calibrate from Prometheus
        faultzero calibrate --prometheus http://prometheus:9090

        # Calibrate from AWS CloudWatch
        faultzero calibrate --cloudwatch --region us-east-1

        # Calibrate and save to a new file
        faultzero calibrate --prometheus http://prometheus:9090 -o calibrated.json

        # Calibrate a YAML model
        faultzero calibrate --yaml infra.yaml --prometheus http://prometheus:9090
    """
    from rich.table import Table

    from infrasim.cli.main import _load_graph_for_analysis
    from infrasim.discovery.metric_calibrator import MetricCalibrator

    graph = _load_graph_for_analysis(model, yaml_file)
    calibrator = MetricCalibrator(graph)

    if prometheus:
        console.print(f"[cyan]Calibrating from Prometheus at {prometheus}...[/]")
        results = calibrator.calibrate_from_prometheus(prometheus)
    elif cloudwatch:
        console.print(f"[cyan]Calibrating from CloudWatch in {region}...[/]")
        results = calibrator.calibrate_from_cloudwatch(region)
    else:
        console.print("[red]Specify --prometheus URL or --cloudwatch[/]")
        raise typer.Exit(1)

    if not results:
        console.print("[yellow]No calibration results (no matching components found).[/]")
        return

    table = Table(title="Calibration Results", show_header=True)
    table.add_column("Component", style="cyan", width=20)
    table.add_column("Metric", width=16)
    table.add_column("Simulated", justify="right", width=10)
    table.add_column("Actual", justify="right", width=10)
    table.add_column("Deviation", justify="right", width=10)
    table.add_column("Calibrated", justify="center", width=10)

    calibrated_count = 0
    for r in results:
        cal_str = "[green]YES[/]" if r.calibrated else "[dim]no[/]"
        dev_color = "red" if abs(r.deviation_percent) >= 20 else "yellow" if abs(r.deviation_percent) >= 10 else "green"
        table.add_row(
            r.component_id,
            r.metric,
            f"{r.simulated_value:.1f}%",
            f"{r.actual_value:.1f}%",
            f"[{dev_color}]{r.deviation_percent:+.1f}%[/]",
            cal_str,
        )
        if r.calibrated:
            calibrated_count += 1

    console.print()
    console.print(table)
    console.print(f"\n[bold]{calibrated_count}[/] of {len(results)} metrics calibrated.")

    save_path = output or model
    graph.save(save_path)
    console.print(f"[green]Calibrated model saved to {save_path}[/]")


@app.command()
def tf_plan(
    plan_file: Path = typer.Argument(..., help="Path to Terraform plan file (terraform plan -out=plan.out)"),
    tf_dir: Path = typer.Option(
        None, "--dir", "-d", help="Terraform project directory"
    ),
    html: Path | None = typer.Option(None, "--html", help="Export HTML report to this path"),
) -> None:
    """Analyze a Terraform plan for change impact and cascade risks.

    Examples:
        # Analyze a Terraform plan file
        terraform plan -out=plan.out
        faultzero tf-plan plan.out

        # Analyze with HTML report
        faultzero tf-plan plan.out --html impact-report.html

        # Specify Terraform directory
        faultzero tf-plan plan.out --dir ./terraform/
    """
    from infrasim.discovery.terraform import load_tf_plan_cmd

    console.print(f"[cyan]Analyzing Terraform plan: {plan_file}...[/]")

    try:
        result = load_tf_plan_cmd(plan_file=plan_file, tf_dir=tf_dir)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)

    changes = result["changes"]
    after_graph = result["after"]

    # Show changes
    if changes:
        console.print(f"\n[bold]Terraform Changes ({len(changes)}):[/]\n")
        from rich.table import Table

        table = Table(show_header=True)
        table.add_column("Risk", style="bold", width=6)
        table.add_column("Action", width=10)
        table.add_column("Resource", style="cyan")
        table.add_column("Changed Attributes")

        for change in changes:
            risk = change["risk_level"]
            if risk >= 8:
                risk_str = f"[bold red]{risk}/10[/]"
            elif risk >= 5:
                risk_str = f"[yellow]{risk}/10[/]"
            else:
                risk_str = f"[green]{risk}/10[/]"

            actions = "+".join(change["actions"])
            attrs = ", ".join(
                f"{a['attribute']}: {a['before']} \u2192 {a['after']}"
                for a in change["changed_attributes"][:3]
            )
            if len(change["changed_attributes"]) > 3:
                attrs += f" (+{len(change['changed_attributes']) - 3} more)"

            table.add_row(risk_str, actions, change["address"], attrs)

        console.print(table)
    else:
        console.print("[green]No changes detected in plan.[/]")
        return

    # Run simulation on the "after" state
    if len(after_graph.components) > 0:
        console.print(f"\n[cyan]Simulating chaos on planned infrastructure ({len(after_graph.components)} components)...[/]")
        engine = SimulationEngine(after_graph)
        sim_report = engine.run_all_defaults()
        print_simulation_report(sim_report, console)

        if html:
            from infrasim.reporter.html_report import save_html_report

            save_html_report(sim_report, after_graph, html)
            console.print(f"\n[green]HTML report saved to {html}[/]")
