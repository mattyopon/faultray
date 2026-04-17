# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Prometheus integration - discover and update infrastructure from Prometheus."""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse

import httpx

from faultray.model.components import (
    Component,
    ComponentType,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph


# Default PromQL queries for node_exporter metrics.
PROMQL_CPU = (
    '100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'
)
PROMQL_MEMORY = (
    "(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100"
)
PROMQL_DISK = (
    '(1 - node_filesystem_avail_bytes{mountpoint="/"}'
    ' / node_filesystem_size_bytes{mountpoint="/"}) * 100'
)
PROMQL_NETWORK_CONNECTIONS = "node_netstat_Tcp_CurrEstab"

PROMQL_MEMORY_TOTAL = "node_memory_MemTotal_bytes"
PROMQL_MEMORY_AVAILABLE = "node_memory_MemAvailable_bytes"
PROMQL_DISK_TOTAL = 'node_filesystem_size_bytes{mountpoint="/"}'
PROMQL_DISK_AVAIL = 'node_filesystem_avail_bytes{mountpoint="/"}'


def _parse_instance(instance: str) -> tuple[str, int]:
    """Extract host and port from a Prometheus ``instance`` label.

    The label typically looks like ``host:port``.  If no port is present the
    default ``0`` is returned.
    """
    if "://" not in instance:
        instance = f"http://{instance}"
    parsed = urlparse(instance)
    host = parsed.hostname or instance
    port = parsed.port or 0
    return host, port


def _safe_float(value: str | float | int, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class PrometheusClient:
    """Client for querying Prometheus and building/updating InfraGraphs."""

    def __init__(self, url: str = "http://localhost:9090", timeout: float = 30.0) -> None:
        self.url = url.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    async def query(self, promql: str) -> list[dict]:
        """Execute a PromQL instant query and return the result list.

        Each element is a dict with ``metric`` (label dict) and ``value``
        (a ``[timestamp, value_string]`` pair).
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.url}/api/v1/query",
                params={"query": promql},
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "success":
            raise RuntimeError(f"Prometheus query failed: {data}")

        return data.get("data", {}).get("result", [])

    async def get_targets(self) -> list[dict]:
        """Retrieve all active scrape targets from Prometheus."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{self.url}/api/v1/targets")
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "success":
            raise RuntimeError(f"Failed to fetch targets: {data}")

        active = data.get("data", {}).get("activeTargets", [])
        return active

    # ------------------------------------------------------------------
    # High-level discovery
    # ------------------------------------------------------------------

    async def discover_components(self) -> InfraGraph:
        """Auto-discover components from Prometheus targets and metrics.

        Each active target becomes a component.  Metrics for CPU, memory,
        disk, and network connections are fetched via PromQL and attached
        to the appropriate component.
        """
        graph = InfraGraph()

        # 1. Discover targets
        targets = await self.get_targets()

        # 2. Build a component for each active target
        instance_map: dict[str, str] = {}  # instance label -> component id
        for target in targets:
            labels = target.get("labels", {})
            instance = labels.get("instance", "")
            job = labels.get("job", "unknown")
            if not instance:
                continue

            host, port = _parse_instance(instance)
            comp_id = f"{host}:{port}" if port else host
            if comp_id in instance_map.values():
                continue

            instance_map[instance] = comp_id

            # Attempt to guess component type from the job name
            comp_type = self._guess_type(job, port)

            component = Component(
                id=comp_id,
                name=f"{job} ({instance})",
                type=comp_type,
                host=host,
                port=port,
                tags=[f"job:{job}"],
            )
            graph.add_component(component)

        # 3. Fetch metrics in parallel
        cpu_res, mem_res, disk_res, net_res, mem_total_res, mem_avail_res, disk_total_res, disk_avail_res = (
            await asyncio.gather(
                self.query(PROMQL_CPU),
                self.query(PROMQL_MEMORY),
                self.query(PROMQL_DISK),
                self.query(PROMQL_NETWORK_CONNECTIONS),
                self.query(PROMQL_MEMORY_TOTAL),
                self.query(PROMQL_MEMORY_AVAILABLE),
                self.query(PROMQL_DISK_TOTAL),
                self.query(PROMQL_DISK_AVAIL),
            )
        )

        # Index results by instance
        def _by_instance(results: list[dict]) -> dict[str, float]:
            out: dict[str, float] = {}
            for r in results:
                inst = r.get("metric", {}).get("instance", "")
                val = r.get("value", [None, "0"])
                out[inst] = _safe_float(val[1])
            return out

        cpu_map = _by_instance(cpu_res)
        mem_map = _by_instance(mem_res)
        disk_map = _by_instance(disk_res)
        net_map = _by_instance(net_res)
        mem_total_map = _by_instance(mem_total_res)
        mem_avail_map = _by_instance(mem_avail_res)
        disk_total_map = _by_instance(disk_total_res)
        disk_avail_map = _by_instance(disk_avail_res)

        # 4. Attach metrics to components
        for instance, comp_id in instance_map.items():
            comp = graph.get_component(comp_id)
            if not comp:
                continue

            mem_total_bytes = mem_total_map.get(instance, 0.0)
            mem_avail_bytes = mem_avail_map.get(instance, 0.0)
            mem_used_bytes = mem_total_bytes - mem_avail_bytes if mem_total_bytes else 0.0

            disk_total_bytes = disk_total_map.get(instance, 0.0)
            disk_avail_bytes = disk_avail_map.get(instance, 0.0)
            disk_used_bytes = disk_total_bytes - disk_avail_bytes if disk_total_bytes else 0.0

            comp.metrics = ResourceMetrics(
                cpu_percent=cpu_map.get(instance, 0.0),
                memory_percent=mem_map.get(instance, 0.0),
                memory_used_mb=mem_used_bytes / (1024 * 1024),
                memory_total_mb=mem_total_bytes / (1024 * 1024),
                disk_percent=disk_map.get(instance, 0.0),
                disk_used_gb=disk_used_bytes / (1024**3),
                disk_total_gb=disk_total_bytes / (1024**3),
                network_connections=int(net_map.get(instance, 0)),
            )

        return graph

    async def update_metrics(self, graph: InfraGraph) -> InfraGraph:
        """Update an existing graph with current Prometheus metrics.

        Components are matched by ``host:port``.  Any component that does
        not have a matching Prometheus instance is left unchanged.
        """
        # Build a lookup from "host:port" -> component
        comp_by_hp: dict[str, Component] = {}
        for comp in graph.components.values():
            key = f"{comp.host}:{comp.port}" if comp.port else comp.host
            comp_by_hp[key] = comp

        # Fetch all metrics
        cpu_res, mem_res, disk_res, net_res, mem_total_res, mem_avail_res, disk_total_res, disk_avail_res = (
            await asyncio.gather(
                self.query(PROMQL_CPU),
                self.query(PROMQL_MEMORY),
                self.query(PROMQL_DISK),
                self.query(PROMQL_NETWORK_CONNECTIONS),
                self.query(PROMQL_MEMORY_TOTAL),
                self.query(PROMQL_MEMORY_AVAILABLE),
                self.query(PROMQL_DISK_TOTAL),
                self.query(PROMQL_DISK_AVAIL),
            )
        )

        def _index(results: list[dict]) -> dict[str, float]:
            out: dict[str, float] = {}
            for r in results:
                inst = r.get("metric", {}).get("instance", "")
                val = r.get("value", [None, "0"])
                host, port = _parse_instance(inst)
                key = f"{host}:{port}" if port else host
                out[key] = _safe_float(val[1])
            return out

        cpu_map = _index(cpu_res)
        mem_map = _index(mem_res)
        disk_map = _index(disk_res)
        net_map = _index(net_res)
        mem_total_map = _index(mem_total_res)
        mem_avail_map = _index(mem_avail_res)
        disk_total_map = _index(disk_total_res)
        disk_avail_map = _index(disk_avail_res)

        for key, comp in comp_by_hp.items():
            if key not in cpu_map and key not in mem_map:
                continue  # no prometheus data for this component

            mem_total_bytes = mem_total_map.get(key, 0.0)
            mem_avail_bytes = mem_avail_map.get(key, 0.0)
            mem_used_bytes = mem_total_bytes - mem_avail_bytes if mem_total_bytes else 0.0

            disk_total_bytes = disk_total_map.get(key, 0.0)
            disk_avail_bytes = disk_avail_map.get(key, 0.0)
            disk_used_bytes = disk_total_bytes - disk_avail_bytes if disk_total_bytes else 0.0

            comp.metrics = ResourceMetrics(
                cpu_percent=cpu_map.get(key, comp.metrics.cpu_percent),
                memory_percent=mem_map.get(key, comp.metrics.memory_percent),
                memory_used_mb=mem_used_bytes / (1024 * 1024) if mem_total_bytes else comp.metrics.memory_used_mb,
                memory_total_mb=mem_total_bytes / (1024 * 1024) if mem_total_bytes else comp.metrics.memory_total_mb,
                disk_percent=disk_map.get(key, comp.metrics.disk_percent),
                disk_used_gb=disk_used_bytes / (1024**3) if disk_total_bytes else comp.metrics.disk_used_gb,
                disk_total_gb=disk_total_bytes / (1024**3) if disk_total_bytes else comp.metrics.disk_total_gb,
                network_connections=int(net_map.get(key, comp.metrics.network_connections)),
            )

        return graph

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _guess_type(job: str, port: int) -> ComponentType:
        """Best-effort guess of the component type from the job name or port."""
        job_lower = job.lower()

        if any(kw in job_lower for kw in ("nginx", "haproxy", "envoy", "traefik", "lb")):
            return ComponentType.LOAD_BALANCER
        if any(kw in job_lower for kw in ("postgres", "mysql", "mariadb", "mongo", "elasticsearch")):
            return ComponentType.DATABASE
        if any(kw in job_lower for kw in ("redis", "memcached", "cache")):
            return ComponentType.CACHE
        if any(kw in job_lower for kw in ("rabbit", "kafka", "nats", "queue")):
            return ComponentType.QUEUE
        if any(kw in job_lower for kw in ("minio", "s3", "ceph", "storage")):
            return ComponentType.STORAGE
        if any(kw in job_lower for kw in ("dns", "coredns", "bind")):
            return ComponentType.DNS
        if any(kw in job_lower for kw in ("web", "httpd", "apache")):
            return ComponentType.WEB_SERVER

        # Fall back to port-based heuristic
        from faultray.discovery.scanner import PORT_SERVICE_MAP

        if port in PORT_SERVICE_MAP:
            return PORT_SERVICE_MAP[port][0]

        return ComponentType.APP_SERVER
