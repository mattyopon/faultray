# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Dependency Injection Analyzer.

Analyzes runtime dependency injection patterns and their resilience
implications.  Covers circular dependency detection, singleton vs
transient lifecycle risk, service locator anti-pattern detection,
missing binding / registration detection, scope mismatch analysis,
lazy initialization failure cascades, factory pattern resilience
evaluation, dependency tree depth analysis, hot-swap capability
assessment, configuration-driven dependency switching risks,
interface-based decoupling score, and dependency graph complexity
metrics (cyclomatic, fan-in / fan-out).
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_SAFE_TREE_DEPTH = 6
MAX_SAFE_FAN_OUT = 8
MAX_SAFE_FAN_IN = 10
SINGLETON_RISK_WEIGHT = 0.8
TRANSIENT_RISK_WEIGHT = 0.3
SCOPED_RISK_WEIGHT = 0.5
LAZY_INIT_FAILURE_PROBABILITY = 0.05
FACTORY_RESILIENCE_BONUS = 0.15
HOT_SWAP_BONUS = 0.2
CONFIG_SWITCH_PENALTY = 0.1
INTERFACE_DECOUPLING_IDEAL = 0.8
CYCLOMATIC_THRESHOLD = 15
SERVICE_LOCATOR_PENALTY = 0.25


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Lifecycle(str, Enum):
    """Component dependency injection lifecycle."""

    SINGLETON = "singleton"
    TRANSIENT = "transient"
    SCOPED = "scoped"


class BindingStatus(str, Enum):
    """Registration / binding status."""

    REGISTERED = "registered"
    MISSING = "missing"
    CONDITIONAL = "conditional"


class InjectionPattern(str, Enum):
    """Injection pattern classification."""

    CONSTRUCTOR = "constructor"
    PROPERTY = "property"
    METHOD = "method"
    SERVICE_LOCATOR = "service_locator"
    FACTORY = "factory"


class RiskLevel(str, Enum):
    """Risk severity level."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ScopeMismatchType(str, Enum):
    """Types of scope mismatch."""

    SINGLETON_DEPENDS_ON_TRANSIENT = "singleton_depends_on_transient"
    SINGLETON_DEPENDS_ON_SCOPED = "singleton_depends_on_scoped"
    SCOPED_DEPENDS_ON_TRANSIENT = "scoped_depends_on_transient"
    NONE = "none"


# ---------------------------------------------------------------------------
# Configuration dataclasses
# ---------------------------------------------------------------------------


@dataclass
class DIRegistration:
    """Represents a single DI registration / binding."""

    component_id: str
    lifecycle: Lifecycle = Lifecycle.TRANSIENT
    binding_status: BindingStatus = BindingStatus.REGISTERED
    injection_pattern: InjectionPattern = InjectionPattern.CONSTRUCTOR
    interface_name: str = ""
    has_factory: bool = False
    supports_hot_swap: bool = False
    config_driven: bool = False
    lazy_init: bool = False


@dataclass
class DIContainerConfig:
    """Full DI container configuration for analysis."""

    registrations: list[DIRegistration] = field(default_factory=list)
    allow_missing_bindings: bool = False
    strict_scope_validation: bool = True
    max_tree_depth: int = MAX_SAFE_TREE_DEPTH


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CircularDependencyResult:
    """Result of circular dependency detection."""

    has_cycles: bool = False
    cycles: list[list[str]] = field(default_factory=list)
    max_cycle_length: int = 0
    risk_level: RiskLevel = RiskLevel.INFO
    affected_components: list[str] = field(default_factory=list)
    impact_description: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class LifecycleRiskResult:
    """Result of singleton vs transient lifecycle risk assessment."""

    component_id: str = ""
    lifecycle: Lifecycle = Lifecycle.TRANSIENT
    risk_score: float = 0.0
    risk_level: RiskLevel = RiskLevel.INFO
    singleton_count: int = 0
    transient_count: int = 0
    scoped_count: int = 0
    state_sharing_risk: float = 0.0
    memory_pressure_risk: float = 0.0
    thread_safety_risk: float = 0.0
    recommendations: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ServiceLocatorResult:
    """Result of service locator anti-pattern detection."""

    detected: bool = False
    locator_components: list[str] = field(default_factory=list)
    severity: RiskLevel = RiskLevel.INFO
    testability_impact: float = 0.0
    coupling_score: float = 0.0
    recommendations: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class MissingBindingResult:
    """Result of missing binding / registration detection."""

    has_missing: bool = False
    missing_bindings: list[str] = field(default_factory=list)
    conditional_bindings: list[str] = field(default_factory=list)
    total_registrations: int = 0
    coverage_ratio: float = 1.0
    risk_level: RiskLevel = RiskLevel.INFO
    recommendations: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ScopeMismatchResult:
    """Result of scope mismatch analysis."""

    has_mismatches: bool = False
    mismatches: list[dict[str, str]] = field(default_factory=list)
    mismatch_count: int = 0
    captive_dependency_risk: float = 0.0
    risk_level: RiskLevel = RiskLevel.INFO
    recommendations: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class LazyInitResult:
    """Result of lazy initialization failure cascade analysis."""

    lazy_components: list[str] = field(default_factory=list)
    lazy_count: int = 0
    cascade_risk: float = 0.0
    startup_failure_probability: float = 0.0
    cold_start_latency_ms: float = 0.0
    risk_level: RiskLevel = RiskLevel.INFO
    failure_paths: list[list[str]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class FactoryResilienceResult:
    """Result of factory pattern resilience evaluation."""

    factory_components: list[str] = field(default_factory=list)
    factory_count: int = 0
    resilience_score: float = 0.0
    abstraction_benefit: float = 0.0
    complexity_cost: float = 0.0
    risk_level: RiskLevel = RiskLevel.INFO
    recommendations: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class TreeDepthResult:
    """Result of dependency tree depth analysis."""

    max_depth: int = 0
    avg_depth: float = 0.0
    deepest_path: list[str] = field(default_factory=list)
    depth_distribution: dict[int, int] = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.INFO
    exceeds_threshold: bool = False
    recommendations: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class HotSwapResult:
    """Result of hot-swap capability assessment."""

    swappable_components: list[str] = field(default_factory=list)
    non_swappable_components: list[str] = field(default_factory=list)
    swap_coverage: float = 0.0
    runtime_flexibility_score: float = 0.0
    risk_level: RiskLevel = RiskLevel.INFO
    recommendations: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ConfigSwitchRiskResult:
    """Result of configuration-driven dependency switching risk analysis."""

    config_driven_components: list[str] = field(default_factory=list)
    total_config_driven: int = 0
    misconfiguration_risk: float = 0.0
    environment_drift_risk: float = 0.0
    rollback_complexity: float = 0.0
    risk_level: RiskLevel = RiskLevel.INFO
    recommendations: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class DecouplingScoreResult:
    """Result of interface-based decoupling score computation."""

    overall_score: float = 0.0
    interface_coverage: float = 0.0
    concrete_coupling_ratio: float = 0.0
    abstraction_depth: float = 0.0
    risk_level: RiskLevel = RiskLevel.INFO
    per_component: dict[str, float] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ComplexityMetricsResult:
    """Result of dependency graph complexity metrics."""

    cyclomatic_complexity: int = 0
    total_edges: int = 0
    total_nodes: int = 0
    max_fan_in: int = 0
    max_fan_out: int = 0
    avg_fan_in: float = 0.0
    avg_fan_out: float = 0.0
    fan_in_distribution: dict[str, int] = field(default_factory=dict)
    fan_out_distribution: dict[str, int] = field(default_factory=dict)
    instability_index: float = 0.0
    abstractness_index: float = 0.0
    distance_from_main_seq: float = 0.0
    risk_level: RiskLevel = RiskLevel.INFO
    recommendations: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class DIAnalysisSummary:
    """Full DI analysis summary aggregating all sub-results."""

    overall_risk_score: float = 0.0
    overall_risk_level: RiskLevel = RiskLevel.INFO
    circular_dependency: CircularDependencyResult = field(
        default_factory=CircularDependencyResult
    )
    lifecycle_risks: list[LifecycleRiskResult] = field(default_factory=list)
    service_locator: ServiceLocatorResult = field(
        default_factory=ServiceLocatorResult
    )
    missing_bindings: MissingBindingResult = field(
        default_factory=MissingBindingResult
    )
    scope_mismatches: ScopeMismatchResult = field(
        default_factory=ScopeMismatchResult
    )
    lazy_init: LazyInitResult = field(default_factory=LazyInitResult)
    factory_resilience: FactoryResilienceResult = field(
        default_factory=FactoryResilienceResult
    )
    tree_depth: TreeDepthResult = field(default_factory=TreeDepthResult)
    hot_swap: HotSwapResult = field(default_factory=HotSwapResult)
    config_switch: ConfigSwitchRiskResult = field(
        default_factory=ConfigSwitchRiskResult
    )
    decoupling: DecouplingScoreResult = field(
        default_factory=DecouplingScoreResult
    )
    complexity: ComplexityMetricsResult = field(
        default_factory=ComplexityMetricsResult
    )
    recommendations: list[str] = field(default_factory=list)
    analyzed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp *value* between *lo* and *hi*."""
    return max(lo, min(hi, value))


def _risk_from_score(score: float) -> RiskLevel:
    """Map a 0-1 risk score to a ``RiskLevel``."""
    if score >= 0.8:
        return RiskLevel.CRITICAL
    if score >= 0.6:
        return RiskLevel.HIGH
    if score >= 0.4:
        return RiskLevel.MEDIUM
    if score >= 0.2:
        return RiskLevel.LOW
    return RiskLevel.INFO


def _lifecycle_risk_weight(lifecycle: Lifecycle) -> float:
    """Return the inherent risk weight for a lifecycle type."""
    if lifecycle == Lifecycle.SINGLETON:
        return SINGLETON_RISK_WEIGHT
    if lifecycle == Lifecycle.SCOPED:
        return SCOPED_RISK_WEIGHT
    return TRANSIENT_RISK_WEIGHT


def _scope_mismatch_type(
    source_lc: Lifecycle, target_lc: Lifecycle
) -> ScopeMismatchType:
    """Determine the scope mismatch type between two lifecycles."""
    if source_lc == Lifecycle.SINGLETON:
        if target_lc == Lifecycle.TRANSIENT:
            return ScopeMismatchType.SINGLETON_DEPENDS_ON_TRANSIENT
        if target_lc == Lifecycle.SCOPED:
            return ScopeMismatchType.SINGLETON_DEPENDS_ON_SCOPED
    if source_lc == Lifecycle.SCOPED and target_lc == Lifecycle.TRANSIENT:
        return ScopeMismatchType.SCOPED_DEPENDS_ON_TRANSIENT
    return ScopeMismatchType.NONE


def _compute_cascade_probability(
    lazy_count: int, total: int
) -> float:
    """Estimate cascade failure probability from lazy init components."""
    if total == 0:
        return 0.0
    ratio = lazy_count / total
    # Probability grows exponentially with ratio of lazy components
    return _clamp(1.0 - math.exp(-3.0 * ratio))


def _compute_cold_start_latency(lazy_count: int) -> float:
    """Estimate additional cold-start latency (ms) due to lazy init."""
    # Each lazy component adds ~50ms of cold-start overhead on average
    return lazy_count * 50.0


def _cyclomatic_complexity(nodes: int, edges: int, connected: int) -> int:
    """Compute cyclomatic complexity for a directed graph.

    M = E - N + 2P  where P is connected components.
    """
    return max(1, edges - nodes + 2 * connected)


def _instability_index(fan_in: int, fan_out: int) -> float:
    """Compute instability = fan_out / (fan_in + fan_out).

    Result between 0 (maximally stable) and 1 (maximally unstable).
    """
    total = fan_in + fan_out
    if total == 0:
        return 0.0
    return fan_out / total


def _distance_from_main_sequence(
    abstractness: float, instability: float
) -> float:
    """Compute the distance from the main sequence.

    D = |A + I - 1|
    """
    return abs(abstractness + instability - 1.0)


def _compute_fan_in(graph: InfraGraph, component_id: str) -> int:
    """Count inbound dependencies (components that depend on this one)."""
    return len(graph.get_dependents(component_id))


def _compute_fan_out(graph: InfraGraph, component_id: str) -> int:
    """Count outbound dependencies (components this one depends on)."""
    return len(graph.get_dependencies(component_id))


def _find_all_paths_dfs(
    graph: InfraGraph,
    start: str,
    visited: set[str] | None = None,
) -> list[list[str]]:
    """Find all directed paths from *start* via DFS (non-cyclic)."""
    if visited is None:
        visited = set()
    paths: list[list[str]] = []
    visited.add(start)
    deps = graph.get_dependencies(start)
    if not deps:
        paths.append([start])
    else:
        for dep in deps:
            if dep.id not in visited:
                for sub_path in _find_all_paths_dfs(graph, dep.id, set(visited)):
                    paths.append([start] + sub_path)
            else:
                paths.append([start])
    return paths


def _detect_cycles_in_graph(graph: InfraGraph) -> list[list[str]]:
    """Detect all simple cycles in the infrastructure graph.

    Uses iterative DFS with a color-based approach.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    comp_ids = list(graph.components.keys())
    color: dict[str, int] = {cid: WHITE for cid in comp_ids}
    parent: dict[str, str | None] = {cid: None for cid in comp_ids}
    cycles: list[list[str]] = []

    for start_id in comp_ids:
        if color[start_id] != WHITE:
            continue
        stack: list[tuple[str, int]] = [(start_id, 0)]
        color[start_id] = GRAY
        while stack:
            node, idx = stack[-1]
            neighbors = [d.id for d in graph.get_dependencies(node)]
            if idx < len(neighbors):
                stack[-1] = (node, idx + 1)
                nb = neighbors[idx]
                if nb not in color:
                    continue
                if color[nb] == WHITE:
                    color[nb] = GRAY
                    parent[nb] = node
                    stack.append((nb, 0))
                elif color[nb] == GRAY:
                    # Reconstruct cycle
                    cycle = [nb]
                    cur = node
                    while cur != nb:
                        cycle.append(cur)
                        cur = parent.get(cur, nb)  # type: ignore[arg-type]
                        if cur is None:
                            break
                    cycle.append(nb)
                    cycle.reverse()
                    cycles.append(cycle)
            else:
                color[node] = BLACK
                stack.pop()
    return cycles


def _count_connected_components(graph: InfraGraph) -> int:
    """Count weakly connected components in the graph."""
    comp_ids = set(graph.components.keys())
    if not comp_ids:
        return 0
    visited: set[str] = set()
    count = 0
    for cid in comp_ids:
        if cid in visited:
            continue
        count += 1
        queue: deque[str] = deque([cid])
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            # Forward edges
            for dep in graph.get_dependencies(current):
                if dep.id not in visited and dep.id in comp_ids:
                    queue.append(dep.id)
            # Backward edges
            for dep in graph.get_dependents(current):
                if dep.id not in visited and dep.id in comp_ids:
                    queue.append(dep.id)
    return count


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class DependencyInjectionAnalyzer:
    """Analyzes DI patterns for resilience risk.

    Parameters
    ----------
    graph:
        The infrastructure graph to analyze.
    config:
        Optional DI container configuration.  When ``None`` a default
        configuration is synthesized from the graph.
    """

    def __init__(
        self,
        graph: InfraGraph,
        config: DIContainerConfig | None = None,
    ) -> None:
        self._graph = graph
        self._config = config or DIContainerConfig()
        self._registrations: dict[str, DIRegistration] = {}
        for reg in self._config.registrations:
            self._registrations[reg.component_id] = reg

    # -- helpers --

    def _get_reg(self, component_id: str) -> DIRegistration | None:
        return self._registrations.get(component_id)

    def _all_component_ids(self) -> list[str]:
        return list(self._graph.components.keys())

    # -----------------------------------------------------------------------
    # Analysis methods
    # -----------------------------------------------------------------------

    def detect_circular_dependencies(self) -> CircularDependencyResult:
        """Detect circular dependencies in the graph and assess impact."""
        cycles = _detect_cycles_in_graph(self._graph)
        affected: set[str] = set()
        max_len = 0
        for cycle in cycles:
            for cid in cycle:
                affected.add(cid)
            if len(cycle) > max_len:
                max_len = len(cycle)

        has_cycles = len(cycles) > 0
        risk_score = _clamp(len(cycles) * 0.2 + max_len * 0.05)
        impact = ""
        if has_cycles:
            impact = (
                f"Detected {len(cycles)} circular dependency chain(s) "
                f"affecting {len(affected)} component(s).  Circular "
                "dependencies can cause infinite resolution loops, "
                "deadlocks, and make the system untestable."
            )
        return CircularDependencyResult(
            has_cycles=has_cycles,
            cycles=cycles,
            max_cycle_length=max_len,
            risk_level=_risk_from_score(risk_score),
            affected_components=sorted(affected),
            impact_description=impact,
        )

    def assess_lifecycle_risks(self) -> list[LifecycleRiskResult]:
        """Assess lifecycle-related risks for each registered component."""
        results: list[LifecycleRiskResult] = []
        singleton_count = sum(
            1 for r in self._registrations.values()
            if r.lifecycle == Lifecycle.SINGLETON
        )
        transient_count = sum(
            1 for r in self._registrations.values()
            if r.lifecycle == Lifecycle.TRANSIENT
        )
        scoped_count = sum(
            1 for r in self._registrations.values()
            if r.lifecycle == Lifecycle.SCOPED
        )

        for cid, reg in self._registrations.items():
            weight = _lifecycle_risk_weight(reg.lifecycle)
            fan_in = _compute_fan_in(self._graph, cid)
            fan_out = _compute_fan_out(self._graph, cid)

            state_risk = 0.0
            memory_risk = 0.0
            thread_risk = 0.0
            recs: list[str] = []

            if reg.lifecycle == Lifecycle.SINGLETON:
                state_risk = _clamp(fan_in * 0.1)
                memory_risk = _clamp(0.3 + fan_out * 0.05)
                thread_risk = _clamp(0.4 + fan_in * 0.05)
                if fan_in > 3:
                    recs.append(
                        f"Singleton '{cid}' has high fan-in ({fan_in}). "
                        "Consider using scoped lifecycle to reduce "
                        "shared state risks."
                    )
                if thread_risk > 0.5:
                    recs.append(
                        f"Singleton '{cid}' may need thread-safety "
                        "mechanisms (locks, concurrent collections)."
                    )
            elif reg.lifecycle == Lifecycle.TRANSIENT:
                memory_risk = _clamp(fan_in * 0.05)
                state_risk = 0.0
                thread_risk = 0.0
                if fan_in > MAX_SAFE_FAN_IN:
                    recs.append(
                        f"Transient '{cid}' is created frequently "
                        f"({fan_in} consumers). Consider pooling or "
                        "scoped lifecycle."
                    )
            else:  # SCOPED
                state_risk = _clamp(fan_in * 0.05)
                memory_risk = _clamp(0.1 + fan_out * 0.03)
                thread_risk = _clamp(0.1 + fan_in * 0.03)

            combined = _clamp(
                weight * (state_risk + memory_risk + thread_risk) / 3.0
            )
            results.append(LifecycleRiskResult(
                component_id=cid,
                lifecycle=reg.lifecycle,
                risk_score=round(combined, 4),
                risk_level=_risk_from_score(combined),
                singleton_count=singleton_count,
                transient_count=transient_count,
                scoped_count=scoped_count,
                state_sharing_risk=round(state_risk, 4),
                memory_pressure_risk=round(memory_risk, 4),
                thread_safety_risk=round(thread_risk, 4),
                recommendations=recs,
            ))
        return results

    def detect_service_locator(self) -> ServiceLocatorResult:
        """Detect service locator anti-pattern usage."""
        locators: list[str] = []
        for cid, reg in self._registrations.items():
            if reg.injection_pattern == InjectionPattern.SERVICE_LOCATOR:
                locators.append(cid)

        detected = len(locators) > 0
        total = len(self._registrations)
        coupling = _clamp(len(locators) / max(total, 1))
        testability = _clamp(len(locators) * SERVICE_LOCATOR_PENALTY)
        severity = _risk_from_score(testability)

        recs: list[str] = []
        if detected:
            recs.append(
                "Replace service locator with constructor injection to "
                "improve testability and make dependencies explicit."
            )
            for loc in locators:
                recs.append(
                    f"Component '{loc}' uses service locator. "
                    "Refactor to constructor injection."
                )

        return ServiceLocatorResult(
            detected=detected,
            locator_components=locators,
            severity=severity,
            testability_impact=round(testability, 4),
            coupling_score=round(coupling, 4),
            recommendations=recs,
        )

    def detect_missing_bindings(self) -> MissingBindingResult:
        """Detect missing or conditional bindings."""
        comp_ids = self._all_component_ids()
        missing: list[str] = []
        conditional: list[str] = []

        for cid in comp_ids:
            reg = self._get_reg(cid)
            if reg is None:
                missing.append(cid)
            elif reg.binding_status == BindingStatus.MISSING:
                missing.append(cid)
            elif reg.binding_status == BindingStatus.CONDITIONAL:
                conditional.append(cid)

        total = len(comp_ids)
        registered_count = total - len(missing)
        coverage = 1.0 if total == 0 else registered_count / total
        risk_score = _clamp(1.0 - coverage + len(conditional) * 0.05)
        recs: list[str] = []
        if missing:
            recs.append(
                f"{len(missing)} component(s) have no DI registration. "
                "Add explicit bindings to prevent runtime resolution failures."
            )
        if conditional:
            recs.append(
                f"{len(conditional)} binding(s) are conditional. Ensure "
                "all environments have valid configuration."
            )

        return MissingBindingResult(
            has_missing=len(missing) > 0,
            missing_bindings=missing,
            conditional_bindings=conditional,
            total_registrations=registered_count,
            coverage_ratio=round(coverage, 4),
            risk_level=_risk_from_score(risk_score),
            recommendations=recs,
        )

    def analyze_scope_mismatches(self) -> ScopeMismatchResult:
        """Detect scope mismatches (e.g. singleton depending on transient)."""
        mismatches: list[dict[str, str]] = []
        for cid, reg in self._registrations.items():
            deps = self._graph.get_dependencies(cid)
            for dep_comp in deps:
                dep_reg = self._get_reg(dep_comp.id)
                if dep_reg is None:
                    continue
                mm_type = _scope_mismatch_type(reg.lifecycle, dep_reg.lifecycle)
                if mm_type != ScopeMismatchType.NONE:
                    mismatches.append({
                        "source": cid,
                        "target": dep_comp.id,
                        "source_lifecycle": reg.lifecycle.value,
                        "target_lifecycle": dep_reg.lifecycle.value,
                        "mismatch_type": mm_type.value,
                    })

        count = len(mismatches)
        captive_risk = _clamp(count * 0.15)
        recs: list[str] = []
        if count > 0:
            recs.append(
                f"{count} scope mismatch(es) detected. A longer-lived "
                "component depending on a shorter-lived one creates "
                "captive dependency risks."
            )
            for mm in mismatches:
                recs.append(
                    f"'{mm['source']}' ({mm['source_lifecycle']}) depends on "
                    f"'{mm['target']}' ({mm['target_lifecycle']}). "
                    f"Type: {mm['mismatch_type']}."
                )

        return ScopeMismatchResult(
            has_mismatches=count > 0,
            mismatches=mismatches,
            mismatch_count=count,
            captive_dependency_risk=round(captive_risk, 4),
            risk_level=_risk_from_score(captive_risk),
            recommendations=recs,
        )

    def analyze_lazy_init_cascades(self) -> LazyInitResult:
        """Analyze lazy initialization failure cascades."""
        lazy_ids: list[str] = []
        for cid, reg in self._registrations.items():
            if reg.lazy_init:
                lazy_ids.append(cid)

        total = len(self._registrations)
        cascade_prob = _compute_cascade_probability(len(lazy_ids), total)
        cold_start = _compute_cold_start_latency(len(lazy_ids))

        # Build failure paths: find paths from lazy components
        failure_paths: list[list[str]] = []
        for lid in lazy_ids:
            paths = _find_all_paths_dfs(self._graph, lid)
            failure_paths.extend(paths)

        startup_prob = _clamp(
            1.0 - math.pow(1.0 - LAZY_INIT_FAILURE_PROBABILITY, max(len(lazy_ids), 1))
        )

        recs: list[str] = []
        if len(lazy_ids) > 0:
            recs.append(
                f"{len(lazy_ids)} component(s) use lazy initialization. "
                "Consider eager initialization for critical path "
                "components to fail fast on startup."
            )
        if cascade_prob > 0.3:
            recs.append(
                "High cascade risk from lazy init. Add health checks "
                "and circuit breakers around lazily initialized services."
            )

        return LazyInitResult(
            lazy_components=lazy_ids,
            lazy_count=len(lazy_ids),
            cascade_risk=round(cascade_prob, 4),
            startup_failure_probability=round(startup_prob, 4),
            cold_start_latency_ms=round(cold_start, 2),
            risk_level=_risk_from_score(cascade_prob),
            failure_paths=failure_paths,
            recommendations=recs,
        )

    def evaluate_factory_resilience(self) -> FactoryResilienceResult:
        """Evaluate factory pattern resilience contribution."""
        factory_ids: list[str] = []
        for cid, reg in self._registrations.items():
            if reg.has_factory or reg.injection_pattern == InjectionPattern.FACTORY:
                factory_ids.append(cid)

        total = max(len(self._registrations), 1)
        factory_ratio = len(factory_ids) / total
        abstraction = _clamp(factory_ratio * FACTORY_RESILIENCE_BONUS * 10)
        complexity = _clamp(factory_ratio * 0.5)
        resilience = _clamp(abstraction - complexity * 0.3)

        recs: list[str] = []
        if factory_ratio == 0.0 and total > 3:
            recs.append(
                "No factory patterns detected. Consider using factories "
                "for components that need runtime configuration or "
                "multiple implementations."
            )
        if complexity > 0.3:
            recs.append(
                "High factory complexity. Consider simplifying by using "
                "convention-based registration."
            )

        return FactoryResilienceResult(
            factory_components=factory_ids,
            factory_count=len(factory_ids),
            resilience_score=round(resilience, 4),
            abstraction_benefit=round(abstraction, 4),
            complexity_cost=round(complexity, 4),
            risk_level=_risk_from_score(1.0 - resilience),
            recommendations=recs,
        )

    def analyze_tree_depth(self) -> TreeDepthResult:
        """Analyze dependency tree depth."""
        comp_ids = self._all_component_ids()
        if not comp_ids:
            return TreeDepthResult(
                risk_level=RiskLevel.INFO,
                recommendations=["No components to analyze."],
            )

        all_paths: list[list[str]] = []
        for cid in comp_ids:
            paths = _find_all_paths_dfs(self._graph, cid)
            all_paths.extend(paths)

        if not all_paths:
            return TreeDepthResult(
                risk_level=RiskLevel.INFO,
                recommendations=["No dependency paths found."],
            )

        depths = [len(p) for p in all_paths]
        max_depth = max(depths)
        avg_depth = sum(depths) / len(depths)
        deepest = max(all_paths, key=len)

        # Build distribution
        dist: dict[int, int] = {}
        for d in depths:
            dist[d] = dist.get(d, 0) + 1

        threshold = self._config.max_tree_depth
        exceeds = max_depth > threshold
        risk_score = _clamp((max_depth - threshold) * 0.15) if exceeds else 0.0
        recs: list[str] = []
        if exceeds:
            recs.append(
                f"Maximum dependency depth ({max_depth}) exceeds "
                f"threshold ({threshold}). Deep chains increase "
                "resolution time, failure propagation, and make "
                "the system harder to test."
            )
        if avg_depth > threshold * 0.7:
            recs.append(
                f"Average depth ({avg_depth:.1f}) is approaching "
                f"the threshold ({threshold}). Consider flattening "
                "the dependency tree."
            )

        return TreeDepthResult(
            max_depth=max_depth,
            avg_depth=round(avg_depth, 2),
            deepest_path=deepest,
            depth_distribution=dist,
            risk_level=_risk_from_score(risk_score),
            exceeds_threshold=exceeds,
            recommendations=recs,
        )

    def assess_hot_swap(self) -> HotSwapResult:
        """Assess hot-swap capability for DI-registered components."""
        swappable: list[str] = []
        non_swappable: list[str] = []

        for cid, reg in self._registrations.items():
            if reg.supports_hot_swap:
                swappable.append(cid)
            else:
                non_swappable.append(cid)

        total = max(len(self._registrations), 1)
        coverage = len(swappable) / total
        flexibility = _clamp(coverage + coverage * HOT_SWAP_BONUS)

        recs: list[str] = []
        if coverage < 0.5 and total > 1:
            recs.append(
                f"Only {coverage:.0%} of components support hot-swap. "
                "Enable hot-swap for components behind interfaces "
                "to improve runtime flexibility."
            )
        for ns_id in non_swappable:
            fan_in = _compute_fan_in(self._graph, ns_id)
            if fan_in > 3:
                recs.append(
                    f"'{ns_id}' has high fan-in ({fan_in}) but does not "
                    "support hot-swap. Consider enabling it."
                )

        return HotSwapResult(
            swappable_components=swappable,
            non_swappable_components=non_swappable,
            swap_coverage=round(coverage, 4),
            runtime_flexibility_score=round(flexibility, 4),
            risk_level=_risk_from_score(1.0 - flexibility),
            recommendations=recs,
        )

    def analyze_config_switch_risks(self) -> ConfigSwitchRiskResult:
        """Analyze configuration-driven dependency switching risks."""
        config_ids: list[str] = []
        for cid, reg in self._registrations.items():
            if reg.config_driven:
                config_ids.append(cid)

        total = max(len(self._registrations), 1)
        config_ratio = len(config_ids) / total
        misconfig_risk = _clamp(config_ratio * CONFIG_SWITCH_PENALTY * 10)
        env_drift = _clamp(config_ratio * 0.3)
        rollback = _clamp(config_ratio * 0.4)

        combined = _clamp((misconfig_risk + env_drift + rollback) / 3.0)

        recs: list[str] = []
        if config_ratio > 0.3:
            recs.append(
                "High proportion of config-driven components. Use "
                "schema validation for configuration files and "
                "environment-specific integration tests."
            )
        if env_drift > 0.2:
            recs.append(
                "Environment drift risk is elevated. Implement "
                "configuration drift detection."
            )

        return ConfigSwitchRiskResult(
            config_driven_components=config_ids,
            total_config_driven=len(config_ids),
            misconfiguration_risk=round(misconfig_risk, 4),
            environment_drift_risk=round(env_drift, 4),
            rollback_complexity=round(rollback, 4),
            risk_level=_risk_from_score(combined),
            recommendations=recs,
        )

    def compute_decoupling_score(self) -> DecouplingScoreResult:
        """Compute interface-based decoupling score."""
        comp_ids = self._all_component_ids()
        if not comp_ids:
            return DecouplingScoreResult(
                overall_score=1.0,
                interface_coverage=1.0,
                risk_level=RiskLevel.INFO,
            )

        per_comp: dict[str, float] = {}
        interface_count = 0
        concrete_count = 0

        for cid in comp_ids:
            reg = self._get_reg(cid)
            if reg and reg.interface_name:
                interface_count += 1
                per_comp[cid] = 1.0
            else:
                concrete_count += 1
                per_comp[cid] = 0.0

        total = len(comp_ids)
        coverage = interface_count / max(total, 1)
        concrete_ratio = concrete_count / max(total, 1)
        # Depth: how many layers of abstraction exist
        tree_result = self.analyze_tree_depth()
        abstraction_depth = _clamp(
            tree_result.avg_depth / max(self._config.max_tree_depth, 1)
        )

        overall = _clamp(
            coverage * 0.6
            + (1.0 - concrete_ratio) * 0.2
            + abstraction_depth * 0.2
        )

        recs: list[str] = []
        if coverage < INTERFACE_DECOUPLING_IDEAL:
            recs.append(
                f"Interface coverage ({coverage:.0%}) is below the "
                f"ideal threshold ({INTERFACE_DECOUPLING_IDEAL:.0%}). "
                "Introduce interfaces for high-fan-in components."
            )

        return DecouplingScoreResult(
            overall_score=round(overall, 4),
            interface_coverage=round(coverage, 4),
            concrete_coupling_ratio=round(concrete_ratio, 4),
            abstraction_depth=round(abstraction_depth, 4),
            risk_level=_risk_from_score(1.0 - overall),
            per_component=per_comp,
            recommendations=recs,
        )

    def compute_complexity_metrics(self) -> ComplexityMetricsResult:
        """Compute dependency graph complexity metrics."""
        comp_ids = self._all_component_ids()
        n_nodes = len(comp_ids)
        edges = self._graph.all_dependency_edges()
        n_edges = len(edges)

        if n_nodes == 0:
            return ComplexityMetricsResult(risk_level=RiskLevel.INFO)

        connected = _count_connected_components(self._graph)
        cc = _cyclomatic_complexity(n_nodes, n_edges, connected)

        fan_in_map: dict[str, int] = {}
        fan_out_map: dict[str, int] = {}
        for cid in comp_ids:
            fi = _compute_fan_in(self._graph, cid)
            fo = _compute_fan_out(self._graph, cid)
            fan_in_map[cid] = fi
            fan_out_map[cid] = fo

        max_fi = max(fan_in_map.values()) if fan_in_map else 0
        max_fo = max(fan_out_map.values()) if fan_out_map else 0
        avg_fi = sum(fan_in_map.values()) / n_nodes if n_nodes else 0.0
        avg_fo = sum(fan_out_map.values()) / n_nodes if n_nodes else 0.0

        total_fi = sum(fan_in_map.values())
        total_fo = sum(fan_out_map.values())
        instability = _instability_index(total_fi, total_fo)

        # Abstractness: ratio of components with interfaces
        abstract_count = sum(
            1 for cid in comp_ids
            if self._get_reg(cid) and self._get_reg(cid).interface_name  # type: ignore[union-attr]
        )
        abstractness = abstract_count / max(n_nodes, 1)
        dist = _distance_from_main_sequence(abstractness, instability)

        risk_score = _clamp(
            (cc / max(CYCLOMATIC_THRESHOLD, 1)) * 0.4
            + (max_fo / max(MAX_SAFE_FAN_OUT, 1)) * 0.3
            + dist * 0.3
        )

        recs: list[str] = []
        if cc > CYCLOMATIC_THRESHOLD:
            recs.append(
                f"Cyclomatic complexity ({cc}) exceeds threshold "
                f"({CYCLOMATIC_THRESHOLD}). Consider decomposing "
                "the dependency graph into smaller modules."
            )
        if max_fo > MAX_SAFE_FAN_OUT:
            recs.append(
                f"Maximum fan-out ({max_fo}) exceeds threshold "
                f"({MAX_SAFE_FAN_OUT}). Components with high fan-out "
                "are fragile -- a change in any dependency can break them."
            )
        if max_fi > MAX_SAFE_FAN_IN:
            recs.append(
                f"Maximum fan-in ({max_fi}) exceeds threshold "
                f"({MAX_SAFE_FAN_IN}). Highly depended-upon components "
                "are single points of failure."
            )

        return ComplexityMetricsResult(
            cyclomatic_complexity=cc,
            total_edges=n_edges,
            total_nodes=n_nodes,
            max_fan_in=max_fi,
            max_fan_out=max_fo,
            avg_fan_in=round(avg_fi, 2),
            avg_fan_out=round(avg_fo, 2),
            fan_in_distribution=fan_in_map,
            fan_out_distribution=fan_out_map,
            instability_index=round(instability, 4),
            abstractness_index=round(abstractness, 4),
            distance_from_main_seq=round(dist, 4),
            risk_level=_risk_from_score(risk_score),
            recommendations=recs,
        )

    # -----------------------------------------------------------------------
    # Full analysis
    # -----------------------------------------------------------------------

    def analyze(self) -> DIAnalysisSummary:
        """Run all sub-analyses and return an aggregated summary."""
        circular = self.detect_circular_dependencies()
        lifecycle = self.assess_lifecycle_risks()
        locator = self.detect_service_locator()
        missing = self.detect_missing_bindings()
        scope = self.analyze_scope_mismatches()
        lazy = self.analyze_lazy_init_cascades()
        factory = self.evaluate_factory_resilience()
        depth = self.analyze_tree_depth()
        swap = self.assess_hot_swap()
        cfg = self.analyze_config_switch_risks()
        decouple = self.compute_decoupling_score()
        complexity = self.compute_complexity_metrics()

        # Aggregate risk
        sub_scores: list[float] = []
        if circular.has_cycles:
            sub_scores.append(0.9)
        if missing.has_missing:
            sub_scores.append(0.7)
        if scope.has_mismatches:
            sub_scores.append(scope.captive_dependency_risk)
        if locator.detected:
            sub_scores.append(locator.testability_impact)
        for lr in lifecycle:
            sub_scores.append(lr.risk_score)
        sub_scores.append(lazy.cascade_risk)
        sub_scores.append(1.0 - factory.resilience_score)
        sub_scores.append(1.0 - swap.swap_coverage)
        sub_scores.append(cfg.misconfiguration_risk)
        sub_scores.append(1.0 - decouple.overall_score)

        overall = _clamp(sum(sub_scores) / max(len(sub_scores), 1))

        # Collect all recommendations
        all_recs: list[str] = []
        if circular.impact_description:
            all_recs.append(circular.impact_description)
        all_recs.extend(locator.recommendations)
        all_recs.extend(missing.recommendations)
        all_recs.extend(scope.recommendations)
        all_recs.extend(lazy.recommendations)
        all_recs.extend(factory.recommendations)
        all_recs.extend(depth.recommendations)
        all_recs.extend(swap.recommendations)
        all_recs.extend(cfg.recommendations)
        all_recs.extend(decouple.recommendations)
        all_recs.extend(complexity.recommendations)
        for lr in lifecycle:
            all_recs.extend(lr.recommendations)

        # Deduplicate
        seen: set[str] = set()
        unique: list[str] = []
        for r in all_recs:
            if r not in seen:
                seen.add(r)
                unique.append(r)

        return DIAnalysisSummary(
            overall_risk_score=round(overall, 4),
            overall_risk_level=_risk_from_score(overall),
            circular_dependency=circular,
            lifecycle_risks=lifecycle,
            service_locator=locator,
            missing_bindings=missing,
            scope_mismatches=scope,
            lazy_init=lazy,
            factory_resilience=factory,
            tree_depth=depth,
            hot_swap=swap,
            config_switch=cfg,
            decoupling=decouple,
            complexity=complexity,
            recommendations=unique,
        )
