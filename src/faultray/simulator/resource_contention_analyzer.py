"""Resource Contention Analyzer.

Analyzes shared resource contention and its impact on system performance.
Features include noisy-neighbor detection, resource isolation evaluation
(cgroups, namespaces, quotas), contention hotspot identification, lock
contention analysis (deadlock detection, lock ordering), memory pressure
cascade modeling (OOM killer impact), disk I/O saturation analysis,
network bandwidth contention, CPU throttling impact (CFS bandwidth control),
resource reservation vs limit analysis (Kubernetes requests/limits), and
contention-induced latency modeling.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ResourceKind(str, Enum):
    """Types of infrastructure resources subject to contention."""

    CPU = "cpu"
    MEMORY = "memory"
    DISK_IO = "disk_io"
    NETWORK_BANDWIDTH = "network_bandwidth"
    FILE_DESCRIPTORS = "file_descriptors"
    LOCKS = "locks"


class IsolationMechanism(str, Enum):
    """Resource isolation mechanisms."""

    NONE = "none"
    CGROUP_V1 = "cgroup_v1"
    CGROUP_V2 = "cgroup_v2"
    NAMESPACE = "namespace"
    QUOTA = "quota"
    DEDICATED_HOST = "dedicated_host"


class ContentionSeverity(str, Enum):
    """Severity level for contention findings."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class LockOrderViolationType(str, Enum):
    """Types of lock ordering violations."""

    POTENTIAL_DEADLOCK = "potential_deadlock"
    INCONSISTENT_ORDER = "inconsistent_order"
    NESTED_LOCK = "nested_lock"


class OOMAction(str, Enum):
    """Actions the OOM killer may take."""

    KILL_PROCESS = "kill_process"
    THROTTLE = "throttle"
    EVICT = "evict"
    NO_ACTION = "no_action"


class ThrottlingPolicy(str, Enum):
    """CPU throttling policies."""

    CFS_BANDWIDTH = "cfs_bandwidth"
    CPU_SHARES = "cpu_shares"
    CPUSET = "cpuset"
    NONE = "none"


# ---------------------------------------------------------------------------
# Impact weights & constants
# ---------------------------------------------------------------------------

_RESOURCE_WEIGHT: dict[ResourceKind, float] = {
    ResourceKind.CPU: 0.30,
    ResourceKind.MEMORY: 0.40,
    ResourceKind.DISK_IO: 0.25,
    ResourceKind.NETWORK_BANDWIDTH: 0.35,
    ResourceKind.FILE_DESCRIPTORS: 0.15,
    ResourceKind.LOCKS: 0.50,
}

_ISOLATION_STRENGTH: dict[IsolationMechanism, float] = {
    IsolationMechanism.NONE: 0.0,
    IsolationMechanism.CGROUP_V1: 0.5,
    IsolationMechanism.CGROUP_V2: 0.7,
    IsolationMechanism.NAMESPACE: 0.6,
    IsolationMechanism.QUOTA: 0.4,
    IsolationMechanism.DEDICATED_HOST: 1.0,
}

_COMPONENT_CONTENTION_PRIORITY: dict[ComponentType, int] = {
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
}

# Memory pressure thresholds (percent)
_MEMORY_PRESSURE_LOW = 60.0
_MEMORY_PRESSURE_MEDIUM = 75.0
_MEMORY_PRESSURE_HIGH = 85.0
_MEMORY_PRESSURE_CRITICAL = 95.0

# Disk IOPS saturation thresholds
_DISK_SATURATION_THRESHOLD = 80.0
_DISK_CRITICAL_THRESHOLD = 95.0

# CFS bandwidth control default period (microseconds)
_CFS_PERIOD_US = 100_000


# ---------------------------------------------------------------------------
# Pydantic result models
# ---------------------------------------------------------------------------


class NoisyNeighborFinding(BaseModel):
    """A detected noisy-neighbor scenario in shared infrastructure."""

    aggressor_id: str
    victim_ids: list[str] = Field(default_factory=list)
    resource: ResourceKind
    aggressor_usage_percent: float = 0.0
    impact_percent: float = 0.0
    severity: ContentionSeverity = ContentionSeverity.NONE
    isolation_mechanism: IsolationMechanism = IsolationMechanism.NONE
    recommendations: list[str] = Field(default_factory=list)


class IsolationEvaluation(BaseModel):
    """Evaluation of resource isolation for a component."""

    component_id: str
    mechanism: IsolationMechanism = IsolationMechanism.NONE
    strength_score: float = 0.0
    gaps: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class ContentionHotspot(BaseModel):
    """A resource contention hotspot in the dependency graph."""

    component_id: str
    resource: ResourceKind
    contention_score: float = 0.0
    contributing_components: list[str] = Field(default_factory=list)
    severity: ContentionSeverity = ContentionSeverity.NONE
    description: str = ""
    recommendations: list[str] = Field(default_factory=list)


class LockContentionFinding(BaseModel):
    """Lock contention analysis result."""

    component_ids: list[str] = Field(default_factory=list)
    violation_type: LockOrderViolationType = LockOrderViolationType.INCONSISTENT_ORDER
    severity: ContentionSeverity = ContentionSeverity.NONE
    cycle: list[str] = Field(default_factory=list)
    description: str = ""
    recommendations: list[str] = Field(default_factory=list)


class MemoryPressureCascade(BaseModel):
    """Modeling of memory pressure cascading through the system."""

    trigger_component_id: str
    oom_action: OOMAction = OOMAction.NO_ACTION
    affected_components: list[str] = Field(default_factory=list)
    cascade_depth: int = 0
    memory_pressure_percent: float = 0.0
    severity: ContentionSeverity = ContentionSeverity.NONE
    description: str = ""
    recommendations: list[str] = Field(default_factory=list)


class DiskIOSaturation(BaseModel):
    """Disk I/O saturation analysis result."""

    component_id: str
    utilization_percent: float = 0.0
    is_saturated: bool = False
    throughput_impact_percent: float = 0.0
    severity: ContentionSeverity = ContentionSeverity.NONE
    competing_components: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class NetworkBandwidthContention(BaseModel):
    """Network bandwidth contention between co-located services."""

    component_id: str
    co_located_ids: list[str] = Field(default_factory=list)
    total_bandwidth_percent: float = 0.0
    individual_share_percent: float = 0.0
    severity: ContentionSeverity = ContentionSeverity.NONE
    recommendations: list[str] = Field(default_factory=list)


class CPUThrottlingImpact(BaseModel):
    """CPU throttling impact analysis (CFS bandwidth control)."""

    component_id: str
    policy: ThrottlingPolicy = ThrottlingPolicy.NONE
    throttled_percent: float = 0.0
    latency_increase_ms: float = 0.0
    severity: ContentionSeverity = ContentionSeverity.NONE
    recommendations: list[str] = Field(default_factory=list)


class ResourceReservation(BaseModel):
    """Resource reservation vs limit analysis (Kubernetes requests/limits)."""

    component_id: str
    resource: ResourceKind
    request_percent: float = 0.0
    limit_percent: float = 0.0
    current_usage_percent: float = 0.0
    overcommit_ratio: float = 1.0
    is_burstable: bool = False
    qos_class: str = "BestEffort"
    severity: ContentionSeverity = ContentionSeverity.NONE
    recommendations: list[str] = Field(default_factory=list)


class ContentionLatencyModel(BaseModel):
    """Contention-induced latency modeling result."""

    component_id: str
    base_latency_ms: float = 0.0
    contention_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    latency_increase_percent: float = 0.0
    primary_contention_source: ResourceKind = ResourceKind.CPU
    severity: ContentionSeverity = ContentionSeverity.NONE
    recommendations: list[str] = Field(default_factory=list)


class ContentionAnalysisReport(BaseModel):
    """Full contention analysis report combining all sub-analyses."""

    timestamp: str = ""
    noisy_neighbors: list[NoisyNeighborFinding] = Field(default_factory=list)
    isolation_evaluations: list[IsolationEvaluation] = Field(default_factory=list)
    hotspots: list[ContentionHotspot] = Field(default_factory=list)
    lock_findings: list[LockContentionFinding] = Field(default_factory=list)
    memory_cascades: list[MemoryPressureCascade] = Field(default_factory=list)
    disk_saturations: list[DiskIOSaturation] = Field(default_factory=list)
    network_contentions: list[NetworkBandwidthContention] = Field(default_factory=list)
    cpu_throttling: list[CPUThrottlingImpact] = Field(default_factory=list)
    reservations: list[ResourceReservation] = Field(default_factory=list)
    latency_models: list[ContentionLatencyModel] = Field(default_factory=list)
    overall_severity: ContentionSeverity = ContentionSeverity.NONE
    summary: str = ""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ResourceContentionAnalyzer:
    """Stateless engine for deep resource contention analysis."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, graph: InfraGraph) -> ContentionAnalysisReport:
        """Run the full contention analysis pipeline and return a report."""
        ts = datetime.now(timezone.utc).isoformat()

        noisy = self.detect_noisy_neighbors(graph)
        isolation = self.evaluate_isolation(graph)
        hotspots = self.identify_hotspots(graph)
        locks = self.analyze_lock_contention(graph)
        memory = self.model_memory_pressure_cascades(graph)
        disk = self.analyze_disk_io_saturation(graph)
        network = self.analyze_network_bandwidth_contention(graph)
        cpu = self.analyze_cpu_throttling(graph)
        reservations = self.analyze_resource_reservations(graph)
        latency = self.model_contention_latency(graph)

        all_severities: list[ContentionSeverity] = []
        for n in noisy:
            all_severities.append(n.severity)
        for h in hotspots:
            all_severities.append(h.severity)
        for lf in locks:
            all_severities.append(lf.severity)
        for m in memory:
            all_severities.append(m.severity)
        for d in disk:
            all_severities.append(d.severity)
        for net in network:
            all_severities.append(net.severity)
        for c in cpu:
            all_severities.append(c.severity)
        for r in reservations:
            all_severities.append(r.severity)
        for lat in latency:
            all_severities.append(lat.severity)

        overall = self._worst_severity(all_severities)

        component_count = len(graph.components)
        finding_count = (
            len(noisy) + len(hotspots) + len(locks) + len(memory)
            + len(disk) + len(network) + len(cpu) + len(reservations)
            + len(latency)
        )
        summary = (
            f"Analyzed {component_count} components. "
            f"Found {finding_count} contention finding(s). "
            f"Overall severity: {overall.value}."
        )

        return ContentionAnalysisReport(
            timestamp=ts,
            noisy_neighbors=noisy,
            isolation_evaluations=isolation,
            hotspots=hotspots,
            lock_findings=locks,
            memory_cascades=memory,
            disk_saturations=disk,
            network_contentions=network,
            cpu_throttling=cpu,
            reservations=reservations,
            latency_models=latency,
            overall_severity=overall,
            summary=summary,
        )

    def detect_noisy_neighbors(
        self, graph: InfraGraph,
    ) -> list[NoisyNeighborFinding]:
        """Detect noisy-neighbor effects in shared infrastructure."""
        findings: list[NoisyNeighborFinding] = []
        components = list(graph.components.values())
        if len(components) < 2:
            return findings

        host_groups = self._group_by_host(components)

        for host, group in host_groups.items():
            if len(group) < 2:
                continue
            for resource in ResourceKind:
                for comp in group:
                    usage = self._get_utilization(comp, resource)
                    if usage < 70.0:
                        continue
                    # This component is an aggressor
                    victims = [c.id for c in group if c.id != comp.id]
                    weight = _RESOURCE_WEIGHT.get(resource, 0.3)
                    impact = min(100.0, usage * weight * (1 + len(victims) * 0.15))
                    severity = self._severity_from_score(impact)

                    iso = self._infer_isolation(comp)
                    iso_strength = _ISOLATION_STRENGTH.get(iso, 0.0)
                    impact = impact * (1.0 - iso_strength * 0.5)

                    recs: list[str] = []
                    if severity in (ContentionSeverity.CRITICAL, ContentionSeverity.HIGH):
                        recs.append(
                            f"Isolate '{comp.id}' onto dedicated infrastructure "
                            f"to prevent {resource.value} noisy-neighbor effects."
                        )
                    if iso == IsolationMechanism.NONE:
                        recs.append(
                            f"Implement cgroup or namespace isolation for "
                            f"'{comp.id}' on host '{host}'."
                        )
                    if usage > 90.0:
                        recs.append(
                            f"Component '{comp.id}' {resource.value} usage at "
                            f"{usage:.0f}%. Consider autoscaling or capacity increase."
                        )

                    findings.append(NoisyNeighborFinding(
                        aggressor_id=comp.id,
                        victim_ids=sorted(victims),
                        resource=resource,
                        aggressor_usage_percent=round(usage, 2),
                        impact_percent=round(impact, 2),
                        severity=severity,
                        isolation_mechanism=iso,
                        recommendations=recs,
                    ))

        findings.sort(key=lambda f: self._severity_rank(f.severity))
        return findings

    def evaluate_isolation(
        self, graph: InfraGraph,
    ) -> list[IsolationEvaluation]:
        """Evaluate resource isolation for each component."""
        evaluations: list[IsolationEvaluation] = []

        for comp in graph.components.values():
            iso = self._infer_isolation(comp)
            strength = _ISOLATION_STRENGTH.get(iso, 0.0)
            gaps: list[str] = []
            recs: list[str] = []

            if iso == IsolationMechanism.NONE:
                gaps.append("No resource isolation mechanism detected.")
                recs.append("Implement cgroup-based resource limits.")
                recs.append("Consider namespace isolation for network resources.")
            elif iso in (IsolationMechanism.CGROUP_V1, IsolationMechanism.QUOTA):
                gaps.append(
                    f"Isolation mechanism '{iso.value}' provides limited protection."
                )
                recs.append("Upgrade to cgroup v2 for better resource control.")

            # Check if component is co-located
            co_located = self._find_co_located(graph, comp)
            if co_located and iso == IsolationMechanism.NONE:
                gaps.append(
                    f"Component shares host with {len(co_located)} other(s) "
                    "without isolation."
                )
                recs.append(
                    "Enable resource quotas for all co-located components."
                )

            # High-priority components need stronger isolation
            priority = _COMPONENT_CONTENTION_PRIORITY.get(comp.type, 1)
            if priority >= 8 and strength < 0.6:
                gaps.append(
                    f"High-priority component '{comp.id}' has insufficient "
                    f"isolation (strength={strength:.1f})."
                )
                recs.append(
                    f"Upgrade isolation for '{comp.id}' to at least "
                    "namespace or container level."
                )

            evaluations.append(IsolationEvaluation(
                component_id=comp.id,
                mechanism=iso,
                strength_score=round(strength, 2),
                gaps=gaps,
                recommendations=recs,
            ))

        return evaluations

    def identify_hotspots(
        self, graph: InfraGraph,
    ) -> list[ContentionHotspot]:
        """Identify contention hotspots across the dependency graph."""
        hotspots: list[ContentionHotspot] = []
        components = list(graph.components.values())

        for comp in components:
            dependents = graph.get_dependents(comp.id)
            dependencies = graph.get_dependencies(comp.id)
            co_located = self._find_co_located(graph, comp)

            contributors = set()
            for d in dependents:
                contributors.add(d.id)
            for d in dependencies:
                contributors.add(d.id)
            for c in co_located:
                contributors.add(c.id)

            if not contributors:
                continue

            for resource in (ResourceKind.CPU, ResourceKind.MEMORY,
                             ResourceKind.DISK_IO, ResourceKind.LOCKS):
                usage = self._get_utilization(comp, resource)
                if usage < 50.0:
                    continue

                fan_in = len(dependents)
                weight = _RESOURCE_WEIGHT.get(resource, 0.3)
                contention_score = usage * weight * (1 + fan_in * 0.2)
                contention_score += len(co_located) * 5.0
                contention_score = min(100.0, contention_score)
                severity = self._severity_from_score(contention_score)

                desc = (
                    f"Component '{comp.id}' is a {resource.value} hotspot "
                    f"with {fan_in} dependent(s) and {len(co_located)} "
                    f"co-located component(s) at {usage:.0f}% utilization."
                )
                recs: list[str] = []
                if severity in (ContentionSeverity.CRITICAL, ContentionSeverity.HIGH):
                    recs.append(
                        f"Scale '{comp.id}' horizontally or add caching layer."
                    )
                if fan_in >= 3:
                    recs.append("Implement request coalescing or load shedding.")
                if resource == ResourceKind.LOCKS:
                    recs.append("Consider read replicas or sharding to reduce lock contention.")

                hotspots.append(ContentionHotspot(
                    component_id=comp.id,
                    resource=resource,
                    contention_score=round(contention_score, 2),
                    contributing_components=sorted(contributors),
                    severity=severity,
                    description=desc,
                    recommendations=recs,
                ))

        hotspots.sort(key=lambda h: self._severity_rank(h.severity))
        return hotspots

    def analyze_lock_contention(
        self, graph: InfraGraph,
    ) -> list[LockContentionFinding]:
        """Analyze lock contention including deadlock detection and lock ordering."""
        findings: list[LockContentionFinding] = []
        components = list(graph.components.values())
        if len(components) < 2:
            return findings

        # Detect potential deadlocks: mutual dependencies between DB/storage
        lock_holders = [
            c for c in components
            if c.type in (ComponentType.DATABASE, ComponentType.STORAGE)
        ]

        for i, a in enumerate(lock_holders):
            for b in lock_holders[i + 1:]:
                # Check for mutual dependency (cycle of length 2)
                a_deps_b = graph.get_dependency_edge(a.id, b.id) is not None
                b_deps_a = graph.get_dependency_edge(b.id, a.id) is not None

                if a_deps_b and b_deps_a:
                    severity = ContentionSeverity.CRITICAL
                    findings.append(LockContentionFinding(
                        component_ids=[a.id, b.id],
                        violation_type=LockOrderViolationType.POTENTIAL_DEADLOCK,
                        severity=severity,
                        cycle=[a.id, b.id, a.id],
                        description=(
                            f"Potential deadlock: '{a.id}' and '{b.id}' have "
                            "mutual dependencies, creating a lock ordering cycle."
                        ),
                        recommendations=[
                            "Break the circular dependency between these components.",
                            "Implement a consistent lock ordering protocol.",
                            "Consider using optimistic concurrency control.",
                        ],
                    ))

        # Detect inconsistent lock ordering: app servers depending on
        # multiple databases that also depend on each other
        app_servers = [c for c in components if c.type == ComponentType.APP_SERVER]
        for app in app_servers:
            db_deps = [
                d for d in graph.get_dependencies(app.id)
                if d.type in (ComponentType.DATABASE, ComponentType.STORAGE)
            ]
            if len(db_deps) < 2:
                continue

            for i, d1 in enumerate(db_deps):
                for d2 in db_deps[i + 1:]:
                    d1_util = self._get_utilization(d1, ResourceKind.LOCKS)
                    d2_util = self._get_utilization(d2, ResourceKind.LOCKS)
                    combined = d1_util + d2_util
                    if combined < 40:
                        continue

                    severity = self._severity_from_score(combined * 0.8)
                    findings.append(LockContentionFinding(
                        component_ids=[app.id, d1.id, d2.id],
                        violation_type=LockOrderViolationType.INCONSISTENT_ORDER,
                        severity=severity,
                        cycle=[],
                        description=(
                            f"App server '{app.id}' accesses '{d1.id}' and "
                            f"'{d2.id}' concurrently. Inconsistent lock "
                            "ordering may cause contention."
                        ),
                        recommendations=[
                            f"Define explicit lock ordering for '{d1.id}' and '{d2.id}'.",
                            "Use distributed locking with timeout to prevent blocking.",
                        ],
                    ))

        # Nested lock detection: deep dependency chains through lock-holding components
        for comp in lock_holders:
            chain = self._lock_chain_depth(graph, comp.id, set())
            if chain >= 3:
                findings.append(LockContentionFinding(
                    component_ids=[comp.id],
                    violation_type=LockOrderViolationType.NESTED_LOCK,
                    severity=ContentionSeverity.HIGH,
                    cycle=[],
                    description=(
                        f"Component '{comp.id}' participates in a lock chain "
                        f"of depth {chain}. Deep nesting increases deadlock risk."
                    ),
                    recommendations=[
                        "Flatten the dependency chain to reduce lock nesting.",
                        "Implement lock-free data structures where possible.",
                    ],
                ))

        findings.sort(key=lambda f: self._severity_rank(f.severity))
        return findings

    def model_memory_pressure_cascades(
        self, graph: InfraGraph,
    ) -> list[MemoryPressureCascade]:
        """Model memory pressure cascading through the system (OOM killer impact)."""
        cascades: list[MemoryPressureCascade] = []

        for comp in graph.components.values():
            mem_usage = comp.metrics.memory_percent
            if mem_usage < _MEMORY_PRESSURE_LOW:
                continue

            oom_action = self._determine_oom_action(mem_usage)
            affected: list[str] = []
            cascade_depth = 0

            if oom_action in (OOMAction.KILL_PROCESS, OOMAction.EVICT):
                # If OOM kills this component, dependents are affected
                all_affected = graph.get_all_affected(comp.id)
                affected = sorted(all_affected)
                cascade_depth = self._cascade_depth(graph, comp.id)

            severity = self._memory_severity(mem_usage, len(affected))
            desc = (
                f"Component '{comp.id}' at {mem_usage:.0f}% memory. "
                f"OOM action: {oom_action.value}. "
                f"{len(affected)} downstream component(s) affected."
            )
            recs: list[str] = []
            if oom_action == OOMAction.KILL_PROCESS:
                recs.append(
                    f"Set OOM score adjustment for '{comp.id}' to prevent "
                    "critical services from being killed."
                )
                recs.append("Implement memory limits via cgroups.")
            if mem_usage > _MEMORY_PRESSURE_HIGH:
                recs.append(
                    f"Reduce memory usage on '{comp.id}' or increase capacity."
                )
            if cascade_depth > 2:
                recs.append(
                    "Add circuit breakers to limit cascade depth."
                )

            cascades.append(MemoryPressureCascade(
                trigger_component_id=comp.id,
                oom_action=oom_action,
                affected_components=affected,
                cascade_depth=cascade_depth,
                memory_pressure_percent=round(mem_usage, 2),
                severity=severity,
                description=desc,
                recommendations=recs,
            ))

        cascades.sort(key=lambda c: self._severity_rank(c.severity))
        return cascades

    def analyze_disk_io_saturation(
        self, graph: InfraGraph,
    ) -> list[DiskIOSaturation]:
        """Analyze disk I/O saturation (IOPS limits, throughput bottlenecks)."""
        results: list[DiskIOSaturation] = []

        for comp in graph.components.values():
            disk_util = comp.metrics.disk_percent
            if disk_util < 40.0:
                continue

            co_located = self._find_co_located(graph, comp)
            competing = [c.id for c in co_located if c.metrics.disk_percent > 20.0]

            is_saturated = disk_util >= _DISK_SATURATION_THRESHOLD
            throughput_impact = 0.0
            if is_saturated:
                overflow = disk_util - _DISK_SATURATION_THRESHOLD
                throughput_impact = min(100.0, overflow * 3.0)

            severity = self._disk_severity(disk_util, len(competing))

            recs: list[str] = []
            if is_saturated:
                recs.append(
                    f"Disk I/O on '{comp.id}' is saturated at {disk_util:.0f}%. "
                    "Consider faster storage (SSD/NVMe) or I/O scheduling."
                )
            if competing:
                recs.append(
                    f"{len(competing)} co-located component(s) also use disk I/O. "
                    "Implement I/O bandwidth throttling per workload."
                )
            if comp.type in (ComponentType.DATABASE, ComponentType.STORAGE):
                recs.append("Consider read replicas or caching to reduce disk load.")

            results.append(DiskIOSaturation(
                component_id=comp.id,
                utilization_percent=round(disk_util, 2),
                is_saturated=is_saturated,
                throughput_impact_percent=round(throughput_impact, 2),
                severity=severity,
                competing_components=sorted(competing),
                recommendations=recs,
            ))

        results.sort(key=lambda r: self._severity_rank(r.severity))
        return results

    def analyze_network_bandwidth_contention(
        self, graph: InfraGraph,
    ) -> list[NetworkBandwidthContention]:
        """Analyze network bandwidth contention between co-located services."""
        results: list[NetworkBandwidthContention] = []

        host_groups = self._group_by_host(list(graph.components.values()))
        for host, group in host_groups.items():
            if len(group) < 2:
                continue

            total_bw = 0.0
            for comp in group:
                net_util = self._get_utilization(comp, ResourceKind.NETWORK_BANDWIDTH)
                total_bw += net_util

            if total_bw < 50.0:
                continue

            per_component = total_bw / len(group)
            severity = self._severity_from_score(min(100.0, total_bw * 0.6))

            recs: list[str] = []
            if total_bw > 80.0:
                recs.append(
                    f"Host '{host}' total network utilization at {total_bw:.0f}%. "
                    "Implement traffic shaping or QoS policies."
                )
            recs.append("Consider network namespaces for bandwidth isolation.")

            for comp in group:
                co_located = [c.id for c in group if c.id != comp.id]
                results.append(NetworkBandwidthContention(
                    component_id=comp.id,
                    co_located_ids=sorted(co_located),
                    total_bandwidth_percent=round(total_bw, 2),
                    individual_share_percent=round(per_component, 2),
                    severity=severity,
                    recommendations=recs,
                ))

        results.sort(key=lambda r: self._severity_rank(r.severity))
        return results

    def analyze_cpu_throttling(
        self, graph: InfraGraph,
    ) -> list[CPUThrottlingImpact]:
        """Analyze CPU throttling impact (CFS bandwidth control)."""
        results: list[CPUThrottlingImpact] = []

        for comp in graph.components.values():
            cpu_util = comp.metrics.cpu_percent
            if cpu_util < 50.0:
                continue

            policy = self._infer_throttling_policy(comp)
            throttled_pct = 0.0
            latency_increase = 0.0

            if policy == ThrottlingPolicy.CFS_BANDWIDTH:
                # Model CFS throttling: above quota, CPU is throttled
                quota_pct = comp.parameters.get("cpu_quota_percent", 80.0)
                if isinstance(quota_pct, str):
                    try:
                        quota_pct = float(quota_pct)
                    except (ValueError, TypeError):
                        quota_pct = 80.0
                if cpu_util > quota_pct:
                    throttled_pct = min(100.0, (cpu_util - quota_pct) / quota_pct * 100)
                    # Each 10% throttling adds ~5ms latency
                    latency_increase = throttled_pct * 0.5
            elif policy == ThrottlingPolicy.CPU_SHARES:
                # Shares-based: contention causes proportional slowdown
                co_located = self._find_co_located(graph, comp)
                if co_located:
                    total_load = cpu_util + sum(
                        c.metrics.cpu_percent for c in co_located
                    )
                    if total_load > 100.0:
                        throttled_pct = min(100.0, (total_load - 100.0) * 0.5)
                        latency_increase = throttled_pct * 0.3
            elif policy == ThrottlingPolicy.CPUSET:
                # CPUSET: hard limit, no throttling until pinned CPUs saturated
                if cpu_util > 95.0:
                    throttled_pct = cpu_util - 95.0
                    latency_increase = throttled_pct * 1.0
            else:
                # No policy: contention is uncontrolled
                if cpu_util > 80.0:
                    throttled_pct = (cpu_util - 80.0) * 0.8
                    latency_increase = throttled_pct * 0.4

            if throttled_pct <= 0.0:
                continue

            severity = self._severity_from_score(throttled_pct)
            recs: list[str] = []
            if throttled_pct > 30.0:
                recs.append(
                    f"'{comp.id}' is significantly throttled ({throttled_pct:.0f}%). "
                    "Increase CPU quota or add replicas."
                )
            if policy == ThrottlingPolicy.NONE:
                recs.append("Implement CFS bandwidth control to manage CPU contention.")
            if latency_increase > 10.0:
                recs.append(
                    f"CPU throttling adds ~{latency_increase:.0f}ms latency. "
                    "Consider dedicated CPU allocation."
                )

            results.append(CPUThrottlingImpact(
                component_id=comp.id,
                policy=policy,
                throttled_percent=round(throttled_pct, 2),
                latency_increase_ms=round(latency_increase, 2),
                severity=severity,
                recommendations=recs,
            ))

        results.sort(key=lambda r: self._severity_rank(r.severity))
        return results

    def analyze_resource_reservations(
        self, graph: InfraGraph,
    ) -> list[ResourceReservation]:
        """Analyze resource reservation vs limit (Kubernetes requests/limits)."""
        results: list[ResourceReservation] = []

        for comp in graph.components.values():
            for resource in (ResourceKind.CPU, ResourceKind.MEMORY):
                usage = self._get_utilization(comp, resource)
                if usage <= 0.0:
                    continue

                request = self._get_request(comp, resource)
                limit = self._get_limit(comp, resource)

                if request <= 0.0 and limit <= 0.0:
                    # No reservation or limit set
                    qos = "BestEffort"
                    overcommit = 0.0
                    is_burstable = False
                elif request > 0.0 and limit > 0.0 and abs(request - limit) < 0.01:
                    qos = "Guaranteed"
                    overcommit = usage / limit if limit > 0 else 0.0
                    is_burstable = False
                else:
                    qos = "Burstable"
                    overcommit = usage / limit if limit > 0 else usage / 100.0
                    is_burstable = True

                severity = self._reservation_severity(usage, request, limit, qos)

                recs: list[str] = []
                if qos == "BestEffort":
                    recs.append(
                        f"Set resource requests and limits for '{comp.id}' "
                        f"{resource.value} to prevent eviction."
                    )
                if overcommit > 1.0:
                    recs.append(
                        f"'{comp.id}' usage ({usage:.0f}%) exceeds limit "
                        f"({limit:.0f}%). Increase limit or reduce load."
                    )
                if is_burstable and usage > request:
                    recs.append(
                        f"Usage exceeds request ({request:.0f}%). "
                        "Increase request to match actual usage."
                    )

                results.append(ResourceReservation(
                    component_id=comp.id,
                    resource=resource,
                    request_percent=round(request, 2),
                    limit_percent=round(limit, 2),
                    current_usage_percent=round(usage, 2),
                    overcommit_ratio=round(overcommit, 2),
                    is_burstable=is_burstable,
                    qos_class=qos,
                    severity=severity,
                    recommendations=recs,
                ))

        results.sort(key=lambda r: self._severity_rank(r.severity))
        return results

    def model_contention_latency(
        self, graph: InfraGraph,
    ) -> list[ContentionLatencyModel]:
        """Model contention-induced latency for each component."""
        results: list[ContentionLatencyModel] = []

        for comp in graph.components.values():
            base_latency = comp.network.rtt_ms
            contention_latency = 0.0
            primary_source = ResourceKind.CPU

            # CPU contention adds latency
            cpu_util = comp.metrics.cpu_percent
            if cpu_util > 60.0:
                cpu_added = (cpu_util - 60.0) * 0.5
                if cpu_added > contention_latency:
                    contention_latency = cpu_added
                    primary_source = ResourceKind.CPU

            # Memory pressure adds latency (swap / GC)
            mem_util = comp.metrics.memory_percent
            if mem_util > 70.0:
                mem_added = (mem_util - 70.0) * 0.8
                if mem_added > contention_latency:
                    contention_latency = mem_added
                    primary_source = ResourceKind.MEMORY

            # Disk I/O contention adds latency
            disk_util = comp.metrics.disk_percent
            if disk_util > 60.0:
                disk_added = (disk_util - 60.0) * 1.0
                if disk_added > contention_latency:
                    contention_latency = disk_added
                    primary_source = ResourceKind.DISK_IO

            # Network contention
            net_util = self._get_utilization(comp, ResourceKind.NETWORK_BANDWIDTH)
            if net_util > 70.0:
                net_added = (net_util - 70.0) * 0.6
                if net_added > contention_latency:
                    contention_latency = net_added
                    primary_source = ResourceKind.NETWORK_BANDWIDTH

            # Lock contention (connection pool pressure)
            lock_util = self._get_utilization(comp, ResourceKind.LOCKS)
            if lock_util > 50.0:
                lock_added = (lock_util - 50.0) * 1.2
                if lock_added > contention_latency:
                    contention_latency = lock_added
                    primary_source = ResourceKind.LOCKS

            if contention_latency <= 0.0:
                continue

            total = base_latency + contention_latency
            increase_pct = (contention_latency / base_latency * 100) if base_latency > 0 else 0.0
            severity = self._latency_severity(contention_latency, increase_pct)

            recs: list[str] = []
            if contention_latency > 20.0:
                recs.append(
                    f"'{comp.id}' has {contention_latency:.1f}ms contention-induced latency. "
                    f"Primary source: {primary_source.value}."
                )
            if increase_pct > 100.0:
                recs.append(
                    "Contention more than doubles latency. Urgent capacity increase needed."
                )

            results.append(ContentionLatencyModel(
                component_id=comp.id,
                base_latency_ms=round(base_latency, 2),
                contention_latency_ms=round(contention_latency, 2),
                total_latency_ms=round(total, 2),
                latency_increase_percent=round(increase_pct, 2),
                primary_contention_source=primary_source,
                severity=severity,
                recommendations=recs,
            ))

        results.sort(key=lambda r: self._severity_rank(r.severity))
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_utilization(comp: Component, resource: ResourceKind) -> float:
        """Get current utilization percentage for a resource kind."""
        if resource == ResourceKind.CPU:
            return comp.metrics.cpu_percent
        if resource == ResourceKind.MEMORY:
            return comp.metrics.memory_percent
        if resource == ResourceKind.DISK_IO:
            return comp.metrics.disk_percent
        if resource == ResourceKind.NETWORK_BANDWIDTH:
            if comp.capacity.max_connections > 0:
                return (comp.metrics.network_connections / comp.capacity.max_connections) * 100
            return 0.0
        if resource == ResourceKind.FILE_DESCRIPTORS:
            if comp.metrics.open_files > 0:
                return min(100.0, (comp.metrics.open_files / 65536) * 100)
            return 0.0
        if resource == ResourceKind.LOCKS:
            if comp.capacity.connection_pool_size > 0:
                return (comp.metrics.network_connections / comp.capacity.connection_pool_size) * 100
            return 0.0
        return 0.0

    @staticmethod
    def _group_by_host(
        components: list[Component],
    ) -> dict[str, list[Component]]:
        """Group components by host."""
        groups: dict[str, list[Component]] = {}
        for comp in components:
            if comp.host:
                groups.setdefault(comp.host, []).append(comp)
        return groups

    @staticmethod
    def _find_co_located(
        graph: InfraGraph, comp: Component,
    ) -> list[Component]:
        """Find components co-located on the same host."""
        if not comp.host:
            return []
        return [
            c for c in graph.components.values()
            if c.id != comp.id and c.host == comp.host
        ]

    @staticmethod
    def _infer_isolation(comp: Component) -> IsolationMechanism:
        """Infer isolation mechanism from component tags and parameters."""
        tags = set(comp.tags)
        params = comp.parameters

        if "dedicated_host" in tags or params.get("isolation") == "dedicated":
            return IsolationMechanism.DEDICATED_HOST
        if "cgroup_v2" in tags or params.get("cgroup") == "v2":
            return IsolationMechanism.CGROUP_V2
        if "cgroup_v1" in tags or params.get("cgroup") == "v1":
            return IsolationMechanism.CGROUP_V1
        if "namespace" in tags or params.get("isolation") == "namespace":
            return IsolationMechanism.NAMESPACE
        if "quota" in tags or params.get("quota") == "enabled":
            return IsolationMechanism.QUOTA
        return IsolationMechanism.NONE

    @staticmethod
    def _infer_throttling_policy(comp: Component) -> ThrottlingPolicy:
        """Infer CPU throttling policy from component parameters."""
        policy = comp.parameters.get("cpu_policy", "")
        if isinstance(policy, str):
            policy_lower = policy.lower()
            if policy_lower == "cfs":
                return ThrottlingPolicy.CFS_BANDWIDTH
            if policy_lower == "shares":
                return ThrottlingPolicy.CPU_SHARES
            if policy_lower == "cpuset":
                return ThrottlingPolicy.CPUSET
        return ThrottlingPolicy.NONE

    @staticmethod
    def _get_request(comp: Component, resource: ResourceKind) -> float:
        """Get Kubernetes resource request from component parameters."""
        if resource == ResourceKind.CPU:
            val = comp.parameters.get("cpu_request", 0.0)
        elif resource == ResourceKind.MEMORY:
            val = comp.parameters.get("memory_request", 0.0)
        else:
            return 0.0
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _get_limit(comp: Component, resource: ResourceKind) -> float:
        """Get Kubernetes resource limit from component parameters."""
        if resource == ResourceKind.CPU:
            val = comp.parameters.get("cpu_limit", 0.0)
        elif resource == ResourceKind.MEMORY:
            val = comp.parameters.get("memory_limit", 0.0)
        else:
            return 0.0
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _severity_from_score(score: float) -> ContentionSeverity:
        """Map a numeric score (0-100) to a severity level."""
        if score >= 60.0:
            return ContentionSeverity.CRITICAL
        if score >= 40.0:
            return ContentionSeverity.HIGH
        if score >= 20.0:
            return ContentionSeverity.MEDIUM
        if score > 0.0:
            return ContentionSeverity.LOW
        return ContentionSeverity.NONE

    @staticmethod
    def _severity_rank(severity: ContentionSeverity) -> int:
        """Return sort rank (lower = more severe)."""
        return {
            ContentionSeverity.CRITICAL: 0,
            ContentionSeverity.HIGH: 1,
            ContentionSeverity.MEDIUM: 2,
            ContentionSeverity.LOW: 3,
            ContentionSeverity.NONE: 4,
        }.get(severity, 5)

    @staticmethod
    def _worst_severity(
        severities: list[ContentionSeverity],
    ) -> ContentionSeverity:
        """Return the worst (most severe) severity from a list."""
        if not severities:
            return ContentionSeverity.NONE
        rank = {
            ContentionSeverity.CRITICAL: 0,
            ContentionSeverity.HIGH: 1,
            ContentionSeverity.MEDIUM: 2,
            ContentionSeverity.LOW: 3,
            ContentionSeverity.NONE: 4,
        }
        return min(severities, key=lambda s: rank.get(s, 5))

    @staticmethod
    def _determine_oom_action(mem_percent: float) -> OOMAction:
        """Determine OOM killer action based on memory pressure."""
        if mem_percent >= _MEMORY_PRESSURE_CRITICAL:
            return OOMAction.KILL_PROCESS
        if mem_percent >= _MEMORY_PRESSURE_HIGH:
            return OOMAction.EVICT
        if mem_percent >= _MEMORY_PRESSURE_MEDIUM:
            return OOMAction.THROTTLE
        return OOMAction.NO_ACTION

    @staticmethod
    def _memory_severity(
        mem_percent: float, affected_count: int,
    ) -> ContentionSeverity:
        """Determine severity from memory pressure and cascade size."""
        if mem_percent >= _MEMORY_PRESSURE_CRITICAL and affected_count > 0:
            return ContentionSeverity.CRITICAL
        if mem_percent >= _MEMORY_PRESSURE_HIGH:
            return ContentionSeverity.HIGH
        if mem_percent >= _MEMORY_PRESSURE_MEDIUM:
            return ContentionSeverity.MEDIUM
        return ContentionSeverity.LOW

    @staticmethod
    def _disk_severity(
        disk_percent: float, competing_count: int,
    ) -> ContentionSeverity:
        """Determine severity from disk utilization and competitor count."""
        if disk_percent >= _DISK_CRITICAL_THRESHOLD:
            return ContentionSeverity.CRITICAL
        if disk_percent >= _DISK_SATURATION_THRESHOLD and competing_count > 0:
            return ContentionSeverity.HIGH
        if disk_percent >= _DISK_SATURATION_THRESHOLD:
            return ContentionSeverity.MEDIUM
        if disk_percent >= 60.0:
            return ContentionSeverity.LOW
        return ContentionSeverity.NONE

    @staticmethod
    def _reservation_severity(
        usage: float, request: float, limit: float, qos: str,
    ) -> ContentionSeverity:
        """Determine severity from reservation analysis."""
        if qos == "BestEffort" and usage > 50.0:
            return ContentionSeverity.HIGH
        if limit > 0 and usage > limit:
            return ContentionSeverity.CRITICAL
        if request > 0 and usage > request * 1.5:
            return ContentionSeverity.HIGH
        if request > 0 and usage > request:
            return ContentionSeverity.MEDIUM
        if qos == "BestEffort":
            return ContentionSeverity.LOW
        return ContentionSeverity.NONE

    @staticmethod
    def _latency_severity(
        contention_ms: float, increase_pct: float,
    ) -> ContentionSeverity:
        """Determine severity from contention-induced latency."""
        if contention_ms > 50.0 or increase_pct > 500.0:
            return ContentionSeverity.CRITICAL
        if contention_ms > 20.0 or increase_pct > 200.0:
            return ContentionSeverity.HIGH
        if contention_ms > 10.0 or increase_pct > 100.0:
            return ContentionSeverity.MEDIUM
        if contention_ms > 0.0:
            return ContentionSeverity.LOW
        return ContentionSeverity.NONE

    def _cascade_depth(
        self, graph: InfraGraph, component_id: str,
    ) -> int:
        """Compute the maximum cascade depth from a component."""
        paths = graph.get_cascade_path(component_id)
        if not paths:
            return 0
        return max(len(p) - 1 for p in paths)

    def _lock_chain_depth(
        self, graph: InfraGraph, component_id: str, visited: set[str],
    ) -> int:
        """Compute the depth of the lock chain from a component."""
        if component_id in visited:
            return 0
        visited.add(component_id)
        deps = graph.get_dependencies(component_id)
        lock_deps = [
            d for d in deps
            if d.type in (ComponentType.DATABASE, ComponentType.STORAGE)
        ]
        if not lock_deps:
            return 1
        max_depth = 0
        for dep in lock_deps:
            depth = self._lock_chain_depth(graph, dep.id, visited)
            if depth > max_depth:
                max_depth = depth
        return 1 + max_depth
