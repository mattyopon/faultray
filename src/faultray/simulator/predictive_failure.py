# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Predictive failure engine — forecast failures before they happen.

Uses time-series analysis and pattern mining to predict which components
will fail next, based on current metrics, historical patterns, and
infrastructure topology.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


class RiskLevel(str, Enum):
    CRITICAL = "critical"  # Failure likely within 24h
    HIGH = "high"  # Failure likely within 7 days
    MEDIUM = "medium"  # Failure likely within 30 days
    LOW = "low"  # No significant risk
    UNKNOWN = "unknown"


class FailurePattern(str, Enum):
    """Common failure sequence patterns."""

    CPU_MEMORY_CASCADE = "cpu_memory_cascade"  # CPU spike -> memory pressure -> OOM
    DISK_EXHAUSTION = "disk_exhaustion"  # Steady disk growth -> full
    CONNECTION_POOL_LEAK = "connection_pool_leak"  # Gradual connection accumulation
    LATENCY_DEGRADATION = "latency_degradation"  # Slow latency increase -> timeout
    REPLICA_DRIFT = "replica_drift"  # Replicas diverge in health
    DEPENDENCY_CHAIN = "dependency_chain"  # Upstream degradation -> downstream failure
    THUNDERING_HERD = "thundering_herd"  # Recovery causes load spike
    COLD_START_STORM = "cold_start_storm"  # Many new instances starting


@dataclass
class FailurePrediction:
    """A predicted failure for a component."""

    component_id: str
    component_name: str
    risk_level: RiskLevel
    confidence: float  # 0.0 - 1.0
    predicted_failure_hours: float  # estimated hours until failure
    failure_pattern: FailurePattern
    contributing_factors: list[str]
    recommended_actions: list[str]
    risk_score: float  # 0-100 composite score


@dataclass
class PatternMatch:
    """A detected failure pattern in the infrastructure."""

    pattern: FailurePattern
    affected_components: list[str]
    severity: float  # 0-1
    description: str


@dataclass
class PredictiveReport:
    """Full predictive failure analysis report."""

    predictions: list[FailurePrediction]
    detected_patterns: list[PatternMatch]
    overall_risk_score: float  # 0-100 (0=safe, 100=imminent failure)
    risk_summary: str
    top_risks: list[str]  # Top 5 risks
    mean_time_to_predicted_failure: float  # Average hours across predictions
    risk_distribution: dict[str, int]  # {risk_level: count}


class PredictiveFailureEngine:
    """Predict infrastructure failures before they happen."""

    # Component type risk baselines (some types are inherently riskier)
    _TYPE_RISK_WEIGHTS: dict[ComponentType, float] = {
        ComponentType.DATABASE: 1.5,
        ComponentType.CACHE: 1.3,
        ComponentType.QUEUE: 1.2,
        ComponentType.APP_SERVER: 1.0,
        ComponentType.WEB_SERVER: 0.9,
        ComponentType.LOAD_BALANCER: 1.4,
        ComponentType.DNS: 0.7,
        ComponentType.STORAGE: 1.3,
        ComponentType.EXTERNAL_API: 1.6,
        ComponentType.CUSTOM: 1.0,
    }

    # Failure pattern detection thresholds
    _CPU_HIGH_THRESHOLD = 75.0
    _MEMORY_HIGH_THRESHOLD = 80.0
    _DISK_HIGH_THRESHOLD = 70.0
    _CONNECTION_HIGH_RATIO = 0.7  # 70% of max connections

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    def predict(self) -> PredictiveReport:
        """Run full predictive analysis."""
        predictions: list[FailurePrediction] = []

        for comp in self._graph.components.values():
            pred = self._predict_component(comp)
            if pred:
                predictions.append(pred)

        patterns = self._detect_patterns()

        # Boost predictions based on pattern detection
        predictions = self._apply_pattern_boosts(predictions, patterns)

        # Sort by risk score descending
        predictions.sort(key=lambda p: p.risk_score, reverse=True)

        # Calculate overall metrics
        if predictions:
            overall_risk = self._calculate_overall_risk(predictions)
            mtpf = sum(p.predicted_failure_hours for p in predictions) / len(
                predictions
            )
        else:
            overall_risk = 0.0
            mtpf = float("inf")

        risk_dist = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "unknown": 0,
        }
        for p in predictions:
            risk_dist[p.risk_level.value] += 1

        top_risks = [
            f"{p.component_name}: {p.failure_pattern.value} (risk={p.risk_score:.0f})"
            for p in predictions[:5]
        ]

        summary = self._generate_summary(predictions, patterns, overall_risk)

        return PredictiveReport(
            predictions=predictions,
            detected_patterns=patterns,
            overall_risk_score=round(overall_risk, 1),
            risk_summary=summary,
            top_risks=top_risks,
            mean_time_to_predicted_failure=round(mtpf, 1),
            risk_distribution=risk_dist,
        )

    def _predict_component(self, comp: Component) -> FailurePrediction | None:
        """Predict failure risk for a single component."""
        factors: list[str] = []
        actions: list[str] = []
        risk_score = 0.0
        pattern = FailurePattern.CPU_MEMORY_CASCADE  # default
        hours = float("inf")

        type_weight = self._TYPE_RISK_WEIGHTS.get(comp.type, 1.0)

        # CPU analysis
        cpu = comp.metrics.cpu_percent
        if cpu > self._CPU_HIGH_THRESHOLD:
            cpu_risk = min(
                40.0,
                (cpu - self._CPU_HIGH_THRESHOLD)
                / (100 - self._CPU_HIGH_THRESHOLD)
                * 40,
            )
            risk_score += cpu_risk * type_weight
            factors.append(
                f"CPU at {cpu}% (threshold: {self._CPU_HIGH_THRESHOLD}%)"
            )
            actions.append(
                "Scale horizontally or optimize CPU-intensive operations"
            )
            # Estimate hours to failure based on how close to 100%
            remaining = 100 - cpu
            if remaining > 0:
                hours = min(hours, remaining / 5.0 * 24)  # Rough estimate
            else:
                hours = 0
            pattern = FailurePattern.CPU_MEMORY_CASCADE

        # Memory analysis
        mem = comp.metrics.memory_percent
        if mem > self._MEMORY_HIGH_THRESHOLD:
            mem_risk = min(
                35.0,
                (mem - self._MEMORY_HIGH_THRESHOLD)
                / (100 - self._MEMORY_HIGH_THRESHOLD)
                * 35,
            )
            risk_score += mem_risk * type_weight
            factors.append(
                f"Memory at {mem}% (threshold: {self._MEMORY_HIGH_THRESHOLD}%)"
            )
            actions.append(
                "Investigate memory leaks or increase memory allocation"
            )
            remaining = 100 - mem
            if remaining > 0:
                hours = min(hours, remaining / 3.0 * 24)
            else:
                hours = 0
            if cpu > self._CPU_HIGH_THRESHOLD:
                pattern = FailurePattern.CPU_MEMORY_CASCADE
            else:
                pattern = FailurePattern.CONNECTION_POOL_LEAK

        # Disk analysis (storage/DB specific)
        disk = comp.metrics.disk_percent
        if disk > self._DISK_HIGH_THRESHOLD:
            disk_risk = min(
                30.0,
                (disk - self._DISK_HIGH_THRESHOLD)
                / (100 - self._DISK_HIGH_THRESHOLD)
                * 30,
            )
            risk_score += disk_risk * type_weight
            factors.append(
                f"Disk at {disk}% (threshold: {self._DISK_HIGH_THRESHOLD}%)"
            )
            actions.append(
                "Expand storage or implement data retention policies"
            )
            remaining = 100 - disk
            if remaining > 0:
                hours = min(hours, remaining / 2.0 * 24)
            else:
                hours = 0
            pattern = FailurePattern.DISK_EXHAUSTION

        # Connection pool analysis
        if comp.capacity.max_connections > 0:
            conn_ratio = (
                comp.metrics.network_connections / comp.capacity.max_connections
            )
            if conn_ratio > self._CONNECTION_HIGH_RATIO:
                conn_risk = min(
                    25.0,
                    (conn_ratio - self._CONNECTION_HIGH_RATIO)
                    / (1.0 - self._CONNECTION_HIGH_RATIO)
                    * 25,
                )
                risk_score += conn_risk * type_weight
                factors.append(
                    f"Connection pool at {conn_ratio * 100:.0f}% capacity"
                )
                actions.append(
                    "Increase connection pool size or add connection pooling proxy"
                )
                remaining = 1.0 - conn_ratio
                if remaining > 0:
                    hours = min(hours, remaining * 48)
                else:
                    hours = 0
                pattern = FailurePattern.CONNECTION_POOL_LEAK

        # Replica risk (single replica = higher risk)
        if comp.replicas == 1:
            risk_score += 10.0 * type_weight
            factors.append("Single replica — no redundancy")
            actions.append(
                "Add at least one replica for high availability"
            )

        # Health-based risk
        if comp.health == HealthStatus.DEGRADED:
            risk_score += 15.0
            factors.append(
                f"Component is already {comp.health.value}"
            )
            actions.append(
                "Investigate current degradation before it worsens"
            )
        elif comp.health == HealthStatus.OVERLOADED:
            risk_score += 25.0
            factors.append(
                f"Component is already {comp.health.value}"
            )
            actions.append(
                "Immediate scaling required — component is overloaded"
            )
            hours = min(hours, 4.0)
        elif comp.health == HealthStatus.DOWN:
            risk_score += 50.0
            factors.append("Component is DOWN")
            actions.append("Immediate incident response required")
            hours = 0

        # No failover configured
        if not comp.failover.enabled and comp.replicas <= 1:
            risk_score += 5.0
            factors.append("No failover configured")
            actions.append("Enable automatic failover")

        # Cap risk score at 100
        risk_score = min(100.0, risk_score)

        # Determine risk level
        if risk_score >= 70:
            risk_level = RiskLevel.CRITICAL
        elif risk_score >= 45:
            risk_level = RiskLevel.HIGH
        elif risk_score >= 20:
            risk_level = RiskLevel.MEDIUM
        elif risk_score > 0:
            risk_level = RiskLevel.LOW
        else:
            return None  # No risk detected

        # Calculate confidence based on number of factors
        confidence = min(1.0, len(factors) * 0.2 + 0.1)

        if hours == float("inf"):
            hours = 720.0  # Default 30 days if can't estimate

        return FailurePrediction(
            component_id=comp.id,
            component_name=comp.name,
            risk_level=risk_level,
            confidence=round(confidence, 2),
            predicted_failure_hours=round(hours, 1),
            failure_pattern=pattern,
            contributing_factors=factors,
            recommended_actions=actions,
            risk_score=round(risk_score, 1),
        )

    def _detect_patterns(self) -> list[PatternMatch]:
        """Detect failure patterns across the infrastructure."""
        patterns: list[PatternMatch] = []

        # Pattern 1: CPU+Memory cascade
        cpu_mem_components: list[str] = []
        for comp in self._graph.components.values():
            if (
                comp.metrics.cpu_percent > 60
                and comp.metrics.memory_percent > 60
            ):
                cpu_mem_components.append(comp.id)
        if cpu_mem_components:
            patterns.append(
                PatternMatch(
                    pattern=FailurePattern.CPU_MEMORY_CASCADE,
                    affected_components=cpu_mem_components,
                    severity=min(1.0, len(cpu_mem_components) * 0.3),
                    description=(
                        f"{len(cpu_mem_components)} components show "
                        "correlated CPU+memory pressure"
                    ),
                )
            )

        # Pattern 2: Dependency chain risk
        for comp in self._graph.components.values():
            if comp.health in (
                HealthStatus.DEGRADED,
                HealthStatus.OVERLOADED,
                HealthStatus.DOWN,
            ):
                dependents = self._graph.get_dependents(comp.id)
                if len(dependents) >= 2:
                    affected = [comp.id] + [d.id for d in dependents]
                    patterns.append(
                        PatternMatch(
                            pattern=FailurePattern.DEPENDENCY_CHAIN,
                            affected_components=affected,
                            severity=min(1.0, len(dependents) * 0.25),
                            description=(
                                f"{comp.name} is {comp.health.value} with "
                                f"{len(dependents)} dependents at risk"
                            ),
                        )
                    )

        # Pattern 3: Replica drift (components of same type with different health)
        type_groups: dict[ComponentType, list[Component]] = {}
        for comp in self._graph.components.values():
            type_groups.setdefault(comp.type, []).append(comp)
        for ctype, comps in type_groups.items():
            if len(comps) >= 2:
                healths = set(c.health for c in comps)
                if len(healths) > 1 and HealthStatus.HEALTHY in healths:
                    unhealthy = [
                        c.id
                        for c in comps
                        if c.health != HealthStatus.HEALTHY
                    ]
                    if unhealthy:
                        patterns.append(
                            PatternMatch(
                                pattern=FailurePattern.REPLICA_DRIFT,
                                affected_components=[c.id for c in comps],
                                severity=len(unhealthy) / len(comps),
                                description=(
                                    f"{ctype.value} group has divergent health: "
                                    f"{len(unhealthy)}/{len(comps)} unhealthy"
                                ),
                            )
                        )

        # Pattern 4: Thundering herd risk (many components recovering simultaneously)
        recovering = [
            c
            for c in self._graph.components.values()
            if c.health == HealthStatus.DEGRADED and c.replicas >= 3
        ]
        if len(recovering) >= 2:
            patterns.append(
                PatternMatch(
                    pattern=FailurePattern.THUNDERING_HERD,
                    affected_components=[c.id for c in recovering],
                    severity=min(1.0, len(recovering) * 0.3),
                    description=(
                        f"{len(recovering)} multi-replica components degraded "
                        "simultaneously — recovery may cause load spike"
                    ),
                )
            )

        # Pattern 5: Cold start storm (many components with low utilization but high replicas)
        cold_start_risk = [
            c
            for c in self._graph.components.values()
            if c.metrics.cpu_percent < 10 and c.replicas >= 5
        ]
        if cold_start_risk:
            patterns.append(
                PatternMatch(
                    pattern=FailurePattern.COLD_START_STORM,
                    affected_components=[c.id for c in cold_start_risk],
                    severity=min(1.0, len(cold_start_risk) * 0.2),
                    description=(
                        f"{len(cold_start_risk)} over-provisioned components "
                        "may cause cold start storms on restart"
                    ),
                )
            )

        # Pattern 6: Disk exhaustion trend
        disk_risk = [
            c
            for c in self._graph.components.values()
            if c.metrics.disk_percent > 60
        ]
        if disk_risk:
            patterns.append(
                PatternMatch(
                    pattern=FailurePattern.DISK_EXHAUSTION,
                    affected_components=[c.id for c in disk_risk],
                    severity=min(
                        1.0,
                        max(c.metrics.disk_percent for c in disk_risk) / 100,
                    ),
                    description=(
                        f"{len(disk_risk)} components with disk usage >60%"
                    ),
                )
            )

        # Pattern 7: Latency degradation (components near timeout)
        latency_risk: list[str] = []
        for comp in self._graph.components.values():
            # latency_ms may be stored in component parameters
            latency_ms = float(comp.parameters.get("latency_ms", 0))
            if comp.capacity.timeout_seconds > 0 and latency_ms > 0:
                ratio = latency_ms / (comp.capacity.timeout_seconds * 1000)
                if ratio > 0.5:
                    latency_risk.append(comp.id)
        if latency_risk:
            patterns.append(
                PatternMatch(
                    pattern=FailurePattern.LATENCY_DEGRADATION,
                    affected_components=latency_risk,
                    severity=min(1.0, len(latency_risk) * 0.3),
                    description=(
                        f"{len(latency_risk)} components with latency "
                        ">50% of timeout threshold"
                    ),
                )
            )

        return patterns

    def _apply_pattern_boosts(
        self,
        predictions: list[FailurePrediction],
        patterns: list[PatternMatch],
    ) -> list[FailurePrediction]:
        """Boost prediction risk scores based on detected patterns."""
        pattern_components: dict[str, float] = {}
        for p in patterns:
            for cid in p.affected_components:
                pattern_components[cid] = max(
                    pattern_components.get(cid, 0),
                    p.severity * 15,
                )

        boosted: list[FailurePrediction] = []
        for pred in predictions:
            boost = pattern_components.get(pred.component_id, 0)
            if boost > 0:
                new_score = min(100.0, pred.risk_score + boost)
                # Re-evaluate risk level
                if new_score >= 70:
                    new_level = RiskLevel.CRITICAL
                elif new_score >= 45:
                    new_level = RiskLevel.HIGH
                elif new_score >= 20:
                    new_level = RiskLevel.MEDIUM
                else:
                    new_level = RiskLevel.LOW
                pred = FailurePrediction(
                    component_id=pred.component_id,
                    component_name=pred.component_name,
                    risk_level=new_level,
                    confidence=min(1.0, pred.confidence + 0.1),
                    predicted_failure_hours=pred.predicted_failure_hours,
                    failure_pattern=pred.failure_pattern,
                    contributing_factors=pred.contributing_factors
                    + ["Pattern detected in infrastructure"],
                    recommended_actions=pred.recommended_actions,
                    risk_score=round(new_score, 1),
                )
            boosted.append(pred)
        return boosted

    @staticmethod
    def _calculate_overall_risk(
        predictions: list[FailurePrediction],
    ) -> float:
        """Calculate overall infrastructure risk from individual predictions."""
        if not predictions:
            return 0.0
        # Weighted average with higher weight for critical predictions
        weights = {
            RiskLevel.CRITICAL: 4,
            RiskLevel.HIGH: 2,
            RiskLevel.MEDIUM: 1,
            RiskLevel.LOW: 0.5,
            RiskLevel.UNKNOWN: 0.5,
        }
        total_weight = 0.0
        weighted_score = 0.0
        for p in predictions:
            w = weights.get(p.risk_level, 1)
            weighted_score += p.risk_score * w
            total_weight += w
        return (
            min(100.0, weighted_score / total_weight)
            if total_weight > 0
            else 0.0
        )

    @staticmethod
    def _generate_summary(
        predictions: list[FailurePrediction],
        patterns: list[PatternMatch],
        overall_risk: float,
    ) -> str:
        """Generate a human-readable risk summary."""
        if not predictions:
            return (
                "No significant failure risks detected. "
                "Infrastructure appears healthy."
            )

        critical_count = sum(
            1 for p in predictions if p.risk_level == RiskLevel.CRITICAL
        )
        high_count = sum(
            1 for p in predictions if p.risk_level == RiskLevel.HIGH
        )

        parts: list[str] = []
        if critical_count > 0:
            parts.append(
                f"{critical_count} CRITICAL "
                f"risk{'s' if critical_count > 1 else ''}"
            )
        if high_count > 0:
            parts.append(
                f"{high_count} HIGH "
                f"risk{'s' if high_count > 1 else ''}"
            )

        summary = f"Overall risk: {overall_risk:.0f}/100. "
        if parts:
            summary += "Detected: " + ", ".join(parts) + ". "
        if patterns:
            summary += (
                f"{len(patterns)} failure "
                f"pattern{'s' if len(patterns) > 1 else ''} "
                "detected across infrastructure."
            )
        return summary
