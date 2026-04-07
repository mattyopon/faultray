# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""On-premises / generic infrastructure discovery scanner.

Supports multiple input methods:
- CMDB CSV or JSON import
- NetBox API (via pynetbox)
- nmap XML scan result import
- Manual YAML definition (passthrough to model loader)

Usage:
    pip install 'faultray[onprem]'

    # From NetBox API
    scanner = OnPremScanner.from_netbox("http://netbox.local", token="xxx")
    result = scanner.scan()

    # From CMDB CSV
    scanner = OnPremScanner.from_cmdb_csv("inventory.csv")
    result = scanner.scan()

    # From nmap XML
    scanner = OnPremScanner.from_nmap_xml("nmap_scan.xml")
    result = scanner.scan()
"""

from __future__ import annotations

import csv
import json
import logging
import time
import defusedxml.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

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

# Well-known port to (ComponentType, service_name) mapping
_PORT_TYPE_MAP: dict[int, tuple[ComponentType, str]] = {
    22: (ComponentType.APP_SERVER, "ssh"),
    25: (ComponentType.APP_SERVER, "smtp"),
    53: (ComponentType.DNS, "dns"),
    80: (ComponentType.WEB_SERVER, "http"),
    443: (ComponentType.WEB_SERVER, "https"),
    3306: (ComponentType.DATABASE, "mysql"),
    5432: (ComponentType.DATABASE, "postgresql"),
    6379: (ComponentType.CACHE, "redis"),
    11211: (ComponentType.CACHE, "memcached"),
    27017: (ComponentType.DATABASE, "mongodb"),
    5672: (ComponentType.QUEUE, "rabbitmq"),
    9092: (ComponentType.QUEUE, "kafka"),
    8080: (ComponentType.APP_SERVER, "http-alt"),
    8443: (ComponentType.APP_SERVER, "https-alt"),
}

# CSV field name variants to canonical names
_CSV_FIELD_MAP: dict[str, str] = {
    "hostname": "name",
    "host_name": "name",
    "server_name": "name",
    "ip": "host",
    "ip_address": "host",
    "ipaddress": "host",
    "address": "host",
    "type": "component_type",
    "role": "component_type",
    "service_type": "component_type",
    "environment": "region",
    "env": "region",
    "datacenter": "region",
    "data_center": "region",
    "site": "region",
    "port": "port",
    "service_port": "port",
}


class OnPremInputMode(str, Enum):
    """Source of on-premises infrastructure data."""

    NETBOX = "netbox"
    CMDB_CSV = "cmdb_csv"
    CMDB_JSON = "cmdb_json"
    NMAP_XML = "nmap_xml"
    YAML = "yaml"


def _normalize_component_type(raw: str) -> ComponentType:
    """Map free-text component type string to ComponentType enum."""
    raw_lower = raw.strip().lower().replace("-", "_").replace(" ", "_")
    mapping = {
        "web": ComponentType.WEB_SERVER,
        "web_server": ComponentType.WEB_SERVER,
        "webserver": ComponentType.WEB_SERVER,
        "nginx": ComponentType.WEB_SERVER,
        "apache": ComponentType.WEB_SERVER,
        "app": ComponentType.APP_SERVER,
        "app_server": ComponentType.APP_SERVER,
        "application": ComponentType.APP_SERVER,
        "api": ComponentType.APP_SERVER,
        "db": ComponentType.DATABASE,
        "database": ComponentType.DATABASE,
        "mysql": ComponentType.DATABASE,
        "postgres": ComponentType.DATABASE,
        "postgresql": ComponentType.DATABASE,
        "oracle": ComponentType.DATABASE,
        "sqlserver": ComponentType.DATABASE,
        "mssql": ComponentType.DATABASE,
        "mongodb": ComponentType.DATABASE,
        "cache": ComponentType.CACHE,
        "redis": ComponentType.CACHE,
        "memcached": ComponentType.CACHE,
        "lb": ComponentType.LOAD_BALANCER,
        "load_balancer": ComponentType.LOAD_BALANCER,
        "haproxy": ComponentType.LOAD_BALANCER,
        "nginx_lb": ComponentType.LOAD_BALANCER,
        "storage": ComponentType.STORAGE,
        "nas": ComponentType.STORAGE,
        "san": ComponentType.STORAGE,
        "nfs": ComponentType.STORAGE,
        "queue": ComponentType.QUEUE,
        "mq": ComponentType.QUEUE,
        "rabbitmq": ComponentType.QUEUE,
        "kafka": ComponentType.QUEUE,
        "dns": ComponentType.DNS,
        "bind": ComponentType.DNS,
    }
    return mapping.get(raw_lower, ComponentType.APP_SERVER)


@dataclass
class OnPremDiscoveryResult:
    """Result of an on-premises infrastructure discovery scan."""

    source: str
    components_found: int
    dependencies_inferred: int
    graph: InfraGraph
    warnings: list[str] = field(default_factory=list)
    scan_duration_seconds: float = 0.0


class OnPremScanner:
    """Discover on-premises infrastructure from various data sources.

    Supports CMDB (CSV/JSON), NetBox API, nmap XML scan results, and manual YAML.
    Normalizes all sources into a standard InfraGraph.

    Use factory class methods to create instances for specific input modes:
    - :meth:`from_netbox`
    - :meth:`from_cmdb_csv`
    - :meth:`from_cmdb_json`
    - :meth:`from_nmap_xml`
    """

    def __init__(
        self,
        mode: OnPremInputMode,
        source: str,
        netbox_url: str | None = None,
        netbox_token: str | None = None,
        default_region: str = "onprem",
        filter_site: str | None = None,
        filter_rack: str | None = None,
    ) -> None:
        self.mode = mode
        self.source = source
        self.netbox_url = netbox_url
        self.netbox_token = netbox_token
        self.default_region = default_region
        self.filter_site = filter_site
        self.filter_rack = filter_rack
        self._warnings: list[str] = []

    # ── Factory methods ───────────────────────────────────────────────────────

    @classmethod
    def from_netbox(
        cls,
        url: str,
        token: str,
        default_region: str = "onprem",
        filter_site: str | None = None,
    ) -> "OnPremScanner":
        """Create scanner for NetBox API source."""
        return cls(
            mode=OnPremInputMode.NETBOX,
            source=url,
            netbox_url=url,
            netbox_token=token,
            default_region=default_region,
            filter_site=filter_site,
        )

    @classmethod
    def from_cmdb_csv(
        cls,
        csv_path: str | Path,
        default_region: str = "onprem",
    ) -> "OnPremScanner":
        """Create scanner for CMDB CSV file source."""
        return cls(
            mode=OnPremInputMode.CMDB_CSV,
            source=str(csv_path),
            default_region=default_region,
        )

    @classmethod
    def from_cmdb_json(
        cls,
        json_path: str | Path,
        default_region: str = "onprem",
    ) -> "OnPremScanner":
        """Create scanner for CMDB JSON file source."""
        return cls(
            mode=OnPremInputMode.CMDB_JSON,
            source=str(json_path),
            default_region=default_region,
        )

    @classmethod
    def from_nmap_xml(
        cls,
        xml_path: str | Path,
        default_region: str = "onprem",
    ) -> "OnPremScanner":
        """Create scanner for nmap XML scan result."""
        return cls(
            mode=OnPremInputMode.NMAP_XML,
            source=str(xml_path),
            default_region=default_region,
        )

    # ── Main scan dispatch ────────────────────────────────────────────────────

    def scan(self) -> OnPremDiscoveryResult:
        """Run discovery scan based on configured input mode.

        Returns an OnPremDiscoveryResult with the discovered InfraGraph.
        """
        start = time.monotonic()
        graph = InfraGraph()

        try:
            if self.mode == OnPremInputMode.NETBOX:
                self._scan_netbox(graph)
            elif self.mode == OnPremInputMode.CMDB_CSV:
                self._scan_cmdb_csv(graph)
            elif self.mode == OnPremInputMode.CMDB_JSON:
                self._scan_cmdb_json(graph)
            elif self.mode == OnPremInputMode.NMAP_XML:
                self._scan_nmap_xml(graph)
            else:
                self._warnings.append(f"Unsupported input mode: {self.mode}")
        except Exception as exc:
            msg = f"OnPrem scan failed ({self.mode}): {exc}"
            logger.error(msg)
            self._warnings.append(msg)

        try:
            self._infer_dependencies(graph)
        except Exception as exc:
            msg = f"Failed to infer on-prem dependencies: {exc}"
            logger.warning(msg)
            self._warnings.append(msg)

        duration = time.monotonic() - start
        dep_count = len(graph.all_dependency_edges())

        return OnPremDiscoveryResult(
            source=self.source,
            components_found=len(graph.components),
            dependencies_inferred=dep_count,
            graph=graph,
            warnings=list(self._warnings),
            scan_duration_seconds=round(duration, 2),
        )

    # ── NetBox ────────────────────────────────────────────────────────────────

    def _scan_netbox(self, graph: InfraGraph) -> None:
        """Discover devices and VMs from NetBox API."""
        try:
            import pynetbox
        except ImportError:
            raise RuntimeError(
                "pynetbox is required for NetBox discovery. "
                "Install with: pip install 'faultray[onprem]'"
            )

        nb = pynetbox.api(self.netbox_url, token=self.netbox_token)

        # Discover physical devices
        try:
            device_filters: dict[str, Any] = {"status": "active"}
            if self.filter_site:
                device_filters["site"] = self.filter_site
            if self.filter_rack:
                device_filters["rack"] = self.filter_rack

            devices = nb.dcim.devices.filter(**device_filters)
            for device in devices:
                self._add_netbox_device(graph, device, is_vm=False)
        except Exception as exc:
            self._warnings.append(f"NetBox devices scan error: {exc}")

        # Discover virtual machines
        try:
            vm_filters: dict[str, Any] = {"status": "active"}
            if self.filter_site:
                vm_filters["site"] = self.filter_site

            vms = nb.virtualization.virtual_machines.filter(**vm_filters)
            for vm in vms:
                self._add_netbox_device(graph, vm, is_vm=True)
        except Exception as exc:
            self._warnings.append(f"NetBox VMs scan error: {exc}")

        # Discover IP addresses for dependency inference
        try:
            ips = nb.ipam.ip_addresses.all()
            for ip in ips:
                pass  # IP data already captured via device primary_ip
        except Exception:
            pass

    def _add_netbox_device(self, graph: InfraGraph, device: Any, is_vm: bool) -> None:
        """Add a NetBox device or VM as an InfraGraph component."""
        device_id = str(getattr(device, "id", ""))
        name = str(getattr(device, "name", "") or device_id)
        prefix = "vm" if is_vm else "dev"
        comp_id = f"onprem-{prefix}-{device_id}"

        # Get primary IP
        host = ""
        primary_ip = getattr(device, "primary_ip", None)
        if primary_ip and hasattr(primary_ip, "address"):
            addr = str(primary_ip.address or "")
            host = addr.split("/")[0]  # Strip prefix length

        # Determine component type from device role
        comp_type = ComponentType.APP_SERVER
        role = getattr(device, "device_role", None) or getattr(device, "role", None)
        if role and hasattr(role, "name"):
            comp_type = _normalize_component_type(str(role.name or ""))

        # Region from site
        site = getattr(device, "site", None)
        site_name = str(site.name) if site and hasattr(site, "name") else self.default_region

        # CPU/memory for VMs
        vcpus = getattr(device, "vcpus", None) or 1
        memory = getattr(device, "memory", None) or 1024

        # Tags from NetBox tags
        nb_tags = [str(t) for t in (getattr(device, "tags", []) or [])]

        component = Component(
            id=comp_id,
            name=name,
            type=comp_type,
            host=host,
            port=0,
            replicas=1,
            region=RegionConfig(region=site_name),
            capacity=Capacity(
                max_connections=int(1000 * float(vcpus)),
                max_rps=int(5000 * float(vcpus)),
                max_memory_mb=float(memory),
            ),
            tags=nb_tags + (["virtual_machine"] if is_vm else ["physical"]),
        )
        graph.add_component(component)

    # ── CMDB CSV ──────────────────────────────────────────────────────────────

    def _scan_cmdb_csv(self, graph: InfraGraph) -> None:
        """Import infrastructure from a CMDB CSV file.

        Expected columns (flexible names accepted):
            name/hostname, host/ip_address, type/role, region/datacenter, port
        """
        path = Path(self.source)
        if not path.exists():
            raise FileNotFoundError(f"CMDB CSV file not found: {path}")

        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                self._warnings.append(f"Empty CSV file: {path}")
                return

            # Normalize field names
            field_map = self._build_field_map(list(reader.fieldnames))

            for i, row in enumerate(reader):
                try:
                    normalized = self._normalize_csv_row(row, field_map)
                    comp = self._row_to_component(normalized, i)
                    if comp:
                        graph.add_component(comp)
                except Exception as exc:
                    self._warnings.append(f"CSV row {i + 1} error: {exc}")

    def _build_field_map(self, fieldnames: list[str]) -> dict[str, str]:
        """Map actual CSV field names to canonical names."""
        result: dict[str, str] = {}
        for fn in fieldnames:
            canonical = _CSV_FIELD_MAP.get(fn.lower().strip(), fn.lower().strip())
            result[fn] = canonical
        return result

    def _normalize_csv_row(self, row: dict[str, str], field_map: dict[str, str]) -> dict[str, str]:
        """Return a dict with canonical field names."""
        return {field_map.get(k, k.lower().strip()): v.strip() for k, v in row.items() if v}

    def _row_to_component(self, row: dict[str, str], idx: int) -> Component | None:
        """Convert a normalized CSV row to a Component."""
        name = row.get("name", "")
        if not name:
            return None

        comp_id = f"onprem-cmdb-{name.replace(' ', '_').lower()}-{idx}"
        host = row.get("host", "")
        region = row.get("region", self.default_region)

        raw_type = row.get("component_type", "app_server")
        comp_type = _normalize_component_type(raw_type)

        port_str = row.get("port", "0")
        try:
            port = int(port_str)
        except (ValueError, TypeError):
            port = 0

        replicas_str = row.get("replicas", "1")
        try:
            replicas = int(replicas_str)
        except (ValueError, TypeError):
            replicas = 1

        # Collect extra fields as tags
        known_fields = {"name", "host", "region", "component_type", "port", "replicas", "description"}
        extra_tags = [f"{k}:{v}" for k, v in row.items() if k not in known_fields and v]

        return Component(
            id=comp_id,
            name=name,
            type=comp_type,
            host=host,
            port=port,
            replicas=replicas,
            region=RegionConfig(region=region),
            capacity=Capacity(max_connections=1000, max_rps=5000),
            tags=extra_tags,
        )

    # ── CMDB JSON ─────────────────────────────────────────────────────────────

    def _scan_cmdb_json(self, graph: InfraGraph) -> None:
        """Import infrastructure from a CMDB JSON file.

        Accepts either a list of objects or a dict with a "hosts"/"servers"/"devices" key.

        Each object may have:
            name, host/ip, type/role, region/datacenter/site, port, replicas, tags
        """
        path = Path(self.source)
        if not path.exists():
            raise FileNotFoundError(f"CMDB JSON file not found: {path}")

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        # Normalize to a flat list
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            for key in ("hosts", "servers", "devices", "components", "inventory"):
                if key in data:
                    items = data[key]
                    break
            else:
                # Try root-level object as single item
                items = [data]
        else:
            self._warnings.append("JSON CMDB: unexpected top-level type, expected list or dict")
            return

        for i, item in enumerate(items):
            try:
                comp = self._json_item_to_component(item, i)
                if comp:
                    graph.add_component(comp)
            except Exception as exc:
                self._warnings.append(f"JSON CMDB item {i}: {exc}")

    def _json_item_to_component(self, item: dict[str, Any], idx: int) -> Component | None:
        """Convert a JSON CMDB item to a Component."""
        if not isinstance(item, dict):
            return None

        name = str(item.get("name") or item.get("hostname") or item.get("server_name") or "")
        if not name:
            return None

        comp_id = f"onprem-json-{name.replace(' ', '_').lower()}-{idx}"

        host = str(
            item.get("host") or item.get("ip") or
            item.get("ip_address") or item.get("address") or ""
        )
        region = str(
            item.get("region") or item.get("datacenter") or
            item.get("site") or item.get("environment") or
            self.default_region
        )
        raw_type = str(
            item.get("type") or item.get("role") or
            item.get("component_type") or "app_server"
        )
        comp_type = _normalize_component_type(raw_type)

        try:
            port = int(item.get("port") or 0)
        except (ValueError, TypeError):
            port = 0

        try:
            replicas = int(item.get("replicas") or 1)
        except (ValueError, TypeError):
            replicas = 1

        raw_tags = item.get("tags") or []
        if isinstance(raw_tags, list):
            tags = [str(t) for t in raw_tags]
        elif isinstance(raw_tags, dict):
            tags = [f"{k}:{v}" for k, v in raw_tags.items()]
        else:
            tags = []

        # Security flags from JSON
        security = SecurityProfile(
            encryption_at_rest=bool(item.get("encryption_at_rest", False)),
            encryption_in_transit=bool(item.get("encryption_in_transit", False)),
            backup_enabled=bool(item.get("backup_enabled", False)),
        )

        return Component(
            id=comp_id,
            name=name,
            type=comp_type,
            host=host,
            port=port,
            replicas=replicas,
            region=RegionConfig(region=region),
            capacity=Capacity(
                max_connections=int(item.get("max_connections") or 1000),
                max_rps=int(item.get("max_rps") or 5000),
                max_memory_mb=float(item.get("memory_mb") or 8192),
            ),
            security=security,
            tags=tags,
        )

    # ── nmap XML ──────────────────────────────────────────────────────────────

    def _scan_nmap_xml(self, graph: InfraGraph) -> None:
        """Import infrastructure from an nmap XML scan result.

        Parses nmap -oX output to discover hosts and open ports,
        then infers component types from well-known port numbers.
        """
        path = Path(self.source)
        if not path.exists():
            raise FileNotFoundError(f"nmap XML file not found: {path}")

        tree = ET.parse(path)
        root = tree.getroot()

        for host_el in root.findall("host"):
            status = host_el.find("status")
            if status is None or status.get("state") != "up":
                continue

            # Get host address
            addr_el = host_el.find("address[@addrtype='ipv4']")
            if addr_el is None:
                addr_el = host_el.find("address[@addrtype='ipv6']")
            if addr_el is None:
                continue

            ip = addr_el.get("addr", "")

            # Get hostname
            hostname = ip
            hostnames_el = host_el.find("hostnames")
            if hostnames_el is not None:
                for hn in hostnames_el.findall("hostname"):
                    if hn.get("type") in ("user", "PTR"):
                        hostname = hn.get("name", ip)
                        break

            # Collect open ports
            ports_el = host_el.find("ports")
            if ports_el is None:
                continue

            open_ports: list[tuple[int, str]] = []  # (port, service_name)
            for port_el in ports_el.findall("port"):
                state_el = port_el.find("state")
                if state_el is None or state_el.get("state") != "open":
                    continue
                portid = int(port_el.get("portid") or 0)
                svc_el = port_el.find("service")
                svc_name = svc_el.get("name", "") if svc_el is not None else ""
                open_ports.append((portid, svc_name))

            if not open_ports:
                continue

            # Create one component per host, using the most-significant port
            # to determine component type
            comp_type, primary_service = self._infer_type_from_ports(open_ports)
            safe_name = hostname.replace(".", "_").replace("-", "_")
            comp_id = f"onprem-nmap-{safe_name}-{ip.replace('.', '_')}"

            port_tags = [f"port:{p}" for p, _ in open_ports[:10]]  # Cap at 10

            component = Component(
                id=comp_id,
                name=hostname,
                type=comp_type,
                host=ip,
                port=open_ports[0][0] if open_ports else 0,
                replicas=1,
                region=RegionConfig(region=self.default_region),
                capacity=Capacity(max_connections=1000, max_rps=5000),
                tags=["nmap_discovered"] + port_tags,
            )
            graph.add_component(component)

    def _infer_type_from_ports(
        self,
        ports: list[tuple[int, str]],
    ) -> tuple[ComponentType, str]:
        """Infer component type from list of open (port, service_name) pairs.

        Prioritizes known service ports; falls back to APP_SERVER.
        """
        # Priority order: DB > Cache > Queue > LB > WEB > APP
        priority_order = [
            ComponentType.DATABASE,
            ComponentType.CACHE,
            ComponentType.QUEUE,
            ComponentType.LOAD_BALANCER,
            ComponentType.WEB_SERVER,
            ComponentType.DNS,
            ComponentType.APP_SERVER,
        ]

        found: dict[ComponentType, str] = {}
        for portid, svc_name in ports:
            if portid in _PORT_TYPE_MAP:
                ct, service = _PORT_TYPE_MAP[portid]
                if ct not in found:
                    found[ct] = service

        for ct in priority_order:
            if ct in found:
                return ct, found[ct]

        # Fallback: use first port's service name
        return ComponentType.APP_SERVER, ports[0][1] if ports else "unknown"

    # ── Dependency Inference ────────────────────────────────────────────────

    def _infer_dependencies(self, graph: InfraGraph) -> None:
        """Infer dependencies by matching component hosts and known service ports.

        Logic:
        - Load balancers -> app servers / web servers in the same region
        - App servers -> databases and caches in the same region
        """
        # Group components by region
        by_region: dict[str, list[str]] = {}
        for comp_id, comp in graph.components.items():
            region = comp.region.region if comp.region else self.default_region
            by_region.setdefault(region, []).append(comp_id)

        for region, members in by_region.items():
            if len(members) < 2:
                continue

            lbs = [m for m in members if m in graph.components and
                   graph.components[m].type == ComponentType.LOAD_BALANCER]
            web = [m for m in members if m in graph.components and
                   graph.components[m].type == ComponentType.WEB_SERVER]
            apps = [m for m in members if m in graph.components and
                    graph.components[m].type == ComponentType.APP_SERVER]
            dbs = [m for m in members if m in graph.components and
                   graph.components[m].type == ComponentType.DATABASE]
            caches = [m for m in members if m in graph.components and
                      graph.components[m].type == ComponentType.CACHE]
            queues = [m for m in members if m in graph.components and
                      graph.components[m].type == ComponentType.QUEUE]

            # LB -> web/app
            for lb in lbs:
                for target in web + apps:
                    dep = Dependency(
                        source_id=lb,
                        target_id=target,
                        dependency_type="routes_to",
                        protocol="http",
                        port=80,
                    )
                    graph.add_dependency(dep)

            # App/web -> DB
            for src in apps + web:
                for db in dbs:
                    db_comp = graph.components[db]
                    dep = Dependency(
                        source_id=src,
                        target_id=db,
                        dependency_type="requires",
                        protocol="tcp",
                        port=db_comp.port,
                    )
                    graph.add_dependency(dep)

            # App/web -> cache
            for src in apps + web:
                for cache in caches:
                    cache_comp = graph.components[cache]
                    dep = Dependency(
                        source_id=src,
                        target_id=cache,
                        dependency_type="requires",
                        protocol="tcp",
                        port=cache_comp.port,
                    )
                    graph.add_dependency(dep)

            # App -> queue
            for src in apps + web:
                for queue in queues:
                    queue_comp = graph.components[queue]
                    dep = Dependency(
                        source_id=src,
                        target_id=queue,
                        dependency_type="publishes_to",
                        protocol="tcp",
                        port=queue_comp.port,
                    )
                    graph.add_dependency(dep)
