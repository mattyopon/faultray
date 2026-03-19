"""Throttle Cascade Analyzer -- models how rate-limiting and throttling
propagate across service dependency chains.

Provides upstream throttle propagation modeling, downstream backpressure
cascade analysis, throttle budget distribution across service chains,
priority-based throttling fairness analysis, adaptive throttle threshold
optimization, throttle-induced retry storm detection, per-tenant throttle
isolation assessment, throttle response code handling analysis (429 vs 503),
throttle window alignment across services, global vs local rate limit
coordination, throttle bypass vulnerability detection, and throttle
capacity planning under load spikes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ThrottleDirection(str, Enum):
    """Direction of throttle propagation."""

    UPSTREAM = "upstream"
    DOWNSTREAM = "downstream"
    BIDIRECTIONAL = "bidirectional"


class ThrottleResponseCode(str, Enum):
    """HTTP response codes used for throttling."""

    HTTP_429 = "429"
    HTTP_503 = "503"
    HTTP_502 = "502"
    CUSTOM = "custom"


class ThrottlePriority(str, Enum):
    """Priority levels for throttled traffic."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    BEST_EFFORT = "best_effort"


class ThrottleScope(str, Enum):
    """Scope at which throttling is applied."""

    GLOBAL = "global"
    LOCAL = "local"
    PER_TENANT = "per_tenant"
    PER_ENDPOINT = "per_endpoint"


class WindowAlignment(str, Enum):
    """How throttle windows align across services."""

    ALIGNED = "aligned"
    STAGGERED = "staggered"
    INDEPENDENT = "independent"


class RetryStormSeverity(str, Enum):
    """Severity of a retry storm."""

    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class BypassRisk(str, Enum):
    """Risk level of a throttle bypass vulnerability."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AdaptiveStrategy(str, Enum):
    """Strategies for adaptive throttle threshold optimisation."""

    FIXED = "fixed"
    AIMD = "aimd"
    GRADIENT = "gradient"
    PID_CONTROLLER = "pid_controller"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


_PRIORITY_WEIGHTS: dict[ThrottlePriority, float] = {
    ThrottlePriority.CRITICAL: 1.0,
    ThrottlePriority.HIGH: 0.8,
    ThrottlePriority.MEDIUM: 0.5,
    ThrottlePriority.LOW: 0.2,
    ThrottlePriority.BEST_EFFORT: 0.05,
}

_RESPONSE_CODE_SEVERITY: dict[ThrottleResponseCode, float] = {
    ThrottleResponseCode.HTTP_429: 0.6,
    ThrottleResponseCode.HTTP_503: 0.9,
    ThrottleResponseCode.HTTP_502: 0.8,
    ThrottleResponseCode.CUSTOM: 0.5,
}


# ---------------------------------------------------------------------------
# Data-class result models
# ---------------------------------------------------------------------------


@dataclass
class ThrottleConfig:
    """Configuration for a throttle on a single component."""

    component_id: str = ""
    rate_limit_rps: float = 100.0
    burst_size: int = 50
    window_seconds: float = 1.0
    response_code: ThrottleResponseCode = ThrottleResponseCode.HTTP_429
    priority: ThrottlePriority = ThrottlePriority.MEDIUM
    scope: ThrottleScope = ThrottleScope.GLOBAL
    adaptive_strategy: AdaptiveStrategy = AdaptiveStrategy.FIXED
    tenant_count: int = 1


@dataclass
class PropagationHop:
    """A single hop in a throttle propagation chain."""

    component_id: str = ""
    incoming_rps: float = 0.0
    throttled_rps: float = 0.0
    passed_rps: float = 0.0
    throttle_ratio: float = 0.0
    depth: int = 0


@dataclass
class UpstreamPropagationResult:
    """Result of upstream throttle propagation analysis."""

    hops: list[PropagationHop] = field(default_factory=list)
    total_throttled_rps: float = 0.0
    max_throttle_ratio: float = 0.0
    propagation_depth: int = 0
    amplification_factor: float = 1.0
    recommendations: list[str] = field(default_factory=list)
    analyzed_at: str = ""


@dataclass
class DownstreamBackpressureResult:
    """Result of downstream backpressure cascade analysis."""

    hops: list[PropagationHop] = field(default_factory=list)
    total_backpressure_rps: float = 0.0
    cascade_depth: int = 0
    bottleneck_component: str = ""
    saturation_ratio: float = 0.0
    recommendations: list[str] = field(default_factory=list)
    analyzed_at: str = ""


@dataclass
class BudgetAllocation:
    """Throttle budget allocated to a single component."""

    component_id: str = ""
    allocated_rps: float = 0.0
    demand_rps: float = 0.0
    utilisation_ratio: float = 0.0
    headroom_rps: float = 0.0


@dataclass
class ThrottleBudgetResult:
    """Result of throttle budget distribution analysis."""

    allocations: list[BudgetAllocation] = field(default_factory=list)
    total_budget_rps: float = 0.0
    total_allocated_rps: float = 0.0
    efficiency_percent: float = 0.0
    over_budget_components: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    analyzed_at: str = ""


@dataclass
class PriorityFairnessEntry:
    """Fairness metrics for a single priority level."""

    priority: ThrottlePriority = ThrottlePriority.MEDIUM
    share_percent: float = 0.0
    actual_rps: float = 0.0
    throttled_rps: float = 0.0
    starvation_risk: float = 0.0


@dataclass
class PriorityFairnessResult:
    """Result of priority-based throttling fairness analysis."""

    entries: list[PriorityFairnessEntry] = field(default_factory=list)
    overall_fairness_score: float = 0.0
    starvation_detected: bool = False
    starved_priorities: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    analyzed_at: str = ""


@dataclass
class AdaptiveThreshold:
    """An optimised throttle threshold for a component."""

    component_id: str = ""
    original_rps: float = 0.0
    optimised_rps: float = 0.0
    strategy: AdaptiveStrategy = AdaptiveStrategy.FIXED
    improvement_percent: float = 0.0


@dataclass
class AdaptiveThresholdResult:
    """Result of adaptive throttle threshold optimisation."""

    thresholds: list[AdaptiveThreshold] = field(default_factory=list)
    avg_improvement_percent: float = 0.0
    recommended_strategy: AdaptiveStrategy = AdaptiveStrategy.FIXED
    recommendations: list[str] = field(default_factory=list)
    analyzed_at: str = ""


@dataclass
class RetryStormResult:
    """Result of throttle-induced retry storm detection."""

    severity: RetryStormSeverity = RetryStormSeverity.NONE
    estimated_retry_rps: float = 0.0
    amplification_factor: float = 1.0
    peak_retry_wave: int = 0
    storm_duration_seconds: float = 0.0
    affected_components: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    analyzed_at: str = ""


@dataclass
class TenantIsolationEntry:
    """Isolation metrics for a single tenant."""

    tenant_id: str = ""
    allocated_rps: float = 0.0
    actual_rps: float = 0.0
    throttle_ratio: float = 0.0
    noisy_neighbour_impact: float = 0.0


@dataclass
class TenantIsolationResult:
    """Result of per-tenant throttle isolation assessment."""

    entries: list[TenantIsolationEntry] = field(default_factory=list)
    isolation_score: float = 0.0
    noisy_neighbour_detected: bool = False
    worst_affected_tenant: str = ""
    recommendations: list[str] = field(default_factory=list)
    analyzed_at: str = ""


@dataclass
class ResponseCodeEntry:
    """Analysis of throttle response code handling at a component."""

    component_id: str = ""
    response_code: ThrottleResponseCode = ThrottleResponseCode.HTTP_429
    includes_retry_after: bool = False
    includes_rate_limit_headers: bool = False
    client_behaviour_score: float = 0.0


@dataclass
class ResponseCodeResult:
    """Result of throttle response code handling analysis."""

    entries: list[ResponseCodeEntry] = field(default_factory=list)
    consistency_score: float = 0.0
    retry_after_coverage: float = 0.0
    recommendations: list[str] = field(default_factory=list)
    analyzed_at: str = ""


@dataclass
class WindowAlignmentEntry:
    """Window alignment info for a component."""

    component_id: str = ""
    window_seconds: float = 1.0
    alignment: WindowAlignment = WindowAlignment.INDEPENDENT
    boundary_burst_risk: float = 0.0


@dataclass
class WindowAlignmentResult:
    """Result of throttle window alignment analysis."""

    entries: list[WindowAlignmentEntry] = field(default_factory=list)
    alignment_score: float = 0.0
    boundary_burst_risk: float = 0.0
    recommendations: list[str] = field(default_factory=list)
    analyzed_at: str = ""


@dataclass
class CoordinationEntry:
    """Coordination status for a component."""

    component_id: str = ""
    scope: ThrottleScope = ThrottleScope.GLOBAL
    effective_rps: float = 0.0
    replicas: int = 1
    per_replica_rps: float = 0.0
    split_brain_risk: float = 0.0


@dataclass
class CoordinationResult:
    """Result of global vs local rate limit coordination analysis."""

    entries: list[CoordinationEntry] = field(default_factory=list)
    coordination_score: float = 0.0
    split_brain_risk: float = 0.0
    mixed_scope_detected: bool = False
    recommendations: list[str] = field(default_factory=list)
    analyzed_at: str = ""


@dataclass
class BypassVulnerability:
    """A detected throttle bypass vulnerability."""

    component_id: str = ""
    vulnerability: str = ""
    risk: BypassRisk = BypassRisk.NONE
    mitigation: str = ""


@dataclass
class BypassDetectionResult:
    """Result of throttle bypass vulnerability detection."""

    vulnerabilities: list[BypassVulnerability] = field(default_factory=list)
    total_vulnerabilities: int = 0
    critical_count: int = 0
    high_count: int = 0
    overall_risk: BypassRisk = BypassRisk.NONE
    recommendations: list[str] = field(default_factory=list)
    analyzed_at: str = ""


@dataclass
class CapacityPlanEntry:
    """Capacity planning data for a component under load spike."""

    component_id: str = ""
    current_limit_rps: float = 0.0
    required_limit_rps: float = 0.0
    headroom_percent: float = 0.0
    scale_factor: float = 1.0
    needs_scaling: bool = False


@dataclass
class CapacityPlanResult:
    """Result of throttle capacity planning under load spikes."""

    entries: list[CapacityPlanEntry] = field(default_factory=list)
    spike_multiplier: float = 1.0
    components_needing_scale: int = 0
    total_additional_rps: float = 0.0
    recommendations: list[str] = field(default_factory=list)
    analyzed_at: str = ""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ThrottleCascadeAnalyzer:
    """Stateless engine for throttle cascade analysis."""

    # -- upstream propagation -------------------------------------------------

    def analyze_upstream_propagation(
        self,
        graph: InfraGraph,
        origin_id: str,
        configs: dict[str, ThrottleConfig],
        incoming_rps: float,
    ) -> UpstreamPropagationResult:
        """Model how throttling at *origin_id* propagates upstream."""
        now = datetime.now(timezone.utc).isoformat()
        hops: list[PropagationHop] = []
        visited: set[str] = set()
        queue: list[tuple[str, float, int]] = [(origin_id, incoming_rps, 0)]
        total_throttled = 0.0
        max_ratio = 0.0
        max_depth = 0

        while queue:
            next_level: list[tuple[str, float, int]] = []
            for cid, rps, depth in queue:
                if cid in visited:
                    continue
                visited.add(cid)

                cfg = configs.get(cid)
                if cfg is not None:
                    capacity = cfg.rate_limit_rps + cfg.burst_size / max(cfg.window_seconds, 0.01)
                    throttled = max(0.0, rps - capacity)
                    passed = rps - throttled
                    ratio = throttled / max(rps, 0.01)
                else:
                    throttled = 0.0
                    passed = rps
                    ratio = 0.0

                total_throttled += throttled
                max_ratio = max(max_ratio, ratio)
                if depth > max_depth:
                    max_depth = depth

                hops.append(PropagationHop(
                    component_id=cid,
                    incoming_rps=round(rps, 2),
                    throttled_rps=round(throttled, 2),
                    passed_rps=round(passed, 2),
                    throttle_ratio=round(_clamp(ratio, 0.0, 1.0), 4),
                    depth=depth,
                ))

                dependents = graph.get_dependents(cid)
                for dep in dependents:
                    if dep.id not in visited:
                        back_rps = throttled * 0.7
                        next_level.append((dep.id, back_rps, depth + 1))

            queue = next_level

        amp = (incoming_rps + total_throttled) / max(incoming_rps, 0.01)
        recs: list[str] = []
        if max_ratio > 0.5:
            recs.append(
                "Over 50% of traffic is throttled at one or more hops; "
                "increase rate limits or add capacity"
            )
        if max_depth > 3:
            recs.append(
                "Throttle propagation reaches depth > 3; add per-service "
                "rate limits to contain upstream impact"
            )
        if total_throttled > incoming_rps * 0.3:
            recs.append(
                "Significant upstream throttle amplification detected; "
                "consider implementing backpressure signals"
            )

        return UpstreamPropagationResult(
            hops=hops,
            total_throttled_rps=round(total_throttled, 2),
            max_throttle_ratio=round(_clamp(max_ratio, 0.0, 1.0), 4),
            propagation_depth=max_depth,
            amplification_factor=round(amp, 3),
            recommendations=recs,
            analyzed_at=now,
        )

    # -- downstream backpressure cascade --------------------------------------

    def analyze_downstream_backpressure(
        self,
        graph: InfraGraph,
        origin_id: str,
        configs: dict[str, ThrottleConfig],
        incoming_rps: float,
    ) -> DownstreamBackpressureResult:
        """Analyze downstream backpressure cascade from *origin_id*."""
        now = datetime.now(timezone.utc).isoformat()
        hops: list[PropagationHop] = []
        visited: set[str] = set()
        queue: list[tuple[str, float, int]] = [(origin_id, incoming_rps, 0)]
        total_bp = 0.0
        max_depth = 0
        bottleneck = ""
        max_sat = 0.0

        while queue:
            next_level: list[tuple[str, float, int]] = []
            for cid, rps, depth in queue:
                if cid in visited:
                    continue
                visited.add(cid)

                comp = graph.get_component(cid)
                cfg = configs.get(cid)
                if cfg is not None:
                    cap = cfg.rate_limit_rps
                else:
                    cap = float(comp.capacity.max_rps) * comp.replicas if comp else 5000.0

                throttled = max(0.0, rps - cap)
                passed = rps - throttled
                ratio = throttled / max(rps, 0.01)
                total_bp += throttled

                sat = rps / max(cap, 0.01)
                if sat > max_sat:
                    max_sat = sat
                    bottleneck = cid
                if depth > max_depth:
                    max_depth = depth

                hops.append(PropagationHop(
                    component_id=cid,
                    incoming_rps=round(rps, 2),
                    throttled_rps=round(throttled, 2),
                    passed_rps=round(passed, 2),
                    throttle_ratio=round(_clamp(ratio, 0.0, 1.0), 4),
                    depth=depth,
                ))

                deps = graph.get_dependencies(cid)
                for dep in deps:
                    if dep.id not in visited:
                        next_level.append((dep.id, passed, depth + 1))

            queue = next_level

        recs: list[str] = []
        if max_sat > 1.0:
            recs.append(
                f"Component '{bottleneck}' is saturated ({max_sat:.1%}); "
                "scale horizontally or increase rate limit"
            )
        if max_depth > 4:
            recs.append(
                "Deep backpressure cascade detected; add circuit breakers "
                "to limit propagation depth"
            )
        if total_bp > incoming_rps * 0.5:
            recs.append(
                "More than half of incoming traffic is throttled across the "
                "cascade; review overall capacity"
            )
        if not hops:
            recs.append("No components in the cascade path")

        return DownstreamBackpressureResult(
            hops=hops,
            total_backpressure_rps=round(total_bp, 2),
            cascade_depth=max_depth,
            bottleneck_component=bottleneck,
            saturation_ratio=round(_clamp(max_sat, 0.0, 5.0), 4),
            recommendations=recs,
            analyzed_at=now,
        )

    # -- throttle budget distribution -----------------------------------------

    def distribute_throttle_budget(
        self,
        graph: InfraGraph,
        component_ids: list[str],
        total_budget_rps: float,
        demand_map: dict[str, float] | None = None,
    ) -> ThrottleBudgetResult:
        """Distribute throttle budget across a service chain."""
        now = datetime.now(timezone.utc).isoformat()
        if not component_ids:
            return ThrottleBudgetResult(
                total_budget_rps=total_budget_rps,
                recommendations=["No components provided for budget distribution"],
                analyzed_at=now,
            )

        if demand_map is None:
            demand_map = {}

        total_demand = 0.0
        demands: dict[str, float] = {}
        for cid in component_ids:
            d = demand_map.get(cid, 0.0)
            if d <= 0.0:
                comp = graph.get_component(cid)
                d = float(comp.capacity.max_rps) * 0.7 if comp else 100.0
            demands[cid] = d
            total_demand += d

        allocations: list[BudgetAllocation] = []
        total_allocated = 0.0
        over_budget: list[str] = []

        for cid in component_ids:
            demand = demands[cid]
            if total_demand > 0:
                share = demand / total_demand
            else:
                share = 1.0 / max(len(component_ids), 1)
            allocated = total_budget_rps * share
            util = allocated / max(demand, 0.01)
            headroom = max(0.0, allocated - demand)

            if allocated < demand:
                over_budget.append(cid)

            allocations.append(BudgetAllocation(
                component_id=cid,
                allocated_rps=round(allocated, 2),
                demand_rps=round(demand, 2),
                utilisation_ratio=round(_clamp(util, 0.0, 5.0), 4),
                headroom_rps=round(headroom, 2),
            ))
            total_allocated += allocated

        efficiency = (total_allocated / max(total_budget_rps, 0.01)) * 100.0

        recs: list[str] = []
        if over_budget:
            recs.append(
                f"Components [{', '.join(over_budget)}] exceed their allocated "
                "budget; redistribute or increase total budget"
            )
        if efficiency > 95.0:
            recs.append(
                "Budget utilisation is near 100%; maintain headroom for bursts"
            )
        if total_demand > total_budget_rps:
            recs.append(
                "Total demand exceeds budget; some services will be "
                "throttled under normal load"
            )

        return ThrottleBudgetResult(
            allocations=allocations,
            total_budget_rps=round(total_budget_rps, 2),
            total_allocated_rps=round(total_allocated, 2),
            efficiency_percent=round(_clamp(efficiency), 2),
            over_budget_components=over_budget,
            recommendations=recs,
            analyzed_at=now,
        )

    # -- priority-based fairness analysis -------------------------------------

    def analyze_priority_fairness(
        self,
        graph: InfraGraph,
        component_id: str,
        total_rps: float,
        priority_distribution: dict[ThrottlePriority, float] | None = None,
        config: ThrottleConfig | None = None,
    ) -> PriorityFairnessResult:
        """Analyze fairness of priority-based throttling."""
        now = datetime.now(timezone.utc).isoformat()
        if priority_distribution is None:
            priority_distribution = {
                ThrottlePriority.CRITICAL: 0.1,
                ThrottlePriority.HIGH: 0.2,
                ThrottlePriority.MEDIUM: 0.4,
                ThrottlePriority.LOW: 0.2,
                ThrottlePriority.BEST_EFFORT: 0.1,
            }

        rate_limit = 100.0
        if config is not None:
            rate_limit = config.rate_limit_rps
        else:
            comp = graph.get_component(component_id)
            if comp is not None:
                rate_limit = float(comp.capacity.max_rps)

        entries: list[PriorityFairnessEntry] = []
        remaining_capacity = rate_limit
        starvation_found = False
        starved: list[str] = []

        sorted_priorities = sorted(
            priority_distribution.items(),
            key=lambda kv: _PRIORITY_WEIGHTS.get(kv[0], 0.5),
            reverse=True,
        )

        for prio, share in sorted_priorities:
            demand = total_rps * share
            weight = _PRIORITY_WEIGHTS.get(prio, 0.5)
            allocated = min(demand, remaining_capacity * weight)
            if remaining_capacity <= 0:
                allocated = 0.0
            else:
                allocated = min(demand, remaining_capacity)
            throttled = max(0.0, demand - allocated)
            remaining_capacity = max(0.0, remaining_capacity - allocated)

            starve_risk = throttled / max(demand, 0.01)
            if starve_risk > 0.8:
                starvation_found = True
                starved.append(prio.value)

            entries.append(PriorityFairnessEntry(
                priority=prio,
                share_percent=round(share * 100, 2),
                actual_rps=round(allocated, 2),
                throttled_rps=round(throttled, 2),
                starvation_risk=round(_clamp(starve_risk, 0.0, 1.0), 4),
            ))

        total_throttled = sum(e.throttled_rps for e in entries)
        sum(e.actual_rps for e in entries)
        fairness = 100.0 - (total_throttled / max(total_rps, 0.01)) * 100.0
        if starvation_found:
            fairness *= 0.7

        recs: list[str] = []
        if starvation_found:
            recs.append(
                f"Starvation detected for priorities: {starved}; "
                "allocate minimum guaranteed capacity per priority"
            )
        if total_throttled > total_rps * 0.3:
            recs.append(
                "More than 30% of total traffic is throttled; increase "
                "capacity or shed only best-effort traffic"
            )
        if len(entries) < 2:
            recs.append(
                "Only one priority level in use; add priority tiers for "
                "better fairness control"
            )

        return PriorityFairnessResult(
            entries=entries,
            overall_fairness_score=round(_clamp(fairness), 2),
            starvation_detected=starvation_found,
            starved_priorities=starved,
            recommendations=recs,
            analyzed_at=now,
        )

    # -- adaptive threshold optimisation --------------------------------------

    def optimize_adaptive_thresholds(
        self,
        graph: InfraGraph,
        configs: dict[str, ThrottleConfig],
        load_rps: float,
    ) -> AdaptiveThresholdResult:
        """Optimize throttle thresholds using adaptive strategies."""
        now = datetime.now(timezone.utc).isoformat()
        thresholds: list[AdaptiveThreshold] = []
        improvements: list[float] = []
        best_strategy = AdaptiveStrategy.FIXED
        best_avg_improvement = 0.0

        for strategy in AdaptiveStrategy:
            strategy_improvements: list[float] = []
            for cid, cfg in configs.items():
                original = cfg.rate_limit_rps
                comp = graph.get_component(cid)
                max_rps = float(comp.capacity.max_rps) * comp.replicas if comp else original * 2
                utilisation = load_rps / max(max_rps, 0.01)

                if strategy == AdaptiveStrategy.FIXED:
                    optimised = original
                elif strategy == AdaptiveStrategy.AIMD:
                    if utilisation < 0.7:
                        optimised = original * 1.1
                    else:
                        optimised = original * 0.5
                elif strategy == AdaptiveStrategy.GRADIENT:
                    gradient = (load_rps - original) / max(original, 0.01)
                    optimised = original * (1.0 + gradient * 0.1)
                elif strategy == AdaptiveStrategy.PID_CONTROLLER:
                    error = load_rps - original
                    kp, ki, kd = 0.1, 0.01, 0.05
                    adjustment = kp * error + ki * error * 0.5 + kd * error * 0.2
                    optimised = original + adjustment
                else:
                    optimised = original

                optimised = _clamp(optimised, 1.0, max_rps)
                improvement = ((optimised - original) / max(original, 0.01)) * 100.0
                strategy_improvements.append(abs(improvement))

            avg_imp = sum(strategy_improvements) / max(len(strategy_improvements), 1)
            if avg_imp > best_avg_improvement and strategy != AdaptiveStrategy.FIXED:
                best_avg_improvement = avg_imp
                best_strategy = strategy

        for cid, cfg in configs.items():
            original = cfg.rate_limit_rps
            comp = graph.get_component(cid)
            max_rps = float(comp.capacity.max_rps) * comp.replicas if comp else original * 2
            utilisation = load_rps / max(max_rps, 0.01)

            if best_strategy == AdaptiveStrategy.AIMD:
                if utilisation < 0.7:
                    optimised = original * 1.1
                else:
                    optimised = original * 0.5
            elif best_strategy == AdaptiveStrategy.GRADIENT:
                gradient = (load_rps - original) / max(original, 0.01)
                optimised = original * (1.0 + gradient * 0.1)
            elif best_strategy == AdaptiveStrategy.PID_CONTROLLER:
                error = load_rps - original
                kp, ki, kd = 0.1, 0.01, 0.05
                adjustment = kp * error + ki * error * 0.5 + kd * error * 0.2
                optimised = original + adjustment
            else:
                optimised = original

            optimised = _clamp(optimised, 1.0, max_rps)
            improvement = ((optimised - original) / max(original, 0.01)) * 100.0
            improvements.append(improvement)

            thresholds.append(AdaptiveThreshold(
                component_id=cid,
                original_rps=round(original, 2),
                optimised_rps=round(optimised, 2),
                strategy=best_strategy,
                improvement_percent=round(improvement, 2),
            ))

        avg_improvement = sum(improvements) / max(len(improvements), 1)

        recs: list[str] = []
        if best_strategy != AdaptiveStrategy.FIXED:
            recs.append(
                f"Recommend switching to '{best_strategy.value}' strategy "
                f"for ~{abs(avg_improvement):.1f}% improvement"
            )
        if any(t.improvement_percent < -20 for t in thresholds):
            recs.append(
                "Some components require aggressive threshold reduction; "
                "implement gradually to avoid sudden drops"
            )
        if not configs:
            recs.append("No throttle configs provided for optimisation")

        return AdaptiveThresholdResult(
            thresholds=thresholds,
            avg_improvement_percent=round(avg_improvement, 2),
            recommended_strategy=best_strategy,
            recommendations=recs,
            analyzed_at=now,
        )

    # -- retry storm detection ------------------------------------------------

    def detect_retry_storm(
        self,
        graph: InfraGraph,
        configs: dict[str, ThrottleConfig],
        incoming_rps: float,
        max_retries: int = 3,
        retry_delay_ms: float = 100.0,
    ) -> RetryStormResult:
        """Detect throttle-induced retry storms across the graph."""
        now = datetime.now(timezone.utc).isoformat()
        affected: list[str] = []
        total_retry_rps = 0.0
        peak_wave = 0

        for cid, cfg in configs.items():
            cap = cfg.rate_limit_rps + cfg.burst_size / max(cfg.window_seconds, 0.01)
            rejected = max(0.0, incoming_rps - cap)
            if rejected <= 0.0:
                continue

            affected.append(cid)
            wave_rps = rejected
            cumulative_retries = 0.0
            for attempt in range(max_retries):
                retry_rps = wave_rps * 0.7
                cumulative_retries += retry_rps
                success_fraction = cap / max(cap + retry_rps, 0.01)
                wave_rps = retry_rps * (1.0 - success_fraction)
                if wave_rps < 1.0:
                    break
                if attempt + 1 > peak_wave:
                    peak_wave = attempt + 1

            total_retry_rps += cumulative_retries

        amp = (incoming_rps + total_retry_rps) / max(incoming_rps, 0.01)

        if amp < 1.1:
            severity = RetryStormSeverity.NONE
        elif amp < 1.3:
            severity = RetryStormSeverity.LOW
        elif amp < 1.6:
            severity = RetryStormSeverity.MODERATE
        elif amp < 2.0:
            severity = RetryStormSeverity.HIGH
        else:
            severity = RetryStormSeverity.CRITICAL

        storm_duration = peak_wave * retry_delay_ms / 1000.0

        recs: list[str] = []
        if severity in (RetryStormSeverity.HIGH, RetryStormSeverity.CRITICAL):
            recs.append(
                "Critical retry storm risk; implement exponential backoff "
                "with jitter and retry budgets"
            )
        if severity == RetryStormSeverity.MODERATE:
            recs.append(
                "Moderate retry storm risk; add Retry-After headers and "
                "client-side backoff"
            )
        if amp > 1.5:
            recs.append(
                f"Retry amplification factor of {amp:.2f}x will overwhelm "
                "services during throttle events"
            )
        if peak_wave >= max_retries:
            recs.append(
                "All retry attempts exhausted; reduce max_retries or "
                "increase rate limits"
            )
        if not configs:
            recs.append("No throttle configs provided")

        return RetryStormResult(
            severity=severity,
            estimated_retry_rps=round(total_retry_rps, 2),
            amplification_factor=round(amp, 3),
            peak_retry_wave=peak_wave,
            storm_duration_seconds=round(storm_duration, 3),
            affected_components=affected,
            recommendations=recs,
            analyzed_at=now,
        )

    # -- per-tenant isolation -------------------------------------------------

    def assess_tenant_isolation(
        self,
        graph: InfraGraph,
        component_id: str,
        config: ThrottleConfig,
        tenant_rps: dict[str, float],
    ) -> TenantIsolationResult:
        """Assess per-tenant throttle isolation for a component."""
        now = datetime.now(timezone.utc).isoformat()
        if not tenant_rps:
            return TenantIsolationResult(
                isolation_score=100.0,
                recommendations=["No tenants provided"],
                analyzed_at=now,
            )

        per_tenant_limit = config.rate_limit_rps / max(config.tenant_count, len(tenant_rps))
        entries: list[TenantIsolationEntry] = []
        noisy_detected = False
        worst_tenant = ""
        worst_impact = 0.0

        total_demand = sum(tenant_rps.values())
        config.rate_limit_rps / max(len(tenant_rps), 1)

        for tid, rps in tenant_rps.items():
            throttled = max(0.0, rps - per_tenant_limit)
            ratio = throttled / max(rps, 0.01)

            other_demand = total_demand - rps
            over_share = max(0.0, other_demand - config.rate_limit_rps + per_tenant_limit)
            noisy_impact = over_share / max(config.rate_limit_rps, 0.01)

            if rps > per_tenant_limit * 2:
                noisy_detected = True

            if noisy_impact > worst_impact:
                worst_impact = noisy_impact
                worst_tenant = tid

            entries.append(TenantIsolationEntry(
                tenant_id=tid,
                allocated_rps=round(per_tenant_limit, 2),
                actual_rps=round(rps, 2),
                throttle_ratio=round(_clamp(ratio, 0.0, 1.0), 4),
                noisy_neighbour_impact=round(_clamp(noisy_impact, 0.0, 1.0), 4),
            ))

        if config.scope == ThrottleScope.PER_TENANT:
            isolation_score = 90.0
        elif config.scope == ThrottleScope.GLOBAL:
            isolation_score = 40.0
        else:
            isolation_score = 65.0

        if noisy_detected:
            isolation_score *= 0.6

        recs: list[str] = []
        if config.scope != ThrottleScope.PER_TENANT:
            recs.append(
                "Throttle scope is not per-tenant; switch to per-tenant "
                "scoping for better isolation"
            )
        if noisy_detected:
            recs.append(
                "Noisy neighbour detected; enforce per-tenant rate limits "
                "to prevent cross-tenant impact"
            )
        if worst_impact > 0.3:
            recs.append(
                f"Tenant '{worst_tenant}' is causing significant impact "
                "on other tenants"
            )

        return TenantIsolationResult(
            entries=entries,
            isolation_score=round(_clamp(isolation_score), 2),
            noisy_neighbour_detected=noisy_detected,
            worst_affected_tenant=worst_tenant,
            recommendations=recs,
            analyzed_at=now,
        )

    # -- response code handling analysis --------------------------------------

    def analyze_response_codes(
        self,
        graph: InfraGraph,
        configs: dict[str, ThrottleConfig],
    ) -> ResponseCodeResult:
        """Analyze throttle response code handling across services."""
        now = datetime.now(timezone.utc).isoformat()
        if not configs:
            return ResponseCodeResult(
                consistency_score=0.0,
                recommendations=["No throttle configs provided"],
                analyzed_at=now,
            )

        entries: list[ResponseCodeEntry] = []
        codes_used: set[ThrottleResponseCode] = set()
        retry_after_count = 0

        for cid, cfg in configs.items():
            codes_used.add(cfg.response_code)
            has_retry_after = cfg.response_code == ThrottleResponseCode.HTTP_429
            has_rl_headers = cfg.response_code in (
                ThrottleResponseCode.HTTP_429, ThrottleResponseCode.CUSTOM
            )
            if has_retry_after:
                retry_after_count += 1

            severity = _RESPONSE_CODE_SEVERITY.get(cfg.response_code, 0.5)
            client_score = (1.0 - severity) * 100.0
            if has_retry_after:
                client_score += 20.0
            if has_rl_headers:
                client_score += 10.0
            client_score = _clamp(client_score)

            entries.append(ResponseCodeEntry(
                component_id=cid,
                response_code=cfg.response_code,
                includes_retry_after=has_retry_after,
                includes_rate_limit_headers=has_rl_headers,
                client_behaviour_score=round(client_score, 2),
            ))

        consistency = 100.0 if len(codes_used) == 1 else max(0.0, 100.0 - (len(codes_used) - 1) * 30.0)
        retry_coverage = (retry_after_count / max(len(configs), 1)) * 100.0

        recs: list[str] = []
        if len(codes_used) > 1:
            recs.append(
                "Multiple throttle response codes in use; standardise on "
                "429 for consistent client behaviour"
            )
        if ThrottleResponseCode.HTTP_503 in codes_used:
            recs.append(
                "503 is used for throttling; clients may interpret this as "
                "a server error rather than rate limiting"
            )
        if retry_coverage < 100.0:
            recs.append(
                "Not all services include Retry-After headers; add them "
                "to help clients back off appropriately"
            )
        if ThrottleResponseCode.HTTP_502 in codes_used:
            recs.append(
                "502 responses for throttling will confuse monitoring; "
                "use 429 instead"
            )

        return ResponseCodeResult(
            entries=entries,
            consistency_score=round(_clamp(consistency), 2),
            retry_after_coverage=round(_clamp(retry_coverage), 2),
            recommendations=recs,
            analyzed_at=now,
        )

    # -- window alignment analysis --------------------------------------------

    def analyze_window_alignment(
        self,
        graph: InfraGraph,
        configs: dict[str, ThrottleConfig],
    ) -> WindowAlignmentResult:
        """Analyze throttle window alignment across services."""
        now = datetime.now(timezone.utc).isoformat()
        if not configs:
            return WindowAlignmentResult(
                alignment_score=0.0,
                recommendations=["No throttle configs provided"],
                analyzed_at=now,
            )

        entries: list[WindowAlignmentEntry] = []
        windows: list[float] = []
        total_burst_risk = 0.0

        for cid, cfg in configs.items():
            windows.append(cfg.window_seconds)

        unique_windows = set(windows)
        if len(unique_windows) == 1:
            global_alignment = WindowAlignment.ALIGNED
        elif len(unique_windows) <= 2:
            global_alignment = WindowAlignment.STAGGERED
        else:
            global_alignment = WindowAlignment.INDEPENDENT

        for cid, cfg in configs.items():
            burst_risk = 0.0
            others = [w for c, w in ((c, configs[c].window_seconds) for c in configs) if c != cid]
            if others:
                for ow in others:
                    if abs(cfg.window_seconds - ow) < 0.01:
                        burst_risk += 0.3
                    elif cfg.window_seconds > 0 and ow > 0:
                        ratio = max(cfg.window_seconds, ow) / min(cfg.window_seconds, ow)
                        if ratio == int(ratio):
                            burst_risk += 0.2

            burst_risk = _clamp(burst_risk, 0.0, 1.0)
            total_burst_risk += burst_risk

            entries.append(WindowAlignmentEntry(
                component_id=cid,
                window_seconds=cfg.window_seconds,
                alignment=global_alignment,
                boundary_burst_risk=round(burst_risk, 4),
            ))

        avg_burst_risk = total_burst_risk / max(len(configs), 1)
        if global_alignment == WindowAlignment.ALIGNED:
            alignment_score = 90.0
        elif global_alignment == WindowAlignment.STAGGERED:
            alignment_score = 60.0
        else:
            alignment_score = 30.0

        alignment_score -= avg_burst_risk * 20.0
        alignment_score = _clamp(alignment_score)

        recs: list[str] = []
        if global_alignment == WindowAlignment.INDEPENDENT:
            recs.append(
                "Throttle windows are unaligned; synchronise window sizes "
                "to reduce boundary-burst effects"
            )
        if avg_burst_risk > 0.5:
            recs.append(
                "High boundary-burst risk; stagger window start times or "
                "use sliding window algorithms"
            )
        if len(unique_windows) > 3:
            recs.append(
                "Too many distinct window sizes; standardise on 1-2 window "
                "durations across services"
            )

        return WindowAlignmentResult(
            entries=entries,
            alignment_score=round(_clamp(alignment_score), 2),
            boundary_burst_risk=round(_clamp(avg_burst_risk, 0.0, 1.0), 4),
            recommendations=recs,
            analyzed_at=now,
        )

    # -- global vs local coordination -----------------------------------------

    def analyze_coordination(
        self,
        graph: InfraGraph,
        configs: dict[str, ThrottleConfig],
    ) -> CoordinationResult:
        """Analyze global vs local rate limit coordination."""
        now = datetime.now(timezone.utc).isoformat()
        if not configs:
            return CoordinationResult(
                coordination_score=0.0,
                recommendations=["No throttle configs provided"],
                analyzed_at=now,
            )

        entries: list[CoordinationEntry] = []
        scopes_used: set[ThrottleScope] = set()
        total_split_risk = 0.0

        for cid, cfg in configs.items():
            scopes_used.add(cfg.scope)
            comp = graph.get_component(cid)
            replicas = comp.replicas if comp else 1
            effective = cfg.rate_limit_rps
            per_replica = effective / max(replicas, 1)

            if cfg.scope == ThrottleScope.LOCAL and replicas > 1:
                split_risk = min(1.0, (replicas - 1) * 0.2)
            elif cfg.scope == ThrottleScope.GLOBAL:
                split_risk = 0.0
            else:
                split_risk = 0.1

            total_split_risk += split_risk

            entries.append(CoordinationEntry(
                component_id=cid,
                scope=cfg.scope,
                effective_rps=round(effective, 2),
                replicas=replicas,
                per_replica_rps=round(per_replica, 2),
                split_brain_risk=round(_clamp(split_risk, 0.0, 1.0), 4),
            ))

        mixed = len(scopes_used) > 1
        avg_split = total_split_risk / max(len(configs), 1)

        coordination = 100.0
        if mixed:
            coordination -= 25.0
        coordination -= avg_split * 40.0
        coordination = _clamp(coordination)

        recs: list[str] = []
        if mixed:
            recs.append(
                "Mixed throttle scopes detected; standardise on global "
                "scope with centralised store for consistency"
            )
        if avg_split > 0.3:
            recs.append(
                "High split-brain risk for local rate limits; use a "
                "distributed counter (Redis, memcached) for coordination"
            )
        local_only = [
            e for e in entries
            if e.scope == ThrottleScope.LOCAL and e.replicas > 1
        ]
        if local_only:
            ids = ", ".join(e.component_id for e in local_only)
            recs.append(
                f"Components [{ids}] use local scope with multiple replicas; "
                "effective limit is multiplied by replica count"
            )

        return CoordinationResult(
            entries=entries,
            coordination_score=round(coordination, 2),
            split_brain_risk=round(_clamp(avg_split, 0.0, 1.0), 4),
            mixed_scope_detected=mixed,
            recommendations=recs,
            analyzed_at=now,
        )

    # -- bypass vulnerability detection ---------------------------------------

    def detect_bypass_vulnerabilities(
        self,
        graph: InfraGraph,
        configs: dict[str, ThrottleConfig],
    ) -> BypassDetectionResult:
        """Detect throttle bypass vulnerabilities in the graph."""
        now = datetime.now(timezone.utc).isoformat()
        vulns: list[BypassVulnerability] = []

        all_ids = set(graph.components.keys())
        configured_ids = set(configs.keys())

        unprotected = all_ids - configured_ids
        for cid in sorted(unprotected):
            comp = graph.get_component(cid)
            if comp is None:
                continue
            deps = graph.get_dependents(cid)
            has_protected_upstream = any(d.id in configured_ids for d in deps)
            if has_protected_upstream:
                vulns.append(BypassVulnerability(
                    component_id=cid,
                    vulnerability="Unprotected component behind throttled upstream; "
                                  "direct access bypasses throttle",
                    risk=BypassRisk.HIGH,
                    mitigation="Add rate limiting to this component or restrict "
                               "direct access",
                ))

        for cid, cfg in configs.items():
            if cfg.scope == ThrottleScope.GLOBAL:
                comp = graph.get_component(cid)
                if comp and comp.replicas > 1:
                    vulns.append(BypassVulnerability(
                        component_id=cid,
                        vulnerability="Global scope with local counters; each "
                                      "replica enforces independently",
                        risk=BypassRisk.MEDIUM,
                        mitigation="Use centralised rate-limit store",
                    ))

            if cfg.response_code == ThrottleResponseCode.CUSTOM:
                vulns.append(BypassVulnerability(
                    component_id=cid,
                    vulnerability="Custom response code may not be handled by "
                                  "all clients",
                    risk=BypassRisk.LOW,
                    mitigation="Standardise on HTTP 429 response code",
                ))

            if cfg.burst_size > cfg.rate_limit_rps * 5:
                vulns.append(BypassVulnerability(
                    component_id=cid,
                    vulnerability="Burst size much larger than rate limit; "
                                  "allows sustained bursts beyond intended limit",
                    risk=BypassRisk.MEDIUM,
                    mitigation="Reduce burst_size to 2-3x rate_limit_rps",
                ))

        critical_count = sum(1 for v in vulns if v.risk == BypassRisk.CRITICAL)
        high_count = sum(1 for v in vulns if v.risk == BypassRisk.HIGH)

        if critical_count > 0:
            overall = BypassRisk.CRITICAL
        elif high_count > 0:
            overall = BypassRisk.HIGH
        elif vulns:
            overall = BypassRisk.MEDIUM
        else:
            overall = BypassRisk.NONE

        recs: list[str] = []
        if unprotected:
            recs.append(
                f"{len(unprotected)} components lack throttle configuration; "
                "add rate limits to prevent bypass"
            )
        if high_count > 0:
            recs.append(
                f"{high_count} high-risk bypass vulnerabilities detected; "
                "address immediately"
            )
        if not vulns:
            recs.append("No bypass vulnerabilities detected")

        return BypassDetectionResult(
            vulnerabilities=vulns,
            total_vulnerabilities=len(vulns),
            critical_count=critical_count,
            high_count=high_count,
            overall_risk=overall,
            recommendations=recs,
            analyzed_at=now,
        )

    # -- capacity planning under load spikes ----------------------------------

    def plan_capacity_for_spikes(
        self,
        graph: InfraGraph,
        configs: dict[str, ThrottleConfig],
        baseline_rps: float,
        spike_multiplier: float = 3.0,
        headroom_target: float = 20.0,
    ) -> CapacityPlanResult:
        """Plan throttle capacity for load spikes."""
        now = datetime.now(timezone.utc).isoformat()
        spike_rps = baseline_rps * spike_multiplier
        entries: list[CapacityPlanEntry] = []
        needs_scale_count = 0
        total_additional = 0.0

        for cid, cfg in configs.items():
            current = cfg.rate_limit_rps
            required = spike_rps * (1.0 + headroom_target / 100.0)
            headroom = ((current - spike_rps) / max(spike_rps, 0.01)) * 100.0
            scale = required / max(current, 0.01)
            needs = current < required

            if needs:
                needs_scale_count += 1
                total_additional += required - current

            entries.append(CapacityPlanEntry(
                component_id=cid,
                current_limit_rps=round(current, 2),
                required_limit_rps=round(required, 2),
                headroom_percent=round(headroom, 2),
                scale_factor=round(scale, 3),
                needs_scaling=needs,
            ))

        recs: list[str] = []
        if needs_scale_count > 0:
            recs.append(
                f"{needs_scale_count} components need scaling to handle "
                f"{spike_multiplier}x load spike"
            )
        if total_additional > 0:
            recs.append(
                f"Total additional capacity needed: {total_additional:.0f} RPS"
            )
        if spike_multiplier > 5.0:
            recs.append(
                "Spike multiplier > 5x; consider auto-scaling or load "
                "shedding instead of static provisioning"
            )
        if not configs:
            recs.append("No throttle configs provided for capacity planning")
        all_ok = all(not e.needs_scaling for e in entries)
        if all_ok and entries:
            recs.append(
                "All components can handle the load spike with current limits"
            )

        return CapacityPlanResult(
            entries=entries,
            spike_multiplier=round(spike_multiplier, 2),
            components_needing_scale=needs_scale_count,
            total_additional_rps=round(total_additional, 2),
            recommendations=recs,
            analyzed_at=now,
        )

    # -- comprehensive cascade analysis (convenience) -------------------------

    def run_full_analysis(
        self,
        graph: InfraGraph,
        configs: dict[str, ThrottleConfig],
        incoming_rps: float,
        origin_id: str | None = None,
    ) -> dict:
        """Run all analyses and return a combined report dict."""
        now = datetime.now(timezone.utc).isoformat()
        if origin_id is None:
            origin_id = next(iter(configs), "")

        component_ids = list(configs.keys())

        upstream = self.analyze_upstream_propagation(
            graph, origin_id, configs, incoming_rps
        )
        downstream = self.analyze_downstream_backpressure(
            graph, origin_id, configs, incoming_rps
        )
        budget = self.distribute_throttle_budget(
            graph, component_ids, incoming_rps
        )
        retry_storm = self.detect_retry_storm(
            graph, configs, incoming_rps
        )
        response_codes = self.analyze_response_codes(graph, configs)
        window_align = self.analyze_window_alignment(graph, configs)
        coordination = self.analyze_coordination(graph, configs)
        bypass = self.detect_bypass_vulnerabilities(graph, configs)
        capacity = self.plan_capacity_for_spikes(
            graph, configs, incoming_rps
        )

        all_recs: list[str] = []
        for r in (upstream.recommendations + downstream.recommendations
                  + budget.recommendations + retry_storm.recommendations
                  + response_codes.recommendations + window_align.recommendations
                  + coordination.recommendations + bypass.recommendations
                  + capacity.recommendations):
            if r not in all_recs:
                all_recs.append(r)

        overall_score = 100.0
        if upstream.max_throttle_ratio > 0.5:
            overall_score -= 15
        if downstream.saturation_ratio > 1.0:
            overall_score -= 20
        if retry_storm.severity in (RetryStormSeverity.HIGH, RetryStormSeverity.CRITICAL):
            overall_score -= 20
        if response_codes.consistency_score < 70:
            overall_score -= 10
        if coordination.split_brain_risk > 0.3:
            overall_score -= 10
        if bypass.overall_risk in (BypassRisk.HIGH, BypassRisk.CRITICAL):
            overall_score -= 15
        if capacity.components_needing_scale > 0:
            overall_score -= 10

        overall_score = _clamp(overall_score)

        return {
            "overall_score": round(overall_score, 2),
            "upstream_propagation": upstream,
            "downstream_backpressure": downstream,
            "throttle_budget": budget,
            "retry_storm": retry_storm,
            "response_codes": response_codes,
            "window_alignment": window_align,
            "coordination": coordination,
            "bypass_vulnerabilities": bypass,
            "capacity_plan": capacity,
            "all_recommendations": all_recs,
            "analyzed_at": now,
        }
