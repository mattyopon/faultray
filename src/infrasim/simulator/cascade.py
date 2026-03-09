"""Cascade rules - defines how failures propagate between components."""

from __future__ import annotations

from dataclasses import dataclass, field

from infrasim.model.components import Component, ComponentType, HealthStatus
from infrasim.model.graph import InfraGraph
from infrasim.simulator.scenarios import Fault, FaultType


@dataclass
class CascadeEffect:
    """The effect of a fault on a specific component."""

    component_id: str
    component_name: str
    health: HealthStatus
    reason: str
    estimated_time_seconds: int = 0
    metrics_impact: dict[str, float] = field(default_factory=dict)


@dataclass
class CascadeChain:
    """A chain of cascading effects from an initial fault."""

    trigger: str
    effects: list[CascadeEffect] = field(default_factory=list)

    @property
    def severity(self) -> float:
        """0.0 (no impact) to 10.0 (total system failure)."""
        if not self.effects:
            return 0.0
        down = sum(1 for e in self.effects if e.health == HealthStatus.DOWN)
        degraded = sum(1 for e in self.effects if e.health == HealthStatus.DEGRADED)
        overloaded = sum(1 for e in self.effects if e.health == HealthStatus.OVERLOADED)
        total = max(len(self.effects), 1)
        return min(10.0, (down * 3 + degraded * 1.5 + overloaded * 0.5) / total * 10)


class CascadeEngine:
    """Simulates cascading failures through the dependency graph."""

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    def simulate_fault(self, fault: Fault) -> CascadeChain:
        """Simulate a single fault and calculate cascade effects."""
        chain = CascadeChain(trigger=f"{fault.fault_type.value} on {fault.target_component_id}")
        target = self.graph.get_component(fault.target_component_id)
        if not target:
            return chain

        # Apply direct effect on target
        direct_effect = self._apply_direct_effect(target, fault)
        chain.effects.append(direct_effect)

        # Propagate through dependency graph
        self._propagate(
            fault.target_component_id,
            direct_effect.health,
            chain,
            visited=set(),
            depth=0,
            elapsed_seconds=0,
        )

        return chain

    def simulate_traffic_spike(self, multiplier: float) -> CascadeChain:
        """Simulate a traffic spike across all components."""
        chain = CascadeChain(trigger=f"Traffic spike {multiplier}x")

        for comp in self.graph.components.values():
            current_util = comp.utilization()
            projected_util = current_util * multiplier

            if projected_util > 100:
                chain.effects.append(CascadeEffect(
                    component_id=comp.id,
                    component_name=comp.name,
                    health=HealthStatus.DOWN,
                    reason=f"Capacity exceeded: {projected_util:.0f}% (max 100%)",
                    metrics_impact={"utilization": projected_util},
                ))
            elif projected_util > 90:
                chain.effects.append(CascadeEffect(
                    component_id=comp.id,
                    component_name=comp.name,
                    health=HealthStatus.OVERLOADED,
                    reason=f"Near capacity: {projected_util:.0f}%",
                    metrics_impact={"utilization": projected_util},
                ))
            elif projected_util > 70:
                chain.effects.append(CascadeEffect(
                    component_id=comp.id,
                    component_name=comp.name,
                    health=HealthStatus.DEGRADED,
                    reason=f"High utilization: {projected_util:.0f}%",
                    metrics_impact={"utilization": projected_util},
                ))

        return chain

    def _apply_direct_effect(self, component: Component, fault: Fault) -> CascadeEffect:
        """Calculate the direct effect of a fault on its target."""
        match fault.fault_type:
            case FaultType.COMPONENT_DOWN:
                return CascadeEffect(
                    component_id=component.id,
                    component_name=component.name,
                    health=HealthStatus.DOWN,
                    reason="Component failure (simulated)",
                    estimated_time_seconds=0,
                )

            case FaultType.CONNECTION_POOL_EXHAUSTION:
                pool = component.capacity.connection_pool_size
                current = component.metrics.network_connections
                headroom = pool - current
                if headroom < pool * 0.1:
                    health = HealthStatus.DOWN
                    reason = f"Pool exhausted: {current}/{pool} connections"
                elif headroom < pool * 0.3:
                    health = HealthStatus.OVERLOADED
                    reason = f"Pool near limit: {current}/{pool} connections"
                else:
                    health = HealthStatus.DEGRADED
                    reason = f"Pool stressed: {current}/{pool} connections"
                return CascadeEffect(
                    component_id=component.id,
                    component_name=component.name,
                    health=health,
                    reason=reason,
                    metrics_impact={"connections": current, "pool_size": pool},
                )

            case FaultType.DISK_FULL:
                disk_pct = component.metrics.disk_percent
                if disk_pct > 95:
                    health = HealthStatus.DOWN
                    reason = f"Disk full: {disk_pct:.1f}% used"
                elif disk_pct > 85:
                    health = HealthStatus.OVERLOADED
                    reason = f"Disk nearly full: {disk_pct:.1f}% used"
                else:
                    health = HealthStatus.DEGRADED
                    reason = f"Disk pressure: {disk_pct:.1f}% used"
                return CascadeEffect(
                    component_id=component.id,
                    component_name=component.name,
                    health=health,
                    reason=reason,
                    metrics_impact={"disk_percent": disk_pct},
                )

            case FaultType.CPU_SATURATION:
                return CascadeEffect(
                    component_id=component.id,
                    component_name=component.name,
                    health=HealthStatus.OVERLOADED,
                    reason=f"CPU saturated: {component.metrics.cpu_percent:.1f}%",
                    metrics_impact={"cpu_percent": 100.0},
                )

            case FaultType.MEMORY_EXHAUSTION:
                return CascadeEffect(
                    component_id=component.id,
                    component_name=component.name,
                    health=HealthStatus.DOWN,
                    reason="OOM: memory exhausted",
                    metrics_impact={"memory_percent": 100.0},
                )

            case FaultType.LATENCY_SPIKE:
                return CascadeEffect(
                    component_id=component.id,
                    component_name=component.name,
                    health=HealthStatus.DEGRADED,
                    reason="Latency spike: response time degraded",
                    metrics_impact={"latency_ms": component.capacity.timeout_seconds * 1000 * 0.8},
                )

            case FaultType.NETWORK_PARTITION:
                return CascadeEffect(
                    component_id=component.id,
                    component_name=component.name,
                    health=HealthStatus.DOWN,
                    reason="Network partition: unreachable",
                )

            case FaultType.TRAFFIC_SPIKE:
                return CascadeEffect(
                    component_id=component.id,
                    component_name=component.name,
                    health=HealthStatus.OVERLOADED,
                    reason="Traffic spike on component",
                )

    def _propagate(
        self,
        failed_id: str,
        failed_health: HealthStatus,
        chain: CascadeChain,
        visited: set[str],
        depth: int,
        elapsed_seconds: int,
    ) -> None:
        """Recursively propagate failure effects through the graph."""
        if depth > 20:
            return
        visited.add(failed_id)

        failed_comp = self.graph.get_component(failed_id)
        if not failed_comp:
            return

        # Find components that depend on the failed component
        dependents = self.graph.get_dependents(failed_id)

        for dep_comp in dependents:
            if dep_comp.id in visited:
                continue

            edge = self.graph.get_dependency_edge(dep_comp.id, failed_id)
            if not edge:
                continue

            # Calculate cascade effect based on dependency type and weight
            cascade_health, reason, time_delta = self._calculate_cascade_effect(
                dep_comp, failed_comp, failed_health, edge.dependency_type, edge.weight
            )

            if cascade_health == HealthStatus.HEALTHY:
                continue

            new_elapsed = elapsed_seconds + time_delta
            chain.effects.append(CascadeEffect(
                component_id=dep_comp.id,
                component_name=dep_comp.name,
                health=cascade_health,
                reason=reason,
                estimated_time_seconds=new_elapsed,
            ))

            # Continue propagation if degraded or worse
            if cascade_health in (HealthStatus.DOWN, HealthStatus.OVERLOADED):
                self._propagate(
                    dep_comp.id, cascade_health, chain, visited, depth + 1, new_elapsed
                )

    def _calculate_cascade_effect(
        self,
        dependent: Component,
        failed: Component,
        failed_health: HealthStatus,
        dep_type: str,
        weight: float,
    ) -> tuple[HealthStatus, str, int]:
        """Calculate how a failure cascades to a dependent component.

        Returns (health_status, reason, time_delta_seconds).
        """
        # Optional dependencies cause degradation, not failure
        if dep_type == "optional":
            if failed_health == HealthStatus.DOWN:
                return (
                    HealthStatus.DEGRADED,
                    f"Optional dependency {failed.name} is down",
                    10,
                )
            return HealthStatus.HEALTHY, "", 0

        # Async dependencies cause delayed degradation
        if dep_type == "async":
            if failed_health == HealthStatus.DOWN:
                return (
                    HealthStatus.DEGRADED,
                    f"Async dependency {failed.name} is down, queue building up",
                    60,
                )
            return HealthStatus.HEALTHY, "", 0

        # Required dependencies - severity depends on replicas and current health
        if failed_health == HealthStatus.DOWN:
            if dependent.replicas > 1:
                return (
                    HealthStatus.DEGRADED,
                    f"Dependency {failed.name} is down, "
                    f"remaining replicas handling load ({dependent.replicas - 1} left)",
                    5,
                )
            # Single point of failure
            timeout = int(dependent.capacity.timeout_seconds)
            retry_time = int(timeout * dependent.capacity.retry_multiplier)
            return (
                HealthStatus.DOWN,
                f"Dependency {failed.name} is down, "
                f"no alternative path. Timeout after {timeout}s, "
                f"retry storm expected ({retry_time}s)",
                timeout,
            )

        if failed_health == HealthStatus.OVERLOADED:
            if dependent.utilization() > 70:
                return (
                    HealthStatus.OVERLOADED,
                    f"Dependency {failed.name} overloaded + "
                    f"own utilization at {dependent.utilization():.0f}%",
                    15,
                )
            return (
                HealthStatus.DEGRADED,
                f"Dependency {failed.name} overloaded, increased latency",
                10,
            )

        if failed_health == HealthStatus.DEGRADED:
            return (
                HealthStatus.DEGRADED,
                f"Dependency {failed.name} degraded, potential latency increase",
                5,
            )

        return HealthStatus.HEALTHY, "", 0
