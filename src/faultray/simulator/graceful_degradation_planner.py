# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Graceful Degradation Planner.

Plans and evaluates graceful degradation strategies for partial failures.
Supports degradation levels, feature criticality classification,
dependency-based degradation planning, user experience impact scoring,
fallback strategy evaluation, circuit breaker coordination, load shedding
strategy analysis, bulkhead pattern evaluation, degradation cascade analysis,
recovery sequence planning, and SLA impact assessment.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DegradationLevel(str, Enum):
    """Ordered degradation levels from full service to offline."""

    FULL_SERVICE = "full_service"
    REDUCED_FUNCTIONALITY = "reduced_functionality"
    READ_ONLY = "read_only"
    MAINTENANCE_MODE = "maintenance_mode"
    OFFLINE = "offline"


class FeatureCriticality(str, Enum):
    """Criticality classification for features."""

    CRITICAL = "critical"
    IMPORTANT = "important"
    NICE_TO_HAVE = "nice_to_have"


class FallbackType(str, Enum):
    """Types of fallback strategies."""

    CACHE = "cache"
    STATIC_CONTENT = "static_content"
    DEFAULT_VALUES = "default_values"
    QUEUE_FOR_LATER = "queue_for_later"
    REDIRECT = "redirect"
    NONE = "none"


class LoadSheddingPriority(str, Enum):
    """Request priority levels for load shedding."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    BEST_EFFORT = "best_effort"


class BulkheadStatus(str, Enum):
    """Status of a bulkhead partition."""

    HEALTHY = "healthy"
    STRESSED = "stressed"
    FAILING = "failing"
    ISOLATED = "isolated"


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class Feature(BaseModel):
    """A service feature with criticality and dependencies."""

    name: str
    criticality: FeatureCriticality = FeatureCriticality.IMPORTANT
    component_ids: list[str] = Field(default_factory=list)
    depends_on_features: list[str] = Field(default_factory=list)
    fallback: FallbackType = FallbackType.NONE
    fallback_ttl_seconds: float = 300.0
    user_impact_weight: float = Field(default=1.0, ge=0.0, le=10.0)
    revenue_impact_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    load_shedding_priority: LoadSheddingPriority = LoadSheddingPriority.MEDIUM


class DegradationRule(BaseModel):
    """A rule mapping a component failure to features to disable."""

    trigger_component_id: str
    disable_features: list[str] = Field(default_factory=list)
    target_level: DegradationLevel = DegradationLevel.REDUCED_FUNCTIONALITY
    description: str = ""


class BulkheadPartition(BaseModel):
    """Defines isolation boundaries between features."""

    name: str
    feature_names: list[str] = Field(default_factory=list)
    max_concurrent_requests: int = Field(default=100, ge=1)
    queue_size: int = Field(default=50, ge=0)
    timeout_seconds: float = Field(default=30.0, ge=0.0)


class DegradationPlan(BaseModel):
    """Complete degradation plan with features, rules, and partitions."""

    features: list[Feature] = Field(default_factory=list)
    rules: list[DegradationRule] = Field(default_factory=list)
    bulkhead_partitions: list[BulkheadPartition] = Field(default_factory=list)


class DegradationLevelAssessment(BaseModel):
    """Assessment at a specific degradation level."""

    level: DegradationLevel
    available_features: list[str] = Field(default_factory=list)
    disabled_features: list[str] = Field(default_factory=list)
    ux_impact_score: float = Field(default=0.0, ge=0.0, le=100.0)
    revenue_impact_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    sla_impact: str = "none"
    description: str = ""


class FallbackEvaluation(BaseModel):
    """Evaluation result for a feature's fallback strategy."""

    feature_name: str
    fallback_type: FallbackType
    effectiveness: float = Field(default=0.0, ge=0.0, le=100.0)
    staleness_risk: str = "low"
    data_consistency_risk: str = "low"
    recommendations: list[str] = Field(default_factory=list)


class CircuitBreakerCoordination(BaseModel):
    """Circuit breaker coordination state across services."""

    component_id: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    affected_features: list[str] = Field(default_factory=list)
    recommended_action: str = ""


class LoadSheddingAnalysis(BaseModel):
    """Analysis of load shedding strategy."""

    total_requests: int = 0
    shed_requests: int = 0
    shed_by_priority: dict[str, int] = Field(default_factory=dict)
    protected_requests: int = 0
    fairness_score: float = Field(default=100.0, ge=0.0, le=100.0)
    recommendations: list[str] = Field(default_factory=list)


class BulkheadEvaluation(BaseModel):
    """Evaluation of bulkhead pattern isolation."""

    partition_name: str
    status: BulkheadStatus = BulkheadStatus.HEALTHY
    isolation_effectiveness: float = Field(default=100.0, ge=0.0, le=100.0)
    blast_radius_contained: bool = True
    overflow_risk: float = Field(default=0.0, ge=0.0, le=100.0)
    recommendations: list[str] = Field(default_factory=list)


class CascadeDegradation(BaseModel):
    """Cascade degradation analysis result."""

    trigger_component_id: str
    cascade_chain: list[str] = Field(default_factory=list)
    affected_features: list[str] = Field(default_factory=list)
    final_level: DegradationLevel = DegradationLevel.FULL_SERVICE
    time_to_full_cascade_seconds: float = 0.0
    mitigation_points: list[str] = Field(default_factory=list)


class RecoveryStep(BaseModel):
    """A single step in a recovery sequence."""

    order: int
    feature_name: str
    component_ids: list[str] = Field(default_factory=list)
    estimated_time_seconds: float = 0.0
    dependencies_met: bool = True
    verification_steps: list[str] = Field(default_factory=list)


class RecoveryPlan(BaseModel):
    """Complete recovery sequence plan."""

    steps: list[RecoveryStep] = Field(default_factory=list)
    total_estimated_time_seconds: float = 0.0
    critical_path_length: int = 0
    recommendations: list[str] = Field(default_factory=list)


class SLAImpactAssessment(BaseModel):
    """SLA impact assessment at a degradation level."""

    level: DegradationLevel
    availability_impact_percent: float = 0.0
    latency_impact_ms: float = 0.0
    error_rate_increase_percent: float = 0.0
    sla_breach_risk: str = "low"
    estimated_credit_percent: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class DegradationReport(BaseModel):
    """Full degradation planning report."""

    timestamp: str = ""
    level_assessments: list[DegradationLevelAssessment] = Field(default_factory=list)
    fallback_evaluations: list[FallbackEvaluation] = Field(default_factory=list)
    circuit_breaker_states: list[CircuitBreakerCoordination] = Field(default_factory=list)
    load_shedding: LoadSheddingAnalysis | None = None
    bulkhead_evaluations: list[BulkheadEvaluation] = Field(default_factory=list)
    cascade_analyses: list[CascadeDegradation] = Field(default_factory=list)
    recovery_plan: RecoveryPlan | None = None
    sla_impacts: list[SLAImpactAssessment] = Field(default_factory=list)
    overall_readiness_score: float = Field(default=0.0, ge=0.0, le=100.0)
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_LEVEL_ORDER: dict[DegradationLevel, int] = {
    DegradationLevel.FULL_SERVICE: 0,
    DegradationLevel.REDUCED_FUNCTIONALITY: 1,
    DegradationLevel.READ_ONLY: 2,
    DegradationLevel.MAINTENANCE_MODE: 3,
    DegradationLevel.OFFLINE: 4,
}

_CRITICALITY_WEIGHT: dict[FeatureCriticality, float] = {
    FeatureCriticality.CRITICAL: 3.0,
    FeatureCriticality.IMPORTANT: 2.0,
    FeatureCriticality.NICE_TO_HAVE: 1.0,
}

_SHEDDING_ORDER: dict[LoadSheddingPriority, int] = {
    LoadSheddingPriority.BEST_EFFORT: 0,
    LoadSheddingPriority.LOW: 1,
    LoadSheddingPriority.MEDIUM: 2,
    LoadSheddingPriority.HIGH: 3,
    LoadSheddingPriority.CRITICAL: 4,
}


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp *value* between *lo* and *hi*."""
    return max(lo, min(hi, value))


def _level_severity(level: DegradationLevel) -> int:
    """Return severity rank for a degradation level (0 = best)."""
    return _LEVEL_ORDER.get(level, 0)


def _worse_level(a: DegradationLevel, b: DegradationLevel) -> DegradationLevel:
    """Return the worse (higher severity) of two degradation levels."""
    if _level_severity(a) >= _level_severity(b):
        return a
    return b


def _ux_impact_for_level(level: DegradationLevel) -> float:
    """Baseline user experience impact score for a degradation level."""
    mapping = {
        DegradationLevel.FULL_SERVICE: 0.0,
        DegradationLevel.REDUCED_FUNCTIONALITY: 25.0,
        DegradationLevel.READ_ONLY: 50.0,
        DegradationLevel.MAINTENANCE_MODE: 80.0,
        DegradationLevel.OFFLINE: 100.0,
    }
    return mapping.get(level, 0.0)


def _sla_impact_label(availability_loss: float) -> str:
    """Return SLA impact label based on availability loss percentage."""
    if availability_loss <= 0.0:
        return "none"
    if availability_loss < 0.1:
        return "minor"
    if availability_loss < 1.0:
        return "moderate"
    if availability_loss < 5.0:
        return "significant"
    return "critical"


def _sla_credit_estimate(availability_loss: float) -> float:
    """Estimate SLA credit percentage based on availability loss."""
    if availability_loss <= 0.0:
        return 0.0
    if availability_loss < 0.1:
        return 0.0
    if availability_loss < 1.0:
        return 10.0
    if availability_loss < 5.0:
        return 25.0
    return 50.0


def _fallback_effectiveness(fallback: FallbackType, ttl: float) -> float:
    """Score the effectiveness of a fallback strategy (0-100)."""
    base: dict[FallbackType, float] = {
        FallbackType.CACHE: 75.0,
        FallbackType.STATIC_CONTENT: 60.0,
        FallbackType.DEFAULT_VALUES: 50.0,
        FallbackType.QUEUE_FOR_LATER: 40.0,
        FallbackType.REDIRECT: 55.0,
        FallbackType.NONE: 0.0,
    }
    score = base.get(fallback, 0.0)

    # Staleness penalty for cache/static content
    if fallback in (FallbackType.CACHE, FallbackType.STATIC_CONTENT):
        if ttl > 3600:
            score *= 0.7
        elif ttl > 1800:
            score *= 0.85
    return round(_clamp(score), 1)


def _staleness_risk(fallback: FallbackType, ttl: float) -> str:
    """Assess staleness risk for a fallback strategy."""
    if fallback not in (FallbackType.CACHE, FallbackType.STATIC_CONTENT):
        return "none"
    if ttl <= 60:
        return "low"
    if ttl <= 300:
        return "low"
    if ttl <= 1800:
        return "medium"
    return "high"


def _data_consistency_risk(fallback: FallbackType) -> str:
    """Assess data consistency risk for a fallback strategy."""
    risk_map: dict[FallbackType, str] = {
        FallbackType.CACHE: "medium",
        FallbackType.STATIC_CONTENT: "low",
        FallbackType.DEFAULT_VALUES: "high",
        FallbackType.QUEUE_FOR_LATER: "medium",
        FallbackType.REDIRECT: "low",
        FallbackType.NONE: "none",
    }
    return risk_map.get(fallback, "none")


def _compute_features_for_level(
    features: list[Feature],
    level: DegradationLevel,
) -> tuple[list[str], list[str]]:
    """Determine available and disabled features for a degradation level.

    Returns (available, disabled) lists of feature names.
    """
    available: list[str] = []
    disabled: list[str] = []
    severity = _level_severity(level)

    for f in features:
        if severity == 0:
            available.append(f.name)
        elif severity == 4:
            disabled.append(f.name)
        elif f.criticality == FeatureCriticality.CRITICAL:
            if severity <= 2:
                available.append(f.name)
            else:
                disabled.append(f.name)
        elif f.criticality == FeatureCriticality.IMPORTANT:
            if severity <= 1:
                available.append(f.name)
            else:
                disabled.append(f.name)
        else:
            # nice_to_have: only available at full_service
            disabled.append(f.name)

    return available, disabled


def _compute_ux_impact(
    features: list[Feature],
    disabled_names: list[str],
    level: DegradationLevel,
) -> float:
    """Compute user experience impact score (0-100)."""
    if not features:
        return _ux_impact_for_level(level)

    total_weight = sum(
        f.user_impact_weight * _CRITICALITY_WEIGHT.get(f.criticality, 1.0)
        for f in features
    )
    if total_weight <= 0:
        return _ux_impact_for_level(level)

    disabled_weight = sum(
        f.user_impact_weight * _CRITICALITY_WEIGHT.get(f.criticality, 1.0)
        for f in features
        if f.name in disabled_names
    )
    raw = (disabled_weight / total_weight) * 100.0
    return round(_clamp(raw), 1)


def _compute_revenue_impact(
    features: list[Feature],
    disabled_names: list[str],
) -> float:
    """Compute revenue impact percentage from disabled features."""
    impact = 0.0
    for f in features:
        if f.name in disabled_names:
            impact += f.revenue_impact_percent
    return round(min(100.0, impact), 1)


def _resolve_feature_deps(
    feature_name: str,
    features: list[Feature],
    disabled: set[str],
    visited: set[str] | None = None,
) -> set[str]:
    """Recursively find all features disabled due to dependency chain."""
    if visited is None:
        visited = set()
    if feature_name in visited:
        return disabled
    visited.add(feature_name)

    {f.name: f for f in features}
    for f in features:
        if feature_name in f.depends_on_features and f.name not in disabled:
            disabled.add(f.name)
            _resolve_feature_deps(f.name, features, disabled, visited)
    return disabled


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class GracefulDegradationPlanner:
    """Stateless engine for graceful degradation planning and evaluation."""

    # -- degradation level assessment ------------------------------------

    def assess_degradation_levels(
        self,
        graph: InfraGraph,
        plan: DegradationPlan,
    ) -> list[DegradationLevelAssessment]:
        """Assess user/revenue impact at each degradation level."""
        assessments: list[DegradationLevelAssessment] = []

        for level in DegradationLevel:
            available, disabled = _compute_features_for_level(plan.features, level)
            ux = _compute_ux_impact(plan.features, disabled, level)
            revenue = _compute_revenue_impact(plan.features, disabled)
            severity = _level_severity(level)
            availability_loss = severity * 1.5
            sla = _sla_impact_label(availability_loss)

            desc_parts: list[str] = []
            if level == DegradationLevel.FULL_SERVICE:
                desc_parts.append("All features operational")
            elif level == DegradationLevel.OFFLINE:
                desc_parts.append("Service completely unavailable")
            else:
                desc_parts.append(
                    f"{len(disabled)} feature(s) disabled, "
                    f"{len(available)} available"
                )

            assessments.append(
                DegradationLevelAssessment(
                    level=level,
                    available_features=available,
                    disabled_features=disabled,
                    ux_impact_score=ux,
                    revenue_impact_percent=revenue,
                    sla_impact=sla,
                    description="; ".join(desc_parts),
                )
            )

        return assessments

    # -- feature criticality classification ------------------------------

    def classify_features(
        self,
        plan: DegradationPlan,
    ) -> dict[str, list[str]]:
        """Group features by criticality.

        Returns a dict with keys 'critical', 'important', 'nice_to_have'.
        """
        result: dict[str, list[str]] = {
            "critical": [],
            "important": [],
            "nice_to_have": [],
        }
        for f in plan.features:
            result[f.criticality.value].append(f.name)
        return result

    # -- dependency-based degradation planning ---------------------------

    def plan_degradation_for_failure(
        self,
        graph: InfraGraph,
        plan: DegradationPlan,
        failed_component_id: str,
    ) -> DegradationLevelAssessment:
        """Plan degradation when a specific component fails.

        Uses degradation rules and dependency analysis to determine which
        features to disable and the resulting degradation level.
        """
        disabled_features: set[str] = set()
        worst_level = DegradationLevel.FULL_SERVICE

        # Apply explicit degradation rules
        for rule in plan.rules:
            if rule.trigger_component_id == failed_component_id:
                disabled_features.update(rule.disable_features)
                worst_level = _worse_level(worst_level, rule.target_level)

        # Check features directly depending on the failed component
        for feature in plan.features:
            if failed_component_id in feature.component_ids:
                disabled_features.add(feature.name)

        # Resolve feature dependency chains
        expanded: set[str] = set(disabled_features)
        for fname in list(disabled_features):
            _resolve_feature_deps(fname, plan.features, expanded)
        disabled_features = expanded

        # Determine severity based on disabled features' criticality
        for feature in plan.features:
            if feature.name in disabled_features:
                if feature.criticality == FeatureCriticality.CRITICAL:
                    worst_level = _worse_level(
                        worst_level, DegradationLevel.MAINTENANCE_MODE
                    )
                elif feature.criticality == FeatureCriticality.IMPORTANT:
                    worst_level = _worse_level(
                        worst_level, DegradationLevel.REDUCED_FUNCTIONALITY
                    )

        # Also consider graph-based transitive failures
        affected_ids = graph.get_all_affected(failed_component_id)
        for feature in plan.features:
            for cid in feature.component_ids:
                if cid in affected_ids:
                    disabled_features.add(feature.name)

        all_names = {f.name for f in plan.features}
        available = sorted(all_names - disabled_features)
        disabled_list = sorted(disabled_features)
        ux = _compute_ux_impact(plan.features, disabled_list, worst_level)
        revenue = _compute_revenue_impact(plan.features, disabled_list)
        sev = _level_severity(worst_level)
        sla = _sla_impact_label(sev * 1.5)

        return DegradationLevelAssessment(
            level=worst_level,
            available_features=available,
            disabled_features=disabled_list,
            ux_impact_score=ux,
            revenue_impact_percent=revenue,
            sla_impact=sla,
            description=f"Degradation due to failure of component '{failed_component_id}'",
        )

    # -- fallback strategy evaluation ------------------------------------

    def evaluate_fallbacks(
        self,
        plan: DegradationPlan,
    ) -> list[FallbackEvaluation]:
        """Evaluate fallback strategies for all features."""
        evaluations: list[FallbackEvaluation] = []

        for feature in plan.features:
            effectiveness = _fallback_effectiveness(
                feature.fallback, feature.fallback_ttl_seconds
            )
            stale = _staleness_risk(feature.fallback, feature.fallback_ttl_seconds)
            consistency = _data_consistency_risk(feature.fallback)

            recs: list[str] = []
            if feature.fallback == FallbackType.NONE:
                if feature.criticality == FeatureCriticality.CRITICAL:
                    recs.append(
                        f"Critical feature '{feature.name}' has no fallback; "
                        "add a cache or static content fallback"
                    )
                elif feature.criticality == FeatureCriticality.IMPORTANT:
                    recs.append(
                        f"Important feature '{feature.name}' has no fallback; "
                        "consider adding default values or a cache fallback"
                    )

            if stale == "high":
                recs.append(
                    f"Feature '{feature.name}' fallback has high staleness risk; "
                    "reduce TTL or add cache invalidation"
                )

            if consistency == "high":
                recs.append(
                    f"Feature '{feature.name}' fallback has high data consistency risk; "
                    "consider using a queue-for-later strategy instead"
                )

            evaluations.append(
                FallbackEvaluation(
                    feature_name=feature.name,
                    fallback_type=feature.fallback,
                    effectiveness=effectiveness,
                    staleness_risk=stale,
                    data_consistency_risk=consistency,
                    recommendations=recs,
                )
            )

        return evaluations

    # -- circuit breaker coordination ------------------------------------

    def coordinate_circuit_breakers(
        self,
        graph: InfraGraph,
        plan: DegradationPlan,
    ) -> list[CircuitBreakerCoordination]:
        """Analyze circuit breaker state coordination across components."""
        results: list[CircuitBreakerCoordination] = []

        for comp_id, comp in graph.components.items():
            # Determine circuit state from component health
            if comp.health == HealthStatus.DOWN:
                state = CircuitState.OPEN
            elif comp.health == HealthStatus.DEGRADED:
                state = CircuitState.HALF_OPEN
            else:
                state = CircuitState.CLOSED

            # Count failures based on health
            failure_count = 0
            if comp.health == HealthStatus.DOWN:
                failure_count = 5
            elif comp.health == HealthStatus.DEGRADED:
                failure_count = 2
            elif comp.health == HealthStatus.OVERLOADED:
                failure_count = 3

            # Find affected features
            affected: list[str] = []
            for feature in plan.features:
                if comp_id in feature.component_ids:
                    affected.append(feature.name)

            # Determine recommended action
            if state == CircuitState.OPEN:
                action = f"Circuit OPEN for '{comp_id}'; route traffic to fallbacks"
            elif state == CircuitState.HALF_OPEN:
                action = (
                    f"Circuit HALF_OPEN for '{comp_id}'; "
                    "allow limited probe requests to test recovery"
                )
            else:
                action = f"Circuit CLOSED for '{comp_id}'; normal operation"

            results.append(
                CircuitBreakerCoordination(
                    component_id=comp_id,
                    state=state,
                    failure_count=failure_count,
                    affected_features=affected,
                    recommended_action=action,
                )
            )

        return results

    # -- load shedding strategy analysis ---------------------------------

    def analyze_load_shedding(
        self,
        plan: DegradationPlan,
        total_requests: int,
        capacity_percent: float,
    ) -> LoadSheddingAnalysis:
        """Analyze priority-based request dropping under load.

        Args:
            plan: The degradation plan with feature priorities.
            total_requests: Total incoming requests.
            capacity_percent: Current capacity utilization (0-100).
        """
        if capacity_percent <= 80.0 or total_requests <= 0:
            return LoadSheddingAnalysis(
                total_requests=total_requests,
                shed_requests=0,
                shed_by_priority={},
                protected_requests=total_requests,
                fairness_score=100.0,
                recommendations=[],
            )

        # Determine how many requests to shed
        overload_factor = max(0.0, (capacity_percent - 80.0) / 20.0)
        overload_factor = min(1.0, overload_factor)
        target_shed = int(total_requests * overload_factor * 0.5)

        # Distribute requests by priority
        priority_counts: dict[str, int] = {}
        for p in LoadSheddingPriority:
            priority_counts[p.value] = 0

        for f in plan.features:
            priority_counts[f.load_shedding_priority.value] += 1

        if not plan.features:
            # Distribute evenly if no features defined
            per_priority = total_requests // 5
            for p in LoadSheddingPriority:
                priority_counts[p.value] = per_priority
            priority_counts[LoadSheddingPriority.MEDIUM.value] += (
                total_requests - per_priority * 5
            )

        # Shed from lowest priority first
        shed_by_priority: dict[str, int] = {}
        remaining_to_shed = target_shed
        sorted_priorities = sorted(
            LoadSheddingPriority, key=lambda p: _SHEDDING_ORDER[p]
        )

        total_feature_count = max(1, len(plan.features))
        for priority in sorted_priorities:
            if remaining_to_shed <= 0:
                break
            pcount = priority_counts.get(priority.value, 0)
            proportion = pcount / total_feature_count if total_feature_count > 0 else 0.2
            requests_at_priority = int(total_requests * max(proportion, 0.1))
            can_shed = min(remaining_to_shed, requests_at_priority)
            if can_shed > 0:
                shed_by_priority[priority.value] = can_shed
                remaining_to_shed -= can_shed

        total_shed = sum(shed_by_priority.values())
        protected = total_requests - total_shed

        # Fairness: higher if shedding is concentrated on low priority
        high_shed = shed_by_priority.get("critical", 0) + shed_by_priority.get("high", 0)
        shed_by_priority.get("best_effort", 0) + shed_by_priority.get("low", 0)
        if total_shed > 0:
            fairness = _clamp(100.0 - (high_shed / total_shed) * 100.0)
        else:
            fairness = 100.0

        recs: list[str] = []
        if high_shed > 0:
            recs.append(
                "High-priority requests are being shed; "
                "consider increasing capacity or adjusting priority thresholds"
            )
        if capacity_percent > 95.0:
            recs.append(
                "System is critically overloaded; "
                "enable emergency load shedding and scale up immediately"
            )
        if total_shed > total_requests * 0.3:
            recs.append(
                f"Over 30% of requests are being shed ({total_shed}/{total_requests}); "
                "this indicates a severe capacity deficit"
            )

        return LoadSheddingAnalysis(
            total_requests=total_requests,
            shed_requests=total_shed,
            shed_by_priority=shed_by_priority,
            protected_requests=protected,
            fairness_score=round(fairness, 1),
            recommendations=recs,
        )

    # -- bulkhead pattern evaluation -------------------------------------

    def evaluate_bulkheads(
        self,
        graph: InfraGraph,
        plan: DegradationPlan,
        current_load: dict[str, float] | None = None,
    ) -> list[BulkheadEvaluation]:
        """Evaluate isolation effectiveness of bulkhead partitions."""
        evaluations: list[BulkheadEvaluation] = []
        load = current_load or {}

        for partition in plan.bulkhead_partitions:
            # Determine status based on load
            partition_load = 0.0
            feature_count = len(partition.feature_names)
            for fname in partition.feature_names:
                partition_load += load.get(fname, 0.0)

            avg_load = partition_load / max(1, feature_count)
            utilization = (avg_load / partition.max_concurrent_requests) * 100.0 if partition.max_concurrent_requests > 0 else 0.0

            if utilization > 100.0:
                status = BulkheadStatus.FAILING
            elif utilization > 80.0:
                status = BulkheadStatus.STRESSED
            elif utilization > 0.0:
                status = BulkheadStatus.HEALTHY
            else:
                status = BulkheadStatus.HEALTHY

            # Check isolation: are features in different partitions sharing components?
            partition_component_ids: set[str] = set()
            for fname in partition.feature_names:
                for f in plan.features:
                    if f.name == fname:
                        partition_component_ids.update(f.component_ids)

            shared_count = 0
            for other_partition in plan.bulkhead_partitions:
                if other_partition.name == partition.name:
                    continue
                for fname in other_partition.feature_names:
                    for f in plan.features:
                        if f.name == fname:
                            shared = partition_component_ids & set(f.component_ids)
                            shared_count += len(shared)

            isolation = 100.0
            if shared_count > 0:
                isolation = max(0.0, 100.0 - shared_count * 20.0)
            blast_contained = isolation >= 50.0

            overflow_risk = 0.0
            if partition.queue_size > 0 and utilization > 70.0:
                overflow_risk = min(100.0, (utilization - 70.0) * 3.33)

            recs: list[str] = []
            if status == BulkheadStatus.FAILING:
                recs.append(
                    f"Partition '{partition.name}' is failing; "
                    "increase max_concurrent_requests or shed load"
                )
            if status == BulkheadStatus.STRESSED:
                recs.append(
                    f"Partition '{partition.name}' is under stress; "
                    "monitor closely and prepare to shed load"
                )
            if not blast_contained:
                recs.append(
                    f"Partition '{partition.name}' has poor isolation (shared components); "
                    "separate shared components into dedicated instances"
                )
            if overflow_risk > 50.0:
                recs.append(
                    f"Partition '{partition.name}' has high overflow risk ({overflow_risk:.0f}%); "
                    "increase queue size or enable backpressure"
                )

            evaluations.append(
                BulkheadEvaluation(
                    partition_name=partition.name,
                    status=status,
                    isolation_effectiveness=round(_clamp(isolation), 1),
                    blast_radius_contained=blast_contained,
                    overflow_risk=round(_clamp(overflow_risk), 1),
                    recommendations=recs,
                )
            )

        return evaluations

    # -- degradation cascade analysis ------------------------------------

    def analyze_cascade(
        self,
        graph: InfraGraph,
        plan: DegradationPlan,
        trigger_component_id: str,
    ) -> CascadeDegradation:
        """Analyze how degradation cascades when a component fails."""
        affected_ids = graph.get_all_affected(trigger_component_id)
        cascade_chain = [trigger_component_id] + sorted(affected_ids)

        affected_features: set[str] = set()
        for feature in plan.features:
            for cid in feature.component_ids:
                if cid == trigger_component_id or cid in affected_ids:
                    affected_features.add(feature.name)

        # Also apply explicit rules
        for rule in plan.rules:
            if rule.trigger_component_id == trigger_component_id:
                affected_features.update(rule.disable_features)

        # Resolve dependency chains among features
        expanded: set[str] = set(affected_features)
        for fname in list(affected_features):
            _resolve_feature_deps(fname, plan.features, expanded)
        affected_features = expanded

        # Determine final degradation level
        final_level = DegradationLevel.FULL_SERVICE
        for feature in plan.features:
            if feature.name in affected_features:
                if feature.criticality == FeatureCriticality.CRITICAL:
                    final_level = _worse_level(
                        final_level, DegradationLevel.MAINTENANCE_MODE
                    )
                elif feature.criticality == FeatureCriticality.IMPORTANT:
                    final_level = _worse_level(
                        final_level, DegradationLevel.REDUCED_FUNCTIONALITY
                    )

        # Estimate cascade time based on chain length
        chain_len = len(cascade_chain)
        time_estimate = chain_len * 5.0  # 5 seconds per hop (simplified)

        # Identify mitigation points (components with circuit breakers)
        mitigation_points: list[str] = []
        for cid in cascade_chain:
            comp = graph.get_component(cid)
            if comp is not None:
                edge_data = graph.get_dependency_edge(trigger_component_id, cid)
                if edge_data and edge_data.circuit_breaker.enabled:
                    mitigation_points.append(cid)
                if comp.failover.enabled:
                    mitigation_points.append(cid)
                if comp.replicas > 1:
                    mitigation_points.append(cid)

        # Deduplicate
        seen: set[str] = set()
        unique_mitigation: list[str] = []
        for mp in mitigation_points:
            if mp not in seen:
                seen.add(mp)
                unique_mitigation.append(mp)

        return CascadeDegradation(
            trigger_component_id=trigger_component_id,
            cascade_chain=cascade_chain,
            affected_features=sorted(affected_features),
            final_level=final_level,
            time_to_full_cascade_seconds=time_estimate,
            mitigation_points=unique_mitigation,
        )

    # -- recovery sequence planning --------------------------------------

    def plan_recovery(
        self,
        graph: InfraGraph,
        plan: DegradationPlan,
    ) -> RecoveryPlan:
        """Plan the recovery sequence: which features to restore first.

        Features are ordered by criticality (critical first), then by
        dependency resolution (dependencies restored before dependents).
        """
        # Build feature dependency graph
        feature_map = {f.name: f for f in plan.features}
        ordered: list[str] = []
        visited: set[str] = set()

        def _topo_visit(fname: str) -> None:
            if fname in visited:
                return
            visited.add(fname)
            f = feature_map.get(fname)
            if f:
                for dep in f.depends_on_features:
                    if dep in feature_map:
                        _topo_visit(dep)
            ordered.append(fname)

        # Process by criticality: critical -> important -> nice_to_have
        for crit in [
            FeatureCriticality.CRITICAL,
            FeatureCriticality.IMPORTANT,
            FeatureCriticality.NICE_TO_HAVE,
        ]:
            for f in plan.features:
                if f.criticality == crit:
                    _topo_visit(f.name)

        steps: list[RecoveryStep] = []
        for i, fname in enumerate(ordered, 1):
            f = feature_map.get(fname)
            if f is None:
                continue

            deps_met = all(
                dep in [s.feature_name for s in steps]
                for dep in f.depends_on_features
                if dep in feature_map
            )

            # Estimate recovery time based on component types
            est_time = 30.0  # base
            for cid in f.component_ids:
                comp = graph.get_component(cid)
                if comp:
                    if comp.type == ComponentType.DATABASE:
                        est_time = max(est_time, 120.0)
                    elif comp.type == ComponentType.CACHE:
                        est_time = max(est_time, 60.0)
                    elif comp.type == ComponentType.QUEUE:
                        est_time = max(est_time, 45.0)

            verification: list[str] = [
                f"Verify {fname} is responding to health checks",
                f"Confirm {fname} is processing requests correctly",
            ]
            if f.criticality == FeatureCriticality.CRITICAL:
                verification.append(f"Run smoke tests for {fname}")

            steps.append(
                RecoveryStep(
                    order=i,
                    feature_name=fname,
                    component_ids=f.component_ids,
                    estimated_time_seconds=est_time,
                    dependencies_met=deps_met,
                    verification_steps=verification,
                )
            )

        total_time = sum(s.estimated_time_seconds for s in steps)

        # Critical path = longest chain of dependent features
        critical_path_len = 0
        for f in plan.features:
            chain_len = _count_dep_chain(f.name, feature_map, set())
            critical_path_len = max(critical_path_len, chain_len)

        recs: list[str] = []
        if total_time > 600:
            recs.append(
                "Total recovery time exceeds 10 minutes; "
                "consider parallelizing independent feature recoveries"
            )
        if critical_path_len > 3:
            recs.append(
                f"Critical dependency chain is {critical_path_len} deep; "
                "reduce coupling between features for faster recovery"
            )

        critical_features = [
            f.name for f in plan.features
            if f.criticality == FeatureCriticality.CRITICAL
        ]
        if critical_features:
            recs.append(
                f"Prioritize recovery of critical features: "
                f"{', '.join(critical_features)}"
            )

        return RecoveryPlan(
            steps=steps,
            total_estimated_time_seconds=round(total_time, 1),
            critical_path_length=critical_path_len,
            recommendations=recs,
        )

    # -- SLA impact assessment -------------------------------------------

    def assess_sla_impact(
        self,
        graph: InfraGraph,
        plan: DegradationPlan,
    ) -> list[SLAImpactAssessment]:
        """Assess SLA impact at each degradation level."""
        assessments: list[SLAImpactAssessment] = []

        for level in DegradationLevel:
            severity = _level_severity(level)
            availability_loss = severity * 1.5
            latency_impact = severity * 50.0
            error_rate = severity * 2.5
            breach_risk = _sla_impact_label(availability_loss)
            credit = _sla_credit_estimate(availability_loss)

            recs: list[str] = []
            if breach_risk in ("significant", "critical"):
                recs.append(
                    f"SLA breach risk is {breach_risk} at {level.value}; "
                    "prepare customer communications and credit processes"
                )
            if availability_loss > 1.0:
                recs.append(
                    f"Availability loss of {availability_loss:.1f}% at {level.value}; "
                    "activate incident response procedures"
                )
            if error_rate > 5.0:
                recs.append(
                    f"Error rate increase of {error_rate:.1f}% at {level.value}; "
                    "enable error page fallbacks"
                )

            assessments.append(
                SLAImpactAssessment(
                    level=level,
                    availability_impact_percent=round(availability_loss, 1),
                    latency_impact_ms=round(latency_impact, 1),
                    error_rate_increase_percent=round(error_rate, 1),
                    sla_breach_risk=breach_risk,
                    estimated_credit_percent=credit,
                    recommendations=recs,
                )
            )

        return assessments

    # -- full report generation ------------------------------------------

    def generate_report(
        self,
        graph: InfraGraph,
        plan: DegradationPlan,
        total_requests: int = 1000,
        capacity_percent: float = 70.0,
        current_load: dict[str, float] | None = None,
    ) -> DegradationReport:
        """Generate a comprehensive degradation planning report."""
        ts = datetime.now(timezone.utc).isoformat()

        level_assessments = self.assess_degradation_levels(graph, plan)
        fallback_evals = self.evaluate_fallbacks(plan)
        cb_states = self.coordinate_circuit_breakers(graph, plan)
        load_shedding = self.analyze_load_shedding(
            plan, total_requests, capacity_percent
        )
        bulkhead_evals = self.evaluate_bulkheads(graph, plan, current_load)

        # Cascade analysis for all components in the graph
        cascade_analyses: list[CascadeDegradation] = []
        for comp_id in graph.components:
            cascade = self.analyze_cascade(graph, plan, comp_id)
            if len(cascade.affected_features) > 0:
                cascade_analyses.append(cascade)

        recovery = self.plan_recovery(graph, plan)
        sla_impacts = self.assess_sla_impact(graph, plan)

        # Compute overall readiness score
        readiness = self._compute_readiness_score(
            plan, fallback_evals, bulkhead_evals, cb_states, cascade_analyses
        )

        # Aggregate recommendations
        all_recs: list[str] = []
        for fb in fallback_evals:
            all_recs.extend(fb.recommendations)
        for bh in bulkhead_evals:
            all_recs.extend(bh.recommendations)
        all_recs.extend(load_shedding.recommendations)
        all_recs.extend(recovery.recommendations)
        for sla in sla_impacts:
            all_recs.extend(sla.recommendations)

        # Deduplicate
        seen: set[str] = set()
        unique_recs: list[str] = []
        for r in all_recs:
            if r not in seen:
                seen.add(r)
                unique_recs.append(r)

        return DegradationReport(
            timestamp=ts,
            level_assessments=level_assessments,
            fallback_evaluations=fallback_evals,
            circuit_breaker_states=cb_states,
            load_shedding=load_shedding,
            bulkhead_evaluations=bulkhead_evals,
            cascade_analyses=cascade_analyses,
            recovery_plan=recovery,
            sla_impacts=sla_impacts,
            overall_readiness_score=round(readiness, 1),
            recommendations=unique_recs,
        )

    # -- readiness score -------------------------------------------------

    def _compute_readiness_score(
        self,
        plan: DegradationPlan,
        fallback_evals: list[FallbackEvaluation],
        bulkhead_evals: list[BulkheadEvaluation],
        cb_states: list[CircuitBreakerCoordination],
        cascade_analyses: list[CascadeDegradation],
    ) -> float:
        """Compute overall degradation readiness score (0-100).

        Factors:
        - Fallback coverage (features with fallbacks)
        - Bulkhead isolation effectiveness
        - Circuit breaker coordination
        - Cascade depth / mitigation coverage
        """
        score = 0.0

        # --- Fallback coverage (0-30) ---
        if plan.features:
            with_fallback = sum(
                1 for f in plan.features if f.fallback != FallbackType.NONE
            )
            fallback_ratio = with_fallback / len(plan.features)
            fallback_score = fallback_ratio * 30.0

            # Bonus for effective fallbacks
            if fallback_evals:
                avg_eff = sum(e.effectiveness for e in fallback_evals) / len(fallback_evals)
                fallback_score *= (0.5 + avg_eff / 200.0)
        else:
            fallback_score = 15.0  # neutral
        score += fallback_score

        # --- Bulkhead isolation (0-25) ---
        if bulkhead_evals:
            avg_isolation = sum(
                e.isolation_effectiveness for e in bulkhead_evals
            ) / len(bulkhead_evals)
            bulkhead_score = (avg_isolation / 100.0) * 25.0
        elif plan.bulkhead_partitions:
            bulkhead_score = 25.0
        else:
            bulkhead_score = 0.0
        score += bulkhead_score

        # --- Circuit breaker coverage (0-25) ---
        if cb_states:
            closed_ratio = sum(
                1 for cb in cb_states if cb.state == CircuitState.CLOSED
            ) / len(cb_states)
            cb_score = closed_ratio * 25.0
        else:
            cb_score = 12.5
        score += cb_score

        # --- Cascade mitigation (0-20) ---
        if cascade_analyses:
            mitigated = sum(
                1 for c in cascade_analyses if len(c.mitigation_points) > 0
            )
            cascade_ratio = mitigated / len(cascade_analyses) if cascade_analyses else 0
            cascade_score = cascade_ratio * 20.0
        else:
            cascade_score = 10.0
        score += cascade_score

        return _clamp(score)

    # -- validate plan ---------------------------------------------------

    def validate_plan(
        self,
        graph: InfraGraph,
        plan: DegradationPlan,
    ) -> list[str]:
        """Validate a degradation plan and return a list of issues.

        Returns an empty list if the plan is valid.
        """
        issues: list[str] = []

        # Check features reference valid components
        for feature in plan.features:
            for cid in feature.component_ids:
                if graph.get_component(cid) is None:
                    issues.append(
                        f"Feature '{feature.name}' references unknown "
                        f"component '{cid}'"
                    )

        # Check feature dependencies exist
        feature_names = {f.name for f in plan.features}
        for feature in plan.features:
            for dep in feature.depends_on_features:
                if dep not in feature_names:
                    issues.append(
                        f"Feature '{feature.name}' depends on unknown "
                        f"feature '{dep}'"
                    )

        # Check rules reference valid components
        for rule in plan.rules:
            if graph.get_component(rule.trigger_component_id) is None:
                issues.append(
                    f"Degradation rule references unknown component "
                    f"'{rule.trigger_component_id}'"
                )
            for fname in rule.disable_features:
                if fname not in feature_names:
                    issues.append(
                        f"Degradation rule disables unknown feature '{fname}'"
                    )

        # Check bulkhead partition features exist
        for partition in plan.bulkhead_partitions:
            for fname in partition.feature_names:
                if fname not in feature_names:
                    issues.append(
                        f"Bulkhead partition '{partition.name}' references "
                        f"unknown feature '{fname}'"
                    )

        # Check critical features have fallbacks
        for feature in plan.features:
            if (
                feature.criticality == FeatureCriticality.CRITICAL
                and feature.fallback == FallbackType.NONE
            ):
                issues.append(
                    f"Critical feature '{feature.name}' has no fallback strategy"
                )

        # Check for circular feature dependencies
        for feature in plan.features:
            if _has_circular_dep(feature.name, plan.features, set()):
                issues.append(
                    f"Feature '{feature.name}' has a circular dependency"
                )
                break  # one circular warning is enough

        return issues


# ---------------------------------------------------------------------------
# Module-level helpers (used by engine but also testable)
# ---------------------------------------------------------------------------


def _count_dep_chain(
    fname: str,
    feature_map: dict[str, Feature],
    visited: set[str],
) -> int:
    """Count the length of the longest dependency chain from *fname*."""
    if fname in visited:
        return 0
    visited.add(fname)
    f = feature_map.get(fname)
    if f is None or not f.depends_on_features:
        return 1
    max_child = 0
    for dep in f.depends_on_features:
        child_len = _count_dep_chain(dep, feature_map, set(visited))
        max_child = max(max_child, child_len)
    return 1 + max_child


def _has_circular_dep(
    fname: str,
    features: list[Feature],
    visited: set[str],
) -> bool:
    """Detect circular dependencies among features."""
    if fname in visited:
        return True
    visited.add(fname)
    feature_map = {f.name: f for f in features}
    f = feature_map.get(fname)
    if f is None:
        return False
    for dep in f.depends_on_features:
        if _has_circular_dep(dep, features, set(visited)):
            return True
    return False
