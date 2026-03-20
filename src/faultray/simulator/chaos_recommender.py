# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""AI-powered chaos experiment recommendation engine.

Analyzes infrastructure topology and current resilience posture to recommend
the most impactful chaos experiments. Prioritizes experiments based on
coverage gaps, risk exposure, and potential learning value.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from faultray.model.components import ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ExperimentType(str, Enum):
    NODE_FAILURE = "node_failure"
    NETWORK_PARTITION = "network_partition"
    LATENCY_INJECTION = "latency_injection"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    DEPENDENCY_FAILURE = "dependency_failure"
    CASCADE_TEST = "cascade_test"
    FAILOVER_TEST = "failover_test"
    LOAD_SPIKE = "load_spike"
    DNS_FAILURE = "dns_failure"
    CONFIG_CORRUPTION = "config_corruption"


class Priority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ChaosExperiment:
    experiment_type: ExperimentType
    target_component_id: str
    target_component_name: str
    priority: Priority
    confidence: Confidence
    rationale: str
    expected_impact: str
    blast_radius: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    estimated_risk_level: float = 0.5


@dataclass
class CoverageGap:
    component_id: str
    component_name: str
    gap_type: str
    description: str
    severity: float = 0.5


@dataclass
class RecommendationReport:
    experiments: list[ChaosExperiment] = field(default_factory=list)
    coverage_gaps: list[CoverageGap] = field(default_factory=list)
    total_experiments: int = 0
    critical_count: int = 0
    high_count: int = 0
    coverage_score: float = 100.0
    recommendations_summary: str = ""


# ---------------------------------------------------------------------------
# Recommender
# ---------------------------------------------------------------------------

class ChaosRecommender:
    """Analyzes an ``InfraGraph`` and recommends chaos experiments."""

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    # -- public API ---------------------------------------------------------

    def recommend(self, max_experiments: int = 10) -> RecommendationReport:
        """Generate a full recommendation report.

        Parameters
        ----------
        max_experiments:
            Maximum number of experiments to include in the report.
        """
        coverage_gaps = self._analyze_coverage_gaps()
        experiments = self._generate_experiments()
        experiments = self._prioritize(experiments)

        # Limit the result set
        experiments = experiments[:max_experiments]

        critical_count = sum(1 for e in experiments if e.priority == Priority.CRITICAL)
        high_count = sum(1 for e in experiments if e.priority == Priority.HIGH)

        coverage_score = self._calculate_coverage_score(coverage_gaps)
        summary = self._build_summary(experiments, coverage_gaps, coverage_score)

        return RecommendationReport(
            experiments=experiments,
            coverage_gaps=coverage_gaps,
            total_experiments=len(experiments),
            critical_count=critical_count,
            high_count=high_count,
            coverage_score=coverage_score,
            recommendations_summary=summary,
        )

    # -- private helpers ----------------------------------------------------

    def _analyze_coverage_gaps(self) -> list[CoverageGap]:
        """Detect coverage gaps across all components."""
        gaps: list[CoverageGap] = []
        components = self._graph.components

        for comp in components.values():
            dependents = self._graph.get_dependents(comp.id)
            num_dependents = len(dependents)

            # 1. No failover
            if not comp.failover.enabled:
                gaps.append(CoverageGap(
                    component_id=comp.id,
                    component_name=comp.name,
                    gap_type="no_failover",
                    description=f"Component '{comp.name}' does not have failover enabled.",
                    severity=0.8 if num_dependents >= 3 else 0.5,
                ))

            # 2. Single replica
            if comp.replicas == 1:
                gaps.append(CoverageGap(
                    component_id=comp.id,
                    component_name=comp.name,
                    gap_type="single_replica",
                    description=f"Component '{comp.name}' has only 1 replica.",
                    severity=0.9 if num_dependents >= 3 else 0.5,
                ))

            # 3. No redundancy in critical path
            if num_dependents >= 3:
                gaps.append(CoverageGap(
                    component_id=comp.id,
                    component_name=comp.name,
                    gap_type="critical_path_no_redundancy",
                    description=(
                        f"Component '{comp.name}' is a dependency for "
                        f"{num_dependents} other components."
                    ),
                    severity=min(1.0, 0.5 + num_dependents * 0.1),
                ))

            # 4. High resource usage
            metrics = comp.metrics
            high_resources: list[str] = []
            if metrics.cpu_percent > 70:
                high_resources.append("CPU")
            if metrics.memory_percent > 70:
                high_resources.append("memory")
            if metrics.disk_percent > 70:
                high_resources.append("disk")
            if high_resources:
                gaps.append(CoverageGap(
                    component_id=comp.id,
                    component_name=comp.name,
                    gap_type="high_resource_usage",
                    description=(
                        f"Component '{comp.name}' has high {', '.join(high_resources)} usage."
                    ),
                    severity=0.7,
                ))

            # 5. External dependencies
            if comp.type == ComponentType.EXTERNAL_API:
                gaps.append(CoverageGap(
                    component_id=comp.id,
                    component_name=comp.name,
                    gap_type="external_dependency",
                    description=f"Component '{comp.name}' is an external API dependency.",
                    severity=0.6,
                ))

            # 6. Load balancer absence – WEB_SERVER without LB as dependency target
            if comp.type == ComponentType.WEB_SERVER:
                deps = self._graph.get_dependencies(comp.id)
                has_lb = any(d.type == ComponentType.LOAD_BALANCER for d in deps)
                dep_of_lb = any(
                    d.type == ComponentType.LOAD_BALANCER
                    for d in dependents
                )
                if not has_lb and not dep_of_lb:
                    gaps.append(CoverageGap(
                        component_id=comp.id,
                        component_name=comp.name,
                        gap_type="no_load_balancer",
                        description=(
                            f"Web server '{comp.name}' has no load balancer association."
                        ),
                        severity=0.6,
                    ))

            # 7. DNS single point of failure
            if comp.type == ComponentType.DNS and comp.replicas == 1:
                gaps.append(CoverageGap(
                    component_id=comp.id,
                    component_name=comp.name,
                    gap_type="dns_spof",
                    description=f"DNS component '{comp.name}' has only 1 replica (SPOF).",
                    severity=0.8,
                ))

            # 8. Unhealthy components
            if comp.health in (HealthStatus.DEGRADED, HealthStatus.DOWN, HealthStatus.OVERLOADED):
                gaps.append(CoverageGap(
                    component_id=comp.id,
                    component_name=comp.name,
                    gap_type="unhealthy",
                    description=(
                        f"Component '{comp.name}' is currently {comp.health.value}."
                    ),
                    severity=0.9 if comp.health == HealthStatus.DOWN else 0.7,
                ))

            # 9. Network bottlenecks
            if comp.capacity.max_connections > 0 and comp.metrics.network_connections > 0:
                ratio = comp.metrics.network_connections / comp.capacity.max_connections
                if ratio > 0.7:
                    gaps.append(CoverageGap(
                        component_id=comp.id,
                        component_name=comp.name,
                        gap_type="network_bottleneck",
                        description=(
                            f"Component '{comp.name}' connection ratio is {ratio:.0%}."
                        ),
                        severity=min(1.0, ratio),
                    ))

            # 10. Config drift risk – missing security controls
            sec = comp.security
            missing_controls: list[str] = []
            if not sec.encryption_at_rest:
                missing_controls.append("encryption_at_rest")
            if not sec.encryption_in_transit:
                missing_controls.append("encryption_in_transit")
            if not sec.rate_limiting:
                missing_controls.append("rate_limiting")
            if not sec.backup_enabled:
                missing_controls.append("backup")
            if missing_controls:
                gaps.append(CoverageGap(
                    component_id=comp.id,
                    component_name=comp.name,
                    gap_type="config_drift_risk",
                    description=(
                        f"Component '{comp.name}' lacks security controls: "
                        f"{', '.join(missing_controls)}."
                    ),
                    severity=min(1.0, 0.3 + len(missing_controls) * 0.1),
                ))

        return gaps

    def _generate_experiments(self) -> list[ChaosExperiment]:
        """Generate candidate experiments from coverage gaps."""
        experiments: list[ChaosExperiment] = []
        components = self._graph.components

        for comp in components.values():
            dependents = self._graph.get_dependents(comp.id)
            num_dependents = len(dependents)
            blast = list(self._compute_blast_radius(comp.id))

            # 1. No failover → FAILOVER_TEST
            if not comp.failover.enabled:
                experiments.append(ChaosExperiment(
                    experiment_type=ExperimentType.FAILOVER_TEST,
                    target_component_id=comp.id,
                    target_component_name=comp.name,
                    priority=Priority.MEDIUM,  # placeholder, set in _prioritize
                    confidence=Confidence.HIGH,
                    rationale=f"Component '{comp.name}' does not have failover enabled.",
                    expected_impact="Unknown recovery behavior on component failure.",
                    blast_radius=blast,
                    prerequisites=["Enable failover configuration before testing"],
                    estimated_risk_level=0.6,
                ))

            # 2. Single replica → NODE_FAILURE
            if comp.replicas == 1:
                experiments.append(ChaosExperiment(
                    experiment_type=ExperimentType.NODE_FAILURE,
                    target_component_id=comp.id,
                    target_component_name=comp.name,
                    priority=Priority.MEDIUM,
                    confidence=Confidence.HIGH,
                    rationale=f"Component '{comp.name}' runs on a single replica.",
                    expected_impact="Complete outage for this component and its dependents.",
                    blast_radius=blast,
                    prerequisites=[],
                    estimated_risk_level=0.7,
                ))

            # 3. Critical path (3+ dependents) → CASCADE_TEST
            if num_dependents >= 3:
                experiments.append(ChaosExperiment(
                    experiment_type=ExperimentType.CASCADE_TEST,
                    target_component_id=comp.id,
                    target_component_name=comp.name,
                    priority=Priority.MEDIUM,
                    confidence=Confidence.HIGH,
                    rationale=(
                        f"Component '{comp.name}' has {num_dependents} dependents; "
                        "failure may cascade widely."
                    ),
                    expected_impact=f"Potential cascade affecting {len(blast)} components.",
                    blast_radius=blast,
                    prerequisites=[],
                    estimated_risk_level=0.8,
                ))

            # 4. High resource usage → RESOURCE_EXHAUSTION
            metrics = comp.metrics
            if metrics.cpu_percent > 70 or metrics.memory_percent > 70 or metrics.disk_percent > 70:
                experiments.append(ChaosExperiment(
                    experiment_type=ExperimentType.RESOURCE_EXHAUSTION,
                    target_component_id=comp.id,
                    target_component_name=comp.name,
                    priority=Priority.MEDIUM,
                    confidence=Confidence.MEDIUM,
                    rationale=f"Component '{comp.name}' already has high resource usage.",
                    expected_impact="Service degradation or crash under additional load.",
                    blast_radius=blast,
                    prerequisites=[],
                    estimated_risk_level=0.6,
                ))

            # 5. External dependency → DEPENDENCY_FAILURE
            if comp.type == ComponentType.EXTERNAL_API:
                experiments.append(ChaosExperiment(
                    experiment_type=ExperimentType.DEPENDENCY_FAILURE,
                    target_component_id=comp.id,
                    target_component_name=comp.name,
                    priority=Priority.MEDIUM,
                    confidence=Confidence.MEDIUM,
                    rationale=f"External API '{comp.name}' is an uncontrolled dependency.",
                    expected_impact="Dependent services may fail or degrade.",
                    blast_radius=blast,
                    prerequisites=["Verify fallback/circuit-breaker is configured"],
                    estimated_risk_level=0.5,
                ))

            # 6. WEB_SERVER without LB → LOAD_SPIKE
            if comp.type == ComponentType.WEB_SERVER:
                deps = self._graph.get_dependencies(comp.id)
                has_lb = any(d.type == ComponentType.LOAD_BALANCER for d in deps)
                dep_of_lb = any(
                    d.type == ComponentType.LOAD_BALANCER
                    for d in dependents
                )
                if not has_lb and not dep_of_lb:
                    experiments.append(ChaosExperiment(
                        experiment_type=ExperimentType.LOAD_SPIKE,
                        target_component_id=comp.id,
                        target_component_name=comp.name,
                        priority=Priority.MEDIUM,
                        confidence=Confidence.MEDIUM,
                        rationale=(
                            f"Web server '{comp.name}' has no load balancer; "
                            "traffic is not distributed."
                        ),
                        expected_impact="Service may become overwhelmed under traffic spike.",
                        blast_radius=blast,
                        prerequisites=[],
                        estimated_risk_level=0.6,
                    ))

            # 7. DNS SPOF → DNS_FAILURE
            if comp.type == ComponentType.DNS and comp.replicas == 1:
                experiments.append(ChaosExperiment(
                    experiment_type=ExperimentType.DNS_FAILURE,
                    target_component_id=comp.id,
                    target_component_name=comp.name,
                    priority=Priority.MEDIUM,
                    confidence=Confidence.HIGH,
                    rationale=f"DNS component '{comp.name}' is a single point of failure.",
                    expected_impact="All DNS-dependent services will be unreachable.",
                    blast_radius=blast,
                    prerequisites=[],
                    estimated_risk_level=0.9,
                ))

            # 8. Unhealthy → NODE_FAILURE (understand cascade)
            if comp.health in (HealthStatus.DEGRADED, HealthStatus.DOWN, HealthStatus.OVERLOADED):
                experiments.append(ChaosExperiment(
                    experiment_type=ExperimentType.NODE_FAILURE,
                    target_component_id=comp.id,
                    target_component_name=comp.name,
                    priority=Priority.MEDIUM,
                    confidence=Confidence.LOW,
                    rationale=(
                        f"Component '{comp.name}' is already {comp.health.value}; "
                        "testing failure behaviour reveals cascade impact."
                    ),
                    expected_impact="Understand how an already-degraded component's failure cascades.",
                    blast_radius=blast,
                    prerequisites=["Ensure monitoring is in place"],
                    estimated_risk_level=0.8,
                ))

            # 9. Network bottleneck → NETWORK_PARTITION
            if comp.capacity.max_connections > 0 and comp.metrics.network_connections > 0:
                ratio = comp.metrics.network_connections / comp.capacity.max_connections
                if ratio > 0.7:
                    experiments.append(ChaosExperiment(
                        experiment_type=ExperimentType.NETWORK_PARTITION,
                        target_component_id=comp.id,
                        target_component_name=comp.name,
                        priority=Priority.MEDIUM,
                        confidence=Confidence.MEDIUM,
                        rationale=(
                            f"Component '{comp.name}' is at {ratio:.0%} network capacity."
                        ),
                        expected_impact="Connection saturation or complete partition.",
                        blast_radius=blast,
                        prerequisites=[],
                        estimated_risk_level=0.7,
                    ))

            # 10. Config drift risk → CONFIG_CORRUPTION
            sec = comp.security
            missing = []
            if not sec.encryption_at_rest:
                missing.append("encryption_at_rest")
            if not sec.encryption_in_transit:
                missing.append("encryption_in_transit")
            if not sec.rate_limiting:
                missing.append("rate_limiting")
            if not sec.backup_enabled:
                missing.append("backup")
            if missing:
                experiments.append(ChaosExperiment(
                    experiment_type=ExperimentType.CONFIG_CORRUPTION,
                    target_component_id=comp.id,
                    target_component_name=comp.name,
                    priority=Priority.MEDIUM,
                    confidence=Confidence.LOW,
                    rationale=(
                        f"Component '{comp.name}' lacks security controls: "
                        f"{', '.join(missing)}."
                    ),
                    expected_impact="Potential data exposure or unrecoverable state.",
                    blast_radius=blast,
                    prerequisites=["Backup current configuration"],
                    estimated_risk_level=0.5,
                ))

        return experiments

    def _prioritize(self, experiments: list[ChaosExperiment]) -> list[ChaosExperiment]:
        """Assign priority to each experiment and sort by priority/risk."""
        components = self._graph.components

        for exp in experiments:
            comp = components.get(exp.target_component_id)
            if comp is None:
                exp.priority = Priority.LOW
                continue

            dependents = self._graph.get_dependents(comp.id)
            num_dependents = len(dependents)

            # CRITICAL: 5+ dependents, single replica, no failover
            if num_dependents >= 5 and comp.replicas == 1 and not comp.failover.enabled:
                exp.priority = Priority.CRITICAL
            # CRITICAL: 5+ dependents (even if other mitigations)
            elif num_dependents >= 5:
                exp.priority = Priority.CRITICAL
            # HIGH: 3+ dependents OR high resource usage
            elif num_dependents >= 3:
                exp.priority = Priority.HIGH
            elif (
                comp.metrics.cpu_percent > 70
                or comp.metrics.memory_percent > 70
                or comp.metrics.disk_percent > 70
            ):
                exp.priority = Priority.HIGH
            # MEDIUM: 1-2 dependents
            elif num_dependents >= 1:
                exp.priority = Priority.MEDIUM
            # LOW: leaf or well-protected
            else:
                exp.priority = Priority.LOW

        # Sort order: CRITICAL > HIGH > MEDIUM > LOW, then by risk descending
        priority_order = {
            Priority.CRITICAL: 0,
            Priority.HIGH: 1,
            Priority.MEDIUM: 2,
            Priority.LOW: 3,
        }
        experiments.sort(
            key=lambda e: (priority_order[e.priority], -e.estimated_risk_level),
        )
        return experiments

    # -- utility ------------------------------------------------------------

    def _compute_blast_radius(self, component_id: str) -> list[str]:
        """BFS to find all transitive dependents (components that would be affected)."""
        affected: list[str] = []
        visited: set[str] = set()
        queue: deque[str] = deque([component_id])

        while queue:
            current = queue.popleft()
            for dep in self._graph.get_dependents(current):
                if dep.id not in visited:
                    visited.add(dep.id)
                    affected.append(dep.id)
                    queue.append(dep.id)

        return affected

    @staticmethod
    def _calculate_coverage_score(gaps: list[CoverageGap]) -> float:
        """Derive a coverage score (0-100) from the detected gaps.

        Rules:
        - Start at 100
        - severity >= 0.8 → CRITICAL, subtract 10
        - 0.6 <= severity < 0.8 → HIGH, subtract 5
        - severity < 0.6 → MEDIUM, subtract 2
        """
        score = 100.0
        for gap in gaps:
            if gap.severity >= 0.8:
                score -= 10
            elif gap.severity >= 0.6:
                score -= 5
            else:
                score -= 2
        return max(0.0, score)

    @staticmethod
    def _build_summary(
        experiments: list[ChaosExperiment],
        gaps: list[CoverageGap],
        coverage_score: float,
    ) -> str:
        """Build a human-readable summary string."""
        if not experiments and not gaps:
            return "No chaos experiments recommended. Infrastructure appears well-protected."

        parts: list[str] = []
        parts.append(
            f"Identified {len(gaps)} coverage gap(s) and recommending "
            f"{len(experiments)} chaos experiment(s)."
        )

        critical = sum(1 for e in experiments if e.priority == Priority.CRITICAL)
        high = sum(1 for e in experiments if e.priority == Priority.HIGH)
        if critical:
            parts.append(f"{critical} experiment(s) are CRITICAL priority.")
        if high:
            parts.append(f"{high} experiment(s) are HIGH priority.")

        parts.append(f"Overall coverage score: {coverage_score:.1f}/100.")

        return " ".join(parts)
