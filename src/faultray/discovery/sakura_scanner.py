# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Sakura Cloud infrastructure auto-discovery scanner.

Connects to Sakura Cloud via REST API to discover infrastructure resources
and generates a complete InfraGraph with components and dependencies.

Usage:
    pip install 'faultray[sakura]'
    scanner = SakuraScanner(token="xxx", secret="yyy", zone="tk1v")
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
    RegionConfig,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

# Sakura Cloud API base URL
_SAKURA_API_BASE = "https://secure.sakura.ad.jp/cloud/zone/{zone}/api/cloud/1.1"

# Mapping from Sakura service type to FaultRay ComponentType
SAKURA_TYPE_MAP: dict[str, ComponentType] = {
    "server": ComponentType.APP_SERVER,
    "disk": ComponentType.STORAGE,
    "load_balancer": ComponentType.LOAD_BALANCER,
    "database": ComponentType.DATABASE,
    "switch": ComponentType.CUSTOM,
    "router": ComponentType.CUSTOM,
    "vpc_router": ComponentType.CUSTOM,
}

# Database plan to ComponentType mapping
_DB_PLAN_MAP: dict[str, ComponentType] = {
    "MariaDB": ComponentType.DATABASE,
    "PostgreSQL": ComponentType.DATABASE,
    "MySQL": ComponentType.DATABASE,
}


def _check_requests() -> None:
    """Check that requests library is importable."""
    try:
        import requests  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "requests is required for Sakura Cloud scanning. "
            "Install with: pip install 'faultray[sakura]'"
        )


def _make_session(token: str, secret: str):  # type: ignore[return]
    """Create an authenticated requests.Session for Sakura Cloud API."""
    import requests

    session = requests.Session()
    session.auth = (token, secret)
    session.headers.update({
        "Accept": "application/json",
        "Content-Type": "application/json",
    })
    return session


@dataclass
class SakuraDiscoveryResult:
    """Result of a Sakura Cloud infrastructure discovery scan."""

    zone: str
    components_found: int
    dependencies_inferred: int
    graph: InfraGraph
    warnings: list[str] = field(default_factory=list)
    scan_duration_seconds: float = 0.0


class SakuraScanner:
    """Discover Sakura Cloud infrastructure and generate InfraGraph automatically.

    Authenticates with Sakura Cloud API using API token + secret.
    Scans servers, disks, load balancers, databases, switches, and VPC routers,
    then infers dependencies from switch connections.

    Args:
        token: Sakura Cloud API token.
        secret: Sakura Cloud API secret.
        zone: Sakura Cloud zone ID (e.g. "tk1v", "is1b", "os1").
    """

    def __init__(
        self,
        token: str,
        secret: str,
        zone: str = "tk1v",
    ) -> None:
        self.token = token
        self.secret = secret
        self.zone = zone
        self._base_url = _SAKURA_API_BASE.format(zone=zone)
        self._warnings: list[str] = []
        # Switch ID -> list of component IDs connected to that switch
        self._switch_members: dict[str, list[str]] = {}
        # Component ID -> list of switch IDs it belongs to
        self._component_switches: dict[str, list[str]] = {}

    def scan(self) -> SakuraDiscoveryResult:
        """Run a full Sakura Cloud infrastructure scan.

        Returns a SakuraDiscoveryResult with the discovered InfraGraph.
        """
        _check_requests()

        start = time.monotonic()
        graph = InfraGraph()
        session = _make_session(self.token, self.secret)

        scanners = [
            ("Servers", lambda g: self._scan_servers(g, session)),
            ("Disks", lambda g: self._scan_disks(g, session)),
            ("LoadBalancers", lambda g: self._scan_load_balancers(g, session)),
            ("Databases", lambda g: self._scan_databases(g, session)),
            ("Switches", lambda g: self._scan_switches(g, session)),
            ("VPCRouters", lambda g: self._scan_vpc_routers(g, session)),
        ]

        for name, scanner_fn in scanners:
            try:
                scanner_fn(graph)
            except RuntimeError:
                raise  # Re-raise library import errors
            except Exception as exc:
                msg = f"Failed to scan Sakura {name}: {exc}"
                logger.warning(msg)
                self._warnings.append(msg)

        try:
            self._infer_dependencies(graph)
        except Exception as exc:
            msg = f"Failed to infer Sakura dependencies: {exc}"
            logger.warning(msg)
            self._warnings.append(msg)

        duration = time.monotonic() - start
        dep_count = len(graph.all_dependency_edges())

        return SakuraDiscoveryResult(
            zone=self.zone,
            components_found=len(graph.components),
            dependencies_inferred=dep_count,
            graph=graph,
            warnings=list(self._warnings),
            scan_duration_seconds=round(duration, 2),
        )

    # ── Individual Resource Scanners ─────────────────────────────────────────

    def _get(self, session, path: str) -> dict:  # type: ignore[no-untyped-def]
        """Make a GET request to the Sakura Cloud API."""
        url = f"{self._base_url}/{path}"
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    def _scan_servers(self, graph: InfraGraph, session) -> None:  # type: ignore[no-untyped-def]
        """Discover Sakura Cloud servers."""
        try:
            data = self._get(session, "server")
            for server in data.get("Servers", []):
                if server.get("Availability") not in ("available", "migrating"):
                    continue

                server_id = server.get("ID", "")
                name = server.get("Name", server_id)
                comp_id = f"sakura-server-{server_id}"

                # Extract IP from interfaces
                host = ""
                ifaces = server.get("Interfaces", [])
                switch_ids: list[str] = []
                for iface in ifaces:
                    if iface.get("IPAddress"):
                        host = iface["IPAddress"]
                    sw = iface.get("Switch", {})
                    if sw and sw.get("ID"):
                        sw_id = str(sw["ID"])
                        switch_ids.append(sw_id)
                        self._switch_members.setdefault(sw_id, []).append(comp_id)

                self._component_switches[comp_id] = switch_ids

                # Server plan info
                plan = server.get("ServerPlan", {})
                cpu = plan.get("CPU", 1)
                memory_gb = plan.get("MemoryMB", 1024) // 1024

                component = Component(
                    id=comp_id,
                    name=name,
                    type=ComponentType.APP_SERVER,
                    host=host,
                    port=0,
                    replicas=1,
                    region=RegionConfig(region=self.zone),
                    capacity=Capacity(
                        max_connections=1000 * cpu,
                        max_rps=5000 * cpu,
                        max_memory_mb=float(memory_gb * 1024),
                    ),
                    tags=[f"cpu:{cpu}", f"memory_gb:{memory_gb}"],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"Sakura server scan error: {exc}")

    def _scan_disks(self, graph: InfraGraph, session) -> None:  # type: ignore[no-untyped-def]
        """Discover Sakura Cloud disks."""
        try:
            data = self._get(session, "disk")
            for disk in data.get("Disks", []):
                if disk.get("Availability") != "available":
                    continue

                disk_id = disk.get("ID", "")
                name = disk.get("Name", disk_id)
                comp_id = f"sakura-disk-{disk_id}"
                size_gb = disk.get("SizeMB", 20480) // 1024

                component = Component(
                    id=comp_id,
                    name=name,
                    type=ComponentType.STORAGE,
                    host="",
                    port=0,
                    replicas=1,
                    region=RegionConfig(region=self.zone),
                    capacity=Capacity(max_disk_gb=float(size_gb)),
                    tags=[f"size_gb:{size_gb}"],
                )
                graph.add_component(component)

                # Disk attached to server -> create dependency
                server_info = disk.get("Server")
                if server_info and server_info.get("ID"):
                    server_comp_id = f"sakura-server-{server_info['ID']}"
                    dep = Dependency(
                        source_id=server_comp_id,
                        target_id=comp_id,
                        dependency_type="uses",
                        protocol="block",
                        port=0,
                    )
                    graph.add_dependency(dep)
        except Exception as exc:
            self._warnings.append(f"Sakura disk scan error: {exc}")

    def _scan_load_balancers(self, graph: InfraGraph, session) -> None:  # type: ignore[no-untyped-def]
        """Discover Sakura Cloud load balancers."""
        try:
            data = self._get(session, "loadbalancer")
            for lb in data.get("LoadBalancers", []):
                lb_id = lb.get("ID", "")
                name = lb.get("Name", lb_id)
                comp_id = f"sakura-lb-{lb_id}"

                vip = lb.get("Remark", {}).get("Servers", [{}])
                host = vip[0].get("IPAddress", "") if vip else ""

                # Track switch membership for dependency inference
                ifaces = lb.get("Interfaces", [])
                switch_ids: list[str] = []
                for iface in ifaces:
                    sw = iface.get("Switch", {})
                    if sw and sw.get("ID"):
                        sw_id = str(sw["ID"])
                        switch_ids.append(sw_id)
                        self._switch_members.setdefault(sw_id, []).append(comp_id)
                self._component_switches[comp_id] = switch_ids

                component = Component(
                    id=comp_id,
                    name=name,
                    type=ComponentType.LOAD_BALANCER,
                    host=host,
                    port=80,
                    replicas=1,
                    region=RegionConfig(region=self.zone),
                    capacity=Capacity(max_connections=50000, max_rps=20000),
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"Sakura load balancer scan error: {exc}")

    def _scan_databases(self, graph: InfraGraph, session) -> None:  # type: ignore[no-untyped-def]
        """Discover Sakura Cloud managed databases."""
        try:
            data = self._get(session, "database")
            for db in data.get("Databases", []):
                db_id = db.get("ID", "")
                name = db.get("Name", db_id)
                comp_id = f"sakura-db-{db_id}"

                settings = db.get("Settings", {})
                db_settings = settings.get("DBConf", {})
                db_type = db.get("Remark", {}).get("DBConf", {}).get("DatabaseName", "Database")
                comp_type = _DB_PLAN_MAP.get(db_type, ComponentType.DATABASE)

                host = db_settings.get("Common", {}).get("DefaultRoute", "")
                port_map = {"MariaDB": 3306, "PostgreSQL": 5432, "MySQL": 3306}
                port = port_map.get(db_type, 5432)

                # Track switch membership
                ifaces = db.get("Interfaces", [])
                switch_ids: list[str] = []
                for iface in ifaces:
                    sw = iface.get("Switch", {})
                    if sw and sw.get("ID"):
                        sw_id = str(sw["ID"])
                        switch_ids.append(sw_id)
                        self._switch_members.setdefault(sw_id, []).append(comp_id)
                self._component_switches[comp_id] = switch_ids

                component = Component(
                    id=comp_id,
                    name=name,
                    type=comp_type,
                    host=host,
                    port=port,
                    replicas=1,
                    region=RegionConfig(region=self.zone),
                    capacity=Capacity(max_connections=500, max_rps=2000),
                    security=SecurityProfile(encryption_at_rest=False),
                    tags=[f"db_type:{db_type}"],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"Sakura database scan error: {exc}")

    def _scan_switches(self, graph: InfraGraph, session) -> None:  # type: ignore[no-untyped-def]
        """Discover Sakura Cloud switches (for dependency inference context)."""
        try:
            data = self._get(session, "switch")
            for sw in data.get("Switches", []):
                sw_id = str(sw.get("ID", ""))
                if not sw_id:
                    continue
                # Populate switch_members with any directly listed servers
                for server in sw.get("Servers", []):
                    server_comp_id = f"sakura-server-{server.get('ID', '')}"
                    self._switch_members.setdefault(sw_id, []).append(server_comp_id)
        except Exception as exc:
            self._warnings.append(f"Sakura switch scan error: {exc}")

    def _scan_vpc_routers(self, graph: InfraGraph, session) -> None:  # type: ignore[no-untyped-def]
        """Discover Sakura Cloud VPC routers."""
        try:
            data = self._get(session, "vpcrouter")
            for vpc in data.get("VPCRouters", []):
                vpc_id = vpc.get("ID", "")
                name = vpc.get("Name", vpc_id)
                comp_id = f"sakura-vpc-{vpc_id}"

                settings = vpc.get("Settings", {})
                router_cfg = settings.get("Router", {})
                host = router_cfg.get("ExternalIPAddress", "")

                component = Component(
                    id=comp_id,
                    name=name,
                    type=ComponentType.CUSTOM,
                    host=host,
                    port=0,
                    replicas=1,
                    region=RegionConfig(region=self.zone),
                    capacity=Capacity(max_connections=10000),
                    tags=["vpc_router"],
                )
                graph.add_component(component)
        except Exception as exc:
            self._warnings.append(f"Sakura VPC router scan error: {exc}")

    # ── Dependency Inference ────────────────────────────────────────────────

    def _infer_dependencies(self, graph: InfraGraph) -> None:
        """Infer dependencies from switch membership.

        Components connected to the same switch are assumed to communicate,
        with load balancers or servers being sources and databases being targets.
        """
        # For each switch, find all members and infer LB->server, server->DB edges
        for sw_id, members in self._switch_members.items():
            # Deduplicate while preserving order
            members = list(dict.fromkeys(members))
            if len(members) < 2:
                continue

            lbs = [m for m in members if m in graph.components and
                   graph.components[m].type == ComponentType.LOAD_BALANCER]
            servers = [m for m in members if m in graph.components and
                       graph.components[m].type == ComponentType.APP_SERVER]
            dbs = [m for m in members if m in graph.components and
                   graph.components[m].type == ComponentType.DATABASE]
            storages = [m for m in members if m in graph.components and
                        graph.components[m].type == ComponentType.STORAGE]

            # LB -> servers
            for lb in lbs:
                for srv in servers:
                    dep = Dependency(
                        source_id=lb,
                        target_id=srv,
                        dependency_type="routes_to",
                        protocol="http",
                        port=80,
                    )
                    graph.add_dependency(dep)

            # Servers -> DBs
            for srv in servers:
                for db in dbs:
                    db_comp = graph.components[db]
                    dep = Dependency(
                        source_id=srv,
                        target_id=db,
                        dependency_type="requires",
                        protocol="tcp",
                        port=db_comp.port,
                    )
                    graph.add_dependency(dep)

            # Servers -> Storage (disks already linked directly; skip)
            # Any component -> storage via switch (only if no direct disk link exists)
            for srv in servers:
                for st in storages:
                    # Avoid duplicate: disk scanning already creates server->disk dep
                    pass
