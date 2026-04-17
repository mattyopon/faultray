# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Discovery-related CLI commands: scan, load, show, tf-import, tf-plan."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from faultray.model.components import Component

import typer

from faultray.cli.main import (
    DEFAULT_MODEL_PATH,
    InfraGraph,
    app,
    console,
)
from faultray.reporter.report import print_infrastructure_summary, print_simulation_report
from faultray.simulator.engine import SimulationEngine
from faultray.discovery.scanner import scan_local


def _scan_multi(  # noqa: PLR0912, PLR0913
    console,  # type: ignore[no-untyped-def]
    aws: bool,
    region: str,
    profile: str | None,
    gcp: bool,
    project: str | None,
    azure: bool,
    subscription: str | None,
    resource_group: str | None,
    k8s: bool,
    context: str | None,
    namespace: str | None,
    sakura: bool,
    sakura_token: str | None,
    sakura_secret: str | None,
    sakura_zone: str,
    alibaba: bool,
    alibaba_access_key: str | None,
    alibaba_access_secret: str | None,
    alibaba_vpc: str | None,
    oci: bool,
    oci_compartment: str | None,
    oci_config_file: str | None,
    oci_profile: str,
    onprem: bool,
    netbox_url: str | None,
    netbox_token: str | None,
    cmdb: Path | None,
    nmap_xml: Path | None,
    onprem_region: str,
) -> InfraGraph:
    """Scan multiple cloud providers and merge all discovered resources into one graph."""
    merged = InfraGraph()
    total_components = 0
    total_dependencies = 0

    def _merge(result_graph: InfraGraph, label: str) -> None:
        nonlocal total_components, total_dependencies
        added_c = 0
        for comp in result_graph.components.values():
            merged.add_component(comp)
            added_c += 1
        added_d = 0
        for edge in result_graph.all_dependency_edges():
            merged.add_dependency(edge)
            added_d += 1
        total_components += added_c
        total_dependencies += added_d
        console.print(
            f"  [green]{label}: +{added_c} components, +{added_d} dependencies[/]"
        )

    console.print("[cyan]Multi-cloud scan started...[/]")

    if aws:
        from faultray.discovery.aws_scanner import AWSScanner
        console.print(f"  [dim]Scanning AWS ({region})...[/]")
        try:
            r = AWSScanner(region=region, profile=profile).scan()
            _merge(r.graph, "AWS")
            for w in r.warnings:
                console.print(f"  [yellow]AWS Warning: {w}[/]")
        except Exception as exc:
            console.print(f"  [yellow]AWS scan skipped: {exc}[/]")

    if gcp and project:
        from faultray.discovery.gcp_scanner import GCPScanner
        console.print(f"  [dim]Scanning GCP (project={project})...[/]")
        try:
            r = GCPScanner(project_id=project).scan()
            _merge(r.graph, "GCP")
            for w in r.warnings:
                console.print(f"  [yellow]GCP Warning: {w}[/]")
        except Exception as exc:
            console.print(f"  [yellow]GCP scan skipped: {exc}[/]")

    if azure and subscription:
        from faultray.discovery.azure_scanner import AzureScanner
        console.print(f"  [dim]Scanning Azure (subscription={subscription})...[/]")
        try:
            r = AzureScanner(subscription_id=subscription, resource_group=resource_group).scan()
            _merge(r.graph, "Azure")
            for w in r.warnings:
                console.print(f"  [yellow]Azure Warning: {w}[/]")
        except Exception as exc:
            console.print(f"  [yellow]Azure scan skipped: {exc}[/]")

    if k8s:
        from faultray.discovery.k8s_scanner import K8sScanner
        console.print("  [dim]Scanning Kubernetes...[/]")
        try:
            r = K8sScanner(context=context, namespace=namespace).scan()
            _merge(r.graph, "Kubernetes")
            for w in r.warnings:
                console.print(f"  [yellow]K8s Warning: {w}[/]")
        except Exception as exc:
            console.print(f"  [yellow]Kubernetes scan skipped: {exc}[/]")

    if sakura and sakura_token and sakura_secret:
        from faultray.discovery.sakura_scanner import SakuraScanner
        console.print(f"  [dim]Scanning Sakura Cloud (zone={sakura_zone})...[/]")
        try:
            r = SakuraScanner(token=sakura_token, secret=sakura_secret, zone=sakura_zone).scan()
            _merge(r.graph, "Sakura Cloud")
            for w in r.warnings:
                console.print(f"  [yellow]Sakura Warning: {w}[/]")
        except Exception as exc:
            console.print(f"  [yellow]Sakura scan skipped: {exc}[/]")

    if alibaba and alibaba_access_key and alibaba_access_secret:
        from faultray.discovery.alibaba_scanner import AlibabaScanner
        console.print(f"  [dim]Scanning Alibaba Cloud (region={region})...[/]")
        try:
            r = AlibabaScanner(
                access_key_id=alibaba_access_key,
                access_key_secret=alibaba_access_secret,
                region=region,
                vpc_id=alibaba_vpc,
            ).scan()
            _merge(r.graph, "Alibaba Cloud")
            for w in r.warnings:
                console.print(f"  [yellow]Alibaba Warning: {w}[/]")
        except Exception as exc:
            console.print(f"  [yellow]Alibaba scan skipped: {exc}[/]")

    if oci and oci_compartment:
        from faultray.discovery.oci_scanner import OCIScanner
        console.print(f"  [dim]Scanning Oracle Cloud (compartment={oci_compartment})...[/]")
        try:
            r = OCIScanner(
                compartment_id=oci_compartment,
                config_file=oci_config_file,
                profile=oci_profile,
            ).scan()
            _merge(r.graph, "Oracle Cloud")
            for w in r.warnings:
                console.print(f"  [yellow]OCI Warning: {w}[/]")
        except Exception as exc:
            console.print(f"  [yellow]OCI scan skipped: {exc}[/]")

    if onprem:
        from faultray.discovery.onprem_scanner import OnPremScanner
        if netbox_url and netbox_token:
            console.print(f"  [dim]Scanning on-premises via NetBox ({netbox_url})...[/]")
            try:
                r = OnPremScanner.from_netbox(netbox_url, netbox_token, onprem_region).scan()
                _merge(r.graph, "On-Premises (NetBox)")
                for w in r.warnings:
                    console.print(f"  [yellow]OnPrem Warning: {w}[/]")
            except Exception as exc:
                console.print(f"  [yellow]NetBox scan skipped: {exc}[/]")
        elif cmdb:
            console.print(f"  [dim]Importing CMDB from {cmdb}...[/]")
            try:
                if cmdb.suffix.lower() == ".json":
                    r = OnPremScanner.from_cmdb_json(cmdb, onprem_region).scan()
                else:
                    r = OnPremScanner.from_cmdb_csv(cmdb, onprem_region).scan()
                _merge(r.graph, "On-Premises (CMDB)")
                for w in r.warnings:
                    console.print(f"  [yellow]CMDB Warning: {w}[/]")
            except Exception as exc:
                console.print(f"  [yellow]CMDB import skipped: {exc}[/]")
        elif nmap_xml:
            console.print(f"  [dim]Importing nmap results from {nmap_xml}...[/]")
            try:
                r = OnPremScanner.from_nmap_xml(nmap_xml, onprem_region).scan()
                _merge(r.graph, "On-Premises (nmap)")
                for w in r.warnings:
                    console.print(f"  [yellow]nmap Warning: {w}[/]")
            except Exception as exc:
                console.print(f"  [yellow]nmap import skipped: {exc}[/]")

    console.print(
        f"[green]Multi-cloud scan complete: "
        f"{total_components} components, {total_dependencies} dependencies[/]"
    )
    return merged


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
    sakura: bool = typer.Option(False, "--sakura", help="Scan Sakura Cloud infrastructure"),
    alibaba: bool = typer.Option(False, "--alibaba", help="Scan Alibaba Cloud (Aliyun) infrastructure"),
    oci: bool = typer.Option(False, "--oci", help="Scan Oracle Cloud Infrastructure"),
    onprem: bool = typer.Option(False, "--onprem", help="Discover on-premises infrastructure"),
    multi: bool = typer.Option(False, "--multi", help="Scan multiple clouds and merge into one graph"),
    region: str = typer.Option("ap-northeast-1", "--region", help="AWS/Alibaba region"),
    profile: str | None = typer.Option(None, "--profile", help="AWS profile name (used with --aws)"),
    project: str | None = typer.Option(None, "--project", help="GCP project ID (used with --gcp)"),
    subscription: str | None = typer.Option(None, "--subscription", help="Azure subscription ID (used with --azure)"),
    resource_group: str | None = typer.Option(None, "--resource-group", help="Azure resource group (used with --azure)"),
    context: str | None = typer.Option(None, "--context", help="Kubernetes context (used with --k8s)"),
    namespace: str | None = typer.Option(None, "--namespace", help="Kubernetes namespace (used with --k8s)"),
    # Sakura Cloud options
    sakura_token: str | None = typer.Option(None, "--token", help="Sakura Cloud API token (used with --sakura)"),
    sakura_secret: str | None = typer.Option(None, "--secret", help="Sakura Cloud API secret (used with --sakura)"),
    sakura_zone: str = typer.Option("tk1v", "--zone", help="Sakura Cloud zone (used with --sakura)"),
    # Alibaba Cloud options
    alibaba_access_key: str | None = typer.Option(None, "--access-key", help="Alibaba Cloud AccessKey ID"),
    alibaba_access_secret: str | None = typer.Option(None, "--access-secret", help="Alibaba Cloud AccessKey Secret"),
    alibaba_vpc: str | None = typer.Option(None, "--vpc", help="Alibaba Cloud VPC ID filter"),
    # OCI options
    oci_compartment: str | None = typer.Option(None, "--compartment", help="OCI Compartment OCID (used with --oci)"),
    oci_config_file: str | None = typer.Option(None, "--oci-config", help="OCI config file path"),
    oci_profile: str = typer.Option("DEFAULT", "--oci-profile", help="OCI config profile"),
    # On-premises options
    netbox_url: str | None = typer.Option(None, "--netbox-url", help="NetBox URL (used with --onprem)"),
    netbox_token: str | None = typer.Option(None, "--netbox-token", help="NetBox API token"),
    cmdb: Path | None = typer.Option(None, "--cmdb", help="CMDB inventory file (CSV or JSON)"),
    nmap_xml: Path | None = typer.Option(None, "--nmap-xml", help="nmap XML scan result file"),
    onprem_region: str = typer.Option("onprem", "--onprem-region", help="Default region label for on-prem resources"),
    save_yaml: Path | None = typer.Option(
        None, "--save-yaml", help="Export discovered model as YAML to this path"
    ),
    infer_hidden: bool = typer.Option(
        False, "--infer-hidden", help="Run ML dependency inference to detect hidden dependencies"
    ),
    infer_confidence: float = typer.Option(
        0.7, "--infer-confidence", help="Minimum confidence threshold for inferred dependencies (0.0-1.0)"
    ),
) -> None:
    """Discover infrastructure and build model.

    Examples:
        # Auto-discover AWS infrastructure
        faultray scan --aws --region us-east-1

        # Scan AWS with a named profile
        faultray scan --aws --profile prod --region ap-northeast-1

        # Scan Kubernetes cluster
        faultray scan --k8s --context prod --namespace default

        # Scan GCP project
        faultray scan --gcp --project my-project

        # Scan Azure subscription
        faultray scan --azure --subscription SUB_ID --resource-group my-rg

        # Scan Sakura Cloud
        faultray scan --sakura --token TOKEN --secret SECRET --zone tk1v

        # Scan Alibaba Cloud
        faultray scan --alibaba --access-key KEY --access-secret SECRET --region cn-hangzhou

        # Scan Oracle Cloud
        faultray scan --oci --compartment ocid1.compartment.oc1..xxx

        # Discover on-premises via NetBox
        faultray scan --onprem --netbox-url http://netbox.local --netbox-token TOKEN

        # Discover on-premises from CMDB CSV
        faultray scan --onprem --cmdb inventory.csv

        # Discover on-premises from nmap XML
        faultray scan --onprem --nmap-xml scan.xml

        # Multi-cloud scan (merge all discovered resources)
        faultray scan --multi --aws --region us-east-1 --gcp --project my-project

        # Discover from Prometheus
        faultray scan --prometheus-url http://localhost:9090

        # Local system scan with custom output
        faultray scan --output model.json

        # Scan and export as YAML
        faultray scan --aws --save-yaml infra.yaml

        # Scan with ML-based hidden dependency inference
        faultray scan --aws --infer-hidden --infer-confidence 0.6
    """
    # --multi mode: scan multiple clouds and merge all graphs
    if multi:
        graph = _scan_multi(
            console=console,
            aws=aws, region=region, profile=profile,
            gcp=gcp, project=project,
            azure=azure, subscription=subscription, resource_group=resource_group,
            k8s=k8s, context=context, namespace=namespace,
            sakura=sakura, sakura_token=sakura_token, sakura_secret=sakura_secret,
            sakura_zone=sakura_zone,
            alibaba=alibaba, alibaba_access_key=alibaba_access_key,
            alibaba_access_secret=alibaba_access_secret, alibaba_vpc=alibaba_vpc,
            oci=oci, oci_compartment=oci_compartment, oci_config_file=oci_config_file,
            oci_profile=oci_profile,
            onprem=onprem, netbox_url=netbox_url, netbox_token=netbox_token,
            cmdb=cmdb, nmap_xml=nmap_xml, onprem_region=onprem_region,
        )
    elif aws:
        from faultray.discovery.aws_scanner import AWSScanner

        console.print(f"[cyan]Scanning AWS infrastructure in {region}...[/]")
        try:
            scanner = AWSScanner(region=region, profile=profile)
            result = scanner.scan()
        except RuntimeError as exc:
            console.print("[red]AWS credentials not found.[/]")
            console.print("[dim]Try: aws configure[/]")
            console.print("[dim]Or: export AWS_PROFILE=myprofile[/]")
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
        from faultray.discovery.gcp_scanner import GCPScanner

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
        from faultray.discovery.azure_scanner import AzureScanner

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
        from faultray.discovery.k8s_scanner import K8sScanner

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
    elif sakura:
        from faultray.discovery.sakura_scanner import SakuraScanner

        if not sakura_token or not sakura_secret:
            console.print("[red]--token and --secret are required with --sakura[/]")
            raise typer.Exit(1)

        console.print(f"[cyan]Scanning Sakura Cloud infrastructure in zone {sakura_zone}...[/]")
        try:
            scanner = SakuraScanner(token=sakura_token, secret=sakura_secret, zone=sakura_zone)
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
    elif alibaba:
        from faultray.discovery.alibaba_scanner import AlibabaScanner

        if not alibaba_access_key or not alibaba_access_secret:
            console.print("[red]--access-key and --access-secret are required with --alibaba[/]")
            raise typer.Exit(1)

        console.print(f"[cyan]Scanning Alibaba Cloud infrastructure in region {region}...[/]")
        try:
            scanner = AlibabaScanner(
                access_key_id=alibaba_access_key,
                access_key_secret=alibaba_access_secret,
                region=region,
                vpc_id=alibaba_vpc,
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
    elif oci:
        from faultray.discovery.oci_scanner import OCIScanner

        if not oci_compartment:
            console.print("[red]--compartment is required with --oci[/]")
            raise typer.Exit(1)

        console.print(f"[cyan]Scanning Oracle Cloud infrastructure in compartment {oci_compartment}...[/]")
        try:
            scanner = OCIScanner(
                compartment_id=oci_compartment,
                config_file=oci_config_file,
                profile=oci_profile,
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
    elif onprem:
        from faultray.discovery.onprem_scanner import OnPremScanner

        if netbox_url:
            if not netbox_token:
                console.print("[red]--netbox-token is required with --netbox-url[/]")
                raise typer.Exit(1)
            console.print(f"[cyan]Discovering on-premises infrastructure from NetBox at {netbox_url}...[/]")
            scanner = OnPremScanner.from_netbox(
                url=netbox_url,
                token=netbox_token,
                default_region=onprem_region,
            )
        elif cmdb:
            suffix = cmdb.suffix.lower()
            if suffix == ".json":
                console.print(f"[cyan]Importing CMDB from JSON: {cmdb}...[/]")
                scanner = OnPremScanner.from_cmdb_json(cmdb, default_region=onprem_region)
            else:
                console.print(f"[cyan]Importing CMDB from CSV: {cmdb}...[/]")
                scanner = OnPremScanner.from_cmdb_csv(cmdb, default_region=onprem_region)
        elif nmap_xml:
            console.print(f"[cyan]Importing nmap scan results from: {nmap_xml}...[/]")
            scanner = OnPremScanner.from_nmap_xml(nmap_xml, default_region=onprem_region)
        else:
            console.print("[red]--onprem requires one of: --netbox-url, --cmdb, or --nmap-xml[/]")
            raise typer.Exit(1)

        try:
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
        from faultray.discovery.prometheus import PrometheusClient

        console.print(f"[cyan]Discovering infrastructure from Prometheus at {prometheus_url}...[/]")
        client = PrometheusClient(url=prometheus_url)
        graph = asyncio.run(client.discover_components())
    else:
        console.print("[cyan]Scanning local infrastructure...[/]")
        graph = scan_local(hostname=hostname)

    if infer_hidden:
        from faultray.discovery.ml_dependency_inference import DependencyInferenceEngine

        console.print("[cyan]Running ML dependency inference...[/]")
        engine = DependencyInferenceEngine()
        inferred = engine.infer_all(graph)
        if inferred:
            added = engine.apply_inferred(graph, inferred, min_confidence=infer_confidence)
            console.print(
                f"[green]ML inference: {len(inferred)} candidates found, "
                f"{added} dependencies added (confidence >= {infer_confidence})[/]"
            )
            for dep in inferred[:5]:
                style = "green" if dep.confidence >= infer_confidence else "dim"
                console.print(
                    f"  [{style}]{dep.source_id} -> {dep.target_id} "
                    f"(confidence={dep.confidence:.2f}, method={dep.inference_method})[/]"
                )
            if len(inferred) > 5:
                console.print(f"  [dim]... and {len(inferred) - 5} more[/]")
        else:
            console.print("[yellow]No hidden dependencies inferred.[/]")

    print_infrastructure_summary(graph, console)

    graph.save(output)
    console.print(f"\n[green]Model saved to {output}[/]")

    if save_yaml:
        from faultray.discovery.aws_scanner import export_yaml

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
        faultray load infra.yaml

        # Load and save to custom output path
        faultray load infra.yaml --output custom-model.json
    """
    from faultray.model.loader import load_yaml

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
        faultray show

        # Show a specific model file
        faultray show --model my-model.json
    """
    if not model.exists():
        console.print(f"[red]Model file not found: {model}[/]")
        console.print("[dim]Try: faultray scan --aws  (auto-discover)[/]")
        console.print("[dim]Or:  faultray quickstart  (interactive builder)[/]")
        console.print("[dim]Or:  faultray demo        (demo infrastructure)[/]")
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
        faultray tf-import --state terraform.tfstate

        # Import by running terraform show in a directory
        faultray tf-import --dir ./terraform/

        # Import from current directory
        faultray tf-import

        # Import and save to custom output
        faultray tf-import --state terraform.tfstate -o my-model.json
    """
    from faultray.discovery.terraform import load_hcl_directory, load_tf_state_cmd, load_tf_state_file

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
    console.print(f"Run [cyan]faultray simulate -m {output}[/] to analyze risks.")


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
        faultray calibrate --prometheus http://prometheus:9090

        # Calibrate from AWS CloudWatch
        faultray calibrate --cloudwatch --region us-east-1

        # Calibrate and save to a new file
        faultray calibrate --prometheus http://prometheus:9090 -o calibrated.json

        # Calibrate a YAML model
        faultray calibrate --yaml infra.yaml --prometheus http://prometheus:9090
    """
    from rich.table import Table

    from faultray.cli.main import _load_graph_for_analysis
    from faultray.discovery.metric_calibrator import MetricCalibrator

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
        faultray tf-plan plan.out

        # Analyze with HTML report
        faultray tf-plan plan.out --html impact-report.html

        # Specify Terraform directory
        faultray tf-plan plan.out --dir ./terraform/
    """
    from faultray.discovery.terraform import load_tf_plan_cmd

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
        print_simulation_report(sim_report, console, graph=after_graph)

        if html:
            from faultray.reporter.html_report import save_html_report

            save_html_report(sim_report, after_graph, html)
            console.print(f"\n[green]HTML report saved to {html}[/]")


@app.command(name="iac-gen")
def iac_gen(
    model: Path = typer.Argument(
        ..., help="FaultRay model file (JSON) to generate IaC from"
    ),
    provider: str = typer.Option(
        "aws",
        "--provider",
        "-p",
        help="Target IaC provider: aws, gcp, azure, generic",
    ),
    output_dir: Path = typer.Option(
        Path("terraform"),
        "--output",
        "-o",
        help="Output directory for generated Terraform HCL files",
    ),
    mode: str = typer.Option(
        "remediate",
        "--mode",
        "-m",
        help="Generation mode: 'remediate' (fix issues) or 'export' (current state as IaC)",
    ),
    target_score: float = typer.Option(
        90.0,
        "--target-score",
        help="Target resilience score for remediation mode (0-100)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be generated without writing files",
    ),
) -> None:
    """Generate Terraform IaC from a FaultRay infrastructure model.

    Two modes are available:

    \\b
    remediate (default): Generate Terraform that fixes detected infrastructure issues.
      Equivalent to the existing 'faultray auto-fix' workflow.

    \\b
    export: Generate Terraform that represents the current infrastructure state.
      Useful for importing discovered infrastructure into version-controlled IaC.

    Examples:
        # Generate remediation Terraform for AWS
        faultray iac-gen faultray-model.json --provider aws --output terraform/

        # Export current state as Terraform (IaC import workflow)
        faultray iac-gen faultray-model.json --mode export --output terraform/

        # Dry-run: preview without writing files
        faultray iac-gen faultray-model.json --dry-run

        # Target a higher score
        faultray iac-gen faultray-model.json --target-score 95
    """
    if not model.exists():
        console.print(f"[red]Model file not found: {model}[/]")
        raise typer.Exit(1)

    graph = InfraGraph.load(model)
    console.print(
        f"[cyan]Loaded model: {len(graph.components)} components, "
        f"resilience score: {graph.resilience_score():.1f}[/]"
    )

    if mode == "remediate":
        _iac_gen_remediate(graph, output_dir, target_score, dry_run, provider)
    elif mode == "export":
        _iac_gen_export(graph, output_dir, dry_run, provider)
    else:
        console.print(f"[red]Unknown mode '{mode}'. Use 'remediate' or 'export'.[/]")
        raise typer.Exit(1)


def _iac_gen_remediate(
    graph: "InfraGraph",
    output_dir: Path,
    target_score: float,
    dry_run: bool,
    provider: str,
) -> None:
    """Generate remediation Terraform from FaultRay analysis."""
    from faultray.remediation.iac_generator import IaCGenerator

    generator = IaCGenerator(graph)
    plan = generator.generate(target_score=target_score)

    if not plan.files:
        console.print("[green]No remediation needed — infrastructure already meets target score.[/]")
        return

    if dry_run:
        console.print("[cyan]Dry run — no files written.[/]")
        console.print(generator.dry_run(plan))
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    files_written = 0

    for f in plan.files:
        file_path = output_dir / f.path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(f.content, encoding="utf-8")
        files_written += 1

    # Write README
    readme_path = output_dir / "README.md"
    readme_path.write_text(plan.readme_content, encoding="utf-8")

    console.print(f"[green]Remediation IaC written: {files_written} files in {output_dir}/[/]")
    console.print(
        f"[green]Expected score improvement: "
        f"{plan.expected_score_before:.1f} -> {plan.expected_score_after:.1f} "
        f"(+{plan.expected_score_after - plan.expected_score_before:.1f})[/]"
    )
    console.print(f"[green]Estimated monthly cost: ${plan.total_monthly_cost:.2f}[/]")
    console.print(f"[dim]Run: cd {output_dir} && terraform init && terraform plan[/]")


def _iac_gen_export(
    graph: "InfraGraph",
    output_dir: Path,
    dry_run: bool,
    provider: str,
) -> None:
    """Export current infrastructure state as Terraform HCL (IaC import workflow)."""
    import re

    def _safe_id(name: str) -> str:
        """Convert a component name/id to a safe Terraform resource identifier."""
        return re.sub(r"[^a-zA-Z0-9_]", "_", name).lower().strip("_")

    lines: list[str] = [
        f'# Generated by FaultRay iac-gen (mode=export, provider={provider})',
        f'# Components: {len(graph.components)}',
        '',
        'terraform {',
        '  required_version = ">= 1.0"',
        '}',
        '',
    ]

    # Add provider block
    if provider == "aws":
        lines += [
            'provider "aws" {',
            '  # Configure via environment: AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY',
            '}',
            '',
        ]
    elif provider == "gcp":
        lines += [
            'provider "google" {',
            '  # Configure via environment: GOOGLE_CREDENTIALS, GOOGLE_PROJECT, GOOGLE_REGION',
            '}',
            '',
        ]
    elif provider == "azure":
        lines += [
            'provider "azurerm" {',
            '  features {}',
            '  # Configure via environment: ARM_SUBSCRIPTION_ID, ARM_CLIENT_ID, etc.',
            '}',
            '',
        ]

    resource_count = 0

    for comp_id, comp in graph.components.items():
        tf_id = _safe_id(comp_id)
        comp_type = comp.type.value

        # Generate appropriate resource block per provider and component type
        if provider == "aws":
            block = _aws_export_block(tf_id, comp, comp_type)
        elif provider == "gcp":
            block = _gcp_export_block(tf_id, comp, comp_type)
        elif provider == "azure":
            block = _azure_export_block(tf_id, comp, comp_type)
        else:
            block = _generic_export_block(tf_id, comp, comp_type)

        if block:
            lines.append(block)
            resource_count += 1

    content = "\n".join(lines)

    if dry_run:
        console.print("[cyan]Dry run — no files written.[/]")
        console.print(content[:3000] + ("..." if len(content) > 3000 else ""))
        console.print(f"\n[dim]{resource_count} resources would be generated.[/]")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / "main.tf"
    out_file.write_text(content, encoding="utf-8")

    console.print(f"[green]Exported {resource_count} resources to {out_file}[/]")
    console.print(
        "[dim]Note: Review and adjust the generated HCL before running 'terraform import'.[/]"
    )


def _aws_export_block(tf_id: str, comp: "Component", comp_type: str) -> str:
    """Generate an AWS Terraform resource block for a component."""
    import json as _json

    name = comp.name
    private_ip = _json.dumps(comp.host) if comp.host else "null"

    if comp_type == "app_server":
        return (
            f'# {name}\n'
            f'resource "aws_instance" "{tf_id}" {{\n'
            f'  ami           = "ami-REPLACE_ME"  # Replace with actual AMI\n'
            f'  instance_type = "t3.medium"\n'
            f'  private_ip    = {private_ip}\n'
            f'\n'
            f'  tags = {{\n'
            f'    Name = {_json.dumps(name)}\n'
            f'  }}\n'
            f'}}\n'
        )
    elif comp_type == "database":
        return (
            f'# {name}\n'
            f'resource "aws_db_instance" "{tf_id}" {{\n'
            f'  identifier        = {_json.dumps(tf_id)}\n'
            f'  engine            = "mysql"\n'
            f'  engine_version    = "8.0"\n'
            f'  instance_class    = "db.t3.medium"\n'
            f'  allocated_storage = 20\n'
            f'  port              = {comp.port or 3306}\n'
            f'  multi_az          = {str(comp.replicas > 1).lower()}\n'
            f'  skip_final_snapshot = true\n'
            f'\n'
            f'  tags = {{\n'
            f'    Name = {_json.dumps(name)}\n'
            f'  }}\n'
            f'}}\n'
        )
    elif comp_type == "cache":
        return (
            f'# {name}\n'
            f'resource "aws_elasticache_cluster" "{tf_id}" {{\n'
            f'  cluster_id        = {_json.dumps(tf_id[:20])}\n'
            f'  engine            = "redis"\n'
            f'  node_type         = "cache.t3.micro"\n'
            f'  num_cache_nodes   = {comp.replicas}\n'
            f'  port              = {comp.port or 6379}\n'
            f'}}\n'
        )
    elif comp_type == "load_balancer":
        return (
            f'# {name}\n'
            f'resource "aws_lb" "{tf_id}" {{\n'
            f'  name               = {_json.dumps(tf_id[:32])}\n'
            f'  internal           = false\n'
            f'  load_balancer_type = "application"\n'
            f'}}\n'
        )
    elif comp_type == "storage":
        return (
            f'# {name}\n'
            f'resource "aws_s3_bucket" "{tf_id}" {{\n'
            f'  bucket = {_json.dumps(tf_id.replace("_", "-"))}\n'
            f'\n'
            f'  tags = {{\n'
            f'    Name = {_json.dumps(name)}\n'
            f'  }}\n'
            f'}}\n'
        )
    return ""


def _gcp_export_block(tf_id: str, comp: "Component", comp_type: str) -> str:
    """Generate a GCP Terraform resource block for a component."""
    import json as _json

    name = comp.name
    if comp_type == "app_server":
        return (
            f'# {name}\n'
            f'resource "google_compute_instance" "{tf_id}" {{\n'
            f'  name         = {_json.dumps(tf_id.replace("_", "-")[:63])}\n'
            f'  machine_type = "e2-medium"\n'
            f'  zone         = "us-central1-a"\n'
            f'\n'
            f'  boot_disk {{\n'
            f'    initialize_params {{\n'
            f'      image = "debian-cloud/debian-11"\n'
            f'    }}\n'
            f'  }}\n'
            f'\n'
            f'  network_interface {{\n'
            f'    network = "default"\n'
            f'  }}\n'
            f'}}\n'
        )
    elif comp_type == "database":
        return (
            f'# {name}\n'
            f'resource "google_sql_database_instance" "{tf_id}" {{\n'
            f'  name             = {_json.dumps(tf_id.replace("_", "-")[:63])}\n'
            f'  database_version = "MYSQL_8_0"\n'
            f'  region           = "us-central1"\n'
            f'\n'
            f'  settings {{\n'
            f'    tier = "db-f1-micro"\n'
            f'  }}\n'
            f'}}\n'
        )
    return ""


def _azure_export_block(tf_id: str, comp: "Component", comp_type: str) -> str:
    """Generate an Azure Terraform resource block for a component."""
    import json as _json

    name = comp.name
    if comp_type == "app_server":
        return (
            f'# {name}\n'
            f'resource "azurerm_linux_virtual_machine" "{tf_id}" {{\n'
            f'  name                = {_json.dumps(tf_id[:15])}\n'
            f'  resource_group_name = "rg-faultray-export"\n'
            f'  location            = "japaneast"\n'
            f'  size                = "Standard_B2s"\n'
            f'  admin_username      = "adminuser"\n'
            f'\n'
            f'  os_disk {{\n'
            f'    caching              = "ReadWrite"\n'
            f'    storage_account_type = "Standard_LRS"\n'
            f'  }}\n'
            f'\n'
            f'  source_image_reference {{\n'
            f'    publisher = "Canonical"\n'
            f'    offer     = "0001-com-ubuntu-server-jammy"\n'
            f'    sku       = "22_04-lts"\n'
            f'    version   = "latest"\n'
            f'  }}\n'
            f'}}\n'
        )
    return ""


def _generic_export_block(tf_id: str, comp: "Component", comp_type: str) -> str:
    """Generate a generic Terraform null_resource block for documentation."""
    import json as _json

    return (
        f'# {comp.name} ({comp_type})\n'
        f'# host={comp.host or "unknown"}, port={comp.port}, replicas={comp.replicas}\n'
        f'resource "null_resource" "{tf_id}" {{\n'
        f'  triggers = {{\n'
        f'    name = {_json.dumps(comp.name)}\n'
        f'    type = {_json.dumps(comp_type)}\n'
        f'    host = {_json.dumps(comp.host or "")}\n'
        f'  }}\n'
        f'}}\n'
    )


@app.command("gas-scan")
def gas_scan_cmd(
    credentials: str | None = typer.Option(
        None,
        "--credentials",
        "-c",
        help="Path to Google service account JSON credentials file.",
    ),
    org: str = typer.Option(
        "Example Corp",
        "--org",
        "-o",
        help="Organization name for the report.",
    ),
    domain: str | None = typer.Option(
        None,
        "--domain",
        "-d",
        help="Google Workspace domain (e.g. example.co.jp). Used with --credentials.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output results as JSON.",
    ),
) -> None:
    """Scan Google Workspace for GAS scripts and personalization risks.

    Without --credentials, runs in demo mode with realistic sample data.

    Examples:

    \b
        faultray gas-scan
        faultray gas-scan --credentials creds.json --domain example.co.jp
        faultray gas-scan --json
        faultray gas-scan --org "サングローブ"
    """
    import json as _json

    from faultray.discovery.gas_scanner import GASScanner
    from faultray.discovery.personalization_analyzer import PersonalizationAnalyzer

    scanner = GASScanner(credentials_path=credentials, domain=domain)

    if credentials:
        console.print("[cyan]Google Workspace GAS スキャン開始...[/]")
        try:
            result = scanner.scan()
        except ImportError as exc:
            console.print(f"[red]依存ライブラリが不足しています: {exc}[/]")
            console.print(
                "[yellow]pip install google-api-python-client google-auth を実行してください[/]"
            )
            raise typer.Exit(1)
        except RuntimeError as exc:
            console.print(f"[red]{exc}[/]")
            raise typer.Exit(1)
    else:
        if not json_output:
            console.print(
                "[yellow]--credentials が指定されていません。デモモードで実行します。[/]"
            )
        result = scanner.scan_demo(org_name=org)

    analyzer = PersonalizationAnalyzer()
    report = analyzer.analyze_gas(result)

    if json_output:
        output = {
            "scan": result.to_dict(),
            "personalization_report": report.to_dict(),
        }
        console.print_json(_json.dumps(output, ensure_ascii=False, indent=2))
        return

    # Rich human-readable output
    console.print()
    console.print(f"[bold cyan]╔══ GAS スキャン結果: {result.organization} ══╗[/]")
    console.print(
        f"  スクリプト総数: [bold]{result.total_scripts}[/]  "
        f"[red]Critical: {result.critical_count}[/]  "
        f"[yellow]Warning: {result.warning_count}[/]  "
        f"[green]OK: {result.ok_count}[/]"
    )
    console.print()

    if result.critical_count:
        console.print("[bold red]■ CRITICAL リスク[/]")
        for risk in result.risks:
            if risk.risk_level != "critical":
                continue
            script = next((s for s in result.scripts if s.id == risk.script_id), None)
            if script:
                console.print(
                    f"  [red]●[/] {script.name}  "
                    f"オーナー: {script.owner_name} ({script.owner_status})  "
                    f"スコア: {risk.risk_score:.0f}/10"
                )
                for reason in risk.reasons:
                    console.print(f"      → {reason}")
        console.print()

    if result.warning_count:
        console.print("[bold yellow]■ WARNING リスク[/]")
        for risk in result.risks:
            if risk.risk_level != "warning":
                continue
            script = next((s for s in result.scripts if s.id == risk.script_id), None)
            if script:
                console.print(
                    f"  [yellow]●[/] {script.name}  "
                    f"オーナー: {script.owner_name}  "
                    f"スコア: {risk.risk_score:.0f}/10"
                )
        console.print()

    console.print("[bold]■ 属人化レポート[/]")
    console.print(f"  関係者人数: {report.total_people}")
    console.print(
        f"  バスファクター 1 (1人退職で崩壊): [bold red]{report.bus_factor_1}[/] スクリプト"
    )
    console.print(
        f"  バスファクター 2 (2人退職で崩壊): [yellow]{report.bus_factor_2}[/] スクリプト"
    )
    console.print()

    if report.improvement_actions:
        console.print("[bold]■ 改善アクション[/]")
        priority_color = {"critical": "red", "high": "yellow", "medium": "blue", "low": "dim"}
        for action in report.improvement_actions:
            color = priority_color.get(action.get("priority", "low"), "white")
            console.print(
                f"  [{color}][{action['priority'].upper()}][/]  {action['title']}"
            )
            console.print(f"    {action['description']}")
        console.print()

    console.print("[bold cyan]╚══════════════════════════════════════════╝[/]")
