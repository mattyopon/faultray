# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Automatic topology updates from APM agent connection data.

Analyses network connections reported by agents to discover services and
infer dependencies, then updates the FaultRay InfraGraph accordingly.
"""

from __future__ import annotations

import logging

from faultray.apm.models import ConnectionInfo, MetricsBatch, ProcessInfo
from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

# Well-known port → likely service type mapping
_PORT_SERVICE_MAP: dict[int, tuple[str, ComponentType]] = {
    80: ("http", ComponentType.WEB_SERVER),
    443: ("https", ComponentType.WEB_SERVER),
    3306: ("mysql", ComponentType.DATABASE),
    5432: ("postgresql", ComponentType.DATABASE),
    6379: ("redis", ComponentType.CACHE),
    11211: ("memcached", ComponentType.CACHE),
    5672: ("rabbitmq", ComponentType.QUEUE),
    9092: ("kafka", ComponentType.QUEUE),
    27017: ("mongodb", ComponentType.DATABASE),
    8080: ("http-alt", ComponentType.APP_SERVER),
    8443: ("https-alt", ComponentType.APP_SERVER),
    9200: ("elasticsearch", ComponentType.DATABASE),
    2181: ("zookeeper", ComponentType.QUEUE),
}

# ---------------------------------------------------------------------------
# Shared graph reference
# ---------------------------------------------------------------------------

_graph: InfraGraph | None = None


def set_topology_graph(graph: InfraGraph) -> None:
    """Set the InfraGraph to update with agent topology data."""
    global _graph
    _graph = graph


def get_topology_graph() -> InfraGraph | None:
    """Return the current topology graph, or None."""
    return _graph


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def update_topology_from_batch(batch: MetricsBatch) -> list[str]:
    """Process a metrics batch and update the topology graph.

    Returns a list of change descriptions (e.g. "added component X",
    "added dependency X -> Y").
    """
    graph = _graph
    if graph is None:
        return []

    changes: list[str] = []

    # Ensure the agent host is represented as a component
    host_id = f"host-{batch.agent_id}"
    if graph.get_component(host_id) is None:
        comp = Component(
            id=host_id,
            name=f"Host ({batch.agent_id})",
            type=ComponentType.APP_SERVER,
        )
        graph.add_component(comp)
        changes.append(f"added component {host_id}")

    # Discover services from listening processes
    listeners = _extract_listeners(batch.processes)
    for port, proc_name in listeners.items():
        svc_id = f"svc-{batch.agent_id}-{port}"
        if graph.get_component(svc_id) is None:
            svc_type = _infer_service_type(port)
            display_name = _PORT_SERVICE_MAP.get(port, (proc_name, svc_type))[0]
            comp = Component(
                id=svc_id,
                name=f"{display_name}:{port} ({batch.agent_id})",
                type=svc_type,
            )
            graph.add_component(comp)
            changes.append(f"added service {svc_id} ({display_name}:{port})")

            # Link service to host
            dep = Dependency(source_id=host_id, target_id=svc_id)
            graph.add_dependency(dep)

    # Discover outbound dependencies from established connections
    all_conns = list(batch.connections)
    for proc in batch.processes:
        all_conns.extend(proc.connections)

    outbound = _extract_outbound(all_conns, listeners)
    for remote_addr, remote_port, local_port in outbound:
        remote_id = f"remote-{remote_addr}:{remote_port}"
        if graph.get_component(remote_id) is None:
            remote_type = _infer_service_type(remote_port)
            svc_name = _PORT_SERVICE_MAP.get(remote_port, (f"svc-{remote_port}", remote_type))[0]
            comp = Component(
                id=remote_id,
                name=f"{svc_name} ({remote_addr}:{remote_port})",
                type=remote_type,
            )
            graph.add_component(comp)
            changes.append(f"discovered remote {remote_id}")

        # Add dependency from local service → remote
        local_svc_id = f"svc-{batch.agent_id}-{local_port}" if local_port in listeners else host_id
        edge = graph.get_dependency_edge(local_svc_id, remote_id)
        if edge is None:
            dep = Dependency(source_id=local_svc_id, target_id=remote_id)
            graph.add_dependency(dep)
            changes.append(f"added dependency {local_svc_id} -> {remote_id}")

    if changes:
        logger.info(
            "Topology updated from agent %s: %d changes", batch.agent_id, len(changes)
        )

    return changes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_listeners(processes: list[ProcessInfo]) -> dict[int, str]:
    """Extract listening ports and the processes behind them."""
    listeners: dict[int, str] = {}
    for proc in processes:
        for conn in proc.connections:
            if conn.status == "LISTEN" and conn.local_port > 0:
                listeners[conn.local_port] = proc.name
    return listeners


def _extract_outbound(
    connections: list[ConnectionInfo],
    local_listeners: dict[int, str],
) -> list[tuple[str, int, int]]:
    """Extract unique outbound connections (remote_addr, remote_port, local_port).

    Filters out:
    - Loopback connections to own listeners.
    - Connections without a remote address.
    """
    seen: set[tuple[str, int]] = set()
    result: list[tuple[str, int, int]] = []

    for conn in connections:
        if conn.status != "ESTABLISHED":
            continue
        if not conn.remote_addr or conn.remote_port == 0:
            continue
        # Skip loopback to own services
        if conn.remote_addr in ("127.0.0.1", "::1") and conn.remote_port in local_listeners:
            continue
        key = (conn.remote_addr, conn.remote_port)
        if key not in seen:
            seen.add(key)
            result.append((conn.remote_addr, conn.remote_port, conn.local_port))

    return result


def _infer_service_type(port: int) -> ComponentType:
    """Infer the service type from a port number."""
    if port in _PORT_SERVICE_MAP:
        return _PORT_SERVICE_MAP[port][1]
    if port < 1024:
        return ComponentType.APP_SERVER
    return ComponentType.CUSTOM
