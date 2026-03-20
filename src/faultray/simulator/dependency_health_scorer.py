# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Dependency Health Scorer for FaultRay.

Scores the health of each dependency relationship in the infrastructure graph
across multiple dimensions: reliability, latency, throughput, error rate,
and freshness.  Provides composite health scores, trend analysis, graph
complexity metrics, circuit-breaker readiness assessment, retry-policy
evaluation, timeout auditing, and orphan dependency detection.

Usage:
    from faultray.simulator.dependency_health_scorer import DependencyHealthScorer
    scorer = DependencyHealthScorer()
    report = scorer.score(graph)
    critical = scorer.critical_dependencies(graph, threshold=40.0)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

import networkx as nx

from faultray.model.components import (
    Component,
    Dependency,
    HealthStatus,
)
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HEALTH_SCORE_MAP: dict[HealthStatus, float] = {
    HealthStatus.HEALTHY: 100.0,
    HealthStatus.DEGRADED: 60.0,
    HealthStatus.OVERLOADED: 35.0,
    HealthStatus.DOWN: 0.0,
}


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DependencyCriticality(str, Enum):
    """How critical a dependency is to the service."""

    CRITICAL_PATH = "critical_path"
    NICE_TO_HAVE = "nice_to_have"
    OPTIONAL = "optional"


class HealthTrend(str, Enum):
    """Direction in which a dependency's health is moving."""

    IMPROVING = "improving"
    STABLE = "stable"
    DEGRADING = "degrading"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class HealthDimensions:
    """Individual health dimension scores for a dependency (0-100 each)."""

    reliability: float = 100.0
    latency: float = 100.0
    throughput: float = 100.0
    error_rate: float = 100.0
    freshness: float = 100.0


@dataclass
class CircuitBreakerReadiness:
    """Assessment of circuit-breaker configuration readiness."""

    enabled: bool = False
    properly_configured: bool = False
    issues: list[str] = field(default_factory=list)
    score: float = 0.0  # 0-100


@dataclass
class RetryPolicyEvaluation:
    """Assessment of retry policy configuration."""

    enabled: bool = False
    has_backoff: bool = False
    has_jitter: bool = False
    has_budget: bool = False
    issues: list[str] = field(default_factory=list)
    score: float = 0.0  # 0-100


@dataclass
class TimeoutAudit:
    """Timeout configuration audit result."""

    timeout_seconds: float = 0.0
    adequate: bool = False
    issues: list[str] = field(default_factory=list)
    score: float = 0.0  # 0-100


@dataclass
class DependencyHealthScore:
    """Full health score for a single dependency edge."""

    source_id: str
    target_id: str
    criticality: DependencyCriticality
    dimensions: HealthDimensions
    composite_score: float  # 0-100
    trend: HealthTrend
    circuit_breaker_readiness: CircuitBreakerReadiness
    retry_policy_evaluation: RetryPolicyEvaluation
    timeout_audit: TimeoutAudit
    fan_in: int = 0
    fan_out: int = 0
    concentration_risk: float = 0.0  # 0-1; high = risky
    recommendations: list[str] = field(default_factory=list)


@dataclass
class GraphComplexityMetrics:
    """Complexity metrics for the entire dependency graph."""

    cyclomatic_complexity: int = 0
    max_depth: int = 0
    max_width: int = 0
    total_nodes: int = 0
    total_edges: int = 0
    density: float = 0.0
    avg_fan_in: float = 0.0
    avg_fan_out: float = 0.0


@dataclass
class DependencyHealthReport:
    """Complete dependency health report for an infrastructure graph."""

    scores: list[DependencyHealthScore]
    graph_complexity: GraphComplexityMetrics
    orphan_dependencies: list[str]
    overall_health: float  # 0-100
    timestamp: str
    recommendations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class DependencyHealthScorer:
    """Score the health of every dependency in an ``InfraGraph``.

    The scorer analyses each dependency edge across five health
    dimensions (reliability, latency, throughput, error-rate, freshness),
    classifies criticality, evaluates circuit-breaker / retry / timeout
    readiness, and produces a composite health score per edge plus
    graph-wide complexity metrics.

    Parameters
    ----------
    latency_threshold_ms:
        Latency above this threshold degrades the latency dimension.
    error_rate_threshold:
        Error rate (0-1) above this threshold degrades the error-rate
        dimension.
    concentration_threshold:
        Fan-in count above this threshold flags concentration risk.
    """

    def __init__(
        self,
        *,
        latency_threshold_ms: float = 100.0,
        error_rate_threshold: float = 0.01,
        concentration_threshold: int = 5,
    ) -> None:
        self.latency_threshold_ms = max(1.0, latency_threshold_ms)
        self.error_rate_threshold = max(0.001, min(error_rate_threshold, 1.0))
        self.concentration_threshold = max(1, concentration_threshold)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score(self, graph: InfraGraph) -> DependencyHealthReport:
        """Produce a full health report for all dependencies in *graph*."""

        scores: list[DependencyHealthScore] = []
        all_recommendations: list[str] = []

        for dep in graph.all_dependency_edges():
            dep_score = self._score_dependency(graph, dep)
            scores.append(dep_score)
            all_recommendations.extend(dep_score.recommendations)

        complexity = self._compute_graph_complexity(graph)
        orphans = self._find_orphan_dependencies(graph)

        if orphans:
            all_recommendations.append(
                f"{len(orphans)} orphan component(s) detected with no "
                "incoming or outgoing dependencies. Consider removing or "
                "connecting them."
            )

        if complexity.cyclomatic_complexity > 10:
            all_recommendations.append(
                f"Graph cyclomatic complexity is {complexity.cyclomatic_complexity}. "
                "Consider simplifying the dependency topology."
            )

        if complexity.max_depth > 6:
            all_recommendations.append(
                f"Maximum dependency depth is {complexity.max_depth}. "
                "Deep chains increase cascade failure risk."
            )

        # Overall health = weighted average of composite scores
        if scores:
            overall = sum(s.composite_score for s in scores) / len(scores)
        else:
            overall = 100.0

        # De-duplicate recommendations
        seen: set[str] = set()
        unique_recs: list[str] = []
        for r in all_recommendations:
            if r not in seen:
                seen.add(r)
                unique_recs.append(r)

        now = datetime.now(timezone.utc)
        return DependencyHealthReport(
            scores=scores,
            graph_complexity=complexity,
            orphan_dependencies=orphans,
            overall_health=round(overall, 2),
            timestamp=now.isoformat(),
            recommendations=unique_recs,
        )

    def score_dependency(
        self, graph: InfraGraph, source_id: str, target_id: str,
    ) -> DependencyHealthScore | None:
        """Score a single dependency edge.

        Returns ``None`` if no dependency edge exists between the given
        components.
        """
        dep = graph.get_dependency_edge(source_id, target_id)
        if dep is None:
            return None
        return self._score_dependency(graph, dep)

    def critical_dependencies(
        self, graph: InfraGraph, *, threshold: float = 40.0,
    ) -> list[DependencyHealthScore]:
        """Return dependency scores whose composite score is at or below
        *threshold* (i.e. unhealthy dependencies).

        Results are sorted by composite score ascending (worst first).
        """
        report = self.score(graph)
        critical = [
            s for s in report.scores if s.composite_score <= threshold
        ]
        critical.sort(key=lambda s: s.composite_score)
        return critical

    def compute_fan_in(self, graph: InfraGraph, component_id: str) -> int:
        """Return the fan-in (number of dependents) of *component_id*."""
        return len(graph.get_dependents(component_id))

    def compute_fan_out(self, graph: InfraGraph, component_id: str) -> int:
        """Return the fan-out (number of dependencies) of *component_id*."""
        return len(graph.get_dependencies(component_id))

    def compute_concentration_risk(
        self, graph: InfraGraph, component_id: str,
    ) -> float:
        """Return concentration risk (0-1) for *component_id*.

        Concentration risk reflects how many other services depend on a
        single component relative to the total number of components.
        """
        total = max(len(graph.components), 1)
        fan_in = self.compute_fan_in(graph, component_id)
        return min(1.0, fan_in / total)

    def compute_graph_complexity(
        self, graph: InfraGraph,
    ) -> GraphComplexityMetrics:
        """Compute graph complexity metrics (public wrapper)."""
        return self._compute_graph_complexity(graph)

    def find_orphan_dependencies(
        self, graph: InfraGraph,
    ) -> list[str]:
        """Find components with no incoming or outgoing dependencies."""
        return self._find_orphan_dependencies(graph)

    def trend_from_snapshots(
        self, previous_score: float, current_score: float,
    ) -> HealthTrend:
        """Determine health trend from two snapshot scores."""
        return self._determine_trend(previous_score, current_score)

    # ------------------------------------------------------------------
    # Internal: per-dependency scoring
    # ------------------------------------------------------------------

    def _score_dependency(
        self, graph: InfraGraph, dep: Dependency,
    ) -> DependencyHealthScore:
        """Score a single dependency edge."""

        source = graph.get_component(dep.source_id)
        target = graph.get_component(dep.target_id)

        dims = self._compute_dimensions(source, target, dep)
        criticality = self._classify_criticality(dep, target, graph)
        cb_readiness = self._assess_circuit_breaker(dep)
        retry_eval = self._evaluate_retry_policy(dep)
        timeout_aud = self._audit_timeout(target, dep)
        composite = self._composite_score(dims, criticality)
        trend = self._determine_trend(composite, composite)

        fan_in_target = self.compute_fan_in(graph, dep.target_id)
        fan_out_source = self.compute_fan_out(graph, dep.source_id)
        concentration = self.compute_concentration_risk(graph, dep.target_id)

        recs = self._build_recommendations(
            dep, dims, criticality, cb_readiness, retry_eval,
            timeout_aud, concentration, fan_in_target,
        )

        return DependencyHealthScore(
            source_id=dep.source_id,
            target_id=dep.target_id,
            criticality=criticality,
            dimensions=dims,
            composite_score=round(composite, 2),
            trend=trend,
            circuit_breaker_readiness=cb_readiness,
            retry_policy_evaluation=retry_eval,
            timeout_audit=timeout_aud,
            fan_in=fan_in_target,
            fan_out=fan_out_source,
            concentration_risk=round(concentration, 4),
            recommendations=recs,
        )

    # ------------------------------------------------------------------
    # Internal: health dimensions
    # ------------------------------------------------------------------

    def _compute_dimensions(
        self,
        source: Component | None,
        target: Component | None,
        dep: Dependency,
    ) -> HealthDimensions:
        """Compute the five health dimension scores."""
        reliability = self._reliability_score(target)
        latency = self._latency_score(dep)
        throughput = self._throughput_score(target)
        error_rate = self._error_rate_score(target)
        freshness = self._freshness_score(target, dep)
        return HealthDimensions(
            reliability=round(reliability, 2),
            latency=round(latency, 2),
            throughput=round(throughput, 2),
            error_rate=round(error_rate, 2),
            freshness=round(freshness, 2),
        )

    def _reliability_score(self, target: Component | None) -> float:
        """Score based on target health status and replica count."""
        if target is None:
            return 50.0
        base = _HEALTH_SCORE_MAP.get(target.health, 50.0)
        # Boost for replicas
        if target.replicas >= 3:
            base = min(100.0, base + 10.0)
        elif target.replicas >= 2:
            base = min(100.0, base + 5.0)
        # Boost for failover
        if target.failover.enabled:
            base = min(100.0, base + 5.0)
        return base

    def _latency_score(self, dep: Dependency) -> float:
        """Score based on dependency latency vs threshold."""
        if dep.latency_ms <= 0:
            return 100.0  # no latency data
        ratio = dep.latency_ms / self.latency_threshold_ms
        if ratio <= 0.5:
            return 100.0
        if ratio <= 1.0:
            return 100.0 - (ratio - 0.5) * 40.0  # 100 -> 80
        if ratio <= 2.0:
            return 80.0 - (ratio - 1.0) * 40.0  # 80 -> 40
        return max(0.0, 40.0 - (ratio - 2.0) * 20.0)

    def _throughput_score(self, target: Component | None) -> float:
        """Score based on target utilization headroom."""
        if target is None:
            return 50.0
        util = target.utilization()
        if util <= 50.0:
            return 100.0
        if util <= 70.0:
            return 100.0 - (util - 50.0) * 1.5  # 100 -> 70
        if util <= 90.0:
            return 70.0 - (util - 70.0) * 2.5  # 70 -> 20
        return max(0.0, 20.0 - (util - 90.0) * 2.0)

    def _error_rate_score(self, target: Component | None) -> float:
        """Score based on target health status as error-rate proxy."""
        if target is None:
            return 50.0
        if target.health == HealthStatus.HEALTHY:
            return 100.0
        if target.health == HealthStatus.DEGRADED:
            return 60.0
        if target.health == HealthStatus.OVERLOADED:
            return 30.0
        return 0.0  # DOWN

    def _freshness_score(
        self, target: Component | None, dep: Dependency,
    ) -> float:
        """Score based on version compatibility heuristics.

        Uses the dependency weight as a proxy: a weight of 1.0 means the
        dependency is critical and up-to-date; lower weights imply staleness.
        """
        base = 100.0
        if dep.weight < 0.5:
            base -= 40.0
        elif dep.weight < 0.8:
            base -= 15.0

        if target is not None and target.health == HealthStatus.DEGRADED:
            base -= 10.0

        return max(0.0, min(100.0, base))

    # ------------------------------------------------------------------
    # Internal: criticality classification
    # ------------------------------------------------------------------

    def _classify_criticality(
        self,
        dep: Dependency,
        target: Component | None,
        graph: InfraGraph,
    ) -> DependencyCriticality:
        """Classify a dependency as critical-path, nice-to-have, or optional."""
        if dep.dependency_type == "requires":
            return DependencyCriticality.CRITICAL_PATH
        if dep.dependency_type == "optional":
            return DependencyCriticality.OPTIONAL
        if dep.dependency_type == "async":
            return DependencyCriticality.NICE_TO_HAVE
        # Fallback: high-weight is critical-path
        if dep.weight >= 0.8:
            return DependencyCriticality.CRITICAL_PATH
        return DependencyCriticality.NICE_TO_HAVE

    # ------------------------------------------------------------------
    # Internal: circuit-breaker readiness
    # ------------------------------------------------------------------

    def _assess_circuit_breaker(
        self, dep: Dependency,
    ) -> CircuitBreakerReadiness:
        """Assess how well a circuit breaker is configured."""
        cb = dep.circuit_breaker
        issues: list[str] = []

        if not cb.enabled:
            issues.append("Circuit breaker is not enabled")
            return CircuitBreakerReadiness(
                enabled=False,
                properly_configured=False,
                issues=issues,
                score=0.0,
            )

        score = 60.0  # enabled = baseline

        if cb.failure_threshold < 1:
            issues.append(
                "Failure threshold is too low (trips immediately)"
            )
            score -= 20.0
        elif cb.failure_threshold > 20:
            issues.append(
                "Failure threshold is very high; circuit breaker may "
                "trip too slowly"
            )
            score -= 10.0
        else:
            score += 15.0

        if cb.recovery_timeout_seconds < 5.0:
            issues.append(
                "Recovery timeout is very short; may cause flapping"
            )
            score -= 10.0
        elif cb.recovery_timeout_seconds > 600.0:
            issues.append(
                "Recovery timeout is very long; service may stay "
                "open too long"
            )
            score -= 5.0
        else:
            score += 15.0

        if cb.half_open_max_requests < 1:
            issues.append("Half-open max requests is zero; cannot probe")
            score -= 10.0
        else:
            score += 10.0

        properly_configured = len(issues) == 0
        return CircuitBreakerReadiness(
            enabled=True,
            properly_configured=properly_configured,
            issues=issues,
            score=max(0.0, min(100.0, score)),
        )

    # ------------------------------------------------------------------
    # Internal: retry policy evaluation
    # ------------------------------------------------------------------

    def _evaluate_retry_policy(
        self, dep: Dependency,
    ) -> RetryPolicyEvaluation:
        """Evaluate the quality of the retry strategy."""
        rs = dep.retry_strategy
        issues: list[str] = []

        if not rs.enabled:
            issues.append("Retry strategy is not enabled")
            return RetryPolicyEvaluation(
                enabled=False,
                has_backoff=False,
                has_jitter=False,
                has_budget=False,
                issues=issues,
                score=0.0,
            )

        score = 40.0
        has_backoff = rs.multiplier > 1.0
        has_jitter = rs.jitter
        has_budget = rs.retry_budget_per_second > 0.0

        if has_backoff:
            score += 20.0
        else:
            issues.append(
                "Retry multiplier <= 1.0; no exponential backoff"
            )

        if has_jitter:
            score += 15.0
        else:
            issues.append("Jitter is disabled; risk of thundering herd")

        if has_budget:
            score += 15.0
        else:
            issues.append(
                "No retry budget configured; retries may overwhelm target"
            )

        if rs.max_retries > 10:
            issues.append(
                f"Max retries ({rs.max_retries}) is high; may cause "
                "excessive load"
            )
            score -= 10.0
        elif rs.max_retries < 1:
            issues.append("Max retries < 1; retries are effectively disabled")
            score -= 15.0
        else:
            score += 10.0

        return RetryPolicyEvaluation(
            enabled=True,
            has_backoff=has_backoff,
            has_jitter=has_jitter,
            has_budget=has_budget,
            issues=issues,
            score=max(0.0, min(100.0, score)),
        )

    # ------------------------------------------------------------------
    # Internal: timeout audit
    # ------------------------------------------------------------------

    def _audit_timeout(
        self, target: Component | None, dep: Dependency,
    ) -> TimeoutAudit:
        """Audit timeout configuration for a dependency edge."""
        issues: list[str] = []

        if target is None:
            issues.append("Target component not found; cannot audit timeout")
            return TimeoutAudit(
                timeout_seconds=0.0,
                adequate=False,
                issues=issues,
                score=0.0,
            )

        timeout = target.capacity.timeout_seconds
        score = 50.0

        if timeout <= 0:
            issues.append("No timeout configured")
            return TimeoutAudit(
                timeout_seconds=0.0,
                adequate=False,
                issues=issues,
                score=0.0,
            )

        if timeout > 120.0:
            issues.append(
                f"Timeout ({timeout}s) is very high; may cause "
                "thread exhaustion on callers"
            )
            score -= 20.0
        elif timeout < 1.0:
            issues.append(
                f"Timeout ({timeout}s) is very low; may cause "
                "premature failures"
            )
            score -= 15.0
        else:
            score += 30.0

        # Cross-check with latency
        if dep.latency_ms > 0:
            expected_s = dep.latency_ms / 1000.0
            if timeout < expected_s * 2.0:
                issues.append(
                    f"Timeout ({timeout}s) is less than 2x the "
                    f"expected latency ({expected_s:.2f}s)"
                )
                score -= 10.0
            else:
                score += 20.0

        adequate = len(issues) == 0
        return TimeoutAudit(
            timeout_seconds=timeout,
            adequate=adequate,
            issues=issues,
            score=max(0.0, min(100.0, score)),
        )

    # ------------------------------------------------------------------
    # Internal: composite & trend
    # ------------------------------------------------------------------

    def _composite_score(
        self, dims: HealthDimensions, criticality: DependencyCriticality,
    ) -> float:
        """Combine dimension scores into a single composite score.

        Critical-path dependencies are penalised more heavily for low
        dimension scores.
        """
        weights = {
            "reliability": 0.30,
            "latency": 0.20,
            "throughput": 0.15,
            "error_rate": 0.20,
            "freshness": 0.15,
        }

        raw = (
            dims.reliability * weights["reliability"]
            + dims.latency * weights["latency"]
            + dims.throughput * weights["throughput"]
            + dims.error_rate * weights["error_rate"]
            + dims.freshness * weights["freshness"]
        )

        # Apply criticality multiplier
        if criticality == DependencyCriticality.CRITICAL_PATH:
            # Amplify penalties for critical-path dependencies
            if raw < 70.0:
                raw *= 0.85
        elif criticality == DependencyCriticality.OPTIONAL:
            # Optional dependencies are less impactful
            raw = min(100.0, raw * 1.05)

        return max(0.0, min(100.0, raw))

    @staticmethod
    def _determine_trend(
        previous_score: float, current_score: float,
    ) -> HealthTrend:
        """Determine the health trend from two scores."""
        delta = current_score - previous_score
        if delta > 5.0:
            return HealthTrend.IMPROVING
        if delta < -5.0:
            return HealthTrend.DEGRADING
        return HealthTrend.STABLE

    # ------------------------------------------------------------------
    # Internal: graph complexity
    # ------------------------------------------------------------------

    def _compute_graph_complexity(
        self, graph: InfraGraph,
    ) -> GraphComplexityMetrics:
        """Compute complexity metrics for the whole graph."""
        g = graph._graph
        n = g.number_of_nodes()
        e = g.number_of_edges()

        if n == 0:
            return GraphComplexityMetrics()

        # Cyclomatic complexity: E - N + 2P (P = connected components)
        try:
            num_weakly = nx.number_weakly_connected_components(g)
        except nx.NetworkXError:
            num_weakly = 1
        cyclomatic = e - n + 2 * num_weakly

        # Max depth: longest path in the DAG (or approximate if cyclic)
        max_depth = 0
        try:
            if nx.is_directed_acyclic_graph(g):
                longest = nx.dag_longest_path(g)
                max_depth = len(longest)
            else:
                # Approximate by looking at simple paths between entries/leaves
                entries = [nd for nd in g.nodes if g.in_degree(nd) == 0]
                leaves = [nd for nd in g.nodes if g.out_degree(nd) == 0]
                if not entries:
                    entries = list(g.nodes)[:1]
                if not leaves:
                    leaves = list(g.nodes)[:1]
                for entry in entries:
                    for leaf in leaves:
                        if entry == leaf:
                            continue
                        try:
                            for p in nx.all_simple_paths(g, entry, leaf):
                                max_depth = max(max_depth, len(p))
                        except nx.NetworkXError:
                            continue
        except nx.NetworkXError:
            pass

        # Max width: maximum number of nodes at any BFS level from any entry
        max_width = self._compute_max_width(g)

        # Density
        density = nx.density(g)

        # Average fan-in / fan-out
        in_degrees = [g.in_degree(nd) for nd in g.nodes]
        out_degrees = [g.out_degree(nd) for nd in g.nodes]
        avg_fan_in = sum(in_degrees) / n if n > 0 else 0.0
        avg_fan_out = sum(out_degrees) / n if n > 0 else 0.0

        return GraphComplexityMetrics(
            cyclomatic_complexity=max(0, cyclomatic),
            max_depth=max_depth,
            max_width=max_width,
            total_nodes=n,
            total_edges=e,
            density=round(density, 4),
            avg_fan_in=round(avg_fan_in, 2),
            avg_fan_out=round(avg_fan_out, 2),
        )

    @staticmethod
    def _compute_max_width(g: nx.DiGraph) -> int:
        """Compute the maximum BFS level width across all entry nodes."""
        max_width = 0
        entries = [nd for nd in g.nodes if g.in_degree(nd) == 0]
        if not entries:
            entries = list(g.nodes)[:1] if g.nodes else []
        for entry in entries:
            level_counts: dict[int, int] = {}
            for node, depth in nx.single_source_shortest_path_length(g, entry).items():
                level_counts[depth] = level_counts.get(depth, 0) + 1
            if level_counts:
                max_width = max(max_width, max(level_counts.values()))
        return max_width

    # ------------------------------------------------------------------
    # Internal: orphan detection
    # ------------------------------------------------------------------

    def _find_orphan_dependencies(
        self, graph: InfraGraph,
    ) -> list[str]:
        """Find components with zero incoming and zero outgoing edges."""
        g = graph._graph
        orphans: list[str] = []
        for node in g.nodes:
            if g.in_degree(node) == 0 and g.out_degree(node) == 0:
                orphans.append(node)
        return sorted(orphans)

    # ------------------------------------------------------------------
    # Internal: recommendations
    # ------------------------------------------------------------------

    def _build_recommendations(
        self,
        dep: Dependency,
        dims: HealthDimensions,
        criticality: DependencyCriticality,
        cb: CircuitBreakerReadiness,
        retry: RetryPolicyEvaluation,
        timeout: TimeoutAudit,
        concentration: float,
        fan_in: int,
    ) -> list[str]:
        """Generate per-dependency recommendations."""
        recs: list[str] = []

        edge_label = f"{dep.source_id} -> {dep.target_id}"

        if not cb.enabled and criticality == DependencyCriticality.CRITICAL_PATH:
            recs.append(
                f"Enable circuit breaker on critical dependency "
                f"{edge_label}."
            )

        if cb.enabled and not cb.properly_configured:
            for issue in cb.issues:
                recs.append(f"Circuit breaker ({edge_label}): {issue}.")

        if not retry.enabled and criticality == DependencyCriticality.CRITICAL_PATH:
            recs.append(
                f"Add retry strategy with exponential backoff on "
                f"{edge_label}."
            )

        if retry.enabled and not retry.has_jitter:
            recs.append(
                f"Enable jitter on retry strategy for {edge_label} to "
                "prevent thundering herd."
            )

        if not timeout.adequate:
            for issue in timeout.issues:
                recs.append(f"Timeout ({edge_label}): {issue}.")

        if dims.reliability < 50.0:
            recs.append(
                f"Target reliability is low ({dims.reliability:.0f}/100) "
                f"for {edge_label}. Consider adding replicas or failover."
            )

        if dims.latency < 50.0:
            recs.append(
                f"Latency score is low ({dims.latency:.0f}/100) for "
                f"{edge_label}. Investigate network path or target "
                "performance."
            )

        if concentration > 0.5:
            recs.append(
                f"High concentration risk ({concentration:.0%}) on "
                f"{dep.target_id}. {fan_in} services depend on it. "
                "Consider adding redundancy or distributing load."
            )

        return recs
