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
    total_components: int = 0
    likelihood: float = 1.0  # 0.0 (unlikely) to 1.0 (certain/imminent)

    @property
    def severity(self) -> float:
        """0.0 (no impact) to 10.0 (total system failure).

        Scoring rules:
        - Base score from affected component health states
        - Divided by TOTAL system components (not just affected)
        - If only the target is affected (no cascade): max 3.0
        - If cascade affects < 30% of components: max 6.0
        - If cascade affects > 50% of components: can reach 10.0
        - "degraded" only effects cap at 4.0
        - Single WARN with no cascade: 1.0-2.0
        - Likelihood factor reduces score for unlikely scenarios
        """
        if not self.effects:
            return 0.0

        down = sum(1 for e in self.effects if e.health == HealthStatus.DOWN)
        degraded = sum(1 for e in self.effects if e.health == HealthStatus.DEGRADED)
        overloaded = sum(1 for e in self.effects if e.health == HealthStatus.OVERLOADED)

        affected_count = len(self.effects)
        total = max(self.total_components, affected_count, 1)

        # Impact score: weighted average severity of affected components (0-1 scale)
        # DOWN=1.0, OVERLOADED=0.5, DEGRADED=0.25
        impact_score = (down * 1.0 + overloaded * 0.5 + degraded * 0.25) / affected_count

        # Spread score: what fraction of the system is affected (0-1 scale)
        spread_score = affected_count / total

        # Combined: impact * spread, scaled to 0-10
        # This ensures that a full system cascade of DOWN = 10.0,
        # and a single degraded component in a 20-component system = very low
        raw_score = impact_score * spread_score * 10.0

        # Apply caps based on cascade spread
        if affected_count <= 1:
            # Only the target itself is affected - no cascade
            if down > 0:
                raw_score = min(raw_score, 3.0)
            elif overloaded > 0:
                raw_score = min(raw_score, 2.0)
            else:
                raw_score = min(raw_score, 1.5)
        elif spread_score < 0.3:
            # Minor cascade - less than 30% of components
            raw_score = min(raw_score, 6.0)
        # else: > 30% affected, score can go up to 10.0

        # Cap degraded-only effects at 4.0
        if down == 0 and overloaded == 0 and degraded > 0:
            raw_score = min(raw_score, 4.0)

        # Apply likelihood factor (reduces score for unlikely scenarios)
        raw_score *= self.likelihood

        return min(10.0, max(0.0, round(raw_score, 1)))


class CascadeEngine:
    """Simulates cascading failures through the dependency graph."""

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    def simulate_fault(self, fault: Fault) -> CascadeChain:
        """Simulate a single fault and calculate cascade effects."""
        total = len(self.graph.components)
        chain = CascadeChain(
            trigger=f"{fault.fault_type.value} on {fault.target_component_id}",
            total_components=total,
        )
        target = self.graph.get_component(fault.target_component_id)
        if not target:
            return chain

        # Apply direct effect on target
        direct_effect = self._apply_direct_effect(target, fault)
        chain.effects.append(direct_effect)

        # Calculate likelihood based on current state vs fault scenario
        chain.likelihood = self._calculate_likelihood(target, fault)

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
        total = len(self.graph.components)
        chain = CascadeChain(
            trigger=f"Traffic spike {multiplier}x",
            total_components=total,
            likelihood=min(1.0, 0.3 + (multiplier - 1.0) * 0.1),  # Higher multiplier = less likely
        )

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
        """Calculate the direct effect of a fault on its target.

        These are "what if" simulations - DISK_FULL means "what if the disk fills up",
        not "check current disk usage". The direct effect is always the full failure
        scenario. Likelihood (how close current state is to the failure) is tracked
        separately.
        """
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
                # "What if" scenario: pool IS exhausted - always DOWN
                pool = component.capacity.connection_pool_size
                return CascadeEffect(
                    component_id=component.id,
                    component_name=component.name,
                    health=HealthStatus.DOWN,
                    reason=f"Pool exhausted: {pool}/{pool} connections (simulated)",
                    metrics_impact={"connections": pool, "pool_size": pool},
                )

            case FaultType.DISK_FULL:
                # "What if" scenario: disk IS full - always DOWN
                return CascadeEffect(
                    component_id=component.id,
                    component_name=component.name,
                    health=HealthStatus.DOWN,
                    reason=f"Disk full: 100% used (simulated, current: {component.metrics.disk_percent:.1f}%)",
                    metrics_impact={"disk_percent": 100.0},
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

    def _calculate_likelihood(self, component: Component, fault: Fault) -> float:
        """Calculate how likely this fault scenario is based on current state.

        Returns a value from 0.2 (very unlikely) to 1.0 (imminent/already happening).
        This reduces the risk score for scenarios that are far from actually occurring.
        """
        match fault.fault_type:
            case FaultType.DISK_FULL:
                disk_pct = component.metrics.disk_percent
                if disk_pct > 90:
                    return 1.0  # imminent
                elif disk_pct > 75:
                    return 0.7
                elif disk_pct > 50:
                    return 0.4
                else:
                    return 0.2  # unlikely

            case FaultType.CONNECTION_POOL_EXHAUSTION:
                pool = component.capacity.connection_pool_size
                current = component.metrics.network_connections
                if pool == 0:
                    return 0.3
                usage_ratio = current / pool
                if usage_ratio > 0.9:
                    return 1.0  # imminent
                elif usage_ratio > 0.7:
                    return 0.7
                elif usage_ratio > 0.4:
                    return 0.4
                else:
                    return 0.2  # unlikely

            case FaultType.CPU_SATURATION:
                cpu = component.metrics.cpu_percent
                if cpu > 85:
                    return 1.0
                elif cpu > 60:
                    return 0.6
                else:
                    return 0.3

            case FaultType.MEMORY_EXHAUSTION:
                mem = component.metrics.memory_percent
                if mem > 85:
                    return 1.0
                elif mem > 60:
                    return 0.6
                else:
                    return 0.3

            case FaultType.COMPONENT_DOWN | FaultType.NETWORK_PARTITION:
                # These are always plausible - hardware/network failures happen
                return 0.8

            case FaultType.LATENCY_SPIKE:
                # Latency spikes are common
                return 0.7

            case FaultType.TRAFFIC_SPIKE:
                return 0.5

            case _:
                return 0.5

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
