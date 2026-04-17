# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Resource Contention Analyzer.

Detects and simulates resource contention between components sharing
infrastructure.  Identifies direct competition, priority inversions,
thundering-herd effects, lock contention, cache thrashing, and bandwidth
saturation.  Provides scheduling, starvation-risk detection, and
resource-limit recommendations.
"""

from __future__ import annotations

import math
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ResourceType(str, Enum):
    """Types of infrastructure resources that can be contended."""

    CPU = "cpu"
    MEMORY = "memory"
    DISK_IO = "disk_io"
    NETWORK_BANDWIDTH = "network_bandwidth"
    GPU = "gpu"
    CONNECTION_POOL = "connection_pool"
    FILE_DESCRIPTORS = "file_descriptors"
    THREAD_POOL = "thread_pool"


class ContentionType(str, Enum):
    """Categories of resource contention."""

    DIRECT_COMPETITION = "direct_competition"
    PRIORITY_INVERSION = "priority_inversion"
    THUNDERING_HERD = "thundering_herd"
    LOCK_CONTENTION = "lock_contention"
    CACHE_THRASH = "cache_thrash"
    BANDWIDTH_SATURATION = "bandwidth_saturation"


# ---------------------------------------------------------------------------
# Severity / impact helpers
# ---------------------------------------------------------------------------

_RESOURCE_BASE_IMPACT: dict[ResourceType, float] = {
    ResourceType.CPU: 30.0,
    ResourceType.MEMORY: 40.0,
    ResourceType.DISK_IO: 25.0,
    ResourceType.NETWORK_BANDWIDTH: 35.0,
    ResourceType.GPU: 45.0,
    ResourceType.CONNECTION_POOL: 50.0,
    ResourceType.FILE_DESCRIPTORS: 20.0,
    ResourceType.THREAD_POOL: 35.0,
}

_CONTENTION_SEVERITY_MULTIPLIER: dict[ContentionType, float] = {
    ContentionType.DIRECT_COMPETITION: 1.0,
    ContentionType.PRIORITY_INVERSION: 1.5,
    ContentionType.THUNDERING_HERD: 2.0,
    ContentionType.LOCK_CONTENTION: 1.3,
    ContentionType.CACHE_THRASH: 1.1,
    ContentionType.BANDWIDTH_SATURATION: 1.4,
}

_RESOURCE_UTILIZATION_FIELD: dict[ResourceType, str] = {
    ResourceType.CPU: "cpu_percent",
    ResourceType.MEMORY: "memory_percent",
    ResourceType.DISK_IO: "disk_percent",
    ResourceType.NETWORK_BANDWIDTH: "network_connections",
    ResourceType.CONNECTION_POOL: "network_connections",
    ResourceType.FILE_DESCRIPTORS: "open_files",
}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ContentionResult(BaseModel):
    """Result of a contention detection analysis."""

    resource_type: ResourceType
    contention_type: ContentionType
    competing_components: list[str] = Field(default_factory=list)
    severity: str = "low"
    performance_impact_percent: float = 0.0
    starvation_risk: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class SpikeResult(BaseModel):
    """Result of simulating a resource spike on a single component."""

    component_id: str
    resource: ResourceType
    multiplier: float = 1.0
    original_utilization: float = 0.0
    spiked_utilization: float = 0.0
    affected_components: list[str] = Field(default_factory=list)
    severity: str = "low"
    performance_impact_percent: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class PriorityInversion(BaseModel):
    """A detected priority-inversion scenario."""

    high_priority_component: str
    low_priority_component: str
    shared_resource: ResourceType
    blocking_severity: str = "low"
    description: str = ""
    recommendations: list[str] = Field(default_factory=list)


class ResourceLimit(BaseModel):
    """A recommended resource limit for a component."""

    component_id: str
    resource: ResourceType
    current_usage: float = 0.0
    recommended_limit: float = 0.0
    headroom_percent: float = 0.0
    reason: str = ""


class NoisyNeighborResult(BaseModel):
    """Result of a noisy-neighbor simulation between components."""

    aggressor_id: str
    resource: ResourceType
    victim_ids: list[str] = Field(default_factory=list)
    impact_severity: str = "none"
    performance_degradation_percent: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class FairScheduleEntry(BaseModel):
    """Fair scheduling allocation for a single component."""

    component_id: str
    weight: float = 1.0
    cpu_share: float = 0.0
    memory_share: float = 0.0
    io_share: float = 0.0


class FairSchedule(BaseModel):
    """Fair scheduling plan across all components."""

    entries: list[FairScheduleEntry] = Field(default_factory=list)
    total_weight: float = 0.0
    fairness_index: float = 0.0


class StarvationRisk(BaseModel):
    """A component at risk of resource starvation."""

    component_id: str
    resource: ResourceType
    current_usage_percent: float = 0.0
    available_capacity_percent: float = 0.0
    competing_component_count: int = 0
    risk_level: str = "low"
    description: str = ""
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ResourceContentionEngine:
    """Stateless engine for resource contention analysis."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_contention(self, graph: InfraGraph) -> list[ContentionResult]:
        """Detect all resource contention scenarios in the graph.

        Scans for direct competition, thundering-herd risks, cache
        thrashing, bandwidth saturation, and lock contention.
        """
        results: list[ContentionResult] = []
        components = list(graph.components.values())

        if len(components) < 2:
            return results

        # 1. Direct competition – components sharing the same host
        results.extend(self._detect_direct_competition(graph, components))

        # 2. Thundering herd – many dependents on a single component
        results.extend(self._detect_thundering_herd(graph, components))

        # 3. Cache thrash – cache components under high contention
        results.extend(self._detect_cache_thrash(graph, components))

        # 4. Bandwidth saturation – high network usage
        results.extend(self._detect_bandwidth_saturation(graph, components))

        # 5. Lock contention – database/storage with many writers
        results.extend(self._detect_lock_contention(graph, components))

        # Sort by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "none": 4}
        results.sort(key=lambda r: severity_order.get(r.severity, 5))
        return results

    def simulate_resource_spike(
        self,
        graph: InfraGraph,
        component_id: str,
        resource: ResourceType,
        multiplier: float,
    ) -> SpikeResult:
        """Simulate a resource spike on a component and evaluate impact."""
        comp = graph.get_component(component_id)
        if comp is None:
            return SpikeResult(
                component_id=component_id,
                resource=resource,
                multiplier=multiplier,
            )

        original_util = self._get_resource_utilization(comp, resource)
        spiked_util = min(100.0, original_util * multiplier)

        # Find affected neighbours – dependents and components on the same host
        affected: list[str] = []
        for dep in graph.get_dependents(component_id):
            if dep.id not in affected:
                affected.append(dep.id)
        for other in graph.components.values():
            if other.id == component_id:
                continue
            if other.host and other.host == comp.host and other.id not in affected:
                affected.append(other.id)

        affected.sort()

        # Impact calculation
        impact = self._calculate_spike_impact(original_util, spiked_util, multiplier, resource)
        severity = self._severity_from_impact(impact)

        recommendations: list[str] = []
        if spiked_util > 90:
            recommendations.append(
                f"Component '{component_id}' {resource.value} usage would reach "
                f"{spiked_util:.0f}%. Enable autoscaling or add capacity."
            )
        if affected:
            recommendations.append(
                f"Spike affects {len(affected)} neighbour(s). "
                "Consider resource isolation or rate limiting."
            )
        if multiplier > 5:
            recommendations.append(
                "Spike multiplier exceeds 5x. Implement circuit breakers "
                "and load shedding."
            )

        return SpikeResult(
            component_id=component_id,
            resource=resource,
            multiplier=multiplier,
            original_utilization=round(original_util, 2),
            spiked_utilization=round(spiked_util, 2),
            affected_components=affected,
            severity=severity,
            performance_impact_percent=round(impact, 2),
            recommendations=recommendations,
        )

    def find_priority_inversions(
        self, graph: InfraGraph,
    ) -> list[PriorityInversion]:
        """Find priority-inversion scenarios.

        A priority inversion occurs when a lower-priority component holds
        a resource (e.g. connection pool, database lock) that a
        higher-priority component needs, potentially starving the
        higher-priority component.
        """
        inversions: list[PriorityInversion] = []
        components = list(graph.components.values())

        if len(components) < 2:
            return inversions

        # Build priority mapping – load-balancers and web-servers are
        # higher priority than app servers, which are higher than
        # databases (based on user-facing proximity).
        for comp in components:
            deps = graph.get_dependencies(comp.id)
            comp_priority = self._component_priority(comp)

            for dep_comp in deps:
                dep_priority = self._component_priority(dep_comp)

                # Inversion: high-priority component depends on a
                # lower-priority one that is heavily loaded.
                if comp_priority > dep_priority and dep_comp.utilization() > 60:
                    resource = self._primary_resource_for_type(dep_comp.type)
                    severity = self._inversion_severity(
                        comp_priority, dep_priority, dep_comp.utilization(),
                    )

                    desc = (
                        f"High-priority '{comp.id}' (priority={comp_priority}) "
                        f"depends on lower-priority '{dep_comp.id}' "
                        f"(priority={dep_priority}) which is at "
                        f"{dep_comp.utilization():.0f}% utilization"
                    )
                    recs: list[str] = []
                    if severity in ("critical", "high"):
                        recs.append(
                            f"Add dedicated resource pool for '{comp.id}' "
                            f"to avoid blocking by '{dep_comp.id}'."
                        )
                    recs.append(
                        f"Implement priority-based scheduling on '{dep_comp.id}'."
                    )

                    inversions.append(PriorityInversion(
                        high_priority_component=comp.id,
                        low_priority_component=dep_comp.id,
                        shared_resource=resource,
                        blocking_severity=severity,
                        description=desc,
                        recommendations=recs,
                    ))

        inversions.sort(key=lambda inv: (
            {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(inv.blocking_severity, 4),
        ))
        return inversions

    def recommend_resource_limits(
        self, graph: InfraGraph,
    ) -> list[ResourceLimit]:
        """Generate resource-limit recommendations for all components."""
        limits: list[ResourceLimit] = []
        for comp in graph.components.values():
            for resource in ResourceType:
                usage = self._get_resource_utilization(comp, resource)
                if usage <= 0:
                    continue

                headroom = self._calculate_headroom(comp, resource, usage)
                recommended = self._calculate_recommended_limit(usage, headroom)
                reason = self._limit_reason(comp, resource, usage, headroom)

                limits.append(ResourceLimit(
                    component_id=comp.id,
                    resource=resource,
                    current_usage=round(usage, 2),
                    recommended_limit=round(recommended, 2),
                    headroom_percent=round(headroom, 2),
                    reason=reason,
                ))

        limits.sort(key=lambda lim: -lim.current_usage)
        return limits

    def simulate_noisy_neighbor(
        self,
        graph: InfraGraph,
        aggressor_id: str,
        resource: ResourceType,
    ) -> NoisyNeighborResult:
        """Simulate a noisy-neighbor scenario from a given aggressor component."""
        comp = graph.get_component(aggressor_id)
        if comp is None:
            return NoisyNeighborResult(
                aggressor_id=aggressor_id,
                resource=resource,
                impact_severity="none",
            )

        # Victims: components on the same host or sharing a dependency
        victims: list[str] = []
        for other in graph.components.values():
            if other.id == aggressor_id:
                continue
            if other.host and other.host == comp.host:
                victims.append(other.id)

        # Also add dependents
        for dep in graph.get_dependents(aggressor_id):
            if dep.id not in victims:
                victims.append(dep.id)

        victims.sort()

        if not victims:
            return NoisyNeighborResult(
                aggressor_id=aggressor_id,
                resource=resource,
                impact_severity="none",
                recommendations=["No co-located or dependent components; isolation is effective."],
            )

        # Calculate degradation
        aggressor_util = self._get_resource_utilization(comp, resource)
        base_impact = _RESOURCE_BASE_IMPACT.get(resource, 30.0)
        utilization_factor = max(0.0, aggressor_util / 100.0)
        degradation = round(base_impact * utilization_factor * (1 + len(victims) * 0.1), 2)
        degradation = min(100.0, degradation)
        severity = self._severity_from_impact(degradation)

        recommendations: list[str] = []
        if severity in ("critical", "high"):
            recommendations.append(
                f"Isolate '{aggressor_id}' onto dedicated infrastructure "
                "to prevent noisy-neighbor effects."
            )
        if resource == ResourceType.CPU:
            recommendations.append("Implement CPU cgroups or resource quotas.")
        elif resource == ResourceType.MEMORY:
            recommendations.append("Set memory limits and OOM kill policies.")
        elif resource in (ResourceType.DISK_IO, ResourceType.NETWORK_BANDWIDTH):
            recommendations.append("Implement I/O bandwidth throttling.")
        elif resource == ResourceType.CONNECTION_POOL:
            recommendations.append("Set per-component connection pool limits.")

        return NoisyNeighborResult(
            aggressor_id=aggressor_id,
            resource=resource,
            victim_ids=victims,
            impact_severity=severity,
            performance_degradation_percent=degradation,
            recommendations=recommendations,
        )

    def calculate_fair_scheduling(
        self, graph: InfraGraph,
    ) -> FairSchedule:
        """Calculate fair resource scheduling across all components.

        Weights are derived from component priority and current
        utilization.  Returns a :class:`FairSchedule` with per-component
        allocations and a Jain's fairness index.
        """
        components = list(graph.components.values())
        if not components:
            return FairSchedule(fairness_index=1.0)

        entries: list[FairScheduleEntry] = []
        total_weight = 0.0

        for comp in components:
            weight = self._scheduling_weight(comp)
            total_weight += weight
            entries.append(FairScheduleEntry(
                component_id=comp.id,
                weight=round(weight, 3),
            ))

        # Distribute shares proportionally to weight
        if total_weight > 0:
            for entry in entries:
                share = entry.weight / total_weight
                entry.cpu_share = round(share * 100, 2)
                entry.memory_share = round(share * 100, 2)
                entry.io_share = round(share * 100, 2)

        # Jain's fairness index: (sum(x_i))^2 / (n * sum(x_i^2))
        n = len(entries)
        shares = [e.cpu_share for e in entries]
        sum_x = sum(shares)
        sum_x2 = sum(x * x for x in shares)
        if n > 0 and sum_x2 > 0:
            fairness = (sum_x ** 2) / (n * sum_x2)
        else:
            fairness = 1.0

        entries.sort(key=lambda e: -e.weight)

        return FairSchedule(
            entries=entries,
            total_weight=round(total_weight, 3),
            fairness_index=round(fairness, 4),
        )

    def detect_starvation_risks(
        self, graph: InfraGraph,
    ) -> list[StarvationRisk]:
        """Detect components at risk of resource starvation.

        A component faces starvation risk when its available capacity is
        low and it competes with many other components for shared resources.
        """
        risks: list[StarvationRisk] = []
        components = list(graph.components.values())

        for comp in components:
            for resource in (ResourceType.CPU, ResourceType.MEMORY,
                             ResourceType.DISK_IO, ResourceType.CONNECTION_POOL):
                usage = self._get_resource_utilization(comp, resource)
                if usage <= 0:
                    continue

                available = max(0.0, 100.0 - usage)

                # Count competitors: same-host or direct dependents/dependencies
                competitors = self._count_competitors(graph, comp)

                risk_level = self._starvation_risk_level(usage, available, competitors)
                if risk_level == "none":
                    continue

                desc = (
                    f"Component '{comp.id}' has {available:.0f}% available "
                    f"{resource.value} capacity with {competitors} competitor(s)"
                )
                recs: list[str] = []
                if risk_level in ("critical", "high"):
                    recs.append(
                        f"Immediately increase {resource.value} capacity for '{comp.id}' "
                        "or reduce competitors."
                    )
                    recs.append(
                        f"Implement resource reservations for '{comp.id}'."
                    )
                elif risk_level == "medium":
                    recs.append(
                        f"Monitor {resource.value} usage on '{comp.id}' closely."
                    )

                risks.append(StarvationRisk(
                    component_id=comp.id,
                    resource=resource,
                    current_usage_percent=round(usage, 2),
                    available_capacity_percent=round(available, 2),
                    competing_component_count=competitors,
                    risk_level=risk_level,
                    description=desc,
                    recommendations=recs,
                ))

        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        risks.sort(key=lambda r: severity_order.get(r.risk_level, 4))
        return risks

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_resource_utilization(comp: Component, resource: ResourceType) -> float:
        """Get current utilization percentage for a resource type."""
        if resource == ResourceType.CPU:
            return comp.metrics.cpu_percent
        if resource == ResourceType.MEMORY:
            return comp.metrics.memory_percent
        if resource == ResourceType.DISK_IO:
            return comp.metrics.disk_percent
        if resource == ResourceType.NETWORK_BANDWIDTH:
            if comp.capacity.max_connections > 0:
                return (comp.metrics.network_connections / comp.capacity.max_connections) * 100
            return 0.0
        if resource == ResourceType.CONNECTION_POOL:
            if comp.capacity.connection_pool_size > 0:
                return (comp.metrics.network_connections / comp.capacity.connection_pool_size) * 100
            return 0.0
        if resource == ResourceType.FILE_DESCRIPTORS:
            # Estimate FD utilization based on open files vs a reasonable max
            if comp.metrics.open_files > 0:
                return min(100.0, (comp.metrics.open_files / 65536) * 100)
            return 0.0
        if resource == ResourceType.GPU:
            # GPU utilization modelled via parameters
            return comp.parameters.get("gpu_percent", 0.0)  # type: ignore[return-value]
        if resource == ResourceType.THREAD_POOL:
            # Thread pool utilisation modelled via parameters
            return comp.parameters.get("thread_pool_percent", 0.0)  # type: ignore[return-value]
        return 0.0

    @staticmethod
    def _component_priority(comp: Component) -> int:
        """Assign priority based on component type (higher = more important)."""
        return {
            ComponentType.DNS: 10,
            ComponentType.LOAD_BALANCER: 9,
            ComponentType.WEB_SERVER: 8,
            ComponentType.EXTERNAL_API: 7,
            ComponentType.APP_SERVER: 6,
            ComponentType.CACHE: 5,
            ComponentType.QUEUE: 4,
            ComponentType.DATABASE: 3,
            ComponentType.STORAGE: 2,
            ComponentType.CUSTOM: 1,
        }.get(comp.type, 1)

    @staticmethod
    def _primary_resource_for_type(ctype: ComponentType) -> ResourceType:
        """Map a component type to its primary contended resource."""
        return {
            ComponentType.DATABASE: ResourceType.CONNECTION_POOL,
            ComponentType.CACHE: ResourceType.MEMORY,
            ComponentType.QUEUE: ResourceType.DISK_IO,
            ComponentType.STORAGE: ResourceType.DISK_IO,
            ComponentType.WEB_SERVER: ResourceType.THREAD_POOL,
            ComponentType.LOAD_BALANCER: ResourceType.NETWORK_BANDWIDTH,
            ComponentType.APP_SERVER: ResourceType.CPU,
            ComponentType.DNS: ResourceType.NETWORK_BANDWIDTH,
            ComponentType.EXTERNAL_API: ResourceType.NETWORK_BANDWIDTH,
            ComponentType.CUSTOM: ResourceType.CPU,
        }.get(ctype, ResourceType.CPU)

    @staticmethod
    def _severity_from_impact(impact: float) -> str:
        if impact > 60:
            return "critical"
        if impact > 40:
            return "high"
        if impact > 20:
            return "medium"
        if impact > 0:
            return "low"
        return "none"

    @staticmethod
    def _inversion_severity(
        high_pri: int, low_pri: int, util: float,
    ) -> str:
        gap = high_pri - low_pri
        if gap >= 5 and util > 80:
            return "critical"
        if gap >= 3 and util > 70:
            return "high"
        if gap >= 2 or util > 60:
            return "medium"
        return "low"

    @staticmethod
    def _calculate_spike_impact(
        original: float, spiked: float, multiplier: float,
        resource: ResourceType,
    ) -> float:
        base = _RESOURCE_BASE_IMPACT.get(resource, 30.0)
        overflow = max(0.0, spiked - 80.0)
        impact = base * (overflow / 100.0) * math.log2(max(2, multiplier))
        return min(100.0, max(0.0, impact))

    @staticmethod
    def _calculate_headroom(
        comp: Component, resource: ResourceType, usage: float,
    ) -> float:
        """Calculate desired headroom percentage."""
        # Critical components need more headroom
        if comp.type in (ComponentType.DATABASE, ComponentType.LOAD_BALANCER):
            return 40.0
        if comp.autoscaling.enabled:
            return 20.0
        return 30.0

    @staticmethod
    def _calculate_recommended_limit(usage: float, headroom: float) -> float:
        # Recommended = usage + headroom, capped at 100
        return min(100.0, usage + headroom)

    @staticmethod
    def _limit_reason(
        comp: Component, resource: ResourceType, usage: float, headroom: float,
    ) -> str:
        if usage > 80:
            return (
                f"Component '{comp.id}' {resource.value} usage is critically high "
                f"at {usage:.0f}%. Immediate capacity increase recommended."
            )
        if usage > 60:
            return (
                f"Component '{comp.id}' {resource.value} usage is elevated "
                f"at {usage:.0f}%. Set limit with {headroom:.0f}% headroom."
            )
        return (
            f"Component '{comp.id}' {resource.value} usage is {usage:.0f}%. "
            f"Recommended limit provides {headroom:.0f}% headroom."
        )

    @staticmethod
    def _scheduling_weight(comp: Component) -> float:
        """Derive a scheduling weight from component characteristics."""
        base = 1.0
        # Higher priority types get more weight
        type_weight = {
            ComponentType.LOAD_BALANCER: 2.0,
            ComponentType.WEB_SERVER: 1.8,
            ComponentType.APP_SERVER: 1.5,
            ComponentType.DATABASE: 1.6,
            ComponentType.CACHE: 1.3,
            ComponentType.QUEUE: 1.2,
            ComponentType.STORAGE: 1.0,
            ComponentType.DNS: 2.0,
            ComponentType.EXTERNAL_API: 1.0,
            ComponentType.CUSTOM: 1.0,
        }.get(comp.type, 1.0)

        # Higher utilization => slightly more weight to prevent starvation
        util_factor = 1.0 + (comp.utilization() / 200.0)

        # More replicas => less per-instance weight needed
        replica_factor = 1.0 / max(1, comp.replicas)

        return round(base * type_weight * util_factor * replica_factor, 3)

    def _count_competitors(self, graph: InfraGraph, comp: Component) -> int:
        """Count components competing for the same resources."""
        competitors = set()
        # Same host
        for other in graph.components.values():
            if other.id == comp.id:
                continue
            if other.host and other.host == comp.host:
                competitors.add(other.id)
        # Dependents
        for dep in graph.get_dependents(comp.id):
            competitors.add(dep.id)
        # Dependencies
        for dep in graph.get_dependencies(comp.id):
            competitors.add(dep.id)
        return len(competitors)

    @staticmethod
    def _starvation_risk_level(
        usage: float, available: float, competitors: int,
    ) -> str:
        if available < 10 and competitors >= 3:
            return "critical"
        if available < 20 and competitors >= 2:
            return "high"
        if available < 30 and competitors >= 1:
            return "medium"
        if available < 40 and competitors >= 1:
            return "low"
        return "none"

    # ------------------------------------------------------------------
    # Contention detectors (private)
    # ------------------------------------------------------------------

    def _detect_direct_competition(
        self,
        graph: InfraGraph,
        components: list[Component],
    ) -> list[ContentionResult]:
        """Detect components on the same host competing for resources."""
        results: list[ContentionResult] = []
        host_groups: dict[str, list[Component]] = {}
        for comp in components:
            if comp.host:
                host_groups.setdefault(comp.host, []).append(comp)

        for host, group in host_groups.items():
            if len(group) < 2:
                continue

            for resource in (ResourceType.CPU, ResourceType.MEMORY, ResourceType.DISK_IO):
                total_util = sum(self._get_resource_utilization(c, resource) for c in group)
                if total_util <= 0:
                    continue

                avg_util = total_util / len(group)
                impact = _RESOURCE_BASE_IMPACT.get(resource, 30.0) * (avg_util / 100.0)
                impact *= len(group) * 0.3
                impact = min(100.0, impact)
                severity = self._severity_from_impact(impact)

                starvation: list[str] = []
                for c in group:
                    cu = self._get_resource_utilization(c, resource)
                    if cu > 80:
                        starvation.append(c.id)

                recs: list[str] = []
                if severity in ("critical", "high"):
                    recs.append(
                        f"Separate components on host '{host}' to reduce "
                        f"{resource.value} contention."
                    )
                recs.append(f"Implement {resource.value} cgroups or quotas on '{host}'.")

                results.append(ContentionResult(
                    resource_type=resource,
                    contention_type=ContentionType.DIRECT_COMPETITION,
                    competing_components=[c.id for c in group],
                    severity=severity,
                    performance_impact_percent=round(impact, 2),
                    starvation_risk=starvation,
                    recommendations=recs,
                ))

        return results

    def _detect_thundering_herd(
        self,
        graph: InfraGraph,
        components: list[Component],
    ) -> list[ContentionResult]:
        """Detect thundering-herd risks from fan-in patterns."""
        results: list[ContentionResult] = []
        for comp in components:
            dependents = graph.get_dependents(comp.id)
            if len(dependents) < 3:
                continue

            resource = self._primary_resource_for_type(comp.type)
            fan_in = len(dependents)
            base = _RESOURCE_BASE_IMPACT.get(resource, 30.0)
            impact = base * (fan_in / 10.0)
            # Amplify if the target is already loaded
            util = comp.utilization()
            impact *= 1.0 + (util / 100.0)
            impact = min(100.0, impact)
            severity = self._severity_from_impact(impact)

            starvation = [comp.id] if util > 70 else []

            recs = [
                f"Component '{comp.id}' has {fan_in} dependents (thundering-herd risk). "
                "Implement request coalescing or singleflight."
            ]
            if fan_in >= 5:
                recs.append("Add a queue or rate limiter in front of this component.")

            results.append(ContentionResult(
                resource_type=resource,
                contention_type=ContentionType.THUNDERING_HERD,
                competing_components=[d.id for d in dependents],
                severity=severity,
                performance_impact_percent=round(impact, 2),
                starvation_risk=starvation,
                recommendations=recs,
            ))
        return results

    def _detect_cache_thrash(
        self,
        graph: InfraGraph,
        components: list[Component],
    ) -> list[ContentionResult]:
        """Detect cache-thrashing risk on cache components."""
        results: list[ContentionResult] = []
        for comp in components:
            if comp.type != ComponentType.CACHE:
                continue
            dependents = graph.get_dependents(comp.id)
            if len(dependents) < 2:
                continue

            mem_util = comp.metrics.memory_percent
            fan_in = len(dependents)
            impact = 15.0 * (fan_in / 5.0)
            impact *= 1.0 + (mem_util / 100.0)
            impact = min(100.0, impact)
            severity = self._severity_from_impact(impact)

            recs = [
                f"Cache '{comp.id}' is accessed by {fan_in} components. "
                "Consider partitioning or increasing cache size."
            ]

            results.append(ContentionResult(
                resource_type=ResourceType.MEMORY,
                contention_type=ContentionType.CACHE_THRASH,
                competing_components=[d.id for d in dependents],
                severity=severity,
                performance_impact_percent=round(impact, 2),
                starvation_risk=[comp.id] if mem_util > 80 else [],
                recommendations=recs,
            ))
        return results

    def _detect_bandwidth_saturation(
        self,
        graph: InfraGraph,
        components: list[Component],
    ) -> list[ContentionResult]:
        """Detect bandwidth-saturation risk."""
        results: list[ContentionResult] = []
        for comp in components:
            net_util = self._get_resource_utilization(comp, ResourceType.NETWORK_BANDWIDTH)
            if net_util < 60:
                continue

            dependents = graph.get_dependents(comp.id)
            impact = net_util * 0.6
            impact = min(100.0, impact)
            severity = self._severity_from_impact(impact)

            competing = [d.id for d in dependents]
            competing.append(comp.id)

            recs = [
                f"Component '{comp.id}' network utilization is at {net_util:.0f}%. "
                "Scale network capacity or implement traffic shaping."
            ]

            results.append(ContentionResult(
                resource_type=ResourceType.NETWORK_BANDWIDTH,
                contention_type=ContentionType.BANDWIDTH_SATURATION,
                competing_components=sorted(competing),
                severity=severity,
                performance_impact_percent=round(impact, 2),
                starvation_risk=[comp.id] if net_util > 80 else [],
                recommendations=recs,
            ))
        return results

    def _detect_lock_contention(
        self,
        graph: InfraGraph,
        components: list[Component],
    ) -> list[ContentionResult]:
        """Detect lock-contention risk on databases and storage."""
        results: list[ContentionResult] = []
        for comp in components:
            if comp.type not in (ComponentType.DATABASE, ComponentType.STORAGE):
                continue

            dependents = graph.get_dependents(comp.id)
            if len(dependents) < 2:
                continue

            conn_util = self._get_resource_utilization(comp, ResourceType.CONNECTION_POOL)
            fan_in = len(dependents)
            impact = 20.0 * (fan_in / 5.0) * (1.0 + conn_util / 100.0)
            impact = min(100.0, impact)
            severity = self._severity_from_impact(impact)

            recs = [
                f"Database/storage '{comp.id}' has {fan_in} concurrent consumers. "
                "Implement connection pooling and read replicas."
            ]

            results.append(ContentionResult(
                resource_type=ResourceType.CONNECTION_POOL,
                contention_type=ContentionType.LOCK_CONTENTION,
                competing_components=[d.id for d in dependents],
                severity=severity,
                performance_impact_percent=round(impact, 2),
                starvation_risk=[comp.id] if conn_util > 70 else [],
                recommendations=recs,
            ))
        return results
