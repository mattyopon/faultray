"""Statistical Anomaly Detection for Infrastructure.

Detects unusual patterns in infrastructure configurations that deviate
from expected norms. Uses statistical methods (z-score, IQR) to identify
outliers without ML dependencies.

Anomaly types:
- Unusually low replica count compared to peer components
- Extreme utilization outliers
- Inconsistent configuration patterns
- Dependency graph anomalies
- Configuration anti-patterns
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from infrasim.model.components import ComponentType
from infrasim.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AnomalyType(str, Enum):
    REPLICA_OUTLIER = "replica_outlier"
    UTILIZATION_OUTLIER = "utilization_outlier"
    CONFIG_INCONSISTENCY = "config_inconsistency"
    DEPENDENCY_ANOMALY = "dependency_anomaly"
    CAPACITY_MISMATCH = "capacity_mismatch"
    SECURITY_INCONSISTENCY = "security_inconsistency"
    OVER_PROVISIONED = "over_provisioned"
    UNDER_PROVISIONED = "under_provisioned"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Anomaly:
    """A single detected anomaly."""

    anomaly_type: AnomalyType
    component_id: str
    component_name: str
    severity: str  # "critical", "warning", "info"
    description: str
    expected_value: str
    actual_value: str
    z_score: float | None = None
    recommendation: str = ""
    confidence: float = 0.0  # 0-1


@dataclass
class AnomalyReport:
    """Complete anomaly detection report."""

    anomalies: list[Anomaly] = field(default_factory=list)
    total_components_analyzed: int = 0
    anomaly_rate: float = 0.0
    critical_count: int = 0
    warning_count: int = 0
    healthiest_components: list[str] = field(default_factory=list)
    most_anomalous_components: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Statistics helpers (no numpy/scipy required)
# ---------------------------------------------------------------------------


def _mean(values: list[float]) -> float:
    """Calculate arithmetic mean."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def _std_dev(values: list[float]) -> float:
    """Calculate population standard deviation."""
    if len(values) < 2:
        return 0.0
    avg = _mean(values)
    variance = sum((x - avg) ** 2 for x in values) / len(values)
    return math.sqrt(variance)


def _z_score(value: float, mean: float, std: float) -> float:
    """Calculate z-score for a value given mean and standard deviation."""
    if std == 0.0:
        return 0.0
    return (value - mean) / std


def _quartiles(values: list[float]) -> tuple[float, float, float]:
    """Calculate Q1, median (Q2), Q3 for a list of values."""
    if not values:
        return 0.0, 0.0, 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)

    def _percentile(data: list[float], p: float) -> float:
        k = (len(data) - 1) * p / 100.0
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return data[int(k)]
        return data[f] * (c - k) + data[c] * (k - f)

    q1 = _percentile(sorted_vals, 25)
    q2 = _percentile(sorted_vals, 50)
    q3 = _percentile(sorted_vals, 75)
    return q1, q2, q3


def _iqr_bounds(values: list[float], factor: float = 1.5) -> tuple[float, float]:
    """Calculate IQR-based outlier bounds."""
    q1, _, q3 = _quartiles(values)
    iqr = q3 - q1
    lower = q1 - factor * iqr
    upper = q3 + factor * iqr
    return lower, upper


# ---------------------------------------------------------------------------
# AnomalyDetector
# ---------------------------------------------------------------------------


class AnomalyDetector:
    """Detects statistical anomalies in infrastructure configurations."""

    def __init__(self) -> None:
        pass

    def detect(self, graph: InfraGraph) -> AnomalyReport:
        """Run all anomaly detection checks and compile a report."""
        if not graph.components:
            return AnomalyReport()

        all_anomalies: list[Anomaly] = []
        all_anomalies.extend(self.detect_replica_anomalies(graph))
        all_anomalies.extend(self.detect_utilization_anomalies(graph))
        all_anomalies.extend(self.detect_config_inconsistencies(graph))
        all_anomalies.extend(self.detect_dependency_anomalies(graph))
        all_anomalies.extend(self.detect_capacity_mismatches(graph))

        # Count severities
        critical_count = sum(1 for a in all_anomalies if a.severity == "critical")
        warning_count = sum(1 for a in all_anomalies if a.severity == "warning")

        # Components with anomalies
        anomaly_counts: dict[str, int] = {}
        for a in all_anomalies:
            anomaly_counts[a.component_id] = anomaly_counts.get(a.component_id, 0) + 1

        # Most anomalous components (sorted by anomaly count desc)
        most_anomalous = sorted(
            anomaly_counts.keys(),
            key=lambda cid: anomaly_counts[cid],
            reverse=True,
        )[:5]

        # Healthiest components (no anomalies)
        all_ids = set(graph.components.keys())
        anomalous_ids = set(anomaly_counts.keys())
        healthy_ids = all_ids - anomalous_ids
        healthiest = sorted(healthy_ids)[:5]

        total = len(graph.components)
        anomaly_rate = len(anomalous_ids) / total * 100.0 if total > 0 else 0.0

        return AnomalyReport(
            anomalies=all_anomalies,
            total_components_analyzed=total,
            anomaly_rate=round(anomaly_rate, 1),
            critical_count=critical_count,
            warning_count=warning_count,
            healthiest_components=healthiest,
            most_anomalous_components=most_anomalous,
        )

    def detect_replica_anomalies(self, graph: InfraGraph) -> list[Anomaly]:
        """Detect components with unusually low replica counts (z-score method)."""
        anomalies: list[Anomaly] = []
        components = list(graph.components.values())

        if len(components) < 2:
            return anomalies

        replica_counts = [float(c.replicas) for c in components]
        avg = _mean(replica_counts)
        std = _std_dev(replica_counts)

        for comp in components:
            z = _z_score(float(comp.replicas), avg, std)
            dependents = graph.get_dependents(comp.id)
            num_dependents = len(dependents)

            # Flag components with z-score < -1.5 (significantly fewer replicas)
            if z < -1.5 and comp.replicas <= 1:
                severity = "critical" if num_dependents >= 2 else "warning"
                confidence = min(1.0, abs(z) / 3.0)

                anomalies.append(Anomaly(
                    anomaly_type=AnomalyType.REPLICA_OUTLIER,
                    component_id=comp.id,
                    component_name=comp.name,
                    severity=severity,
                    description=(
                        f"Component has {comp.replicas} replica(s), significantly below "
                        f"the average of {avg:.1f} across {len(components)} components."
                    ),
                    expected_value=f">= {max(2, int(avg))} replicas",
                    actual_value=f"{comp.replicas} replica(s)",
                    z_score=round(z, 2),
                    recommendation=(
                        f"Add at least {max(2, int(avg)) - comp.replicas} more replica(s) "
                        f"to match peer components. This component has {num_dependents} dependent(s)."
                    ),
                    confidence=round(confidence, 2),
                ))
            # Also flag components with replicas=1 that have many dependents
            elif comp.replicas == 1 and num_dependents >= 2 and not comp.failover.enabled:
                anomalies.append(Anomaly(
                    anomaly_type=AnomalyType.UNDER_PROVISIONED,
                    component_id=comp.id,
                    component_name=comp.name,
                    severity="warning",
                    description=(
                        f"Single-instance component with {num_dependents} dependents "
                        f"and no failover enabled."
                    ),
                    expected_value=">= 2 replicas or failover enabled",
                    actual_value=f"1 replica, no failover",
                    z_score=round(z, 2) if std > 0 else None,
                    recommendation=(
                        f"Enable failover or add replicas. This is a single point of failure "
                        f"affecting {num_dependents} dependent component(s)."
                    ),
                    confidence=0.85,
                ))

        return anomalies

    def detect_utilization_anomalies(self, graph: InfraGraph) -> list[Anomaly]:
        """Detect components with outlier utilization values (IQR method)."""
        anomalies: list[Anomaly] = []
        components = list(graph.components.values())

        utilizations = [c.utilization() for c in components]
        non_zero = [u for u in utilizations if u > 0.0]

        if len(non_zero) < 3:
            # Need at least 3 values for meaningful IQR
            return anomalies

        lower, upper = _iqr_bounds(non_zero)
        avg = _mean(non_zero)
        std = _std_dev(non_zero)

        for comp in components:
            util = comp.utilization()
            if util <= 0.0:
                continue

            if util > upper:
                z = _z_score(util, avg, std) if std > 0 else None
                severity = "critical" if util > 90.0 else "warning"

                anomalies.append(Anomaly(
                    anomaly_type=AnomalyType.UTILIZATION_OUTLIER,
                    component_id=comp.id,
                    component_name=comp.name,
                    severity=severity,
                    description=(
                        f"Utilization ({util:.1f}%) is significantly above the normal "
                        f"range (upper bound: {upper:.1f}%)."
                    ),
                    expected_value=f"<= {upper:.1f}%",
                    actual_value=f"{util:.1f}%",
                    z_score=round(z, 2) if z is not None else None,
                    recommendation=(
                        "Scale up capacity, enable autoscaling, or redistribute load."
                    ),
                    confidence=min(1.0, (util - upper) / max(upper, 1.0)),
                ))
            elif util < lower and lower > 0:
                z = _z_score(util, avg, std) if std > 0 else None
                anomalies.append(Anomaly(
                    anomaly_type=AnomalyType.OVER_PROVISIONED,
                    component_id=comp.id,
                    component_name=comp.name,
                    severity="info",
                    description=(
                        f"Utilization ({util:.1f}%) is significantly below the normal "
                        f"range (lower bound: {lower:.1f}%). Component may be over-provisioned."
                    ),
                    expected_value=f">= {lower:.1f}%",
                    actual_value=f"{util:.1f}%",
                    z_score=round(z, 2) if z is not None else None,
                    recommendation=(
                        "Consider reducing capacity to save costs, or verify that "
                        "the low utilization is expected (e.g., disaster recovery standby)."
                    ),
                    confidence=0.6,
                ))

        return anomalies

    def detect_config_inconsistencies(self, graph: InfraGraph) -> list[Anomaly]:
        """Detect inconsistent configuration patterns across similar components."""
        anomalies: list[Anomaly] = []
        components = list(graph.components.values())

        if len(components) < 2:
            return anomalies

        # Group components by type
        by_type: dict[ComponentType, list] = {}
        for comp in components:
            by_type.setdefault(comp.type, []).append(comp)

        # Check feature adoption within each type group
        for comp_type, group in by_type.items():
            if len(group) < 2:
                continue

            # Check failover adoption
            failover_count = sum(1 for c in group if c.failover.enabled)
            failover_ratio = failover_count / len(group)

            if failover_ratio >= 0.5:
                # Most have failover - flag those that don't
                for comp in group:
                    if not comp.failover.enabled:
                        anomalies.append(Anomaly(
                            anomaly_type=AnomalyType.CONFIG_INCONSISTENCY,
                            component_id=comp.id,
                            component_name=comp.name,
                            severity="warning",
                            description=(
                                f"{failover_count}/{len(group)} {comp_type.value} components "
                                f"have failover enabled, but '{comp.name}' does not."
                            ),
                            expected_value="failover enabled",
                            actual_value="failover disabled",
                            z_score=None,
                            recommendation=(
                                f"Enable failover to match {failover_count} peer component(s) "
                                f"of type {comp_type.value}."
                            ),
                            confidence=round(failover_ratio, 2),
                        ))

            # Check autoscaling adoption
            as_count = sum(1 for c in group if c.autoscaling.enabled)
            as_ratio = as_count / len(group)

            if as_ratio >= 0.5:
                for comp in group:
                    if not comp.autoscaling.enabled:
                        anomalies.append(Anomaly(
                            anomaly_type=AnomalyType.CONFIG_INCONSISTENCY,
                            component_id=comp.id,
                            component_name=comp.name,
                            severity="info",
                            description=(
                                f"{as_count}/{len(group)} {comp_type.value} components "
                                f"have autoscaling enabled, but '{comp.name}' does not."
                            ),
                            expected_value="autoscaling enabled",
                            actual_value="autoscaling disabled",
                            z_score=None,
                            recommendation=(
                                f"Enable autoscaling to match {as_count} peer component(s)."
                            ),
                            confidence=round(as_ratio, 2),
                        ))

        # Check circuit breaker adoption across all edges
        all_edges = graph.all_dependency_edges()
        if len(all_edges) >= 2:
            cb_count = sum(1 for e in all_edges if e.circuit_breaker.enabled)
            cb_ratio = cb_count / len(all_edges)

            if cb_ratio >= 0.5:
                for edge in all_edges:
                    if not edge.circuit_breaker.enabled:
                        source = graph.get_component(edge.source_id)
                        target = graph.get_component(edge.target_id)
                        source_name = source.name if source else edge.source_id
                        target_name = target.name if target else edge.target_id

                        anomalies.append(Anomaly(
                            anomaly_type=AnomalyType.CONFIG_INCONSISTENCY,
                            component_id=edge.source_id,
                            component_name=source_name,
                            severity="warning",
                            description=(
                                f"{cb_count}/{len(all_edges)} dependency edges have circuit "
                                f"breakers, but the edge {source_name} -> {target_name} does not."
                            ),
                            expected_value="circuit breaker enabled",
                            actual_value="circuit breaker disabled",
                            z_score=None,
                            recommendation=(
                                f"Enable circuit breaker on {source_name} -> {target_name} "
                                f"to prevent cascade failures."
                            ),
                            confidence=round(cb_ratio, 2),
                        ))

        # Check security consistency
        security_features = {
            "encryption_at_rest": lambda c: c.security.encryption_at_rest,
            "encryption_in_transit": lambda c: c.security.encryption_in_transit,
            "backup_enabled": lambda c: c.security.backup_enabled,
        }

        for feature_name, check_fn in security_features.items():
            enabled_count = sum(1 for c in components if check_fn(c))
            ratio = enabled_count / len(components)

            if 0.5 <= ratio < 1.0:
                for comp in components:
                    if not check_fn(comp):
                        display_name = feature_name.replace("_", " ")
                        anomalies.append(Anomaly(
                            anomaly_type=AnomalyType.SECURITY_INCONSISTENCY,
                            component_id=comp.id,
                            component_name=comp.name,
                            severity="warning",
                            description=(
                                f"{enabled_count}/{len(components)} components have "
                                f"{display_name}, but '{comp.name}' does not."
                            ),
                            expected_value=f"{display_name} enabled",
                            actual_value=f"{display_name} disabled",
                            z_score=None,
                            recommendation=(
                                f"Enable {display_name} for consistent security posture."
                            ),
                            confidence=round(ratio, 2),
                        ))

        return anomalies

    def detect_dependency_anomalies(self, graph: InfraGraph) -> list[Anomaly]:
        """Detect anomalous dependency graph patterns."""
        anomalies: list[Anomaly] = []
        components = list(graph.components.values())

        if not components:
            return anomalies

        # Count dependents for each component
        dependent_counts = {
            comp.id: len(graph.get_dependents(comp.id))
            for comp in components
        }
        dep_values = list(dependent_counts.values())

        if len(dep_values) >= 3:
            avg = _mean([float(v) for v in dep_values])
            std = _std_dev([float(v) for v in dep_values])

            for comp in components:
                count = dependent_counts[comp.id]
                if std > 0:
                    z = _z_score(float(count), avg, std)
                else:
                    z = 0.0

                # Hub detection: component with significantly more dependents
                if z > 2.0 and count >= 3:
                    anomalies.append(Anomaly(
                        anomaly_type=AnomalyType.DEPENDENCY_ANOMALY,
                        component_id=comp.id,
                        component_name=comp.name,
                        severity="critical" if count >= 5 else "warning",
                        description=(
                            f"Component is a critical hub with {count} dependents "
                            f"(average: {avg:.1f}). Failure would cascade widely."
                        ),
                        expected_value=f"<= {int(avg + std)} dependents",
                        actual_value=f"{count} dependents",
                        z_score=round(z, 2),
                        recommendation=(
                            "Consider adding redundancy (replicas, failover) or "
                            "introducing a load balancer/proxy to reduce direct dependencies."
                        ),
                        confidence=min(1.0, z / 3.0),
                    ))

        # Orphan detection: components with no connections
        for comp in components:
            dependents = graph.get_dependents(comp.id)
            dependencies = graph.get_dependencies(comp.id)
            if not dependents and not dependencies and len(components) > 1:
                anomalies.append(Anomaly(
                    anomaly_type=AnomalyType.DEPENDENCY_ANOMALY,
                    component_id=comp.id,
                    component_name=comp.name,
                    severity="info",
                    description=(
                        "Component has no dependencies and no dependents (orphan node). "
                        "It may be unused or incorrectly configured."
                    ),
                    expected_value="at least 1 connection",
                    actual_value="0 connections",
                    z_score=None,
                    recommendation=(
                        "Verify that this component is needed and properly connected "
                        "in the dependency graph."
                    ),
                    confidence=0.7,
                ))

        # Circular dependency chains (via networkx)
        import networkx as nx
        try:
            cycles = list(nx.simple_cycles(graph._graph))
            for cycle in cycles[:5]:  # Limit to first 5 cycles
                cycle_str = " -> ".join(cycle + [cycle[0]])
                # Report on the first component in the cycle
                comp = graph.get_component(cycle[0])
                if comp:
                    anomalies.append(Anomaly(
                        anomaly_type=AnomalyType.DEPENDENCY_ANOMALY,
                        component_id=comp.id,
                        component_name=comp.name,
                        severity="critical",
                        description=(
                            f"Circular dependency detected: {cycle_str}. "
                            f"This can cause deadlocks and cascade failures."
                        ),
                        expected_value="no circular dependencies",
                        actual_value=cycle_str,
                        z_score=None,
                        recommendation=(
                            "Break the circular dependency by introducing async "
                            "communication or restructuring the dependency graph."
                        ),
                        confidence=1.0,
                    ))
        except Exception:
            pass  # Skip if graph analysis fails

        return anomalies

    def detect_capacity_mismatches(self, graph: InfraGraph) -> list[Anomaly]:
        """Detect capacity mismatches between related components."""
        anomalies: list[Anomaly] = []
        components = list(graph.components.values())

        if len(components) < 2:
            return anomalies

        for comp in components:
            dependents = graph.get_dependents(comp.id)
            if not dependents:
                continue

            # Check if a component with many dependents has low replicas
            if len(dependents) >= 3 and comp.replicas <= 1:
                anomalies.append(Anomaly(
                    anomaly_type=AnomalyType.CAPACITY_MISMATCH,
                    component_id=comp.id,
                    component_name=comp.name,
                    severity="critical",
                    description=(
                        f"Component has {len(dependents)} dependents but only "
                        f"{comp.replicas} replica(s). High fan-in with low capacity."
                    ),
                    expected_value=f">= {min(len(dependents), 3)} replicas for {len(dependents)} dependents",
                    actual_value=f"{comp.replicas} replica(s)",
                    z_score=None,
                    recommendation=(
                        f"Increase replicas to at least {min(len(dependents), 3)} to handle "
                        f"the load from {len(dependents)} dependent components."
                    ),
                    confidence=0.9,
                ))

            # Check if upstream components have more capacity than downstream
            for dep_comp in dependents:
                edge = graph.get_dependency_edge(dep_comp.id, comp.id)
                if edge and edge.dependency_type == "requires":
                    if dep_comp.replicas > comp.replicas * 2 and comp.replicas <= 1:
                        anomalies.append(Anomaly(
                            anomaly_type=AnomalyType.CAPACITY_MISMATCH,
                            component_id=comp.id,
                            component_name=comp.name,
                            severity="warning",
                            description=(
                                f"Upstream component '{dep_comp.name}' has {dep_comp.replicas} "
                                f"replicas but depends on '{comp.name}' with only {comp.replicas}. "
                                f"Bottleneck risk."
                            ),
                            expected_value=f">= {max(2, dep_comp.replicas // 2)} replicas",
                            actual_value=f"{comp.replicas} replica(s)",
                            z_score=None,
                            recommendation=(
                                f"Scale '{comp.name}' to at least {max(2, dep_comp.replicas // 2)} "
                                f"replicas to avoid becoming a bottleneck."
                            ),
                            confidence=0.75,
                        ))

        return anomalies
