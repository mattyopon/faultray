"""Queue Backpressure Analyzer.

Analyzes message queue backpressure scenarios and their cascading effects
across distributed infrastructure. Supports Kafka, RabbitMQ, SQS,
Redis Streams, and NATS JetStream. Provides consumer lag analysis,
DLQ overflow risk assessment, partition rebalancing impact modeling,
producer throttling strategy evaluation, message TTL / expiration policy
analysis, queue depth vs processing latency correlation, consumer group
scaling recommendations, poison message detection with circuit breaking,
flow control mechanism evaluation, and multi-queue dependency chain
backpressure propagation analysis.

Designed for commercial chaos engineering: helps teams understand how
backpressure propagates through complex queue topologies under failure
conditions and identify optimal mitigation strategies.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class QueuePlatform(str, Enum):
    """Supported message queue / event streaming platforms."""

    KAFKA = "kafka"
    RABBITMQ = "rabbitmq"
    SQS = "sqs"
    REDIS_STREAMS = "redis_streams"
    NATS_JETSTREAM = "nats_jetstream"


class BackpressureSeverity(str, Enum):
    """Severity level for backpressure conditions."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ThrottleStrategy(str, Enum):
    """Producer throttling strategies."""

    NONE = "none"
    BLOCK = "block"
    DROP_OLDEST = "drop_oldest"
    DROP_NEWEST = "drop_newest"
    RATE_LIMIT = "rate_limit"
    ADAPTIVE = "adaptive"


class FlowControlMode(str, Enum):
    """Flow control mechanisms."""

    NONE = "none"
    CREDIT_BASED = "credit_based"
    WINDOW_BASED = "window_based"
    TOKEN_BUCKET = "token_bucket"
    BACKOFF = "backoff"


class CircuitState(str, Enum):
    """Circuit breaker state for poison message handling."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class RiskLevel(str, Enum):
    """Risk assessment level."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Platform characteristics
# ---------------------------------------------------------------------------

_PLATFORM_TRAITS: dict[QueuePlatform, dict[str, Any]] = {
    QueuePlatform.KAFKA: {
        "supports_partitions": True,
        "native_dlq": False,
        "flow_control": FlowControlMode.BACKOFF,
        "max_consumers_per_partition": 1,
        "ordering_guarantee": "per_partition",
        "default_retention_hours": 168,
        "rebalance_downtime_factor": 1.5,
    },
    QueuePlatform.RABBITMQ: {
        "supports_partitions": False,
        "native_dlq": True,
        "flow_control": FlowControlMode.CREDIT_BASED,
        "max_consumers_per_partition": -1,  # unlimited
        "ordering_guarantee": "per_queue",
        "default_retention_hours": 0,  # no built-in retention
        "rebalance_downtime_factor": 0.5,
    },
    QueuePlatform.SQS: {
        "supports_partitions": False,
        "native_dlq": True,
        "flow_control": FlowControlMode.NONE,
        "max_consumers_per_partition": -1,
        "ordering_guarantee": "best_effort",
        "default_retention_hours": 96,
        "rebalance_downtime_factor": 0.0,
    },
    QueuePlatform.REDIS_STREAMS: {
        "supports_partitions": False,
        "native_dlq": False,
        "flow_control": FlowControlMode.BACKOFF,
        "max_consumers_per_partition": -1,
        "ordering_guarantee": "per_stream",
        "default_retention_hours": 0,
        "rebalance_downtime_factor": 0.3,
    },
    QueuePlatform.NATS_JETSTREAM: {
        "supports_partitions": False,
        "native_dlq": False,
        "flow_control": FlowControlMode.WINDOW_BASED,
        "max_consumers_per_partition": -1,
        "ordering_guarantee": "per_stream",
        "default_retention_hours": 24,
        "rebalance_downtime_factor": 0.2,
    },
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class QueueEndpoint:
    """A single queue / topic / stream endpoint in the topology."""

    queue_id: str
    component_id: str
    platform: QueuePlatform
    partitions: int = 1
    consumers: int = 1
    producer_rate_msg_sec: float = 100.0
    consumer_rate_msg_sec: float = 120.0
    current_depth: int = 0
    max_depth: int = 100_000
    message_ttl_seconds: float = 0.0  # 0 = no TTL
    dlq_enabled: bool = True
    dlq_current_depth: int = 0
    dlq_max_depth: int = 10_000
    retry_max: int = 3
    consumer_group_id: str = ""
    is_healthy: bool = True


@dataclass
class QueueDependencyEdge:
    """A dependency link between two queue endpoints.

    Represents a processing pipeline where messages consumed from
    *source_queue_id* produce messages into *target_queue_id*.
    """

    source_queue_id: str
    target_queue_id: str
    amplification_factor: float = 1.0  # messages produced per consumed


@dataclass
class ConsumerLagSnapshot:
    """Point-in-time consumer lag measurement."""

    queue_id: str
    timestamp: datetime
    lag_messages: int = 0
    lag_seconds: float = 0.0
    consumer_count: int = 1


@dataclass
class ConsumerLagAnalysis:
    """Result of analysing consumer lag trend and growth rate."""

    queue_id: str
    current_lag: int = 0
    lag_growth_rate_per_sec: float = 0.0
    estimated_drain_time_sec: float = 0.0
    is_growing: bool = False
    severity: BackpressureSeverity = BackpressureSeverity.NONE
    recommendations: list[str] = field(default_factory=list)


@dataclass
class DLQRiskAssessment:
    """Dead letter queue overflow risk assessment."""

    queue_id: str
    dlq_enabled: bool = True
    current_depth: int = 0
    max_depth: int = 10_000
    fill_ratio: float = 0.0
    estimated_overflow_minutes: float = float("inf")
    risk_level: RiskLevel = RiskLevel.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class PartitionRebalanceImpact:
    """Impact assessment of a consumer failure triggering partition rebalance."""

    queue_id: str
    platform: QueuePlatform
    partitions_affected: int = 0
    estimated_downtime_seconds: float = 0.0
    messages_at_risk: int = 0
    ordering_disrupted: bool = False
    recommendations: list[str] = field(default_factory=list)


@dataclass
class ThrottleImpact:
    """System-wide impact of a producer throttling strategy."""

    queue_id: str
    strategy: ThrottleStrategy = ThrottleStrategy.NONE
    message_loss_risk: bool = False
    latency_increase_factor: float = 1.0
    upstream_impact_score: float = 0.0  # 0-100
    recommendations: list[str] = field(default_factory=list)


@dataclass
class TTLAnalysis:
    """Message TTL and expiration policy analysis."""

    queue_id: str
    ttl_seconds: float = 0.0
    messages_expiring_per_minute: float = 0.0
    data_loss_risk: bool = False
    risk_level: RiskLevel = RiskLevel.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class DepthLatencyCorrelation:
    """Queue depth vs processing latency correlation."""

    queue_id: str
    current_depth: int = 0
    estimated_latency_ms: float = 0.0
    latency_at_max_depth_ms: float = 0.0
    depth_utilization_pct: float = 0.0
    severity: BackpressureSeverity = BackpressureSeverity.NONE
    recommendations: list[str] = field(default_factory=list)


@dataclass
class ScalingRecommendation:
    """Consumer group scaling recommendation."""

    queue_id: str
    current_consumers: int = 1
    recommended_consumers: int = 1
    reason: str = ""
    estimated_drain_improvement_pct: float = 0.0
    max_useful_consumers: int = 1


@dataclass
class PoisonMessageAssessment:
    """Poison message detection and circuit breaking analysis."""

    queue_id: str
    circuit_state: CircuitState = CircuitState.CLOSED
    retry_max: int = 3
    dlq_available: bool = True
    estimated_block_duration_sec: float = 0.0
    consumer_stall_risk: bool = False
    recommendations: list[str] = field(default_factory=list)


@dataclass
class FlowControlAssessment:
    """Flow control mechanism evaluation."""

    queue_id: str
    mode: FlowControlMode = FlowControlMode.NONE
    effectiveness_score: float = 0.0  # 0-100
    latency_overhead_ms: float = 0.0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class PropagationStep:
    """One step in a backpressure propagation chain."""

    queue_id: str
    depth_increase: int = 0
    latency_increase_ms: float = 0.0
    severity: BackpressureSeverity = BackpressureSeverity.NONE


@dataclass
class BackpressurePropagation:
    """Multi-queue dependency chain backpressure propagation result."""

    origin_queue_id: str
    chain: list[PropagationStep] = field(default_factory=list)
    total_queues_affected: int = 0
    max_severity: BackpressureSeverity = BackpressureSeverity.NONE
    recommendations: list[str] = field(default_factory=list)


@dataclass
class BackpressureReport:
    """Comprehensive backpressure analysis report."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    queues_analyzed: int = 0
    consumer_lag_analyses: list[ConsumerLagAnalysis] = field(default_factory=list)
    dlq_assessments: list[DLQRiskAssessment] = field(default_factory=list)
    rebalance_impacts: list[PartitionRebalanceImpact] = field(default_factory=list)
    throttle_impacts: list[ThrottleImpact] = field(default_factory=list)
    ttl_analyses: list[TTLAnalysis] = field(default_factory=list)
    depth_latency_correlations: list[DepthLatencyCorrelation] = field(
        default_factory=list
    )
    scaling_recommendations: list[ScalingRecommendation] = field(default_factory=list)
    poison_assessments: list[PoisonMessageAssessment] = field(default_factory=list)
    flow_control_assessments: list[FlowControlAssessment] = field(default_factory=list)
    propagation_results: list[BackpressurePropagation] = field(default_factory=list)
    overall_risk: RiskLevel = RiskLevel.LOW
    summary: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _severity_from_ratio(ratio: float) -> BackpressureSeverity:
    """Map a 0-1 ratio to a backpressure severity level."""
    if ratio >= 0.9:
        return BackpressureSeverity.CRITICAL
    if ratio >= 0.7:
        return BackpressureSeverity.HIGH
    if ratio >= 0.4:
        return BackpressureSeverity.MEDIUM
    if ratio > 0.0:
        return BackpressureSeverity.LOW
    return BackpressureSeverity.NONE


def _risk_from_ratio(ratio: float) -> RiskLevel:
    """Map a 0-1 ratio to a risk level."""
    if ratio >= 0.9:
        return RiskLevel.CRITICAL
    if ratio >= 0.7:
        return RiskLevel.HIGH
    if ratio >= 0.4:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


_SEVERITY_RANK: dict[BackpressureSeverity, int] = {
    BackpressureSeverity.NONE: 0,
    BackpressureSeverity.LOW: 1,
    BackpressureSeverity.MEDIUM: 2,
    BackpressureSeverity.HIGH: 3,
    BackpressureSeverity.CRITICAL: 4,
}

_RISK_RANK: dict[RiskLevel, int] = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


def _max_severity(*severities: BackpressureSeverity) -> BackpressureSeverity:
    if not severities:
        return BackpressureSeverity.NONE
    return max(severities, key=lambda s: _SEVERITY_RANK[s])


def _max_risk(*risks: RiskLevel) -> RiskLevel:
    if not risks:
        return RiskLevel.LOW
    return max(risks, key=lambda r: _RISK_RANK[r])


def _risk_to_severity(risk: RiskLevel) -> BackpressureSeverity:
    mapping = {
        RiskLevel.LOW: BackpressureSeverity.LOW,
        RiskLevel.MEDIUM: BackpressureSeverity.MEDIUM,
        RiskLevel.HIGH: BackpressureSeverity.HIGH,
        RiskLevel.CRITICAL: BackpressureSeverity.CRITICAL,
    }
    return mapping[risk]


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class QueueBackpressureAnalyzer:
    """Analyzes message queue backpressure scenarios and cascading effects.

    Parameters
    ----------
    graph : InfraGraph
        The infrastructure dependency graph to reference for component data.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph
        self._queues: dict[str, QueueEndpoint] = {}
        self._edges: list[QueueDependencyEdge] = []

    # -- registration -------------------------------------------------------

    def add_queue(self, queue: QueueEndpoint) -> None:
        """Register a queue endpoint for analysis."""
        self._queues[queue.queue_id] = queue

    def add_dependency(self, edge: QueueDependencyEdge) -> None:
        """Register a dependency between two queue endpoints."""
        self._edges.append(edge)

    # -- consumer lag analysis ----------------------------------------------

    def analyze_consumer_lag(
        self,
        queue: QueueEndpoint,
        snapshots: list[ConsumerLagSnapshot] | None = None,
    ) -> ConsumerLagAnalysis:
        """Analyze consumer lag and predict growth rate.

        If *snapshots* are provided (at least two), the growth rate is
        computed from the trend.  Otherwise it is estimated from the
        difference between producer and consumer rates.
        """
        growth_rate: float = 0.0
        current_lag = queue.current_depth

        if snapshots and len(snapshots) >= 2:
            sorted_snaps = sorted(snapshots, key=lambda s: s.timestamp)
            first, last = sorted_snaps[0], sorted_snaps[-1]
            dt = (last.timestamp - first.timestamp).total_seconds()
            if dt > 0:
                growth_rate = (last.lag_messages - first.lag_messages) / dt
                current_lag = last.lag_messages
        else:
            # Estimate from rate differential
            net_rate = queue.producer_rate_msg_sec - (
                queue.consumer_rate_msg_sec * max(queue.consumers, 1)
            )
            growth_rate = max(0.0, net_rate)

        is_growing = growth_rate > 0.0

        # Estimate drain time
        if is_growing:
            drain_time = float("inf")
        else:
            effective_drain_rate = (
                queue.consumer_rate_msg_sec * max(queue.consumers, 1)
            ) - queue.producer_rate_msg_sec
            if effective_drain_rate > 0 and current_lag > 0:
                drain_time = current_lag / effective_drain_rate
            else:
                drain_time = 0.0

        depth_ratio = current_lag / max(queue.max_depth, 1)
        severity = _severity_from_ratio(depth_ratio)

        recommendations: list[str] = []
        if is_growing:
            recommendations.append(
                "Consumer lag is growing; consider scaling consumers"
            )
        if depth_ratio > 0.7:
            recommendations.append(
                "Queue depth exceeds 70% of capacity; risk of message loss"
            )
        if queue.consumers < queue.partitions:
            recommendations.append(
                f"Consumers ({queue.consumers}) < partitions ({queue.partitions}); "
                "add consumers for full parallelism"
            )

        return ConsumerLagAnalysis(
            queue_id=queue.queue_id,
            current_lag=current_lag,
            lag_growth_rate_per_sec=round(growth_rate, 4),
            estimated_drain_time_sec=round(drain_time, 2) if math.isfinite(drain_time) else float("inf"),
            is_growing=is_growing,
            severity=severity,
            recommendations=recommendations,
        )

    # -- DLQ overflow risk --------------------------------------------------

    def assess_dlq_risk(self, queue: QueueEndpoint) -> DLQRiskAssessment:
        """Assess dead letter queue overflow risk."""
        if not queue.dlq_enabled:
            return DLQRiskAssessment(
                queue_id=queue.queue_id,
                dlq_enabled=False,
                current_depth=0,
                max_depth=0,
                fill_ratio=0.0,
                estimated_overflow_minutes=float("inf"),
                risk_level=RiskLevel.HIGH,
                recommendations=[
                    "DLQ is disabled; failed messages will be lost or block processing",
                    "Enable DLQ with appropriate max depth and alerting",
                ],
            )

        fill_ratio = queue.dlq_current_depth / max(queue.dlq_max_depth, 1)
        risk = _risk_from_ratio(fill_ratio)

        # Estimate time to overflow based on current error rate assumption
        # Use 1% of producer rate as assumed error rate
        error_rate = queue.producer_rate_msg_sec * 0.01
        remaining = max(queue.dlq_max_depth - queue.dlq_current_depth, 0)
        if error_rate > 0 and remaining > 0:
            overflow_sec = remaining / error_rate
            overflow_min = overflow_sec / 60.0
        elif remaining <= 0:
            overflow_min = 0.0
            risk = RiskLevel.CRITICAL
        else:
            overflow_min = float("inf")

        recommendations: list[str] = []
        if fill_ratio > 0.5:
            recommendations.append(
                "DLQ fill ratio exceeds 50%; investigate and drain failed messages"
            )
        if fill_ratio > 0.8:
            recommendations.append(
                "DLQ nearing capacity; immediate attention required"
            )
        if queue.dlq_max_depth < 1000:
            recommendations.append(
                "DLQ max depth is low; consider increasing capacity"
            )

        return DLQRiskAssessment(
            queue_id=queue.queue_id,
            dlq_enabled=True,
            current_depth=queue.dlq_current_depth,
            max_depth=queue.dlq_max_depth,
            fill_ratio=round(fill_ratio, 4),
            estimated_overflow_minutes=round(overflow_min, 2) if math.isfinite(overflow_min) else float("inf"),
            risk_level=risk,
            recommendations=recommendations,
        )

    # -- partition rebalancing impact ---------------------------------------

    def assess_rebalance_impact(
        self,
        queue: QueueEndpoint,
        failing_consumers: int = 1,
    ) -> PartitionRebalanceImpact:
        """Assess impact of consumer failure triggering partition rebalance."""
        traits = _PLATFORM_TRAITS.get(queue.platform, {})
        rebalance_factor = traits.get("rebalance_downtime_factor", 1.0)
        supports_partitions = traits.get("supports_partitions", False)

        surviving = max(queue.consumers - failing_consumers, 0)

        if supports_partitions:
            partitions_affected = queue.partitions
        else:
            partitions_affected = 0 if surviving > 0 else 1

        # Estimate downtime: base 5s per partition affected * platform factor
        downtime_sec = partitions_affected * 5.0 * rebalance_factor
        if surviving == 0:
            # Complete consumer group loss
            downtime_sec = max(downtime_sec, 60.0)

        messages_at_risk = int(
            queue.producer_rate_msg_sec * downtime_sec
        )

        ordering = traits.get("ordering_guarantee", "none")
        ordering_disrupted = ordering == "per_partition" and partitions_affected > 0

        recommendations: list[str] = []
        if surviving == 0:
            recommendations.append(
                "All consumers failed; queue will accumulate messages until recovery"
            )
        if partitions_affected > 0:
            recommendations.append(
                "Use sticky partition assignment to minimise rebalance impact"
            )
        if queue.consumers <= 1:
            recommendations.append(
                "Single consumer is an SPOF; add at least one more consumer"
            )

        return PartitionRebalanceImpact(
            queue_id=queue.queue_id,
            platform=queue.platform,
            partitions_affected=partitions_affected,
            estimated_downtime_seconds=round(downtime_sec, 2),
            messages_at_risk=max(0, messages_at_risk),
            ordering_disrupted=ordering_disrupted,
            recommendations=recommendations,
        )

    # -- producer throttling ------------------------------------------------

    def evaluate_throttle_strategy(
        self,
        queue: QueueEndpoint,
        strategy: ThrottleStrategy,
    ) -> ThrottleImpact:
        """Evaluate the system-wide impact of a producer throttling strategy."""
        loss_risk = False
        latency_factor = 1.0
        upstream_score = 0.0
        recommendations: list[str] = []

        depth_ratio = queue.current_depth / max(queue.max_depth, 1)

        if strategy == ThrottleStrategy.NONE:
            if depth_ratio > 0.8:
                upstream_score = 80.0
                recommendations.append(
                    "No throttling with high depth; producers may be blocked by broker"
                )
            else:
                upstream_score = 0.0

        elif strategy == ThrottleStrategy.BLOCK:
            latency_factor = 1.0 + depth_ratio * 5.0
            upstream_score = _clamp(depth_ratio * 100.0)
            recommendations.append(
                "Blocking strategy adds latency proportional to queue depth"
            )

        elif strategy == ThrottleStrategy.DROP_OLDEST:
            loss_risk = True
            latency_factor = 1.0
            upstream_score = 20.0
            recommendations.append(
                "Drop-oldest discards old messages; acceptable only for "
                "time-sensitive data (e.g. metrics, sensor readings)"
            )

        elif strategy == ThrottleStrategy.DROP_NEWEST:
            loss_risk = True
            latency_factor = 1.0
            upstream_score = 30.0
            recommendations.append(
                "Drop-newest rejects new messages; producers must implement retry"
            )

        elif strategy == ThrottleStrategy.RATE_LIMIT:
            latency_factor = 1.0 + depth_ratio * 2.0
            upstream_score = _clamp(depth_ratio * 60.0)
            recommendations.append(
                "Rate limiting smooths traffic but may cause upstream queuing"
            )

        elif strategy == ThrottleStrategy.ADAPTIVE:
            latency_factor = 1.0 + depth_ratio * 1.5
            upstream_score = _clamp(depth_ratio * 40.0)
            recommendations.append(
                "Adaptive throttling is recommended; adjusts dynamically to load"
            )

        return ThrottleImpact(
            queue_id=queue.queue_id,
            strategy=strategy,
            message_loss_risk=loss_risk,
            latency_increase_factor=round(latency_factor, 4),
            upstream_impact_score=round(upstream_score, 2),
            recommendations=recommendations,
        )

    # -- message TTL analysis -----------------------------------------------

    def analyze_ttl(self, queue: QueueEndpoint) -> TTLAnalysis:
        """Analyze message TTL and expiration policy."""
        if queue.message_ttl_seconds <= 0:
            return TTLAnalysis(
                queue_id=queue.queue_id,
                ttl_seconds=0.0,
                messages_expiring_per_minute=0.0,
                data_loss_risk=False,
                risk_level=RiskLevel.LOW,
                recommendations=[
                    "No TTL configured; messages persist indefinitely unless consumed"
                ],
            )

        # Estimate expiration rate: messages older than TTL are dropped
        effective_consume_rate = queue.consumer_rate_msg_sec * max(queue.consumers, 1)
        net_rate = queue.producer_rate_msg_sec - effective_consume_rate
        if net_rate > 0:
            # If lag is growing, messages will start expiring once depth
            # exceeds what can be consumed within TTL window
            capacity_within_ttl = effective_consume_rate * queue.message_ttl_seconds
            if queue.current_depth > capacity_within_ttl:
                expiring_per_sec = net_rate
            else:
                expiring_per_sec = 0.0
        else:
            expiring_per_sec = 0.0

        expiring_per_min = expiring_per_sec * 60.0
        data_loss_risk = expiring_per_min > 0

        if data_loss_risk:
            ratio = min(expiring_per_min / max(queue.producer_rate_msg_sec * 60, 1), 1.0)
            risk = _risk_from_ratio(ratio)
        else:
            risk = RiskLevel.LOW

        recommendations: list[str] = []
        if queue.message_ttl_seconds < 60:
            recommendations.append(
                "TTL is very short (< 60s); high risk of message expiration under load"
            )
        if data_loss_risk:
            recommendations.append(
                "Messages are expiring before consumption; scale consumers or increase TTL"
            )
        if not queue.dlq_enabled and data_loss_risk:
            recommendations.append(
                "No DLQ to capture expired messages; enable DLQ for recovery"
            )

        return TTLAnalysis(
            queue_id=queue.queue_id,
            ttl_seconds=queue.message_ttl_seconds,
            messages_expiring_per_minute=round(expiring_per_min, 2),
            data_loss_risk=data_loss_risk,
            risk_level=risk,
            recommendations=recommendations,
        )

    # -- depth vs latency correlation ---------------------------------------

    def correlate_depth_latency(
        self,
        queue: QueueEndpoint,
        base_latency_ms: float = 5.0,
    ) -> DepthLatencyCorrelation:
        """Estimate processing latency based on queue depth.

        Latency grows logarithmically with depth, reflecting real-world
        broker behaviour where deeper queues incur higher seek/scan costs.
        """
        depth_pct = (queue.current_depth / max(queue.max_depth, 1)) * 100.0

        # Logarithmic latency model
        if queue.current_depth > 0:
            depth_factor = 1.0 + math.log1p(queue.current_depth / 1000.0)
        else:
            depth_factor = 1.0

        estimated_latency = base_latency_ms * depth_factor

        # Latency at max depth
        if queue.max_depth > 0:
            max_depth_factor = 1.0 + math.log1p(queue.max_depth / 1000.0)
        else:
            max_depth_factor = 1.0
        latency_at_max = base_latency_ms * max_depth_factor

        severity = _severity_from_ratio(depth_pct / 100.0)

        recommendations: list[str] = []
        if depth_pct > 50:
            recommendations.append(
                "Queue depth above 50%; latency is elevated"
            )
        if depth_pct > 80:
            recommendations.append(
                "Queue depth above 80%; consider emergency consumer scaling"
            )

        return DepthLatencyCorrelation(
            queue_id=queue.queue_id,
            current_depth=queue.current_depth,
            estimated_latency_ms=round(estimated_latency, 4),
            latency_at_max_depth_ms=round(latency_at_max, 4),
            depth_utilization_pct=round(depth_pct, 2),
            severity=severity,
            recommendations=recommendations,
        )

    # -- consumer group scaling ---------------------------------------------

    def recommend_scaling(self, queue: QueueEndpoint) -> ScalingRecommendation:
        """Recommend consumer group scaling based on current metrics."""
        traits = _PLATFORM_TRAITS.get(queue.platform, {})
        supports_partitions = traits.get("supports_partitions", False)
        max_per_partition = traits.get("max_consumers_per_partition", -1)

        # Max useful consumers
        if supports_partitions and max_per_partition == 1:
            max_useful = queue.partitions
        else:
            # For non-partitioned systems, cap at a reasonable upper bound
            max_useful = max(queue.partitions * 4, 16)

        # Calculate needed consumers based on rate
        total_consume_needed = queue.producer_rate_msg_sec * 1.2  # 20% headroom
        if queue.consumer_rate_msg_sec > 0:
            needed = math.ceil(total_consume_needed / queue.consumer_rate_msg_sec)
        else:
            needed = queue.consumers

        recommended = max(1, min(needed, max_useful))

        reason = ""
        improvement = 0.0
        if recommended > queue.consumers:
            reason = (
                f"Scale from {queue.consumers} to {recommended} consumers "
                f"to maintain 20% headroom at current producer rate"
            )
            if queue.consumers > 0:
                improvement = ((recommended - queue.consumers) / queue.consumers) * 100.0
        elif recommended < queue.consumers:
            reason = (
                f"Current {queue.consumers} consumers exceed needed {recommended}; "
                "consider scaling down to reduce cost"
            )
        else:
            reason = "Current consumer count is optimal"

        return ScalingRecommendation(
            queue_id=queue.queue_id,
            current_consumers=queue.consumers,
            recommended_consumers=recommended,
            reason=reason,
            estimated_drain_improvement_pct=round(improvement, 2),
            max_useful_consumers=max_useful,
        )

    # -- poison message detection -------------------------------------------

    def assess_poison_messages(
        self,
        queue: QueueEndpoint,
        failed_delivery_count: int = 0,
    ) -> PoisonMessageAssessment:
        """Assess poison message risk and circuit breaking readiness."""
        if failed_delivery_count >= queue.retry_max:
            circuit_state = CircuitState.OPEN
        elif failed_delivery_count > 0:
            circuit_state = CircuitState.HALF_OPEN
        else:
            circuit_state = CircuitState.CLOSED

        # Without DLQ, a poison message can stall the entire consumer group
        consumer_stall_risk = (
            not queue.dlq_enabled and failed_delivery_count > 0
        )

        # Estimated block duration: retries * backoff
        block_sec = 0.0
        if failed_delivery_count > 0:
            for attempt in range(min(failed_delivery_count, queue.retry_max)):
                block_sec += 2 ** attempt  # exponential backoff seconds

        recommendations: list[str] = []
        if not queue.dlq_enabled:
            recommendations.append(
                "Enable DLQ to prevent poison messages from blocking consumers"
            )
        if queue.retry_max > 5:
            recommendations.append(
                "High retry max may delay poison message detection; consider reducing"
            )
        if circuit_state == CircuitState.OPEN:
            recommendations.append(
                "Circuit breaker is OPEN; investigate and resolve the poison message"
            )
        if consumer_stall_risk:
            recommendations.append(
                "Consumer stall risk: poison message without DLQ will block processing"
            )

        return PoisonMessageAssessment(
            queue_id=queue.queue_id,
            circuit_state=circuit_state,
            retry_max=queue.retry_max,
            dlq_available=queue.dlq_enabled,
            estimated_block_duration_sec=round(block_sec, 2),
            consumer_stall_risk=consumer_stall_risk,
            recommendations=recommendations,
        )

    # -- flow control evaluation --------------------------------------------

    def evaluate_flow_control(
        self,
        queue: QueueEndpoint,
    ) -> FlowControlAssessment:
        """Evaluate the flow control mechanism for the queue platform."""
        traits = _PLATFORM_TRAITS.get(queue.platform, {})
        mode = traits.get("flow_control", FlowControlMode.NONE)

        effectiveness = 0.0
        overhead_ms = 0.0
        recommendations: list[str] = []

        if mode == FlowControlMode.NONE:
            effectiveness = 10.0
            overhead_ms = 0.0
            recommendations.append(
                "No flow control; implement application-level backpressure handling"
            )

        elif mode == FlowControlMode.CREDIT_BASED:
            effectiveness = 85.0
            overhead_ms = 0.5
            recommendations.append(
                "Credit-based flow control is effective; ensure credits are tuned"
            )

        elif mode == FlowControlMode.WINDOW_BASED:
            effectiveness = 75.0
            overhead_ms = 1.0
            recommendations.append(
                "Window-based flow control provides good backpressure protection"
            )

        elif mode == FlowControlMode.TOKEN_BUCKET:
            effectiveness = 70.0
            overhead_ms = 0.2
            recommendations.append(
                "Token bucket flow control smooths bursts effectively"
            )

        elif mode == FlowControlMode.BACKOFF:
            effectiveness = 60.0
            overhead_ms = 2.0
            recommendations.append(
                "Backoff-based flow control may cause latency spikes under load"
            )

        # Adjust effectiveness based on current load
        depth_ratio = queue.current_depth / max(queue.max_depth, 1)
        if depth_ratio > 0.8:
            effectiveness *= 0.7  # flow control less effective when already deep
            recommendations.append(
                "Flow control effectiveness reduced at high queue depth"
            )

        return FlowControlAssessment(
            queue_id=queue.queue_id,
            mode=mode,
            effectiveness_score=round(_clamp(effectiveness), 2),
            latency_overhead_ms=round(overhead_ms, 4),
            recommendations=recommendations,
        )

    # -- multi-queue backpressure propagation --------------------------------

    def analyze_propagation(
        self,
        origin_queue_id: str,
    ) -> BackpressurePropagation:
        """Analyze backpressure propagation through the queue dependency chain.

        Starting from the *origin_queue_id*, follow downstream dependency
        edges and compute cumulative depth increase and latency impact.
        """
        origin = self._queues.get(origin_queue_id)
        if origin is None:
            return BackpressurePropagation(
                origin_queue_id=origin_queue_id,
                chain=[],
                total_queues_affected=0,
                max_severity=BackpressureSeverity.NONE,
                recommendations=["Queue not found in topology"],
            )

        visited: set[str] = set()
        chain: list[PropagationStep] = []
        current_ids = [origin_queue_id]
        cumulative_pressure = origin.current_depth / max(origin.max_depth, 1)

        while current_ids:
            next_ids: list[str] = []
            for cid in current_ids:
                if cid in visited:
                    continue
                visited.add(cid)

                q = self._queues.get(cid)
                if q is None:
                    continue

                depth_ratio = q.current_depth / max(q.max_depth, 1)
                combined_ratio = min(1.0, (depth_ratio + cumulative_pressure) / 2.0)
                severity = _severity_from_ratio(combined_ratio)

                depth_increase = int(
                    q.producer_rate_msg_sec * 10 * cumulative_pressure
                )
                latency_increase = 5.0 * combined_ratio * 10  # ms

                chain.append(
                    PropagationStep(
                        queue_id=cid,
                        depth_increase=depth_increase,
                        latency_increase_ms=round(latency_increase, 2),
                        severity=severity,
                    )
                )

                # Find downstream queues via edges
                for edge in self._edges:
                    if edge.source_queue_id == cid and edge.target_queue_id not in visited:
                        next_ids.append(edge.target_queue_id)
                        cumulative_pressure = min(
                            1.0,
                            cumulative_pressure * edge.amplification_factor * 0.8,
                        )

            current_ids = next_ids

        severities = [step.severity for step in chain]
        max_sev = _max_severity(*severities) if severities else BackpressureSeverity.NONE

        recommendations: list[str] = []
        if len(chain) > 3:
            recommendations.append(
                "Long dependency chain detected; consider adding buffer queues"
            )
        if max_sev in (BackpressureSeverity.HIGH, BackpressureSeverity.CRITICAL):
            recommendations.append(
                "High backpressure propagation risk; implement circuit breakers "
                "between queue stages"
            )

        return BackpressurePropagation(
            origin_queue_id=origin_queue_id,
            chain=chain,
            total_queues_affected=len(chain),
            max_severity=max_sev,
            recommendations=recommendations,
        )

    # -- comprehensive report -----------------------------------------------

    def generate_report(
        self,
        throttle_strategy: ThrottleStrategy = ThrottleStrategy.ADAPTIVE,
    ) -> BackpressureReport:
        """Generate a comprehensive backpressure analysis report.

        Analyses all registered queues across every dimension and
        produces a consolidated report with overall risk assessment.
        """
        lag_analyses: list[ConsumerLagAnalysis] = []
        dlq_assessments: list[DLQRiskAssessment] = []
        rebalance_impacts: list[PartitionRebalanceImpact] = []
        throttle_impacts: list[ThrottleImpact] = []
        ttl_analyses: list[TTLAnalysis] = []
        depth_correlations: list[DepthLatencyCorrelation] = []
        scaling_recs: list[ScalingRecommendation] = []
        poison_assessments: list[PoisonMessageAssessment] = []
        flow_assessments: list[FlowControlAssessment] = []
        propagation_results: list[BackpressurePropagation] = []

        for queue in self._queues.values():
            lag_analyses.append(self.analyze_consumer_lag(queue))
            dlq_assessments.append(self.assess_dlq_risk(queue))
            rebalance_impacts.append(self.assess_rebalance_impact(queue))
            throttle_impacts.append(
                self.evaluate_throttle_strategy(queue, throttle_strategy)
            )
            ttl_analyses.append(self.analyze_ttl(queue))
            depth_correlations.append(self.correlate_depth_latency(queue))
            scaling_recs.append(self.recommend_scaling(queue))
            poison_assessments.append(self.assess_poison_messages(queue))
            flow_assessments.append(self.evaluate_flow_control(queue))
            propagation_results.append(self.analyze_propagation(queue.queue_id))

        # Determine overall risk
        all_risks: list[RiskLevel] = []
        for dlq in dlq_assessments:
            all_risks.append(dlq.risk_level)
        for ttl in ttl_analyses:
            all_risks.append(ttl.risk_level)
        # Map severities to risk
        for lag in lag_analyses:
            if lag.severity in (
                BackpressureSeverity.HIGH,
                BackpressureSeverity.CRITICAL,
            ):
                all_risks.append(RiskLevel.HIGH)
            elif lag.severity == BackpressureSeverity.MEDIUM:
                all_risks.append(RiskLevel.MEDIUM)
        for prop in propagation_results:
            if prop.max_severity in (
                BackpressureSeverity.HIGH,
                BackpressureSeverity.CRITICAL,
            ):
                all_risks.append(RiskLevel.HIGH)

        overall = _max_risk(*all_risks) if all_risks else RiskLevel.LOW

        # Summary
        summary: list[str] = []
        growing_count = sum(1 for la in lag_analyses if la.is_growing)
        if growing_count:
            summary.append(
                f"{growing_count} queue(s) have growing consumer lag"
            )
        dlq_risk_count = sum(
            1
            for d in dlq_assessments
            if d.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        )
        if dlq_risk_count:
            summary.append(
                f"{dlq_risk_count} queue(s) have high DLQ overflow risk"
            )
        scale_needed = sum(
            1
            for s in scaling_recs
            if s.recommended_consumers > s.current_consumers
        )
        if scale_needed:
            summary.append(
                f"{scale_needed} queue(s) need consumer scaling"
            )

        if not summary:
            summary.append("All queues are operating within normal parameters")

        return BackpressureReport(
            queues_analyzed=len(self._queues),
            consumer_lag_analyses=lag_analyses,
            dlq_assessments=dlq_assessments,
            rebalance_impacts=rebalance_impacts,
            throttle_impacts=throttle_impacts,
            ttl_analyses=ttl_analyses,
            depth_latency_correlations=depth_correlations,
            scaling_recommendations=scaling_recs,
            poison_assessments=poison_assessments,
            flow_control_assessments=flow_assessments,
            propagation_results=propagation_results,
            overall_risk=overall,
            summary=summary,
        )
