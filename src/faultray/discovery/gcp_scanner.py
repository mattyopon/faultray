"""GCP infrastructure auto-discovery scanner.

Connects to GCP via google-cloud libraries to discover all infrastructure
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

# Mapping from GCP service to FaultRay ComponentType
GCP_TYPE_MAP: dict[str, ComponentType] = {
    "compute": ComponentType.APP_SERVER,
    "cloud_sql": ComponentType.DATABASE,
    "memorystore": ComponentType.CACHE,
    "cloud_load_balancing": ComponentType.LOAD_BALANCER,
    "gke": ComponentType.APP_SERVER,
    "cloud_storage": ComponentType.STORAGE,
    "pub_sub": ComponentType.QUEUE,
    "cloud_dns": ComponentType.DNS,
    "cloud_run": ComponentType.APP_SERVER,
    "cloud_functions": ComponentType.APP_SERVER,
}


def _check_gcp_libs() -> None:
    """Check that required google-cloud libraries are importable."""
    try:
        import google.cloud.compute_v1  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "google-cloud-compute is required for GCP scanning. "
            "Install with: pip install 'faultray[gcp]'"
        )


@dataclass
class GCPDiscoveryResult:
    """Result of a GCP infrastructure discovery scan."""

    project_id: str
    components_found: int
    dependencies_inferred: int
    graph: InfraGraph
    warnings: list[str] = field(default_factory=list)
    scan_duration_seconds: float = 0.0


class GCPScanner:
    """Discover GCP infrastructure and generate InfraGraph automatically."""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self._warnings: list[str] = []
        # Firewall rule tracking: network -> list of (source_tag, target_tag, port)
        self._firewall_rules: list[dict] = []
        # Component tag tracking: component_id -> list of network tags
        self._component_tags: dict[str, list[str]] = {}
        # Component network tracking: component_id -> network name
        self._component_networks: dict[str, str] = {}
        # GKE cluster -> component_id mapping
        self._gke_clusters: dict[str, str] = {}

    def scan(self) -> GCPDiscoveryResult:
        """Run a full GCP infrastructure scan.

        Returns a GCPDiscoveryResult with the discovered InfraGraph.
        """
        _check_gcp_libs()

        start = time.monotonic()
        graph = InfraGraph()

        scanners = [
            ("Compute Engine", self._scan_compute_instances),
            ("Cloud SQL", self._scan_cloud_sql),
            ("Memorystore", self._scan_memorystore),
            ("Cloud Load Balancing", self._scan_cloud_load_balancing),
            ("Cloud Run", self._scan_cloud_run),
            ("GKE", self._scan_gke),
            ("Cloud Storage", self._scan_cloud_storage),
            ("Pub/Sub", self._scan_pub_sub),
            ("Cloud DNS", self._scan_cloud_dns),
            ("Cloud Functions", self._scan_cloud_functions),
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

        return GCPDiscoveryResult(
            project_id=self.project_id,
            components_found=len(graph.components),
            dependencies_inferred=dep_count,
            graph=graph,
            warnings=list(self._warnings),
            scan_duration_seconds=round(duration, 2),
        )

    # ── Individual Resource Scanners ─────────────────────────────────────────

    def _scan_compute_instances(self, graph: InfraGraph) -> None:
        """Discover Compute Engine instances."""
        from google.cloud import compute_v1

        client = compute_v1.InstancesClient()

        try:
            request = compute_v1.AggregatedListInstancesRequest(
                project=self.project_id,
            )
            for zone, response in client.aggregated_list(request=request):
                if not response.instances:
                    continue
                for inst in response.instances:
                    if inst.status != "RUNNING":
                        continue

                    str(inst.id)
                    name = inst.name
                    zone_name = zone.split("/")[-1] if "/" in zone else zone

                    comp_id = f"gce-{name}"

                    # Extract network tags
                    tags = list(inst.tags.items) if inst.tags and inst.tags.items else []
                    self._component_tags[comp_id] = tags

                    # Extract network interface info
                    if inst.network_interfaces:
                        nic = inst.network_interfaces[0]
                        network = nic.network.split("/")[-1] if nic.network else ""
                        self._component_networks[comp_id] = network
                        host = nic.network_i_p or ""
                    else:
                        host = ""

                    component = Component(
                        id=comp_id,
                        name=name,
                        type=ComponentType.APP_SERVER,
                        host=host,
                        port=0,
                        replicas=1,
                        region=RegionConfig(
                            region=self.project_id,
                            availability_zone=zone_name,
                        ),
                        capacity=Capacity(
                            max_connections=1000,
                            max_rps=5000,
                        ),
                        tags=[f"machine_type:{inst.machine_type.split('/')[-1] if inst.machine_type else ''}"],
                    )
                    graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"Compute Engine scan error: {exc}")

    def _scan_cloud_sql(self, graph: InfraGraph) -> None:
        """Discover Cloud SQL instances."""
        try:
            from google.cloud.sql_v1 import SqlInstancesServiceClient
        except ImportError:
            self._warnings.append("google-cloud-sql-admin not installed, skipping Cloud SQL scan")
            return

        try:
            client = SqlInstancesServiceClient()
            request = {"project": self.project_id}
            response = client.list(request=request)

            for instance in response:
                instance_name = instance.name
                comp_id = f"cloudsql-{instance_name}"

                # Determine database type and port
                db_version = instance.database_version if hasattr(instance, "database_version") else ""
                if "POSTGRES" in str(db_version).upper():
                    port = 5432
                elif "MYSQL" in str(db_version).upper():
                    port = 3306
                else:
                    port = 5432

                # High availability
                ha_enabled = False
                if hasattr(instance, "settings") and instance.settings:
                    ha_enabled = str(
                        getattr(instance.settings, "availability_type", "")
                    ).upper() == "REGIONAL"

                # IP address
                host = ""
                if hasattr(instance, "ip_addresses") and instance.ip_addresses:
                    for ip in instance.ip_addresses:
                        if str(getattr(ip, "type_", "")).upper() == "PRIVATE":
                            host = ip.ip_address
                            break
                    if not host:
                        host = instance.ip_addresses[0].ip_address

                # Backup configuration
                backup_enabled = False
                if hasattr(instance, "settings") and instance.settings:
                    backup_cfg = getattr(instance.settings, "backup_configuration", None)
                    if backup_cfg:
                        backup_enabled = getattr(backup_cfg, "enabled", False)

                component = Component(
                    id=comp_id,
                    name=instance_name,
                    type=ComponentType.DATABASE,
                    host=host,
                    port=port,
                    replicas=2 if ha_enabled else 1,
                    region=RegionConfig(
                        region=getattr(instance, "region", self.project_id),
                    ),
                    failover=FailoverConfig(
                        enabled=ha_enabled,
                        promotion_time_seconds=60.0 if ha_enabled else 0.0,
                    ),
                    security=SecurityProfile(
                        backup_enabled=backup_enabled,
                        backup_frequency_hours=24.0 if backup_enabled else 0.0,
                    ),
                    tags=["cloud_sql", f"engine:{db_version}"],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"Cloud SQL scan error: {exc}")

    def _scan_memorystore(self, graph: InfraGraph) -> None:
        """Discover Memorystore (Redis) instances."""
        try:
            from google.cloud import redis_v1
        except ImportError:
            self._warnings.append("google-cloud-redis not installed, skipping Memorystore scan")
            return

        try:
            client = redis_v1.CloudRedisClient()
            parent = f"projects/{self.project_id}/locations/-"
            request = redis_v1.ListInstancesRequest(parent=parent)
            response = client.list_instances(request=request)

            for instance in response:
                instance_name = instance.name.split("/")[-1]
                comp_id = f"memorystore-{instance_name}"

                ha_enabled = str(getattr(instance, "tier", "")).upper() == "STANDARD"
                replica_count = getattr(instance, "replica_count", 0)

                component = Component(
                    id=comp_id,
                    name=instance_name,
                    type=ComponentType.CACHE,
                    host=getattr(instance, "host", ""),
                    port=getattr(instance, "port", 6379),
                    replicas=max(1 + replica_count, 1),
                    region=RegionConfig(
                        region=getattr(instance, "location_id", self.project_id),
                    ),
                    failover=FailoverConfig(
                        enabled=ha_enabled,
                        promotion_time_seconds=30.0 if ha_enabled else 0.0,
                    ),
                    security=SecurityProfile(
                        encryption_in_transit=getattr(instance, "transit_encryption_mode", 0) != 0,
                    ),
                    tags=["memorystore", "redis"],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"Memorystore scan error: {exc}")

    def _scan_cloud_load_balancing(self, graph: InfraGraph) -> None:
        """Discover Cloud Load Balancing (forwarding rules)."""
        from google.cloud import compute_v1

        try:
            client = compute_v1.GlobalForwardingRulesClient()
            request = compute_v1.ListGlobalForwardingRulesRequest(
                project=self.project_id,
            )
            for rule in client.list(request=request):
                rule_name = rule.name
                comp_id = f"gclb-{rule_name}"

                port_str = rule.port_range if hasattr(rule, "port_range") and rule.port_range else "443"
                try:
                    port = int(port_str.split("-")[0])
                except (ValueError, IndexError):
                    port = 443

                component = Component(
                    id=comp_id,
                    name=rule_name,
                    type=ComponentType.LOAD_BALANCER,
                    host=getattr(rule, "I_p_address", "") or "",
                    port=port,
                    replicas=3,  # Global LB is inherently distributed
                    region=RegionConfig(region="global"),
                    capacity=Capacity(
                        max_connections=100000,
                        max_rps=100000,
                    ),
                    security=SecurityProfile(
                        encryption_in_transit=port == 443,
                    ),
                    tags=["gclb"],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"Cloud Load Balancing scan error: {exc}")

    def _scan_cloud_run(self, graph: InfraGraph) -> None:
        """Discover Cloud Run services."""
        try:
            from google.cloud import run_v2
        except ImportError:
            self._warnings.append("google-cloud-run not installed, skipping Cloud Run scan")
            return

        try:
            client = run_v2.ServicesClient()
            parent = f"projects/{self.project_id}/locations/-"
            request = run_v2.ListServicesRequest(parent=parent)
            response = client.list_services(request=request)

            for service in response:
                svc_name = service.name.split("/")[-1]
                comp_id = f"cloudrun-{svc_name}"

                # Extract scaling config
                min_instances = 0
                max_instances = 100
                if hasattr(service, "template") and service.template:
                    scaling = getattr(service.template, "scaling", None)
                    if scaling:
                        min_instances = getattr(scaling, "min_instance_count", 0)
                        max_instances = getattr(scaling, "max_instance_count", 100)

                component = Component(
                    id=comp_id,
                    name=svc_name,
                    type=ComponentType.APP_SERVER,
                    host=getattr(service, "uri", "") or "",
                    port=443,
                    replicas=max(min_instances, 1),
                    region=RegionConfig(region=self.project_id),
                    autoscaling=AutoScalingConfig(
                        enabled=True,
                        min_replicas=min_instances,
                        max_replicas=max_instances,
                    ),
                    security=SecurityProfile(
                        encryption_in_transit=True,  # Cloud Run always uses HTTPS
                    ),
                    tags=["cloud_run"],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"Cloud Run scan error: {exc}")

    def _scan_gke(self, graph: InfraGraph) -> None:
        """Discover GKE clusters."""
        try:
            from google.cloud import container_v1
        except ImportError:
            self._warnings.append("google-cloud-container not installed, skipping GKE scan")
            return

        try:
            client = container_v1.ClusterManagerClient()
            parent = f"projects/{self.project_id}/locations/-"
            response = client.list_clusters(parent=parent)

            for cluster in response.clusters:
                cluster_name = cluster.name
                comp_id = f"gke-{cluster_name}"
                self._gke_clusters[cluster_name] = comp_id

                # Node count
                total_nodes = 0
                if cluster.node_pools:
                    for pool in cluster.node_pools:
                        total_nodes += getattr(pool, "initial_node_count", 0)

                # HA: regional cluster has multiple zones
                locations = list(cluster.locations) if cluster.locations else []
                ha_enabled = len(locations) > 1

                component = Component(
                    id=comp_id,
                    name=cluster_name,
                    type=ComponentType.APP_SERVER,
                    host=getattr(cluster, "endpoint", "") or "",
                    port=443,
                    replicas=max(total_nodes, 1),
                    region=RegionConfig(
                        region=getattr(cluster, "location", self.project_id),
                        availability_zone=",".join(locations),
                    ),
                    failover=FailoverConfig(
                        enabled=ha_enabled,
                    ),
                    autoscaling=AutoScalingConfig(
                        enabled=any(
                            getattr(pool, "autoscaling", None) and getattr(pool.autoscaling, "enabled", False)
                            for pool in (cluster.node_pools or [])
                        ),
                    ),
                    tags=["gke", f"version:{getattr(cluster, 'current_master_version', '')}"],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"GKE scan error: {exc}")

    def _scan_cloud_storage(self, graph: InfraGraph) -> None:
        """Discover Cloud Storage (GCS) buckets."""
        try:
            from google.cloud import storage
        except ImportError:
            self._warnings.append("google-cloud-storage not installed, skipping GCS scan")
            return

        try:
            client = storage.Client(project=self.project_id)
            buckets = client.list_buckets()

            for bucket in buckets:
                bucket_name = bucket.name
                comp_id = f"gcs-{bucket_name}"

                # Check versioning
                versioning_enabled = bucket.versioning_enabled if hasattr(bucket, "versioning_enabled") else False

                # Check default encryption
                getattr(bucket, "default_kms_key_name", None)

                component = Component(
                    id=comp_id,
                    name=bucket_name,
                    type=ComponentType.STORAGE,
                    replicas=3,  # GCS is inherently replicated
                    region=RegionConfig(
                        region=getattr(bucket, "location", self.project_id),
                    ),
                    security=SecurityProfile(
                        encryption_at_rest=True,  # GCS always encrypts at rest
                        backup_enabled=versioning_enabled,
                    ),
                    tags=["gcs"],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"Cloud Storage scan error: {exc}")

    def _scan_pub_sub(self, graph: InfraGraph) -> None:
        """Discover Pub/Sub topics."""
        try:
            from google.cloud import pubsub_v1
        except ImportError:
            self._warnings.append("google-cloud-pubsub not installed, skipping Pub/Sub scan")
            return

        try:
            publisher = pubsub_v1.PublisherClient()
            project_path = f"projects/{self.project_id}"
            topics = publisher.list_topics(request={"project": project_path})

            for topic in topics:
                topic_name = topic.name.split("/")[-1]
                comp_id = f"pubsub-{topic_name}"

                component = Component(
                    id=comp_id,
                    name=topic_name,
                    type=ComponentType.QUEUE,
                    replicas=3,  # Pub/Sub is regionally replicated
                    region=RegionConfig(region=self.project_id),
                    security=SecurityProfile(
                        encryption_at_rest=True,  # Pub/Sub encrypts at rest by default
                    ),
                    tags=["pubsub"],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"Pub/Sub scan error: {exc}")

    def _scan_cloud_dns(self, graph: InfraGraph) -> None:
        """Discover Cloud DNS managed zones."""
        try:
            from google.cloud import dns
        except ImportError:
            self._warnings.append("google-cloud-dns not installed, skipping Cloud DNS scan")
            return

        try:
            client = dns.Client(project=self.project_id)
            zones = client.list_zones()

            for zone in zones:
                zone_name = zone.name
                dns_name = getattr(zone, "dns_name", zone_name)

                comp_id = f"clouddns-{zone_name}"
                component = Component(
                    id=comp_id,
                    name=f"DNS: {dns_name}",
                    type=ComponentType.DNS,
                    replicas=4,  # Cloud DNS is globally redundant
                    region=RegionConfig(region="global"),
                    tags=["cloud_dns", f"zone:{dns_name}"],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"Cloud DNS scan error: {exc}")

    def _scan_cloud_functions(self, graph: InfraGraph) -> None:
        """Discover Cloud Functions."""
        try:
            from google.cloud import functions_v2
        except ImportError:
            self._warnings.append("google-cloud-functions not installed, skipping Cloud Functions scan")
            return

        try:
            client = functions_v2.FunctionServiceClient()
            parent = f"projects/{self.project_id}/locations/-"
            request = functions_v2.ListFunctionsRequest(parent=parent)
            response = client.list_functions(request=request)

            for func in response:
                func_name = func.name.split("/")[-1]
                comp_id = f"gcf-{func_name}"

                # Extract memory/timeout from service config
                memory_mb = 256
                timeout_seconds = 60
                if hasattr(func, "service_config") and func.service_config:
                    svc_cfg = func.service_config
                    mem_str = getattr(svc_cfg, "available_memory", "")
                    if mem_str:
                        try:
                            memory_mb = int(str(mem_str).replace("M", "").replace("Mi", ""))
                        except ValueError:
                            pass
                    timeout_str = getattr(svc_cfg, "timeout_seconds", 60)
                    try:
                        timeout_seconds = int(timeout_str)
                    except (ValueError, TypeError):
                        pass

                component = Component(
                    id=comp_id,
                    name=func_name,
                    type=ComponentType.APP_SERVER,
                    replicas=1,
                    region=RegionConfig(region=self.project_id),
                    capacity=Capacity(
                        max_memory_mb=float(memory_mb),
                        timeout_seconds=float(timeout_seconds),
                    ),
                    autoscaling=AutoScalingConfig(
                        enabled=True,
                        min_replicas=0,
                        max_replicas=1000,
                    ),
                    tags=["cloud_functions", f"runtime:{getattr(func, 'build_config', None) and getattr(func.build_config, 'runtime', '') or ''}"],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"Cloud Functions scan error: {exc}")

    # ── Dependency Inference ─────────────────────────────────────────────────

    def _infer_dependencies(self, graph: InfraGraph) -> None:
        """Infer dependencies from VPC firewall rules and network tags."""
        from google.cloud import compute_v1

        existing_edges: set[tuple[str, str]] = set()

        # Collect firewall rules
        try:
            client = compute_v1.FirewallsClient()
            request = compute_v1.ListFirewallsRequest(project=self.project_id)
            for rule in client.list(request=request):
                if rule.direction != "INGRESS":
                    continue
                if rule.disabled:
                    continue

                source_tags = list(rule.source_tags) if rule.source_tags else []
                target_tags = list(rule.target_tags) if rule.target_tags else []

                for allowed in (rule.allowed or []):
                    ports = []
                    for port_str in (allowed.ports or []):
                        try:
                            ports.append(int(port_str.split("-")[0]))
                        except (ValueError, IndexError):
                            pass

                    self._firewall_rules.append({
                        "source_tags": source_tags,
                        "target_tags": target_tags,
                        "ports": ports,
                        "network": rule.network.split("/")[-1] if rule.network else "",
                    })
        except Exception as exc:
            self._warnings.append(f"Firewall rule scan error: {exc}")

        # Match firewall rules to components via tags
        for rule in self._firewall_rules:
            source_comps = []
            target_comps = []

            for comp_id, tags in self._component_tags.items():
                if comp_id not in graph.components:
                    continue
                if any(t in tags for t in rule["source_tags"]):
                    source_comps.append(comp_id)
                if any(t in tags for t in rule["target_tags"]):
                    target_comps.append(comp_id)

            for src in source_comps:
                for tgt in target_comps:
                    if src == tgt:
                        continue
                    edge_key = (src, tgt)
                    if edge_key in existing_edges:
                        continue
                    existing_edges.add(edge_key)

                    port = rule["ports"][0] if rule["ports"] else 0
                    dep_type = "requires" if port in {3306, 5432, 6379, 11211, 27017} else "optional"

                    dep = Dependency(
                        source_id=src,
                        target_id=tgt,
                        dependency_type=dep_type,
                        protocol="tcp",
                        port=port,
                    )
                    graph.add_dependency(dep)

    # ── Security Profile Detection ───────────────────────────────────────────

    def _detect_security(self, graph: InfraGraph) -> None:
        """Detect and enrich security profiles for all components."""
        # Network segmentation: components with network tags are considered segmented
        for comp_id, tags in self._component_tags.items():
            if comp_id in graph.components and tags:
                graph.components[comp_id].security.network_segmented = True

        # Encryption in transit: HTTPS port
        for comp in graph.components.values():
            if comp.port == 443:
                comp.security.encryption_in_transit = True
