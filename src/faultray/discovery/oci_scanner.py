# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Oracle Cloud Infrastructure (OCI) auto-discovery scanner.

Connects to OCI via the official Python SDK to discover infrastructure resources
and generates a complete InfraGraph with components and dependencies.

Usage:
    pip install 'faultray[oci]'
    scanner = OCIScanner(compartment_id="ocid1.compartment.oc1..xxx")
    result = scanner.scan()
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from faultray.model.components import (
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

# Mapping from OCI service to FaultRay ComponentType
OCI_TYPE_MAP: dict[str, ComponentType] = {
    "compute": ComponentType.APP_SERVER,
    "db_system": ComponentType.DATABASE,
    "autonomous_database": ComponentType.DATABASE,
    "load_balancer": ComponentType.LOAD_BALANCER,
    "vcn": ComponentType.CUSTOM,
    "object_storage": ComponentType.STORAGE,
}

# OCI DB edition -> port mapping
_OCI_DB_PORT: dict[str, int] = {
    "STANDARD_EDITION": 1521,
    "ENTERPRISE_EDITION": 1521,
    "ENTERPRISE_EDITION_HIGH_PERFORMANCE": 1521,
    "ENTERPRISE_EDITION_EXTREME_PERFORMANCE": 1521,
    "STANDARD": 1521,
}


def _check_oci_libs() -> None:
    """Check that the OCI SDK is importable."""
    try:
        import oci  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "oci is required for Oracle Cloud scanning. "
            "Install with: pip install 'faultray[oci]'"
        )


def _make_config(
    compartment_id: str,
    config_file: str | None = None,
    profile: str = "DEFAULT",
) -> dict:
    """Load OCI configuration from file or instance principal."""
    import oci

    if config_file:
        config = oci.config.from_file(file_location=config_file, profile_name=profile)
    else:
        try:
            config = oci.config.from_file(profile_name=profile)
        except Exception:
            # Fall back to instance principal (running on OCI compute)
            config = {}
    return config


@dataclass
class OCIDiscoveryResult:
    """Result of an OCI infrastructure discovery scan."""

    compartment_id: str
    components_found: int
    dependencies_inferred: int
    graph: InfraGraph
    warnings: list[str] = field(default_factory=list)
    scan_duration_seconds: float = 0.0


class OCIScanner:
    """Discover Oracle Cloud Infrastructure and generate InfraGraph automatically.

    Uses the OCI Python SDK with config from ~/.oci/config or instance principal.

    Args:
        compartment_id: OCID of the compartment to scan.
        config_file: Path to OCI config file (default: ~/.oci/config).
        profile: OCI config profile name (default: "DEFAULT").
        region: OCI region identifier (e.g. "us-ashburn-1"). If None, uses config value.
    """

    def __init__(
        self,
        compartment_id: str,
        config_file: str | None = None,
        profile: str = "DEFAULT",
        region: str | None = None,
    ) -> None:
        self.compartment_id = compartment_id
        self.config_file = config_file
        self.profile = profile
        self.region = region
        self._warnings: list[str] = []
        # VCN ID -> list of component IDs in that VCN
        self._vcn_members: dict[str, list[str]] = {}
        # Load balancer OCID -> list of backend instance OCIDs
        self._lb_backends: dict[str, list[str]] = {}
        # Subnet OCID -> VCN OCID
        self._subnet_vcn: dict[str, str] = {}

    def scan(self) -> OCIDiscoveryResult:
        """Run a full OCI infrastructure scan.

        Returns an OCIDiscoveryResult with the discovered InfraGraph.
        """
        _check_oci_libs()

        start = time.monotonic()
        graph = InfraGraph()

        config = _make_config(self.compartment_id, self.config_file, self.profile)
        if self.region:
            config["region"] = self.region

        scanners = [
            ("Compute", lambda g: self._scan_compute(g, config)),
            ("DBSystems", lambda g: self._scan_db_systems(g, config)),
            ("AutonomousDB", lambda g: self._scan_autonomous_db(g, config)),
            ("LoadBalancers", lambda g: self._scan_load_balancers(g, config)),
            ("VCN", lambda g: self._scan_vcn(g, config)),
            ("ObjectStorage", lambda g: self._scan_object_storage(g, config)),
        ]

        for name, scanner_fn in scanners:
            try:
                scanner_fn(graph)
            except RuntimeError:
                raise  # Re-raise library import errors
            except Exception as exc:
                msg = f"Failed to scan OCI {name}: {exc}"
                logger.warning(msg)
                self._warnings.append(msg)

        try:
            self._infer_dependencies(graph)
        except Exception as exc:
            msg = f"Failed to infer OCI dependencies: {exc}"
            logger.warning(msg)
            self._warnings.append(msg)

        duration = time.monotonic() - start
        dep_count = len(graph.all_dependency_edges())

        return OCIDiscoveryResult(
            compartment_id=self.compartment_id,
            components_found=len(graph.components),
            dependencies_inferred=dep_count,
            graph=graph,
            warnings=list(self._warnings),
            scan_duration_seconds=round(duration, 2),
        )

    # ── Individual Resource Scanners ─────────────────────────────────────────

    def _scan_compute(self, graph: InfraGraph, config: dict) -> None:
        """Discover OCI Compute instances."""
        try:
            import oci

            client = oci.core.ComputeClient(config)
            vnic_client = oci.core.VirtualNetworkClient(config)

            response = oci.pagination.list_call_get_all_results(
                client.list_instances,
                compartment_id=self.compartment_id,
                lifecycle_state="RUNNING",
            )

            for inst in response.data:
                inst_id = inst.id or ""
                name = inst.display_name or inst_id
                comp_id = f"oci-compute-{inst_id.split('.')[-1]}"

                # Get VNIC attachments for IP and VCN
                host = ""
                vcn_id = ""
                subnet_id = ""
                try:
                    vnic_attachments = oci.pagination.list_call_get_all_results(
                        client.list_vnic_attachments,
                        compartment_id=self.compartment_id,
                        instance_id=inst_id,
                    ).data
                    if vnic_attachments:
                        vnic_id = vnic_attachments[0].vnic_id
                        vnic = vnic_client.get_vnic(vnic_id).data
                        host = vnic.private_ip or ""
                        subnet_id = vnic.subnet_id or ""
                        if subnet_id in self._subnet_vcn:
                            vcn_id = self._subnet_vcn[subnet_id]
                except Exception:
                    pass

                if vcn_id:
                    self._vcn_members.setdefault(vcn_id, []).append(comp_id)

                shape = inst.shape or ""
                ocpus = getattr(inst.shape_config, "ocpus", 1) if inst.shape_config else 1
                memory_gb = getattr(inst.shape_config, "memory_in_gbs", 16) if inst.shape_config else 16

                region = config.get("region", "us-ashburn-1")
                az = inst.availability_domain or ""

                component = Component(
                    id=comp_id,
                    name=name,
                    type=ComponentType.APP_SERVER,
                    host=host,
                    port=0,
                    replicas=1,
                    region=RegionConfig(region=region, availability_zone=az),
                    capacity=Capacity(
                        max_connections=int(1000 * ocpus),
                        max_rps=int(5000 * ocpus),
                        max_memory_mb=float(memory_gb * 1024),
                    ),
                    tags=[f"shape:{shape}", f"ocpus:{ocpus}"],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"OCI compute scan error: {exc}")

    def _scan_db_systems(self, graph: InfraGraph, config: dict) -> None:
        """Discover OCI DB Systems (Oracle Database)."""
        try:
            import oci

            client = oci.database.DatabaseClient(config)
            response = oci.pagination.list_call_get_all_results(
                client.list_db_systems,
                compartment_id=self.compartment_id,
                lifecycle_state="AVAILABLE",
            )

            for db_sys in response.data:
                sys_id = db_sys.id or ""
                name = db_sys.display_name or sys_id
                comp_id = f"oci-dbsys-{sys_id.split('.')[-1]}"

                subnet_id = db_sys.subnet_id or ""
                vcn_id = self._subnet_vcn.get(subnet_id, "")
                if vcn_id:
                    self._vcn_members.setdefault(vcn_id, []).append(comp_id)

                region = config.get("region", "us-ashburn-1")
                az = db_sys.availability_domain or ""

                replicas = db_sys.node_count or 1
                has_data_guard = bool(getattr(db_sys, "data_storage_percentage", 0))

                component = Component(
                    id=comp_id,
                    name=name,
                    type=ComponentType.DATABASE,
                    host=db_sys.hostname or "",
                    port=1521,
                    replicas=replicas,
                    region=RegionConfig(region=region, availability_zone=az),
                    capacity=Capacity(
                        max_connections=500,
                        max_rps=2000,
                    ),
                    failover=FailoverConfig(enabled=has_data_guard),
                    security=SecurityProfile(
                        encryption_at_rest=True,  # OCI DB always encrypts
                        backup_enabled=True,
                    ),
                    tags=[f"shape:{db_sys.shape or ''}"],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"OCI DB Systems scan error: {exc}")

    def _scan_autonomous_db(self, graph: InfraGraph, config: dict) -> None:
        """Discover OCI Autonomous Databases."""
        try:
            import oci

            client = oci.database.DatabaseClient(config)
            response = oci.pagination.list_call_get_all_results(
                client.list_autonomous_databases,
                compartment_id=self.compartment_id,
                lifecycle_state="AVAILABLE",
            )

            for adb in response.data:
                adb_id = adb.id or ""
                name = adb.display_name or adb_id
                comp_id = f"oci-adb-{adb_id.split('.')[-1]}"

                region = config.get("region", "us-ashburn-1")

                component = Component(
                    id=comp_id,
                    name=name,
                    type=ComponentType.DATABASE,
                    host="",  # Connection string via wallet
                    port=1522,  # TLS port for ADB
                    replicas=3,  # ADB is always replicated
                    region=RegionConfig(region=region),
                    capacity=Capacity(
                        max_connections=300,
                        max_rps=10000,
                    ),
                    failover=FailoverConfig(enabled=True),
                    security=SecurityProfile(
                        encryption_at_rest=True,
                        encryption_in_transit=True,
                        backup_enabled=True,
                    ),
                    tags=[
                        f"workload:{adb.db_workload or ''}",
                        f"ocpus:{adb.cpu_core_count or 1}",
                    ],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"OCI Autonomous DB scan error: {exc}")

    def _scan_load_balancers(self, graph: InfraGraph, config: dict) -> None:
        """Discover OCI Load Balancers."""
        try:
            import oci

            client = oci.load_balancer.LoadBalancerClient(config)
            response = oci.pagination.list_call_get_all_results(
                client.list_load_balancers,
                compartment_id=self.compartment_id,
                lifecycle_state="ACTIVE",
            )

            for lb in response.data:
                lb_id = lb.id or ""
                name = lb.display_name or lb_id
                comp_id = f"oci-lb-{lb_id.split('.')[-1]}"

                # Get public IPs
                host = ""
                if lb.ip_addresses:
                    for ip_info in lb.ip_addresses:
                        if ip_info.is_public:
                            host = ip_info.ip_address or ""
                            break
                    if not host and lb.ip_addresses:
                        host = lb.ip_addresses[0].ip_address or ""

                # Track VCN membership via subnet
                subnet_ids = lb.subnet_ids or []
                vcn_id = ""
                for sn_id in subnet_ids:
                    if sn_id in self._subnet_vcn:
                        vcn_id = self._subnet_vcn[sn_id]
                        break
                if vcn_id:
                    self._vcn_members.setdefault(vcn_id, []).append(comp_id)

                region = config.get("region", "us-ashburn-1")

                component = Component(
                    id=comp_id,
                    name=name,
                    type=ComponentType.LOAD_BALANCER,
                    host=host,
                    port=443,
                    replicas=2,  # OCI LB is always HA
                    region=RegionConfig(region=region),
                    capacity=Capacity(max_connections=50000, max_rps=20000),
                )
                graph.add_component(component)

                # Extract backend set members for dependency inference
                try:
                    for bs_name, backend_set in (lb.backend_sets or {}).items():
                        for backend in (backend_set.backends or []):
                            # OCI backends reference IP:port; try to map back to instance
                            target_ip = backend.ip_address or ""
                            if target_ip:
                                self._lb_backends.setdefault(comp_id, []).append(target_ip)
                except Exception:
                    pass
        except Exception as exc:
            self._warnings.append(f"OCI Load Balancer scan error: {exc}")

    def _scan_vcn(self, graph: InfraGraph, config: dict) -> None:
        """Discover OCI Virtual Cloud Networks and populate subnet->VCN mapping."""
        try:
            import oci

            client = oci.core.VirtualNetworkClient(config)

            # List VCNs
            vcns = oci.pagination.list_call_get_all_results(
                client.list_vcns,
                compartment_id=self.compartment_id,
                lifecycle_state="AVAILABLE",
            ).data

            for vcn in vcns:
                vcn_id = vcn.id or ""

            # List subnets to build subnet->VCN mapping
            subnets = oci.pagination.list_call_get_all_results(
                client.list_subnets,
                compartment_id=self.compartment_id,
                lifecycle_state="AVAILABLE",
            ).data

            for subnet in subnets:
                subnet_id = subnet.id or ""
                vcn_id = subnet.vcn_id or ""
                if subnet_id and vcn_id:
                    self._subnet_vcn[subnet_id] = vcn_id
        except Exception as exc:
            self._warnings.append(f"OCI VCN scan error: {exc}")

    def _scan_object_storage(self, graph: InfraGraph, config: dict) -> None:
        """Discover OCI Object Storage buckets."""
        try:
            import oci

            client = oci.object_storage.ObjectStorageClient(config)

            namespace = client.get_namespace().data

            buckets = oci.pagination.list_call_get_all_results(
                client.list_buckets,
                namespace_name=namespace,
                compartment_id=self.compartment_id,
            ).data

            region = config.get("region", "us-ashburn-1")

            for bucket in buckets:
                bucket_name = bucket.name or ""
                comp_id = f"oci-bucket-{bucket_name}"

                component = Component(
                    id=comp_id,
                    name=bucket_name,
                    type=ComponentType.STORAGE,
                    host=f"{namespace}.objectstorage.{region}.oci.customer-oci.com",
                    port=443,
                    replicas=3,  # OCI Object Storage is inherently replicated
                    region=RegionConfig(region=region),
                    capacity=Capacity(max_disk_gb=1024 * 1024),
                    security=SecurityProfile(
                        encryption_at_rest=True,
                        encryption_in_transit=True,
                    ),
                    tags=[f"storage_tier:{bucket.storage_tier or 'Standard'}"],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"OCI Object Storage scan error: {exc}")

    # ── Dependency Inference ────────────────────────────────────────────────

    def _infer_dependencies(self, graph: InfraGraph) -> None:
        """Infer dependencies from VCN membership and LB backend relationships."""
        # LB -> Compute (via backend IP matching)
        compute_by_ip: dict[str, str] = {}
        for comp_id, comp in graph.components.items():
            if comp.type == ComponentType.APP_SERVER and comp.host:
                compute_by_ip[comp.host] = comp_id

        for lb_comp_id, backend_ips in self._lb_backends.items():
            if lb_comp_id not in graph.components:
                continue
            for ip in backend_ips:
                target_id = compute_by_ip.get(ip)
                if target_id:
                    dep = Dependency(
                        source_id=lb_comp_id,
                        target_id=target_id,
                        dependency_type="routes_to",
                        protocol="http",
                        port=80,
                    )
                    graph.add_dependency(dep)

        # Within-VCN: Compute -> DB dependencies
        for vcn_id, members in self._vcn_members.items():
            members_set = set(members)
            compute_members = [m for m in members_set if m in graph.components and
                               graph.components[m].type == ComponentType.APP_SERVER]
            db_members = [m for m in members_set if m in graph.components and
                          graph.components[m].type == ComponentType.DATABASE]

            for comp in compute_members:
                for db in db_members:
                    db_obj = graph.components[db]
                    dep = Dependency(
                        source_id=comp,
                        target_id=db,
                        dependency_type="requires",
                        protocol="tcp",
                        port=db_obj.port,
                    )
                    graph.add_dependency(dep)
