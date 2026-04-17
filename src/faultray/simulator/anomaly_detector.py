# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Infrastructure Anomaly Detection Engine.

Detects unusual patterns in infrastructure configurations including:
- Utilization spikes and waste
- Health status anomalies
- Topology issues (deep chains, orphans, circular deps, fan-out)
- Configuration anomalies (missing replicas, failover, over-provisioning)
- Security gaps (encryption, logging, backups)
- Dependency relationship anomalies (missing circuit breakers, single deps)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from faultray.model.components import ComponentType, HealthStatus
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AnomalyType(str, Enum):
    UTILIZATION_SPIKE = "utilization_spike"
    HEALTH_ANOMALY = "health_anomaly"
    TOPOLOGY_ANOMALY = "topology_anomaly"
    CONFIGURATION_ANOMALY = "configuration_anomaly"
    SECURITY_ANOMALY = "security_anomaly"
    CAPACITY_ANOMALY = "capacity_anomaly"
    DEPENDENCY_ANOMALY = "dependency_anomaly"


class AnomalySeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Anomaly:
    """A single detected anomaly."""

    id: str
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    component_id: str
    component_name: str
    description: str
    metric_value: float
    expected_range: str  # e.g., "0-80%"
    confidence: float  # 0-1.0
    recommendation: str


@dataclass
class AnomalyReport:
    """Complete anomaly detection report."""

    anomalies: list[Anomaly] = field(default_factory=list)
    total_count: int = 0
    critical_count: int = 0
    high_count: int = 0
    health_score: float = 100.0  # 0-100, based on anomaly findings
    risk_areas: list[str] = field(default_factory=list)
    top_recommendations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Severity penalties for health score calculation
# ---------------------------------------------------------------------------

_SEVERITY_PENALTY = {
    AnomalySeverity.CRITICAL: 15,
    AnomalySeverity.HIGH: 10,
    AnomalySeverity.MEDIUM: 5,
    AnomalySeverity.LOW: 2,
    AnomalySeverity.INFO: 0,
}


# ---------------------------------------------------------------------------
# AnomalyDetector
# ---------------------------------------------------------------------------


class AnomalyDetector:
    """Detects anomalies in infrastructure configurations."""

    def __init__(
        self,
        utilization_threshold: float = 80.0,
        dependency_depth_threshold: int = 4,
        min_replicas_for_critical: int = 2,
    ) -> None:
        self._util_threshold = utilization_threshold
        self._depth_threshold = dependency_depth_threshold
        self._min_replicas = min_replicas_for_critical

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def detect(self, graph: InfraGraph) -> AnomalyReport:
        """Run all anomaly detection checks and compile a report."""
        all_anomalies: list[Anomaly] = []
        all_anomalies.extend(self.detect_utilization_anomalies(graph))
        all_anomalies.extend(self.detect_health_anomalies(graph))
        all_anomalies.extend(self.detect_topology_anomalies(graph))
        all_anomalies.extend(self.detect_configuration_anomalies(graph))
        all_anomalies.extend(self.detect_security_anomalies(graph))
        all_anomalies.extend(self.detect_dependency_anomalies(graph))

        total_count = len(all_anomalies)
        critical_count = sum(
            1 for a in all_anomalies if a.severity == AnomalySeverity.CRITICAL
        )
        high_count = sum(
            1 for a in all_anomalies if a.severity == AnomalySeverity.HIGH
        )

        # Health score: 100 minus penalties per anomaly severity
        health_score = 100.0
        for a in all_anomalies:
            health_score -= _SEVERITY_PENALTY.get(a.severity, 0)
        health_score = max(0.0, health_score)

        # Risk areas: deduplicated anomaly type descriptions
        risk_set: list[str] = []
        seen_types: set[str] = set()
        for a in all_anomalies:
            label = a.anomaly_type.value
            if label not in seen_types:
                seen_types.add(label)
                risk_set.append(label)

        # Top recommendations from highest severity anomalies (top 5)
        severity_order = {
            AnomalySeverity.CRITICAL: 0,
            AnomalySeverity.HIGH: 1,
            AnomalySeverity.MEDIUM: 2,
            AnomalySeverity.LOW: 3,
            AnomalySeverity.INFO: 4,
        }
        sorted_anomalies = sorted(
            all_anomalies, key=lambda a: severity_order.get(a.severity, 5)
        )
        seen_recs: set[str] = set()
        top_recs: list[str] = []
        for a in sorted_anomalies:
            if a.recommendation and a.recommendation not in seen_recs:
                seen_recs.add(a.recommendation)
                top_recs.append(a.recommendation)
            if len(top_recs) >= 5:
                break

        return AnomalyReport(
            anomalies=all_anomalies,
            total_count=total_count,
            critical_count=critical_count,
            high_count=high_count,
            health_score=health_score,
            risk_areas=risk_set,
            top_recommendations=top_recs,
        )

    # ------------------------------------------------------------------
    # Utilization anomalies
    # ------------------------------------------------------------------

    def detect_utilization_anomalies(self, graph: InfraGraph) -> list[Anomaly]:
        """Detect components with abnormal utilization levels.

        Checks for:
        - High utilization (above threshold) -- potential spike/bottleneck
        - Zero utilization on non-trivial components -- potential waste
        """
        anomalies: list[Anomaly] = []
        for comp in graph.components.values():
            util = comp.utilization()

            # High utilization
            if util > self._util_threshold:
                if util > 95.0:
                    severity = AnomalySeverity.CRITICAL
                    confidence = 0.95
                elif util > 90.0:
                    severity = AnomalySeverity.HIGH
                    confidence = 0.9
                else:
                    severity = AnomalySeverity.MEDIUM
                    confidence = 0.8

                anomalies.append(Anomaly(
                    id=f"{AnomalyType.UTILIZATION_SPIKE.value}-{comp.id}",
                    anomaly_type=AnomalyType.UTILIZATION_SPIKE,
                    severity=severity,
                    component_id=comp.id,
                    component_name=comp.name,
                    description=(
                        f"Utilization at {util:.1f}% exceeds threshold "
                        f"of {self._util_threshold}%."
                    ),
                    metric_value=util,
                    expected_range=f"0-{self._util_threshold:.0f}%",
                    confidence=confidence,
                    recommendation=(
                        "Scale up capacity, enable autoscaling, or redistribute load "
                        f"to bring utilization below {self._util_threshold:.0f}%."
                    ),
                ))

            # Zero utilization (waste detection) -- only flag if component has
            # metrics configured (at least one metric field is set implicitly
            # through Component defaults, so util==0 means truly idle)
            elif util == 0.0 and comp.replicas > 1:
                anomalies.append(Anomaly(
                    id=f"{AnomalyType.CAPACITY_ANOMALY.value}-{comp.id}-idle",
                    anomaly_type=AnomalyType.CAPACITY_ANOMALY,
                    severity=AnomalySeverity.LOW,
                    component_id=comp.id,
                    component_name=comp.name,
                    description=(
                        f"Component has {comp.replicas} replicas but zero utilization. "
                        "Possible resource waste."
                    ),
                    metric_value=util,
                    expected_range="1-80%",
                    confidence=0.6,
                    recommendation=(
                        "Verify that the component is actively used. Consider reducing "
                        "replicas or decommissioning if idle."
                    ),
                ))

        return anomalies

    # ------------------------------------------------------------------
    # Health anomalies
    # ------------------------------------------------------------------

    def detect_health_anomalies(self, graph: InfraGraph) -> list[Anomaly]:
        """Detect components with abnormal health status.

        Checks for DOWN, DEGRADED, and OVERLOADED statuses.
        """
        anomalies: list[Anomaly] = []
        _health_severity = {
            HealthStatus.DOWN: AnomalySeverity.CRITICAL,
            HealthStatus.DEGRADED: AnomalySeverity.HIGH,
            HealthStatus.OVERLOADED: AnomalySeverity.HIGH,
        }

        for comp in graph.components.values():
            if comp.health in _health_severity:
                severity = _health_severity[comp.health]
                dependents = graph.get_dependents(comp.id)
                dep_count = len(dependents)

                # Increase confidence if the component has dependents
                confidence = 0.9 if dep_count > 0 else 0.8

                anomalies.append(Anomaly(
                    id=f"{AnomalyType.HEALTH_ANOMALY.value}-{comp.id}",
                    anomaly_type=AnomalyType.HEALTH_ANOMALY,
                    severity=severity,
                    component_id=comp.id,
                    component_name=comp.name,
                    description=(
                        f"Component health is {comp.health.value}. "
                        f"{dep_count} dependent component(s) may be affected."
                    ),
                    metric_value=dep_count,
                    expected_range="healthy",
                    confidence=confidence,
                    recommendation=(
                        f"Investigate and restore '{comp.name}' to healthy status. "
                        f"Check logs, restart if needed, and verify dependent services."
                    ),
                ))

        return anomalies

    # ------------------------------------------------------------------
    # Topology anomalies
    # ------------------------------------------------------------------

    def detect_topology_anomalies(self, graph: InfraGraph) -> list[Anomaly]:
        """Detect unusual topology patterns.

        Checks for:
        - Deep dependency chains (depth > threshold)
        - Orphan components (no deps and no dependents)
        - Circular dependencies
        - Overly connected components (fan-out > 5)
        """
        anomalies: list[Anomaly] = []
        components = list(graph.components.values())
        if not components:
            return anomalies

        # --- Deep dependency chains ---
        critical_paths = graph.get_critical_paths()
        if critical_paths:
            max_depth = len(critical_paths[0])
            if max_depth > self._depth_threshold:
                # Report on the first component in the deepest path
                first_id = critical_paths[0][0]
                comp = graph.get_component(first_id)
                comp_name = comp.name if comp else first_id
                path_str = " -> ".join(critical_paths[0])

                anomalies.append(Anomaly(
                    id=f"{AnomalyType.TOPOLOGY_ANOMALY.value}-deep-chain-{first_id}",
                    anomaly_type=AnomalyType.TOPOLOGY_ANOMALY,
                    severity=AnomalySeverity.HIGH,
                    component_id=first_id,
                    component_name=comp_name,
                    description=(
                        f"Deep dependency chain of depth {max_depth} detected "
                        f"(threshold: {self._depth_threshold}). "
                        f"Path: {path_str}"
                    ),
                    metric_value=float(max_depth),
                    expected_range=f"1-{self._depth_threshold}",
                    confidence=0.85,
                    recommendation=(
                        "Reduce dependency chain depth by introducing async "
                        "communication, caching, or restructuring the architecture."
                    ),
                ))

        # --- Orphan components ---
        for comp in components:
            dependents = graph.get_dependents(comp.id)
            dependencies = graph.get_dependencies(comp.id)
            if not dependents and not dependencies and len(components) > 1:
                anomalies.append(Anomaly(
                    id=f"{AnomalyType.TOPOLOGY_ANOMALY.value}-orphan-{comp.id}",
                    anomaly_type=AnomalyType.TOPOLOGY_ANOMALY,
                    severity=AnomalySeverity.LOW,
                    component_id=comp.id,
                    component_name=comp.name,
                    description=(
                        "Component has no dependencies and no dependents (orphan). "
                        "It may be unused or misconfigured."
                    ),
                    metric_value=0.0,
                    expected_range=">=1 connection",
                    confidence=0.7,
                    recommendation=(
                        "Verify that this component is needed and properly connected "
                        "in the dependency graph."
                    ),
                ))

        # --- Circular dependencies ---
        import networkx as nx
        try:
            cycles = list(nx.simple_cycles(graph._graph))
            for cycle in cycles[:5]:
                cycle_str = " -> ".join(cycle + [cycle[0]])
                comp = graph.get_component(cycle[0])
                comp_name = comp.name if comp else cycle[0]

                anomalies.append(Anomaly(
                    id=f"{AnomalyType.TOPOLOGY_ANOMALY.value}-cycle-{cycle[0]}",
                    anomaly_type=AnomalyType.TOPOLOGY_ANOMALY,
                    severity=AnomalySeverity.CRITICAL,
                    component_id=cycle[0],
                    component_name=comp_name,
                    description=(
                        f"Circular dependency detected: {cycle_str}. "
                        "This can cause deadlocks and cascade failures."
                    ),
                    metric_value=float(len(cycle)),
                    expected_range="no cycles",
                    confidence=1.0,
                    recommendation=(
                        "Break the circular dependency by introducing async "
                        "communication or restructuring the dependency graph."
                    ),
                ))
        except Exception as e:
            logger.warning("Circular dependency detection failed: %s", e)

        # --- Overly connected components (fan-out > 5) ---
        for comp in components:
            deps = graph.get_dependencies(comp.id)
            if len(deps) > 5:
                anomalies.append(Anomaly(
                    id=f"{AnomalyType.TOPOLOGY_ANOMALY.value}-fanout-{comp.id}",
                    anomaly_type=AnomalyType.TOPOLOGY_ANOMALY,
                    severity=AnomalySeverity.MEDIUM,
                    component_id=comp.id,
                    component_name=comp.name,
                    description=(
                        f"Component depends on {len(deps)} other components "
                        f"(fan-out > 5). High coupling risk."
                    ),
                    metric_value=float(len(deps)),
                    expected_range="1-5",
                    confidence=0.75,
                    recommendation=(
                        "Reduce fan-out by consolidating dependencies, introducing "
                        "an API gateway, or using a message queue."
                    ),
                ))

        return anomalies

    # ------------------------------------------------------------------
    # Configuration anomalies
    # ------------------------------------------------------------------

    def detect_configuration_anomalies(self, graph: InfraGraph) -> list[Anomaly]:
        """Detect configuration issues.

        Checks for:
        - Critical components (databases, etc.) without sufficient replicas
        - No failover on databases
        - Components with replicas > 10 (over-provisioned)
        """
        anomalies: list[Anomaly] = []

        for comp in graph.components.values():
            dependents = graph.get_dependents(comp.id)
            dep_count = len(dependents)

            # Critical components without enough replicas
            is_critical_type = comp.type in (
                ComponentType.DATABASE,
                ComponentType.LOAD_BALANCER,
                ComponentType.QUEUE,
            )
            if (is_critical_type or dep_count >= 2) and comp.replicas < self._min_replicas:
                severity = AnomalySeverity.CRITICAL if dep_count >= 2 else AnomalySeverity.HIGH
                anomalies.append(Anomaly(
                    id=f"{AnomalyType.CONFIGURATION_ANOMALY.value}-replicas-{comp.id}",
                    anomaly_type=AnomalyType.CONFIGURATION_ANOMALY,
                    severity=severity,
                    component_id=comp.id,
                    component_name=comp.name,
                    description=(
                        f"Component has {comp.replicas} replica(s) but requires at "
                        f"least {self._min_replicas} for reliability. "
                        f"Type: {comp.type.value}, dependents: {dep_count}."
                    ),
                    metric_value=float(comp.replicas),
                    expected_range=f">={self._min_replicas}",
                    confidence=0.9,
                    recommendation=(
                        f"Increase replicas to at least {self._min_replicas} "
                        f"to ensure high availability."
                    ),
                ))

            # No failover on databases
            if comp.type == ComponentType.DATABASE and not comp.failover.enabled:
                anomalies.append(Anomaly(
                    id=f"{AnomalyType.CONFIGURATION_ANOMALY.value}-failover-{comp.id}",
                    anomaly_type=AnomalyType.CONFIGURATION_ANOMALY,
                    severity=AnomalySeverity.HIGH,
                    component_id=comp.id,
                    component_name=comp.name,
                    description=(
                        "Database has no failover configured. "
                        "A failure will cause data unavailability."
                    ),
                    metric_value=0.0,
                    expected_range="failover enabled",
                    confidence=0.9,
                    recommendation=(
                        "Enable failover for the database to ensure automatic "
                        "recovery and reduce downtime."
                    ),
                ))

            # Over-provisioned replicas (> 10)
            if comp.replicas > 10:
                anomalies.append(Anomaly(
                    id=f"{AnomalyType.CONFIGURATION_ANOMALY.value}-overprov-{comp.id}",
                    anomaly_type=AnomalyType.CONFIGURATION_ANOMALY,
                    severity=AnomalySeverity.MEDIUM,
                    component_id=comp.id,
                    component_name=comp.name,
                    description=(
                        f"Component has {comp.replicas} replicas, which may be "
                        "over-provisioned. Review if this level of redundancy "
                        "is justified."
                    ),
                    metric_value=float(comp.replicas),
                    expected_range="1-10",
                    confidence=0.7,
                    recommendation=(
                        "Review replica count and reduce if not justified by "
                        "traffic or availability requirements."
                    ),
                ))

        return anomalies

    # ------------------------------------------------------------------
    # Security anomalies
    # ------------------------------------------------------------------

    def detect_security_anomalies(self, graph: InfraGraph) -> list[Anomaly]:
        """Detect security configuration gaps.

        Checks for:
        - Databases without encryption at rest
        - Components without logging enabled
        - Storage/database without backups
        """
        anomalies: list[Anomaly] = []

        for comp in graph.components.values():
            # Databases without encryption at rest
            if (
                comp.type == ComponentType.DATABASE
                and not comp.security.encryption_at_rest
            ):
                anomalies.append(Anomaly(
                    id=f"{AnomalyType.SECURITY_ANOMALY.value}-encrypt-{comp.id}",
                    anomaly_type=AnomalyType.SECURITY_ANOMALY,
                    severity=AnomalySeverity.CRITICAL,
                    component_id=comp.id,
                    component_name=comp.name,
                    description=(
                        "Database does not have encryption at rest enabled. "
                        "Data is vulnerable to unauthorized access."
                    ),
                    metric_value=0.0,
                    expected_range="encryption enabled",
                    confidence=0.95,
                    recommendation=(
                        "Enable encryption at rest to protect sensitive data "
                        "at the storage level."
                    ),
                ))

            # No logging
            if not comp.security.log_enabled:
                anomalies.append(Anomaly(
                    id=f"{AnomalyType.SECURITY_ANOMALY.value}-logging-{comp.id}",
                    anomaly_type=AnomalyType.SECURITY_ANOMALY,
                    severity=AnomalySeverity.MEDIUM,
                    component_id=comp.id,
                    component_name=comp.name,
                    description=(
                        "Logging is not enabled. Incidents cannot be "
                        "properly investigated without audit logs."
                    ),
                    metric_value=0.0,
                    expected_range="logging enabled",
                    confidence=0.85,
                    recommendation=(
                        "Enable logging to support incident investigation, "
                        "compliance, and audit requirements."
                    ),
                ))

            # Storage/database without backups
            if (
                comp.type in (ComponentType.DATABASE, ComponentType.STORAGE)
                and not comp.security.backup_enabled
            ):
                anomalies.append(Anomaly(
                    id=f"{AnomalyType.SECURITY_ANOMALY.value}-backup-{comp.id}",
                    anomaly_type=AnomalyType.SECURITY_ANOMALY,
                    severity=AnomalySeverity.HIGH,
                    component_id=comp.id,
                    component_name=comp.name,
                    description=(
                        f"{comp.type.value} component has no backups configured. "
                        "Data loss risk is high."
                    ),
                    metric_value=0.0,
                    expected_range="backup enabled",
                    confidence=0.9,
                    recommendation=(
                        "Enable automated backups with appropriate retention "
                        "policy to protect against data loss."
                    ),
                ))

        return anomalies

    # ------------------------------------------------------------------
    # Dependency anomalies
    # ------------------------------------------------------------------

    def detect_dependency_anomalies(self, graph: InfraGraph) -> list[Anomaly]:
        """Detect dependency relationship anomalies.

        Checks for:
        - Dependencies on external APIs without circuit breakers
        - Single dependency (all eggs in one basket)
        """
        anomalies: list[Anomaly] = []

        for comp in graph.components.values():
            deps = graph.get_dependencies(comp.id)
            if not deps:
                continue

            # Check dependencies on external APIs without circuit breakers
            for dep_comp in deps:
                if dep_comp.type == ComponentType.EXTERNAL_API:
                    edge = graph.get_dependency_edge(comp.id, dep_comp.id)
                    if edge and not edge.circuit_breaker.enabled:
                        anomalies.append(Anomaly(
                            id=f"{AnomalyType.DEPENDENCY_ANOMALY.value}-cb-{comp.id}-{dep_comp.id}",
                            anomaly_type=AnomalyType.DEPENDENCY_ANOMALY,
                            severity=AnomalySeverity.HIGH,
                            component_id=comp.id,
                            component_name=comp.name,
                            description=(
                                f"Depends on external API '{dep_comp.name}' without "
                                "a circuit breaker. External failures will cascade."
                            ),
                            metric_value=0.0,
                            expected_range="circuit breaker enabled",
                            confidence=0.9,
                            recommendation=(
                                f"Enable circuit breaker on the dependency to "
                                f"'{dep_comp.name}' to prevent cascade failures "
                                f"from external service outages."
                            ),
                        ))

            # Single dependency -- all eggs in one basket
            required_deps = []
            for dep_comp in deps:
                edge = graph.get_dependency_edge(comp.id, dep_comp.id)
                if edge and edge.dependency_type == "requires":
                    required_deps.append(dep_comp)

            if len(required_deps) == 1:
                single_dep = required_deps[0]
                if single_dep.replicas < self._min_replicas and not single_dep.failover.enabled:
                    anomalies.append(Anomaly(
                        id=f"{AnomalyType.DEPENDENCY_ANOMALY.value}-single-{comp.id}",
                        anomaly_type=AnomalyType.DEPENDENCY_ANOMALY,
                        severity=AnomalySeverity.MEDIUM,
                        component_id=comp.id,
                        component_name=comp.name,
                        description=(
                            f"Has a single required dependency on '{single_dep.name}' "
                            f"which has only {single_dep.replicas} replica(s) and "
                            "no failover. Single point of failure risk."
                        ),
                        metric_value=float(single_dep.replicas),
                        expected_range=f">={self._min_replicas} replicas or failover",
                        confidence=0.8,
                        recommendation=(
                            f"Add redundancy to '{single_dep.name}' (more replicas "
                            "or failover) or add alternative dependencies."
                        ),
                    ))

        return anomalies
