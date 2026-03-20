# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""System scanner - discovers local infrastructure components."""

from __future__ import annotations

import logging
import socket

import psutil

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

# Well-known port to service type mappings
PORT_SERVICE_MAP: dict[int, tuple[ComponentType, str]] = {
    80: (ComponentType.WEB_SERVER, "http"),
    443: (ComponentType.WEB_SERVER, "https"),
    3000: (ComponentType.APP_SERVER, "app-3000"),
    3306: (ComponentType.DATABASE, "mysql"),
    5432: (ComponentType.DATABASE, "postgresql"),
    6379: (ComponentType.CACHE, "redis"),
    11211: (ComponentType.CACHE, "memcached"),
    27017: (ComponentType.DATABASE, "mongodb"),
    5672: (ComponentType.QUEUE, "rabbitmq"),
    9092: (ComponentType.QUEUE, "kafka"),
    8080: (ComponentType.APP_SERVER, "app-8080"),
    8443: (ComponentType.APP_SERVER, "app-8443"),
    9090: (ComponentType.APP_SERVER, "prometheus"),
    9200: (ComponentType.DATABASE, "elasticsearch"),
}


def scan_system_metrics() -> ResourceMetrics:
    """Scan current system resource metrics."""
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    conns = len(psutil.net_connections(kind="inet"))

    return ResourceMetrics(
        cpu_percent=cpu,
        memory_percent=mem.percent,
        memory_used_mb=mem.used / (1024 * 1024),
        memory_total_mb=mem.total / (1024 * 1024),
        disk_percent=disk.percent,
        disk_used_gb=disk.used / (1024**3),
        disk_total_gb=disk.total / (1024**3),
        network_connections=conns,
    )


def scan_listening_services() -> list[dict]:
    """Discover services listening on ports."""
    services = []
    seen_ports: set[int] = set()

    for conn in psutil.net_connections(kind="inet"):
        if conn.status != "LISTEN":
            continue
        port = conn.laddr.port
        if port in seen_ports:
            continue
        seen_ports.add(port)

        proc_name = ""
        pid = conn.pid
        if pid:
            try:
                proc = psutil.Process(pid)
                proc_name = proc.name()
            except psutil.NoSuchProcess:
                logger.debug("Process %d no longer exists, skipping", pid)
            except psutil.AccessDenied:
                logger.debug("Access denied reading process %d, skipping", pid)

        services.append({
            "port": port,
            "address": conn.laddr.ip,
            "pid": pid,
            "process": proc_name,
        })

    return sorted(services, key=lambda s: s["port"])


def scan_established_connections() -> list[dict]:
    """Discover established connections (potential dependencies)."""
    connections = []
    seen: set[tuple[int, int]] = set()

    for conn in psutil.net_connections(kind="inet"):
        if conn.status != "ESTABLISHED" or not conn.raddr:
            continue
        key = (conn.laddr.port, conn.raddr.port)
        if key in seen:
            continue
        seen.add(key)

        connections.append({
            "local_port": conn.laddr.port,
            "remote_host": conn.raddr.ip,
            "remote_port": conn.raddr.port,
            "pid": conn.pid,
        })

    return connections


def detect_component_type(port: int, process_name: str) -> tuple[ComponentType, str]:
    """Detect component type from port and process name."""
    if port in PORT_SERVICE_MAP:
        return PORT_SERVICE_MAP[port]

    name_lower = process_name.lower()
    if "nginx" in name_lower or "apache" in name_lower or "httpd" in name_lower:
        return ComponentType.WEB_SERVER, process_name
    if "postgres" in name_lower:
        return ComponentType.DATABASE, "postgresql"
    if "mysql" in name_lower or "mariadb" in name_lower:
        return ComponentType.DATABASE, "mysql"
    if "redis" in name_lower:
        return ComponentType.CACHE, "redis"
    if "rabbitmq" in name_lower or "amqp" in name_lower:
        return ComponentType.QUEUE, "rabbitmq"
    if "kafka" in name_lower:
        return ComponentType.QUEUE, "kafka"
    if "mongod" in name_lower:
        return ComponentType.DATABASE, "mongodb"
    if "docker" in name_lower or "containerd" in name_lower:
        return ComponentType.APP_SERVER, "container-runtime"
    if "node" in name_lower or "python" in name_lower or "java" in name_lower:
        return ComponentType.APP_SERVER, process_name
    if "haproxy" in name_lower or "envoy" in name_lower:
        return ComponentType.LOAD_BALANCER, process_name

    return ComponentType.CUSTOM, process_name


def scan_local(hostname: str | None = None) -> InfraGraph:
    """Perform a full local system scan and build an InfraGraph."""
    graph = InfraGraph()
    hostname = hostname or socket.gethostname()

    # Scan listening services and create components
    services = scan_listening_services()
    system_metrics = scan_system_metrics()
    component_ids: dict[int, str] = {}  # port -> component_id

    for svc in services:
        port = svc["port"]
        process = svc["process"]
        comp_type, service_name = detect_component_type(port, process)

        comp_id = f"{hostname}:{service_name}:{port}"
        component_ids[port] = comp_id

        component = Component(
            id=comp_id,
            name=f"{service_name} (:{port})",
            type=comp_type,
            host=hostname,
            port=port,
            metrics=system_metrics,
            parameters={"process": process, "pid": svc["pid"] or 0},
        )
        graph.add_component(component)

    # Scan established connections to infer dependencies
    connections = scan_established_connections()
    for conn in connections:
        source_id = component_ids.get(conn["local_port"])
        target_port = conn["remote_port"]

        # If the remote port matches a local service, create internal dependency
        target_id = component_ids.get(target_port)
        if source_id and target_id and source_id != target_id:
            dep = Dependency(
                source_id=source_id,
                target_id=target_id,
                dependency_type="requires",
                protocol="tcp",
                port=target_port,
            )
            graph.add_dependency(dep)

    return graph
