# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Architecture Fitness Functions.

Continuous architectural quality metrics inspired by
"Building Evolutionary Architectures" (Neal Ford). Each fitness function
scores an aspect of the architecture on a 0-100 scale, producing an
overall weighted report with grades and actionable improvement suggestions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from faultray.model.components import ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class FitnessCategory(str, Enum):
    RESILIENCE = "resilience"
    SECURITY = "security"
    PERFORMANCE = "performance"
    OPERABILITY = "operability"
    SCALABILITY = "scalability"
    COST_EFFICIENCY = "cost_efficiency"


class FitnessGrade(str, Enum):
    A = "A"  # 90-100
    B = "B"  # 75-89
    C = "C"  # 60-74
    D = "D"  # 40-59
    F = "F"  # 0-39


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FitnessResult:
    """Result of evaluating a single fitness function."""

    function_id: str
    function_name: str
    category: FitnessCategory
    score: float  # 0-100
    grade: FitnessGrade
    weight: float  # importance weight
    details: str
    passed: bool  # met minimum threshold
    threshold: float  # minimum acceptable score


@dataclass
class FitnessReport:
    """Aggregate report from evaluating all fitness functions."""

    results: list[FitnessResult] = field(default_factory=list)
    overall_score: float = 0.0
    overall_grade: FitnessGrade = FitnessGrade.F
    category_scores: dict[str, float] = field(default_factory=dict)
    passed_count: int = 0
    failed_count: int = 0
    critical_failures: list[str] = field(default_factory=list)
    trends: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


class FitnessEvaluator:
    """Evaluate architecture fitness functions against an InfraGraph.

    The evaluator ships with 14 built-in fitness functions spanning
    resilience, security, performance, operability, scalability,
    and cost-efficiency.
    """

    # Default thresholds per function (minimum passing score)
    _DEFAULT_THRESHOLDS: dict[str, float] = {
        "redundancy": 60.0,
        "failover": 60.0,
        "spof": 60.0,
        "circuit_breaker": 60.0,
        "encryption": 60.0,
        "monitoring": 60.0,
        "backup": 60.0,
        "compliance": 60.0,
        "utilization": 60.0,
        "dependency_depth": 60.0,
        "health": 60.0,
        "retry": 60.0,
        "autoscale_readiness": 60.0,
        "load_distribution": 60.0,
        "right_sizing": 60.0,
    }

    # Weights: RESILIENCE=1.5, SECURITY=1.3, others=1.0
    _CATEGORY_WEIGHTS: dict[FitnessCategory, float] = {
        FitnessCategory.RESILIENCE: 1.5,
        FitnessCategory.SECURITY: 1.3,
        FitnessCategory.PERFORMANCE: 1.0,
        FitnessCategory.OPERABILITY: 1.0,
        FitnessCategory.SCALABILITY: 1.0,
        FitnessCategory.COST_EFFICIENCY: 1.0,
    }

    # Registry: (function_id, function_name, category, evaluator_method_name)
    _FUNCTION_REGISTRY: list[tuple[str, str, FitnessCategory, str]] = [
        # RESILIENCE
        ("redundancy", "Redundancy Fitness", FitnessCategory.RESILIENCE, "_eval_redundancy"),
        ("failover", "Failover Fitness", FitnessCategory.RESILIENCE, "_eval_failover"),
        ("spof", "SPOF Fitness", FitnessCategory.RESILIENCE, "_eval_spof"),
        ("circuit_breaker", "Circuit Breaker Fitness", FitnessCategory.RESILIENCE, "_eval_circuit_breaker"),
        # SECURITY
        ("encryption", "Encryption Fitness", FitnessCategory.SECURITY, "_eval_encryption"),
        ("monitoring", "Monitoring Fitness", FitnessCategory.SECURITY, "_eval_monitoring"),
        ("backup", "Backup Fitness", FitnessCategory.SECURITY, "_eval_backup"),
        ("compliance", "Compliance Fitness", FitnessCategory.SECURITY, "_eval_compliance"),
        # PERFORMANCE
        ("utilization", "Utilization Fitness", FitnessCategory.PERFORMANCE, "_eval_utilization"),
        ("dependency_depth", "Dependency Depth Fitness", FitnessCategory.PERFORMANCE, "_eval_dependency_depth"),
        # OPERABILITY
        ("health", "Health Fitness", FitnessCategory.OPERABILITY, "_eval_health"),
        ("retry", "Retry Fitness", FitnessCategory.OPERABILITY, "_eval_retry"),
        # SCALABILITY
        ("autoscale_readiness", "Autoscale Readiness", FitnessCategory.SCALABILITY, "_eval_autoscale_readiness"),
        ("load_distribution", "Load Distribution", FitnessCategory.SCALABILITY, "_eval_load_distribution"),
        # COST_EFFICIENCY
        ("right_sizing", "Right Sizing", FitnessCategory.COST_EFFICIENCY, "_eval_right_sizing"),
    ]

    def __init__(self, custom_thresholds: dict[str, float] | None = None) -> None:
        self._thresholds: dict[str, float] = dict(self._DEFAULT_THRESHOLDS)
        if custom_thresholds:
            self._thresholds.update(custom_thresholds)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def grade(self, score: float) -> FitnessGrade:
        """Convert numeric score to letter grade."""
        if score >= 90.0:
            return FitnessGrade.A
        if score >= 75.0:
            return FitnessGrade.B
        if score >= 60.0:
            return FitnessGrade.C
        if score >= 40.0:
            return FitnessGrade.D
        return FitnessGrade.F

    def evaluate(self, graph: InfraGraph) -> FitnessReport:
        """Run all fitness functions against the infrastructure."""
        results: list[FitnessResult] = []
        for func_id, func_name, category, method_name in self._FUNCTION_REGISTRY:
            evaluator = getattr(self, method_name)
            score = evaluator(graph)
            score = max(0.0, min(100.0, score))
            threshold = self._thresholds.get(func_id, 60.0)
            weight = self._CATEGORY_WEIGHTS.get(category, 1.0)
            results.append(FitnessResult(
                function_id=func_id,
                function_name=func_name,
                category=category,
                score=round(score, 2),
                grade=self.grade(score),
                weight=weight,
                details=self._get_details(func_id, graph, score),
                passed=score >= threshold,
                threshold=threshold,
            ))

        return self._build_report(results)

    def evaluate_category(
        self, graph: InfraGraph, category: FitnessCategory
    ) -> list[FitnessResult]:
        """Evaluate fitness functions for a specific category."""
        results: list[FitnessResult] = []
        for func_id, func_name, cat, method_name in self._FUNCTION_REGISTRY:
            if cat != category:
                continue
            evaluator = getattr(self, method_name)
            score = evaluator(graph)
            score = max(0.0, min(100.0, score))
            threshold = self._thresholds.get(func_id, 60.0)
            weight = self._CATEGORY_WEIGHTS.get(cat, 1.0)
            results.append(FitnessResult(
                function_id=func_id,
                function_name=func_name,
                category=cat,
                score=round(score, 2),
                grade=self.grade(score),
                weight=weight,
                details=self._get_details(func_id, graph, score),
                passed=score >= threshold,
                threshold=threshold,
            ))
        return results

    # ------------------------------------------------------------------
    # Report builder
    # ------------------------------------------------------------------

    def _build_report(self, results: list[FitnessResult]) -> FitnessReport:
        """Assemble a FitnessReport from individual results."""
        if not results:
            return FitnessReport()

        # Overall weighted average
        total_weight = sum(r.weight for r in results)
        if total_weight > 0:
            overall_score = sum(r.score * r.weight for r in results) / total_weight
        else:
            overall_score = 0.0
        overall_score = max(0.0, min(100.0, overall_score))

        # Category averages
        cat_scores: dict[str, list[float]] = {}
        for r in results:
            cat_scores.setdefault(r.category.value, []).append(r.score)
        category_scores = {
            cat: round(sum(scores) / len(scores), 2)
            for cat, scores in cat_scores.items()
        }

        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed

        # Critical failures: any function scoring below 30
        critical_failures = [
            r.function_id for r in results if r.score < 30.0
        ]

        # Trends / improvement suggestions
        trends = self._generate_trends(results, category_scores)

        return FitnessReport(
            results=results,
            overall_score=round(overall_score, 2),
            overall_grade=self.grade(overall_score),
            category_scores=category_scores,
            passed_count=passed,
            failed_count=failed,
            critical_failures=critical_failures,
            trends=trends,
        )

    def _generate_trends(
        self,
        results: list[FitnessResult],
        category_scores: dict[str, float],
    ) -> list[str]:
        """Generate improvement suggestions based on results."""
        trends: list[str] = []

        # Identify lowest-scoring category
        if category_scores:
            worst_cat = min(category_scores, key=category_scores.get)  # type: ignore[arg-type]
            worst_score = category_scores[worst_cat]
            if worst_score < 60.0:
                trends.append(
                    f"Focus on improving {worst_cat} (score: {worst_score:.1f})"
                )

        # Identify individual failures
        for r in results:
            if not r.passed:
                trends.append(
                    f"Improve {r.function_name} — currently {r.score:.1f}, "
                    f"needs {r.threshold:.1f}"
                )

        return trends

    # ------------------------------------------------------------------
    # Detail text generator
    # ------------------------------------------------------------------

    def _get_details(self, func_id: str, graph: InfraGraph, score: float) -> str:
        """Generate human-readable detail text for a fitness result."""
        components = list(graph.components.values())
        n = len(components)

        if n == 0:
            return "No components to evaluate."

        detail_map: dict[str, str] = {
            "redundancy": f"{sum(1 for c in components if c.replicas > 1)}/{n} components have replicas > 1.",
            "failover": self._failover_detail(graph),
            "spof": self._spof_detail(graph),
            "circuit_breaker": self._cb_detail(graph),
            "encryption": f"{sum(1 for c in components if c.security.encryption_at_rest or c.security.encryption_in_transit)}/{n} components have encryption.",
            "monitoring": f"{sum(1 for c in components if c.security.log_enabled)}/{n} components have logging enabled.",
            "backup": self._backup_detail(graph),
            "compliance": self._compliance_detail(graph),
            "utilization": f"Average utilization headroom score: {score:.1f}.",
            "dependency_depth": self._depth_detail(graph),
            "health": f"{sum(1 for c in components if c.health == HealthStatus.HEALTHY)}/{n} components are healthy.",
            "retry": self._retry_detail(graph),
            "autoscale_readiness": f"{sum(1 for c in components if c.autoscaling.enabled)}/{n} components have autoscaling.",
            "load_distribution": f"Load distribution score: {score:.1f}.",
            "right_sizing": f"Right-sizing score: {score:.1f}.",
        }
        return detail_map.get(func_id, f"Score: {score:.1f}")

    def _failover_detail(self, graph: InfraGraph) -> str:
        components = list(graph.components.values())
        critical = [c for c in components if len(graph.get_dependents(c.id)) > 0]
        if not critical:
            return "No critical components found."
        with_fo = sum(1 for c in critical if c.failover.enabled)
        return f"{with_fo}/{len(critical)} critical components have failover enabled."

    def _spof_detail(self, graph: InfraGraph) -> str:
        components = list(graph.components.values())
        spofs = [
            c.id for c in components
            if c.replicas <= 1 and len(graph.get_dependents(c.id)) > 0
        ]
        if not spofs:
            return "No single points of failure detected."
        return f"SPOFs detected: {', '.join(spofs)}."

    def _cb_detail(self, graph: InfraGraph) -> str:
        edges = graph.all_dependency_edges()
        if not edges:
            return "No dependency edges to evaluate."
        cb = sum(1 for e in edges if e.circuit_breaker.enabled)
        return f"{cb}/{len(edges)} dependencies have circuit breakers."

    def _backup_detail(self, graph: InfraGraph) -> str:
        data_stores = [
            c for c in graph.components.values()
            if c.type in {ComponentType.DATABASE, ComponentType.STORAGE}
        ]
        if not data_stores:
            return "No data stores to evaluate."
        backed = sum(1 for c in data_stores if c.security.backup_enabled)
        return f"{backed}/{len(data_stores)} data stores have backups."

    def _compliance_detail(self, graph: InfraGraph) -> str:
        components = list(graph.components.values())
        tagged = sum(
            1 for c in components
            if c.compliance_tags.pci_scope or c.compliance_tags.contains_pii
        )
        return f"{tagged}/{len(components)} components have compliance tags."

    def _depth_detail(self, graph: InfraGraph) -> str:
        paths = graph.get_critical_paths()
        depth = len(paths[0]) if paths else 0
        return f"Maximum dependency chain depth: {depth}."

    def _retry_detail(self, graph: InfraGraph) -> str:
        edges = graph.all_dependency_edges()
        if not edges:
            return "No dependency edges to evaluate."
        with_retry = sum(1 for e in edges if e.retry_strategy.max_retries > 0)
        return f"{with_retry}/{len(edges)} dependencies have retry strategies."

    # ------------------------------------------------------------------
    # RESILIENCE fitness functions
    # ------------------------------------------------------------------

    def _eval_redundancy(self, graph: InfraGraph) -> float:
        """% of components with replicas > 1."""
        components = list(graph.components.values())
        if not components:
            return 100.0
        redundant = sum(1 for c in components if c.replicas > 1)
        return (redundant / len(components)) * 100.0

    def _eval_failover(self, graph: InfraGraph) -> float:
        """% of critical components (with dependents) that have failover enabled."""
        components = list(graph.components.values())
        critical = [c for c in components if len(graph.get_dependents(c.id)) > 0]
        if not critical:
            return 100.0
        with_failover = sum(1 for c in critical if c.failover.enabled)
        return (with_failover / len(critical)) * 100.0

    def _eval_spof(self, graph: InfraGraph) -> float:
        """Inverse of SPOF ratio. Fewer SPOFs = higher score."""
        components = list(graph.components.values())
        if not components:
            return 100.0
        spof_count = sum(
            1 for c in components
            if c.replicas <= 1 and len(graph.get_dependents(c.id)) > 0
        )
        spof_ratio = spof_count / len(components)
        return (1.0 - spof_ratio) * 100.0

    def _eval_circuit_breaker(self, graph: InfraGraph) -> float:
        """% of dependencies with circuit breakers enabled."""
        edges = graph.all_dependency_edges()
        if not edges:
            return 100.0
        cb_enabled = sum(1 for e in edges if e.circuit_breaker.enabled)
        return (cb_enabled / len(edges)) * 100.0

    # ------------------------------------------------------------------
    # SECURITY fitness functions
    # ------------------------------------------------------------------

    def _eval_encryption(self, graph: InfraGraph) -> float:
        """% of components with encryption (at rest or in transit)."""
        components = list(graph.components.values())
        if not components:
            return 100.0
        encrypted = sum(
            1 for c in components
            if c.security.encryption_at_rest or c.security.encryption_in_transit
        )
        return (encrypted / len(components)) * 100.0

    def _eval_monitoring(self, graph: InfraGraph) -> float:
        """% of components with logging enabled."""
        components = list(graph.components.values())
        if not components:
            return 100.0
        monitored = sum(1 for c in components if c.security.log_enabled)
        return (monitored / len(components)) * 100.0

    def _eval_backup(self, graph: InfraGraph) -> float:
        """% of data stores (DATABASE, STORAGE) with backups enabled."""
        components = list(graph.components.values())
        data_stores = [
            c for c in components
            if c.type in {ComponentType.DATABASE, ComponentType.STORAGE}
        ]
        if not data_stores:
            return 100.0
        backed = sum(1 for c in data_stores if c.security.backup_enabled)
        return (backed / len(data_stores)) * 100.0

    def _eval_compliance(self, graph: InfraGraph) -> float:
        """Compliance tag coverage across components."""
        components = list(graph.components.values())
        if not components:
            return 100.0
        tagged = sum(
            1 for c in components
            if c.compliance_tags.pci_scope or c.compliance_tags.contains_pii
        )
        return (tagged / len(components)) * 100.0

    # ------------------------------------------------------------------
    # PERFORMANCE fitness functions
    # ------------------------------------------------------------------

    def _eval_utilization(self, graph: InfraGraph) -> float:
        """Inverse of avg utilization. Lower utilization = more headroom = higher score."""
        components = list(graph.components.values())
        if not components:
            return 100.0
        avg_util = sum(c.utilization() for c in components) / len(components)
        # 0% utilization -> 100 score, 100% utilization -> 0 score
        return max(0.0, 100.0 - avg_util)

    def _eval_dependency_depth(self, graph: InfraGraph) -> float:
        """Penalty for deep dependency chains. Depth 1-3 = 100, 10+ = 0."""
        components = list(graph.components.values())
        if not components:
            return 100.0
        paths = graph.get_critical_paths()
        if not paths:
            return 100.0
        max_depth = len(paths[0])
        if max_depth <= 3:
            return 100.0
        if max_depth >= 10:
            return 0.0
        # Linear decay from 100 at depth 3 to 0 at depth 10
        return max(0.0, 100.0 * (1.0 - (max_depth - 3) / 7.0))

    # ------------------------------------------------------------------
    # OPERABILITY fitness functions
    # ------------------------------------------------------------------

    def _eval_health(self, graph: InfraGraph) -> float:
        """% of components in HEALTHY state."""
        components = list(graph.components.values())
        if not components:
            return 100.0
        healthy = sum(1 for c in components if c.health == HealthStatus.HEALTHY)
        return (healthy / len(components)) * 100.0

    def _eval_retry(self, graph: InfraGraph) -> float:
        """% of dependencies with retry strategies (max_retries > 0)."""
        edges = graph.all_dependency_edges()
        if not edges:
            return 100.0
        with_retry = sum(1 for e in edges if e.retry_strategy.max_retries > 0)
        return (with_retry / len(edges)) * 100.0

    # ------------------------------------------------------------------
    # SCALABILITY fitness functions
    # ------------------------------------------------------------------

    def _eval_autoscale_readiness(self, graph: InfraGraph) -> float:
        """% of components configured for scaling (autoscaling enabled)."""
        components = list(graph.components.values())
        if not components:
            return 100.0
        scaled = sum(1 for c in components if c.autoscaling.enabled)
        return (scaled / len(components)) * 100.0

    def _eval_load_distribution(self, graph: InfraGraph) -> float:
        """How evenly load is distributed. Lower utilization variance = higher score."""
        components = list(graph.components.values())
        if not components:
            return 100.0
        utils = [c.utilization() for c in components]
        if len(utils) < 2:
            return 100.0
        mean_util = sum(utils) / len(utils)
        variance = sum((u - mean_util) ** 2 for u in utils) / len(utils)
        stddev = variance ** 0.5
        # stddev 0 -> 100, stddev >= 50 -> 0, linear
        if stddev <= 0.0:
            return 100.0
        if stddev >= 50.0:
            return 0.0
        return max(0.0, 100.0 * (1.0 - stddev / 50.0))

    # ------------------------------------------------------------------
    # COST_EFFICIENCY fitness functions
    # ------------------------------------------------------------------

    def _eval_right_sizing(self, graph: InfraGraph) -> float:
        """Penalize over-provisioned or under-utilized components.

        Components with utilization between 20-80% are considered well-sized.
        Below 20% is over-provisioned, above 80% is under-provisioned.
        """
        components = list(graph.components.values())
        if not components:
            return 100.0
        well_sized = 0
        for c in components:
            util = c.utilization()
            if 20.0 <= util <= 80.0:
                well_sized += 1
            elif util == 0.0:
                # No utilization data; assume well-sized
                well_sized += 1
        return (well_sized / len(components)) * 100.0
