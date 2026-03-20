# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Cold Start Analyzer -- cold start performance and resilience analysis.

Analyzes cold start behaviour across infrastructure components: cold start
latency estimation per component, warm-up time modelling (cache warming,
connection pool filling, JIT compilation), cold start cascade analysis
(dependent services cold starting simultaneously), container / serverless
cold start overhead, initialization order dependency resolution, cold start
impact on SLA during scale-out events, pre-warming strategy evaluation,
cold start mitigation scoring (keep-alive, provisioned concurrency),
database connection pool cold start analysis, cold start frequency estimation
based on autoscaling patterns, startup probe timeout adequacy analysis, and
resource consumption spike during cold start.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ColdStartSeverity(str, Enum):
    """Severity levels for cold start analysis findings."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class WarmUpPhase(str, Enum):
    """Warm-up phase types that a component goes through."""

    CACHE_WARMING = "cache_warming"
    CONNECTION_POOL = "connection_pool"
    JIT_COMPILATION = "jit_compilation"
    DNS_RESOLUTION = "dns_resolution"
    TLS_HANDSHAKE = "tls_handshake"
    HEALTH_CHECK = "health_check"


class MitigationStrategy(str, Enum):
    """Mitigation strategies for cold start latency."""

    KEEP_ALIVE = "keep_alive"
    PROVISIONED_CONCURRENCY = "provisioned_concurrency"
    PRE_WARMING = "pre_warming"
    WARM_POOL = "warm_pool"
    SNAPSHOT_RESTORE = "snapshot_restore"
    LAZY_INIT = "lazy_init"
    CONNECTION_POOLING = "connection_pooling"
    CACHED_DNS = "cached_dns"


class ComponentRuntime(str, Enum):
    """Runtime environment classification for cold start estimation."""

    CONTAINER = "container"
    SERVERLESS = "serverless"
    VM = "vm"
    BARE_METAL = "bare_metal"
    MANAGED_SERVICE = "managed_service"


class StartupProbeStatus(str, Enum):
    """Status of startup probe adequacy."""

    ADEQUATE = "adequate"
    TOO_SHORT = "too_short"
    TOO_LONG = "too_long"
    MISSING = "missing"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ColdStartProfile:
    """Cold start timing profile for a single component."""

    component_id: str
    runtime: ComponentRuntime = ComponentRuntime.CONTAINER
    base_start_ms: float = 0.0
    image_pull_ms: float = 0.0
    init_ms: float = 0.0
    dependency_wait_ms: float = 0.0
    total_cold_start_ms: float = 0.0
    warm_start_ms: float = 0.0
    severity: ColdStartSeverity = ColdStartSeverity.INFO


@dataclass
class WarmUpModel:
    """Warm-up time model for a component after cold start."""

    component_id: str
    phases: list[WarmUpPhaseDetail] = field(default_factory=list)
    total_warm_up_ms: float = 0.0
    ready_at_percent: float = 0.0
    full_capacity_ms: float = 0.0


@dataclass
class WarmUpPhaseDetail:
    """Detail for a single warm-up phase."""

    phase: WarmUpPhase
    duration_ms: float = 0.0
    capacity_percent: float = 0.0
    is_blocking: bool = False


@dataclass
class CascadeNode:
    """A node in the cold start cascade tree."""

    component_id: str
    cold_start_ms: float = 0.0
    cumulative_ms: float = 0.0
    depth: int = 0
    children: list[CascadeNode] = field(default_factory=list)


@dataclass
class CascadeAnalysis:
    """Result of cold start cascade analysis."""

    root_component_id: str
    total_cascade_ms: float = 0.0
    max_depth: int = 0
    affected_components: int = 0
    cascade_tree: CascadeNode | None = None
    critical_path: list[str] = field(default_factory=list)
    critical_path_ms: float = 0.0
    severity: ColdStartSeverity = ColdStartSeverity.INFO


@dataclass
class ContainerOverhead:
    """Container or serverless cold start overhead breakdown."""

    component_id: str
    runtime: ComponentRuntime = ComponentRuntime.CONTAINER
    image_pull_ms: float = 0.0
    runtime_init_ms: float = 0.0
    app_init_ms: float = 0.0
    network_setup_ms: float = 0.0
    total_overhead_ms: float = 0.0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class InitOrder:
    """Initialization order for components based on dependency graph."""

    order: list[list[str]] = field(default_factory=list)
    total_layers: int = 0
    has_cycle: bool = False
    cycle_components: list[str] = field(default_factory=list)


@dataclass
class SLAImpact:
    """Cold start impact on SLA during scale-out events."""

    component_id: str
    cold_start_ms: float = 0.0
    sla_target_ms: float = 0.0
    breach_probability: float = 0.0
    affected_requests_percent: float = 0.0
    estimated_error_budget_burn_percent: float = 0.0
    severity: ColdStartSeverity = ColdStartSeverity.INFO
    recommendations: list[str] = field(default_factory=list)


@dataclass
class PreWarmStrategy:
    """Pre-warming strategy evaluation result."""

    strategy: MitigationStrategy
    effectiveness_score: float = 0.0
    cost_impact_percent: float = 0.0
    latency_reduction_ms: float = 0.0
    complexity: str = "low"
    applicable: bool = True
    reason: str = ""


@dataclass
class MitigationScore:
    """Cold start mitigation scoring for a component."""

    component_id: str
    current_score: float = 0.0
    max_score: float = 100.0
    active_mitigations: list[MitigationStrategy] = field(default_factory=list)
    recommended_mitigations: list[PreWarmStrategy] = field(default_factory=list)
    potential_improvement: float = 0.0


@dataclass
class ConnectionPoolAnalysis:
    """Database connection pool cold start analysis."""

    component_id: str
    pool_size: int = 0
    fill_time_ms: float = 0.0
    connection_overhead_ms: float = 0.0
    total_pool_start_ms: float = 0.0
    warmup_queries_needed: int = 0
    steady_state_time_ms: float = 0.0
    severity: ColdStartSeverity = ColdStartSeverity.INFO
    recommendations: list[str] = field(default_factory=list)


@dataclass
class ColdStartFrequency:
    """Cold start frequency estimation based on autoscaling patterns."""

    component_id: str
    estimated_daily_cold_starts: float = 0.0
    scale_events_per_day: float = 0.0
    idle_timeout_cold_starts: float = 0.0
    deployment_cold_starts: float = 0.0
    total_daily_cold_starts: float = 0.0
    severity: ColdStartSeverity = ColdStartSeverity.INFO


@dataclass
class StartupProbeAnalysis:
    """Startup probe timeout adequacy analysis."""

    component_id: str
    probe_timeout_ms: float = 0.0
    estimated_start_ms: float = 0.0
    margin_ms: float = 0.0
    margin_percent: float = 0.0
    status: StartupProbeStatus = StartupProbeStatus.MISSING
    recommendations: list[str] = field(default_factory=list)


@dataclass
class ResourceSpike:
    """Resource consumption spike during cold start."""

    component_id: str
    cpu_spike_percent: float = 0.0
    memory_spike_percent: float = 0.0
    network_spike_mbps: float = 0.0
    disk_io_spike_mbps: float = 0.0
    spike_duration_ms: float = 0.0
    steady_state_cpu: float = 0.0
    steady_state_memory: float = 0.0
    severity: ColdStartSeverity = ColdStartSeverity.INFO
    recommendations: list[str] = field(default_factory=list)


@dataclass
class FullColdStartReport:
    """Complete cold start analysis report for a component."""

    component_id: str
    profile: ColdStartProfile | None = None
    warm_up: WarmUpModel | None = None
    sla_impact: SLAImpact | None = None
    mitigation: MitigationScore | None = None
    connection_pool: ConnectionPoolAnalysis | None = None
    frequency: ColdStartFrequency | None = None
    startup_probe: StartupProbeAnalysis | None = None
    resource_spike: ResourceSpike | None = None
    overall_score: float = 0.0
    severity: ColdStartSeverity = ColdStartSeverity.INFO
    analyzed_at: str = ""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Base cold start latencies by component type (milliseconds)
_BASE_COLD_START_MS: dict[ComponentType, float] = {
    ComponentType.LOAD_BALANCER: 500.0,
    ComponentType.WEB_SERVER: 2000.0,
    ComponentType.APP_SERVER: 3000.0,
    ComponentType.DATABASE: 5000.0,
    ComponentType.CACHE: 1000.0,
    ComponentType.QUEUE: 1500.0,
    ComponentType.STORAGE: 800.0,
    ComponentType.DNS: 200.0,
    ComponentType.EXTERNAL_API: 100.0,
    ComponentType.CUSTOM: 2000.0,
}

# Runtime overhead multipliers
_RUNTIME_MULTIPLIER: dict[ComponentRuntime, float] = {
    ComponentRuntime.CONTAINER: 1.0,
    ComponentRuntime.SERVERLESS: 1.5,
    ComponentRuntime.VM: 3.0,
    ComponentRuntime.BARE_METAL: 5.0,
    ComponentRuntime.MANAGED_SERVICE: 0.5,
}

# Image pull time estimates by runtime (ms)
_IMAGE_PULL_MS: dict[ComponentRuntime, float] = {
    ComponentRuntime.CONTAINER: 2000.0,
    ComponentRuntime.SERVERLESS: 500.0,
    ComponentRuntime.VM: 0.0,
    ComponentRuntime.BARE_METAL: 0.0,
    ComponentRuntime.MANAGED_SERVICE: 0.0,
}

# Connection overhead per database connection (ms)
_CONNECTION_OVERHEAD_MS = 50.0

# Warm-up durations by phase (ms)
_WARMUP_DURATIONS: dict[WarmUpPhase, float] = {
    WarmUpPhase.CACHE_WARMING: 5000.0,
    WarmUpPhase.CONNECTION_POOL: 2000.0,
    WarmUpPhase.JIT_COMPILATION: 3000.0,
    WarmUpPhase.DNS_RESOLUTION: 100.0,
    WarmUpPhase.TLS_HANDSHAKE: 200.0,
    WarmUpPhase.HEALTH_CHECK: 500.0,
}

# Capacity percent after each warm-up phase
_WARMUP_CAPACITY: dict[WarmUpPhase, float] = {
    WarmUpPhase.CACHE_WARMING: 30.0,
    WarmUpPhase.CONNECTION_POOL: 20.0,
    WarmUpPhase.JIT_COMPILATION: 25.0,
    WarmUpPhase.DNS_RESOLUTION: 5.0,
    WarmUpPhase.TLS_HANDSHAKE: 5.0,
    WarmUpPhase.HEALTH_CHECK: 15.0,
}


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------

class ColdStartAnalyzer:
    """Analyzes cold start behaviour across infrastructure components.

    Provides comprehensive analysis of cold start latency, warm-up time,
    cascade effects, container overhead, initialization order, SLA impact,
    pre-warming strategies, mitigation scoring, connection pool analysis,
    frequency estimation, startup probe adequacy, and resource spikes.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph
        self._profiles: dict[str, ColdStartProfile] = {}
        self._runtime_overrides: dict[str, ComponentRuntime] = {}
        self._probe_timeouts: dict[str, float] = {}
        self._sla_targets: dict[str, float] = {}
        self._mitigation_configs: dict[str, list[MitigationStrategy]] = {}

    # -- Configuration --

    def set_runtime(self, component_id: str, runtime: ComponentRuntime) -> None:
        """Override the runtime classification for a component."""
        self._runtime_overrides[component_id] = runtime

    def set_probe_timeout(self, component_id: str, timeout_ms: float) -> None:
        """Set the startup probe timeout for a component."""
        self._probe_timeouts[component_id] = timeout_ms

    def set_sla_target(self, component_id: str, target_ms: float) -> None:
        """Set the SLA latency target for a component."""
        self._sla_targets[component_id] = target_ms

    def set_mitigations(
        self, component_id: str, mitigations: list[MitigationStrategy]
    ) -> None:
        """Set the active mitigation strategies for a component."""
        self._mitigation_configs[component_id] = list(mitigations)

    def get_runtime(self, component_id: str) -> ComponentRuntime:
        """Get the runtime classification for a component."""
        if component_id in self._runtime_overrides:
            return self._runtime_overrides[component_id]
        comp = self._graph.get_component(component_id)
        if comp is None:
            return ComponentRuntime.CONTAINER
        return self._infer_runtime(comp)

    # -- Cold Start Latency Estimation --

    def estimate_cold_start(self, component_id: str) -> ColdStartProfile:
        """Estimate cold start latency for a single component."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return ColdStartProfile(
                component_id=component_id,
                severity=ColdStartSeverity.INFO,
            )

        runtime = self.get_runtime(component_id)
        base = _BASE_COLD_START_MS.get(comp.type, 2000.0)
        multiplier = _RUNTIME_MULTIPLIER.get(runtime, 1.0)
        image_pull = _IMAGE_PULL_MS.get(runtime, 0.0)

        init_ms = base * multiplier
        dep_wait = self._estimate_dependency_wait(component_id)
        total = image_pull + init_ms + dep_wait
        warm_start = base * 0.1

        severity = self._cold_start_severity(total)

        profile = ColdStartProfile(
            component_id=component_id,
            runtime=runtime,
            base_start_ms=base,
            image_pull_ms=image_pull,
            init_ms=init_ms,
            dependency_wait_ms=dep_wait,
            total_cold_start_ms=total,
            warm_start_ms=warm_start,
            severity=severity,
        )
        self._profiles[component_id] = profile
        return profile

    def estimate_all_cold_starts(self) -> list[ColdStartProfile]:
        """Estimate cold start latency for all components in the graph."""
        profiles: list[ColdStartProfile] = []
        for cid in self._graph.components:
            profiles.append(self.estimate_cold_start(cid))
        return profiles

    # -- Warm-Up Time Modelling --

    def model_warm_up(self, component_id: str) -> WarmUpModel:
        """Model warm-up phases after cold start for a component."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return WarmUpModel(component_id=component_id)

        phases = self._determine_warm_up_phases(comp)
        details: list[WarmUpPhaseDetail] = []
        total_ms = 0.0
        total_capacity = 0.0

        for phase in phases:
            dur = _WARMUP_DURATIONS.get(phase, 1000.0)
            cap = _WARMUP_CAPACITY.get(phase, 10.0)
            is_blocking = phase in (
                WarmUpPhase.DNS_RESOLUTION,
                WarmUpPhase.TLS_HANDSHAKE,
                WarmUpPhase.HEALTH_CHECK,
            )
            details.append(WarmUpPhaseDetail(
                phase=phase,
                duration_ms=dur,
                capacity_percent=cap,
                is_blocking=is_blocking,
            ))
            if is_blocking:
                total_ms += dur
            else:
                total_ms = max(total_ms, dur)
            total_capacity += cap

        ready_pct = min(100.0, total_capacity)
        blocking_total = sum(d.duration_ms for d in details if d.is_blocking)
        non_blocking_max = max(
            (d.duration_ms for d in details if not d.is_blocking), default=0.0
        )
        full_capacity_ms = blocking_total + non_blocking_max

        return WarmUpModel(
            component_id=component_id,
            phases=details,
            total_warm_up_ms=full_capacity_ms,
            ready_at_percent=ready_pct,
            full_capacity_ms=full_capacity_ms,
        )

    # -- Cold Start Cascade Analysis --

    def analyze_cascade(self, root_component_id: str) -> CascadeAnalysis:
        """Analyze cold start cascade when a component and its deps cold start."""
        comp = self._graph.get_component(root_component_id)
        if comp is None:
            return CascadeAnalysis(root_component_id=root_component_id)

        visited: set[str] = set()
        tree = self._build_cascade_tree(root_component_id, visited, depth=0)

        max_depth = self._tree_max_depth(tree)
        affected = self._tree_count_nodes(tree) - 1  # exclude root
        critical_path, critical_ms = self._find_critical_path(tree)

        severity = self._cascade_severity(critical_ms, affected)

        return CascadeAnalysis(
            root_component_id=root_component_id,
            total_cascade_ms=tree.cumulative_ms,
            max_depth=max_depth,
            affected_components=affected,
            cascade_tree=tree,
            critical_path=critical_path,
            critical_path_ms=critical_ms,
            severity=severity,
        )

    # -- Container / Serverless Cold Start Overhead --

    def analyze_container_overhead(self, component_id: str) -> ContainerOverhead:
        """Break down container/serverless cold start overhead."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return ContainerOverhead(component_id=component_id)

        runtime = self.get_runtime(component_id)
        image_pull = _IMAGE_PULL_MS.get(runtime, 0.0)
        base = _BASE_COLD_START_MS.get(comp.type, 2000.0) if comp else 2000.0
        multiplier = _RUNTIME_MULTIPLIER.get(runtime, 1.0)

        runtime_init = base * multiplier * 0.3
        app_init = base * multiplier * 0.7
        network_setup = comp.network.rtt_ms * 2 + comp.network.dns_resolution_ms

        total = image_pull + runtime_init + app_init + network_setup

        recs: list[str] = []
        if runtime == ComponentRuntime.CONTAINER and image_pull > 1500:
            recs.append(
                "Use a smaller base image or multi-stage build to reduce pull time."
            )
        if runtime == ComponentRuntime.SERVERLESS:
            recs.append(
                "Consider provisioned concurrency to eliminate cold starts."
            )
        if app_init > 3000:
            recs.append(
                "Defer non-critical initialization to reduce cold start latency."
            )
        if network_setup > 100:
            recs.append("Cache DNS resolution and reuse TLS sessions.")

        return ContainerOverhead(
            component_id=component_id,
            runtime=runtime,
            image_pull_ms=image_pull,
            runtime_init_ms=runtime_init,
            app_init_ms=app_init,
            network_setup_ms=network_setup,
            total_overhead_ms=total,
            recommendations=recs,
        )

    # -- Initialization Order Dependency Resolution --

    def resolve_init_order(self) -> InitOrder:
        """Resolve the initialization order based on dependency topology.

        Uses topological sort in layers.  Each layer can be started in
        parallel.  Components without dependencies come first.
        """
        components = set(self._graph.components.keys())
        if not components:
            return InitOrder()

        # Build adjacency from dependency edges
        in_degree: dict[str, int] = {cid: 0 for cid in components}
        children: dict[str, list[str]] = {cid: [] for cid in components}

        for edge in self._graph.all_dependency_edges():
            src = edge.source_id
            tgt = edge.target_id
            if src in components and tgt in components:
                in_degree[src] = in_degree.get(src, 0) + 1
                children.setdefault(tgt, []).append(src)

        layers: list[list[str]] = []
        remaining = set(components)

        while remaining:
            layer = [
                cid for cid in remaining
                if in_degree.get(cid, 0) == 0
            ]
            if not layer:
                # Cycle detected
                return InitOrder(
                    order=layers,
                    total_layers=len(layers),
                    has_cycle=True,
                    cycle_components=sorted(remaining),
                )
            layer.sort()
            layers.append(layer)
            for cid in layer:
                remaining.discard(cid)
                for child in children.get(cid, []):
                    if child in in_degree:
                        in_degree[child] -= 1

        return InitOrder(
            order=layers,
            total_layers=len(layers),
            has_cycle=False,
        )

    # -- Cold Start Impact on SLA --

    def analyze_sla_impact(
        self,
        component_id: str,
        sla_target_ms: float | None = None,
        scale_out_count: int = 1,
    ) -> SLAImpact:
        """Analyze cold start impact on SLA during scale-out events."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return SLAImpact(component_id=component_id)

        target = sla_target_ms or self._sla_targets.get(component_id, 500.0)
        profile = self._profiles.get(component_id)
        if profile is None:
            profile = self.estimate_cold_start(component_id)

        cold_ms = profile.total_cold_start_ms

        # Probability of SLA breach during cold start
        if target <= 0:
            breach_prob = 1.0
        elif cold_ms <= target:
            breach_prob = 0.0
        else:
            # Ratio of cold start exceeding SLA target
            breach_prob = min(1.0, (cold_ms - target) / target)

        # Affected requests percent during scale-out
        # During cold start, new instances handle no requests
        replicas = max(1, comp.replicas)
        if replicas + scale_out_count > 0:
            affected_pct = (scale_out_count / (replicas + scale_out_count)) * 100.0
        else:
            affected_pct = 100.0

        # Error budget burn: higher cold start = more budget consumed
        budget_burn = breach_prob * affected_pct
        budget_burn = min(100.0, budget_burn)

        recs: list[str] = []
        severity = ColdStartSeverity.INFO
        if breach_prob > 0.8:
            severity = ColdStartSeverity.CRITICAL
            recs.append(
                "Cold start significantly exceeds SLA. Use provisioned concurrency "
                "or pre-warming."
            )
        elif breach_prob > 0.5:
            severity = ColdStartSeverity.HIGH
            recs.append("Cold start exceeds SLA target. Consider warm pool strategy.")
        elif breach_prob > 0.2:
            severity = ColdStartSeverity.MEDIUM
            recs.append("Cold start may occasionally breach SLA. Monitor closely.")
        elif breach_prob > 0.0:
            severity = ColdStartSeverity.LOW
            recs.append("Minor SLA risk from cold start. Acceptable in most cases.")

        return SLAImpact(
            component_id=component_id,
            cold_start_ms=cold_ms,
            sla_target_ms=target,
            breach_probability=breach_prob,
            affected_requests_percent=affected_pct,
            estimated_error_budget_burn_percent=budget_burn,
            severity=severity,
            recommendations=recs,
        )

    # -- Pre-Warming Strategy Evaluation --

    def evaluate_pre_warming(
        self, component_id: str
    ) -> list[PreWarmStrategy]:
        """Evaluate pre-warming strategies for a component."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return []

        runtime = self.get_runtime(component_id)
        profile = self._profiles.get(component_id)
        if profile is None:
            profile = self.estimate_cold_start(component_id)

        cold_ms = profile.total_cold_start_ms
        strategies: list[PreWarmStrategy] = []

        # Keep-alive
        strategies.append(PreWarmStrategy(
            strategy=MitigationStrategy.KEEP_ALIVE,
            effectiveness_score=70.0,
            cost_impact_percent=10.0,
            latency_reduction_ms=cold_ms * 0.9,
            complexity="low",
            applicable=True,
            reason="Keeps instances warm by periodic health checks.",
        ))

        # Provisioned concurrency -- best for serverless
        is_serverless = runtime == ComponentRuntime.SERVERLESS
        strategies.append(PreWarmStrategy(
            strategy=MitigationStrategy.PROVISIONED_CONCURRENCY,
            effectiveness_score=95.0 if is_serverless else 40.0,
            cost_impact_percent=30.0 if is_serverless else 50.0,
            latency_reduction_ms=cold_ms * 0.95 if is_serverless else cold_ms * 0.3,
            complexity="medium",
            applicable=is_serverless,
            reason=(
                "Eliminates cold starts for serverless."
                if is_serverless
                else "Less applicable to non-serverless runtimes."
            ),
        ))

        # Pre-warming
        strategies.append(PreWarmStrategy(
            strategy=MitigationStrategy.PRE_WARMING,
            effectiveness_score=80.0,
            cost_impact_percent=15.0,
            latency_reduction_ms=cold_ms * 0.8,
            complexity="medium",
            applicable=True,
            reason="Pre-starts instances before anticipated demand.",
        ))

        # Warm pool
        strategies.append(PreWarmStrategy(
            strategy=MitigationStrategy.WARM_POOL,
            effectiveness_score=85.0,
            cost_impact_percent=20.0,
            latency_reduction_ms=cold_ms * 0.85,
            complexity="medium",
            applicable=runtime in (ComponentRuntime.CONTAINER, ComponentRuntime.VM),
            reason="Maintains pre-initialized instances ready for use.",
        ))

        # Snapshot restore
        strategies.append(PreWarmStrategy(
            strategy=MitigationStrategy.SNAPSHOT_RESTORE,
            effectiveness_score=75.0,
            cost_impact_percent=5.0,
            latency_reduction_ms=cold_ms * 0.7,
            complexity="high",
            applicable=runtime != ComponentRuntime.MANAGED_SERVICE,
            reason="Restores from snapshot to skip initialization.",
        ))

        # Lazy init
        strategies.append(PreWarmStrategy(
            strategy=MitigationStrategy.LAZY_INIT,
            effectiveness_score=50.0,
            cost_impact_percent=0.0,
            latency_reduction_ms=cold_ms * 0.4,
            complexity="low",
            applicable=True,
            reason="Defers non-critical initialization to after first request.",
        ))

        # Connection pooling
        is_db = comp.type == ComponentType.DATABASE
        strategies.append(PreWarmStrategy(
            strategy=MitigationStrategy.CONNECTION_POOLING,
            effectiveness_score=60.0 if is_db else 30.0,
            cost_impact_percent=2.0,
            latency_reduction_ms=cold_ms * 0.5 if is_db else cold_ms * 0.1,
            complexity="low",
            applicable=True,
            reason="Reuses existing connections to reduce connection setup time.",
        ))

        # Cached DNS
        strategies.append(PreWarmStrategy(
            strategy=MitigationStrategy.CACHED_DNS,
            effectiveness_score=20.0,
            cost_impact_percent=0.0,
            latency_reduction_ms=min(cold_ms * 0.05, 200.0),
            complexity="low",
            applicable=True,
            reason="Caches DNS resolution results to avoid lookup on start.",
        ))

        return strategies

    # -- Cold Start Mitigation Scoring --

    def score_mitigation(self, component_id: str) -> MitigationScore:
        """Score current cold start mitigation and suggest improvements."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return MitigationScore(component_id=component_id)

        active = self._mitigation_configs.get(component_id, [])
        strategies = self.evaluate_pre_warming(component_id)

        # Calculate current score from active mitigations
        current_score = 0.0
        for strat in strategies:
            if strat.strategy in active:
                current_score += strat.effectiveness_score * 0.15
        current_score = min(100.0, current_score)

        # Filter recommended strategies that are not active and applicable
        recommended: list[PreWarmStrategy] = []
        for strat in strategies:
            if strat.strategy not in active and strat.applicable:
                recommended.append(strat)

        # Sort by effectiveness descending
        recommended.sort(key=lambda s: s.effectiveness_score, reverse=True)

        potential = 0.0
        for strat in recommended:
            potential += strat.effectiveness_score * 0.15
        potential = min(100.0 - current_score, potential)

        return MitigationScore(
            component_id=component_id,
            current_score=round(current_score, 1),
            max_score=100.0,
            active_mitigations=list(active),
            recommended_mitigations=recommended,
            potential_improvement=round(potential, 1),
        )

    # -- Database Connection Pool Cold Start Analysis --

    def analyze_connection_pool(self, component_id: str) -> ConnectionPoolAnalysis:
        """Analyze database connection pool cold start behaviour."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return ConnectionPoolAnalysis(component_id=component_id)

        pool_size = comp.capacity.connection_pool_size
        conn_overhead = _CONNECTION_OVERHEAD_MS
        fill_time = pool_size * conn_overhead
        warmup_queries = max(1, pool_size // 10)
        query_time = warmup_queries * 20.0  # 20ms per warmup query
        total = fill_time + query_time
        steady_state = total * 1.5  # add buffer to reach steady state

        recs: list[str] = []
        severity = ColdStartSeverity.INFO

        if pool_size > 200:
            severity = ColdStartSeverity.HIGH
            recs.append(
                f"Large pool size ({pool_size}). Consider lazy pool initialization."
            )
        elif pool_size > 100:
            severity = ColdStartSeverity.MEDIUM
            recs.append("Moderate pool size. Monitor fill time during scale-out.")

        if fill_time > 5000:
            recs.append(
                "Pool fill time exceeds 5s. Use connection pre-warming or "
                "reduce initial pool size."
            )

        if comp.type != ComponentType.DATABASE:
            recs.append(
                "Component is not a database. Connection pool analysis "
                "may not be fully applicable."
            )

        return ConnectionPoolAnalysis(
            component_id=component_id,
            pool_size=pool_size,
            fill_time_ms=fill_time,
            connection_overhead_ms=conn_overhead,
            total_pool_start_ms=total,
            warmup_queries_needed=warmup_queries,
            steady_state_time_ms=steady_state,
            severity=severity,
            recommendations=recs,
        )

    # -- Cold Start Frequency Estimation --

    def estimate_frequency(self, component_id: str) -> ColdStartFrequency:
        """Estimate cold start frequency based on autoscaling patterns."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return ColdStartFrequency(component_id=component_id)

        autoscaling = comp.autoscaling

        # Scale events per day
        if autoscaling.enabled:
            # Estimate based on autoscaling config
            range_size = autoscaling.max_replicas - autoscaling.min_replicas
            if range_size <= 0:
                scale_events = 0.0
            else:
                # Assume typical workload pattern: ~4 scale-ups and 4 scale-downs
                scale_events = min(range_size * 2.0, 8.0)
        else:
            scale_events = 0.0

        # Idle timeout cold starts (if min replicas is 0 or serverless)
        runtime = self.get_runtime(component_id)
        if runtime == ComponentRuntime.SERVERLESS:
            idle_cold_starts = 12.0  # typical for serverless with idle periods
        elif autoscaling.enabled and autoscaling.min_replicas == 1:
            idle_cold_starts = 2.0
        else:
            idle_cold_starts = 0.0

        # Deployment-triggered cold starts (assume 1 deploy/day)
        deploy_cold_starts = float(comp.replicas)

        total = scale_events + idle_cold_starts + deploy_cold_starts

        severity = ColdStartSeverity.INFO
        if total > 20:
            severity = ColdStartSeverity.HIGH
        elif total > 10:
            severity = ColdStartSeverity.MEDIUM
        elif total > 5:
            severity = ColdStartSeverity.LOW

        return ColdStartFrequency(
            component_id=component_id,
            estimated_daily_cold_starts=total,
            scale_events_per_day=scale_events,
            idle_timeout_cold_starts=idle_cold_starts,
            deployment_cold_starts=deploy_cold_starts,
            total_daily_cold_starts=total,
            severity=severity,
        )

    # -- Startup Probe Timeout Adequacy Analysis --

    def analyze_startup_probe(self, component_id: str) -> StartupProbeAnalysis:
        """Analyze whether startup probe timeout is adequate."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return StartupProbeAnalysis(component_id=component_id)

        profile = self._profiles.get(component_id)
        if profile is None:
            profile = self.estimate_cold_start(component_id)

        estimated_start = profile.total_cold_start_ms
        probe_timeout = self._probe_timeouts.get(component_id, 0.0)

        recs: list[str] = []

        if probe_timeout <= 0:
            status = StartupProbeStatus.MISSING
            margin = 0.0
            margin_pct = 0.0
            recs.append(
                "No startup probe configured. Add one with timeout >= "
                f"{estimated_start * 1.5:.0f}ms."
            )
        else:
            margin = probe_timeout - estimated_start
            if estimated_start > 0:
                margin_pct = (margin / estimated_start) * 100.0
            else:
                margin_pct = 100.0

            if margin_pct >= 50.0:
                status = StartupProbeStatus.ADEQUATE
            elif margin_pct >= 0:
                status = StartupProbeStatus.TOO_SHORT
                recs.append(
                    f"Probe timeout has only {margin_pct:.0f}% margin. "
                    f"Increase to at least {estimated_start * 1.5:.0f}ms."
                )
            else:
                status = StartupProbeStatus.TOO_SHORT
                recs.append(
                    f"Probe timeout ({probe_timeout:.0f}ms) is shorter than "
                    f"estimated cold start ({estimated_start:.0f}ms). "
                    "Component will be killed before startup completes."
                )

            if probe_timeout > estimated_start * 5:
                status = StartupProbeStatus.TOO_LONG
                recs.append(
                    f"Probe timeout ({probe_timeout:.0f}ms) is much longer than "
                    f"needed ({estimated_start:.0f}ms). "
                    "This delays failure detection."
                )

        return StartupProbeAnalysis(
            component_id=component_id,
            probe_timeout_ms=probe_timeout,
            estimated_start_ms=estimated_start,
            margin_ms=margin,
            margin_percent=margin_pct,
            status=status,
            recommendations=recs,
        )

    # -- Resource Consumption Spike During Cold Start --

    def analyze_resource_spike(self, component_id: str) -> ResourceSpike:
        """Analyze resource consumption spike during cold start."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return ResourceSpike(component_id=component_id)

        profile = self._profiles.get(component_id)
        if profile is None:
            profile = self.estimate_cold_start(component_id)

        # Estimate spike based on component type and runtime
        runtime = self.get_runtime(component_id)
        type_multiplier = self._type_spike_multiplier(comp.type)
        runtime_multiplier = _RUNTIME_MULTIPLIER.get(runtime, 1.0)

        base_cpu = comp.metrics.cpu_percent if comp.metrics.cpu_percent > 0 else 20.0
        base_mem = (
            comp.metrics.memory_percent if comp.metrics.memory_percent > 0 else 30.0
        )

        # During cold start CPU and memory spike
        cpu_spike = min(100.0, base_cpu * type_multiplier * runtime_multiplier)
        mem_spike = min(100.0, base_mem * type_multiplier * (runtime_multiplier * 0.7))

        # Network spike from image pull and connection setup
        network_spike = 0.0
        if runtime in (ComponentRuntime.CONTAINER, ComponentRuntime.SERVERLESS):
            network_spike = 50.0 * runtime_multiplier

        # Disk IO spike from image extraction and initialization
        disk_spike = 0.0
        if runtime == ComponentRuntime.CONTAINER:
            disk_spike = 30.0
        elif runtime == ComponentRuntime.VM:
            disk_spike = 60.0

        spike_duration = profile.total_cold_start_ms

        recs: list[str] = []
        severity = ColdStartSeverity.INFO

        if cpu_spike > 80:
            severity = ColdStartSeverity.HIGH
            recs.append(
                f"CPU spikes to {cpu_spike:.0f}% during cold start. "
                "Set resource requests/limits appropriately."
            )
        elif cpu_spike > 60:
            severity = ColdStartSeverity.MEDIUM
            recs.append("Moderate CPU spike during cold start. Monitor for throttling.")

        if mem_spike > 80:
            if severity != ColdStartSeverity.HIGH:
                severity = ColdStartSeverity.HIGH
            recs.append(
                f"Memory spikes to {mem_spike:.0f}% during cold start. "
                "Risk of OOM kill."
            )

        return ResourceSpike(
            component_id=component_id,
            cpu_spike_percent=round(cpu_spike, 1),
            memory_spike_percent=round(mem_spike, 1),
            network_spike_mbps=round(network_spike, 1),
            disk_io_spike_mbps=round(disk_spike, 1),
            spike_duration_ms=spike_duration,
            steady_state_cpu=base_cpu,
            steady_state_memory=base_mem,
            severity=severity,
            recommendations=recs,
        )

    # -- Full Analysis --

    def analyze(self, component_id: str | None = None) -> list[FullColdStartReport]:
        """Run full cold start analysis for one or all components."""
        if component_id is not None:
            comp = self._graph.get_component(component_id)
            if comp is None:
                return [FullColdStartReport(
                    component_id=component_id,
                    overall_score=0.0,
                    severity=ColdStartSeverity.INFO,
                    analyzed_at=datetime.now(timezone.utc).isoformat(),
                )]
            return [self._analyze_single(component_id)]

        reports: list[FullColdStartReport] = []
        for cid in self._graph.components:
            reports.append(self._analyze_single(cid))
        return reports

    def generate_summary(
        self, reports: list[FullColdStartReport]
    ) -> dict[str, Any]:
        """Generate summary statistics from a list of reports."""
        if not reports:
            return {
                "total_components": 0,
                "average_score": 0.0,
                "worst_component": "",
                "worst_score": 0.0,
                "severity_counts": {},
                "recommendations_count": 0,
            }

        scores = [r.overall_score for r in reports]
        avg_score = statistics.mean(scores)
        worst_report = min(reports, key=lambda r: r.overall_score)

        severity_counts: dict[str, int] = {}
        total_recs = 0
        for r in reports:
            sev = r.severity.value
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
            if r.sla_impact:
                total_recs += len(r.sla_impact.recommendations)
            if r.resource_spike:
                total_recs += len(r.resource_spike.recommendations)
            if r.connection_pool:
                total_recs += len(r.connection_pool.recommendations)
            if r.startup_probe:
                total_recs += len(r.startup_probe.recommendations)

        return {
            "total_components": len(reports),
            "average_score": round(avg_score, 1),
            "worst_component": worst_report.component_id,
            "worst_score": worst_report.overall_score,
            "severity_counts": severity_counts,
            "recommendations_count": total_recs,
        }

    # -- Internal helpers --

    def _analyze_single(self, component_id: str) -> FullColdStartReport:
        """Run all analyses for a single component and combine into a report."""
        profile = self.estimate_cold_start(component_id)
        warm_up = self.model_warm_up(component_id)
        sla_impact = self.analyze_sla_impact(component_id)
        mitigation = self.score_mitigation(component_id)
        conn_pool = self.analyze_connection_pool(component_id)
        frequency = self.estimate_frequency(component_id)
        probe = self.analyze_startup_probe(component_id)
        spike = self.analyze_resource_spike(component_id)

        # Overall score: weighted average of sub-scores
        score = self._compute_overall_score(
            profile, sla_impact, mitigation, frequency, probe, spike,
        )
        severity = self._overall_severity(score)

        return FullColdStartReport(
            component_id=component_id,
            profile=profile,
            warm_up=warm_up,
            sla_impact=sla_impact,
            mitigation=mitigation,
            connection_pool=conn_pool,
            frequency=frequency,
            startup_probe=probe,
            resource_spike=spike,
            overall_score=round(score, 1),
            severity=severity,
            analyzed_at=datetime.now(timezone.utc).isoformat(),
        )

    def _compute_overall_score(
        self,
        profile: ColdStartProfile,
        sla_impact: SLAImpact,
        mitigation: MitigationScore,
        frequency: ColdStartFrequency,
        probe: StartupProbeAnalysis,
        spike: ResourceSpike,
    ) -> float:
        """Compute overall cold start resilience score (0-100)."""
        score = 100.0

        # Penalize high cold start latency
        if profile.total_cold_start_ms > 10000:
            score -= 30.0
        elif profile.total_cold_start_ms > 5000:
            score -= 20.0
        elif profile.total_cold_start_ms > 2000:
            score -= 10.0

        # Penalize SLA breach probability
        score -= sla_impact.breach_probability * 20.0

        # Reward mitigations
        score += mitigation.current_score * 0.1

        # Penalize high frequency
        if frequency.total_daily_cold_starts > 20:
            score -= 15.0
        elif frequency.total_daily_cold_starts > 10:
            score -= 8.0

        # Penalize missing/short probe
        if probe.status == StartupProbeStatus.MISSING:
            score -= 10.0
        elif probe.status == StartupProbeStatus.TOO_SHORT:
            score -= 5.0

        # Penalize resource spikes
        if spike.cpu_spike_percent > 80:
            score -= 10.0
        elif spike.cpu_spike_percent > 60:
            score -= 5.0

        return max(0.0, min(100.0, score))

    @staticmethod
    def _cold_start_severity(total_ms: float) -> ColdStartSeverity:
        """Derive severity from total cold start milliseconds."""
        if total_ms > 15000:
            return ColdStartSeverity.CRITICAL
        if total_ms > 8000:
            return ColdStartSeverity.HIGH
        if total_ms > 4000:
            return ColdStartSeverity.MEDIUM
        if total_ms > 1500:
            return ColdStartSeverity.LOW
        return ColdStartSeverity.INFO

    @staticmethod
    def _cascade_severity(
        critical_path_ms: float, affected_count: int
    ) -> ColdStartSeverity:
        """Derive severity from cascade analysis."""
        if critical_path_ms > 30000 or affected_count > 10:
            return ColdStartSeverity.CRITICAL
        if critical_path_ms > 15000 or affected_count > 5:
            return ColdStartSeverity.HIGH
        if critical_path_ms > 8000 or affected_count > 3:
            return ColdStartSeverity.MEDIUM
        if critical_path_ms > 3000 or affected_count > 1:
            return ColdStartSeverity.LOW
        return ColdStartSeverity.INFO

    @staticmethod
    def _overall_severity(score: float) -> ColdStartSeverity:
        """Derive overall severity from score."""
        if score >= 90:
            return ColdStartSeverity.INFO
        if score >= 70:
            return ColdStartSeverity.LOW
        if score >= 50:
            return ColdStartSeverity.MEDIUM
        if score >= 30:
            return ColdStartSeverity.HIGH
        return ColdStartSeverity.CRITICAL

    @staticmethod
    def _infer_runtime(comp: Component) -> ComponentRuntime:
        """Infer runtime from component type and tags."""
        if "serverless" in comp.tags:
            return ComponentRuntime.SERVERLESS
        if "vm" in comp.tags:
            return ComponentRuntime.VM
        if "bare_metal" in comp.tags:
            return ComponentRuntime.BARE_METAL
        if comp.type == ComponentType.EXTERNAL_API:
            return ComponentRuntime.MANAGED_SERVICE
        if comp.type in (ComponentType.DATABASE, ComponentType.CACHE):
            return ComponentRuntime.MANAGED_SERVICE
        return ComponentRuntime.CONTAINER

    @staticmethod
    def _type_spike_multiplier(ctype: ComponentType) -> float:
        """Return resource spike multiplier by component type."""
        multipliers: dict[ComponentType, float] = {
            ComponentType.DATABASE: 2.5,
            ComponentType.APP_SERVER: 2.0,
            ComponentType.WEB_SERVER: 1.5,
            ComponentType.CACHE: 1.8,
            ComponentType.QUEUE: 1.3,
            ComponentType.LOAD_BALANCER: 1.2,
            ComponentType.STORAGE: 1.4,
            ComponentType.DNS: 1.0,
            ComponentType.EXTERNAL_API: 1.0,
            ComponentType.CUSTOM: 1.5,
        }
        return multipliers.get(ctype, 1.5)

    def _estimate_dependency_wait(self, component_id: str) -> float:
        """Estimate time waiting for dependencies to be ready."""
        deps = self._graph.get_dependencies(component_id)
        if not deps:
            return 0.0

        max_wait = 0.0
        for dep in deps:
            edge = self._graph.get_dependency_edge(component_id, dep.id)
            dep_base = _BASE_COLD_START_MS.get(dep.type, 2000.0)
            latency = edge.latency_ms if edge else 0.0

            if edge and edge.dependency_type == "requires":
                wait = dep_base * 0.3 + latency
            elif edge and edge.dependency_type == "optional":
                wait = dep_base * 0.1 + latency
            else:
                wait = latency
            max_wait = max(max_wait, wait)
        return max_wait

    def _determine_warm_up_phases(self, comp: Component) -> list[WarmUpPhase]:
        """Determine which warm-up phases apply to a component type."""
        phases: list[WarmUpPhase] = [
            WarmUpPhase.DNS_RESOLUTION,
            WarmUpPhase.HEALTH_CHECK,
        ]

        if comp.type in (ComponentType.WEB_SERVER, ComponentType.APP_SERVER):
            phases.extend([
                WarmUpPhase.TLS_HANDSHAKE,
                WarmUpPhase.JIT_COMPILATION,
                WarmUpPhase.CONNECTION_POOL,
            ])
        elif comp.type == ComponentType.DATABASE:
            phases.extend([
                WarmUpPhase.CONNECTION_POOL,
                WarmUpPhase.CACHE_WARMING,
            ])
        elif comp.type == ComponentType.CACHE:
            phases.append(WarmUpPhase.CACHE_WARMING)
        elif comp.type == ComponentType.LOAD_BALANCER:
            phases.append(WarmUpPhase.TLS_HANDSHAKE)

        return phases

    def _build_cascade_tree(
        self,
        component_id: str,
        visited: set[str],
        depth: int,
    ) -> CascadeNode:
        """Recursively build cascade tree from dependency graph."""
        visited.add(component_id)
        profile = self._profiles.get(component_id)
        if profile is None:
            profile = self.estimate_cold_start(component_id)

        cold_ms = profile.total_cold_start_ms
        node = CascadeNode(
            component_id=component_id,
            cold_start_ms=cold_ms,
            cumulative_ms=cold_ms,
            depth=depth,
        )

        # Get components that depend ON this component
        dependents = self._graph.get_dependents(component_id)
        for dep in dependents:
            if dep.id not in visited:
                child = self._build_cascade_tree(dep.id, visited, depth + 1)
                child.cumulative_ms = cold_ms + child.cold_start_ms
                node.children.append(child)

        # Update cumulative to reflect the longest child chain
        if node.children:
            max_child_cumulative = max(c.cumulative_ms for c in node.children)
            node.cumulative_ms = max(node.cumulative_ms, max_child_cumulative)

        return node

    @staticmethod
    def _tree_max_depth(node: CascadeNode) -> int:
        """Find maximum depth in cascade tree."""
        if not node.children:
            return node.depth
        return max(ColdStartAnalyzer._tree_max_depth(c) for c in node.children)

    @staticmethod
    def _tree_count_nodes(node: CascadeNode) -> int:
        """Count total nodes in cascade tree."""
        count = 1
        for child in node.children:
            count += ColdStartAnalyzer._tree_count_nodes(child)
        return count

    @staticmethod
    def _find_critical_path(node: CascadeNode) -> tuple[list[str], float]:
        """Find the longest latency path in the cascade tree."""
        if not node.children:
            return [node.component_id], node.cold_start_ms

        best_path: list[str] = []
        best_ms = 0.0
        for child in node.children:
            child_path, child_ms = ColdStartAnalyzer._find_critical_path(child)
            total = node.cold_start_ms + child_ms
            if total > best_ms:
                best_ms = total
                best_path = [node.component_id] + child_path

        if not best_path:
            return [node.component_id], node.cold_start_ms

        return best_path, best_ms
