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


def generate_default_scenarios(component_ids: list[str]) -> list[Scenario]:
    """Generate standard chaos scenarios for given components."""
    scenarios: list[Scenario] = []

    # Scenario 1: Each component goes down individually
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

    # Scenario 2: Connection pool exhaustion for each component
    for comp_id in component_ids:
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

    # Scenario 3: Traffic spike (2x normal)
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

    # Scenario 4: Traffic spike (5x)
    if component_ids:
        scenarios.append(
            Scenario(
                id="traffic-spike-5x",
                name="Traffic spike (5x)",
                description="Traffic spikes to 5x normal",
                faults=[],
                traffic_multiplier=5.0,
            )
        )

    # Scenario 5: Disk full for each component
    for comp_id in component_ids:
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

    return scenarios
