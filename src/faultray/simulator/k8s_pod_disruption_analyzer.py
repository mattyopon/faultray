"""K8s Pod Disruption Analyzer -- analyze PDB configurations and their impact.

Evaluates Kubernetes Pod Disruption Budget (PDB) configurations and their
impact on infrastructure resilience.  Covers PDB policy evaluation
(minAvailable / maxUnavailable), rolling-update interaction, node-drain
simulation, multi-PDB conflict detection, eviction-budget calculation,
maintenance-window optimization, StatefulSet vs Deployment differences,
PDB violation risk scoring, cross-namespace interaction analysis, and
optimal PDB setting recommendations.
"""

from __future__ import annotations

import logging
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PDBPolicyType(str, Enum):
    """Type of PDB policy constraint."""

    MIN_AVAILABLE = "min_available"
    MAX_UNAVAILABLE = "max_unavailable"


class WorkloadType(str, Enum):
    """Kubernetes workload controller type."""

    DEPLOYMENT = "deployment"
    STATEFUL_SET = "stateful_set"
    DAEMON_SET = "daemon_set"
    REPLICA_SET = "replica_set"


class DisruptionSeverity(str, Enum):
    """Severity levels for disruption findings."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ConflictCategory(str, Enum):
    """Categories of PDB conflicts."""

    OVERLAPPING_SELECTOR = "overlapping_selector"
    CONTRADICTORY_BUDGET = "contradictory_budget"
    OVER_CONSTRAINED = "over_constrained"
    CROSS_NAMESPACE_CLASH = "cross_namespace_clash"
    STALE_SELECTOR = "stale_selector"


class DrainOutcome(str, Enum):
    """Outcome of a node drain attempt."""

    SUCCESS = "success"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"


class MaintenanceStrategy(str, Enum):
    """Maintenance-window scheduling strategies."""

    ROLLING = "rolling"
    BLUE_GREEN = "blue_green"
    CANARY = "canary"
    BIG_BANG = "big_bang"


class RiskLevel(str, Enum):
    """Overall risk-level classification."""

    MINIMAL = "minimal"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class RecommendationPriority(str, Enum):
    """Priority levels for PDB recommendations."""

    MUST = "must"
    SHOULD = "should"
    NICE_TO_HAVE = "nice_to_have"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PDBSpec:
    """Specification for a single Pod Disruption Budget."""

    pdb_id: str
    namespace: str = "default"
    policy_type: PDBPolicyType = PDBPolicyType.MAX_UNAVAILABLE
    value: int = 1
    percentage: bool = False
    selector_labels: dict[str, str] = field(default_factory=dict)
    component_ids: list[str] = field(default_factory=list)
    workload_type: WorkloadType = WorkloadType.DEPLOYMENT
    total_replicas: int = 3
    ready_replicas: int = 3
    max_surge: int = 1
    max_unavailable_rolling: int = 0
    created_at: str = ""


@dataclass
class EvictionBudget:
    """Calculated eviction budget for a set of pods."""

    component_id: str
    pdb_id: str
    total_replicas: int
    ready_replicas: int
    allowed_disruptions: int
    min_available_effective: int
    max_unavailable_effective: int
    current_unavailable: int
    headroom: int
    is_blocked: bool


@dataclass
class RollingUpdateImpact:
    """Impact analysis of PDB on rolling update process."""

    component_id: str
    pdb_id: str
    workload_type: WorkloadType
    max_surge: int
    max_unavailable_rolling: int
    effective_parallelism: int
    estimated_duration_seconds: float
    pod_transitions: int
    can_proceed: bool
    blocking_reason: str = ""
    severity: DisruptionSeverity = DisruptionSeverity.INFO


@dataclass
class DrainSimulationResult:
    """Result of simulating a node drain operation."""

    node_id: str
    outcome: DrainOutcome
    pods_evicted: int
    pods_blocked: int
    total_pods: int
    blocking_pdbs: list[str] = field(default_factory=list)
    eviction_order: list[str] = field(default_factory=list)
    estimated_duration_seconds: float = 0.0
    connection_drain_seconds: float = 0.0
    cascade_affected: list[str] = field(default_factory=list)
    severity: DisruptionSeverity = DisruptionSeverity.INFO


@dataclass
class PDBConflict:
    """A detected conflict between PDB configurations."""

    pdb_a_id: str
    pdb_b_id: str
    conflict_category: ConflictCategory
    severity: DisruptionSeverity
    description: str
    affected_components: list[str] = field(default_factory=list)
    recommendation: str = ""


@dataclass
class MaintenanceWindow:
    """A proposed maintenance window for disruption."""

    start_hour: int  # 0-23
    end_hour: int  # 0-23
    day_of_week: int  # 0=Mon .. 6=Sun
    strategy: MaintenanceStrategy
    estimated_duration_minutes: float
    risk_score: float  # 0-100
    max_concurrent_disruptions: int
    affected_namespaces: list[str] = field(default_factory=list)
    recommendation: str = ""


@dataclass
class ViolationRisk:
    """Risk assessment for a PDB violation scenario."""

    pdb_id: str
    component_id: str
    risk_level: RiskLevel
    risk_score: float  # 0-100
    violation_probability: float  # 0-1
    contributing_factors: list[str] = field(default_factory=list)
    mitigations: list[str] = field(default_factory=list)


@dataclass
class CrossNamespaceInteraction:
    """Cross-namespace PDB interaction analysis."""

    namespace_a: str
    namespace_b: str
    pdb_a_id: str
    pdb_b_id: str
    shared_node_pool: bool
    resource_contention: bool
    eviction_priority_conflict: bool
    severity: DisruptionSeverity
    description: str


@dataclass
class PDBRecommendation:
    """A recommendation for improving PDB configuration."""

    component_id: str
    priority: RecommendationPriority
    category: str
    description: str
    current_config: str
    suggested_config: str
    estimated_improvement: str


@dataclass
class WorkloadPDBDifference:
    """Differences in PDB behavior between workload types."""

    workload_type: WorkloadType
    ordered_pod_management: bool
    supports_parallel_scaling: bool
    volume_affinity: bool
    identity_stability: bool
    pdb_effectiveness_score: float  # 0-100
    notes: list[str] = field(default_factory=list)


@dataclass
class AnalysisReport:
    """Complete PDB disruption analysis report."""

    timestamp: str
    total_pdbs: int
    total_components: int
    eviction_budgets: list[EvictionBudget] = field(default_factory=list)
    rolling_update_impacts: list[RollingUpdateImpact] = field(default_factory=list)
    drain_results: list[DrainSimulationResult] = field(default_factory=list)
    conflicts: list[PDBConflict] = field(default_factory=list)
    violation_risks: list[ViolationRisk] = field(default_factory=list)
    cross_namespace_interactions: list[CrossNamespaceInteraction] = field(
        default_factory=list,
    )
    maintenance_windows: list[MaintenanceWindow] = field(default_factory=list)
    recommendations: list[PDBRecommendation] = field(default_factory=list)
    workload_differences: list[WorkloadPDBDifference] = field(default_factory=list)
    overall_risk_level: RiskLevel = RiskLevel.MINIMAL
    overall_risk_score: float = 0.0


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _calculate_min_available(spec: PDBSpec) -> int:
    """Resolve the effective minAvailable count for a PDB spec."""
    if spec.policy_type == PDBPolicyType.MIN_AVAILABLE:
        if spec.percentage:
            return max(1, math.ceil(spec.total_replicas * spec.value / 100))
        return min(spec.value, spec.total_replicas)
    # maxUnavailable -> derive minAvailable
    if spec.percentage:
        max_unav = max(1, math.floor(spec.total_replicas * spec.value / 100))
    else:
        max_unav = spec.value
    return max(0, spec.total_replicas - max_unav)


def _calculate_max_unavailable(spec: PDBSpec) -> int:
    """Resolve the effective maxUnavailable count for a PDB spec."""
    if spec.policy_type == PDBPolicyType.MAX_UNAVAILABLE:
        if spec.percentage:
            return max(1, math.floor(spec.total_replicas * spec.value / 100))
        return min(spec.value, spec.total_replicas)
    # minAvailable -> derive maxUnavailable
    if spec.percentage:
        min_avail = max(1, math.ceil(spec.total_replicas * spec.value / 100))
    else:
        min_avail = spec.value
    return max(0, spec.total_replicas - min_avail)


def _labels_overlap(a: dict[str, str], b: dict[str, str]) -> bool:
    """Return True when any key in *a* also appears in *b* with the same value."""
    if not a or not b:
        return False
    for k, v in a.items():
        if k in b and b[k] == v:
            return True
    return False


def _severity_rank(s: DisruptionSeverity) -> int:
    """Map severity to a numeric rank for comparison (higher = worse)."""
    mapping = {
        DisruptionSeverity.INFO: 0,
        DisruptionSeverity.LOW: 1,
        DisruptionSeverity.MEDIUM: 2,
        DisruptionSeverity.HIGH: 3,
        DisruptionSeverity.CRITICAL: 4,
    }
    return mapping.get(s, 0)


def _risk_level_from_score(score: float) -> RiskLevel:
    """Map a 0-100 risk score to a RiskLevel."""
    if score >= 80:
        return RiskLevel.CRITICAL
    if score >= 60:
        return RiskLevel.HIGH
    if score >= 40:
        return RiskLevel.MODERATE
    if score >= 20:
        return RiskLevel.LOW
    return RiskLevel.MINIMAL


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp *value* between *lo* and *hi*."""
    return max(lo, min(hi, value))


def _workload_duration_multiplier(wtype: WorkloadType) -> float:
    """Return a duration multiplier reflecting workload controller behaviour."""
    if wtype == WorkloadType.STATEFUL_SET:
        return 1.5
    if wtype == WorkloadType.DAEMON_SET:
        return 1.2
    return 1.0


# ---------------------------------------------------------------------------
# Main analyzer class
# ---------------------------------------------------------------------------

class PodDisruptionAnalyzer:
    """Analyze PDB configurations against an InfraGraph.

    Usage::

        graph = InfraGraph()
        graph.add_component(Component(id="app", name="app",
                                      type=ComponentType.APP_SERVER))
        analyzer = PodDisruptionAnalyzer(graph)
        spec = PDBSpec(pdb_id="pdb-app", component_ids=["app"],
                       total_replicas=5)
        analyzer.add_pdb(spec)
        report = analyzer.analyze()
    """

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph
        self._pdbs: dict[str, PDBSpec] = {}
        self._node_assignments: dict[str, list[str]] = {}  # node->[comp ids]
        self._traffic_weights: dict[str, float] = {}  # comp_id->weight 0-1
        self._custom_drain_timeout: float = 300.0

    # -- configuration API ---------------------------------------------------

    def add_pdb(self, spec: PDBSpec) -> None:
        """Register a PDB spec."""
        self._pdbs[spec.pdb_id] = spec

    def remove_pdb(self, pdb_id: str) -> bool:
        """Remove a PDB spec by id. Returns True if removed."""
        return self._pdbs.pop(pdb_id, None) is not None

    def set_node_assignment(self, node_id: str, component_ids: list[str]) -> None:
        """Declare which components are hosted on a given node."""
        self._node_assignments[node_id] = list(component_ids)

    def set_traffic_weight(self, component_id: str, weight: float) -> None:
        """Set relative traffic weight for a component (0-1)."""
        self._traffic_weights[component_id] = _clamp(weight, 0.0, 1.0)

    def set_drain_timeout(self, timeout: float) -> None:
        """Set global drain timeout in seconds."""
        self._custom_drain_timeout = max(0.0, timeout)

    @property
    def pdbs(self) -> dict[str, PDBSpec]:
        """Expose registered PDBs (read-only view)."""
        return dict(self._pdbs)

    @property
    def node_assignments(self) -> dict[str, list[str]]:
        """Expose node assignments (read-only copy)."""
        return {k: list(v) for k, v in self._node_assignments.items()}

    # -- PDB policy evaluation -----------------------------------------------

    def evaluate_pdb_policy(self, pdb_id: str) -> EvictionBudget | None:
        """Evaluate a single PDB and return its eviction budget."""
        spec = self._pdbs.get(pdb_id)
        if spec is None:
            return None

        min_avail = _calculate_min_available(spec)
        max_unav = _calculate_max_unavailable(spec)
        current_unavailable = max(0, spec.total_replicas - spec.ready_replicas)
        allowed = max(0, max_unav - current_unavailable)
        headroom = max(0, spec.ready_replicas - min_avail)
        is_blocked = allowed == 0

        comp_id = spec.component_ids[0] if spec.component_ids else ""
        return EvictionBudget(
            component_id=comp_id,
            pdb_id=pdb_id,
            total_replicas=spec.total_replicas,
            ready_replicas=spec.ready_replicas,
            allowed_disruptions=allowed,
            min_available_effective=min_avail,
            max_unavailable_effective=max_unav,
            current_unavailable=current_unavailable,
            headroom=headroom,
            is_blocked=is_blocked,
        )

    def evaluate_all_pdbs(self) -> list[EvictionBudget]:
        """Evaluate every registered PDB and return eviction budgets."""
        results: list[EvictionBudget] = []
        for pdb_id in self._pdbs:
            budget = self.evaluate_pdb_policy(pdb_id)
            if budget is not None:
                results.append(budget)
        return results

    # -- rolling-update impact -----------------------------------------------

    def analyze_rolling_update(self, pdb_id: str) -> RollingUpdateImpact | None:
        """Determine how a PDB constrains rolling update progress."""
        spec = self._pdbs.get(pdb_id)
        if spec is None:
            return None

        comp_id = spec.component_ids[0] if spec.component_ids else ""
        max_unav = _calculate_max_unavailable(spec)
        effective_parallelism = min(max_unav, spec.max_surge + max_unav)
        if effective_parallelism <= 0:
            effective_parallelism = 1

        pod_transition_time = 30.0
        transitions_needed = spec.total_replicas
        batches = math.ceil(transitions_needed / effective_parallelism)
        estimated_duration = batches * pod_transition_time
        estimated_duration *= _workload_duration_multiplier(spec.workload_type)

        can_proceed = max_unav > 0
        blocking_reason = ""
        severity = DisruptionSeverity.INFO

        if not can_proceed:
            blocking_reason = (
                f"PDB {pdb_id} allows 0 unavailable pods; rolling update is blocked."
            )
            severity = DisruptionSeverity.CRITICAL
        elif effective_parallelism == 1:
            severity = DisruptionSeverity.MEDIUM
            blocking_reason = "Parallelism limited to 1; update will be slow."
        elif effective_parallelism < max(1, spec.total_replicas // 3):
            severity = DisruptionSeverity.LOW

        if spec.workload_type == WorkloadType.STATEFUL_SET:
            if severity == DisruptionSeverity.INFO:
                severity = DisruptionSeverity.LOW

        return RollingUpdateImpact(
            component_id=comp_id,
            pdb_id=pdb_id,
            workload_type=spec.workload_type,
            max_surge=spec.max_surge,
            max_unavailable_rolling=spec.max_unavailable_rolling,
            effective_parallelism=effective_parallelism,
            estimated_duration_seconds=estimated_duration,
            pod_transitions=transitions_needed,
            can_proceed=can_proceed,
            blocking_reason=blocking_reason,
            severity=severity,
        )

    def analyze_all_rolling_updates(self) -> list[RollingUpdateImpact]:
        """Analyze rolling update impact for all PDBs."""
        results: list[RollingUpdateImpact] = []
        for pdb_id in self._pdbs:
            impact = self.analyze_rolling_update(pdb_id)
            if impact is not None:
                results.append(impact)
        return results

    # -- node-drain simulation -----------------------------------------------

    def simulate_node_drain(self, node_id: str) -> DrainSimulationResult:
        """Simulate draining a node and report on PDB blocking."""
        components_on_node = self._node_assignments.get(node_id, [])
        total_pods = len(components_on_node)
        pods_evicted = 0
        pods_blocked = 0
        blocking_pdbs: list[str] = []
        eviction_order: list[str] = []
        severity = DisruptionSeverity.INFO
        cascade_affected: list[str] = []

        if total_pods == 0:
            return DrainSimulationResult(
                node_id=node_id,
                outcome=DrainOutcome.SUCCESS,
                pods_evicted=0,
                pods_blocked=0,
                total_pods=0,
                estimated_duration_seconds=0.0,
                severity=DisruptionSeverity.INFO,
            )

        # Map component -> relevant PDBs
        comp_pdbs: dict[str, list[PDBSpec]] = {}
        for spec in self._pdbs.values():
            for cid in spec.component_ids:
                comp_pdbs.setdefault(cid, []).append(spec)

        for cid in components_on_node:
            pdbs_for_comp = comp_pdbs.get(cid, [])
            if not pdbs_for_comp:
                pods_evicted += 1
                eviction_order.append(cid)
                continue

            blocked = False
            for spec in pdbs_for_comp:
                budget = self.evaluate_pdb_policy(spec.pdb_id)
                if budget is not None and budget.is_blocked:
                    blocked = True
                    if spec.pdb_id not in blocking_pdbs:
                        blocking_pdbs.append(spec.pdb_id)

            if blocked:
                pods_blocked += 1
            else:
                pods_evicted += 1
                eviction_order.append(cid)

        # Cascade impact via graph
        for cid in eviction_order:
            affected = self._graph.get_all_affected(cid)
            for a in affected:
                if a not in cascade_affected and a not in components_on_node:
                    cascade_affected.append(a)

        if pods_blocked == 0:
            outcome = DrainOutcome.SUCCESS
        elif pods_evicted == 0:
            outcome = DrainOutcome.BLOCKED
            severity = DisruptionSeverity.CRITICAL
        else:
            outcome = DrainOutcome.PARTIAL
            severity = DisruptionSeverity.HIGH

        estimated_duration = pods_evicted * 5.0
        connection_drain = 0.0
        if pods_blocked > 0:
            estimated_duration += self._custom_drain_timeout
            connection_drain = self._custom_drain_timeout

        return DrainSimulationResult(
            node_id=node_id,
            outcome=outcome,
            pods_evicted=pods_evicted,
            pods_blocked=pods_blocked,
            total_pods=total_pods,
            blocking_pdbs=blocking_pdbs,
            eviction_order=eviction_order,
            estimated_duration_seconds=estimated_duration,
            connection_drain_seconds=connection_drain,
            cascade_affected=cascade_affected,
            severity=severity,
        )

    def simulate_multi_node_drain(
        self, node_ids: list[str],
    ) -> list[DrainSimulationResult]:
        """Simulate draining multiple nodes sequentially."""
        results: list[DrainSimulationResult] = []
        for nid in node_ids:
            result = self.simulate_node_drain(nid)
            results.append(result)
        return results

    # -- multi-PDB conflict detection ----------------------------------------

    def detect_conflicts(self) -> list[PDBConflict]:
        """Detect conflicts between registered PDBs."""
        conflicts: list[PDBConflict] = []
        pdb_list = list(self._pdbs.values())

        for i in range(len(pdb_list)):
            for j in range(i + 1, len(pdb_list)):
                a = pdb_list[i]
                b = pdb_list[j]
                new_conflicts = self._compare_pdbs(a, b)
                conflicts.extend(new_conflicts)

        # Check over-constraining per component
        comp_pdbs: dict[str, list[PDBSpec]] = {}
        for spec in self._pdbs.values():
            for cid in spec.component_ids:
                comp_pdbs.setdefault(cid, []).append(spec)

        for cid, specs in comp_pdbs.items():
            if len(specs) > 1:
                total_min = sum(_calculate_min_available(s) for s in specs)
                comp = self._graph.get_component(cid)
                replicas = comp.replicas if comp else specs[0].total_replicas
                if total_min > replicas:
                    conflicts.append(PDBConflict(
                        pdb_a_id=specs[0].pdb_id,
                        pdb_b_id=specs[1].pdb_id,
                        conflict_category=ConflictCategory.OVER_CONSTRAINED,
                        severity=DisruptionSeverity.CRITICAL,
                        description=(
                            f"Combined minAvailable ({total_min}) exceeds "
                            f"replica count ({replicas}) for component {cid}."
                        ),
                        affected_components=[cid],
                        recommendation=(
                            "Reduce minAvailable in one or more PDBs, or "
                            "increase replica count."
                        ),
                    ))

        return conflicts

    def _compare_pdbs(self, a: PDBSpec, b: PDBSpec) -> list[PDBConflict]:
        """Compare two PDB specs for conflicts."""
        conflicts: list[PDBConflict] = []

        shared_components = set(a.component_ids) & set(b.component_ids)
        label_overlap = _labels_overlap(a.selector_labels, b.selector_labels)

        if not shared_components and not label_overlap:
            return conflicts

        # Overlapping selector
        if label_overlap and not shared_components:
            conflicts.append(PDBConflict(
                pdb_a_id=a.pdb_id,
                pdb_b_id=b.pdb_id,
                conflict_category=ConflictCategory.OVERLAPPING_SELECTOR,
                severity=DisruptionSeverity.MEDIUM,
                description=(
                    f"PDBs {a.pdb_id} and {b.pdb_id} have overlapping "
                    "label selectors which may match the same pods."
                ),
                affected_components=sorted(
                    set(a.component_ids) | set(b.component_ids),
                ),
                recommendation="Use more specific label selectors.",
            ))

        # Contradictory budget (different policy types on same pods)
        if shared_components or label_overlap:
            if a.policy_type != b.policy_type:
                conflicts.append(PDBConflict(
                    pdb_a_id=a.pdb_id,
                    pdb_b_id=b.pdb_id,
                    conflict_category=ConflictCategory.CONTRADICTORY_BUDGET,
                    severity=DisruptionSeverity.HIGH,
                    description=(
                        f"PDBs {a.pdb_id} ({a.policy_type.value}) and "
                        f"{b.pdb_id} ({b.policy_type.value}) use different "
                        "policy types on the same pods."
                    ),
                    affected_components=sorted(shared_components),
                    recommendation=(
                        "Standardize on one policy type (preferably maxUnavailable)."
                    ),
                ))

        # Cross-namespace clash
        if a.namespace != b.namespace and shared_components:
            conflicts.append(PDBConflict(
                pdb_a_id=a.pdb_id,
                pdb_b_id=b.pdb_id,
                conflict_category=ConflictCategory.CROSS_NAMESPACE_CLASH,
                severity=DisruptionSeverity.HIGH,
                description=(
                    f"PDBs {a.pdb_id} (ns={a.namespace}) and "
                    f"{b.pdb_id} (ns={b.namespace}) target the same components "
                    "across namespaces."
                ),
                affected_components=sorted(shared_components),
                recommendation=(
                    "Ensure PDBs are namespace-scoped and components are "
                    "not shared across namespace boundaries."
                ),
            ))

        # Stale selector: same labels but one PDB targets 0 ready replicas
        if label_overlap:
            for spec in (a, b):
                if spec.ready_replicas == 0 and spec.total_replicas > 0:
                    other = b if spec is a else a
                    conflicts.append(PDBConflict(
                        pdb_a_id=spec.pdb_id,
                        pdb_b_id=other.pdb_id,
                        conflict_category=ConflictCategory.STALE_SELECTOR,
                        severity=DisruptionSeverity.LOW,
                        description=(
                            f"PDB {spec.pdb_id} has 0 ready replicas; "
                            "selector may be stale or workload is down."
                        ),
                        affected_components=list(spec.component_ids),
                        recommendation=(
                            "Verify the PDB selector still matches a running workload."
                        ),
                    ))

        return conflicts

    # -- eviction budget calculation -----------------------------------------

    def calculate_eviction_budget(self, component_id: str) -> EvictionBudget | None:
        """Calculate the aggregate eviction budget for a component."""
        relevant_pdbs = [
            spec for spec in self._pdbs.values()
            if component_id in spec.component_ids
        ]
        if not relevant_pdbs:
            comp = self._graph.get_component(component_id)
            if comp is None:
                return None
            return EvictionBudget(
                component_id=component_id,
                pdb_id="",
                total_replicas=comp.replicas,
                ready_replicas=comp.replicas,
                allowed_disruptions=comp.replicas,
                min_available_effective=0,
                max_unavailable_effective=comp.replicas,
                current_unavailable=0,
                headroom=comp.replicas,
                is_blocked=False,
            )

        # Take the most restrictive PDB
        most_restrictive: EvictionBudget | None = None
        for spec in relevant_pdbs:
            budget = self.evaluate_pdb_policy(spec.pdb_id)
            if budget is None:
                continue
            if most_restrictive is None:
                most_restrictive = budget
            elif budget.allowed_disruptions < most_restrictive.allowed_disruptions:
                most_restrictive = budget

        if most_restrictive is not None:
            most_restrictive.component_id = component_id
        return most_restrictive

    # -- maintenance window optimization -------------------------------------

    def optimize_maintenance_windows(
        self,
        available_hours: list[tuple[int, int]] | None = None,
    ) -> list[MaintenanceWindow]:
        """Suggest optimal maintenance windows based on PDB constraints."""
        if available_hours is None:
            available_hours = [(2, 6), (22, 2)]

        windows: list[MaintenanceWindow] = []
        namespaces = sorted({s.namespace for s in self._pdbs.values()})
        budgets = self.evaluate_all_pdbs()

        total_allowed = sum(b.allowed_disruptions for b in budgets)
        total_replicas = sum(b.total_replicas for b in budgets)

        if total_replicas == 0:
            return windows

        disruption_ratio = total_allowed / total_replicas if total_replicas > 0 else 0

        for start_hour, end_hour in available_hours:
            if end_hour > start_hour:
                duration_hours = end_hour - start_hour
            else:
                duration_hours = (24 - start_hour) + end_hour

            duration_minutes = duration_hours * 60.0

            risk_score = _clamp(100.0 - disruption_ratio * 100.0)
            if total_allowed == 0:
                risk_score = 100.0

            if disruption_ratio > 0.5:
                strategy = MaintenanceStrategy.ROLLING
            elif disruption_ratio > 0.2:
                strategy = MaintenanceStrategy.CANARY
            elif disruption_ratio > 0.0:
                strategy = MaintenanceStrategy.BLUE_GREEN
            else:
                strategy = MaintenanceStrategy.BIG_BANG
                risk_score = 100.0

            max_concurrent = total_allowed
            recommendation = self._maintenance_recommendation(
                strategy, disruption_ratio, total_allowed,
            )

            windows.append(MaintenanceWindow(
                start_hour=start_hour,
                end_hour=end_hour,
                day_of_week=6,
                strategy=strategy,
                estimated_duration_minutes=duration_minutes,
                risk_score=risk_score,
                max_concurrent_disruptions=max_concurrent,
                affected_namespaces=namespaces,
                recommendation=recommendation,
            ))

        windows.sort(key=lambda w: w.risk_score)
        return windows

    def _maintenance_recommendation(
        self,
        strategy: MaintenanceStrategy,
        ratio: float,
        allowed: int,
    ) -> str:
        """Generate a maintenance recommendation string."""
        if strategy == MaintenanceStrategy.BIG_BANG:
            return (
                "No disruptions allowed by current PDB configuration. "
                "Consider temporarily relaxing PDB constraints or "
                "increasing replica count before maintenance."
            )
        if strategy == MaintenanceStrategy.BLUE_GREEN:
            return (
                f"Low disruption budget ({allowed} pods). Use blue-green "
                "deployment to minimize risk."
            )
        if strategy == MaintenanceStrategy.CANARY:
            return (
                f"Moderate disruption budget ({allowed} pods). "
                "Canary strategy recommended for safe validation."
            )
        return (
            f"Healthy disruption budget ({allowed} pods). "
            "Rolling strategy is safe and efficient."
        )

    # -- StatefulSet vs Deployment differences --------------------------------

    def analyze_workload_differences(self) -> list[WorkloadPDBDifference]:
        """Describe PDB behavioral differences across workload types."""
        results: list[WorkloadPDBDifference] = []

        type_configs: dict[WorkloadType, dict[str, Any]] = {
            WorkloadType.DEPLOYMENT: {
                "ordered": False,
                "parallel": True,
                "volume": False,
                "identity": False,
                "effectiveness": 90.0,
                "notes": [
                    "Pods are interchangeable; PDB primarily guards capacity.",
                    "maxUnavailable is the preferred policy type.",
                ],
            },
            WorkloadType.STATEFUL_SET: {
                "ordered": True,
                "parallel": False,
                "volume": True,
                "identity": True,
                "effectiveness": 75.0,
                "notes": [
                    "Pods have stable identities and ordered startup/shutdown.",
                    "PDB must account for volume re-attach delays.",
                    "Consider using minAvailable for quorum-based workloads.",
                ],
            },
            WorkloadType.DAEMON_SET: {
                "ordered": False,
                "parallel": True,
                "volume": False,
                "identity": False,
                "effectiveness": 60.0,
                "notes": [
                    "One pod per node; PDB has limited effect.",
                    "Node drain is the primary disruption vector.",
                ],
            },
            WorkloadType.REPLICA_SET: {
                "ordered": False,
                "parallel": True,
                "volume": False,
                "identity": False,
                "effectiveness": 85.0,
                "notes": [
                    "Similar to Deployment; PDB guards capacity.",
                    "Typically managed by a Deployment controller.",
                ],
            },
        }

        for wtype, cfg in type_configs.items():
            results.append(WorkloadPDBDifference(
                workload_type=wtype,
                ordered_pod_management=cfg["ordered"],
                supports_parallel_scaling=cfg["parallel"],
                volume_affinity=cfg["volume"],
                identity_stability=cfg["identity"],
                pdb_effectiveness_score=cfg["effectiveness"],
                notes=list(cfg["notes"]),
            ))

        return results

    # -- PDB violation risk scoring ------------------------------------------

    def assess_violation_risk(self, pdb_id: str) -> ViolationRisk | None:
        """Score the risk of PDB violations for a specific PDB."""
        spec = self._pdbs.get(pdb_id)
        if spec is None:
            return None

        comp_id = spec.component_ids[0] if spec.component_ids else ""
        factors: list[str] = []
        mitigations: list[str] = []
        score = 0.0

        # Factor 1: headroom ratio
        budget = self.evaluate_pdb_policy(pdb_id)
        if budget is not None:
            headroom_ratio = (
                budget.headroom / budget.total_replicas
                if budget.total_replicas > 0
                else 0.0
            )
            if headroom_ratio < 0.1:
                score += 35.0
                factors.append(
                    f"Very low headroom ({budget.headroom}/{budget.total_replicas})."
                )
                mitigations.append("Increase replica count to add headroom.")
            elif headroom_ratio < 0.3:
                score += 20.0
                factors.append(
                    f"Low headroom ({budget.headroom}/{budget.total_replicas})."
                )
            elif headroom_ratio < 0.5:
                score += 10.0
                factors.append("Moderate headroom.")

            if budget.is_blocked:
                score += 30.0
                factors.append("Currently blocked (0 allowed disruptions).")
                mitigations.append(
                    "Check for unhealthy pods or reduce minAvailable."
                )

        # Factor 2: workload type
        if spec.workload_type == WorkloadType.STATEFUL_SET:
            score += 10.0
            factors.append("StatefulSet workloads are more sensitive to disruption.")
            mitigations.append("Ensure volume re-attach time is accounted for.")
        elif spec.workload_type == WorkloadType.DAEMON_SET:
            score += 5.0
            factors.append("DaemonSet: PDB has limited effect on per-node pods.")

        # Factor 3: low replica count
        if spec.total_replicas <= 2:
            score += 20.0
            factors.append(
                f"Low replica count ({spec.total_replicas}); single failure "
                "can trigger violation."
            )
            mitigations.append("Increase to at least 3 replicas.")
        elif spec.total_replicas <= 4:
            score += 10.0
            factors.append(f"Moderate replica count ({spec.total_replicas}).")

        # Factor 4: percentage-based PDB on small sets
        if spec.percentage and spec.total_replicas <= 3:
            score += 10.0
            factors.append(
                "Percentage-based PDB on small replica set can produce "
                "unexpected rounding."
            )
            mitigations.append("Use absolute values for small replica sets.")

        # Factor 5: node concentration
        node_count = 0
        for node_comps in self._node_assignments.values():
            if any(cid in spec.component_ids for cid in node_comps):
                node_count += 1
        if node_count == 1 and spec.total_replicas > 1:
            score += 15.0
            factors.append("All pods appear to be on a single node.")
            mitigations.append("Spread pods across multiple nodes.")
        elif 0 < node_count < spec.total_replicas:
            score += 5.0
            factors.append("Pod-to-node ratio suggests potential concentration.")

        # Factor 6: traffic weight
        traffic = self._traffic_weights.get(comp_id, 0.0)
        if traffic > 0.8:
            score += 10.0
            factors.append("High traffic weight increases blast radius of disruption.")
        elif traffic > 0.5:
            score += 5.0
            factors.append("Moderate traffic weight.")

        score = _clamp(score)
        risk_level = _risk_level_from_score(score)
        violation_prob = _clamp(score / 100.0, 0.0, 1.0)

        return ViolationRisk(
            pdb_id=pdb_id,
            component_id=comp_id,
            risk_level=risk_level,
            risk_score=score,
            violation_probability=violation_prob,
            contributing_factors=factors,
            mitigations=mitigations,
        )

    def assess_all_violation_risks(self) -> list[ViolationRisk]:
        """Assess violation risk for every registered PDB."""
        results: list[ViolationRisk] = []
        for pdb_id in self._pdbs:
            risk = self.assess_violation_risk(pdb_id)
            if risk is not None:
                results.append(risk)
        return results

    # -- cross-namespace interaction analysis --------------------------------

    def analyze_cross_namespace(self) -> list[CrossNamespaceInteraction]:
        """Identify cross-namespace PDB interactions."""
        interactions: list[CrossNamespaceInteraction] = []
        pdb_list = list(self._pdbs.values())

        for i in range(len(pdb_list)):
            for j in range(i + 1, len(pdb_list)):
                a = pdb_list[i]
                b = pdb_list[j]
                if a.namespace == b.namespace:
                    continue

                shared_nodes = self._shared_nodes(a, b)
                resource_contention = self._resource_contention(a, b)
                priority_conflict = self._eviction_priority_conflict(a, b)

                if not shared_nodes and not resource_contention and not priority_conflict:
                    continue

                severity = DisruptionSeverity.LOW
                if shared_nodes and resource_contention:
                    severity = DisruptionSeverity.HIGH
                elif shared_nodes or resource_contention:
                    severity = DisruptionSeverity.MEDIUM
                if priority_conflict:
                    severity = max(
                        severity, DisruptionSeverity.MEDIUM,
                        key=_severity_rank,
                    )

                desc_parts: list[str] = []
                if shared_nodes:
                    desc_parts.append("share node pool")
                if resource_contention:
                    desc_parts.append("have resource contention")
                if priority_conflict:
                    desc_parts.append("have eviction priority conflict")

                interactions.append(CrossNamespaceInteraction(
                    namespace_a=a.namespace,
                    namespace_b=b.namespace,
                    pdb_a_id=a.pdb_id,
                    pdb_b_id=b.pdb_id,
                    shared_node_pool=shared_nodes,
                    resource_contention=resource_contention,
                    eviction_priority_conflict=priority_conflict,
                    severity=severity,
                    description=(
                        f"PDBs {a.pdb_id} (ns={a.namespace}) and "
                        f"{b.pdb_id} (ns={b.namespace}) "
                        + ", ".join(desc_parts) + "."
                    ),
                ))

        return interactions

    def _shared_nodes(self, a: PDBSpec, b: PDBSpec) -> bool:
        """Check if two PDB specs have components on the same node."""
        a_comps = set(a.component_ids)
        b_comps = set(b.component_ids)
        for node_comps in self._node_assignments.values():
            node_set = set(node_comps)
            if node_set & a_comps and node_set & b_comps:
                return True
        return False

    def _resource_contention(self, a: PDBSpec, b: PDBSpec) -> bool:
        """Detect resource contention between two PDB-managed workloads."""
        a_replicas = a.total_replicas
        b_replicas = b.total_replicas
        a_max_unav = _calculate_max_unavailable(a)
        b_max_unav = _calculate_max_unavailable(b)

        a_ratio = a_max_unav / a_replicas if a_replicas > 0 else 0
        b_ratio = b_max_unav / b_replicas if b_replicas > 0 else 0

        return a_ratio < 0.3 and b_ratio < 0.3

    def _eviction_priority_conflict(self, a: PDBSpec, b: PDBSpec) -> bool:
        """Check if two PDBs in different namespaces compete for eviction."""
        a_min = _calculate_min_available(a)
        b_min = _calculate_min_available(b)
        return (
            a_min >= a.total_replicas - 1
            and b_min >= b.total_replicas - 1
            and self._shared_nodes(a, b)
        )

    # -- recommendations for optimal PDB settings ----------------------------

    def generate_recommendations(self) -> list[PDBRecommendation]:
        """Generate actionable recommendations for all registered PDBs."""
        recs: list[PDBRecommendation] = []

        for spec in self._pdbs.values():
            comp_id = spec.component_ids[0] if spec.component_ids else ""
            budget = self.evaluate_pdb_policy(spec.pdb_id)
            if budget is None:
                continue

            # R1: blocked evictions
            if budget.is_blocked:
                recs.append(PDBRecommendation(
                    component_id=comp_id,
                    priority=RecommendationPriority.MUST,
                    category="blocked_eviction",
                    description=(
                        "PDB is currently blocking all evictions. "
                        "This prevents node maintenance and upgrades."
                    ),
                    current_config=f"{spec.policy_type.value}={spec.value}",
                    suggested_config="Increase replicas or reduce minAvailable",
                    estimated_improvement="Unblock node maintenance",
                ))

            # R2: zero headroom (but not blocked)
            if budget.headroom == 0 and not budget.is_blocked:
                recs.append(PDBRecommendation(
                    component_id=comp_id,
                    priority=RecommendationPriority.SHOULD,
                    category="zero_headroom",
                    description=(
                        "PDB allows disruptions but has zero headroom. "
                        "A single pod failure will block further evictions."
                    ),
                    current_config=(
                        f"replicas={spec.total_replicas}, "
                        f"{spec.policy_type.value}={spec.value}"
                    ),
                    suggested_config=(
                        f"Increase replicas to {spec.total_replicas + 1}"
                    ),
                    estimated_improvement="Add safety margin for pod failures",
                ))

            # R3: percentage-based on small sets
            if spec.percentage and spec.total_replicas <= 3:
                recs.append(PDBRecommendation(
                    component_id=comp_id,
                    priority=RecommendationPriority.SHOULD,
                    category="percentage_small_set",
                    description=(
                        "Percentage-based PDB on a small replica set can "
                        "produce unexpected rounding behavior."
                    ),
                    current_config=(
                        f"{spec.policy_type.value}={spec.value}%"
                    ),
                    suggested_config=(
                        f"Use absolute value: "
                        f"{spec.policy_type.value}="
                        f"{_calculate_max_unavailable(spec)}"
                    ),
                    estimated_improvement="Predictable disruption behavior",
                ))

            # R4: minAvailable equals replicas (zero tolerance)
            min_avail = _calculate_min_available(spec)
            if min_avail >= spec.total_replicas and spec.total_replicas > 0:
                recs.append(PDBRecommendation(
                    component_id=comp_id,
                    priority=RecommendationPriority.MUST,
                    category="zero_tolerance",
                    description=(
                        f"minAvailable ({min_avail}) equals or exceeds total "
                        f"replicas ({spec.total_replicas}), blocking all "
                        "disruptions."
                    ),
                    current_config=f"minAvailable={min_avail}",
                    suggested_config=(
                        f"Set minAvailable to {max(1, spec.total_replicas - 1)} "
                        f"or use maxUnavailable=1"
                    ),
                    estimated_improvement="Allow controlled disruptions",
                ))

            # R5: StatefulSet awareness
            if spec.workload_type == WorkloadType.STATEFUL_SET:
                quorum = spec.total_replicas // 2 + 1
                recs.append(PDBRecommendation(
                    component_id=comp_id,
                    priority=RecommendationPriority.NICE_TO_HAVE,
                    category="statefulset_awareness",
                    description=(
                        "StatefulSet workloads benefit from minAvailable "
                        "policies that respect quorum requirements."
                    ),
                    current_config=f"{spec.policy_type.value}={spec.value}",
                    suggested_config=(
                        f"Consider minAvailable={quorum} for quorum safety"
                    ),
                    estimated_improvement="Maintain quorum during disruptions",
                ))

            # R6: single-replica workload with PDB
            if spec.total_replicas == 1:
                recs.append(PDBRecommendation(
                    component_id=comp_id,
                    priority=RecommendationPriority.MUST,
                    category="single_replica",
                    description=(
                        "Single-replica workload with PDB will either always "
                        "block or always allow disruptions."
                    ),
                    current_config=(
                        f"replicas=1, {spec.policy_type.value}={spec.value}"
                    ),
                    suggested_config="Scale to at least 2 replicas",
                    estimated_improvement="Enable meaningful PDB protection",
                ))

            # R7: high max_unavailable relative to replicas
            max_unav = _calculate_max_unavailable(spec)
            if max_unav > spec.total_replicas // 2 and spec.total_replicas > 2:
                recs.append(PDBRecommendation(
                    component_id=comp_id,
                    priority=RecommendationPriority.SHOULD,
                    category="high_max_unavailable",
                    description=(
                        f"maxUnavailable ({max_unav}) is more than half the "
                        f"total replicas ({spec.total_replicas}), which may "
                        "cause capacity issues during disruptions."
                    ),
                    current_config=f"maxUnavailable={max_unav}",
                    suggested_config=(
                        f"maxUnavailable={max(1, spec.total_replicas // 3)}"
                    ),
                    estimated_improvement="Reduce blast radius of disruptions",
                ))

            # R8: DaemonSet with restrictive PDB
            if spec.workload_type == WorkloadType.DAEMON_SET and max_unav <= 0:
                recs.append(PDBRecommendation(
                    component_id=comp_id,
                    priority=RecommendationPriority.SHOULD,
                    category="daemonset_restrictive",
                    description=(
                        "DaemonSet with fully restrictive PDB will block "
                        "all node drains and cluster upgrades."
                    ),
                    current_config=f"maxUnavailable=0 (DaemonSet)",
                    suggested_config="maxUnavailable=1",
                    estimated_improvement="Allow node-by-node upgrades",
                ))

        return recs

    # -- full analysis -------------------------------------------------------

    def analyze(self) -> AnalysisReport:
        """Run the complete PDB disruption analysis and return a report."""
        timestamp = datetime.now(timezone.utc).isoformat()

        eviction_budgets = self.evaluate_all_pdbs()
        rolling_impacts = self.analyze_all_rolling_updates()
        drain_results = self.simulate_multi_node_drain(
            list(self._node_assignments.keys()),
        )
        conflicts = self.detect_conflicts()
        violation_risks = self.assess_all_violation_risks()
        cross_ns = self.analyze_cross_namespace()
        maintenance = self.optimize_maintenance_windows()
        recommendations = self.generate_recommendations()
        workload_diffs = self.analyze_workload_differences()

        # Overall risk
        risk_scores = [r.risk_score for r in violation_risks]
        conflict_penalties = sum(
            10.0 if c.severity == DisruptionSeverity.CRITICAL else
            7.0 if c.severity == DisruptionSeverity.HIGH else 5.0
            for c in conflicts
        )
        drain_penalties = sum(
            15.0 if d.outcome == DrainOutcome.BLOCKED else
            5.0 if d.outcome == DrainOutcome.PARTIAL else 0.0
            for d in drain_results
        )

        avg_risk = statistics.mean(risk_scores) if risk_scores else 0.0
        overall_score = _clamp(avg_risk + conflict_penalties + drain_penalties)
        overall_level = _risk_level_from_score(overall_score)

        return AnalysisReport(
            timestamp=timestamp,
            total_pdbs=len(self._pdbs),
            total_components=len(self._graph.components),
            eviction_budgets=eviction_budgets,
            rolling_update_impacts=rolling_impacts,
            drain_results=drain_results,
            conflicts=conflicts,
            violation_risks=violation_risks,
            cross_namespace_interactions=cross_ns,
            maintenance_windows=maintenance,
            recommendations=recommendations,
            workload_differences=workload_diffs,
            overall_risk_level=overall_level,
            overall_risk_score=overall_score,
        )

    # -- utility queries -----------------------------------------------------

    def get_blocked_components(self) -> list[str]:
        """Return IDs of components whose PDB blocks all evictions."""
        blocked: list[str] = []
        for spec in self._pdbs.values():
            budget = self.evaluate_pdb_policy(spec.pdb_id)
            if budget is not None and budget.is_blocked:
                for cid in spec.component_ids:
                    if cid not in blocked:
                        blocked.append(cid)
        return blocked

    def get_safest_drain_order(self) -> list[str]:
        """Suggest the safest order in which to drain nodes."""
        node_scores: list[tuple[str, float]] = []
        for node_id in self._node_assignments:
            result = self.simulate_node_drain(node_id)
            score = result.pods_blocked * 10.0 + len(result.cascade_affected) * 5.0
            node_scores.append((node_id, score))
        node_scores.sort(key=lambda x: x[1])
        return [n for n, _ in node_scores]

    def pdb_coverage_ratio(self) -> float:
        """Return fraction of graph components covered by at least one PDB."""
        all_comp_ids = set(self._graph.components.keys())
        if not all_comp_ids:
            return 0.0
        covered: set[str] = set()
        for spec in self._pdbs.values():
            covered.update(cid for cid in spec.component_ids if cid in all_comp_ids)
        return len(covered) / len(all_comp_ids)

    def find_unprotected_components(self) -> list[str]:
        """Return component IDs that have no PDB coverage."""
        all_comp_ids = set(self._graph.components.keys())
        covered: set[str] = set()
        for spec in self._pdbs.values():
            covered.update(cid for cid in spec.component_ids if cid in all_comp_ids)
        return sorted(all_comp_ids - covered)

    def count_by_workload_type(self) -> dict[str, int]:
        """Return count of PDBs grouped by workload type."""
        counts: dict[str, int] = {}
        for spec in self._pdbs.values():
            key = spec.workload_type.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    def max_disruption_capacity(self) -> int:
        """Return the total number of pods that can be disrupted across all PDBs."""
        total = 0
        for pdb_id in self._pdbs:
            budget = self.evaluate_pdb_policy(pdb_id)
            if budget is not None:
                total += budget.allowed_disruptions
        return total

    def summary(self) -> dict[str, Any]:
        """Return a compact summary dict."""
        budgets = self.evaluate_all_pdbs()
        conflicts = self.detect_conflicts()
        risks = self.assess_all_violation_risks()

        blocked_count = sum(1 for b in budgets if b.is_blocked)
        total_allowed = sum(b.allowed_disruptions for b in budgets)
        avg_risk = (
            statistics.mean([r.risk_score for r in risks]) if risks else 0.0
        )

        return {
            "total_pdbs": len(self._pdbs),
            "total_components": len(self._graph.components),
            "blocked_pdbs": blocked_count,
            "total_allowed_disruptions": total_allowed,
            "conflicts": len(conflicts),
            "average_risk_score": round(avg_risk, 1),
            "coverage_ratio": round(self.pdb_coverage_ratio(), 2),
        }
