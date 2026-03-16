"""Feature Flag Interaction Simulator.

Simulates how feature flag combinations interact with infrastructure
resilience.  Detects conflicts, dependency chains, resource contention,
and kill-switch coverage gaps.  Provides rollout simulation and
failure-mode analysis so operators can safely manage flag state across
a distributed system.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_ROLLOUT_STAGES = 5
_RESOURCE_OVERHEAD_THRESHOLD = 0.20  # 20% overhead is risky
_CRITICAL_RESOURCE_THRESHOLD = 0.50  # 50% overhead is dangerous
_ROLLBACK_SAFE_THRESHOLD = 30.0  # seconds
_ROLLBACK_RISKY_THRESHOLD = 120.0  # seconds
_RESILIENCE_POSITIVE_CAP = 15.0
_RESILIENCE_NEGATIVE_CAP = -30.0


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class FlagType(str, Enum):
    """Kind of feature flag."""

    RELEASE = "release"
    EXPERIMENT = "experiment"
    OPS_TOGGLE = "ops_toggle"
    KILL_SWITCH = "kill_switch"
    PERMISSION = "permission"
    GRADUAL_ROLLOUT = "gradual_rollout"


class FlagState(str, Enum):
    """Current state of a feature flag."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    PERCENTAGE_ROLLOUT = "percentage_rollout"
    USER_TARGETED = "user_targeted"
    CANARY = "canary"


class FlagInteractionType(str, Enum):
    """How two flags interact."""

    CONFLICT = "conflict"
    DEPENDENCY = "dependency"
    MUTUAL_EXCLUSION = "mutual_exclusion"
    CASCADE_ENABLE = "cascade_enable"
    CASCADE_DISABLE = "cascade_disable"
    RESOURCE_CONTENTION = "resource_contention"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


class FeatureFlag(BaseModel):
    """A single feature flag definition."""

    id: str
    name: str
    flag_type: FlagType
    state: FlagState
    rollout_percentage: float = Field(default=0.0, ge=0.0, le=100.0)
    resource_impact: dict[str, float] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    kill_switch_for: list[str] = Field(default_factory=list)


class FlagInteraction(BaseModel):
    """A detected interaction between two flags."""

    flag_a_id: str
    flag_b_id: str
    interaction_type: FlagInteractionType
    severity: str  # critical / high / medium / low
    description: str
    resolution: str


class FlagResilienceImpact(BaseModel):
    """How a single flag affects infrastructure resilience."""

    flag_id: str
    resilience_delta: float
    affected_components: list[str] = Field(default_factory=list)
    resource_overhead: dict[str, float] = Field(default_factory=dict)
    rollback_safety: str  # safe / risky / dangerous
    rollback_time_seconds: float


class RolloutStageResult(BaseModel):
    """Result of one rollout stage."""

    stage: int
    percentage: float
    healthy: bool
    affected_components: list[str] = Field(default_factory=list)
    resource_usage: dict[str, float] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FlagFailureResult(BaseModel):
    """What happens when a flag service goes down."""

    flag_id: str
    affected_flags: list[str] = Field(default_factory=list)
    affected_components: list[str] = Field(default_factory=list)
    severity: str  # critical / high / medium / low
    fallback_behaviour: str
    estimated_impact_percent: float
    recommendations: list[str] = Field(default_factory=list)


class RolloutStrategy(BaseModel):
    """Recommended rollout plan."""

    flag_id: str
    recommended_stages: int
    stage_percentages: list[float] = Field(default_factory=list)
    estimated_duration_minutes: float
    risk_level: str  # low / medium / high
    prerequisites: list[str] = Field(default_factory=list)
    rollback_plan: str
    monitoring_points: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class FeatureFlagInteractionEngine:
    """Stateless engine that analyses feature-flag interactions and their
    effect on infrastructure resilience."""

    # -- public API ---------------------------------------------------------

    def detect_interactions(self, flags: list[FeatureFlag]) -> list[FlagInteraction]:
        """Find conflicts, dependencies, and resource contention among *flags*."""
        interactions: list[FlagInteraction] = []
        flag_map = {f.id: f for f in flags}

        for i, fa in enumerate(flags):
            for fb in flags[i + 1 :]:
                interactions.extend(self._check_pair(fa, fb, flag_map))

        return interactions

    def analyze_resilience_impact(
        self,
        graph: InfraGraph,
        flags: list[FeatureFlag],
    ) -> list[FlagResilienceImpact]:
        """Compute how each flag affects the resilience of *graph*."""
        results: list[FlagResilienceImpact] = []
        component_ids = set(graph.components.keys())

        for flag in flags:
            affected = self._flag_affected_components(flag, component_ids, graph)
            overhead = self._compute_resource_overhead(flag, affected, graph)
            delta = self._compute_resilience_delta(flag, affected, graph)
            rb_time = self._estimate_rollback_time(flag, affected, graph)
            rb_safety = self._classify_rollback_safety(rb_time, overhead)

            results.append(
                FlagResilienceImpact(
                    flag_id=flag.id,
                    resilience_delta=delta,
                    affected_components=sorted(affected),
                    resource_overhead=overhead,
                    rollback_safety=rb_safety,
                    rollback_time_seconds=rb_time,
                )
            )

        return results

    def simulate_rollout(
        self,
        graph: InfraGraph,
        flag: FeatureFlag,
        stages: int = _DEFAULT_ROLLOUT_STAGES,
    ) -> list[RolloutStageResult]:
        """Simulate a gradual rollout of *flag* across *stages*."""
        if stages < 1:
            stages = 1
        component_ids = set(graph.components.keys())
        affected = self._flag_affected_components(flag, component_ids, graph)
        results: list[RolloutStageResult] = []

        for s in range(1, stages + 1):
            pct = round(s / stages * 100, 2)
            scale = pct / 100.0
            usage: dict[str, float] = {}
            errors: list[str] = []
            healthy = True

            for key, val in flag.resource_impact.items():
                scaled = val * scale
                usage[key] = round(scaled, 4)
                if abs(scaled) >= _CRITICAL_RESOURCE_THRESHOLD:
                    healthy = False
                    errors.append(
                        f"Resource {key} impact {scaled:.1%} exceeds critical threshold"
                    )
                elif abs(scaled) >= _RESOURCE_OVERHEAD_THRESHOLD:
                    errors.append(
                        f"Resource {key} impact {scaled:.1%} exceeds warning threshold"
                    )

            # Check component health at this rollout %
            stage_affected = self._stage_affected(affected, scale)
            for cid in stage_affected:
                comp = graph.get_component(cid)
                if comp and comp.health == HealthStatus.DOWN:
                    healthy = False
                    errors.append(f"Component {cid} is DOWN")

            results.append(
                RolloutStageResult(
                    stage=s,
                    percentage=pct,
                    healthy=healthy,
                    affected_components=sorted(stage_affected),
                    resource_usage=usage,
                    errors=errors,
                )
            )

        return results

    def find_kill_switch_gaps(
        self,
        graph: InfraGraph,
        flags: list[FeatureFlag],
    ) -> list[str]:
        """Return component IDs that have no kill switch covering them."""
        covered: set[str] = set()
        for flag in flags:
            if flag.flag_type == FlagType.KILL_SWITCH:
                covered.update(flag.kill_switch_for)

        all_ids = set(graph.components.keys())
        return sorted(all_ids - covered)

    def simulate_flag_failure(
        self,
        graph: InfraGraph,
        flag_id: str,
        flags: list[FeatureFlag],
    ) -> FlagFailureResult:
        """Simulate a flag-service failure for *flag_id*."""
        flag_map = {f.id: f for f in flags}
        target = flag_map.get(flag_id)

        if target is None:
            return FlagFailureResult(
                flag_id=flag_id,
                severity="low",
                fallback_behaviour="Flag not found; no impact",
                estimated_impact_percent=0.0,
            )

        # Find dependent flags
        dependent_flags: list[str] = []
        for f in flags:
            if flag_id in f.dependencies:
                dependent_flags.append(f.id)

        # Affected components
        component_ids = set(graph.components.keys())
        directly_affected = self._flag_affected_components(target, component_ids, graph)

        # Cascade through dependent flags
        all_affected: set[str] = set(directly_affected)
        for dep_id in dependent_flags:
            dep_flag = flag_map[dep_id]
            dep_affected = self._flag_affected_components(dep_flag, component_ids, graph)
            all_affected.update(dep_affected)

        total = len(component_ids) if component_ids else 1
        impact_pct = round(len(all_affected) / total * 100, 2)

        severity = self._classify_failure_severity(
            target, dependent_flags, impact_pct
        )
        fallback = self._determine_fallback(target)
        recommendations = self._failure_recommendations(target, dependent_flags)

        return FlagFailureResult(
            flag_id=flag_id,
            affected_flags=sorted(dependent_flags),
            affected_components=sorted(all_affected),
            severity=severity,
            fallback_behaviour=fallback,
            estimated_impact_percent=impact_pct,
            recommendations=recommendations,
        )

    def recommend_rollout_strategy(
        self,
        graph: InfraGraph,
        flag: FeatureFlag,
    ) -> RolloutStrategy:
        """Produce an optimal rollout plan for *flag*."""
        component_ids = set(graph.components.keys())
        affected = self._flag_affected_components(flag, component_ids, graph)
        risk = self._assess_rollout_risk(flag, affected, graph)

        if risk == "high":
            stages = 7
            percentages = [1.0, 5.0, 10.0, 25.0, 50.0, 75.0, 100.0]
            duration = 7 * 60.0  # 7 hours
        elif risk == "medium":
            stages = 5
            percentages = [5.0, 20.0, 50.0, 80.0, 100.0]
            duration = 3 * 60.0
        else:
            stages = 3
            percentages = [25.0, 50.0, 100.0]
            duration = 60.0

        prerequisites = self._rollout_prerequisites(flag, graph)
        monitoring = self._monitoring_points(flag, affected, graph)
        rollback_plan = self._rollback_plan(flag)

        return RolloutStrategy(
            flag_id=flag.id,
            recommended_stages=stages,
            stage_percentages=percentages,
            estimated_duration_minutes=duration,
            risk_level=risk,
            prerequisites=prerequisites,
            rollback_plan=rollback_plan,
            monitoring_points=monitoring,
        )

    def generate_flag_dependency_graph(
        self,
        flags: list[FeatureFlag],
    ) -> dict:
        """Return a visualisation-ready dependency graph."""
        nodes: list[dict] = []
        edges: list[dict] = []
        flag_map = {f.id: f for f in flags}

        for f in flags:
            nodes.append(
                {
                    "id": f.id,
                    "name": f.name,
                    "type": f.flag_type.value,
                    "state": f.state.value,
                    "rollout_percentage": f.rollout_percentage,
                }
            )
            for dep_id in f.dependencies:
                edges.append(
                    {
                        "source": f.id,
                        "target": dep_id,
                        "type": "dependency",
                    }
                )
            for comp_id in f.kill_switch_for:
                edges.append(
                    {
                        "source": f.id,
                        "target": comp_id,
                        "type": "kill_switch",
                    }
                )

        return {
            "nodes": nodes,
            "edges": edges,
            "flag_count": len(flags),
            "dependency_count": sum(len(f.dependencies) for f in flags),
            "kill_switch_count": sum(
                1 for f in flags if f.flag_type == FlagType.KILL_SWITCH
            ),
        }

    # -- private helpers ----------------------------------------------------

    def _check_pair(
        self,
        fa: FeatureFlag,
        fb: FeatureFlag,
        flag_map: dict[str, FeatureFlag],
    ) -> list[FlagInteraction]:
        interactions: list[FlagInteraction] = []

        # Dependency
        if fb.id in fa.dependencies:
            interactions.append(
                FlagInteraction(
                    flag_a_id=fa.id,
                    flag_b_id=fb.id,
                    interaction_type=FlagInteractionType.DEPENDENCY,
                    severity=self._dep_severity(fa, fb),
                    description=f"Flag {fa.id} depends on flag {fb.id}",
                    resolution=f"Ensure {fb.id} is enabled before enabling {fa.id}",
                )
            )
        if fa.id in fb.dependencies:
            interactions.append(
                FlagInteraction(
                    flag_a_id=fb.id,
                    flag_b_id=fa.id,
                    interaction_type=FlagInteractionType.DEPENDENCY,
                    severity=self._dep_severity(fb, fa),
                    description=f"Flag {fb.id} depends on flag {fa.id}",
                    resolution=f"Ensure {fa.id} is enabled before enabling {fb.id}",
                )
            )

        # Mutual exclusion — both enabled and share kill_switch targets
        if self._are_mutually_exclusive(fa, fb):
            interactions.append(
                FlagInteraction(
                    flag_a_id=fa.id,
                    flag_b_id=fb.id,
                    interaction_type=FlagInteractionType.MUTUAL_EXCLUSION,
                    severity="high",
                    description=(
                        f"Flags {fa.id} and {fb.id} target overlapping "
                        f"kill-switch components"
                    ),
                    resolution="Enable only one of these flags at a time",
                )
            )

        # Conflict — both enabled and affect same resource in opposite ways
        conflict = self._detect_conflict(fa, fb)
        if conflict:
            interactions.append(conflict)

        # Cascade enable
        if self._is_cascade_enable(fa, fb, flag_map):
            interactions.append(
                FlagInteraction(
                    flag_a_id=fa.id,
                    flag_b_id=fb.id,
                    interaction_type=FlagInteractionType.CASCADE_ENABLE,
                    severity="medium",
                    description=f"Enabling {fa.id} cascades to enable {fb.id}",
                    resolution="Verify cascade is intentional before enabling",
                )
            )

        # Cascade disable
        if self._is_cascade_disable(fa, fb, flag_map):
            interactions.append(
                FlagInteraction(
                    flag_a_id=fa.id,
                    flag_b_id=fb.id,
                    interaction_type=FlagInteractionType.CASCADE_DISABLE,
                    severity="high",
                    description=f"Disabling {fa.id} cascades to disable {fb.id}",
                    resolution="Add fallback for dependent flags before disabling",
                )
            )

        # Resource contention
        contention = self._detect_resource_contention(fa, fb)
        if contention:
            interactions.append(contention)

        return interactions

    def _dep_severity(self, fa: FeatureFlag, fb: FeatureFlag) -> str:
        if fb.state == FlagState.DISABLED:
            return "critical"
        if fb.state in (FlagState.CANARY, FlagState.PERCENTAGE_ROLLOUT):
            return "high"
        return "medium"

    def _are_mutually_exclusive(self, fa: FeatureFlag, fb: FeatureFlag) -> bool:
        if not fa.kill_switch_for or not fb.kill_switch_for:
            return False
        overlap = set(fa.kill_switch_for) & set(fb.kill_switch_for)
        return len(overlap) > 0

    def _detect_conflict(
        self, fa: FeatureFlag, fb: FeatureFlag
    ) -> FlagInteraction | None:
        if fa.state == FlagState.DISABLED or fb.state == FlagState.DISABLED:
            return None
        # Check for opposite resource impacts
        common_keys = set(fa.resource_impact.keys()) & set(fb.resource_impact.keys())
        for key in common_keys:
            va = fa.resource_impact[key]
            vb = fb.resource_impact[key]
            if (va > 0 and vb < 0) or (va < 0 and vb > 0):
                return FlagInteraction(
                    flag_a_id=fa.id,
                    flag_b_id=fb.id,
                    interaction_type=FlagInteractionType.CONFLICT,
                    severity="high",
                    description=(
                        f"Flags {fa.id} and {fb.id} have opposing "
                        f"resource impacts on {key}"
                    ),
                    resolution=f"Review resource impact on {key} for both flags",
                )
        return None

    def _is_cascade_enable(
        self,
        fa: FeatureFlag,
        fb: FeatureFlag,
        flag_map: dict[str, FeatureFlag],
    ) -> bool:
        """True if enabling fa would trigger a cascade that enables fb."""
        if fb.id not in fa.dependencies:
            return False
        if fa.state in (FlagState.ENABLED, FlagState.PERCENTAGE_ROLLOUT):
            return fb.state == FlagState.DISABLED
        return False

    def _is_cascade_disable(
        self,
        fa: FeatureFlag,
        fb: FeatureFlag,
        flag_map: dict[str, FeatureFlag],
    ) -> bool:
        """True if disabling fa would cascade-disable fb."""
        return fa.id in fb.dependencies and fa.state == FlagState.DISABLED

    def _detect_resource_contention(
        self, fa: FeatureFlag, fb: FeatureFlag
    ) -> FlagInteraction | None:
        if fa.state == FlagState.DISABLED or fb.state == FlagState.DISABLED:
            return None
        common_keys = set(fa.resource_impact.keys()) & set(fb.resource_impact.keys())
        for key in common_keys:
            combined = abs(fa.resource_impact[key]) + abs(fb.resource_impact[key])
            if combined >= _RESOURCE_OVERHEAD_THRESHOLD:
                return FlagInteraction(
                    flag_a_id=fa.id,
                    flag_b_id=fb.id,
                    interaction_type=FlagInteractionType.RESOURCE_CONTENTION,
                    severity="critical" if combined >= _CRITICAL_RESOURCE_THRESHOLD else "high",
                    description=(
                        f"Flags {fa.id} and {fb.id} combined resource "
                        f"impact on {key} is {combined:.1%}"
                    ),
                    resolution=f"Stagger rollouts or reduce resource impact for {key}",
                )
        return None

    # -- resilience helpers ------------------------------------------------

    def _flag_affected_components(
        self,
        flag: FeatureFlag,
        component_ids: set[str],
        graph: InfraGraph,
    ) -> list[str]:
        """Determine which components a flag affects."""
        affected: set[str] = set()

        # Kill-switch targets
        for cid in flag.kill_switch_for:
            if cid in component_ids:
                affected.add(cid)
                # Cascade via graph
                affected.update(graph.get_all_affected(cid) & component_ids)

        # If a flag has resource impacts, it potentially affects all components
        if flag.resource_impact and not affected:
            # Heuristic: affect a fraction of components based on rollout
            if flag.state == FlagState.ENABLED:
                affected = set(component_ids)
            elif flag.state in (FlagState.PERCENTAGE_ROLLOUT, FlagState.CANARY):
                # Affect proportional slice
                all_ids = sorted(component_ids)
                count = max(1, int(len(all_ids) * flag.rollout_percentage / 100))
                affected = set(all_ids[:count])
            elif flag.state == FlagState.USER_TARGETED:
                # Minimal impact
                all_ids = sorted(component_ids)
                affected = set(all_ids[:1]) if all_ids else set()

        return sorted(affected)

    def _compute_resource_overhead(
        self,
        flag: FeatureFlag,
        affected: list[str],
        graph: InfraGraph,
    ) -> dict[str, float]:
        overhead: dict[str, float] = {}
        scale = self._effective_scale(flag)
        for key, val in flag.resource_impact.items():
            overhead[key] = round(val * scale, 4)
        return overhead

    def _effective_scale(self, flag: FeatureFlag) -> float:
        if flag.state == FlagState.DISABLED:
            return 0.0
        if flag.state == FlagState.ENABLED:
            return 1.0
        if flag.state == FlagState.PERCENTAGE_ROLLOUT:
            return flag.rollout_percentage / 100.0
        if flag.state == FlagState.CANARY:
            return 0.05  # 5% canary
        # USER_TARGETED or any unknown future state
        return 0.01

    def _compute_resilience_delta(
        self,
        flag: FeatureFlag,
        affected: list[str],
        graph: InfraGraph,
    ) -> float:
        """Positive delta = improves resilience, negative = harms it."""
        delta = 0.0

        # Kill switches improve resilience
        if flag.flag_type == FlagType.KILL_SWITCH:
            delta += 5.0 * len(flag.kill_switch_for)

        # Ops toggles slightly positive
        if flag.flag_type == FlagType.OPS_TOGGLE:
            delta += 2.0

        # Experiments add risk
        if flag.flag_type == FlagType.EXPERIMENT:
            delta -= 3.0

        # Resource impact penalty/bonus
        total_impact = sum(abs(v) for v in flag.resource_impact.values())
        if total_impact > _RESOURCE_OVERHEAD_THRESHOLD:
            delta -= total_impact * 10.0

        # Many affected components increases risk
        if len(affected) > 5:
            delta -= (len(affected) - 5) * 0.5

        # Clamp
        delta = max(_RESILIENCE_NEGATIVE_CAP, min(_RESILIENCE_POSITIVE_CAP, delta))
        return round(delta, 2)

    def _estimate_rollback_time(
        self,
        flag: FeatureFlag,
        affected: list[str],
        graph: InfraGraph,
    ) -> float:
        """Estimate seconds to roll back a flag."""
        base = 5.0  # flag flip itself

        # Add time per affected component
        base += len(affected) * 2.0

        # Kill switches are fast
        if flag.flag_type == FlagType.KILL_SWITCH:
            return base

        # Experiments with data may take longer
        if flag.flag_type == FlagType.EXPERIMENT:
            base += 30.0

        # Gradual rollout has cache/state
        if flag.state == FlagState.PERCENTAGE_ROLLOUT:
            base += flag.rollout_percentage * 0.5

        return round(base, 2)

    def _classify_rollback_safety(
        self, rollback_time: float, overhead: dict[str, float]
    ) -> str:
        max_overhead = max((abs(v) for v in overhead.values()), default=0.0)
        if rollback_time > _ROLLBACK_RISKY_THRESHOLD or max_overhead > _CRITICAL_RESOURCE_THRESHOLD:
            return "dangerous"
        if rollback_time > _ROLLBACK_SAFE_THRESHOLD or max_overhead > _RESOURCE_OVERHEAD_THRESHOLD:
            return "risky"
        return "safe"

    # -- rollout helpers ---------------------------------------------------

    def _stage_affected(self, all_affected: list[str], scale: float) -> list[str]:
        count = max(1, int(math.ceil(len(all_affected) * scale)))
        return all_affected[:count]

    # -- failure helpers ---------------------------------------------------

    def _classify_failure_severity(
        self,
        flag: FeatureFlag,
        dependent_flags: list[str],
        impact_pct: float,
    ) -> str:
        if flag.flag_type == FlagType.KILL_SWITCH:
            return "critical"
        if impact_pct > 50:
            return "critical"
        if impact_pct > 20 or len(dependent_flags) > 3:
            return "high"
        if impact_pct > 5 or len(dependent_flags) > 0:
            return "medium"
        return "low"

    def _determine_fallback(self, flag: FeatureFlag) -> str:
        if flag.flag_type == FlagType.KILL_SWITCH:
            return "Fail-open: components remain running without kill-switch protection"
        if flag.flag_type == FlagType.EXPERIMENT:
            return "Fail-closed: experiment disabled, use control path"
        if flag.flag_type == FlagType.OPS_TOGGLE:
            return "Fail-open: operational toggle defaults to enabled"
        if flag.flag_type == FlagType.GRADUAL_ROLLOUT:
            return "Fail-closed: rollout halted at current percentage"
        if flag.flag_type == FlagType.PERMISSION:
            return "Fail-closed: permission denied by default"
        return "Fail-closed: flag defaults to disabled"

    def _failure_recommendations(
        self, flag: FeatureFlag, dependent_flags: list[str]
    ) -> list[str]:
        recs: list[str] = []
        if flag.flag_type == FlagType.KILL_SWITCH:
            recs.append("Implement local kill-switch cache with TTL")
        if dependent_flags:
            recs.append(f"Decouple {len(dependent_flags)} dependent flag(s) with defaults")
        if flag.state == FlagState.PERCENTAGE_ROLLOUT:
            recs.append("Cache current rollout percentage locally")
        recs.append("Ensure flag service has circuit breaker configured")
        return recs

    # -- strategy helpers --------------------------------------------------

    def _assess_rollout_risk(
        self,
        flag: FeatureFlag,
        affected: list[str],
        graph: InfraGraph,
    ) -> str:
        risk_score = 0

        # Number of affected components
        if len(affected) > 10:
            risk_score += 3
        elif len(affected) > 5:
            risk_score += 2
        elif len(affected) > 0:
            risk_score += 1

        # Resource impact magnitude
        total_impact = sum(abs(v) for v in flag.resource_impact.values())
        if total_impact >= _CRITICAL_RESOURCE_THRESHOLD:
            risk_score += 3
        elif total_impact >= _RESOURCE_OVERHEAD_THRESHOLD:
            risk_score += 2

        # Dependencies add risk
        risk_score += len(flag.dependencies)

        # Kill switches are inherently high risk
        if flag.flag_type == FlagType.KILL_SWITCH:
            risk_score += 2

        if risk_score >= 5:
            return "high"
        if risk_score >= 3:
            return "medium"
        return "low"

    def _rollout_prerequisites(
        self, flag: FeatureFlag, graph: InfraGraph
    ) -> list[str]:
        prereqs: list[str] = []
        for dep in flag.dependencies:
            prereqs.append(f"Ensure flag {dep} is enabled")
        if flag.flag_type == FlagType.KILL_SWITCH:
            prereqs.append("Verify kill-switch targets are healthy")
        if flag.resource_impact:
            prereqs.append("Verify resource headroom for impacted resources")
        return prereqs

    def _monitoring_points(
        self,
        flag: FeatureFlag,
        affected: list[str],
        graph: InfraGraph,
    ) -> list[str]:
        points: list[str] = []
        for key in flag.resource_impact:
            points.append(f"Monitor {key} metric")
        if affected:
            points.append(f"Watch error rates for {len(affected)} affected component(s)")
        points.append("Monitor flag evaluation latency")
        return points

    def _rollback_plan(self, flag: FeatureFlag) -> str:
        if flag.flag_type == FlagType.KILL_SWITCH:
            return "Immediately disable kill-switch flag and verify component recovery"
        if flag.flag_type == FlagType.EXPERIMENT:
            return "Disable experiment flag; users revert to control path"
        return f"Disable flag {flag.id} and monitor affected components for 15 minutes"
