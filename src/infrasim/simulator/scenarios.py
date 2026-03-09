"""Chaos scenarios - defines what failures to simulate."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class FaultType(str, Enum):
    COMPONENT_DOWN = "component_down"
    LATENCY_SPIKE = "latency_spike"
    CPU_SATURATION = "cpu_saturation"
    MEMORY_EXHAUSTION = "memory_exhaustion"
    DISK_FULL = "disk_full"
    CONNECTION_POOL_EXHAUSTION = "connection_pool_exhaustion"
    NETWORK_PARTITION = "network_partition"
    TRAFFIC_SPIKE = "traffic_spike"


class Fault(BaseModel):
    """A single fault injection."""

    target_component_id: str
    fault_type: FaultType
    severity: float = 1.0  # 0.0 (mild) to 1.0 (total failure)
    duration_seconds: int = 300
    parameters: dict[str, float | int | str] = Field(default_factory=dict)


class Scenario(BaseModel):
    """A chaos scenario consisting of one or more faults."""

    id: str
    name: str
    description: str
    faults: list[Fault]
    traffic_multiplier: float = 1.0  # 1.0 = normal, 2.0 = double traffic


def generate_default_scenarios(
    component_ids: list[str],
    components: dict | None = None,
) -> list[Scenario]:
    """Generate chaos scenarios based on component types present.

    Args:
        component_ids: List of component IDs.
        components: Optional dict mapping component ID to Component objects.
            When provided, scenarios are tailored to component types.
    """
    scenarios: list[Scenario] = []

    # Categorize components by type if component objects are provided
    databases: list[str] = []
    caches: list[str] = []
    app_servers: list[str] = []
    load_balancers: list[str] = []
    queues: list[str] = []
    storage: list[str] = []
    other: list[str] = []

    if components:
        for comp_id, comp in components.items():
            ctype = comp.type.value if hasattr(comp.type, "value") else str(comp.type)
            if ctype == "database":
                databases.append(comp_id)
            elif ctype == "cache":
                caches.append(comp_id)
            elif ctype in ("app_server", "web_server"):
                app_servers.append(comp_id)
            elif ctype == "load_balancer":
                load_balancers.append(comp_id)
            elif ctype == "queue":
                queues.append(comp_id)
            elif ctype == "storage":
                storage.append(comp_id)
            else:
                other.append(comp_id)
    else:
        # Fallback: treat all as generic
        other = list(component_ids)

    all_categorized = databases + caches + app_servers + load_balancers + queues + storage + other

    # --- Category 1: Single component failures (core scenarios) ---
    for comp_id in component_ids:
        scenarios.append(
            Scenario(
                id=f"single-failure-{comp_id}",
                name=f"Single failure: {comp_id}",
                description=f"Simulate complete failure of {comp_id}",
                faults=[
                    Fault(
                        target_component_id=comp_id,
                        fault_type=FaultType.COMPONENT_DOWN,
                    )
                ],
            )
        )

    # --- Category 2: Resource-type-specific scenarios ---

    # Connection pool exhaustion - only for databases and app servers (components that use pools)
    pool_targets = databases + app_servers if components else component_ids
    for comp_id in pool_targets:
        scenarios.append(
            Scenario(
                id=f"pool-exhaustion-{comp_id}",
                name=f"Connection pool exhaustion: {comp_id}",
                description=f"Connection pool reaches capacity on {comp_id}",
                faults=[
                    Fault(
                        target_component_id=comp_id,
                        fault_type=FaultType.CONNECTION_POOL_EXHAUSTION,
                    )
                ],
            )
        )

    # Disk full - only for databases and storage (components with significant disk usage)
    disk_targets = databases + storage if components else component_ids
    for comp_id in disk_targets:
        scenarios.append(
            Scenario(
                id=f"disk-full-{comp_id}",
                name=f"Disk full: {comp_id}",
                description=f"Disk reaches capacity on {comp_id}",
                faults=[
                    Fault(
                        target_component_id=comp_id,
                        fault_type=FaultType.DISK_FULL,
                    )
                ],
            )
        )

    # --- Category 3: Latency degradation scenarios ---
    for comp_id in databases:
        scenarios.append(
            Scenario(
                id=f"db-latency-spike-{comp_id}",
                name=f"DB latency 10x: {comp_id}",
                description=f"Database query latency increases 10x on {comp_id} (slow queries, lock contention)",
                faults=[
                    Fault(
                        target_component_id=comp_id,
                        fault_type=FaultType.LATENCY_SPIKE,
                        parameters={"multiplier": 10},
                    )
                ],
            )
        )

    # Network latency spikes for load balancers
    for comp_id in load_balancers:
        scenarios.append(
            Scenario(
                id=f"network-latency-{comp_id}",
                name=f"Network latency spike: {comp_id}",
                description=f"Network latency spike on {comp_id} affecting all downstream traffic",
                faults=[
                    Fault(
                        target_component_id=comp_id,
                        fault_type=FaultType.LATENCY_SPIKE,
                        parameters={"multiplier": 5},
                    )
                ],
            )
        )

    # --- Category 4: Compound failures (two components fail simultaneously) ---

    # Cache failure + traffic spike (very common real-world pattern: cache goes down,
    # all traffic hits the database)
    for cache_id in caches:
        scenarios.append(
            Scenario(
                id=f"cache-down-traffic-spike-{cache_id}",
                name=f"Cache stampede: {cache_id} down + traffic spike",
                description=(
                    f"Cache {cache_id} fails while traffic increases 2x. "
                    "Classic thundering herd / cache stampede scenario."
                ),
                faults=[
                    Fault(
                        target_component_id=cache_id,
                        fault_type=FaultType.COMPONENT_DOWN,
                    )
                ],
                traffic_multiplier=2.0,
            )
        )

    # Database + one app server down simultaneously
    if databases and app_servers:
        db_id = databases[0]
        app_id = app_servers[0]
        scenarios.append(
            Scenario(
                id=f"compound-db-app-{db_id}-{app_id}",
                name=f"Compound: {db_id} + {app_id} down",
                description=f"Simultaneous failure of database {db_id} and app server {app_id}",
                faults=[
                    Fault(
                        target_component_id=db_id,
                        fault_type=FaultType.COMPONENT_DOWN,
                    ),
                    Fault(
                        target_component_id=app_id,
                        fault_type=FaultType.COMPONENT_DOWN,
                    ),
                ],
            )
        )

    # --- Category 5: Cascading resource exhaustion ---

    # Memory leak (gradual OOM) on app servers
    for comp_id in app_servers:
        scenarios.append(
            Scenario(
                id=f"memory-leak-{comp_id}",
                name=f"Memory leak (OOM): {comp_id}",
                description=f"Gradual memory exhaustion on {comp_id} simulating a memory leak leading to OOM",
                faults=[
                    Fault(
                        target_component_id=comp_id,
                        fault_type=FaultType.MEMORY_EXHAUSTION,
                        parameters={"leak_rate": "gradual"},
                    )
                ],
            )
        )

    # Log explosion / disk fill on databases
    for comp_id in databases:
        scenarios.append(
            Scenario(
                id=f"log-explosion-{comp_id}",
                name=f"Log explosion (disk fill): {comp_id}",
                description=f"Transaction logs or slow query logs fill disk on {comp_id}",
                faults=[
                    Fault(
                        target_component_id=comp_id,
                        fault_type=FaultType.DISK_FULL,
                        parameters={"cause": "log_explosion"},
                    )
                ],
            )
        )

    # --- Category 6: Traffic spike scenarios ---
    if component_ids:
        scenarios.append(
            Scenario(
                id="traffic-spike-2x",
                name="Traffic spike (2x)",
                description="Traffic doubles across all entry points",
                faults=[],
                traffic_multiplier=2.0,
            )
        )

        scenarios.append(
            Scenario(
                id="traffic-spike-5x",
                name="Traffic spike (5x)",
                description="Traffic spikes to 5x normal",
                faults=[],
                traffic_multiplier=5.0,
            )
        )

    # Peak hour simulation: 3x on all components
    if component_ids:
        scenarios.append(
            Scenario(
                id="peak-hour-3x",
                name="Peak hour simulation (3x)",
                description="Simulates peak hour load: all traffic at 3x normal across all components",
                faults=[],
                traffic_multiplier=3.0,
            )
        )

    # --- Category 7: Network partition scenarios ---
    for comp_id in databases:
        scenarios.append(
            Scenario(
                id=f"network-partition-{comp_id}",
                name=f"Network partition: {comp_id}",
                description=f"Network partition isolates {comp_id} from the rest of the system",
                faults=[
                    Fault(
                        target_component_id=comp_id,
                        fault_type=FaultType.NETWORK_PARTITION,
                    )
                ],
            )
        )

    return scenarios
