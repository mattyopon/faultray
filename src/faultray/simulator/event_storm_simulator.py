# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Event Storm Simulator.

Simulates event storms across distributed event bus / message streaming
platforms (Kafka, RabbitMQ, SQS, SNS, Pulsar, NATS, Redis Streams, Kinesis).
Analyses broadcast storms, retry amplification, dead-letter floods, consumer
lag cascades, partition rebalancing, schema-change storms, replay floods,
and fan-out explosions.
"""

from __future__ import annotations

import math
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class StormType(str, Enum):
    """Types of event storms."""

    BROADCAST_STORM = "broadcast_storm"
    RETRY_STORM = "retry_storm"
    DEAD_LETTER_FLOOD = "dead_letter_flood"
    CONSUMER_LAG_CASCADE = "consumer_lag_cascade"
    PARTITION_REBALANCE = "partition_rebalance"
    SCHEMA_CHANGE_STORM = "schema_change_storm"
    REPLAY_FLOOD = "replay_flood"
    FANOUT_EXPLOSION = "fanout_explosion"


class EventBusType(str, Enum):
    """Supported event bus / message streaming platforms."""

    KAFKA = "kafka"
    RABBITMQ = "rabbitmq"
    SQS = "sqs"
    SNS = "sns"
    PULSAR = "pulsar"
    NATS = "nats"
    REDIS_STREAMS = "redis_streams"
    KINESIS = "kinesis"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class StormConfig(BaseModel):
    """Configuration for an event storm simulation."""

    storm_type: StormType
    bus_type: EventBusType = EventBusType.KAFKA
    events_per_second: float = Field(default=1000.0, gt=0.0)
    duration_seconds: float = Field(default=60.0, ge=0.0)
    partitions: int = Field(default=3, ge=1)
    consumers: int = Field(default=3, ge=1)
    retry_multiplier: float = Field(default=3.0, ge=1.0)
    fanout_factor: float = Field(default=1.0, ge=1.0)
    failure_rate: float = Field(default=0.1, ge=0.0, le=1.0)
    incompatibility_rate: float = Field(default=0.0, ge=0.0, le=1.0)


class StormResult(BaseModel):
    """Result of an event storm simulation."""

    storm_type: StormType
    bus_type: EventBusType
    total_events: int = 0
    processed_events: int = 0
    dead_letter_events: int = 0
    peak_throughput: float = 0.0
    avg_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    consumer_utilization: float = Field(default=0.0, ge=0.0, le=100.0)
    degradation_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    is_overloaded: bool = False
    recommendations: list[str] = Field(default_factory=list)


class StormRisk(BaseModel):
    """A detected storm risk in the infrastructure graph."""

    component_id: str
    risk_type: str
    severity: float = Field(default=0.0, ge=0.0, le=1.0)
    description: str = ""
    mitigation: str = ""


class ConsumerCapacityReport(BaseModel):
    """Consumer capacity analysis report."""

    total_consumers: int = 0
    total_partitions: int = 0
    consumer_to_partition_ratio: float = 0.0
    estimated_max_throughput: float = 0.0
    headroom_percent: float = 0.0
    is_under_provisioned: bool = False
    is_over_provisioned: bool = False
    recommendations: list[str] = Field(default_factory=list)


class RebalanceResult(BaseModel):
    """Result of a partition rebalance simulation."""

    rebalance_duration_ms: float = 0.0
    partitions_moved: int = 0
    events_delayed: int = 0
    consumer_downtime_ms: float = 0.0
    ordering_violated: bool = False
    recommendations: list[str] = Field(default_factory=list)


class StormProtection(BaseModel):
    """A recommended storm protection measure."""

    protection_type: str
    description: str
    priority: float = Field(default=0.0, ge=0.0, le=1.0)
    estimated_risk_reduction: float = Field(default=0.0, ge=0.0, le=1.0)


class BackpressureResult(BaseModel):
    """Result of a backpressure response simulation."""

    applied_backpressure: bool = False
    throttle_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    events_dropped: int = 0
    events_delayed: int = 0
    producer_blocked: bool = False
    queue_depth: int = 0
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Bus-specific characteristics
# ---------------------------------------------------------------------------

_BUS_CHARACTERISTICS: dict[EventBusType, dict] = {
    EventBusType.KAFKA: {
        "throughput_per_partition": 10000.0,
        "rebalance_ms": 5000.0,
        "ordering": True,
        "dlq_native": False,
        "latency_base_ms": 5.0,
        "backpressure_capable": True,
    },
    EventBusType.RABBITMQ: {
        "throughput_per_partition": 20000.0,
        "rebalance_ms": 2000.0,
        "ordering": True,
        "dlq_native": True,
        "latency_base_ms": 2.0,
        "backpressure_capable": True,
    },
    EventBusType.SQS: {
        "throughput_per_partition": 3000.0,
        "rebalance_ms": 0.0,
        "ordering": False,
        "dlq_native": True,
        "latency_base_ms": 20.0,
        "backpressure_capable": False,
    },
    EventBusType.SNS: {
        "throughput_per_partition": 30000.0,
        "rebalance_ms": 0.0,
        "ordering": False,
        "dlq_native": True,
        "latency_base_ms": 15.0,
        "backpressure_capable": False,
    },
    EventBusType.PULSAR: {
        "throughput_per_partition": 15000.0,
        "rebalance_ms": 3000.0,
        "ordering": True,
        "dlq_native": True,
        "latency_base_ms": 4.0,
        "backpressure_capable": True,
    },
    EventBusType.NATS: {
        "throughput_per_partition": 50000.0,
        "rebalance_ms": 1000.0,
        "ordering": False,
        "dlq_native": False,
        "latency_base_ms": 1.0,
        "backpressure_capable": True,
    },
    EventBusType.REDIS_STREAMS: {
        "throughput_per_partition": 25000.0,
        "rebalance_ms": 1500.0,
        "ordering": True,
        "dlq_native": False,
        "latency_base_ms": 1.5,
        "backpressure_capable": True,
    },
    EventBusType.KINESIS: {
        "throughput_per_partition": 1000.0,
        "rebalance_ms": 10000.0,
        "ordering": True,
        "dlq_native": False,
        "latency_base_ms": 25.0,
        "backpressure_capable": False,
    },
}


# Storm severity weights
_STORM_SEVERITY: dict[StormType, float] = {
    StormType.BROADCAST_STORM: 0.7,
    StormType.RETRY_STORM: 0.8,
    StormType.DEAD_LETTER_FLOOD: 0.6,
    StormType.CONSUMER_LAG_CASCADE: 0.75,
    StormType.PARTITION_REBALANCE: 0.5,
    StormType.SCHEMA_CHANGE_STORM: 0.65,
    StormType.REPLAY_FLOOD: 0.55,
    StormType.FANOUT_EXPLOSION: 0.85,
}


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Simulator Engine
# ---------------------------------------------------------------------------


class EventStormSimulatorEngine:
    """Simulates event storms and assesses impact on event bus infrastructure."""

    def __init__(self, graph: InfraGraph | None = None) -> None:
        self._graph = graph or InfraGraph()

    # -- simulate_storm ----------------------------------------------------

    def simulate_storm(
        self, graph: InfraGraph, config: StormConfig
    ) -> StormResult:
        """Simulate an event storm and return the impact result."""
        bus = _BUS_CHARACTERISTICS[config.bus_type]
        base_tp: float = bus["throughput_per_partition"]
        if base_tp <= 0:
            base_tp = 1.0
        max_consumer_throughput = base_tp * config.partitions
        total_events = int(config.events_per_second * config.duration_seconds)
        severity = _STORM_SEVERITY.get(config.storm_type, 0.5)

        effective_eps = config.events_per_second
        failure_rate = config.failure_rate
        incompatibility_rate = config.incompatibility_rate

        # Storm-type specific adjustments
        if config.storm_type == StormType.BROADCAST_STORM:
            effective_eps *= config.fanout_factor
        elif config.storm_type == StormType.RETRY_STORM:
            effective_eps *= 1 + (config.retry_multiplier - 1) * failure_rate
        elif config.storm_type == StormType.DEAD_LETTER_FLOOD:
            pass  # failure_rate drives dead letter count
        elif config.storm_type == StormType.CONSUMER_LAG_CASCADE:
            effective_eps *= 1.0 + severity * 0.5
        elif config.storm_type == StormType.PARTITION_REBALANCE:
            max_consumer_throughput *= 0.7  # reduced during rebalance
        elif config.storm_type == StormType.SCHEMA_CHANGE_STORM:
            pass  # incompatibility_rate drives degradation
        elif config.storm_type == StormType.REPLAY_FLOOD:
            effective_eps *= 2.0
        elif config.storm_type == StormType.FANOUT_EXPLOSION:
            effective_eps *= config.fanout_factor

        is_overloaded = effective_eps > max_consumer_throughput
        utilization = _clamp((effective_eps / max_consumer_throughput) * 100.0)

        if is_overloaded:
            processed_events = int(max_consumer_throughput * config.duration_seconds)
        else:
            processed_events = total_events

        # Dead letter events
        if config.storm_type == StormType.DEAD_LETTER_FLOOD:
            dead_letter_events = int(total_events * failure_rate)
            processed_events = total_events - dead_letter_events
        elif config.storm_type == StormType.SCHEMA_CHANGE_STORM:
            dead_letter_events = int(total_events * incompatibility_rate)
            processed_events = total_events - dead_letter_events
        elif is_overloaded:
            overflow = total_events - processed_events
            dead_letter_events = overflow
        else:
            dead_letter_events = int(total_events * failure_rate * 0.1)

        # Latency
        latency_base = bus["latency_base_ms"]
        if is_overloaded:
            overload_factor = effective_eps / max_consumer_throughput
            avg_latency = latency_base * overload_factor
            max_latency = avg_latency * 5.0
        else:
            avg_latency = latency_base * (1.0 + utilization / 200.0)
            max_latency = avg_latency * 3.0

        # Degradation
        degradation = 0.0
        if is_overloaded:
            degradation = _clamp(
                (effective_eps - max_consumer_throughput)
                / max_consumer_throughput
                * 100.0
                * severity
            )
        if config.storm_type == StormType.DEAD_LETTER_FLOOD and failure_rate > 0:
            degradation = max(degradation, _clamp(failure_rate * 100.0 * severity))
        if config.storm_type == StormType.SCHEMA_CHANGE_STORM and incompatibility_rate > 0:
            degradation = max(degradation, _clamp(incompatibility_rate * 100.0 * severity))

        # Recommendations
        recommendations: list[str] = []
        if is_overloaded:
            recommendations.append("Increase partitions or consumers to handle peak load")
        if dead_letter_events > total_events * 0.1:
            recommendations.append("Investigate high dead letter rate")
        if not bus["dlq_native"]:
            recommendations.append(f"Configure DLQ for {config.bus_type.value}")
        if not bus["backpressure_capable"] and is_overloaded:
            recommendations.append("Implement client-side backpressure")
        if config.storm_type == StormType.RETRY_STORM:
            recommendations.append("Implement exponential backoff with jitter")
        if config.storm_type == StormType.FANOUT_EXPLOSION:
            recommendations.append("Limit fan-out factor or use topic filtering")
        if config.storm_type == StormType.SCHEMA_CHANGE_STORM:
            recommendations.append("Use schema registry with compatibility checks")

        peak_throughput = min(effective_eps, max_consumer_throughput)

        return StormResult(
            storm_type=config.storm_type,
            bus_type=config.bus_type,
            total_events=max(0, total_events),
            processed_events=max(0, processed_events),
            dead_letter_events=max(0, dead_letter_events),
            peak_throughput=round(peak_throughput, 2),
            avg_latency_ms=round(max(0.0, avg_latency), 2),
            max_latency_ms=round(max(0.0, max_latency), 2),
            consumer_utilization=round(utilization, 2),
            degradation_percent=round(degradation, 2),
            is_overloaded=is_overloaded,
            recommendations=recommendations,
        )

    # -- detect_storm_risks ------------------------------------------------

    def detect_storm_risks(self, graph: InfraGraph) -> list[StormRisk]:
        """Detect potential storm risks in the infrastructure graph."""
        risks: list[StormRisk] = []

        for comp_id, comp in graph.components.items():
            # Single consumer risk
            if comp.type == ComponentType.QUEUE and comp.replicas <= 1:
                risks.append(
                    StormRisk(
                        component_id=comp_id,
                        risk_type="single_consumer",
                        severity=0.7,
                        description=f"Queue '{comp_id}' has only {comp.replicas} replica(s)",
                        mitigation="Add consumer replicas for redundancy",
                    )
                )

            # High fan-out risk
            dependents = graph.get_dependents(comp_id)
            if len(dependents) > 3:
                risks.append(
                    StormRisk(
                        component_id=comp_id,
                        risk_type="high_fanout",
                        severity=min(1.0, len(dependents) / 10.0),
                        description=f"Component '{comp_id}' has {len(dependents)} dependents (fan-out risk)",
                        mitigation="Implement rate limiting or topic filtering",
                    )
                )

            # No circuit breaker on dependencies
            dependencies = graph.get_dependencies(comp_id)
            for dep_comp in dependencies:
                edge = graph.get_dependency_edge(comp_id, dep_comp.id)
                if edge and not edge.circuit_breaker.enabled:
                    risks.append(
                        StormRisk(
                            component_id=comp_id,
                            risk_type="no_circuit_breaker",
                            severity=0.6,
                            description=(
                                f"Dependency {comp_id} -> {dep_comp.id} "
                                "lacks circuit breaker"
                            ),
                            mitigation="Enable circuit breaker to prevent cascade failures",
                        )
                    )

        return risks

    # -- analyze_consumer_capacity -----------------------------------------

    def analyze_consumer_capacity(
        self, graph: InfraGraph, config: StormConfig
    ) -> ConsumerCapacityReport:
        """Analyse consumer capacity for the given storm config."""
        bus = _BUS_CHARACTERISTICS[config.bus_type]
        base_tp: float = bus["throughput_per_partition"]
        if base_tp <= 0:
            base_tp = 1.0
        max_throughput = base_tp * config.partitions

        ratio = config.consumers / config.partitions
        headroom = _clamp(
            ((max_throughput - config.events_per_second) / max_throughput) * 100.0
        )

        is_under = config.consumers < config.partitions
        is_over = config.consumers > config.partitions * 2

        recommendations: list[str] = []
        if is_under:
            recommendations.append(
                f"Scale consumers to at least {config.partitions} "
                f"(currently {config.consumers})"
            )
        if is_over:
            recommendations.append(
                "Reduce consumers; excess consumers are idle"
            )
        if headroom < 20.0:
            recommendations.append("Low headroom; consider adding partitions")
        if not recommendations:
            recommendations.append("Consumer capacity is well-provisioned")

        return ConsumerCapacityReport(
            total_consumers=config.consumers,
            total_partitions=config.partitions,
            consumer_to_partition_ratio=round(ratio, 2),
            estimated_max_throughput=round(max_throughput, 2),
            headroom_percent=round(headroom, 2),
            is_under_provisioned=is_under,
            is_over_provisioned=is_over,
            recommendations=recommendations,
        )

    # -- simulate_partition_rebalance --------------------------------------

    def simulate_partition_rebalance(
        self, graph: InfraGraph, config: StormConfig
    ) -> RebalanceResult:
        """Simulate a partition rebalance event."""
        bus = _BUS_CHARACTERISTICS[config.bus_type]
        rebalance_base_ms: float = bus["rebalance_ms"]
        ordering = bus["ordering"]

        # Duration scales with partitions
        rebalance_duration = rebalance_base_ms * math.log2(max(config.partitions, 2))

        # Partitions moved ~ half of total
        partitions_moved = max(1, config.partitions // 2)

        # Events delayed during rebalance
        events_delayed = int(
            config.events_per_second * (rebalance_duration / 1000.0)
        )

        # Consumer downtime
        consumer_downtime = rebalance_duration * 0.8

        # Ordering violated if ordering guaranteed and > 1 partition moved
        ordering_violated = ordering and partitions_moved > 1

        recommendations: list[str] = []
        if rebalance_duration > 10000:
            recommendations.append(
                "High rebalance time; use incremental rebalancing"
            )
        if ordering_violated:
            recommendations.append(
                "Enable sticky partition assignment to preserve ordering"
            )
        if config.partitions > config.consumers * 2:
            recommendations.append(
                "Too many partitions per consumer; scale consumers"
            )
        if not recommendations:
            recommendations.append("Rebalance parameters are acceptable")

        return RebalanceResult(
            rebalance_duration_ms=round(rebalance_duration, 2),
            partitions_moved=partitions_moved,
            events_delayed=max(0, events_delayed),
            consumer_downtime_ms=round(consumer_downtime, 2),
            ordering_violated=ordering_violated,
            recommendations=recommendations,
        )

    # -- recommend_storm_protection ----------------------------------------

    def recommend_storm_protection(
        self, graph: InfraGraph
    ) -> list[StormProtection]:
        """Recommend storm protection measures based on the graph."""
        protections: list[StormProtection] = []

        queue_components = [
            c for c in graph.components.values() if c.type == ComponentType.QUEUE
        ]
        all_edges = graph.all_dependency_edges()

        # Rate limiting
        protections.append(
            StormProtection(
                protection_type="rate_limiting",
                description="Apply rate limiting on producers to prevent burst storms",
                priority=0.9,
                estimated_risk_reduction=0.7,
            )
        )

        # Circuit breaker
        has_cb = any(e.circuit_breaker.enabled for e in all_edges) if all_edges else False
        if not has_cb:
            protections.append(
                StormProtection(
                    protection_type="circuit_breaker",
                    description="Enable circuit breakers on dependency edges",
                    priority=0.85,
                    estimated_risk_reduction=0.6,
                )
            )

        # DLQ
        protections.append(
            StormProtection(
                protection_type="dead_letter_queue",
                description="Configure dead letter queues for failed message handling",
                priority=0.8,
                estimated_risk_reduction=0.5,
            )
        )

        # Schema registry
        protections.append(
            StormProtection(
                protection_type="schema_registry",
                description="Use a schema registry with backward compatibility checks",
                priority=0.6,
                estimated_risk_reduction=0.4,
            )
        )

        # Consumer autoscaling
        for q in queue_components:
            if not q.autoscaling.enabled:
                protections.append(
                    StormProtection(
                        protection_type="consumer_autoscaling",
                        description=f"Enable autoscaling for consumers of '{q.id}'",
                        priority=0.75,
                        estimated_risk_reduction=0.55,
                    )
                )

        # Backpressure
        protections.append(
            StormProtection(
                protection_type="backpressure",
                description="Implement backpressure mechanisms on producers",
                priority=0.7,
                estimated_risk_reduction=0.45,
            )
        )

        return protections

    # -- estimate_recovery_time --------------------------------------------

    def estimate_recovery_time(
        self, graph: InfraGraph, config: StormConfig
    ) -> float:
        """Estimate recovery time in seconds after the storm subsides."""
        bus = _BUS_CHARACTERISTICS[config.bus_type]
        base_tp: float = bus["throughput_per_partition"]
        if base_tp <= 0:
            base_tp = 1.0
        max_throughput = base_tp * config.partitions

        config.events_per_second * config.duration_seconds
        effective_eps = config.events_per_second

        if config.storm_type == StormType.REPLAY_FLOOD:
            effective_eps *= 2.0
        elif config.storm_type == StormType.FANOUT_EXPLOSION:
            effective_eps *= config.fanout_factor
        elif config.storm_type == StormType.BROADCAST_STORM:
            effective_eps *= config.fanout_factor
        elif config.storm_type == StormType.RETRY_STORM:
            effective_eps *= 1 + (config.retry_multiplier - 1) * config.failure_rate

        if effective_eps <= max_throughput:
            return 0.0

        # Backlog accumulated during storm
        backlog = (effective_eps - max_throughput) * config.duration_seconds

        # Recovery rate = max_throughput (consumers drain at full speed)
        recovery_time = backlog / max_throughput

        # Add rebalance time if applicable
        if config.storm_type == StormType.PARTITION_REBALANCE:
            recovery_time += bus["rebalance_ms"] / 1000.0

        return round(max(0.0, recovery_time), 2)

    # -- simulate_backpressure_response ------------------------------------

    def simulate_backpressure_response(
        self, graph: InfraGraph, config: StormConfig
    ) -> BackpressureResult:
        """Simulate how the system handles backpressure during a storm."""
        bus = _BUS_CHARACTERISTICS[config.bus_type]
        base_tp: float = bus["throughput_per_partition"]
        if base_tp <= 0:
            base_tp = 1.0
        max_throughput = base_tp * config.partitions
        backpressure_capable: bool = bus["backpressure_capable"]

        effective_eps = config.events_per_second
        if config.storm_type == StormType.REPLAY_FLOOD:
            effective_eps *= 2.0
        elif config.storm_type == StormType.FANOUT_EXPLOSION:
            effective_eps *= config.fanout_factor
        elif config.storm_type == StormType.BROADCAST_STORM:
            effective_eps *= config.fanout_factor

        overloaded = effective_eps > max_throughput
        applied = overloaded and backpressure_capable

        throttle = 0.0
        events_dropped = 0
        events_delayed = 0
        producer_blocked = False
        queue_depth = 0
        recommendations: list[str] = []

        if overloaded:
            overflow_ratio = (effective_eps - max_throughput) / max_throughput

            if backpressure_capable:
                throttle = _clamp(overflow_ratio * 100.0)
                events_delayed = int(
                    (effective_eps - max_throughput)
                    * config.duration_seconds
                    * 0.7
                )
                events_dropped = int(
                    (effective_eps - max_throughput)
                    * config.duration_seconds
                    * 0.1
                )
                producer_blocked = overflow_ratio > 1.0
                queue_depth = int(
                    (effective_eps - max_throughput)
                    * min(config.duration_seconds, 10.0)
                )
                recommendations.append("Backpressure engaged; monitor producer latency")
            else:
                # No backpressure support -> messages dropped
                events_dropped = int(
                    (effective_eps - max_throughput) * config.duration_seconds
                )
                events_delayed = 0
                queue_depth = 0
                recommendations.append(
                    f"{config.bus_type.value} does not support native backpressure; "
                    "implement client-side throttling"
                )
        else:
            recommendations.append("System within capacity; no backpressure needed")

        return BackpressureResult(
            applied_backpressure=applied,
            throttle_percent=round(throttle, 2),
            events_dropped=max(0, events_dropped),
            events_delayed=max(0, events_delayed),
            producer_blocked=producer_blocked,
            queue_depth=max(0, queue_depth),
            recommendations=recommendations,
        )
