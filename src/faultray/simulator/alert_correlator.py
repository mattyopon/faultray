# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Alert correlator — correlate infrastructure alerts to root causes.

Groups related alerts by analyzing the infrastructure dependency graph,
identifies probable root causes, and reduces alert noise by clustering
correlated events.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from faultray.model.components import HealthStatus
from faultray.model.graph import InfraGraph


class AlertSeverity(str, Enum):
    """Alert severity level."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AlertStatus(str, Enum):
    """Alert status."""

    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


@dataclass
class Alert:
    """A single infrastructure alert."""

    id: str
    component_id: str
    severity: AlertSeverity
    title: str
    description: str
    timestamp: datetime
    status: AlertStatus = AlertStatus.ACTIVE
    metric_value: float = 0.0


@dataclass
class AlertCluster:
    """A group of correlated alerts."""

    cluster_id: str
    root_cause_component: str
    root_cause_name: str
    alerts: list[Alert]
    probable_cause: str
    confidence: float  # 0-1
    affected_components: list[str]
    severity: AlertSeverity
    recommended_action: str


@dataclass
class CorrelationReport:
    """Full alert correlation analysis."""

    total_alerts: int
    clusters: list[AlertCluster]
    suppressed_count: int
    noise_reduction_percent: float
    root_causes: list[str]
    top_recommendations: list[str]


class AlertCorrelator:
    """Correlate alerts using infrastructure topology."""

    def __init__(
        self,
        graph: InfraGraph,
        time_window_minutes: int = 15,
    ) -> None:
        self._graph = graph
        self._time_window = time_window_minutes
        self._alerts: list[Alert] = []

    def add_alert(self, alert: Alert) -> None:
        """Add an alert to correlate."""
        self._alerts.append(alert)

    def add_alerts(self, alerts: list[Alert]) -> None:
        """Add multiple alerts."""
        self._alerts.extend(alerts)

    def get_alerts(self) -> list[Alert]:
        """Get all alerts."""
        return list(self._alerts)

    def correlate(self) -> CorrelationReport:
        """Analyze all alerts and produce correlation report."""
        if not self._alerts:
            return CorrelationReport(
                total_alerts=0,
                clusters=[],
                suppressed_count=0,
                noise_reduction_percent=0,
                root_causes=[],
                top_recommendations=[],
            )

        clusters = self._build_clusters()
        suppressed = sum(
            len(c.alerts) - 1 for c in clusters if len(c.alerts) > 1
        )
        total = len(self._alerts)
        noise_pct = (suppressed / total * 100) if total > 0 else 0

        root_causes = [c.root_cause_name for c in clusters]
        recommendations = []
        for cluster in clusters:
            if cluster.recommended_action and cluster.recommended_action not in recommendations:
                recommendations.append(cluster.recommended_action)

        return CorrelationReport(
            total_alerts=total,
            clusters=clusters,
            suppressed_count=suppressed,
            noise_reduction_percent=round(noise_pct, 1),
            root_causes=root_causes,
            top_recommendations=recommendations[:5],
        )

    def find_root_cause(self, component_id: str) -> str | None:
        """Find probable root cause for an alerting component."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return None

        # Check if any dependency is also alerting
        deps = self._graph.get_dependencies(component_id)
        alerting_deps = [
            d.id for d in deps
            if any(a.component_id == d.id for a in self._alerts)
        ]

        if alerting_deps:
            # Root cause is likely an alerting dependency
            return alerting_deps[0]

        # If the component itself is alerting and no deps are, it's the root
        return component_id

    def _build_clusters(self) -> list[AlertCluster]:
        """Build clusters of correlated alerts."""
        # Group alerts by time proximity and topology
        used: set[str] = set()
        clusters: list[AlertCluster] = []
        cluster_idx = 0

        # Sort alerts by severity (critical first) then timestamp
        sorted_alerts = sorted(
            self._alerts,
            key=lambda a: (
                {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}[a.severity.value],
                a.timestamp,
            ),
        )

        for alert in sorted_alerts:
            if alert.id in used:
                continue

            # Find correlated alerts
            correlated = [alert]
            used.add(alert.id)

            for other in sorted_alerts:
                if other.id in used:
                    continue
                if self._are_correlated(alert, other):
                    correlated.append(other)
                    used.add(other.id)

            # Determine root cause
            root_id = self._find_cluster_root(correlated)
            root_comp = self._graph.get_component(root_id)
            root_name = root_comp.name if root_comp else root_id

            # Build cluster
            affected = list({a.component_id for a in correlated})
            max_severity = min(
                correlated,
                key=lambda a: {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}[a.severity.value],
            ).severity

            cause = self._infer_cause(root_id, correlated)
            action = self._recommend_action(root_id, correlated)

            confidence = min(1.0, len(correlated) * 0.3) if len(correlated) > 1 else 0.5

            clusters.append(AlertCluster(
                cluster_id=f"cluster-{cluster_idx}",
                root_cause_component=root_id,
                root_cause_name=root_name,
                alerts=correlated,
                probable_cause=cause,
                confidence=round(confidence, 2),
                affected_components=affected,
                severity=max_severity,
                recommended_action=action,
            ))
            cluster_idx += 1

        return clusters

    def _are_correlated(self, a: Alert, b: Alert) -> bool:
        """Check if two alerts are correlated (topology + time proximity)."""
        # Time proximity
        time_diff = abs((a.timestamp - b.timestamp).total_seconds())
        if time_diff > self._time_window * 60:
            return False

        # Topology proximity: same component, direct dependency, or shared dependency
        if a.component_id == b.component_id:
            return True

        # Check if one depends on the other
        a_deps = {d.id for d in self._graph.get_dependencies(a.component_id)}
        if b.component_id in a_deps:
            return True

        b_deps = {d.id for d in self._graph.get_dependencies(b.component_id)}
        if a.component_id in b_deps:
            return True

        # Check shared dependency
        if a_deps & b_deps:
            return True

        return False

    def _find_cluster_root(self, alerts: list[Alert]) -> str:
        """Find the root cause component in a cluster of alerts."""
        component_ids = {a.component_id for a in alerts}

        # The root cause is the component that others depend on
        for cid in component_ids:
            deps_of_others = set()
            for other_id in component_ids:
                if other_id != cid:
                    deps = {d.id for d in self._graph.get_dependencies(other_id)}
                    deps_of_others.update(deps)
            if cid in deps_of_others:
                return cid

        # If no clear dependency, pick the one with highest severity
        highest = min(
            alerts,
            key=lambda a: {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}[a.severity.value],
        )
        return highest.component_id

    def _infer_cause(self, root_id: str, alerts: list[Alert]) -> str:
        """Infer probable cause from alert patterns."""
        comp = self._graph.get_component(root_id)
        if comp is None:
            return "Unknown root cause"

        if comp.health == HealthStatus.DOWN:
            return f"{comp.name} is down, causing cascading alerts"
        if comp.health == HealthStatus.DEGRADED:
            return f"{comp.name} is degraded, impacting dependent services"
        if comp.health == HealthStatus.OVERLOADED:
            return f"{comp.name} is overloaded, causing timeouts in dependents"

        if len(alerts) > 3:
            return f"Multiple alerts from {comp.name} and dependents suggest infrastructure issue"

        return f"Alert on {comp.name} — investigate component health"

    def _recommend_action(self, root_id: str, alerts: list[Alert]) -> str:
        """Generate recommended action for a cluster."""
        comp = self._graph.get_component(root_id)
        if comp is None:
            return "Investigate alerting components"

        if comp.health == HealthStatus.DOWN:
            if comp.failover.enabled:
                return f"Verify failover for {comp.name} has activated; check health endpoint"
            return f"Restart {comp.name} or trigger manual failover"

        if comp.health == HealthStatus.OVERLOADED:
            if comp.autoscaling.enabled:
                return f"Check autoscaling for {comp.name}; may need to increase max instances"
            return f"Scale up {comp.name} replicas to handle load"

        if comp.replicas <= 1:
            return f"Add replicas to {comp.name} to improve resilience"

        return f"Investigate {comp.name} — check logs and metrics"
