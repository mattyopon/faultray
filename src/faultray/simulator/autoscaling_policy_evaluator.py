# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Autoscaling Policy Evaluator — simulate and evaluate autoscaling policies.

Evaluates infrastructure autoscaling policies for resilience by simulating
scaling strategies (reactive, predictive, scheduled, step), analyzing
cooldown oscillation, scale-up/down asymmetry, cost optimization, scaling
lag, policy conflicts, warm pool management, blast radius during scale-in,
and regional scaling coordination.
"""

from __future__ import annotations

import logging
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ScalingStrategy(str, Enum):
    """Supported autoscaling strategy types."""

    REACTIVE = "reactive"
    PREDICTIVE = "predictive"
    SCHEDULED = "scheduled"
    STEP = "step"


class MetricType(str, Enum):
    """Metric types that can trigger scaling."""

    CPU = "cpu"
    MEMORY = "memory"
    REQUEST_RATE = "request_rate"
    QUEUE_DEPTH = "queue_depth"
    CUSTOM = "custom"
    COMBINED = "combined"


class ScalingDirection(str, Enum):
    """Direction of a scaling action."""

    UP = "scale_up"
    DOWN = "scale_down"
    NONE = "none"


class PolicySeverity(str, Enum):
    """Severity levels for policy evaluation findings."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ConflictType(str, Enum):
    """Types of policy conflicts."""

    CONTRADICTORY_THRESHOLDS = "contradictory_thresholds"
    OVERLAPPING_SCHEDULES = "overlapping_schedules"
    COOLDOWN_CONFLICT = "cooldown_conflict"
    METRIC_CONFLICT = "metric_conflict"
    DIRECTION_CONFLICT = "direction_conflict"


class CostStrategy(str, Enum):
    """Cost optimization strategies for scaling."""

    RIGHT_SIZING = "right_sizing"
    SPOT_MIX = "spot_mix"
    RESERVED_CAPACITY = "reserved_capacity"
    SCHEDULED_SCALING = "scheduled_scaling"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class MetricDataPoint:
    """A single metric observation at a point in time."""

    timestamp: float  # seconds since epoch or relative seconds
    value: float
    metric_type: MetricType = MetricType.CPU


@dataclass
class ScalingPolicy:
    """Definition of a single autoscaling policy rule."""

    policy_id: str
    component_id: str
    strategy: ScalingStrategy
    metric_type: MetricType
    scale_up_threshold: float = 70.0
    scale_down_threshold: float = 30.0
    min_instances: int = 1
    max_instances: int = 10
    cooldown_up_seconds: int = 60
    cooldown_down_seconds: int = 300
    step_adjustments: list[dict[str, Any]] = field(default_factory=list)
    schedule_expressions: list[dict[str, Any]] = field(default_factory=list)
    predictive_lookahead_seconds: int = 300
    warm_pool_size: int = 0
    warm_pool_reuse: bool = True
    connection_drain_seconds: int = 30
    region: str = ""
    priority: int = 0  # higher = takes precedence


@dataclass
class ScalingEvent:
    """A recorded or simulated scaling event."""

    timestamp: float
    component_id: str
    direction: ScalingDirection
    from_count: int
    to_count: int
    trigger_metric: MetricType
    trigger_value: float
    lag_seconds: float = 0.0
    policy_id: str = ""
    was_blocked_by_cooldown: bool = False
    warm_pool_used: int = 0


@dataclass
class OscillationWindow:
    """A detected period of scaling oscillation."""

    start_time: float
    end_time: float
    direction_changes: int
    avg_interval_seconds: float
    affected_component: str


@dataclass
class PolicyConflict:
    """A detected conflict between two scaling policies."""

    policy_a_id: str
    policy_b_id: str
    conflict_type: ConflictType
    severity: PolicySeverity
    description: str
    recommendation: str


@dataclass
class CostAnalysis:
    """Cost analysis for a scaling configuration."""

    component_id: str
    strategy: CostStrategy
    current_monthly_cost: float
    optimized_monthly_cost: float
    savings_percent: float
    spot_ratio: float = 0.0
    reserved_ratio: float = 0.0
    recommendation: str = ""


@dataclass
class ScalingLagAnalysis:
    """Analysis of time from scaling trigger to instance readiness."""

    component_id: str
    avg_lag_seconds: float
    p95_lag_seconds: float
    max_lag_seconds: float
    breakdown: dict[str, float] = field(default_factory=dict)
    meets_sla: bool = True
    sla_target_seconds: float = 120.0


@dataclass
class BlastRadiusResult:
    """Analysis of impact when instances are removed during scale-in."""

    component_id: str
    instances_removed: int
    active_connections_affected: int
    drain_time_seconds: float
    request_drop_estimate: float
    dependent_components: list[str] = field(default_factory=list)
    risk_level: PolicySeverity = PolicySeverity.LOW


@dataclass
class RegionalScalingState:
    """Scaling state for a specific region."""

    region: str
    component_id: str
    current_instances: int
    target_instances: int
    is_primary: bool = True
    cross_region_latency_ms: float = 0.0


@dataclass
class WarmPoolState:
    """State of the warm pool for a component."""

    component_id: str
    pool_size: int
    available: int
    initializing: int
    reuse_enabled: bool = True
    avg_init_time_seconds: float = 30.0


@dataclass
class EvaluationResult:
    """Complete result of autoscaling policy evaluation."""

    component_id: str
    policies_evaluated: int
    scaling_events: list[ScalingEvent] = field(default_factory=list)
    oscillations: list[OscillationWindow] = field(default_factory=list)
    conflicts: list[PolicyConflict] = field(default_factory=list)
    cost_analyses: list[CostAnalysis] = field(default_factory=list)
    lag_analyses: list[ScalingLagAnalysis] = field(default_factory=list)
    blast_radius_results: list[BlastRadiusResult] = field(default_factory=list)
    warm_pool_states: list[WarmPoolState] = field(default_factory=list)
    regional_states: list[RegionalScalingState] = field(default_factory=list)
    overall_severity: PolicySeverity = PolicySeverity.INFO
    recommendations: list[str] = field(default_factory=list)
    score: float = 100.0  # 0-100, higher is better
    evaluated_at: str = ""


# ---------------------------------------------------------------------------
# Core evaluator
# ---------------------------------------------------------------------------

class AutoscalingPolicyEvaluator:
    """Evaluate and simulate autoscaling policies for infrastructure resilience.

    Parameters
    ----------
    graph:
        The infrastructure graph to analyse.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph
        self._policies: list[ScalingPolicy] = []
        self._metric_history: dict[str, list[MetricDataPoint]] = {}
        self._scaling_events: list[ScalingEvent] = []

    # -- Policy management ---------------------------------------------------

    def add_policy(self, policy: ScalingPolicy) -> None:
        """Register a scaling policy."""
        self._policies.append(policy)

    def add_policies(self, policies: list[ScalingPolicy]) -> None:
        """Register multiple scaling policies at once."""
        self._policies.extend(policies)

    def get_policies(self, component_id: str | None = None) -> list[ScalingPolicy]:
        """Return policies, optionally filtered by component."""
        if component_id is None:
            return list(self._policies)
        return [p for p in self._policies if p.component_id == component_id]

    def clear_policies(self) -> None:
        """Remove all registered policies."""
        self._policies.clear()

    # -- Metric history ------------------------------------------------------

    def add_metric_data(
        self,
        component_id: str,
        data_points: list[MetricDataPoint],
    ) -> None:
        """Record metric history for a component."""
        self._metric_history.setdefault(component_id, []).extend(data_points)

    def get_metric_history(self, component_id: str) -> list[MetricDataPoint]:
        """Return recorded metric data for a component."""
        return list(self._metric_history.get(component_id, []))

    # -- Simulation ----------------------------------------------------------

    def simulate_scaling(
        self,
        component_id: str,
        metric_series: list[MetricDataPoint],
        initial_instances: int = 1,
        duration_seconds: float | None = None,
    ) -> list[ScalingEvent]:
        """Simulate scaling events given a time-series of metric values.

        Walks through the metric series chronologically and applies all
        matching policies to determine when scaling would occur, honouring
        cooldown periods, min/max constraints, and warm pool availability.

        Returns a list of :class:`ScalingEvent` in chronological order.
        """
        policies = self.get_policies(component_id)
        if not policies or not metric_series:
            return []

        sorted_series = sorted(metric_series, key=lambda dp: dp.timestamp)
        if duration_seconds is not None:
            end_time = sorted_series[0].timestamp + duration_seconds
            sorted_series = [dp for dp in sorted_series if dp.timestamp <= end_time]

        current_instances = initial_instances
        events: list[ScalingEvent] = []
        last_scale_up_time: float = -float("inf")
        last_scale_down_time: float = -float("inf")

        for dp in sorted_series:
            for policy in sorted(policies, key=lambda p: -p.priority):
                if policy.metric_type != MetricType.COMBINED and policy.metric_type != dp.metric_type:
                    continue

                direction = self._evaluate_threshold(
                    dp.value,
                    policy.scale_up_threshold,
                    policy.scale_down_threshold,
                    policy.strategy,
                    policy.step_adjustments,
                )

                if direction == ScalingDirection.NONE:
                    continue

                # Check cooldown
                blocked = False
                if direction == ScalingDirection.UP:
                    if dp.timestamp - last_scale_up_time < policy.cooldown_up_seconds:
                        blocked = True
                else:
                    if dp.timestamp - last_scale_down_time < policy.cooldown_down_seconds:
                        blocked = True

                new_count = self._compute_new_count(
                    current_instances,
                    direction,
                    policy,
                    dp.value,
                )

                # Enforce min/max
                new_count = max(policy.min_instances, min(policy.max_instances, new_count))

                if new_count == current_instances:
                    continue

                # Warm pool benefit
                warm_used = 0
                if direction == ScalingDirection.UP and policy.warm_pool_size > 0:
                    needed = new_count - current_instances
                    warm_used = min(needed, policy.warm_pool_size)

                lag = self._estimate_lag(
                    direction,
                    new_count - current_instances if direction == ScalingDirection.UP else current_instances - new_count,
                    warm_used,
                    policy.connection_drain_seconds,
                )

                event = ScalingEvent(
                    timestamp=dp.timestamp,
                    component_id=component_id,
                    direction=direction,
                    from_count=current_instances,
                    to_count=new_count,
                    trigger_metric=dp.metric_type,
                    trigger_value=dp.value,
                    lag_seconds=lag,
                    policy_id=policy.policy_id,
                    was_blocked_by_cooldown=blocked,
                    warm_pool_used=warm_used,
                )
                events.append(event)

                if not blocked:
                    if direction == ScalingDirection.UP:
                        last_scale_up_time = dp.timestamp
                    else:
                        last_scale_down_time = dp.timestamp
                    current_instances = new_count

        self._scaling_events.extend(events)
        return events

    # -- Oscillation detection -----------------------------------------------

    def detect_oscillations(
        self,
        events: list[ScalingEvent],
        window_seconds: float = 600.0,
        min_direction_changes: int = 3,
    ) -> list[OscillationWindow]:
        """Detect scaling oscillation (thrashing) in a sequence of events.

        An oscillation window is identified when the scaling direction changes
        at least *min_direction_changes* times within *window_seconds*.
        """
        if len(events) < min_direction_changes:
            return []

        # Only consider non-blocked events
        effective = [e for e in events if not e.was_blocked_by_cooldown]
        if len(effective) < min_direction_changes:
            return []

        effective.sort(key=lambda e: e.timestamp)
        oscillations: list[OscillationWindow] = []

        i = 0
        while i < len(effective):
            window_start = effective[i].timestamp
            window_end = window_start + window_seconds
            window_events = [
                e for e in effective
                if window_start <= e.timestamp <= window_end
            ]

            if len(window_events) < min_direction_changes:
                i += 1
                continue

            direction_changes = 0
            for j in range(1, len(window_events)):
                if window_events[j].direction != window_events[j - 1].direction:
                    direction_changes += 1

            if direction_changes >= min_direction_changes:
                intervals = [
                    window_events[j].timestamp - window_events[j - 1].timestamp
                    for j in range(1, len(window_events))
                ]
                avg_interval = statistics.mean(intervals) if intervals else 0.0

                oscillations.append(OscillationWindow(
                    start_time=window_events[0].timestamp,
                    end_time=window_events[-1].timestamp,
                    direction_changes=direction_changes,
                    avg_interval_seconds=avg_interval,
                    affected_component=window_events[0].component_id,
                ))
                # Skip past this window
                i += len(window_events)
            else:
                i += 1

        return oscillations

    # -- Asymmetry analysis --------------------------------------------------

    def analyse_asymmetry(
        self,
        policies: list[ScalingPolicy],
    ) -> dict[str, Any]:
        """Analyse scale-up vs scale-down asymmetry in policies.

        Returns a dict with asymmetry metrics for each component.  Good
        practice is aggressive scale-up but conservative scale-down.
        """
        result: dict[str, Any] = {}

        for policy in policies:
            cid = policy.component_id
            up_threshold = policy.scale_up_threshold
            down_threshold = policy.scale_down_threshold

            threshold_gap = up_threshold - down_threshold
            cooldown_ratio = (
                policy.cooldown_down_seconds / policy.cooldown_up_seconds
                if policy.cooldown_up_seconds > 0
                else 0.0
            )

            is_healthy = threshold_gap >= 20.0 and cooldown_ratio >= 2.0
            recommendations: list[str] = []
            if threshold_gap < 20.0:
                recommendations.append(
                    f"Increase threshold gap (currently {threshold_gap:.0f}%) "
                    f"to at least 20% to reduce oscillation risk."
                )
            if cooldown_ratio < 2.0:
                recommendations.append(
                    f"Scale-down cooldown ({policy.cooldown_down_seconds}s) should "
                    f"be at least 2x scale-up cooldown ({policy.cooldown_up_seconds}s)."
                )
            if down_threshold < 10.0:
                recommendations.append(
                    f"Scale-down threshold ({down_threshold}%) is very low; "
                    f"instances may remain underutilised for extended periods."
                )

            result[cid] = {
                "policy_id": policy.policy_id,
                "threshold_gap": threshold_gap,
                "cooldown_ratio": round(cooldown_ratio, 2),
                "is_healthy": is_healthy,
                "recommendations": recommendations,
            }

        return result

    # -- Conflict detection --------------------------------------------------

    def detect_conflicts(
        self,
        policies: list[ScalingPolicy] | None = None,
    ) -> list[PolicyConflict]:
        """Detect conflicts between scaling policies.

        Checks for contradictory thresholds, overlapping schedules,
        cooldown mismatches, metric conflicts, and directional conflicts.
        """
        policies = policies if policies is not None else self._policies
        conflicts: list[PolicyConflict] = []

        # Group policies by component
        by_component: dict[str, list[ScalingPolicy]] = {}
        for p in policies:
            by_component.setdefault(p.component_id, []).append(p)

        for cid, comp_policies in by_component.items():
            for i in range(len(comp_policies)):
                for j in range(i + 1, len(comp_policies)):
                    pa = comp_policies[i]
                    pb = comp_policies[j]
                    conflicts.extend(self._check_pair_conflicts(pa, pb))

        return conflicts

    def _check_pair_conflicts(
        self,
        pa: ScalingPolicy,
        pb: ScalingPolicy,
    ) -> list[PolicyConflict]:
        """Check two policies for conflicts."""
        conflicts: list[PolicyConflict] = []

        # Contradictory thresholds: pa scale-up < pb scale-down (or vice versa)
        if pa.scale_up_threshold < pb.scale_down_threshold:
            conflicts.append(PolicyConflict(
                policy_a_id=pa.policy_id,
                policy_b_id=pb.policy_id,
                conflict_type=ConflictType.CONTRADICTORY_THRESHOLDS,
                severity=PolicySeverity.CRITICAL,
                description=(
                    f"Policy '{pa.policy_id}' scale-up threshold "
                    f"({pa.scale_up_threshold}%) is below policy "
                    f"'{pb.policy_id}' scale-down threshold "
                    f"({pb.scale_down_threshold}%).  This will cause "
                    f"simultaneous scale-up and scale-down signals."
                ),
                recommendation="Align thresholds so scale-up > scale-down across all policies.",
            ))

        if pb.scale_up_threshold < pa.scale_down_threshold:
            conflicts.append(PolicyConflict(
                policy_a_id=pa.policy_id,
                policy_b_id=pb.policy_id,
                conflict_type=ConflictType.CONTRADICTORY_THRESHOLDS,
                severity=PolicySeverity.CRITICAL,
                description=(
                    f"Policy '{pb.policy_id}' scale-up threshold "
                    f"({pb.scale_up_threshold}%) is below policy "
                    f"'{pa.policy_id}' scale-down threshold "
                    f"({pa.scale_down_threshold}%).  This will cause "
                    f"simultaneous scale-up and scale-down signals."
                ),
                recommendation="Align thresholds so scale-up > scale-down across all policies.",
            ))

        # Cooldown conflict — dramatically different cooldowns
        if pa.cooldown_up_seconds > 0 and pb.cooldown_up_seconds > 0:
            ratio = max(pa.cooldown_up_seconds, pb.cooldown_up_seconds) / min(
                pa.cooldown_up_seconds, pb.cooldown_up_seconds
            )
            if ratio > 5.0:
                conflicts.append(PolicyConflict(
                    policy_a_id=pa.policy_id,
                    policy_b_id=pb.policy_id,
                    conflict_type=ConflictType.COOLDOWN_CONFLICT,
                    severity=PolicySeverity.MEDIUM,
                    description=(
                        f"Scale-up cooldown differs by {ratio:.1f}x between "
                        f"'{pa.policy_id}' ({pa.cooldown_up_seconds}s) and "
                        f"'{pb.policy_id}' ({pb.cooldown_up_seconds}s)."
                    ),
                    recommendation="Standardise cooldown periods to avoid unpredictable behaviour.",
                ))

        # Min/max conflict
        if pa.min_instances > pb.max_instances or pb.min_instances > pa.max_instances:
            conflicts.append(PolicyConflict(
                policy_a_id=pa.policy_id,
                policy_b_id=pb.policy_id,
                conflict_type=ConflictType.DIRECTION_CONFLICT,
                severity=PolicySeverity.HIGH,
                description=(
                    f"Instance range conflict: '{pa.policy_id}' "
                    f"[{pa.min_instances}-{pa.max_instances}] vs "
                    f"'{pb.policy_id}' [{pb.min_instances}-{pb.max_instances}]."
                ),
                recommendation="Ensure instance ranges overlap across policies for the same component.",
            ))

        # Metric conflict — same metric, conflicting directions
        if (
            pa.metric_type == pb.metric_type
            and pa.metric_type != MetricType.COMBINED
            and pa.scale_up_threshold <= pb.scale_up_threshold
            and pa.scale_down_threshold >= pb.scale_down_threshold
        ):
            if pa.policy_id != pb.policy_id:
                conflicts.append(PolicyConflict(
                    policy_a_id=pa.policy_id,
                    policy_b_id=pb.policy_id,
                    conflict_type=ConflictType.METRIC_CONFLICT,
                    severity=PolicySeverity.LOW,
                    description=(
                        f"Policies '{pa.policy_id}' and '{pb.policy_id}' "
                        f"target the same metric ({pa.metric_type.value}) "
                        f"with nested thresholds — one may shadow the other."
                    ),
                    recommendation="Remove redundant policy or differentiate threshold ranges.",
                ))

        return conflicts

    # -- Cost optimisation ---------------------------------------------------

    def analyse_cost(
        self,
        component_id: str,
        hourly_instance_cost: float = 0.10,
        spot_discount: float = 0.70,
        reserved_discount: float = 0.40,
        avg_instances: float | None = None,
    ) -> CostAnalysis:
        """Analyse cost optimisation opportunities for a component.

        Evaluates right-sizing, spot instance mix, and reserved capacity
        strategies.
        """
        comp = self.graph.get_component(component_id)
        if comp is None:
            return CostAnalysis(
                component_id=component_id,
                strategy=CostStrategy.RIGHT_SIZING,
                current_monthly_cost=0.0,
                optimized_monthly_cost=0.0,
                savings_percent=0.0,
                recommendation="Component not found.",
            )

        instances = avg_instances if avg_instances is not None else float(comp.replicas)
        hours_per_month = 730.0
        current_cost = instances * hourly_instance_cost * hours_per_month

        policies = self.get_policies(component_id)
        min_required = max((p.min_instances for p in policies), default=comp.replicas)

        # Reserved for baseline, spot for burst
        reserved_count = float(min_required)
        burst_count = max(0.0, instances - reserved_count)

        spot_ratio = burst_count / instances if instances > 0 else 0.0
        reserved_ratio = reserved_count / instances if instances > 0 else 1.0

        optimised_cost = (
            reserved_count * hourly_instance_cost * (1.0 - reserved_discount) * hours_per_month
            + burst_count * hourly_instance_cost * (1.0 - spot_discount) * hours_per_month
        )

        savings = (
            (current_cost - optimised_cost) / current_cost * 100.0
            if current_cost > 0
            else 0.0
        )

        best_strategy = CostStrategy.SPOT_MIX if burst_count > 0 else CostStrategy.RESERVED_CAPACITY

        recommendation_parts: list[str] = []
        if reserved_count > 0:
            recommendation_parts.append(
                f"Reserve {int(reserved_count)} base instance(s) "
                f"(save {reserved_discount * 100:.0f}%)."
            )
        if burst_count > 0:
            recommendation_parts.append(
                f"Use spot for {burst_count:.0f} burst instance(s) "
                f"(save {spot_discount * 100:.0f}%)."
            )

        return CostAnalysis(
            component_id=component_id,
            strategy=best_strategy,
            current_monthly_cost=round(current_cost, 2),
            optimized_monthly_cost=round(optimised_cost, 2),
            savings_percent=round(savings, 2),
            spot_ratio=round(spot_ratio, 4),
            reserved_ratio=round(reserved_ratio, 4),
            recommendation=" ".join(recommendation_parts),
        )

    # -- Scaling lag analysis ------------------------------------------------

    def analyse_scaling_lag(
        self,
        events: list[ScalingEvent],
        sla_target_seconds: float = 120.0,
    ) -> ScalingLagAnalysis:
        """Analyse scaling lag across a set of events.

        Computes average, p95, and max lag and checks against an SLA target.
        """
        if not events:
            return ScalingLagAnalysis(
                component_id="",
                avg_lag_seconds=0.0,
                p95_lag_seconds=0.0,
                max_lag_seconds=0.0,
                meets_sla=True,
                sla_target_seconds=sla_target_seconds,
            )

        component_id = events[0].component_id
        lags = [e.lag_seconds for e in events if e.lag_seconds > 0]
        if not lags:
            return ScalingLagAnalysis(
                component_id=component_id,
                avg_lag_seconds=0.0,
                p95_lag_seconds=0.0,
                max_lag_seconds=0.0,
                meets_sla=True,
                sla_target_seconds=sla_target_seconds,
            )

        sorted_lags = sorted(lags)
        avg_lag = statistics.mean(sorted_lags)
        p95_index = max(0, int(math.ceil(len(sorted_lags) * 0.95)) - 1)
        p95_lag = sorted_lags[p95_index]
        max_lag = sorted_lags[-1]

        # Breakdown
        breakdown: dict[str, float] = {}
        up_lags = [e.lag_seconds for e in events if e.direction == ScalingDirection.UP and e.lag_seconds > 0]
        down_lags = [e.lag_seconds for e in events if e.direction == ScalingDirection.DOWN and e.lag_seconds > 0]
        if up_lags:
            breakdown["scale_up_avg"] = round(statistics.mean(up_lags), 2)
        if down_lags:
            breakdown["scale_down_avg"] = round(statistics.mean(down_lags), 2)

        return ScalingLagAnalysis(
            component_id=component_id,
            avg_lag_seconds=round(avg_lag, 2),
            p95_lag_seconds=round(p95_lag, 2),
            max_lag_seconds=round(max_lag, 2),
            breakdown=breakdown,
            meets_sla=p95_lag <= sla_target_seconds,
            sla_target_seconds=sla_target_seconds,
        )

    # -- Blast radius during scale-in ----------------------------------------

    def analyse_blast_radius(
        self,
        component_id: str,
        instances_to_remove: int = 1,
        connections_per_instance: int = 100,
        requests_in_flight: int = 50,
    ) -> BlastRadiusResult:
        """Estimate blast radius when removing instances during scale-in.

        Considers connection draining, in-flight request loss, and downstream
        impact.
        """
        comp = self.graph.get_component(component_id)
        if comp is None:
            return BlastRadiusResult(
                component_id=component_id,
                instances_removed=instances_to_remove,
                active_connections_affected=0,
                drain_time_seconds=0.0,
                request_drop_estimate=0.0,
                risk_level=PolicySeverity.INFO,
            )

        policies = self.get_policies(component_id)
        drain_time = max(
            (p.connection_drain_seconds for p in policies),
            default=30.0,
        )

        affected_connections = instances_to_remove * connections_per_instance
        # Estimate dropped requests: those arriving during drain that exceed
        # the remaining capacity of the removed instance's queue.
        drop_estimate = max(0.0, float(requests_in_flight * instances_to_remove) - drain_time * 0.5)

        # Dependent components
        dependents = self.graph.get_dependents(component_id)
        dependent_ids = [d.id for d in dependents]

        remaining = comp.replicas - instances_to_remove
        if remaining <= 0:
            risk = PolicySeverity.CRITICAL
        elif remaining < 2:
            risk = PolicySeverity.HIGH
        elif instances_to_remove > comp.replicas // 2:
            risk = PolicySeverity.MEDIUM
        else:
            risk = PolicySeverity.LOW

        return BlastRadiusResult(
            component_id=component_id,
            instances_removed=instances_to_remove,
            active_connections_affected=affected_connections,
            drain_time_seconds=drain_time,
            request_drop_estimate=round(drop_estimate, 2),
            dependent_components=dependent_ids,
            risk_level=risk,
        )

    # -- Warm pool management ------------------------------------------------

    def evaluate_warm_pool(
        self,
        component_id: str,
        avg_init_time_seconds: float = 30.0,
    ) -> WarmPoolState:
        """Evaluate warm pool configuration for a component."""
        policies = self.get_policies(component_id)
        if not policies:
            return WarmPoolState(
                component_id=component_id,
                pool_size=0,
                available=0,
                initializing=0,
                reuse_enabled=True,
                avg_init_time_seconds=avg_init_time_seconds,
            )

        total_pool = sum(p.warm_pool_size for p in policies)
        reuse = all(p.warm_pool_reuse for p in policies)

        # Estimate availability: assume 80% of warm pool ready at any time
        available = int(total_pool * 0.8)
        initializing = total_pool - available

        return WarmPoolState(
            component_id=component_id,
            pool_size=total_pool,
            available=available,
            initializing=initializing,
            reuse_enabled=reuse,
            avg_init_time_seconds=avg_init_time_seconds,
        )

    # -- Regional scaling coordination --------------------------------------

    def coordinate_regional_scaling(
        self,
        component_id: str,
        regions: list[dict[str, Any]],
    ) -> list[RegionalScalingState]:
        """Coordinate scaling decisions across multiple regions.

        Parameters
        ----------
        component_id:
            The component to evaluate.
        regions:
            List of dicts with keys: ``region``, ``current_instances``,
            ``target_instances``, ``is_primary``, ``latency_ms``.
        """
        if not regions:
            return []

        states: list[RegionalScalingState] = []
        total_current = sum(r.get("current_instances", 0) for r in regions)
        total_target = sum(r.get("target_instances", 0) for r in regions)

        for r in regions:
            current = r.get("current_instances", 0)
            target = r.get("target_instances", current)
            is_primary = r.get("is_primary", False)
            latency = r.get("latency_ms", 0.0)

            # Adjust target based on regional weight
            if total_target > 0 and total_current > 0:
                weight = current / total_current
                adjusted_target = max(1, int(math.ceil(total_target * weight)))
            else:
                adjusted_target = target

            # Primary region gets at least 2 instances
            if is_primary and adjusted_target < 2:
                adjusted_target = 2

            states.append(RegionalScalingState(
                region=r.get("region", "unknown"),
                component_id=component_id,
                current_instances=current,
                target_instances=adjusted_target,
                is_primary=is_primary,
                cross_region_latency_ms=latency,
            ))

        return states

    # -- Multi-dimensional scaling -------------------------------------------

    def evaluate_multi_metric(
        self,
        component_id: str,
        metric_snapshots: dict[MetricType, float],
    ) -> ScalingDirection:
        """Determine scaling direction when multiple metrics are considered.

        If *any* metric exceeds the scale-up threshold of a matching
        policy, scale up is recommended.  Scale-down requires *all*
        metrics to be below their scale-down thresholds.
        """
        policies = self.get_policies(component_id)
        if not policies:
            return ScalingDirection.NONE

        any_up = False
        all_down = True

        for policy in policies:
            for metric_type, value in metric_snapshots.items():
                if policy.metric_type not in (metric_type, MetricType.COMBINED):
                    continue

                if value >= policy.scale_up_threshold:
                    any_up = True
                    all_down = False
                elif value > policy.scale_down_threshold:
                    all_down = False

        if any_up:
            return ScalingDirection.UP
        if all_down and metric_snapshots:
            return ScalingDirection.DOWN
        return ScalingDirection.NONE

    # -- Predictive scaling helpers ------------------------------------------

    def forecast_metric(
        self,
        data_points: list[MetricDataPoint],
        horizon_seconds: float = 300.0,
    ) -> list[MetricDataPoint]:
        """Simple linear forecast of metric values.

        Fits a linear model to the data and generates forecast points every
        60 seconds into the future.
        """
        if len(data_points) < 2:
            return []

        sorted_dp = sorted(data_points, key=lambda d: d.timestamp)
        n = len(sorted_dp)
        xs = [dp.timestamp for dp in sorted_dp]
        ys = [dp.value for dp in sorted_dp]

        mean_x = sum(xs) / n
        mean_y = sum(ys) / n

        numerator = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
        denominator = sum((xs[i] - mean_x) ** 2 for i in range(n))

        if denominator == 0:
            slope = 0.0
        else:
            slope = numerator / denominator

        intercept = mean_y - slope * mean_x

        forecasts: list[MetricDataPoint] = []
        last_ts = sorted_dp[-1].timestamp
        step = 60.0
        t = last_ts + step
        metric_type = sorted_dp[0].metric_type

        while t <= last_ts + horizon_seconds:
            predicted = slope * t + intercept
            forecasts.append(MetricDataPoint(
                timestamp=t,
                value=max(0.0, predicted),
                metric_type=metric_type,
            ))
            t += step

        return forecasts

    # -- Full evaluation -----------------------------------------------------

    def evaluate(
        self,
        component_id: str | None = None,
    ) -> list[EvaluationResult]:
        """Run a full evaluation for one or all components.

        Returns an :class:`EvaluationResult` per component summarising
        conflicts, oscillations, cost, lag, blast radius, warm pool state,
        and overall score.
        """
        component_ids: list[str]
        if component_id is not None:
            component_ids = [component_id]
        else:
            component_ids = list(self.graph.components.keys())

        if not component_ids:
            return []

        results: list[EvaluationResult] = []
        now = datetime.now(timezone.utc).isoformat()

        for cid in component_ids:
            policies = self.get_policies(cid)
            metric_data = self.get_metric_history(cid)

            # Simulate if we have metric data
            events: list[ScalingEvent] = []
            if metric_data and policies:
                comp = self.graph.get_component(cid)
                initial = comp.replicas if comp else 1
                events = self.simulate_scaling(cid, metric_data, initial_instances=initial)

            # Oscillation
            oscillations = self.detect_oscillations(events) if events else []

            # Conflicts
            conflicts = self.detect_conflicts(policies)

            # Cost
            cost_analyses: list[CostAnalysis] = []
            if self.graph.get_component(cid) is not None:
                cost_analyses.append(self.analyse_cost(cid))

            # Lag
            lag_analyses: list[ScalingLagAnalysis] = []
            if events:
                lag_analyses.append(self.analyse_scaling_lag(events))

            # Blast radius
            blast_results: list[BlastRadiusResult] = []
            comp = self.graph.get_component(cid)
            if comp is not None and comp.replicas > 1:
                blast_results.append(self.analyse_blast_radius(cid))

            # Warm pool
            warm_pool = self.evaluate_warm_pool(cid)

            # Score
            score = self._calculate_score(
                policies,
                events,
                oscillations,
                conflicts,
                lag_analyses,
                blast_results,
            )

            # Severity
            severity = self._derive_severity(score)

            # Recommendations
            recommendations = self._build_recommendations(
                cid,
                policies,
                oscillations,
                conflicts,
                lag_analyses,
                blast_results,
                warm_pool,
            )

            results.append(EvaluationResult(
                component_id=cid,
                policies_evaluated=len(policies),
                scaling_events=events,
                oscillations=oscillations,
                conflicts=conflicts,
                cost_analyses=cost_analyses,
                lag_analyses=lag_analyses,
                blast_radius_results=blast_results,
                warm_pool_states=[warm_pool] if warm_pool.pool_size > 0 else [],
                overall_severity=severity,
                recommendations=recommendations,
                score=round(score, 1),
                evaluated_at=now,
            ))

        return results

    # -- Internal helpers ----------------------------------------------------

    @staticmethod
    def _evaluate_threshold(
        value: float,
        up_threshold: float,
        down_threshold: float,
        strategy: ScalingStrategy,
        step_adjustments: list[dict[str, Any]],
    ) -> ScalingDirection:
        """Determine scaling direction from a metric value and thresholds."""
        if strategy == ScalingStrategy.STEP and step_adjustments:
            for step in sorted(step_adjustments, key=lambda s: s.get("threshold", 0)):
                threshold = step.get("threshold", up_threshold)
                direction = step.get("direction", "up")
                if direction == "up" and value >= threshold:
                    return ScalingDirection.UP
                if direction == "down" and value <= threshold:
                    return ScalingDirection.DOWN
            return ScalingDirection.NONE

        if value >= up_threshold:
            return ScalingDirection.UP
        if value <= down_threshold:
            return ScalingDirection.DOWN
        return ScalingDirection.NONE

    @staticmethod
    def _compute_new_count(
        current: int,
        direction: ScalingDirection,
        policy: ScalingPolicy,
        metric_value: float,
    ) -> int:
        """Compute the target instance count after a scaling action."""
        if direction == ScalingDirection.UP:
            if policy.strategy == ScalingStrategy.STEP and policy.step_adjustments:
                # Find matching step
                for step in sorted(
                    policy.step_adjustments,
                    key=lambda s: s.get("threshold", 0),
                    reverse=True,
                ):
                    if metric_value >= step.get("threshold", 0):
                        adj = step.get("adjustment", 1)
                        return current + adj
                return current + 1
            # Default: add proportional to overshoot
            overshoot = (metric_value - policy.scale_up_threshold) / policy.scale_up_threshold
            add = max(1, int(math.ceil(current * overshoot))) if overshoot > 0 else 1
            return current + add
        else:
            # Scale down: remove one instance
            return max(policy.min_instances, current - 1)

    @staticmethod
    def _estimate_lag(
        direction: ScalingDirection,
        count_change: int,
        warm_pool_used: int,
        drain_seconds: float,
    ) -> float:
        """Estimate time lag for a scaling operation.

        Scale-up lag = instance boot time (reduced by warm pool).
        Scale-down lag = connection drain time.
        """
        if direction == ScalingDirection.UP:
            cold_start = max(0, count_change - warm_pool_used)
            warm_start = warm_pool_used
            # Cold-start instances: ~45s each (parallel), warm: ~5s
            lag = max(cold_start * 45.0, warm_start * 5.0) if cold_start > 0 else warm_start * 5.0
            return lag
        else:
            return drain_seconds

    def _calculate_score(
        self,
        policies: list[ScalingPolicy],
        events: list[ScalingEvent],
        oscillations: list[OscillationWindow],
        conflicts: list[PolicyConflict],
        lag_analyses: list[ScalingLagAnalysis],
        blast_results: list[BlastRadiusResult],
    ) -> float:
        """Calculate overall evaluation score (0-100)."""
        score = 100.0

        # No policies configured
        if not policies:
            return 50.0

        # Deductions for conflicts
        for conflict in conflicts:
            if conflict.severity == PolicySeverity.CRITICAL:
                score -= 20.0
            elif conflict.severity == PolicySeverity.HIGH:
                score -= 12.0
            elif conflict.severity == PolicySeverity.MEDIUM:
                score -= 5.0
            elif conflict.severity == PolicySeverity.LOW:
                score -= 2.0

        # Deductions for oscillations
        score -= len(oscillations) * 10.0

        # Deductions for blocked events (cooldown)
        blocked = sum(1 for e in events if e.was_blocked_by_cooldown)
        score -= blocked * 3.0

        # Deductions for lag SLA violations
        for lag in lag_analyses:
            if not lag.meets_sla:
                score -= 15.0

        # Deductions for blast radius
        for br in blast_results:
            if br.risk_level == PolicySeverity.CRITICAL:
                score -= 15.0
            elif br.risk_level == PolicySeverity.HIGH:
                score -= 8.0
            elif br.risk_level == PolicySeverity.MEDIUM:
                score -= 3.0

        return max(0.0, min(100.0, score))

    @staticmethod
    def _derive_severity(score: float) -> PolicySeverity:
        """Map a score to a severity level."""
        if score >= 90.0:
            return PolicySeverity.INFO
        if score >= 70.0:
            return PolicySeverity.LOW
        if score >= 50.0:
            return PolicySeverity.MEDIUM
        if score >= 30.0:
            return PolicySeverity.HIGH
        return PolicySeverity.CRITICAL

    def _build_recommendations(
        self,
        component_id: str,
        policies: list[ScalingPolicy],
        oscillations: list[OscillationWindow],
        conflicts: list[PolicyConflict],
        lag_analyses: list[ScalingLagAnalysis],
        blast_results: list[BlastRadiusResult],
        warm_pool: WarmPoolState,
    ) -> list[str]:
        """Generate recommendations based on evaluation findings."""
        recs: list[str] = []

        if not policies:
            recs.append(
                f"No scaling policies defined for '{component_id}'. "
                f"Configure at least one autoscaling policy."
            )
            return recs

        for osc in oscillations:
            recs.append(
                f"Scaling oscillation detected ({osc.direction_changes} direction "
                f"changes in {osc.end_time - osc.start_time:.0f}s). "
                f"Consider increasing cooldown periods or widening threshold gap."
            )

        for conflict in conflicts:
            recs.append(f"[{conflict.severity.value.upper()}] {conflict.recommendation}")

        for lag in lag_analyses:
            if not lag.meets_sla:
                recs.append(
                    f"Scaling lag p95 ({lag.p95_lag_seconds:.0f}s) exceeds SLA target "
                    f"({lag.sla_target_seconds:.0f}s). Consider adding warm pool instances."
                )

        for br in blast_results:
            if br.risk_level in (PolicySeverity.CRITICAL, PolicySeverity.HIGH):
                recs.append(
                    f"Scale-in blast radius is {br.risk_level.value}: removing "
                    f"{br.instances_removed} instance(s) affects "
                    f"{br.active_connections_affected} connections. "
                    f"Increase connection drain time or reduce scale-in step."
                )

        if warm_pool.pool_size == 0 and policies:
            max_lag = max((la.max_lag_seconds for la in lag_analyses), default=0.0)
            if max_lag > 60.0:
                recs.append(
                    f"No warm pool configured but max scaling lag is {max_lag:.0f}s. "
                    f"Configure a warm pool to reduce cold-start latency."
                )

        # Asymmetry check
        asymmetry = self.analyse_asymmetry(policies)
        for cid_key, info in asymmetry.items():
            if not info["is_healthy"]:
                for r in info["recommendations"]:
                    recs.append(r)

        return recs
