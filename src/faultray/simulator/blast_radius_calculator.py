# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Blast Radius Calculator -- precise mathematical quantification of failure blast radii.

Calculates the blast radius of infrastructure failures with financial/user
impact quantification, cascade depth analysis, temporal propagation modelling,
cross-region analysis, and isolation boundary effectiveness scoring.

This module is DISTINCT from blast_radius_mapper (BFS mapping with Pydantic
models) and blast_radius_predictor (prediction with confidence intervals).
It focuses on precise mathematical CALCULATION with financial and user impact
quantification, using dataclass result models.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DegradationZone(str, Enum):
    """Classification of outage severity for a component."""

    FULL_OUTAGE = "full_outage"
    SEVERE_DEGRADATION = "severe_degradation"
    PARTIAL_DEGRADATION = "partial_degradation"
    MINIMAL_IMPACT = "minimal_impact"
    NO_IMPACT = "no_impact"


class ContainmentMechanism(str, Enum):
    """Type of containment mechanism that limits blast radius."""

    CIRCUIT_BREAKER = "circuit_breaker"
    BULKHEAD = "bulkhead"
    FAILOVER = "failover"
    REDUNDANCY = "redundancy"
    RATE_LIMITER = "rate_limiter"
    NETWORK_SEGMENTATION = "network_segmentation"
    NONE = "none"


class TemporalPhase(str, Enum):
    """Temporal phase of blast radius propagation."""

    IMMEDIATE = "immediate"
    SHORT_TERM = "short_term"
    MEDIUM_TERM = "medium_term"
    LONG_TERM = "long_term"
    EXTENDED = "extended"


class RecommendationPriority(str, Enum):
    """Priority level for blast radius reduction recommendations."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ---------------------------------------------------------------------------
# Dataclass result models
# ---------------------------------------------------------------------------


@dataclass
class ComponentImpactScore:
    """Impact score for a single component failure."""

    component_id: str
    direct_impact_score: float = 0.0
    transitive_impact_score: float = 0.0
    total_impact_score: float = 0.0
    cascade_depth: int = 0
    affected_downstream_count: int = 0
    degradation_zone: DegradationZone = DegradationZone.NO_IMPACT
    user_impact_percent: float = 0.0
    revenue_impact_per_hour: float = 0.0


@dataclass
class CascadeDepthResult:
    """Result of cascade depth calculation for a failure origin."""

    origin_component_id: str
    max_depth: int = 0
    components_at_depth: Dict[int, List[str]] = field(default_factory=dict)
    total_affected: int = 0
    propagation_paths: List[List[str]] = field(default_factory=list)


@dataclass
class UserImpactEstimate:
    """Estimation of user impact from a component failure."""

    component_id: str
    direct_user_percent: float = 0.0
    indirect_user_percent: float = 0.0
    total_user_percent: float = 0.0
    affected_user_flows: List[str] = field(default_factory=list)
    estimated_error_rate: float = 0.0


@dataclass
class RevenueImpact:
    """Financial impact model for a component failure."""

    component_id: str
    revenue_loss_per_minute: float = 0.0
    revenue_loss_per_hour: float = 0.0
    sla_credit_exposure: float = 0.0
    recovery_cost: float = 0.0
    total_cost_per_hour: float = 0.0
    impacted_revenue_streams: List[str] = field(default_factory=list)


@dataclass
class TemporalBlastRadius:
    """How blast radius looks at a specific temporal snapshot."""

    origin_component_id: str
    phase: TemporalPhase = TemporalPhase.IMMEDIATE
    elapsed_seconds: float = 0.0
    affected_count: int = 0
    affected_components: List[str] = field(default_factory=list)
    cumulative_user_impact_percent: float = 0.0
    cumulative_revenue_loss: float = 0.0


@dataclass
class TemporalProgression:
    """Complete temporal progression of a blast radius."""

    origin_component_id: str
    snapshots: List[TemporalBlastRadius] = field(default_factory=list)
    time_to_full_propagation_seconds: float = 0.0
    peak_affected_count: int = 0
    peak_user_impact_percent: float = 0.0


@dataclass
class CrossRegionImpact:
    """Blast radius impact across regions."""

    origin_component_id: str
    origin_region: str = ""
    affected_regions: List[str] = field(default_factory=list)
    region_impact_scores: Dict[str, float] = field(default_factory=dict)
    cross_region_propagation: bool = False
    total_regions_affected: int = 0


@dataclass
class IsolationBoundary:
    """An isolation boundary and its effectiveness."""

    boundary_id: str
    mechanism: ContainmentMechanism = ContainmentMechanism.NONE
    protected_components: List[str] = field(default_factory=list)
    effectiveness_score: float = 0.0
    failure_leak_probability: float = 1.0
    components_behind: int = 0


@dataclass
class ContainmentStrategy:
    """Strategy for containing blast radius."""

    boundaries: List[IsolationBoundary] = field(default_factory=list)
    overall_containment_score: float = 0.0
    unprotected_components: List[str] = field(default_factory=list)
    containment_gap_score: float = 0.0


@dataclass
class BlastRadiusReduction:
    """A recommendation for reducing blast radius."""

    target_component_id: str
    recommendation: str = ""
    priority: RecommendationPriority = RecommendationPriority.MEDIUM
    estimated_risk_reduction_percent: float = 0.0
    estimated_implementation_hours: float = 0.0
    mechanism: ContainmentMechanism = ContainmentMechanism.NONE


@dataclass
class ScenarioComparison:
    """Comparison of blast radii between different failure scenarios."""

    scenarios: List[ComponentImpactScore] = field(default_factory=list)
    worst_case_component: str = ""
    best_case_component: str = ""
    average_impact_score: float = 0.0
    median_impact_score: float = 0.0
    risk_ranking: List[Tuple[str, float]] = field(default_factory=list)


@dataclass
class BlastRadiusReport:
    """Complete blast radius calculation report."""

    timestamp: str = ""
    graph_component_count: int = 0
    graph_dependency_count: int = 0
    impact_scores: List[ComponentImpactScore] = field(default_factory=list)
    cascade_results: List[CascadeDepthResult] = field(default_factory=list)
    user_impacts: List[UserImpactEstimate] = field(default_factory=list)
    revenue_impacts: List[RevenueImpact] = field(default_factory=list)
    temporal_progressions: List[TemporalProgression] = field(default_factory=list)
    cross_region_impacts: List[CrossRegionImpact] = field(default_factory=list)
    containment_strategy: Optional[ContainmentStrategy] = None
    recommendations: List[BlastRadiusReduction] = field(default_factory=list)
    scenario_comparison: Optional[ScenarioComparison] = None
    overall_risk_score: float = 0.0


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_BFS_DEPTH = 50

_COMPONENT_USER_WEIGHTS: Dict[ComponentType, float] = {
    ComponentType.LOAD_BALANCER: 1.0,
    ComponentType.WEB_SERVER: 0.95,
    ComponentType.APP_SERVER: 0.85,
    ComponentType.DATABASE: 0.9,
    ComponentType.CACHE: 0.4,
    ComponentType.QUEUE: 0.35,
    ComponentType.STORAGE: 0.6,
    ComponentType.DNS: 1.0,
    ComponentType.EXTERNAL_API: 0.3,
    ComponentType.CUSTOM: 0.5,
    ComponentType.AI_AGENT: 0.75,
    ComponentType.LLM_ENDPOINT: 0.7,
    ComponentType.TOOL_SERVICE: 0.5,
    ComponentType.AGENT_ORCHESTRATOR: 0.8,
}

_COMPONENT_REVENUE_WEIGHTS: Dict[ComponentType, float] = {
    ComponentType.LOAD_BALANCER: 0.95,
    ComponentType.WEB_SERVER: 0.9,
    ComponentType.APP_SERVER: 0.85,
    ComponentType.DATABASE: 1.0,
    ComponentType.CACHE: 0.3,
    ComponentType.QUEUE: 0.4,
    ComponentType.STORAGE: 0.7,
    ComponentType.DNS: 0.95,
    ComponentType.EXTERNAL_API: 0.25,
    ComponentType.CUSTOM: 0.5,
    ComponentType.AI_AGENT: 0.65,
    ComponentType.LLM_ENDPOINT: 0.6,
    ComponentType.TOOL_SERVICE: 0.4,
    ComponentType.AGENT_ORCHESTRATOR: 0.7,
}

_TEMPORAL_BOUNDARIES: List[Tuple[TemporalPhase, float]] = [
    (TemporalPhase.IMMEDIATE, 30.0),
    (TemporalPhase.SHORT_TERM, 300.0),
    (TemporalPhase.MEDIUM_TERM, 1800.0),
    (TemporalPhase.LONG_TERM, 7200.0),
    (TemporalPhase.EXTENDED, float("inf")),
]

_PROPAGATION_DELAY_PER_HOP = 15.0

_CONTAINMENT_EFFECTIVENESS: Dict[ContainmentMechanism, float] = {
    ContainmentMechanism.CIRCUIT_BREAKER: 0.85,
    ContainmentMechanism.BULKHEAD: 0.75,
    ContainmentMechanism.FAILOVER: 0.7,
    ContainmentMechanism.REDUNDANCY: 0.6,
    ContainmentMechanism.RATE_LIMITER: 0.5,
    ContainmentMechanism.NETWORK_SEGMENTATION: 0.8,
    ContainmentMechanism.NONE: 0.0,
}


# ---------------------------------------------------------------------------
# Helper functions (module-level, testable)
# ---------------------------------------------------------------------------


def classify_degradation_zone(impact_score: float) -> DegradationZone:
    """Classify the degradation zone based on impact score (0-100)."""
    if impact_score >= 80.0:
        return DegradationZone.FULL_OUTAGE
    if impact_score >= 50.0:
        return DegradationZone.SEVERE_DEGRADATION
    if impact_score >= 20.0:
        return DegradationZone.PARTIAL_DEGRADATION
    if impact_score > 0.0:
        return DegradationZone.MINIMAL_IMPACT
    return DegradationZone.NO_IMPACT


def get_temporal_phase(elapsed_seconds: float) -> TemporalPhase:
    """Map elapsed seconds to temporal phase."""
    for phase, boundary in _TEMPORAL_BOUNDARIES:
        if elapsed_seconds <= boundary:
            return phase
    return TemporalPhase.EXTENDED


def dep_type_weight(dep_type: str) -> float:
    """Return a weight factor based on dependency type."""
    if dep_type == "requires":
        return 1.0
    if dep_type == "optional":
        return 0.3
    return 0.1


def replica_mitigation_factor(replicas: int) -> float:
    """Calculate mitigation factor based on replica count.

    More replicas lowers the failure impact on that component.
    Returns a value between 0.1 and 1.0.
    """
    if replicas <= 1:
        return 1.0
    if replicas == 2:
        return 0.6
    if replicas == 3:
        return 0.35
    return max(0.1, 1.0 / replicas)


def identify_containment_mechanism(
    comp: Component,
    graph: InfraGraph,
) -> ContainmentMechanism:
    """Identify the primary containment mechanism for a component."""
    for dep_comp in graph.get_dependencies(comp.id):
        edge = graph.get_dependency_edge(comp.id, dep_comp.id)
        if edge is not None and edge.circuit_breaker.enabled:
            return ContainmentMechanism.CIRCUIT_BREAKER

    if comp.failover.enabled and comp.replicas >= 2:
        return ContainmentMechanism.FAILOVER

    if comp.replicas >= 3:
        return ContainmentMechanism.REDUNDANCY

    if comp.security.network_segmented:
        return ContainmentMechanism.NETWORK_SEGMENTATION

    if comp.security.rate_limiting:
        return ContainmentMechanism.RATE_LIMITER

    return ContainmentMechanism.NONE


def compute_direct_impact(
    comp: Component,
    graph: InfraGraph,
) -> float:
    """Compute the direct impact score for a component failure (0-100).

    Considers:
    - Number of direct dependents and their dependency types
    - Component type weight
    - Replica count mitigation
    """
    dependents = graph.get_dependents(comp.id)
    type_weight = _COMPONENT_USER_WEIGHTS.get(comp.type, 0.5)
    rep_factor = replica_mitigation_factor(comp.replicas)

    if not dependents:
        return round(type_weight * 20.0 * rep_factor, 2)

    weighted_dep_count = 0.0
    for dep_comp in dependents:
        edge = graph.get_dependency_edge(dep_comp.id, comp.id)
        if edge is not None:
            weighted_dep_count += dep_type_weight(edge.dependency_type) * edge.weight
        else:
            weighted_dep_count += 1.0

    raw = min(100.0, weighted_dep_count * 15.0 * type_weight * rep_factor)

    # Agent hallucination risk boost: if this component's failure causes
    # agent dependents to lose grounding, increase impact score
    _AGENT_TYPES = {
        ComponentType.AI_AGENT, ComponentType.LLM_ENDPOINT,
        ComponentType.TOOL_SERVICE, ComponentType.AGENT_ORCHESTRATOR,
    }
    for dep_comp in dependents:
        if dep_comp.type in _AGENT_TYPES:
            hallucination_risk = float(dep_comp.parameters.get("hallucination_risk", 0.0))
            requires_grounding = bool(dep_comp.parameters.get("requires_grounding", 0))
            if requires_grounding and hallucination_risk > 0:
                # Agents that lose their grounding data source are high-risk
                raw = min(100.0, raw * (1.0 + hallucination_risk * 5.0))

    return round(raw, 2)


def compute_transitive_impact(
    comp_id: str,
    graph: InfraGraph,
) -> Tuple[float, int, List[str]]:
    """Compute transitive impact score via BFS through dependents.

    Returns (transitive_score, max_depth, list_of_affected_ids).
    """
    visited: set[str] = {comp_id}
    queue: deque[Tuple[str, int]] = deque()
    total_score = 0.0
    max_depth = 0
    affected: List[str] = []

    for dep_comp in graph.get_dependents(comp_id):
        if dep_comp.id not in visited:
            queue.append((dep_comp.id, 1))
            visited.add(dep_comp.id)

    while queue:
        cid, depth = queue.popleft()
        if depth > _MAX_BFS_DEPTH:
            continue

        c = graph.get_component(cid)
        if c is None:
            continue

        max_depth = max(max_depth, depth)
        affected.append(cid)

        decay = max(0.05, 1.0 - depth * 0.15)
        type_w = _COMPONENT_USER_WEIGHTS.get(c.type, 0.5)
        rep_f = replica_mitigation_factor(c.replicas)

        cb_factor = 1.0
        for dep_c in graph.get_dependencies(c.id):
            if dep_c.id in visited:
                edge = graph.get_dependency_edge(c.id, dep_c.id)
                if edge is not None and edge.circuit_breaker.enabled:
                    cb_factor = 0.15
                    break

        failover_factor = 0.3 if c.failover.enabled else 1.0

        hop_score = 10.0 * decay * type_w * rep_f * cb_factor * failover_factor
        total_score += hop_score

        if cb_factor < 1.0 and failover_factor < 1.0 and c.replicas >= 2:
            continue

        for next_dep in graph.get_dependents(cid):
            if next_dep.id not in visited:
                queue.append((next_dep.id, depth + 1))
                visited.add(next_dep.id)

    return round(total_score, 2), max_depth, affected


def containment_effectiveness_base(mechanism: ContainmentMechanism) -> float:
    """Return baseline containment effectiveness for a mechanism."""
    return _CONTAINMENT_EFFECTIVENESS.get(mechanism, 0.0)


def component_user_weight(comp_type: ComponentType) -> float:
    """Return user-facing weight for a component type."""
    return _COMPONENT_USER_WEIGHTS.get(comp_type, 0.5)


def component_revenue_weight(comp_type: ComponentType) -> float:
    """Return revenue criticality weight for a component type."""
    return _COMPONENT_REVENUE_WEIGHTS.get(comp_type, 0.5)


# ---------------------------------------------------------------------------
# Main Calculator
# ---------------------------------------------------------------------------


class BlastRadiusCalculator:
    """Calculates the blast radius of infrastructure failures with precise
    mathematical quantification of impact.

    Accepts an InfraGraph and provides methods for:
    - Component failure impact scoring (direct + transitive)
    - Cascade depth calculation
    - User impact estimation
    - Revenue impact modelling
    - Service degradation zone classification
    - Blast radius containment strategy analysis
    - Temporal blast radius progression
    - Cross-region blast radius analysis
    - Scenario comparison
    - Blast radius reduction recommendations
    - Isolation boundary effectiveness scoring
    - Full report generation
    """

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    @property
    def graph(self) -> InfraGraph:
        """Return the underlying infrastructure graph."""
        return self._graph

    # ------------------------------------------------------------------
    # 1. Component Impact Scoring
    # ------------------------------------------------------------------

    def calculate_impact_score(self, component_id: str) -> ComponentImpactScore:
        """Calculate the full impact score for a single component failure."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return ComponentImpactScore(component_id=component_id)

        direct = compute_direct_impact(comp, self._graph)
        transitive, depth, affected = compute_transitive_impact(
            component_id, self._graph
        )
        total = round(min(100.0, direct + transitive), 2)
        zone = classify_degradation_zone(total)
        user_pct = self._estimate_user_percent(component_id, depth, len(affected))
        rev_hr = self._estimate_revenue_per_hour(component_id, total)

        return ComponentImpactScore(
            component_id=component_id,
            direct_impact_score=direct,
            transitive_impact_score=transitive,
            total_impact_score=total,
            cascade_depth=depth,
            affected_downstream_count=len(affected),
            degradation_zone=zone,
            user_impact_percent=user_pct,
            revenue_impact_per_hour=rev_hr,
        )

    def calculate_all_impact_scores(self) -> List[ComponentImpactScore]:
        """Calculate impact scores for every component in the graph."""
        scores: List[ComponentImpactScore] = []
        for cid in self._graph.components:
            scores.append(self.calculate_impact_score(cid))
        scores.sort(key=lambda s: s.total_impact_score, reverse=True)
        return scores

    # ------------------------------------------------------------------
    # 2. Cascade Depth Calculation
    # ------------------------------------------------------------------

    def calculate_cascade_depth(self, component_id: str) -> CascadeDepthResult:
        """Calculate cascade depth and enumerate affected components per depth."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return CascadeDepthResult(origin_component_id=component_id)

        visited: set[str] = {component_id}
        queue: deque[Tuple[str, int]] = deque()
        components_at_depth: Dict[int, List[str]] = {}
        max_depth = 0

        for dep_comp in self._graph.get_dependents(component_id):
            if dep_comp.id not in visited:
                queue.append((dep_comp.id, 1))
                visited.add(dep_comp.id)

        while queue:
            cid, depth = queue.popleft()
            if depth > _MAX_BFS_DEPTH:
                continue
            c = self._graph.get_component(cid)
            if c is None:
                continue

            max_depth = max(max_depth, depth)
            components_at_depth.setdefault(depth, []).append(cid)

            for next_dep in self._graph.get_dependents(cid):
                if next_dep.id not in visited:
                    queue.append((next_dep.id, depth + 1))
                    visited.add(next_dep.id)

        all_affected: set[str] = set()
        for ids in components_at_depth.values():
            all_affected.update(ids)
        paths = self._build_propagation_paths(component_id, all_affected)

        total_affected = sum(len(v) for v in components_at_depth.values())

        return CascadeDepthResult(
            origin_component_id=component_id,
            max_depth=max_depth,
            components_at_depth=components_at_depth,
            total_affected=total_affected,
            propagation_paths=paths,
        )

    # ------------------------------------------------------------------
    # 3. User Impact Estimation
    # ------------------------------------------------------------------

    def estimate_user_impact(self, component_id: str) -> UserImpactEstimate:
        """Estimate the percentage of users affected by a component failure."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return UserImpactEstimate(component_id=component_id)

        type_w = component_user_weight(comp.type)
        rep_f = replica_mitigation_factor(comp.replicas)

        direct_pct = round(type_w * 100.0 * rep_f, 2)

        affected = self._graph.get_all_affected(component_id)
        total_comps = len(self._graph.components)
        if total_comps <= 1:
            indirect_pct = 0.0
        else:
            affected_ratio = len(affected) / max(total_comps - 1, 1)
            indirect_pct = round(affected_ratio * 50.0 * rep_f, 2)

        total_pct = round(min(100.0, direct_pct * 0.6 + indirect_pct * 0.4), 2)

        flows = self._determine_affected_flows(comp, affected)
        error_rate = round(min(1.0, total_pct / 100.0), 4)

        return UserImpactEstimate(
            component_id=component_id,
            direct_user_percent=min(100.0, direct_pct),
            indirect_user_percent=min(100.0, indirect_pct),
            total_user_percent=total_pct,
            affected_user_flows=flows,
            estimated_error_rate=error_rate,
        )

    # ------------------------------------------------------------------
    # 4. Revenue Impact Modelling
    # ------------------------------------------------------------------

    def calculate_revenue_impact(self, component_id: str) -> RevenueImpact:
        """Calculate the financial cost of a component failure."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return RevenueImpact(component_id=component_id)

        cost = comp.cost_profile
        rev_w = component_revenue_weight(comp.type)
        rep_f = replica_mitigation_factor(comp.replicas)

        rev_per_min = cost.revenue_per_minute * rev_w * rep_f
        rev_per_hour = round(rev_per_min * 60.0, 2)

        sla_credit = round(
            cost.monthly_contract_value * (cost.sla_credit_percent / 100.0), 2
        )

        team_size = cost.recovery_team_size if cost.recovery_team_size > 0 else 2
        recovery_cost = round(
            team_size * cost.recovery_engineer_cost
            * (comp.operational_profile.mttr_minutes / 60.0),
            2,
        )

        total = round(rev_per_hour + sla_credit + recovery_cost, 2)
        streams = self._identify_revenue_streams(comp)

        return RevenueImpact(
            component_id=component_id,
            revenue_loss_per_minute=round(rev_per_min, 2),
            revenue_loss_per_hour=rev_per_hour,
            sla_credit_exposure=sla_credit,
            recovery_cost=recovery_cost,
            total_cost_per_hour=total,
            impacted_revenue_streams=streams,
        )

    # ------------------------------------------------------------------
    # 5. Service Degradation Zones
    # ------------------------------------------------------------------

    def classify_degradation_zones(self) -> Dict[str, DegradationZone]:
        """Classify all components into degradation zones."""
        zones: Dict[str, DegradationZone] = {}
        for cid in self._graph.components:
            score = self.calculate_impact_score(cid)
            zones[cid] = score.degradation_zone
        return zones

    def get_components_in_zone(self, zone: DegradationZone) -> List[str]:
        """Return component IDs that fall into a specific degradation zone."""
        all_zones = self.classify_degradation_zones()
        return [cid for cid, z in all_zones.items() if z == zone]

    # ------------------------------------------------------------------
    # 6. Containment Strategy Analysis
    # ------------------------------------------------------------------

    def analyze_containment_strategy(self) -> ContainmentStrategy:
        """Analyze the current containment strategy across the graph."""
        boundaries: List[IsolationBoundary] = []
        protected_set: set[str] = set()

        for comp in self._graph.components.values():
            mechanism = identify_containment_mechanism(comp, self._graph)
            if mechanism == ContainmentMechanism.NONE:
                continue

            protected = [d.id for d in self._graph.get_dependents(comp.id)]
            effectiveness = containment_effectiveness_base(mechanism)

            if comp.replicas >= 3:
                effectiveness = min(1.0, effectiveness + 0.1)
            elif comp.replicas >= 2:
                effectiveness = min(1.0, effectiveness + 0.05)

            leak_prob = round(1.0 - effectiveness, 4)

            boundary = IsolationBoundary(
                boundary_id=f"boundary-{comp.id}",
                mechanism=mechanism,
                protected_components=protected,
                effectiveness_score=round(effectiveness, 4),
                failure_leak_probability=leak_prob,
                components_behind=len(protected),
            )
            boundaries.append(boundary)
            protected_set.add(comp.id)
            protected_set.update(protected)

        all_ids = set(self._graph.components.keys())
        unprotected = sorted(all_ids - protected_set)

        if not self._graph.components:
            overall = 0.0
        elif not boundaries:
            overall = 0.0
        else:
            total_eff = sum(b.effectiveness_score for b in boundaries)
            overall = round(
                min(100.0, (total_eff / len(boundaries)) * 100.0), 2
            )

        gap = round(
            (len(unprotected) / max(len(self._graph.components), 1)) * 100.0, 2
        )

        return ContainmentStrategy(
            boundaries=boundaries,
            overall_containment_score=overall,
            unprotected_components=unprotected,
            containment_gap_score=gap,
        )

    # ------------------------------------------------------------------
    # 7. Temporal Blast Radius
    # ------------------------------------------------------------------

    def calculate_temporal_progression(
        self, component_id: str
    ) -> TemporalProgression:
        """Model how blast radius propagates over time."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return TemporalProgression(origin_component_id=component_id)

        cascade = self.calculate_cascade_depth(component_id)
        if cascade.total_affected == 0:
            snap = TemporalBlastRadius(
                origin_component_id=component_id,
                phase=TemporalPhase.IMMEDIATE,
                elapsed_seconds=0.0,
                affected_count=0,
                affected_components=[],
                cumulative_user_impact_percent=0.0,
                cumulative_revenue_loss=0.0,
            )
            return TemporalProgression(
                origin_component_id=component_id,
                snapshots=[snap],
                time_to_full_propagation_seconds=0.0,
                peak_affected_count=0,
                peak_user_impact_percent=0.0,
            )

        snapshots: List[TemporalBlastRadius] = []
        cumulative_affected: List[str] = []
        cumulative_user = 0.0
        cumulative_rev = 0.0

        for depth in sorted(cascade.components_at_depth.keys()):
            components_at = cascade.components_at_depth[depth]
            elapsed = depth * _PROPAGATION_DELAY_PER_HOP
            phase = get_temporal_phase(elapsed)

            cumulative_affected.extend(components_at)

            for cid in components_at:
                c = self._graph.get_component(cid)
                if c is not None:
                    w = component_user_weight(c.type)
                    rf = replica_mitigation_factor(c.replicas)
                    total_c = max(len(self._graph.components), 1)
                    cumulative_user += w * rf * (100.0 / total_c)
                    cumulative_rev += c.cost_profile.revenue_per_minute * rf

            snap = TemporalBlastRadius(
                origin_component_id=component_id,
                phase=phase,
                elapsed_seconds=elapsed,
                affected_count=len(cumulative_affected),
                affected_components=list(cumulative_affected),
                cumulative_user_impact_percent=round(min(100.0, cumulative_user), 2),
                cumulative_revenue_loss=round(cumulative_rev, 2),
            )
            snapshots.append(snap)

        full_time = cascade.max_depth * _PROPAGATION_DELAY_PER_HOP
        peak_count = len(cumulative_affected)
        peak_user = round(min(100.0, cumulative_user), 2)

        return TemporalProgression(
            origin_component_id=component_id,
            snapshots=snapshots,
            time_to_full_propagation_seconds=full_time,
            peak_affected_count=peak_count,
            peak_user_impact_percent=peak_user,
        )

    # ------------------------------------------------------------------
    # 8. Cross-Region Analysis
    # ------------------------------------------------------------------

    def analyze_cross_region_impact(
        self, component_id: str
    ) -> CrossRegionImpact:
        """Analyze blast radius impact across regions."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return CrossRegionImpact(origin_component_id=component_id)

        origin_region = comp.region.region or "unknown"
        affected_ids = self._graph.get_all_affected(component_id)

        region_scores: Dict[str, float] = {}
        affected_regions_set: set[str] = set()

        for aid in affected_ids:
            ac = self._graph.get_component(aid)
            if ac is None:
                continue
            r = ac.region.region or "unknown"
            affected_regions_set.add(r)
            w = component_user_weight(ac.type)
            rf = replica_mitigation_factor(ac.replicas)
            region_scores[r] = round(
                region_scores.get(r, 0.0) + w * rf * 25.0, 2
            )

        for r in region_scores:
            region_scores[r] = round(min(100.0, region_scores[r]), 2)

        cross_region = any(r != origin_region for r in affected_regions_set)

        return CrossRegionImpact(
            origin_component_id=component_id,
            origin_region=origin_region,
            affected_regions=sorted(affected_regions_set),
            region_impact_scores=region_scores,
            cross_region_propagation=cross_region,
            total_regions_affected=len(affected_regions_set),
        )

    # ------------------------------------------------------------------
    # 9. Scenario Comparison
    # ------------------------------------------------------------------

    def compare_scenarios(
        self, component_ids: List[str]
    ) -> ScenarioComparison:
        """Compare blast radii between different failure scenarios."""
        if not component_ids:
            return ScenarioComparison()

        scores: List[ComponentImpactScore] = []
        for cid in component_ids:
            scores.append(self.calculate_impact_score(cid))

        if not scores:
            return ScenarioComparison()

        ranking = [
            (s.component_id, s.total_impact_score) for s in scores
        ]
        ranking.sort(key=lambda x: x[1], reverse=True)

        values = [s.total_impact_score for s in scores]
        avg = round(sum(values) / len(values), 2) if values else 0.0

        sorted_vals = sorted(values)
        n = len(sorted_vals)
        if n % 2 == 1:
            median = sorted_vals[n // 2]
        else:
            median = round(
                (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2.0, 2
            )

        worst = ranking[0][0] if ranking else ""
        best = ranking[-1][0] if ranking else ""

        return ScenarioComparison(
            scenarios=scores,
            worst_case_component=worst,
            best_case_component=best,
            average_impact_score=avg,
            median_impact_score=median,
            risk_ranking=ranking,
        )

    # ------------------------------------------------------------------
    # 10. Blast Radius Reduction Recommendations
    # ------------------------------------------------------------------

    def generate_recommendations(self) -> List[BlastRadiusReduction]:
        """Generate recommendations for reducing blast radius."""
        recommendations: List[BlastRadiusReduction] = []
        scores = self.calculate_all_impact_scores()

        for score in scores:
            comp = self._graph.get_component(score.component_id)
            if comp is None:
                continue

            mechanism = identify_containment_mechanism(comp, self._graph)

            if score.total_impact_score >= 50.0 and mechanism == ContainmentMechanism.NONE:
                recommendations.append(
                    BlastRadiusReduction(
                        target_component_id=score.component_id,
                        recommendation=(
                            f"Add circuit breaker to {score.component_id} "
                            f"(impact score: {score.total_impact_score})"
                        ),
                        priority=RecommendationPriority.CRITICAL,
                        estimated_risk_reduction_percent=35.0,
                        estimated_implementation_hours=4.0,
                        mechanism=ContainmentMechanism.CIRCUIT_BREAKER,
                    )
                )

            if comp.replicas < 2 and score.affected_downstream_count > 0:
                priority = (
                    RecommendationPriority.HIGH
                    if score.affected_downstream_count >= 3
                    else RecommendationPriority.MEDIUM
                )
                recommendations.append(
                    BlastRadiusReduction(
                        target_component_id=score.component_id,
                        recommendation=(
                            f"Add replicas to {score.component_id} "
                            f"({score.affected_downstream_count} downstream)"
                        ),
                        priority=priority,
                        estimated_risk_reduction_percent=25.0,
                        estimated_implementation_hours=2.0,
                        mechanism=ContainmentMechanism.REDUNDANCY,
                    )
                )

            if (
                not comp.failover.enabled
                and score.total_impact_score >= 20.0
                and score.cascade_depth >= 2
            ):
                recommendations.append(
                    BlastRadiusReduction(
                        target_component_id=score.component_id,
                        recommendation=(
                            f"Enable failover for {score.component_id} "
                            f"(cascade depth: {score.cascade_depth})"
                        ),
                        priority=RecommendationPriority.HIGH,
                        estimated_risk_reduction_percent=20.0,
                        estimated_implementation_hours=6.0,
                        mechanism=ContainmentMechanism.FAILOVER,
                    )
                )

            if score.cascade_depth >= 3 and mechanism != ContainmentMechanism.BULKHEAD:
                recommendations.append(
                    BlastRadiusReduction(
                        target_component_id=score.component_id,
                        recommendation=(
                            f"Implement bulkhead isolation for {score.component_id} "
                            f"(cascade depth: {score.cascade_depth})"
                        ),
                        priority=RecommendationPriority.MEDIUM,
                        estimated_risk_reduction_percent=15.0,
                        estimated_implementation_hours=8.0,
                        mechanism=ContainmentMechanism.BULKHEAD,
                    )
                )

            if (
                comp.type in (ComponentType.DATABASE, ComponentType.STORAGE)
                and not comp.security.network_segmented
                and score.total_impact_score >= 10.0
            ):
                recommendations.append(
                    BlastRadiusReduction(
                        target_component_id=score.component_id,
                        recommendation=(
                            f"Enable network segmentation for {score.component_id} "
                            f"({comp.type.value} should be isolated)"
                        ),
                        priority=RecommendationPriority.MEDIUM,
                        estimated_risk_reduction_percent=10.0,
                        estimated_implementation_hours=4.0,
                        mechanism=ContainmentMechanism.NETWORK_SEGMENTATION,
                    )
                )

        prio_order = {
            RecommendationPriority.CRITICAL: 0,
            RecommendationPriority.HIGH: 1,
            RecommendationPriority.MEDIUM: 2,
            RecommendationPriority.LOW: 3,
        }
        recommendations.sort(key=lambda r: prio_order.get(r.priority, 99))
        return recommendations

    # ------------------------------------------------------------------
    # 11. Isolation Boundary Effectiveness
    # ------------------------------------------------------------------

    def score_isolation_boundaries(self) -> List[IsolationBoundary]:
        """Score the effectiveness of all isolation boundaries."""
        strategy = self.analyze_containment_strategy()
        return strategy.boundaries

    def calculate_boundary_effectiveness(
        self, component_id: str
    ) -> float:
        """Calculate isolation boundary effectiveness for a component.

        Returns 0.0 (no isolation) to 1.0 (perfect isolation).
        """
        comp = self._graph.get_component(component_id)
        if comp is None:
            return 0.0

        mechanism = identify_containment_mechanism(comp, self._graph)
        if mechanism == ContainmentMechanism.NONE:
            return 0.0

        base = containment_effectiveness_base(mechanism)

        if comp.replicas >= 3:
            base = min(1.0, base + 0.1)
        elif comp.replicas >= 2:
            base = min(1.0, base + 0.05)

        if comp.failover.enabled and mechanism != ContainmentMechanism.FAILOVER:
            base = min(1.0, base + 0.05)

        return round(base, 4)

    # ------------------------------------------------------------------
    # Full Report
    # ------------------------------------------------------------------

    def generate_full_report(self) -> BlastRadiusReport:
        """Generate a comprehensive blast radius report for the entire graph."""
        now = datetime.now(timezone.utc).isoformat()

        impact_scores = self.calculate_all_impact_scores()
        cascade_results = [
            self.calculate_cascade_depth(s.component_id) for s in impact_scores
        ]
        user_impacts = [
            self.estimate_user_impact(s.component_id) for s in impact_scores
        ]
        revenue_impacts = [
            self.calculate_revenue_impact(s.component_id) for s in impact_scores
        ]
        temporal = [
            self.calculate_temporal_progression(s.component_id)
            for s in impact_scores
        ]
        cross_region = [
            self.analyze_cross_region_impact(s.component_id)
            for s in impact_scores
        ]
        containment = self.analyze_containment_strategy()
        recommendations = self.generate_recommendations()
        comparison = self.compare_scenarios(
            [s.component_id for s in impact_scores]
        )

        if impact_scores:
            total = sum(s.total_impact_score for s in impact_scores)
            overall_risk = round(total / len(impact_scores), 2)
        else:
            overall_risk = 0.0

        dep_count = len(self._graph.all_dependency_edges())

        return BlastRadiusReport(
            timestamp=now,
            graph_component_count=len(self._graph.components),
            graph_dependency_count=dep_count,
            impact_scores=impact_scores,
            cascade_results=cascade_results,
            user_impacts=user_impacts,
            revenue_impacts=revenue_impacts,
            temporal_progressions=temporal,
            cross_region_impacts=cross_region,
            containment_strategy=containment,
            recommendations=recommendations,
            scenario_comparison=comparison,
            overall_risk_score=overall_risk,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _estimate_user_percent(
        self, component_id: str, cascade_depth: int, affected_count: int
    ) -> float:
        """Estimate user impact percentage based on component properties."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return 0.0

        type_w = component_user_weight(comp.type)
        rep_f = replica_mitigation_factor(comp.replicas)
        total = len(self._graph.components)

        base = type_w * 100.0 * rep_f

        if total > 1:
            breadth_factor = min(1.5, 1.0 + affected_count / max(total - 1, 1))
        else:
            breadth_factor = 1.0

        raw = base * 0.5 * breadth_factor
        return round(min(100.0, raw), 2)

    def _estimate_revenue_per_hour(
        self, component_id: str, impact_score: float
    ) -> float:
        """Estimate revenue impact per hour based on impact score."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return 0.0

        cost = comp.cost_profile
        rev_w = component_revenue_weight(comp.type)
        base_rev = cost.revenue_per_minute * 60.0 * rev_w
        score_factor = impact_score / 100.0
        return round(base_rev * score_factor, 2)

    def _build_propagation_paths(
        self, origin_id: str, affected_ids: set[str]
    ) -> List[List[str]]:
        """Build propagation paths from origin through affected components."""
        if not affected_ids:
            return []

        paths: List[List[str]] = []
        self._dfs_paths(origin_id, [origin_id], set(), paths, affected_ids)
        paths.sort(key=len, reverse=True)
        return paths[:10]

    def _dfs_paths(
        self,
        current_id: str,
        current_path: List[str],
        visited: set[str],
        all_paths: List[List[str]],
        affected_ids: set[str],
    ) -> None:
        """DFS to enumerate propagation paths."""
        visited.add(current_id)
        dependents = self._graph.get_dependents(current_id)
        reachable = [
            d for d in dependents
            if d.id not in visited and d.id in affected_ids
        ]

        if not reachable:
            if len(current_path) > 1:
                all_paths.append(list(current_path))
        else:
            for dep in reachable:
                current_path.append(dep.id)
                self._dfs_paths(
                    dep.id, current_path, visited, all_paths, affected_ids
                )
                current_path.pop()

        visited.discard(current_id)

    def _determine_affected_flows(
        self, comp: Component, affected_ids: set[str]
    ) -> List[str]:
        """Determine which user flows are affected by a component failure."""
        flows: List[str] = []

        _type_to_flow = {
            ComponentType.WEB_SERVER: "web_requests",
            ComponentType.LOAD_BALANCER: "web_requests",
            ComponentType.APP_SERVER: "api_requests",
            ComponentType.DATABASE: "data_operations",
            ComponentType.CACHE: "cached_reads",
            ComponentType.QUEUE: "async_processing",
            ComponentType.DNS: "dns_resolution",
            ComponentType.STORAGE: "file_operations",
            ComponentType.EXTERNAL_API: "external_integrations",
        }

        flow = _type_to_flow.get(comp.type)
        if flow is not None:
            flows.append(flow)

        for aid in affected_ids:
            ac = self._graph.get_component(aid)
            if ac is None:
                continue
            f = _type_to_flow.get(ac.type)
            if f is not None and f not in flows:
                flows.append(f)

        return flows

    def _identify_revenue_streams(self, comp: Component) -> List[str]:
        """Identify revenue streams impacted by a component's failure."""
        streams: List[str] = []
        if comp.cost_profile.revenue_per_minute > 0:
            streams.append("direct_revenue")
        if comp.cost_profile.monthly_contract_value > 0:
            streams.append("contract_revenue")
        if comp.cost_profile.customer_ltv > 0:
            streams.append("customer_lifetime_value")
        if comp.cost_profile.hourly_infra_cost > 0:
            streams.append("infrastructure_cost")
        if not streams:
            streams.append("indirect_operational")
        return streams
