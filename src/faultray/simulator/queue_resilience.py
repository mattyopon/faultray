# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Queue/Event Stream Resilience Simulator.

Simulates failure modes specific to message queues and event streaming
systems (Kafka, SQS, RabbitMQ, Pub/Sub, etc.). Tests message ordering
guarantees, dead letter queue behavior, consumer lag, partition
rebalancing, and backpressure scenarios.
"""

from __future__ import annotations

import math
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class QueueType(str, Enum):
    """Supported message queue / event streaming platforms."""

    KAFKA = "kafka"
    SQS = "sqs"
    RABBITMQ = "rabbitmq"
    PUBSUB = "pubsub"
    KINESIS = "kinesis"
    SERVICE_BUS = "service_bus"
    NATS = "nats"
    REDIS_STREAMS = "redis_streams"


class QueueFailureMode(str, Enum):
    """Failure modes for queue/streaming systems."""

    CONSUMER_LAG = "consumer_lag"
    PARTITION_REBALANCE = "partition_rebalance"
    MESSAGE_ORDERING_LOSS = "message_ordering_loss"
    DEAD_LETTER_OVERFLOW = "dead_letter_overflow"
    BACKPRESSURE = "backpressure"
    DUPLICATE_DELIVERY = "duplicate_delivery"
    POISON_MESSAGE = "poison_message"
    BROKER_FAILURE = "broker_failure"
    RETENTION_EXPIRY = "retention_expiry"
    THROUGHPUT_THROTTLE = "throughput_throttle"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class QueueConfig(BaseModel):
    """Configuration for a queue / event stream."""

    queue_type: QueueType
    partitions: int = Field(default=1, ge=1)
    consumers: int = Field(default=1, ge=1)
    retention_hours: int = Field(default=168, ge=1)
    max_message_size_kb: int = Field(default=256, ge=1)
    dead_letter_enabled: bool = True
    ordering_guaranteed: bool = True
    deduplication_enabled: bool = False
    max_throughput_per_sec: int = Field(default=1000, ge=1)


class QueueFailureScenario(BaseModel):
    """A single failure scenario to simulate."""

    failure_mode: QueueFailureMode
    severity: float = Field(default=0.5, ge=0.0, le=1.0)
    duration_minutes: float = Field(default=10.0, ge=0.0)
    affected_partitions_percent: float = Field(default=100.0, ge=0.0, le=100.0)


class QueueImpact(BaseModel):
    """Impact assessment from a failure scenario."""

    scenario: QueueFailureScenario
    messages_at_risk: int = 0
    ordering_violated: bool = False
    data_loss_possible: bool = False
    consumer_recovery_minutes: float = 0.0
    estimated_message_delay_seconds: float = 0.0
    mitigation_actions: list[str] = Field(default_factory=list)


class QueueResilienceReport(BaseModel):
    """Full resilience report across multiple configs and scenarios."""

    queue_configs_tested: int = 0
    scenarios_run: int = 0
    critical_risks: int = 0
    impacts: list[QueueImpact] = Field(default_factory=list)
    overall_queue_resilience: float = Field(default=0.0, ge=0.0, le=100.0)
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Base impact weights per failure mode
# ---------------------------------------------------------------------------

_FAILURE_BASE_IMPACT: dict[QueueFailureMode, float] = {
    QueueFailureMode.CONSUMER_LAG: 35.0,
    QueueFailureMode.PARTITION_REBALANCE: 40.0,
    QueueFailureMode.MESSAGE_ORDERING_LOSS: 50.0,
    QueueFailureMode.DEAD_LETTER_OVERFLOW: 55.0,
    QueueFailureMode.BACKPRESSURE: 45.0,
    QueueFailureMode.DUPLICATE_DELIVERY: 30.0,
    QueueFailureMode.POISON_MESSAGE: 60.0,
    QueueFailureMode.BROKER_FAILURE: 80.0,
    QueueFailureMode.RETENTION_EXPIRY: 65.0,
    QueueFailureMode.THROUGHPUT_THROTTLE: 35.0,
}

# Default platform properties (ordering, DLQ support, partitioning)
_PLATFORM_DEFAULTS: dict[QueueType, dict[str, bool]] = {
    QueueType.KAFKA: {"ordered_by_default": True, "dlq_native": False, "partitioned": True},
    QueueType.SQS: {"ordered_by_default": False, "dlq_native": True, "partitioned": False},
    QueueType.RABBITMQ: {"ordered_by_default": True, "dlq_native": True, "partitioned": False},
    QueueType.PUBSUB: {"ordered_by_default": False, "dlq_native": True, "partitioned": False},
    QueueType.KINESIS: {"ordered_by_default": True, "dlq_native": False, "partitioned": True},
    QueueType.SERVICE_BUS: {"ordered_by_default": True, "dlq_native": True, "partitioned": True},
    QueueType.NATS: {"ordered_by_default": False, "dlq_native": False, "partitioned": False},
    QueueType.REDIS_STREAMS: {"ordered_by_default": True, "dlq_native": False, "partitioned": False},
}


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------


class QueueResilienceSimulator:
    """Simulates queue/event-stream failures and assesses resilience."""

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    # -- single failure simulation -----------------------------------------

    def simulate_failure(
        self,
        config: QueueConfig,
        scenario: QueueFailureScenario,
    ) -> QueueImpact:
        """Simulate a single failure scenario against a queue config."""
        mode = scenario.failure_mode
        severity = scenario.severity
        duration = scenario.duration_minutes
        affected_frac = scenario.affected_partitions_percent / 100.0

        messages_at_risk = 0
        ordering_violated = False
        data_loss_possible = False
        recovery_min = 0.0
        delay_sec = 0.0
        mitigations: list[str] = []

        throughput = config.max_throughput_per_sec
        duration_sec = duration * 60.0

        if mode == QueueFailureMode.CONSUMER_LAG:
            messages_at_risk = int(throughput * duration_sec * severity * affected_frac)
            delay_sec = duration_sec * severity
            recovery_min = duration * severity * (config.partitions / max(config.consumers, 1))
            mitigations.append("Scale up consumers to reduce lag")
            mitigations.append("Enable auto-scaling for consumer group")

        elif mode == QueueFailureMode.PARTITION_REBALANCE:
            ratio = config.partitions / max(config.consumers, 1)
            recovery_min = ratio * severity * 2.0
            messages_at_risk = int(throughput * recovery_min * 60 * affected_frac)
            delay_sec = recovery_min * 60.0
            ordering_violated = config.ordering_guaranteed
            mitigations.append("Use sticky partition assignment")
            mitigations.append("Minimize partition count relative to consumers")

        elif mode == QueueFailureMode.MESSAGE_ORDERING_LOSS:
            if config.ordering_guaranteed:
                ordering_violated = True
                messages_at_risk = int(throughput * duration_sec * severity * affected_frac)
                delay_sec = 0.0
                mitigations.append("Use single-partition topics for strict ordering")
                mitigations.append("Implement sequence numbers for client-side reordering")
            else:
                messages_at_risk = 0
                mitigations.append("Ordering not guaranteed; no impact on this queue")

        elif mode == QueueFailureMode.DEAD_LETTER_OVERFLOW:
            if config.dead_letter_enabled:
                messages_at_risk = int(throughput * duration_sec * severity * 0.1 * affected_frac)
                data_loss_possible = severity > 0.8
                mitigations.append("Monitor DLQ depth and set up alerts")
                mitigations.append("Implement DLQ consumer for reprocessing")
            else:
                messages_at_risk = int(throughput * duration_sec * severity * affected_frac)
                data_loss_possible = True
                mitigations.append("Enable dead letter queue to capture failed messages")
                mitigations.append("Implement retry policies with exponential backoff")

        elif mode == QueueFailureMode.BACKPRESSURE:
            messages_at_risk = int(throughput * duration_sec * severity * affected_frac)
            delay_sec = duration_sec * severity * 0.5
            recovery_min = duration * severity
            mitigations.append("Implement producer-side flow control")
            mitigations.append("Add buffer queues to absorb traffic spikes")

        elif mode == QueueFailureMode.DUPLICATE_DELIVERY:
            if config.deduplication_enabled:
                messages_at_risk = int(throughput * duration_sec * severity * 0.05 * affected_frac)
                mitigations.append("Deduplication is enabled; impact is minimal")
            else:
                messages_at_risk = int(throughput * duration_sec * severity * affected_frac)
                mitigations.append("Enable deduplication or implement idempotent consumers")
                mitigations.append("Use message IDs for client-side deduplication")

        elif mode == QueueFailureMode.POISON_MESSAGE:
            if config.dead_letter_enabled:
                messages_at_risk = 1
                recovery_min = 1.0 * severity
                mitigations.append("Poison message routed to DLQ; investigate and fix")
            else:
                messages_at_risk = int(throughput * duration_sec * severity * affected_frac)
                recovery_min = duration * severity * 2.0
                data_loss_possible = True
                mitigations.append("Enable DLQ to prevent poison message infinite loops")
                mitigations.append("Add message validation before processing")

        elif mode == QueueFailureMode.BROKER_FAILURE:
            affected_partitions = int(config.partitions * affected_frac)
            messages_at_risk = int(throughput * duration_sec * severity * affected_frac)
            data_loss_possible = severity > 0.5
            recovery_min = duration * severity * 1.5
            delay_sec = recovery_min * 60.0
            if affected_partitions >= config.partitions:
                data_loss_possible = True
            mitigations.append("Deploy multi-broker cluster with replication")
            mitigations.append("Configure minimum in-sync replicas")

        elif mode == QueueFailureMode.RETENTION_EXPIRY:
            hours_at_risk = config.retention_hours * severity
            messages_at_risk = int(throughput * hours_at_risk * 3600 * affected_frac)
            data_loss_possible = True
            mitigations.append("Increase retention period")
            mitigations.append("Archive messages to long-term storage before expiry")

        elif mode == QueueFailureMode.THROUGHPUT_THROTTLE:
            reduced_throughput = throughput * (1.0 - severity)
            excess = throughput - reduced_throughput
            messages_at_risk = int(excess * duration_sec * affected_frac)
            delay_sec = duration_sec * severity * 0.3
            recovery_min = 1.0 * severity
            mitigations.append("Request throughput quota increase")
            mitigations.append("Implement adaptive rate limiting on producers")

        return QueueImpact(
            scenario=scenario,
            messages_at_risk=max(0, messages_at_risk),
            ordering_violated=ordering_violated,
            data_loss_possible=data_loss_possible,
            consumer_recovery_minutes=round(max(0.0, recovery_min), 2),
            estimated_message_delay_seconds=round(max(0.0, delay_sec), 2),
            mitigation_actions=mitigations,
        )

    # -- health assessment -------------------------------------------------

    def assess_queue_health(self, config: QueueConfig) -> float:
        """Return a health score from 0 to 100 for the given queue config."""
        score = 100.0

        # Consumer-to-partition ratio
        ratio = config.consumers / max(config.partitions, 1)
        if ratio < 0.5:
            score -= 20.0
        elif ratio < 1.0:
            score -= 10.0

        # Dead letter queue
        if not config.dead_letter_enabled:
            score -= 15.0

        # Ordering without sufficient partitioning
        if config.ordering_guaranteed and config.partitions > 1:
            score -= 5.0

        # Deduplication
        if not config.deduplication_enabled:
            score -= 5.0

        # Retention too short
        if config.retention_hours < 24:
            score -= 10.0
        elif config.retention_hours < 72:
            score -= 5.0

        # Low throughput capacity
        if config.max_throughput_per_sec < 100:
            score -= 10.0

        # Single consumer
        if config.consumers <= 1:
            score -= 10.0

        return _clamp(score)

    # -- recommended config ------------------------------------------------

    def recommend_queue_config(
        self,
        queue_type: QueueType,
        throughput_required: int,
    ) -> QueueConfig:
        """Return an optimal QueueConfig for the given platform and throughput."""
        platform = _PLATFORM_DEFAULTS.get(queue_type, {})

        # Scale partitions based on throughput
        if throughput_required <= 1000:
            partitions = 3
        elif throughput_required <= 10000:
            partitions = 6
        elif throughput_required <= 100000:
            partitions = 12
        else:
            partitions = 24

        # Consumers ~= partitions for optimal parallelism
        consumers = partitions

        # Non-partitioned systems use 1 partition
        if not platform.get("partitioned", False):
            partitions = 1
            consumers = max(2, int(math.ceil(throughput_required / 5000)))

        return QueueConfig(
            queue_type=queue_type,
            partitions=partitions,
            consumers=consumers,
            retention_hours=168,
            max_message_size_kb=256,
            dead_letter_enabled=True,
            ordering_guaranteed=platform.get("ordered_by_default", False),
            deduplication_enabled=True,
            max_throughput_per_sec=max(throughput_required, 1),
        )

    # -- vulnerability finder ----------------------------------------------

    def find_queue_vulnerabilities(self, config: QueueConfig) -> list[str]:
        """Identify weaknesses in the given queue configuration."""
        vulns: list[str] = []

        if config.consumers < config.partitions:
            vulns.append(
                f"Under-provisioned consumers ({config.consumers}) for "
                f"partitions ({config.partitions}); messages will queue up"
            )

        if not config.dead_letter_enabled:
            vulns.append("Dead letter queue disabled; poison messages can block processing")

        if config.ordering_guaranteed and config.partitions > 1:
            vulns.append(
                "Ordering guaranteed with multiple partitions; "
                "cross-partition ordering cannot be enforced"
            )

        if not config.deduplication_enabled:
            vulns.append("Deduplication disabled; at-least-once delivery may cause duplicates")

        if config.retention_hours < 24:
            vulns.append(
                f"Retention period ({config.retention_hours}h) is very short; "
                "consumers offline for >1 day will lose messages"
            )

        if config.max_throughput_per_sec < 100:
            vulns.append(
                f"Low throughput limit ({config.max_throughput_per_sec}/s); "
                "traffic spikes will cause backpressure"
            )

        if config.consumers <= 1:
            vulns.append("Single consumer is a single point of failure")

        if config.max_message_size_kb > 1024:
            vulns.append(
                f"Large max message size ({config.max_message_size_kb}KB) "
                "may impact broker performance"
            )

        return vulns

    # -- full report -------------------------------------------------------

    def generate_report(
        self,
        configs: list[QueueConfig],
        scenarios: list[QueueFailureScenario],
    ) -> QueueResilienceReport:
        """Generate a comprehensive resilience report."""
        impacts: list[QueueImpact] = []
        for cfg in configs:
            for scenario in scenarios:
                impacts.append(self.simulate_failure(cfg, scenario))

        # Count critical risks: data loss or high messages at risk
        critical = 0
        for imp in impacts:
            if imp.data_loss_possible:
                critical += 1
            elif imp.messages_at_risk > 10000:
                critical += 1

        # Overall resilience: average health across configs
        if configs:
            health_scores = [self.assess_queue_health(cfg) for cfg in configs]
            avg_health = sum(health_scores) / len(health_scores)
        else:
            avg_health = 0.0

        # Impact penalty: reduce score based on severity of impacts
        if impacts:
            avg_messages = sum(i.messages_at_risk for i in impacts) / len(impacts)
            impact_penalty = min(30.0, avg_messages / 1000.0)
            avg_health = _clamp(avg_health - impact_penalty)

        # Recommendations
        recommendations: list[str] = []
        all_vulns: set[str] = set()
        for cfg in configs:
            for v in self.find_queue_vulnerabilities(cfg):
                all_vulns.add(v)
        recommendations.extend(sorted(all_vulns))

        if critical > 0:
            recommendations.insert(0, f"{critical} critical risk(s) detected; prioritize mitigation")

        return QueueResilienceReport(
            queue_configs_tested=len(configs),
            scenarios_run=len(impacts),
            critical_risks=critical,
            impacts=impacts,
            overall_queue_resilience=round(_clamp(avg_health), 1),
            recommendations=recommendations,
        )
