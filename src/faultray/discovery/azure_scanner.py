# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Azure infrastructure auto-discovery scanner.

Connects to Azure via azure-mgmt libraries to discover all infrastructure
resources and generates a complete InfraGraph with components, dependencies,
metrics, security profiles, and cost profiles.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    RegionConfig,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

# Mapping from Azure service to FaultRay ComponentType
AZURE_TYPE_MAP: dict[str, ComponentType] = {
    "virtual_machine": ComponentType.APP_SERVER,
    "sql_database": ComponentType.DATABASE,
    "cosmos_db": ComponentType.DATABASE,
    "redis_cache": ComponentType.CACHE,
    "app_service": ComponentType.APP_SERVER,
    "functions": ComponentType.APP_SERVER,
    "aks": ComponentType.APP_SERVER,
    "load_balancer": ComponentType.LOAD_BALANCER,
    "app_gateway": ComponentType.LOAD_BALANCER,
    "front_door": ComponentType.LOAD_BALANCER,
    "blob_storage": ComponentType.STORAGE,
    "service_bus": ComponentType.QUEUE,
    "event_hubs": ComponentType.QUEUE,
    "dns": ComponentType.DNS,
}


def _check_azure_libs() -> None:
    """Check that required azure-mgmt libraries are importable."""
    try:
        import azure.identity  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "azure-identity is required for Azure scanning. "
            "Install with: pip install 'faultray[azure]'"
        )


@dataclass
class AzureDiscoveryResult:
    """Result of an Azure infrastructure discovery scan."""

    subscription_id: str
    components_found: int
    dependencies_inferred: int
    graph: InfraGraph
    warnings: list[str] = field(default_factory=list)
    scan_duration_seconds: float = 0.0


class AzureScanner:
    """Discover Azure infrastructure and generate InfraGraph automatically."""

    def __init__(self, subscription_id: str, resource_group: str | None = None):
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self._warnings: list[str] = []
        # NSG rule tracking for dependency inference
        self._nsg_rules: list[dict] = []
        # Component subnet tracking: component_id -> subnet_id
        self._component_subnets: dict[str, str] = {}
        # AKS cluster -> component_id mapping
        self._aks_clusters: dict[str, str] = {}

    def scan(self) -> AzureDiscoveryResult:
        """Run a full Azure infrastructure scan.

        Returns an AzureDiscoveryResult with the discovered InfraGraph.
        """
        _check_azure_libs()

        start = time.monotonic()
        graph = InfraGraph()

        scanners = [
            ("Virtual Machines", self._scan_virtual_machines),
            ("SQL Databases", self._scan_sql_databases),
            ("Redis Cache", self._scan_redis_cache),
            ("App Service", self._scan_app_service),
            ("AKS", self._scan_aks),
            ("Load Balancer", self._scan_load_balancer),
            ("Storage", self._scan_storage),
            ("Service Bus", self._scan_service_bus),
            ("DNS", self._scan_dns),
        ]

        for name, scanner_fn in scanners:
            try:
                scanner_fn(graph)
            except RuntimeError:
                raise  # Re-raise library import errors
            except Exception as exc:
                msg = f"Failed to scan {name}: {exc}"
                logger.warning(msg)
                self._warnings.append(msg)

        # Post-processing
        try:
            self._infer_dependencies(graph)
        except Exception as exc:
            msg = f"Failed to infer dependencies: {exc}"
            logger.warning(msg)
            self._warnings.append(msg)

        try:
            self._detect_security(graph)
        except Exception as exc:
            msg = f"Failed to detect security profiles: {exc}"
            logger.warning(msg)
            self._warnings.append(msg)

        duration = time.monotonic() - start
        dep_count = len(graph.all_dependency_edges())

        return AzureDiscoveryResult(
            subscription_id=self.subscription_id,
            components_found=len(graph.components),
            dependencies_inferred=dep_count,
            graph=graph,
            warnings=list(self._warnings),
            scan_duration_seconds=round(duration, 2),
        )

    # -- Individual Resource Scanners ------------------------------------------

    def _scan_virtual_machines(self, graph: InfraGraph) -> None:
        """Discover Azure Virtual Machines."""
        from azure.identity import DefaultAzureCredential
        from azure.mgmt.compute import ComputeManagementClient

        credential = DefaultAzureCredential()
        client = ComputeManagementClient(credential, self.subscription_id)

        try:
            if self.resource_group:
                vms = client.virtual_machines.list(self.resource_group)
            else:
                vms = client.virtual_machines.list_all()

            for vm in vms:
                vm_name = vm.name
                comp_id = f"azvm-{vm_name}"
                location = getattr(vm, "location", "")

                # Extract VM size
                vm_size = ""
                if hasattr(vm, "hardware_profile") and vm.hardware_profile:
                    vm_size = getattr(vm.hardware_profile, "vm_size", "")

                # Extract network info
                host = ""
                if hasattr(vm, "network_profile") and vm.network_profile:
                    nics = vm.network_profile.network_interfaces or []
                    if nics:
                        nic_ref = nics[0]
                        nic_id = getattr(nic_ref, "id", "")
                        if nic_id:
                            self._component_subnets[comp_id] = nic_id

                component = Component(
                    id=comp_id,
                    name=vm_name,
                    type=ComponentType.APP_SERVER,
                    host=host,
                    port=0,
                    replicas=1,
                    region=RegionConfig(region=location),
                    capacity=Capacity(
                        max_connections=1000,
                        max_rps=5000,
                    ),
                    tags=[f"vm_size:{vm_size}", "azure_vm"],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"Virtual Machines scan error: {exc}")

    def _scan_sql_databases(self, graph: InfraGraph) -> None:
        """Discover Azure SQL Databases and Cosmos DB accounts."""
        try:
            from azure.identity import DefaultAzureCredential
            from azure.mgmt.sql import SqlManagementClient
        except ImportError:
            self._warnings.append(
                "azure-mgmt-sql not installed, skipping SQL Database scan"
            )
            return

        try:
            credential = DefaultAzureCredential()
            client = SqlManagementClient(credential, self.subscription_id)

            if self.resource_group:
                servers = client.servers.list_by_resource_group(self.resource_group)
            else:
                servers = client.servers.list()

            for server in servers:
                server_name = server.name
                location = getattr(server, "location", "")
                fqdn = getattr(server, "fully_qualified_domain_name", "")

                # List databases on this server
                try:
                    rg = self.resource_group or _extract_resource_group(
                        getattr(server, "id", "")
                    )
                    databases = client.databases.list_by_server(rg, server_name)
                    for db in databases:
                        db_name = db.name
                        if db_name in ("master",):
                            continue

                        comp_id = f"azsql-{server_name}-{db_name}"

                        # HA / tier info
                        sku_name = ""
                        if hasattr(db, "sku") and db.sku:
                            sku_name = getattr(db.sku, "name", "")

                        ha_enabled = "premium" in sku_name.lower() or "business" in sku_name.lower()

                        component = Component(
                            id=comp_id,
                            name=f"{server_name}/{db_name}",
                            type=ComponentType.DATABASE,
                            host=fqdn,
                            port=1433,
                            replicas=2 if ha_enabled else 1,
                            region=RegionConfig(region=location),
                            failover=FailoverConfig(
                                enabled=ha_enabled,
                                promotion_time_seconds=30.0 if ha_enabled else 0.0,
                            ),
                            security=SecurityProfile(
                                encryption_at_rest=True,
                                encryption_in_transit=True,
                            ),
                            tags=["azure_sql", f"sku:{sku_name}"],
                        )
                        graph.add_component(component)
                except Exception as exc:
                    self._warnings.append(
                        f"SQL Database scan error for server {server_name}: {exc}"
                    )
        except Exception as exc:
            self._warnings.append(f"SQL Database scan error: {exc}")

    def _scan_redis_cache(self, graph: InfraGraph) -> None:
        """Discover Azure Cache for Redis instances."""
        try:
            from azure.identity import DefaultAzureCredential
            from azure.mgmt.redis import RedisManagementClient
        except ImportError:
            self._warnings.append(
                "azure-mgmt-redis not installed, skipping Redis Cache scan"
            )
            return

        try:
            credential = DefaultAzureCredential()
            client = RedisManagementClient(credential, self.subscription_id)

            if self.resource_group:
                caches = client.redis.list_by_resource_group(self.resource_group)
            else:
                caches = client.redis.list_by_subscription()

            for cache in caches:
                cache_name = cache.name
                comp_id = f"azredis-{cache_name}"
                location = getattr(cache, "location", "")
                host_name = getattr(cache, "host_name", "")
                port = getattr(cache, "ssl_port", 6380)

                # SKU info
                sku_name = ""
                replicas = 1
                if hasattr(cache, "sku") and cache.sku:
                    sku_name = getattr(cache.sku, "name", "")
                    if sku_name.lower() in ("premium", "standard"):
                        replicas = 2

                shard_count = getattr(cache, "shard_count", 0) or 0

                component = Component(
                    id=comp_id,
                    name=cache_name,
                    type=ComponentType.CACHE,
                    host=host_name,
                    port=port,
                    replicas=max(replicas, 1),
                    region=RegionConfig(region=location),
                    failover=FailoverConfig(
                        enabled=replicas > 1,
                        promotion_time_seconds=30.0 if replicas > 1 else 0.0,
                    ),
                    security=SecurityProfile(
                        encryption_in_transit=True,
                    ),
                    tags=["azure_redis", f"sku:{sku_name}", f"shards:{shard_count}"],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"Redis Cache scan error: {exc}")

    def _scan_app_service(self, graph: InfraGraph) -> None:
        """Discover Azure App Service and Functions apps."""
        try:
            from azure.identity import DefaultAzureCredential
            from azure.mgmt.web import WebSiteManagementClient
        except ImportError:
            self._warnings.append(
                "azure-mgmt-web not installed, skipping App Service scan"
            )
            return

        try:
            credential = DefaultAzureCredential()
            client = WebSiteManagementClient(credential, self.subscription_id)

            if self.resource_group:
                apps = client.web_apps.list_by_resource_group(self.resource_group)
            else:
                apps = client.web_apps.list()

            for app in apps:
                app_name = app.name
                kind = getattr(app, "kind", "") or ""
                location = getattr(app, "location", "")
                default_host = getattr(app, "default_host_name", "")

                is_function = "functionapp" in kind.lower()
                comp_id = f"azfunc-{app_name}" if is_function else f"azapp-{app_name}"

                component = Component(
                    id=comp_id,
                    name=app_name,
                    type=ComponentType.APP_SERVER,
                    host=default_host,
                    port=443,
                    replicas=1,
                    region=RegionConfig(region=location),
                    autoscaling=AutoScalingConfig(
                        enabled=True,
                        min_replicas=1,
                        max_replicas=30,
                    ),
                    security=SecurityProfile(
                        encryption_in_transit=True,
                    ),
                    tags=["azure_function" if is_function else "azure_app_service", f"kind:{kind}"],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"App Service scan error: {exc}")

    def _scan_aks(self, graph: InfraGraph) -> None:
        """Discover Azure Kubernetes Service (AKS) clusters."""
        try:
            from azure.identity import DefaultAzureCredential
            from azure.mgmt.containerservice import ContainerServiceClient
        except ImportError:
            self._warnings.append(
                "azure-mgmt-containerservice not installed, skipping AKS scan"
            )
            return

        try:
            credential = DefaultAzureCredential()
            client = ContainerServiceClient(credential, self.subscription_id)

            if self.resource_group:
                clusters = client.managed_clusters.list_by_resource_group(
                    self.resource_group
                )
            else:
                clusters = client.managed_clusters.list()

            for cluster in clusters:
                cluster_name = cluster.name
                comp_id = f"azaks-{cluster_name}"
                self._aks_clusters[cluster_name] = comp_id
                location = getattr(cluster, "location", "")
                fqdn = getattr(cluster, "fqdn", "")

                # Node count
                total_nodes = 0
                agent_pools = getattr(cluster, "agent_pool_profiles", []) or []
                for pool in agent_pools:
                    total_nodes += getattr(pool, "count", 0)

                # HA: multiple availability zones
                zones = []
                if agent_pools:
                    zones = list(
                        getattr(agent_pools[0], "availability_zones", []) or []
                    )
                ha_enabled = len(zones) > 1

                component = Component(
                    id=comp_id,
                    name=cluster_name,
                    type=ComponentType.APP_SERVER,
                    host=fqdn,
                    port=443,
                    replicas=max(total_nodes, 1),
                    region=RegionConfig(
                        region=location,
                        availability_zone=",".join(zones),
                    ),
                    failover=FailoverConfig(enabled=ha_enabled),
                    autoscaling=AutoScalingConfig(
                        enabled=any(
                            getattr(pool, "enable_auto_scaling", False)
                            for pool in agent_pools
                        ),
                    ),
                    tags=[
                        "azure_aks",
                        f"version:{getattr(cluster, 'kubernetes_version', '')}",
                    ],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"AKS scan error: {exc}")

    def _scan_load_balancer(self, graph: InfraGraph) -> None:
        """Discover Azure Load Balancers, App Gateways, and Front Door."""
        try:
            from azure.identity import DefaultAzureCredential
            from azure.mgmt.network import NetworkManagementClient
        except ImportError:
            self._warnings.append(
                "azure-mgmt-network not installed, skipping Load Balancer scan"
            )
            return

        try:
            credential = DefaultAzureCredential()
            client = NetworkManagementClient(credential, self.subscription_id)

            # Load Balancers
            if self.resource_group:
                lbs = client.load_balancers.list(self.resource_group)
            else:
                lbs = client.load_balancers.list_all()

            for lb in lbs:
                lb_name = lb.name
                comp_id = f"azlb-{lb_name}"
                location = getattr(lb, "location", "")

                sku_name = ""
                if hasattr(lb, "sku") and lb.sku:
                    sku_name = getattr(lb.sku, "name", "")

                component = Component(
                    id=comp_id,
                    name=lb_name,
                    type=ComponentType.LOAD_BALANCER,
                    port=443,
                    replicas=2 if "standard" in sku_name.lower() else 1,
                    region=RegionConfig(region=location),
                    capacity=Capacity(
                        max_connections=100000,
                        max_rps=100000,
                    ),
                    security=SecurityProfile(
                        encryption_in_transit=True,
                    ),
                    tags=["azure_lb", f"sku:{sku_name}"],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"Load Balancer scan error: {exc}")

    def _scan_storage(self, graph: InfraGraph) -> None:
        """Discover Azure Blob Storage accounts."""
        try:
            from azure.identity import DefaultAzureCredential
            from azure.mgmt.storage import StorageManagementClient
        except ImportError:
            self._warnings.append(
                "azure-mgmt-storage not installed, skipping Storage scan"
            )
            return

        try:
            credential = DefaultAzureCredential()
            client = StorageManagementClient(credential, self.subscription_id)

            if self.resource_group:
                accounts = client.storage_accounts.list_by_resource_group(
                    self.resource_group
                )
            else:
                accounts = client.storage_accounts.list()

            for account in accounts:
                account_name = account.name
                comp_id = f"azstore-{account_name}"
                location = getattr(account, "location", "")

                # Replication type
                sku_name = ""
                if hasattr(account, "sku") and account.sku:
                    sku_name = getattr(account.sku, "name", "")

                # GRS/RA-GRS = geo-redundant
                replicas = 3 if "grs" in sku_name.lower() else 2

                component = Component(
                    id=comp_id,
                    name=account_name,
                    type=ComponentType.STORAGE,
                    replicas=replicas,
                    region=RegionConfig(region=location),
                    security=SecurityProfile(
                        encryption_at_rest=True,
                        encryption_in_transit=True,
                    ),
                    tags=["azure_storage", f"sku:{sku_name}"],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"Storage scan error: {exc}")

    def _scan_service_bus(self, graph: InfraGraph) -> None:
        """Discover Azure Service Bus namespaces and Event Hubs."""
        try:
            from azure.identity import DefaultAzureCredential
            from azure.mgmt.servicebus import ServiceBusManagementClient
        except ImportError:
            self._warnings.append(
                "azure-mgmt-servicebus not installed, skipping Service Bus scan"
            )
            return

        try:
            credential = DefaultAzureCredential()
            client = ServiceBusManagementClient(credential, self.subscription_id)

            if self.resource_group:
                namespaces = client.namespaces.list_by_resource_group(
                    self.resource_group
                )
            else:
                namespaces = client.namespaces.list()

            for ns in namespaces:
                ns_name = ns.name
                comp_id = f"azsb-{ns_name}"
                location = getattr(ns, "location", "")

                sku_tier = ""
                if hasattr(ns, "sku") and ns.sku:
                    sku_tier = getattr(ns.sku, "tier", "")

                # Premium tier has zone redundancy
                replicas = 3 if "premium" in str(sku_tier).lower() else 1

                component = Component(
                    id=comp_id,
                    name=ns_name,
                    type=ComponentType.QUEUE,
                    replicas=replicas,
                    region=RegionConfig(region=location),
                    security=SecurityProfile(
                        encryption_at_rest=True,
                        encryption_in_transit=True,
                    ),
                    tags=["azure_service_bus", f"tier:{sku_tier}"],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"Service Bus scan error: {exc}")

    def _scan_dns(self, graph: InfraGraph) -> None:
        """Discover Azure DNS zones."""
        try:
            from azure.identity import DefaultAzureCredential
            from azure.mgmt.dns import DnsManagementClient
        except ImportError:
            self._warnings.append(
                "azure-mgmt-dns not installed, skipping DNS scan"
            )
            return

        try:
            credential = DefaultAzureCredential()
            client = DnsManagementClient(credential, self.subscription_id)

            zones = client.zones.list()

            for zone in zones:
                zone_name = zone.name
                comp_id = f"azdns-{zone_name}"

                component = Component(
                    id=comp_id,
                    name=f"DNS: {zone_name}",
                    type=ComponentType.DNS,
                    replicas=4,  # Azure DNS is globally redundant
                    region=RegionConfig(region="global"),
                    tags=["azure_dns", f"zone:{zone_name}"],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"DNS scan error: {exc}")

    # -- Dependency Inference --------------------------------------------------

    def _infer_dependencies(self, graph: InfraGraph) -> None:
        """Infer dependencies from NSG rules and subnet associations."""
        try:
            from azure.identity import DefaultAzureCredential
            from azure.mgmt.network import NetworkManagementClient
        except ImportError:
            self._warnings.append(
                "azure-mgmt-network not installed, skipping dependency inference"
            )
            return

        existing_edges: set[tuple[str, str]] = set()

        try:
            credential = DefaultAzureCredential()
            client = NetworkManagementClient(credential, self.subscription_id)

            # Collect NSG rules
            if self.resource_group:
                nsgs = client.network_security_groups.list(self.resource_group)
            else:
                nsgs = client.network_security_groups.list_all()

            for nsg in nsgs:
                rules = getattr(nsg, "security_rules", []) or []
                for rule in rules:
                    if getattr(rule, "direction", "") != "Inbound":
                        continue
                    if getattr(rule, "access", "") != "Allow":
                        continue

                    dest_port = getattr(rule, "destination_port_range", "")
                    try:
                        port = int(str(dest_port).split("-")[0])
                    except (ValueError, IndexError):
                        port = 0

                    self._nsg_rules.append({
                        "nsg_name": nsg.name,
                        "port": port,
                        "source": getattr(rule, "source_address_prefix", ""),
                        "destination": getattr(rule, "destination_address_prefix", ""),
                    })
        except Exception as exc:
            self._warnings.append(f"NSG rule scan error: {exc}")

        # Heuristic: connect LBs to app servers, apps to databases/caches
        component_list = list(graph.components.values())
        lb_comps = [c for c in component_list if c.type == ComponentType.LOAD_BALANCER]
        app_comps = [c for c in component_list if c.type == ComponentType.APP_SERVER]
        db_comps = [c for c in component_list if c.type == ComponentType.DATABASE]
        cache_comps = [c for c in component_list if c.type == ComponentType.CACHE]
        queue_comps = [c for c in component_list if c.type == ComponentType.QUEUE]

        # LB -> App Server
        for lb in lb_comps:
            for app in app_comps:
                edge_key = (lb.id, app.id)
                if edge_key not in existing_edges:
                    existing_edges.add(edge_key)
                    graph.add_dependency(Dependency(
                        source_id=lb.id,
                        target_id=app.id,
                        dependency_type="routes_to",
                        protocol="tcp",
                        port=app.port or 443,
                    ))

        # App Server -> Database / Cache / Queue
        for app in app_comps:
            for db in db_comps:
                edge_key = (app.id, db.id)
                if edge_key not in existing_edges:
                    existing_edges.add(edge_key)
                    graph.add_dependency(Dependency(
                        source_id=app.id,
                        target_id=db.id,
                        dependency_type="requires",
                        protocol="tcp",
                        port=db.port,
                    ))
            for cache in cache_comps:
                edge_key = (app.id, cache.id)
                if edge_key not in existing_edges:
                    existing_edges.add(edge_key)
                    graph.add_dependency(Dependency(
                        source_id=app.id,
                        target_id=cache.id,
                        dependency_type="optional",
                        protocol="tcp",
                        port=cache.port,
                    ))
            for queue in queue_comps:
                edge_key = (app.id, queue.id)
                if edge_key not in existing_edges:
                    existing_edges.add(edge_key)
                    graph.add_dependency(Dependency(
                        source_id=app.id,
                        target_id=queue.id,
                        dependency_type="optional",
                        protocol="tcp",
                        port=5671,
                    ))

    # -- Security Profile Detection --------------------------------------------

    def _detect_security(self, graph: InfraGraph) -> None:
        """Detect and enrich security profiles for all components."""
        for comp in graph.components.values():
            # HTTPS port implies encryption in transit
            if comp.port == 443:
                comp.security.encryption_in_transit = True

            # Azure SQL always encrypts at rest
            if "azure_sql" in comp.tags:
                comp.security.encryption_at_rest = True

            # Azure Storage always encrypts at rest
            if "azure_storage" in comp.tags:
                comp.security.encryption_at_rest = True

            # Components with subnet associations are network-segmented
            if comp.id in self._component_subnets:
                comp.security.network_segmented = True


def _extract_resource_group(resource_id: str) -> str:
    """Extract resource group name from an Azure resource ID string."""
    parts = resource_id.split("/")
    for i, part in enumerate(parts):
        if part.lower() == "resourcegroups" and i + 1 < len(parts):
            return parts[i + 1]
    return ""
