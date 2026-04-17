# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Infrastructure Evolution Tracker — tracks how infrastructure resilience
changes over time with each modification.

Captures infrastructure state snapshots and tracks how resilience metrics
evolve over time.  Identifies trends, regressions, and improvements, enabling
teams to see if their infrastructure is getting more or less resilient.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List

from faultray.model.components import Component, HealthStatus
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TrendDirection(str, Enum):
    IMPROVING = "improving"
    STABLE = "stable"
    DEGRADING = "degrading"


class ChangeType(str, Enum):
    COMPONENT_ADDED = "component_added"
    COMPONENT_REMOVED = "component_removed"
    REPLICA_CHANGED = "replica_changed"
    FAILOVER_CHANGED = "failover_changed"
    HEALTH_CHANGED = "health_changed"
    DEPENDENCY_ADDED = "dependency_added"
    DEPENDENCY_REMOVED = "dependency_removed"
    SECURITY_CHANGED = "security_changed"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class InfraSnapshot:
    """A point-in-time snapshot of infrastructure state."""

    snapshot_id: str
    timestamp: str
    total_components: int
    healthy_count: int
    degraded_count: int
    down_count: int
    total_replicas: int
    failover_enabled_count: int
    avg_cpu: float
    avg_memory: float
    resilience_score: float  # 0-100
    component_ids: List[str] = field(default_factory=list)


@dataclass
class InfraChange:
    """A detected change between two infrastructure states."""

    change_type: ChangeType
    component_id: str
    component_name: str
    old_value: str
    new_value: str
    impact_description: str


@dataclass
class TrendAnalysis:
    """Analysis of a single metric's trend direction."""

    metric_name: str
    direction: TrendDirection
    current_value: float
    previous_value: float
    change_percent: float
    assessment: str


@dataclass
class EvolutionReport:
    """Full evolution report across snapshots."""

    snapshots: List[InfraSnapshot] = field(default_factory=list)
    changes: List[InfraChange] = field(default_factory=list)
    trends: List[TrendAnalysis] = field(default_factory=list)
    overall_trend: TrendDirection = TrendDirection.STABLE
    improvement_count: int = 0
    regression_count: int = 0
    recommendations: List[str] = field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------

class EvolutionTracker:
    """Tracks infrastructure state evolution over time."""

    def __init__(self) -> None:
        self._snapshots: List[InfraSnapshot] = []

    # -- public helpers -----------------------------------------------------

    def get_snapshot_count(self) -> int:
        """Return the number of captured snapshots."""
        return len(self._snapshots)

    def clear_history(self) -> None:
        """Reset all captured snapshots."""
        self._snapshots.clear()

    # -- capture ------------------------------------------------------------

    def capture(self, graph: InfraGraph) -> InfraSnapshot:
        """Capture the current state of *graph* and store a snapshot."""

        components: dict[str, Component] = graph.components
        total = len(components)

        healthy = 0
        degraded = 0
        down = 0
        total_replicas = 0
        failover_count = 0
        cpu_sum = 0.0
        memory_sum = 0.0
        component_ids: list[str] = []

        for comp in components.values():
            component_ids.append(comp.id)
            if comp.health == HealthStatus.HEALTHY:
                healthy += 1
            elif comp.health in (HealthStatus.DEGRADED, HealthStatus.OVERLOADED):
                degraded += 1
            elif comp.health == HealthStatus.DOWN:
                down += 1
            total_replicas += comp.replicas
            if comp.failover.enabled:
                failover_count += 1
            cpu_sum += comp.metrics.cpu_percent
            memory_sum += comp.metrics.memory_percent

        avg_cpu = cpu_sum / total if total > 0 else 0.0
        avg_memory = memory_sum / total if total > 0 else 0.0

        resilience_score = self._compute_resilience_score(
            total=total,
            healthy=healthy,
            total_replicas=total_replicas,
            failover_count=failover_count,
            avg_cpu=avg_cpu,
            avg_memory=avg_memory,
        )

        snapshot = InfraSnapshot(
            snapshot_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_components=total,
            healthy_count=healthy,
            degraded_count=degraded,
            down_count=down,
            total_replicas=total_replicas,
            failover_enabled_count=failover_count,
            avg_cpu=round(avg_cpu, 2),
            avg_memory=round(avg_memory, 2),
            resilience_score=round(resilience_score, 2),
            component_ids=sorted(component_ids),
        )

        self._snapshots.append(snapshot)
        return snapshot

    # -- compare ------------------------------------------------------------

    def compare(self, graph_a: InfraGraph, graph_b: InfraGraph) -> List[InfraChange]:
        """Compare two infrastructure graphs and return detected changes."""

        changes: list[InfraChange] = []
        a_comps = graph_a.components
        b_comps = graph_b.components

        a_ids = set(a_comps.keys())
        b_ids = set(b_comps.keys())

        # Added components
        for cid in sorted(b_ids - a_ids):
            comp = b_comps[cid]
            changes.append(InfraChange(
                change_type=ChangeType.COMPONENT_ADDED,
                component_id=cid,
                component_name=comp.name,
                old_value="",
                new_value=comp.type.value,
                impact_description=f"Component '{comp.name}' added ({comp.type.value}).",
            ))

        # Removed components
        for cid in sorted(a_ids - b_ids):
            comp = a_comps[cid]
            changes.append(InfraChange(
                change_type=ChangeType.COMPONENT_REMOVED,
                component_id=cid,
                component_name=comp.name,
                old_value=comp.type.value,
                new_value="",
                impact_description=f"Component '{comp.name}' removed ({comp.type.value}).",
            ))

        # Changes within common components
        for cid in sorted(a_ids & b_ids):
            ca = a_comps[cid]
            cb = b_comps[cid]

            if ca.replicas != cb.replicas:
                changes.append(InfraChange(
                    change_type=ChangeType.REPLICA_CHANGED,
                    component_id=cid,
                    component_name=cb.name,
                    old_value=str(ca.replicas),
                    new_value=str(cb.replicas),
                    impact_description=(
                        f"Replicas for '{cb.name}' changed from "
                        f"{ca.replicas} to {cb.replicas}."
                    ),
                ))

            if ca.failover.enabled != cb.failover.enabled:
                changes.append(InfraChange(
                    change_type=ChangeType.FAILOVER_CHANGED,
                    component_id=cid,
                    component_name=cb.name,
                    old_value=str(ca.failover.enabled),
                    new_value=str(cb.failover.enabled),
                    impact_description=(
                        f"Failover for '{cb.name}' changed from "
                        f"{ca.failover.enabled} to {cb.failover.enabled}."
                    ),
                ))

            if ca.health != cb.health:
                changes.append(InfraChange(
                    change_type=ChangeType.HEALTH_CHANGED,
                    component_id=cid,
                    component_name=cb.name,
                    old_value=ca.health.value,
                    new_value=cb.health.value,
                    impact_description=(
                        f"Health of '{cb.name}' changed from "
                        f"{ca.health.value} to {cb.health.value}."
                    ),
                ))

            if self._security_differs(ca, cb):
                changes.append(InfraChange(
                    change_type=ChangeType.SECURITY_CHANGED,
                    component_id=cid,
                    component_name=cb.name,
                    old_value=self._security_summary(ca),
                    new_value=self._security_summary(cb),
                    impact_description=(
                        f"Security settings for '{cb.name}' changed."
                    ),
                ))

        return changes

    # -- trend analysis -----------------------------------------------------

    def analyze_trends(self) -> EvolutionReport:
        """Analyze all captured snapshots and produce an evolution report."""

        report = EvolutionReport(snapshots=list(self._snapshots))

        if len(self._snapshots) < 2:
            report.summary = (
                "Not enough snapshots to analyze trends. "
                "Capture at least two snapshots."
            )
            return report

        prev = self._snapshots[-2]
        curr = self._snapshots[-1]

        # Compute trend analyses
        trends: list[TrendAnalysis] = []

        # resilience_score (higher is better)
        trends.append(self._trend(
            "resilience_score",
            curr.resilience_score,
            prev.resilience_score,
            higher_is_better=True,
        ))

        # healthy_ratio (higher is better)
        curr_healthy_ratio = (
            (curr.healthy_count / curr.total_components * 100)
            if curr.total_components > 0 else 0.0
        )
        prev_healthy_ratio = (
            (prev.healthy_count / prev.total_components * 100)
            if prev.total_components > 0 else 0.0
        )
        trends.append(self._trend(
            "healthy_ratio",
            curr_healthy_ratio,
            prev_healthy_ratio,
            higher_is_better=True,
        ))

        # replica_average (higher is better)
        curr_replica_avg = (
            (curr.total_replicas / curr.total_components)
            if curr.total_components > 0 else 0.0
        )
        prev_replica_avg = (
            (prev.total_replicas / prev.total_components)
            if prev.total_components > 0 else 0.0
        )
        trends.append(self._trend(
            "replica_average",
            curr_replica_avg,
            prev_replica_avg,
            higher_is_better=True,
        ))

        # failover_coverage (higher is better)
        curr_failover = (
            (curr.failover_enabled_count / curr.total_components * 100)
            if curr.total_components > 0 else 0.0
        )
        prev_failover = (
            (prev.failover_enabled_count / prev.total_components * 100)
            if prev.total_components > 0 else 0.0
        )
        trends.append(self._trend(
            "failover_coverage",
            curr_failover,
            prev_failover,
            higher_is_better=True,
        ))

        # resource_usage — avg_cpu (lower is better)
        trends.append(self._trend(
            "resource_usage",
            curr.avg_cpu,
            prev.avg_cpu,
            higher_is_better=False,
        ))

        report.trends = trends

        # Overall trend
        improving = sum(1 for t in trends if t.direction == TrendDirection.IMPROVING)
        degrading = sum(1 for t in trends if t.direction == TrendDirection.DEGRADING)

        report.improvement_count = improving
        report.regression_count = degrading

        if improving > degrading:
            report.overall_trend = TrendDirection.IMPROVING
        elif degrading > improving:
            report.overall_trend = TrendDirection.DEGRADING
        else:
            report.overall_trend = TrendDirection.STABLE

        # Recommendations
        recommendations: list[str] = []

        for t in trends:
            if t.metric_name == "resilience_score" and t.direction == TrendDirection.DEGRADING:
                recommendations.append(
                    "Resilience is degrading. Review recent changes."
                )
            if t.metric_name == "healthy_ratio" and t.direction == TrendDirection.DEGRADING:
                recommendations.append(
                    "Component health declining. Investigate root causes."
                )
            if t.metric_name == "replica_average" and t.direction == TrendDirection.DEGRADING:
                recommendations.append(
                    "Redundancy is reducing. Consider adding replicas."
                )
            if t.metric_name == "resource_usage" and t.direction == TrendDirection.DEGRADING:
                recommendations.append(
                    "Resource pressure increasing. Plan capacity expansion."
                )

        report.recommendations = recommendations

        # Summary
        report.summary = (
            f"Overall trend: {report.overall_trend.value}. "
            f"{improving} metric(s) improving, "
            f"{degrading} metric(s) degrading, "
            f"{len(trends) - improving - degrading} metric(s) stable."
        )

        return report

    # -- private helpers ----------------------------------------------------

    @staticmethod
    def _compute_resilience_score(
        *,
        total: int,
        healthy: int,
        total_replicas: int,
        failover_count: int,
        avg_cpu: float,
        avg_memory: float,
    ) -> float:
        """Weighted resilience score (0-100)."""

        if total == 0:
            return 0.0

        # healthy_ratio * 40
        healthy_ratio = healthy / total
        healthy_score = healthy_ratio * 40.0

        # replica_score * 20 (avg_replicas / 3 * 20, capped at 20)
        avg_replicas = total_replicas / total
        replica_score = min(20.0, (avg_replicas / 3.0) * 20.0)

        # failover_score * 20 (failover_ratio * 20)
        failover_ratio = failover_count / total
        failover_score = failover_ratio * 20.0

        # resource_headroom * 20 ((100 - max(avg_cpu, avg_memory)) / 100 * 20)
        headroom = (100.0 - max(avg_cpu, avg_memory)) / 100.0 * 20.0
        headroom = max(0.0, headroom)

        return min(100.0, healthy_score + replica_score + failover_score + headroom)

    @staticmethod
    def _security_differs(a: Component, b: Component) -> bool:
        """Return True if security profiles differ."""
        sa = a.security
        sb = b.security
        return (
            sa.encryption_at_rest != sb.encryption_at_rest
            or sa.encryption_in_transit != sb.encryption_in_transit
            or sa.waf_protected != sb.waf_protected
            or sa.rate_limiting != sb.rate_limiting
            or sa.auth_required != sb.auth_required
            or sa.network_segmented != sb.network_segmented
            or sa.backup_enabled != sb.backup_enabled
            or sa.log_enabled != sb.log_enabled
            or sa.ids_monitored != sb.ids_monitored
        )

    @staticmethod
    def _security_summary(comp: Component) -> str:
        """Return a concise summary of security settings."""
        s = comp.security
        flags: list[str] = []
        if s.encryption_at_rest:
            flags.append("enc-rest")
        if s.encryption_in_transit:
            flags.append("enc-transit")
        if s.waf_protected:
            flags.append("waf")
        if s.rate_limiting:
            flags.append("rate-limit")
        if s.auth_required:
            flags.append("auth")
        if s.network_segmented:
            flags.append("segmented")
        if s.backup_enabled:
            flags.append("backup")
        if s.log_enabled:
            flags.append("log")
        if s.ids_monitored:
            flags.append("ids")
        return ",".join(flags) if flags else "none"

    @staticmethod
    def _trend(
        metric_name: str,
        current: float,
        previous: float,
        *,
        higher_is_better: bool,
    ) -> TrendAnalysis:
        """Determine trend direction for a single metric."""

        if previous != 0:
            change_pct = ((current - previous) / abs(previous)) * 100.0
        else:
            change_pct = 0.0 if current == 0 else 100.0

        diff = current - previous

        # For "higher is better" metrics, positive diff = improving.
        # For "lower is better" metrics, negative diff = improving.
        if higher_is_better:
            if diff > 2:
                direction = TrendDirection.IMPROVING
            elif diff < -2:
                direction = TrendDirection.DEGRADING
            else:
                direction = TrendDirection.STABLE
        else:
            if diff < -2:
                direction = TrendDirection.IMPROVING
            elif diff > 2:
                direction = TrendDirection.DEGRADING
            else:
                direction = TrendDirection.STABLE

        assessments = {
            TrendDirection.IMPROVING: f"{metric_name} is improving.",
            TrendDirection.DEGRADING: f"{metric_name} is degrading.",
            TrendDirection.STABLE: f"{metric_name} is stable.",
        }

        return TrendAnalysis(
            metric_name=metric_name,
            direction=direction,
            current_value=round(current, 4),
            previous_value=round(previous, 4),
            change_percent=round(change_pct, 2),
            assessment=assessments[direction],
        )
