"""Tests for the Queue Backpressure Analyzer module.

Covers consumer lag analysis, DLQ overflow risk assessment, partition
rebalancing impact, producer throttling strategies, message TTL analysis,
queue depth vs latency correlation, consumer group scaling recommendations,
poison message detection with circuit breaking, flow control mechanism
evaluation, multi-queue dependency chain backpressure propagation, and
comprehensive report generation. Targets 100% branch coverage.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.simulator.queue_backpressure_analyzer import (
    BackpressureReport,
    BackpressurePropagation,
    BackpressureSeverity,
    CircuitState,
    ConsumerLagAnalysis,
    ConsumerLagSnapshot,
    DepthLatencyCorrelation,
    DLQRiskAssessment,
    FlowControlAssessment,
    FlowControlMode,
    PartitionRebalanceImpact,
    PoisonMessageAssessment,
    PropagationStep,
    QueueBackpressureAnalyzer,
    QueueDependencyEdge,
    QueueEndpoint,
    QueuePlatform,
    RiskLevel,
    ScalingRecommendation,
    ThrottleImpact,
    ThrottleStrategy,
    TTLAnalysis,
    _clamp,
    _max_risk,
    _max_severity,
    _risk_from_ratio,
    _risk_to_severity,
    _severity_from_ratio,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(cid="c1", ctype=ComponentType.APP_SERVER):
    return Component(id=cid, name=cid, type=ctype)


def _graph(*comps):
    from faultray.model.graph import InfraGraph

    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _queue(
    queue_id="q1",
    component_id="c1",
    platform=QueuePlatform.KAFKA,
    partitions=6,
    consumers=3,
    producer_rate=100.0,
    consumer_rate=120.0,
    current_depth=0,
    max_depth=100_000,
    message_ttl=0.0,
    dlq_enabled=True,
    dlq_depth=0,
    dlq_max=10_000,
    retry_max=3,
    is_healthy=True,
) -> QueueEndpoint:
    return QueueEndpoint(
        queue_id=queue_id,
        component_id=component_id,
        platform=platform,
        partitions=partitions,
        consumers=consumers,
        producer_rate_msg_sec=producer_rate,
        consumer_rate_msg_sec=consumer_rate,
        current_depth=current_depth,
        max_depth=max_depth,
        message_ttl_seconds=message_ttl,
        dlq_enabled=dlq_enabled,
        dlq_current_depth=dlq_depth,
        dlq_max_depth=dlq_max,
        retry_max=retry_max,
        is_healthy=is_healthy,
    )


_TS_BASE = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Test: Enums and helpers
# ---------------------------------------------------------------------------


class TestEnumsAndHelpers:
    """Verify enum values and utility functions."""

    def test_queue_platform_values(self):
        assert QueuePlatform.KAFKA.value == "kafka"
        assert QueuePlatform.RABBITMQ.value == "rabbitmq"
        assert QueuePlatform.SQS.value == "sqs"
        assert QueuePlatform.REDIS_STREAMS.value == "redis_streams"
        assert QueuePlatform.NATS_JETSTREAM.value == "nats_jetstream"

    def test_backpressure_severity_values(self):
        assert BackpressureSeverity.NONE.value == "none"
        assert BackpressureSeverity.LOW.value == "low"
        assert BackpressureSeverity.CRITICAL.value == "critical"

    def test_throttle_strategy_values(self):
        assert ThrottleStrategy.NONE.value == "none"
        assert ThrottleStrategy.ADAPTIVE.value == "adaptive"
        assert ThrottleStrategy.BLOCK.value == "block"
        assert ThrottleStrategy.DROP_OLDEST.value == "drop_oldest"
        assert ThrottleStrategy.DROP_NEWEST.value == "drop_newest"
        assert ThrottleStrategy.RATE_LIMIT.value == "rate_limit"

    def test_flow_control_mode_values(self):
        assert FlowControlMode.CREDIT_BASED.value == "credit_based"
        assert FlowControlMode.WINDOW_BASED.value == "window_based"
        assert FlowControlMode.TOKEN_BUCKET.value == "token_bucket"
        assert FlowControlMode.BACKOFF.value == "backoff"

    def test_circuit_state_values(self):
        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.OPEN.value == "open"
        assert CircuitState.HALF_OPEN.value == "half_open"

    def test_risk_level_values(self):
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_clamp(self):
        assert _clamp(50.0) == 50.0
        assert _clamp(-10.0) == 0.0
        assert _clamp(200.0) == 100.0
        assert _clamp(5.0, 10.0, 20.0) == 10.0

    def test_severity_from_ratio(self):
        assert _severity_from_ratio(0.0) == BackpressureSeverity.NONE
        assert _severity_from_ratio(0.1) == BackpressureSeverity.LOW
        assert _severity_from_ratio(0.5) == BackpressureSeverity.MEDIUM
        assert _severity_from_ratio(0.75) == BackpressureSeverity.HIGH
        assert _severity_from_ratio(0.95) == BackpressureSeverity.CRITICAL

    def test_risk_from_ratio(self):
        assert _risk_from_ratio(0.1) == RiskLevel.LOW
        assert _risk_from_ratio(0.5) == RiskLevel.MEDIUM
        assert _risk_from_ratio(0.75) == RiskLevel.HIGH
        assert _risk_from_ratio(0.95) == RiskLevel.CRITICAL

    def test_max_severity(self):
        assert _max_severity() == BackpressureSeverity.NONE
        assert _max_severity(BackpressureSeverity.LOW, BackpressureSeverity.HIGH) == BackpressureSeverity.HIGH
        assert _max_severity(BackpressureSeverity.CRITICAL) == BackpressureSeverity.CRITICAL

    def test_max_risk(self):
        assert _max_risk() == RiskLevel.LOW
        assert _max_risk(RiskLevel.MEDIUM, RiskLevel.HIGH) == RiskLevel.HIGH

    def test_risk_to_severity(self):
        assert _risk_to_severity(RiskLevel.LOW) == BackpressureSeverity.LOW
        assert _risk_to_severity(RiskLevel.CRITICAL) == BackpressureSeverity.CRITICAL


# ---------------------------------------------------------------------------
# Test: Consumer Lag Analysis
# ---------------------------------------------------------------------------


class TestConsumerLagAnalysis:
    """Verify consumer lag analysis and growth rate prediction."""

    def test_lag_no_growth_healthy_queue(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(producer_rate=100.0, consumer_rate=120.0, consumers=1, current_depth=0)
        result = analyzer.analyze_consumer_lag(q)
        assert result.queue_id == "q1"
        assert result.is_growing is False
        assert result.lag_growth_rate_per_sec == 0.0
        assert result.severity == BackpressureSeverity.NONE

    def test_lag_growing_when_producer_exceeds_consumer(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(producer_rate=500.0, consumer_rate=100.0, consumers=1, current_depth=50000, max_depth=100000)
        result = analyzer.analyze_consumer_lag(q)
        assert result.is_growing is True
        assert result.lag_growth_rate_per_sec > 0
        assert result.estimated_drain_time_sec == float("inf")
        assert result.severity == BackpressureSeverity.MEDIUM

    def test_lag_from_snapshots_growing(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(current_depth=1000, max_depth=100000)
        snapshots = [
            ConsumerLagSnapshot(queue_id="q1", timestamp=_TS_BASE, lag_messages=100, consumer_count=3),
            ConsumerLagSnapshot(
                queue_id="q1",
                timestamp=_TS_BASE + timedelta(seconds=60),
                lag_messages=400,
                consumer_count=3,
            ),
        ]
        result = analyzer.analyze_consumer_lag(q, snapshots=snapshots)
        assert result.is_growing is True
        assert result.current_lag == 400
        assert result.lag_growth_rate_per_sec > 0

    def test_lag_from_snapshots_shrinking(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(current_depth=500, consumer_rate=200.0, consumers=2, producer_rate=50.0)
        snapshots = [
            ConsumerLagSnapshot(queue_id="q1", timestamp=_TS_BASE, lag_messages=500, consumer_count=2),
            ConsumerLagSnapshot(
                queue_id="q1",
                timestamp=_TS_BASE + timedelta(seconds=100),
                lag_messages=200,
                consumer_count=2,
            ),
        ]
        result = analyzer.analyze_consumer_lag(q, snapshots=snapshots)
        assert result.is_growing is False

    def test_lag_high_depth_recommendations(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(
            current_depth=85000,
            max_depth=100000,
            producer_rate=100.0,
            consumer_rate=120.0,
            consumers=1,
            partitions=6,
        )
        result = analyzer.analyze_consumer_lag(q)
        assert result.severity in (BackpressureSeverity.HIGH, BackpressureSeverity.CRITICAL)
        assert any("70%" in r for r in result.recommendations)

    def test_lag_consumers_lt_partitions_recommendation(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(partitions=12, consumers=3, current_depth=0, producer_rate=50, consumer_rate=120)
        result = analyzer.analyze_consumer_lag(q)
        assert any("partitions" in r for r in result.recommendations)

    def test_lag_drain_time_calculation(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(producer_rate=50.0, consumer_rate=100.0, consumers=1, current_depth=5000, max_depth=100000)
        result = analyzer.analyze_consumer_lag(q)
        assert result.is_growing is False
        assert result.estimated_drain_time_sec > 0
        assert math.isfinite(result.estimated_drain_time_sec)


# ---------------------------------------------------------------------------
# Test: DLQ Risk Assessment
# ---------------------------------------------------------------------------


class TestDLQRiskAssessment:
    """Verify dead letter queue overflow risk assessment."""

    def test_dlq_disabled(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(dlq_enabled=False)
        result = analyzer.assess_dlq_risk(q)
        assert result.dlq_enabled is False
        assert result.risk_level == RiskLevel.HIGH
        assert any("disabled" in r.lower() for r in result.recommendations)

    def test_dlq_healthy(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(dlq_enabled=True, dlq_depth=100, dlq_max=10000)
        result = analyzer.assess_dlq_risk(q)
        assert result.fill_ratio < 0.1
        assert result.risk_level == RiskLevel.LOW

    def test_dlq_nearly_full(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(dlq_enabled=True, dlq_depth=9500, dlq_max=10000)
        result = analyzer.assess_dlq_risk(q)
        assert result.fill_ratio > 0.9
        assert result.risk_level == RiskLevel.CRITICAL
        assert any("50%" in r for r in result.recommendations)
        assert any("nearing" in r.lower() for r in result.recommendations)

    def test_dlq_overflow_already(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(dlq_enabled=True, dlq_depth=10000, dlq_max=10000)
        result = analyzer.assess_dlq_risk(q)
        assert result.estimated_overflow_minutes == 0.0
        assert result.risk_level == RiskLevel.CRITICAL

    def test_dlq_small_max_depth_recommendation(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(dlq_enabled=True, dlq_depth=0, dlq_max=500)
        result = analyzer.assess_dlq_risk(q)
        assert any("low" in r.lower() for r in result.recommendations)


# ---------------------------------------------------------------------------
# Test: Partition Rebalance Impact
# ---------------------------------------------------------------------------


class TestPartitionRebalanceImpact:
    """Verify partition rebalancing impact during consumer failures."""

    def test_kafka_rebalance_single_consumer_failure(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(platform=QueuePlatform.KAFKA, partitions=6, consumers=3)
        result = analyzer.assess_rebalance_impact(q, failing_consumers=1)
        assert result.partitions_affected == 6
        assert result.estimated_downtime_seconds > 0
        assert result.ordering_disrupted is True

    def test_rabbitmq_rebalance_single_failure(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(platform=QueuePlatform.RABBITMQ, partitions=1, consumers=3)
        result = analyzer.assess_rebalance_impact(q, failing_consumers=1)
        assert result.partitions_affected == 0  # non-partitioned, survivors remain
        assert result.ordering_disrupted is False

    def test_all_consumers_fail(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(platform=QueuePlatform.KAFKA, partitions=6, consumers=2)
        result = analyzer.assess_rebalance_impact(q, failing_consumers=2)
        assert result.estimated_downtime_seconds >= 60.0
        assert any("All consumers" in r for r in result.recommendations)

    def test_single_consumer_spof_recommendation(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(platform=QueuePlatform.SQS, consumers=1)
        result = analyzer.assess_rebalance_impact(q, failing_consumers=1)
        assert any("SPOF" in r for r in result.recommendations)

    def test_sqs_no_partition_rebalance_with_survivors(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(platform=QueuePlatform.SQS, consumers=4)
        result = analyzer.assess_rebalance_impact(q, failing_consumers=1)
        # SQS is not partitioned; surviving consumers keep going
        assert result.partitions_affected == 0


# ---------------------------------------------------------------------------
# Test: Producer Throttling
# ---------------------------------------------------------------------------


class TestThrottleStrategy:
    """Verify producer throttling strategy impact evaluation."""

    def test_no_throttle_high_depth(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(current_depth=90000, max_depth=100000)
        result = analyzer.evaluate_throttle_strategy(q, ThrottleStrategy.NONE)
        assert result.upstream_impact_score == 80.0

    def test_no_throttle_low_depth(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(current_depth=0, max_depth=100000)
        result = analyzer.evaluate_throttle_strategy(q, ThrottleStrategy.NONE)
        assert result.upstream_impact_score == 0.0

    def test_block_strategy(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(current_depth=50000, max_depth=100000)
        result = analyzer.evaluate_throttle_strategy(q, ThrottleStrategy.BLOCK)
        assert result.latency_increase_factor > 1.0
        assert result.message_loss_risk is False

    def test_drop_oldest_strategy(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue()
        result = analyzer.evaluate_throttle_strategy(q, ThrottleStrategy.DROP_OLDEST)
        assert result.message_loss_risk is True

    def test_drop_newest_strategy(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue()
        result = analyzer.evaluate_throttle_strategy(q, ThrottleStrategy.DROP_NEWEST)
        assert result.message_loss_risk is True
        assert result.upstream_impact_score == 30.0

    def test_rate_limit_strategy(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(current_depth=50000, max_depth=100000)
        result = analyzer.evaluate_throttle_strategy(q, ThrottleStrategy.RATE_LIMIT)
        assert result.latency_increase_factor > 1.0
        assert result.message_loss_risk is False

    def test_adaptive_strategy(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(current_depth=50000, max_depth=100000)
        result = analyzer.evaluate_throttle_strategy(q, ThrottleStrategy.ADAPTIVE)
        assert result.latency_increase_factor > 1.0
        assert any("Adaptive" in r for r in result.recommendations)


# ---------------------------------------------------------------------------
# Test: TTL Analysis
# ---------------------------------------------------------------------------


class TestTTLAnalysis:
    """Verify message TTL and expiration policy analysis."""

    def test_no_ttl(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(message_ttl=0.0)
        result = analyzer.analyze_ttl(q)
        assert result.ttl_seconds == 0.0
        assert result.data_loss_risk is False
        assert any("indefinitely" in r for r in result.recommendations)

    def test_ttl_with_growing_lag(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        # Producer outpaces consumer, depth exceeds what can be consumed in TTL
        q = _queue(
            message_ttl=30.0,
            producer_rate=500.0,
            consumer_rate=100.0,
            consumers=1,
            current_depth=50000,
        )
        result = analyzer.analyze_ttl(q)
        assert result.data_loss_risk is True
        assert result.messages_expiring_per_minute > 0
        assert result.risk_level != RiskLevel.LOW

    def test_ttl_very_short(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(message_ttl=10.0, producer_rate=50.0, consumer_rate=100.0, consumers=1, current_depth=0)
        result = analyzer.analyze_ttl(q)
        assert any("short" in r.lower() for r in result.recommendations)

    def test_ttl_no_data_loss_consumers_keep_up(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(message_ttl=3600.0, producer_rate=50.0, consumer_rate=100.0, consumers=2, current_depth=0)
        result = analyzer.analyze_ttl(q)
        assert result.data_loss_risk is False
        assert result.risk_level == RiskLevel.LOW

    def test_ttl_no_dlq_with_expiration(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(
            message_ttl=20.0,
            producer_rate=500.0,
            consumer_rate=50.0,
            consumers=1,
            current_depth=50000,
            dlq_enabled=False,
        )
        result = analyzer.analyze_ttl(q)
        assert result.data_loss_risk is True
        assert any("DLQ" in r for r in result.recommendations)


# ---------------------------------------------------------------------------
# Test: Depth vs Latency Correlation
# ---------------------------------------------------------------------------


class TestDepthLatencyCorrelation:
    """Verify queue depth vs processing latency correlation."""

    def test_empty_queue(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(current_depth=0, max_depth=100000)
        result = analyzer.correlate_depth_latency(q, base_latency_ms=5.0)
        assert result.estimated_latency_ms == 5.0
        assert result.depth_utilization_pct == 0.0
        assert result.severity == BackpressureSeverity.NONE

    def test_half_full_queue(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        # Use depth just above 50% to trigger the recommendation
        q = _queue(current_depth=51000, max_depth=100000)
        result = analyzer.correlate_depth_latency(q, base_latency_ms=5.0)
        assert result.estimated_latency_ms > 5.0
        assert result.depth_utilization_pct > 50.0
        assert result.severity == BackpressureSeverity.MEDIUM
        assert any("50%" in r for r in result.recommendations)

    def test_full_queue_latency(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(current_depth=95000, max_depth=100000)
        result = analyzer.correlate_depth_latency(q)
        assert result.severity == BackpressureSeverity.CRITICAL
        assert any("80%" in r for r in result.recommendations)

    def test_latency_at_max_depth(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(current_depth=100000, max_depth=100000)
        result = analyzer.correlate_depth_latency(q, base_latency_ms=10.0)
        # At max depth, estimated latency should equal latency_at_max_depth_ms
        assert abs(result.estimated_latency_ms - result.latency_at_max_depth_ms) < 0.01


# ---------------------------------------------------------------------------
# Test: Consumer Group Scaling
# ---------------------------------------------------------------------------


class TestScalingRecommendation:
    """Verify consumer group scaling recommendations."""

    def test_scaling_needed_kafka(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(
            platform=QueuePlatform.KAFKA,
            partitions=12,
            consumers=2,
            producer_rate=1000.0,
            consumer_rate=100.0,
        )
        result = analyzer.recommend_scaling(q)
        assert result.recommended_consumers > result.current_consumers
        assert result.recommended_consumers <= result.max_useful_consumers
        assert result.estimated_drain_improvement_pct > 0

    def test_scaling_optimal(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(
            platform=QueuePlatform.KAFKA,
            partitions=6,
            consumers=6,
            producer_rate=100.0,
            consumer_rate=100.0,
        )
        result = analyzer.recommend_scaling(q)
        # With 20% headroom, might suggest 2 consumers; but max is partition count
        assert result.recommended_consumers >= 1

    def test_scaling_over_provisioned(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(
            platform=QueuePlatform.RABBITMQ,
            partitions=1,
            consumers=16,
            producer_rate=10.0,
            consumer_rate=100.0,
        )
        result = analyzer.recommend_scaling(q)
        assert result.recommended_consumers < result.current_consumers
        assert "scaling down" in result.reason.lower()

    def test_scaling_max_useful_kafka(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(
            platform=QueuePlatform.KAFKA,
            partitions=3,
            consumers=1,
            producer_rate=10000.0,
            consumer_rate=50.0,
        )
        result = analyzer.recommend_scaling(q)
        # Kafka max useful = partitions
        assert result.max_useful_consumers == 3
        assert result.recommended_consumers <= 3

    def test_scaling_zero_consumer_rate(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(consumer_rate=0.0, consumers=1)
        result = analyzer.recommend_scaling(q)
        # Should not crash; falls back to current consumer count
        assert result.recommended_consumers >= 1


# ---------------------------------------------------------------------------
# Test: Poison Message Detection
# ---------------------------------------------------------------------------


class TestPoisonMessageAssessment:
    """Verify poison message detection and circuit breaking."""

    def test_no_failures(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue()
        result = analyzer.assess_poison_messages(q, failed_delivery_count=0)
        assert result.circuit_state == CircuitState.CLOSED
        assert result.consumer_stall_risk is False
        assert result.estimated_block_duration_sec == 0.0

    def test_some_failures_half_open(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(retry_max=5)
        result = analyzer.assess_poison_messages(q, failed_delivery_count=2)
        assert result.circuit_state == CircuitState.HALF_OPEN
        assert result.estimated_block_duration_sec > 0

    def test_max_failures_circuit_open(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(retry_max=3)
        result = analyzer.assess_poison_messages(q, failed_delivery_count=3)
        assert result.circuit_state == CircuitState.OPEN
        assert any("OPEN" in r for r in result.recommendations)

    def test_poison_no_dlq_stall_risk(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(dlq_enabled=False)
        result = analyzer.assess_poison_messages(q, failed_delivery_count=1)
        assert result.consumer_stall_risk is True
        assert any("DLQ" in r for r in result.recommendations)

    def test_poison_high_retry_max(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(retry_max=10)
        result = analyzer.assess_poison_messages(q, failed_delivery_count=5)
        assert any("retry max" in r.lower() for r in result.recommendations)


# ---------------------------------------------------------------------------
# Test: Flow Control Evaluation
# ---------------------------------------------------------------------------


class TestFlowControlAssessment:
    """Verify flow control mechanism evaluation."""

    def test_kafka_backoff_flow_control(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(platform=QueuePlatform.KAFKA, current_depth=0)
        result = analyzer.evaluate_flow_control(q)
        assert result.mode == FlowControlMode.BACKOFF
        assert result.effectiveness_score > 0

    def test_rabbitmq_credit_based(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(platform=QueuePlatform.RABBITMQ, current_depth=0)
        result = analyzer.evaluate_flow_control(q)
        assert result.mode == FlowControlMode.CREDIT_BASED
        assert result.effectiveness_score > 70

    def test_sqs_no_flow_control(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(platform=QueuePlatform.SQS, current_depth=0)
        result = analyzer.evaluate_flow_control(q)
        assert result.mode == FlowControlMode.NONE
        assert result.effectiveness_score < 20

    def test_nats_window_based(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(platform=QueuePlatform.NATS_JETSTREAM, current_depth=0)
        result = analyzer.evaluate_flow_control(q)
        assert result.mode == FlowControlMode.WINDOW_BASED

    def test_high_depth_reduces_effectiveness(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(platform=QueuePlatform.RABBITMQ, current_depth=90000, max_depth=100000)
        result = analyzer.evaluate_flow_control(q)
        # Effectiveness should be reduced at high depth
        assert result.effectiveness_score < 85.0
        assert any("reduced" in r.lower() for r in result.recommendations)

    def test_redis_streams_flow_control(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(platform=QueuePlatform.REDIS_STREAMS, current_depth=0)
        result = analyzer.evaluate_flow_control(q)
        assert result.mode == FlowControlMode.BACKOFF


# ---------------------------------------------------------------------------
# Test: Multi-Queue Backpressure Propagation
# ---------------------------------------------------------------------------


class TestBackpressurePropagation:
    """Verify multi-queue dependency chain backpressure propagation."""

    def test_single_queue_no_chain(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(queue_id="q1", current_depth=50000, max_depth=100000)
        analyzer.add_queue(q)
        result = analyzer.analyze_propagation("q1")
        assert result.total_queues_affected == 1
        assert len(result.chain) == 1

    def test_queue_not_found(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        result = analyzer.analyze_propagation("nonexistent")
        assert result.total_queues_affected == 0
        assert any("not found" in r.lower() for r in result.recommendations)

    def test_chain_propagation(self):
        g = _graph(
            _comp("c1", ComponentType.QUEUE),
            _comp("c2", ComponentType.QUEUE),
            _comp("c3", ComponentType.QUEUE),
        )
        analyzer = QueueBackpressureAnalyzer(g)
        q1 = _queue(queue_id="q1", component_id="c1", current_depth=80000, max_depth=100000)
        q2 = _queue(queue_id="q2", component_id="c2", current_depth=30000, max_depth=100000)
        q3 = _queue(queue_id="q3", component_id="c3", current_depth=10000, max_depth=100000)
        analyzer.add_queue(q1)
        analyzer.add_queue(q2)
        analyzer.add_queue(q3)
        analyzer.add_dependency(QueueDependencyEdge(source_queue_id="q1", target_queue_id="q2"))
        analyzer.add_dependency(QueueDependencyEdge(source_queue_id="q2", target_queue_id="q3"))

        result = analyzer.analyze_propagation("q1")
        assert result.total_queues_affected == 3
        assert len(result.chain) == 3
        assert result.chain[0].queue_id == "q1"

    def test_long_chain_recommendations(self):
        g = _graph()
        analyzer = QueueBackpressureAnalyzer(g)
        ids = [f"q{i}" for i in range(5)]
        for qid in ids:
            comp = _comp(qid, ComponentType.QUEUE)
            g.add_component(comp)
            analyzer.add_queue(
                _queue(queue_id=qid, component_id=qid, current_depth=70000, max_depth=100000)
            )
        for i in range(len(ids) - 1):
            analyzer.add_dependency(
                QueueDependencyEdge(source_queue_id=ids[i], target_queue_id=ids[i + 1])
            )

        result = analyzer.analyze_propagation("q0")
        assert result.total_queues_affected >= 4
        assert any("chain" in r.lower() for r in result.recommendations)

    def test_propagation_no_cycle(self):
        """Ensure visited-tracking prevents infinite loops on a cycle."""
        g = _graph(
            _comp("c1", ComponentType.QUEUE),
            _comp("c2", ComponentType.QUEUE),
        )
        analyzer = QueueBackpressureAnalyzer(g)
        q1 = _queue(queue_id="q1", component_id="c1", current_depth=50000, max_depth=100000)
        q2 = _queue(queue_id="q2", component_id="c2", current_depth=50000, max_depth=100000)
        analyzer.add_queue(q1)
        analyzer.add_queue(q2)
        # Create a cycle
        analyzer.add_dependency(QueueDependencyEdge(source_queue_id="q1", target_queue_id="q2"))
        analyzer.add_dependency(QueueDependencyEdge(source_queue_id="q2", target_queue_id="q1"))

        result = analyzer.analyze_propagation("q1")
        assert result.total_queues_affected == 2  # both visited but no infinite loop


# ---------------------------------------------------------------------------
# Test: Comprehensive Report
# ---------------------------------------------------------------------------


class TestBackpressureReport:
    """Verify comprehensive report generation."""

    def test_empty_report(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        report = analyzer.generate_report()
        assert report.queues_analyzed == 0
        assert report.overall_risk == RiskLevel.LOW
        assert len(report.summary) >= 1

    def test_single_queue_report(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(current_depth=5000, max_depth=100000, dlq_depth=100, dlq_max=10000)
        analyzer.add_queue(q)
        report = analyzer.generate_report()
        assert report.queues_analyzed == 1
        assert len(report.consumer_lag_analyses) == 1
        assert len(report.dlq_assessments) == 1
        assert len(report.rebalance_impacts) == 1
        assert len(report.throttle_impacts) == 1
        assert len(report.ttl_analyses) == 1
        assert len(report.depth_latency_correlations) == 1
        assert len(report.scaling_recommendations) == 1
        assert len(report.poison_assessments) == 1
        assert len(report.flow_control_assessments) == 1
        assert len(report.propagation_results) == 1
        assert report.timestamp is not None

    def test_multi_queue_high_risk_report(self):
        g = _graph(
            _comp("c1", ComponentType.QUEUE),
            _comp("c2", ComponentType.QUEUE),
        )
        analyzer = QueueBackpressureAnalyzer(g)
        # Queue 1: high lag, DLQ nearly full
        q1 = _queue(
            queue_id="q1",
            component_id="c1",
            current_depth=95000,
            max_depth=100000,
            dlq_depth=9500,
            dlq_max=10000,
            producer_rate=500.0,
            consumer_rate=100.0,
            consumers=1,
        )
        # Queue 2: growing lag
        q2 = _queue(
            queue_id="q2",
            component_id="c2",
            current_depth=80000,
            max_depth=100000,
            producer_rate=300.0,
            consumer_rate=50.0,
            consumers=1,
        )
        analyzer.add_queue(q1)
        analyzer.add_queue(q2)
        report = analyzer.generate_report()
        assert report.queues_analyzed == 2
        assert report.overall_risk in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        # Summary should mention growing lag and/or DLQ risk
        assert len(report.summary) > 0

    def test_report_with_custom_throttle_strategy(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(current_depth=50000, max_depth=100000)
        analyzer.add_queue(q)
        report = analyzer.generate_report(throttle_strategy=ThrottleStrategy.BLOCK)
        assert len(report.throttle_impacts) == 1
        assert report.throttle_impacts[0].strategy == ThrottleStrategy.BLOCK

    def test_report_healthy_queues(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(
            current_depth=100,
            max_depth=100000,
            producer_rate=50.0,
            consumer_rate=200.0,
            consumers=3,
        )
        analyzer.add_queue(q)
        report = analyzer.generate_report()
        assert report.overall_risk == RiskLevel.LOW
        assert any("normal" in s.lower() for s in report.summary)

    def test_report_scaling_needed_summary(self):
        g = _graph(_comp("c1", ComponentType.QUEUE))
        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(
            platform=QueuePlatform.RABBITMQ,
            producer_rate=1000.0,
            consumer_rate=100.0,
            consumers=1,
            partitions=1,
            current_depth=50000,
            max_depth=100000,
        )
        analyzer.add_queue(q)
        report = analyzer.generate_report()
        assert any("scaling" in s.lower() for s in report.summary)


# ---------------------------------------------------------------------------
# Test: Integration with InfraGraph
# ---------------------------------------------------------------------------


class TestInfraGraphIntegration:
    """Verify analyzer works correctly with InfraGraph components."""

    def test_analyzer_with_graph_components(self):
        lb = _comp("lb", ComponentType.LOAD_BALANCER)
        api = _comp("api", ComponentType.APP_SERVER)
        queue_comp = _comp("mq", ComponentType.QUEUE)
        worker = _comp("worker", ComponentType.APP_SERVER)
        g = _graph(lb, api, queue_comp, worker)
        g.add_dependency(Dependency(source_id="lb", target_id="api"))
        g.add_dependency(Dependency(source_id="api", target_id="mq"))
        g.add_dependency(Dependency(source_id="mq", target_id="worker"))

        analyzer = QueueBackpressureAnalyzer(g)
        q = _queue(queue_id="mq-topic", component_id="mq")
        analyzer.add_queue(q)

        report = analyzer.generate_report()
        assert report.queues_analyzed == 1
        # Verify graph is accessible
        assert g.get_component("mq") is not None
        assert len(g.get_dependents("mq")) == 1  # api depends on mq

    def test_analyzer_with_dependency_edge(self):
        g = _graph(
            _comp("c1", ComponentType.QUEUE),
            _comp("c2", ComponentType.QUEUE),
        )
        g.add_dependency(Dependency(source_id="c1", target_id="c2"))

        analyzer = QueueBackpressureAnalyzer(g)
        q1 = _queue(queue_id="ingest", component_id="c1", current_depth=60000, max_depth=100000)
        q2 = _queue(queue_id="process", component_id="c2", current_depth=20000, max_depth=100000)
        analyzer.add_queue(q1)
        analyzer.add_queue(q2)
        analyzer.add_dependency(QueueDependencyEdge(source_queue_id="ingest", target_queue_id="process"))

        prop = analyzer.analyze_propagation("ingest")
        assert prop.total_queues_affected == 2
