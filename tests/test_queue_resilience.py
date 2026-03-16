"""Tests for Queue/Event Stream Resilience Simulator.

130+ tests covering all queue types, failure modes, configurations,
edge cases, and report generation.
"""

from __future__ import annotations

import pytest

from faultray.model.graph import InfraGraph
from faultray.simulator.queue_resilience import (
    QueueConfig,
    QueueFailureMode,
    QueueFailureScenario,
    QueueImpact,
    QueueResilienceReport,
    QueueResilienceSimulator,
    QueueType,
    _FAILURE_BASE_IMPACT,
    _PLATFORM_DEFAULTS,
    _clamp,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def graph() -> InfraGraph:
    return InfraGraph()


@pytest.fixture
def sim(graph: InfraGraph) -> QueueResilienceSimulator:
    return QueueResilienceSimulator(graph)


@pytest.fixture
def default_config() -> QueueConfig:
    return QueueConfig(
        queue_type=QueueType.KAFKA,
        partitions=6,
        consumers=6,
        retention_hours=168,
        max_message_size_kb=256,
        dead_letter_enabled=True,
        ordering_guaranteed=True,
        deduplication_enabled=True,
        max_throughput_per_sec=10000,
    )


@pytest.fixture
def weak_config() -> QueueConfig:
    """A deliberately weak config to expose vulnerabilities."""
    return QueueConfig(
        queue_type=QueueType.SQS,
        partitions=4,
        consumers=1,
        retention_hours=12,
        max_message_size_kb=2048,
        dead_letter_enabled=False,
        ordering_guaranteed=True,
        deduplication_enabled=False,
        max_throughput_per_sec=50,
    )


def _make_scenario(
    mode: QueueFailureMode,
    severity: float = 0.5,
    duration_minutes: float = 10.0,
    affected_partitions_percent: float = 100.0,
) -> QueueFailureScenario:
    return QueueFailureScenario(
        failure_mode=mode,
        severity=severity,
        duration_minutes=duration_minutes,
        affected_partitions_percent=affected_partitions_percent,
    )


# ===========================================================================
# 1. Enum completeness
# ===========================================================================


class TestQueueTypeEnum:
    def test_all_queue_types_exist(self):
        expected = {"kafka", "sqs", "rabbitmq", "pubsub", "kinesis", "service_bus", "nats", "redis_streams"}
        assert {qt.value for qt in QueueType} == expected

    @pytest.mark.parametrize("qt", list(QueueType))
    def test_queue_type_is_str_enum(self, qt: QueueType):
        assert isinstance(qt.value, str)

    def test_queue_type_count(self):
        assert len(QueueType) == 8


class TestQueueFailureModeEnum:
    def test_all_failure_modes_exist(self):
        expected = {
            "consumer_lag", "partition_rebalance", "message_ordering_loss",
            "dead_letter_overflow", "backpressure", "duplicate_delivery",
            "poison_message", "broker_failure", "retention_expiry",
            "throughput_throttle",
        }
        assert {fm.value for fm in QueueFailureMode} == expected

    @pytest.mark.parametrize("fm", list(QueueFailureMode))
    def test_failure_mode_is_str_enum(self, fm: QueueFailureMode):
        assert isinstance(fm.value, str)

    def test_failure_mode_count(self):
        assert len(QueueFailureMode) == 10

    @pytest.mark.parametrize("fm", list(QueueFailureMode))
    def test_all_failure_modes_have_base_impact(self, fm: QueueFailureMode):
        assert fm in _FAILURE_BASE_IMPACT


# ===========================================================================
# 2. Pydantic model validation
# ===========================================================================


class TestQueueConfig:
    def test_defaults(self):
        cfg = QueueConfig(queue_type=QueueType.KAFKA)
        assert cfg.partitions == 1
        assert cfg.consumers == 1
        assert cfg.retention_hours == 168
        assert cfg.max_message_size_kb == 256
        assert cfg.dead_letter_enabled is True
        assert cfg.ordering_guaranteed is True
        assert cfg.deduplication_enabled is False
        assert cfg.max_throughput_per_sec == 1000

    def test_custom_values(self):
        cfg = QueueConfig(
            queue_type=QueueType.SQS,
            partitions=3,
            consumers=5,
            retention_hours=24,
            max_message_size_kb=512,
            dead_letter_enabled=False,
            ordering_guaranteed=False,
            deduplication_enabled=True,
            max_throughput_per_sec=5000,
        )
        assert cfg.queue_type == QueueType.SQS
        assert cfg.partitions == 3
        assert cfg.consumers == 5

    def test_partitions_min_validation(self):
        with pytest.raises(Exception):
            QueueConfig(queue_type=QueueType.KAFKA, partitions=0)

    def test_consumers_min_validation(self):
        with pytest.raises(Exception):
            QueueConfig(queue_type=QueueType.KAFKA, consumers=0)

    def test_retention_min_validation(self):
        with pytest.raises(Exception):
            QueueConfig(queue_type=QueueType.KAFKA, retention_hours=0)

    def test_throughput_min_validation(self):
        with pytest.raises(Exception):
            QueueConfig(queue_type=QueueType.KAFKA, max_throughput_per_sec=0)


class TestQueueFailureScenario:
    def test_defaults(self):
        s = QueueFailureScenario(failure_mode=QueueFailureMode.CONSUMER_LAG)
        assert s.severity == 0.5
        assert s.duration_minutes == 10.0
        assert s.affected_partitions_percent == 100.0

    def test_severity_bounds(self):
        s = QueueFailureScenario(failure_mode=QueueFailureMode.CONSUMER_LAG, severity=0.0)
        assert s.severity == 0.0
        s = QueueFailureScenario(failure_mode=QueueFailureMode.CONSUMER_LAG, severity=1.0)
        assert s.severity == 1.0

    def test_severity_out_of_range(self):
        with pytest.raises(Exception):
            QueueFailureScenario(failure_mode=QueueFailureMode.CONSUMER_LAG, severity=1.5)
        with pytest.raises(Exception):
            QueueFailureScenario(failure_mode=QueueFailureMode.CONSUMER_LAG, severity=-0.1)

    def test_affected_partitions_bounds(self):
        s = QueueFailureScenario(
            failure_mode=QueueFailureMode.CONSUMER_LAG,
            affected_partitions_percent=0.0,
        )
        assert s.affected_partitions_percent == 0.0

    def test_affected_partitions_out_of_range(self):
        with pytest.raises(Exception):
            QueueFailureScenario(
                failure_mode=QueueFailureMode.CONSUMER_LAG,
                affected_partitions_percent=101.0,
            )


class TestQueueImpactModel:
    def test_defaults(self):
        s = QueueFailureScenario(failure_mode=QueueFailureMode.CONSUMER_LAG)
        imp = QueueImpact(scenario=s)
        assert imp.messages_at_risk == 0
        assert imp.ordering_violated is False
        assert imp.data_loss_possible is False
        assert imp.consumer_recovery_minutes == 0.0
        assert imp.estimated_message_delay_seconds == 0.0
        assert imp.mitigation_actions == []


class TestQueueResilienceReportModel:
    def test_defaults(self):
        r = QueueResilienceReport()
        assert r.queue_configs_tested == 0
        assert r.scenarios_run == 0
        assert r.critical_risks == 0
        assert r.impacts == []
        assert r.overall_queue_resilience == 0.0
        assert r.recommendations == []


# ===========================================================================
# 3. _clamp utility
# ===========================================================================


class TestClamp:
    def test_within_range(self):
        assert _clamp(50.0) == 50.0

    def test_below_min(self):
        assert _clamp(-10.0) == 0.0

    def test_above_max(self):
        assert _clamp(150.0) == 100.0

    def test_at_boundaries(self):
        assert _clamp(0.0) == 0.0
        assert _clamp(100.0) == 100.0

    def test_custom_range(self):
        assert _clamp(5.0, 10.0, 20.0) == 10.0
        assert _clamp(25.0, 10.0, 20.0) == 20.0
        assert _clamp(15.0, 10.0, 20.0) == 15.0


# ===========================================================================
# 4. Platform defaults
# ===========================================================================


class TestPlatformDefaults:
    @pytest.mark.parametrize("qt", list(QueueType))
    def test_all_queue_types_have_defaults(self, qt: QueueType):
        assert qt in _PLATFORM_DEFAULTS

    @pytest.mark.parametrize("qt", list(QueueType))
    def test_defaults_have_required_keys(self, qt: QueueType):
        d = _PLATFORM_DEFAULTS[qt]
        assert "ordered_by_default" in d
        assert "dlq_native" in d
        assert "partitioned" in d

    def test_kafka_is_partitioned(self):
        assert _PLATFORM_DEFAULTS[QueueType.KAFKA]["partitioned"] is True

    def test_sqs_not_ordered_by_default(self):
        assert _PLATFORM_DEFAULTS[QueueType.SQS]["ordered_by_default"] is False


# ===========================================================================
# 5. simulate_failure — per failure mode
# ===========================================================================


class TestSimulateConsumerLag:
    def test_basic(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.CONSUMER_LAG, severity=0.5, duration_minutes=10.0)
        impact = sim.simulate_failure(default_config, s)
        assert impact.messages_at_risk > 0
        assert impact.estimated_message_delay_seconds > 0
        assert impact.consumer_recovery_minutes > 0
        assert len(impact.mitigation_actions) >= 1

    def test_zero_severity(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.CONSUMER_LAG, severity=0.0)
        impact = sim.simulate_failure(default_config, s)
        assert impact.messages_at_risk == 0

    def test_full_severity(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.CONSUMER_LAG, severity=1.0, duration_minutes=60.0)
        impact = sim.simulate_failure(default_config, s)
        assert impact.messages_at_risk > 0

    def test_partial_partitions(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        s_full = _make_scenario(QueueFailureMode.CONSUMER_LAG, affected_partitions_percent=100.0)
        s_half = _make_scenario(QueueFailureMode.CONSUMER_LAG, affected_partitions_percent=50.0)
        imp_full = sim.simulate_failure(default_config, s_full)
        imp_half = sim.simulate_failure(default_config, s_half)
        assert imp_full.messages_at_risk > imp_half.messages_at_risk


class TestSimulatePartitionRebalance:
    def test_basic(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.PARTITION_REBALANCE)
        impact = sim.simulate_failure(default_config, s)
        assert impact.consumer_recovery_minutes > 0
        assert impact.messages_at_risk > 0
        assert len(impact.mitigation_actions) >= 1

    def test_ordering_violation(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.PARTITION_REBALANCE)
        impact = sim.simulate_failure(default_config, s)
        assert impact.ordering_violated is True  # config has ordering_guaranteed=True

    def test_no_ordering_violation_when_not_guaranteed(self, sim: QueueResilienceSimulator):
        cfg = QueueConfig(queue_type=QueueType.SQS, ordering_guaranteed=False)
        s = _make_scenario(QueueFailureMode.PARTITION_REBALANCE)
        impact = sim.simulate_failure(cfg, s)
        assert impact.ordering_violated is False


class TestSimulateMessageOrderingLoss:
    def test_with_ordering_guaranteed(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.MESSAGE_ORDERING_LOSS)
        impact = sim.simulate_failure(default_config, s)
        assert impact.ordering_violated is True
        assert impact.messages_at_risk > 0

    def test_without_ordering_guaranteed(self, sim: QueueResilienceSimulator):
        cfg = QueueConfig(queue_type=QueueType.NATS, ordering_guaranteed=False)
        s = _make_scenario(QueueFailureMode.MESSAGE_ORDERING_LOSS)
        impact = sim.simulate_failure(cfg, s)
        assert impact.ordering_violated is False
        assert impact.messages_at_risk == 0

    def test_mitigation_content_with_ordering(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.MESSAGE_ORDERING_LOSS)
        impact = sim.simulate_failure(default_config, s)
        joined = " ".join(impact.mitigation_actions).lower()
        assert "ordering" in joined or "partition" in joined

    def test_mitigation_content_without_ordering(self, sim: QueueResilienceSimulator):
        cfg = QueueConfig(queue_type=QueueType.PUBSUB, ordering_guaranteed=False)
        s = _make_scenario(QueueFailureMode.MESSAGE_ORDERING_LOSS)
        impact = sim.simulate_failure(cfg, s)
        joined = " ".join(impact.mitigation_actions).lower()
        assert "not guaranteed" in joined


class TestSimulateDeadLetterOverflow:
    def test_with_dlq_enabled(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.DEAD_LETTER_OVERFLOW, severity=0.5)
        impact = sim.simulate_failure(default_config, s)
        assert impact.data_loss_possible is False
        assert impact.messages_at_risk >= 0

    def test_with_dlq_enabled_high_severity(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.DEAD_LETTER_OVERFLOW, severity=0.9)
        impact = sim.simulate_failure(default_config, s)
        assert impact.data_loss_possible is True

    def test_without_dlq(self, sim: QueueResilienceSimulator, weak_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.DEAD_LETTER_OVERFLOW, severity=0.5)
        impact = sim.simulate_failure(weak_config, s)
        assert impact.data_loss_possible is True
        assert impact.messages_at_risk > 0

    def test_dlq_mitigations_when_disabled(self, sim: QueueResilienceSimulator, weak_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.DEAD_LETTER_OVERFLOW)
        impact = sim.simulate_failure(weak_config, s)
        joined = " ".join(impact.mitigation_actions).lower()
        assert "dead letter" in joined or "enable" in joined


class TestSimulateBackpressure:
    def test_basic(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.BACKPRESSURE, severity=0.7)
        impact = sim.simulate_failure(default_config, s)
        assert impact.messages_at_risk > 0
        assert impact.estimated_message_delay_seconds > 0
        assert impact.consumer_recovery_minutes > 0

    def test_mitigations(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.BACKPRESSURE)
        impact = sim.simulate_failure(default_config, s)
        assert len(impact.mitigation_actions) >= 1


class TestSimulateDuplicateDelivery:
    def test_with_deduplication(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.DUPLICATE_DELIVERY, severity=0.5)
        impact = sim.simulate_failure(default_config, s)
        # With dedup enabled, messages_at_risk is much lower (0.05 factor)
        s_no_dedup = _make_scenario(QueueFailureMode.DUPLICATE_DELIVERY, severity=0.5)
        cfg_no_dedup = default_config.model_copy(update={"deduplication_enabled": False})
        impact_no = sim.simulate_failure(cfg_no_dedup, s_no_dedup)
        assert impact.messages_at_risk < impact_no.messages_at_risk

    def test_without_deduplication(self, sim: QueueResilienceSimulator, weak_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.DUPLICATE_DELIVERY, severity=0.5)
        impact = sim.simulate_failure(weak_config, s)
        assert impact.messages_at_risk > 0
        joined = " ".join(impact.mitigation_actions).lower()
        assert "deduplication" in joined or "idempotent" in joined

    def test_dedup_mitigation_message(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.DUPLICATE_DELIVERY)
        impact = sim.simulate_failure(default_config, s)
        joined = " ".join(impact.mitigation_actions).lower()
        assert "deduplication" in joined or "minimal" in joined


class TestSimulatePoisonMessage:
    def test_with_dlq(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.POISON_MESSAGE, severity=0.5)
        impact = sim.simulate_failure(default_config, s)
        assert impact.messages_at_risk == 1
        assert impact.data_loss_possible is False

    def test_without_dlq(self, sim: QueueResilienceSimulator, weak_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.POISON_MESSAGE, severity=0.5)
        impact = sim.simulate_failure(weak_config, s)
        assert impact.messages_at_risk > 1
        assert impact.data_loss_possible is True
        assert impact.consumer_recovery_minutes > 0

    def test_without_dlq_mitigations(self, sim: QueueResilienceSimulator, weak_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.POISON_MESSAGE)
        impact = sim.simulate_failure(weak_config, s)
        joined = " ".join(impact.mitigation_actions).lower()
        assert "dlq" in joined or "dead letter" in joined or "validation" in joined


class TestSimulateBrokerFailure:
    def test_basic(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.BROKER_FAILURE, severity=0.6)
        impact = sim.simulate_failure(default_config, s)
        assert impact.data_loss_possible is True
        assert impact.messages_at_risk > 0
        assert impact.consumer_recovery_minutes > 0

    def test_low_severity_partial_partitions_no_severity_data_loss(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        # With severity <= 0.5 AND only partial partitions affected, the severity check
        # does not trigger data_loss_possible. But the all-partitions check may still trigger.
        s = _make_scenario(QueueFailureMode.BROKER_FAILURE, severity=0.3, affected_partitions_percent=50.0)
        impact = sim.simulate_failure(default_config, s)
        # severity 0.3 <= 0.5, and affected_partitions = 3 < 6 total
        assert impact.data_loss_possible is False

    def test_full_partition_failure(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.BROKER_FAILURE, severity=0.3, affected_partitions_percent=100.0)
        impact = sim.simulate_failure(default_config, s)
        assert impact.data_loss_possible is True  # all partitions affected

    def test_mitigations(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.BROKER_FAILURE)
        impact = sim.simulate_failure(default_config, s)
        joined = " ".join(impact.mitigation_actions).lower()
        assert "replication" in joined or "multi-broker" in joined


class TestSimulateRetentionExpiry:
    def test_basic(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.RETENTION_EXPIRY, severity=0.5)
        impact = sim.simulate_failure(default_config, s)
        assert impact.data_loss_possible is True
        assert impact.messages_at_risk > 0

    def test_mitigations(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.RETENTION_EXPIRY)
        impact = sim.simulate_failure(default_config, s)
        joined = " ".join(impact.mitigation_actions).lower()
        assert "retention" in joined or "archive" in joined


class TestSimulateThroughputThrottle:
    def test_basic(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.THROUGHPUT_THROTTLE, severity=0.5)
        impact = sim.simulate_failure(default_config, s)
        assert impact.messages_at_risk > 0
        assert impact.estimated_message_delay_seconds > 0

    def test_recovery(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.THROUGHPUT_THROTTLE, severity=0.8)
        impact = sim.simulate_failure(default_config, s)
        assert impact.consumer_recovery_minutes > 0

    def test_mitigations(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.THROUGHPUT_THROTTLE)
        impact = sim.simulate_failure(default_config, s)
        joined = " ".join(impact.mitigation_actions).lower()
        assert "throughput" in joined or "rate" in joined


# ===========================================================================
# 6. simulate_failure — cross-cutting concerns
# ===========================================================================


class TestSimulateFailureCrossCutting:
    @pytest.mark.parametrize("mode", list(QueueFailureMode))
    def test_all_modes_return_impact(self, sim: QueueResilienceSimulator, default_config: QueueConfig, mode: QueueFailureMode):
        s = _make_scenario(mode, severity=0.5)
        impact = sim.simulate_failure(default_config, s)
        assert isinstance(impact, QueueImpact)
        assert impact.messages_at_risk >= 0
        assert len(impact.mitigation_actions) >= 1

    @pytest.mark.parametrize("mode", list(QueueFailureMode))
    def test_zero_duration_yields_minimal_impact(self, sim: QueueResilienceSimulator, default_config: QueueConfig, mode: QueueFailureMode):
        s = _make_scenario(mode, severity=0.5, duration_minutes=0.0)
        impact = sim.simulate_failure(default_config, s)
        assert isinstance(impact, QueueImpact)

    @pytest.mark.parametrize("mode", list(QueueFailureMode))
    def test_zero_affected_partitions(self, sim: QueueResilienceSimulator, default_config: QueueConfig, mode: QueueFailureMode):
        s = _make_scenario(mode, severity=0.5, affected_partitions_percent=0.0)
        impact = sim.simulate_failure(default_config, s)
        assert isinstance(impact, QueueImpact)

    @pytest.mark.parametrize("qt", list(QueueType))
    def test_all_queue_types_with_consumer_lag(self, sim: QueueResilienceSimulator, qt: QueueType):
        cfg = QueueConfig(queue_type=qt, partitions=3, consumers=3, max_throughput_per_sec=1000)
        s = _make_scenario(QueueFailureMode.CONSUMER_LAG, severity=0.5)
        impact = sim.simulate_failure(cfg, s)
        assert isinstance(impact, QueueImpact)
        assert impact.messages_at_risk >= 0

    def test_scenario_is_preserved_in_impact(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.BACKPRESSURE, severity=0.7)
        impact = sim.simulate_failure(default_config, s)
        assert impact.scenario == s
        assert impact.scenario.failure_mode == QueueFailureMode.BACKPRESSURE

    def test_messages_at_risk_never_negative(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        for mode in QueueFailureMode:
            s = _make_scenario(mode, severity=0.0, duration_minutes=0.0, affected_partitions_percent=0.0)
            impact = sim.simulate_failure(default_config, s)
            assert impact.messages_at_risk >= 0

    def test_recovery_never_negative(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        for mode in QueueFailureMode:
            s = _make_scenario(mode, severity=0.5)
            impact = sim.simulate_failure(default_config, s)
            assert impact.consumer_recovery_minutes >= 0.0

    def test_delay_never_negative(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        for mode in QueueFailureMode:
            s = _make_scenario(mode, severity=0.5)
            impact = sim.simulate_failure(default_config, s)
            assert impact.estimated_message_delay_seconds >= 0.0


# ===========================================================================
# 7. assess_queue_health
# ===========================================================================


class TestAssessQueueHealth:
    def test_healthy_config(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        score = sim.assess_queue_health(default_config)
        assert 0.0 <= score <= 100.0
        assert score >= 70.0  # strong config should score well

    def test_weak_config_scores_lower(self, sim: QueueResilienceSimulator, default_config: QueueConfig, weak_config: QueueConfig):
        strong = sim.assess_queue_health(default_config)
        weak = sim.assess_queue_health(weak_config)
        assert weak < strong

    def test_no_dlq_penalty(self, sim: QueueResilienceSimulator):
        cfg_dlq = QueueConfig(queue_type=QueueType.KAFKA, dead_letter_enabled=True, consumers=2, deduplication_enabled=True)
        cfg_no_dlq = QueueConfig(queue_type=QueueType.KAFKA, dead_letter_enabled=False, consumers=2, deduplication_enabled=True)
        assert sim.assess_queue_health(cfg_dlq) > sim.assess_queue_health(cfg_no_dlq)

    def test_low_consumer_ratio_penalty(self, sim: QueueResilienceSimulator):
        cfg = QueueConfig(queue_type=QueueType.KAFKA, partitions=10, consumers=2)
        score = sim.assess_queue_health(cfg)
        assert score < 100.0

    def test_very_low_consumer_ratio_penalty(self, sim: QueueResilienceSimulator):
        cfg_low = QueueConfig(queue_type=QueueType.KAFKA, partitions=10, consumers=1)
        cfg_ok = QueueConfig(queue_type=QueueType.KAFKA, partitions=10, consumers=6)
        assert sim.assess_queue_health(cfg_low) < sim.assess_queue_health(cfg_ok)

    def test_short_retention_penalty(self, sim: QueueResilienceSimulator):
        cfg_short = QueueConfig(queue_type=QueueType.KAFKA, retention_hours=12, consumers=2, deduplication_enabled=True, dead_letter_enabled=True)
        cfg_long = QueueConfig(queue_type=QueueType.KAFKA, retention_hours=168, consumers=2, deduplication_enabled=True, dead_letter_enabled=True)
        assert sim.assess_queue_health(cfg_short) < sim.assess_queue_health(cfg_long)

    def test_medium_retention_penalty(self, sim: QueueResilienceSimulator):
        cfg_48h = QueueConfig(queue_type=QueueType.KAFKA, retention_hours=48, consumers=2, deduplication_enabled=True, dead_letter_enabled=True)
        cfg_168h = QueueConfig(queue_type=QueueType.KAFKA, retention_hours=168, consumers=2, deduplication_enabled=True, dead_letter_enabled=True)
        assert sim.assess_queue_health(cfg_48h) < sim.assess_queue_health(cfg_168h)

    def test_low_throughput_penalty(self, sim: QueueResilienceSimulator):
        cfg_low = QueueConfig(queue_type=QueueType.KAFKA, max_throughput_per_sec=50, consumers=2, deduplication_enabled=True, dead_letter_enabled=True)
        cfg_high = QueueConfig(queue_type=QueueType.KAFKA, max_throughput_per_sec=5000, consumers=2, deduplication_enabled=True, dead_letter_enabled=True)
        assert sim.assess_queue_health(cfg_low) < sim.assess_queue_health(cfg_high)

    def test_single_consumer_penalty(self, sim: QueueResilienceSimulator):
        cfg_single = QueueConfig(queue_type=QueueType.KAFKA, consumers=1, deduplication_enabled=True, dead_letter_enabled=True)
        cfg_multi = QueueConfig(queue_type=QueueType.KAFKA, consumers=3, deduplication_enabled=True, dead_letter_enabled=True)
        assert sim.assess_queue_health(cfg_single) < sim.assess_queue_health(cfg_multi)

    def test_no_dedup_penalty(self, sim: QueueResilienceSimulator):
        cfg_dedup = QueueConfig(queue_type=QueueType.KAFKA, consumers=2, deduplication_enabled=True, dead_letter_enabled=True)
        cfg_no_dedup = QueueConfig(queue_type=QueueType.KAFKA, consumers=2, deduplication_enabled=False, dead_letter_enabled=True)
        assert sim.assess_queue_health(cfg_dedup) > sim.assess_queue_health(cfg_no_dedup)

    def test_ordering_with_multi_partitions_penalty(self, sim: QueueResilienceSimulator):
        cfg_ordered = QueueConfig(queue_type=QueueType.KAFKA, partitions=4, consumers=4, ordering_guaranteed=True, deduplication_enabled=True, dead_letter_enabled=True)
        cfg_unordered = QueueConfig(queue_type=QueueType.KAFKA, partitions=4, consumers=4, ordering_guaranteed=False, deduplication_enabled=True, dead_letter_enabled=True)
        assert sim.assess_queue_health(cfg_ordered) < sim.assess_queue_health(cfg_unordered)

    def test_score_clamped_to_0_100(self, sim: QueueResilienceSimulator, weak_config: QueueConfig):
        score = sim.assess_queue_health(weak_config)
        assert 0.0 <= score <= 100.0


# ===========================================================================
# 8. recommend_queue_config
# ===========================================================================


class TestRecommendQueueConfig:
    @pytest.mark.parametrize("qt", list(QueueType))
    def test_all_queue_types(self, sim: QueueResilienceSimulator, qt: QueueType):
        cfg = sim.recommend_queue_config(qt, 5000)
        assert cfg.queue_type == qt
        assert cfg.dead_letter_enabled is True
        assert cfg.deduplication_enabled is True
        assert cfg.consumers >= 1
        assert cfg.partitions >= 1
        assert cfg.max_throughput_per_sec >= 5000

    def test_low_throughput(self, sim: QueueResilienceSimulator):
        cfg = sim.recommend_queue_config(QueueType.KAFKA, 500)
        assert cfg.partitions == 3
        assert cfg.consumers == 3

    def test_medium_throughput(self, sim: QueueResilienceSimulator):
        cfg = sim.recommend_queue_config(QueueType.KAFKA, 5000)
        assert cfg.partitions == 6

    def test_high_throughput(self, sim: QueueResilienceSimulator):
        cfg = sim.recommend_queue_config(QueueType.KAFKA, 50000)
        assert cfg.partitions == 12

    def test_very_high_throughput(self, sim: QueueResilienceSimulator):
        cfg = sim.recommend_queue_config(QueueType.KAFKA, 200000)
        assert cfg.partitions == 24

    def test_non_partitioned_system(self, sim: QueueResilienceSimulator):
        cfg = sim.recommend_queue_config(QueueType.SQS, 5000)
        assert cfg.partitions == 1
        assert cfg.consumers >= 2

    def test_recommended_config_scores_well(self, sim: QueueResilienceSimulator):
        cfg = sim.recommend_queue_config(QueueType.KAFKA, 10000)
        score = sim.assess_queue_health(cfg)
        assert score >= 70.0

    def test_ordering_matches_platform_default(self, sim: QueueResilienceSimulator):
        cfg_kafka = sim.recommend_queue_config(QueueType.KAFKA, 1000)
        assert cfg_kafka.ordering_guaranteed is True  # Kafka is ordered by default

        cfg_sqs = sim.recommend_queue_config(QueueType.SQS, 1000)
        assert cfg_sqs.ordering_guaranteed is False  # SQS is not ordered by default

    def test_retention_is_one_week(self, sim: QueueResilienceSimulator):
        cfg = sim.recommend_queue_config(QueueType.RABBITMQ, 1000)
        assert cfg.retention_hours == 168


# ===========================================================================
# 9. find_queue_vulnerabilities
# ===========================================================================


class TestFindQueueVulnerabilities:
    def test_strong_config_few_vulns(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        vulns = sim.find_queue_vulnerabilities(default_config)
        # Strong config should still flag ordering+multi-partition
        assert isinstance(vulns, list)

    def test_weak_config_many_vulns(self, sim: QueueResilienceSimulator, weak_config: QueueConfig):
        vulns = sim.find_queue_vulnerabilities(weak_config)
        assert len(vulns) >= 4  # multiple weaknesses

    def test_under_provisioned_consumers(self, sim: QueueResilienceSimulator):
        cfg = QueueConfig(queue_type=QueueType.KAFKA, partitions=10, consumers=3)
        vulns = sim.find_queue_vulnerabilities(cfg)
        assert any("under-provisioned" in v.lower() for v in vulns)

    def test_no_dlq_vulnerability(self, sim: QueueResilienceSimulator):
        cfg = QueueConfig(queue_type=QueueType.KAFKA, dead_letter_enabled=False)
        vulns = sim.find_queue_vulnerabilities(cfg)
        assert any("dead letter" in v.lower() for v in vulns)

    def test_ordering_multipartition_vuln(self, sim: QueueResilienceSimulator):
        cfg = QueueConfig(queue_type=QueueType.KAFKA, partitions=4, ordering_guaranteed=True)
        vulns = sim.find_queue_vulnerabilities(cfg)
        assert any("ordering" in v.lower() for v in vulns)

    def test_no_dedup_vuln(self, sim: QueueResilienceSimulator):
        cfg = QueueConfig(queue_type=QueueType.KAFKA, deduplication_enabled=False)
        vulns = sim.find_queue_vulnerabilities(cfg)
        assert any("deduplication" in v.lower() or "duplicate" in v.lower() for v in vulns)

    def test_short_retention_vuln(self, sim: QueueResilienceSimulator):
        cfg = QueueConfig(queue_type=QueueType.KAFKA, retention_hours=12)
        vulns = sim.find_queue_vulnerabilities(cfg)
        assert any("retention" in v.lower() for v in vulns)

    def test_low_throughput_vuln(self, sim: QueueResilienceSimulator):
        cfg = QueueConfig(queue_type=QueueType.KAFKA, max_throughput_per_sec=50)
        vulns = sim.find_queue_vulnerabilities(cfg)
        assert any("throughput" in v.lower() for v in vulns)

    def test_single_consumer_vuln(self, sim: QueueResilienceSimulator):
        cfg = QueueConfig(queue_type=QueueType.KAFKA, consumers=1)
        vulns = sim.find_queue_vulnerabilities(cfg)
        assert any("single" in v.lower() for v in vulns)

    def test_large_message_size_vuln(self, sim: QueueResilienceSimulator):
        cfg = QueueConfig(queue_type=QueueType.KAFKA, max_message_size_kb=2048)
        vulns = sim.find_queue_vulnerabilities(cfg)
        assert any("message size" in v.lower() for v in vulns)

    def test_no_vuln_for_equal_consumers_partitions(self, sim: QueueResilienceSimulator):
        cfg = QueueConfig(
            queue_type=QueueType.KAFKA,
            partitions=6,
            consumers=6,
            dead_letter_enabled=True,
            ordering_guaranteed=False,
            deduplication_enabled=True,
            retention_hours=168,
            max_throughput_per_sec=5000,
            max_message_size_kb=256,
        )
        vulns = sim.find_queue_vulnerabilities(cfg)
        assert not any("under-provisioned" in v.lower() for v in vulns)


# ===========================================================================
# 10. generate_report
# ===========================================================================


class TestGenerateReport:
    def test_empty_inputs(self, sim: QueueResilienceSimulator):
        report = sim.generate_report([], [])
        assert report.queue_configs_tested == 0
        assert report.scenarios_run == 0
        assert report.overall_queue_resilience == 0.0

    def test_configs_only_no_scenarios(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        report = sim.generate_report([default_config], [])
        assert report.queue_configs_tested == 1
        assert report.scenarios_run == 0

    def test_single_config_single_scenario(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.CONSUMER_LAG)
        report = sim.generate_report([default_config], [s])
        assert report.queue_configs_tested == 1
        assert report.scenarios_run == 1
        assert len(report.impacts) == 1
        assert 0.0 <= report.overall_queue_resilience <= 100.0

    def test_multiple_configs_multiple_scenarios(self, sim: QueueResilienceSimulator, default_config: QueueConfig, weak_config: QueueConfig):
        scenarios = [
            _make_scenario(QueueFailureMode.CONSUMER_LAG),
            _make_scenario(QueueFailureMode.BROKER_FAILURE),
        ]
        report = sim.generate_report([default_config, weak_config], scenarios)
        assert report.queue_configs_tested == 2
        assert report.scenarios_run == 4  # 2 configs x 2 scenarios
        assert len(report.impacts) == 4

    def test_critical_risks_counted(self, sim: QueueResilienceSimulator, weak_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.BROKER_FAILURE, severity=0.9, duration_minutes=60.0)
        report = sim.generate_report([weak_config], [s])
        assert report.critical_risks >= 1

    def test_recommendations_populated(self, sim: QueueResilienceSimulator, weak_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.CONSUMER_LAG)
        report = sim.generate_report([weak_config], [s])
        assert len(report.recommendations) >= 1

    def test_report_resilience_in_range(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        scenarios = [_make_scenario(fm) for fm in QueueFailureMode]
        report = sim.generate_report([default_config], scenarios)
        assert 0.0 <= report.overall_queue_resilience <= 100.0

    def test_report_with_all_modes(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        scenarios = [_make_scenario(fm, severity=0.5) for fm in QueueFailureMode]
        report = sim.generate_report([default_config], scenarios)
        assert report.scenarios_run == len(QueueFailureMode)

    def test_critical_risk_from_data_loss(self, sim: QueueResilienceSimulator):
        cfg = QueueConfig(
            queue_type=QueueType.KAFKA,
            dead_letter_enabled=False,
            max_throughput_per_sec=10000,
        )
        s = _make_scenario(QueueFailureMode.DEAD_LETTER_OVERFLOW, severity=0.9, duration_minutes=30.0)
        report = sim.generate_report([cfg], [s])
        assert report.critical_risks >= 1

    def test_critical_risk_from_high_message_count(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.CONSUMER_LAG, severity=1.0, duration_minutes=120.0)
        report = sim.generate_report([default_config], [s])
        # 10000 * 120*60 * 1.0 = 72_000_000 messages >> 10000 threshold
        assert report.critical_risks >= 1

    def test_recommendations_include_critical_count(self, sim: QueueResilienceSimulator, weak_config: QueueConfig):
        s = _make_scenario(QueueFailureMode.BROKER_FAILURE, severity=0.9, duration_minutes=60.0)
        report = sim.generate_report([weak_config], [s])
        if report.critical_risks > 0:
            assert any("critical" in r.lower() for r in report.recommendations)


# ===========================================================================
# 11. QueueResilienceSimulator initialization
# ===========================================================================


class TestSimulatorInit:
    def test_constructor(self, graph: InfraGraph):
        sim = QueueResilienceSimulator(graph)
        assert sim._graph is graph

    def test_with_empty_graph(self, graph: InfraGraph):
        sim = QueueResilienceSimulator(graph)
        cfg = QueueConfig(queue_type=QueueType.KAFKA)
        s = _make_scenario(QueueFailureMode.CONSUMER_LAG)
        impact = sim.simulate_failure(cfg, s)
        assert isinstance(impact, QueueImpact)


# ===========================================================================
# 12. Edge cases and boundary values
# ===========================================================================


class TestEdgeCases:
    def test_minimal_config(self, sim: QueueResilienceSimulator):
        cfg = QueueConfig(
            queue_type=QueueType.NATS,
            partitions=1,
            consumers=1,
            retention_hours=1,
            max_message_size_kb=1,
            max_throughput_per_sec=1,
        )
        s = _make_scenario(QueueFailureMode.CONSUMER_LAG, severity=1.0)
        impact = sim.simulate_failure(cfg, s)
        assert isinstance(impact, QueueImpact)

    def test_max_severity_all_modes(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        for mode in QueueFailureMode:
            s = _make_scenario(mode, severity=1.0, duration_minutes=1440.0)
            impact = sim.simulate_failure(default_config, s)
            assert impact.messages_at_risk >= 0

    def test_min_severity_all_modes(self, sim: QueueResilienceSimulator, default_config: QueueConfig):
        for mode in QueueFailureMode:
            s = _make_scenario(mode, severity=0.0, duration_minutes=10.0)
            impact = sim.simulate_failure(default_config, s)
            assert impact.messages_at_risk >= 0

    def test_very_high_throughput(self, sim: QueueResilienceSimulator):
        cfg = QueueConfig(
            queue_type=QueueType.KAFKA,
            partitions=24,
            consumers=24,
            max_throughput_per_sec=1000000,
        )
        s = _make_scenario(QueueFailureMode.CONSUMER_LAG, severity=1.0, duration_minutes=60.0)
        impact = sim.simulate_failure(cfg, s)
        assert impact.messages_at_risk > 0

    def test_report_with_many_configs(self, sim: QueueResilienceSimulator):
        configs = [
            QueueConfig(queue_type=qt, partitions=3, consumers=3)
            for qt in QueueType
        ]
        scenarios = [_make_scenario(QueueFailureMode.CONSUMER_LAG)]
        report = sim.generate_report(configs, scenarios)
        assert report.queue_configs_tested == len(QueueType)
        assert report.scenarios_run == len(QueueType)

    def test_recommend_then_assess(self, sim: QueueResilienceSimulator):
        """Recommended config should score reasonably well."""
        for qt in QueueType:
            cfg = sim.recommend_queue_config(qt, 5000)
            score = sim.assess_queue_health(cfg)
            assert score >= 50.0, f"{qt} recommended config scored {score}"

    def test_recommend_with_min_throughput(self, sim: QueueResilienceSimulator):
        cfg = sim.recommend_queue_config(QueueType.KAFKA, 1)
        assert cfg.max_throughput_per_sec >= 1

    def test_single_partition_ordering_no_vuln(self, sim: QueueResilienceSimulator):
        cfg = QueueConfig(queue_type=QueueType.KAFKA, partitions=1, ordering_guaranteed=True)
        vulns = sim.find_queue_vulnerabilities(cfg)
        assert not any("ordering" in v.lower() and "partition" in v.lower() for v in vulns)
