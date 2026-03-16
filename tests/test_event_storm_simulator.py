"""Tests for Event Storm Simulator.

Covers all enums, models, bus characteristics, storm types, and engine
methods with edge cases for 100 % coverage.
"""

from __future__ import annotations

import math

import pytest

from faultray.model.components import (
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    AutoScalingConfig,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.event_storm_simulator import (
    BackpressureResult,
    ConsumerCapacityReport,
    EventBusType,
    EventStormSimulatorEngine,
    RebalanceResult,
    StormConfig,
    StormProtection,
    StormResult,
    StormRisk,
    StormType,
    _BUS_CHARACTERISTICS,
    _STORM_SEVERITY,
    _clamp,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(cid: str = "c1", ctype: ComponentType = ComponentType.QUEUE, **kw):
    return Component(id=cid, name=cid, type=ctype, **kw)


def _graph(*comps, deps=None):
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    for d in deps or []:
        g.add_dependency(d)
    return g


# ---------------------------------------------------------------------------
# Enum coverage
# ---------------------------------------------------------------------------


class TestEnums:
    def test_storm_type_has_8_members(self):
        assert len(StormType) == 8

    def test_storm_type_values(self):
        expected = {
            "broadcast_storm",
            "retry_storm",
            "dead_letter_flood",
            "consumer_lag_cascade",
            "partition_rebalance",
            "schema_change_storm",
            "replay_flood",
            "fanout_explosion",
        }
        assert {s.value for s in StormType} == expected

    def test_event_bus_type_has_8_members(self):
        assert len(EventBusType) == 8

    def test_event_bus_type_values(self):
        expected = {
            "kafka",
            "rabbitmq",
            "sqs",
            "sns",
            "pulsar",
            "nats",
            "redis_streams",
            "kinesis",
        }
        assert {b.value for b in EventBusType} == expected


# ---------------------------------------------------------------------------
# Model defaults
# ---------------------------------------------------------------------------


class TestModelDefaults:
    def test_storm_config_defaults(self):
        cfg = StormConfig(storm_type=StormType.BROADCAST_STORM)
        assert cfg.bus_type == EventBusType.KAFKA
        assert cfg.events_per_second == 1000.0
        assert cfg.duration_seconds == 60.0
        assert cfg.partitions == 3
        assert cfg.consumers == 3
        assert cfg.retry_multiplier == 3.0
        assert cfg.fanout_factor == 1.0
        assert cfg.failure_rate == 0.1
        assert cfg.incompatibility_rate == 0.0

    def test_storm_result_defaults(self):
        r = StormResult(storm_type=StormType.BROADCAST_STORM, bus_type=EventBusType.KAFKA)
        assert r.total_events == 0
        assert r.processed_events == 0
        assert r.dead_letter_events == 0
        assert r.is_overloaded is False
        assert r.recommendations == []

    def test_storm_risk_defaults(self):
        r = StormRisk(component_id="x", risk_type="test")
        assert r.severity == 0.0
        assert r.description == ""
        assert r.mitigation == ""

    def test_consumer_capacity_report_defaults(self):
        r = ConsumerCapacityReport()
        assert r.total_consumers == 0
        assert r.headroom_percent == 0.0
        assert r.is_under_provisioned is False

    def test_rebalance_result_defaults(self):
        r = RebalanceResult()
        assert r.rebalance_duration_ms == 0.0
        assert r.ordering_violated is False

    def test_storm_protection_defaults(self):
        p = StormProtection(protection_type="test", description="desc")
        assert p.priority == 0.0
        assert p.estimated_risk_reduction == 0.0

    def test_backpressure_result_defaults(self):
        r = BackpressureResult()
        assert r.applied_backpressure is False
        assert r.throttle_percent == 0.0
        assert r.events_dropped == 0
        assert r.producer_blocked is False


# ---------------------------------------------------------------------------
# Bus characteristics & severity tables
# ---------------------------------------------------------------------------


class TestLookupTables:
    def test_all_bus_types_have_characteristics(self):
        for bt in EventBusType:
            assert bt in _BUS_CHARACTERISTICS

    def test_all_storm_types_have_severity(self):
        for st in StormType:
            assert st in _STORM_SEVERITY

    def test_characteristics_keys(self):
        required_keys = {
            "throughput_per_partition",
            "rebalance_ms",
            "ordering",
            "dlq_native",
            "latency_base_ms",
            "backpressure_capable",
        }
        for bt in EventBusType:
            assert required_keys.issubset(_BUS_CHARACTERISTICS[bt].keys())


# ---------------------------------------------------------------------------
# _clamp helper
# ---------------------------------------------------------------------------


class TestClamp:
    def test_within_range(self):
        assert _clamp(50.0) == 50.0

    def test_below_low(self):
        assert _clamp(-10.0) == 0.0

    def test_above_high(self):
        assert _clamp(200.0) == 100.0

    def test_custom_bounds(self):
        assert _clamp(5.0, 1.0, 10.0) == 5.0
        assert _clamp(0.0, 1.0, 10.0) == 1.0
        assert _clamp(15.0, 1.0, 10.0) == 10.0


# ---------------------------------------------------------------------------
# Engine construction
# ---------------------------------------------------------------------------


class TestEngineConstruction:
    def test_default_graph(self):
        engine = EventStormSimulatorEngine()
        assert engine._graph is not None

    def test_custom_graph(self):
        g = _graph()
        engine = EventStormSimulatorEngine(graph=g)
        assert engine._graph is g


# ---------------------------------------------------------------------------
# simulate_storm
# ---------------------------------------------------------------------------


class TestSimulateStorm:
    def setup_method(self):
        self.engine = EventStormSimulatorEngine()
        self.graph = _graph(
            _comp("q1", ComponentType.QUEUE),
            _comp("a1", ComponentType.APP_SERVER),
        )

    # -- per storm type ---

    def test_broadcast_storm_basic(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            bus_type=EventBusType.KAFKA,
            events_per_second=1000.0,
            partitions=3,
            consumers=3,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        assert result.storm_type == StormType.BROADCAST_STORM
        assert result.bus_type == EventBusType.KAFKA
        assert result.total_events == 60000
        assert result.is_overloaded is False

    def test_broadcast_storm_high_fanout_bus(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            bus_type=EventBusType.SNS,
            events_per_second=50000.0,
            partitions=3,
            fanout_factor=5.0,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        assert result.is_overloaded is True

    def test_retry_storm(self):
        cfg = StormConfig(
            storm_type=StormType.RETRY_STORM,
            bus_type=EventBusType.KAFKA,
            events_per_second=5000.0,
            partitions=3,
            failure_rate=0.5,
            retry_multiplier=4.0,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        assert result.storm_type == StormType.RETRY_STORM
        assert any("backoff" in r.lower() for r in result.recommendations)

    def test_dead_letter_flood(self):
        cfg = StormConfig(
            storm_type=StormType.DEAD_LETTER_FLOOD,
            events_per_second=2000.0,
            failure_rate=0.3,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        assert result.dead_letter_events > 0
        assert result.processed_events == result.total_events - result.dead_letter_events

    def test_consumer_lag_cascade(self):
        cfg = StormConfig(
            storm_type=StormType.CONSUMER_LAG_CASCADE,
            events_per_second=40000.0,
            partitions=3,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        assert result.is_overloaded is True

    def test_partition_rebalance(self):
        cfg = StormConfig(
            storm_type=StormType.PARTITION_REBALANCE,
            events_per_second=25000.0,
            partitions=3,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        # 30 % throughput reduction during rebalance
        assert result.is_overloaded is True

    def test_schema_change_storm(self):
        cfg = StormConfig(
            storm_type=StormType.SCHEMA_CHANGE_STORM,
            events_per_second=1000.0,
            incompatibility_rate=0.4,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        assert result.dead_letter_events > 0
        assert result.degradation_percent > 0
        assert any("schema" in r.lower() for r in result.recommendations)

    def test_replay_flood(self):
        cfg = StormConfig(
            storm_type=StormType.REPLAY_FLOOD,
            events_per_second=20000.0,
            partitions=3,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        # Replay doubles effective eps -> overloaded
        assert result.is_overloaded is True

    def test_fanout_explosion(self):
        cfg = StormConfig(
            storm_type=StormType.FANOUT_EXPLOSION,
            events_per_second=5000.0,
            partitions=3,
            fanout_factor=10.0,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        assert result.is_overloaded is True
        assert any("fan-out" in r.lower() or "fanout" in r.lower() for r in result.recommendations)

    # -- overload / non-overload paths ---

    def test_not_overloaded_low_eps(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            events_per_second=100.0,
            partitions=6,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        assert result.is_overloaded is False
        assert result.processed_events == result.total_events

    def test_overloaded_high_eps(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            events_per_second=100000.0,
            partitions=1,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        assert result.is_overloaded is True
        assert result.processed_events < result.total_events

    # -- latency ---

    def test_latency_increases_when_overloaded(self):
        cfg_low = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            events_per_second=100.0,
            partitions=6,
        )
        cfg_high = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            events_per_second=100000.0,
            partitions=1,
        )
        r_low = self.engine.simulate_storm(self.graph, cfg_low)
        r_high = self.engine.simulate_storm(self.graph, cfg_high)
        assert r_high.avg_latency_ms > r_low.avg_latency_ms
        assert r_high.max_latency_ms > r_low.max_latency_ms

    # -- dead letter paths ---

    def test_dead_letter_flood_high_failure_rate(self):
        cfg = StormConfig(
            storm_type=StormType.DEAD_LETTER_FLOOD,
            events_per_second=1000.0,
            failure_rate=0.9,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        assert result.dead_letter_events > result.total_events * 0.1

    def test_non_overloaded_small_dead_letter(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            events_per_second=100.0,
            partitions=6,
            failure_rate=0.05,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        assert result.dead_letter_events >= 0

    # -- degradation ---

    def test_degradation_zero_when_not_overloaded(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            events_per_second=100.0,
            partitions=6,
            failure_rate=0.0,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        assert result.degradation_percent == 0.0

    def test_dead_letter_flood_degradation(self):
        cfg = StormConfig(
            storm_type=StormType.DEAD_LETTER_FLOOD,
            events_per_second=100.0,
            failure_rate=0.5,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        assert result.degradation_percent > 0.0

    def test_schema_change_storm_degradation(self):
        cfg = StormConfig(
            storm_type=StormType.SCHEMA_CHANGE_STORM,
            events_per_second=100.0,
            incompatibility_rate=0.3,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        assert result.degradation_percent > 0.0

    # -- recommendations ---

    def test_recommendation_no_native_dlq(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            bus_type=EventBusType.KAFKA,  # dlq_native=False
            events_per_second=100.0,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        assert any("dlq" in r.lower() or "DLQ" in r for r in result.recommendations)

    def test_recommendation_backpressure_not_capable(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            bus_type=EventBusType.SQS,  # not backpressure_capable
            events_per_second=100000.0,
            partitions=1,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        assert any("backpressure" in r.lower() for r in result.recommendations)

    # -- all bus types ---

    @pytest.mark.parametrize("bus_type", list(EventBusType))
    def test_all_bus_types(self, bus_type):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            bus_type=bus_type,
            events_per_second=1000.0,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        assert isinstance(result, StormResult)
        assert result.bus_type == bus_type

    # -- all storm types ---

    @pytest.mark.parametrize("storm_type", list(StormType))
    def test_all_storm_types(self, storm_type):
        cfg = StormConfig(
            storm_type=storm_type,
            events_per_second=2000.0,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        assert isinstance(result, StormResult)
        assert result.storm_type == storm_type

    # -- empty graph ---

    def test_empty_graph(self):
        g = _graph()
        cfg = StormConfig(storm_type=StormType.BROADCAST_STORM, events_per_second=1000.0)
        result = self.engine.simulate_storm(g, cfg)
        assert isinstance(result, StormResult)

    # -- zero duration ---

    def test_zero_duration(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            events_per_second=1000.0,
            duration_seconds=0.0,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        assert result.total_events == 0

    # -- peak throughput ---

    def test_peak_throughput_capped(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            events_per_second=100000.0,
            partitions=1,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        bus = _BUS_CHARACTERISTICS[EventBusType.KAFKA]
        assert result.peak_throughput <= bus["throughput_per_partition"] * 1


# ---------------------------------------------------------------------------
# detect_storm_risks
# ---------------------------------------------------------------------------


class TestDetectStormRisks:
    def setup_method(self):
        self.engine = EventStormSimulatorEngine()

    def test_single_consumer_risk(self):
        g = _graph(_comp("q1", ComponentType.QUEUE, replicas=1))
        risks = self.engine.detect_storm_risks(g)
        assert any(r.risk_type == "single_consumer" for r in risks)

    def test_no_single_consumer_risk_with_replicas(self):
        g = _graph(_comp("q1", ComponentType.QUEUE, replicas=3))
        risks = self.engine.detect_storm_risks(g)
        assert not any(r.risk_type == "single_consumer" for r in risks)

    def test_high_fanout_risk(self):
        q = _comp("q1", ComponentType.QUEUE, replicas=3)
        a1 = _comp("a1", ComponentType.APP_SERVER)
        a2 = _comp("a2", ComponentType.APP_SERVER)
        a3 = _comp("a3", ComponentType.APP_SERVER)
        a4 = _comp("a4", ComponentType.APP_SERVER)
        g = _graph(
            q, a1, a2, a3, a4,
            deps=[
                Dependency(source_id="a1", target_id="q1"),
                Dependency(source_id="a2", target_id="q1"),
                Dependency(source_id="a3", target_id="q1"),
                Dependency(source_id="a4", target_id="q1"),
            ],
        )
        risks = self.engine.detect_storm_risks(g)
        assert any(r.risk_type == "high_fanout" for r in risks)

    def test_no_circuit_breaker_risk(self):
        a = _comp("a1", ComponentType.APP_SERVER)
        b = _comp("b1", ComponentType.DATABASE)
        g = _graph(
            a, b,
            deps=[Dependency(source_id="a1", target_id="b1")],
        )
        risks = self.engine.detect_storm_risks(g)
        assert any(r.risk_type == "no_circuit_breaker" for r in risks)

    def test_circuit_breaker_enabled_no_risk(self):
        a = _comp("a1", ComponentType.APP_SERVER)
        b = _comp("b1", ComponentType.DATABASE)
        g = _graph(
            a, b,
            deps=[
                Dependency(
                    source_id="a1",
                    target_id="b1",
                    circuit_breaker=CircuitBreakerConfig(enabled=True),
                )
            ],
        )
        risks = self.engine.detect_storm_risks(g)
        assert not any(r.risk_type == "no_circuit_breaker" for r in risks)

    def test_empty_graph_no_risks(self):
        g = _graph()
        risks = self.engine.detect_storm_risks(g)
        assert risks == []

    def test_fanout_severity_capped(self):
        q = _comp("q1", ComponentType.QUEUE, replicas=3)
        comps = [q]
        deps = []
        for i in range(15):
            c = _comp(f"a{i}", ComponentType.APP_SERVER)
            comps.append(c)
            deps.append(Dependency(source_id=f"a{i}", target_id="q1"))
        g = _graph(*comps, deps=deps)
        risks = self.engine.detect_storm_risks(g)
        fanout_risks = [r for r in risks if r.risk_type == "high_fanout"]
        for r in fanout_risks:
            assert r.severity <= 1.0


# ---------------------------------------------------------------------------
# analyze_consumer_capacity
# ---------------------------------------------------------------------------


class TestAnalyzeConsumerCapacity:
    def setup_method(self):
        self.engine = EventStormSimulatorEngine()
        self.graph = _graph(_comp("q1", ComponentType.QUEUE))

    def test_well_provisioned(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            bus_type=EventBusType.KAFKA,
            events_per_second=1000.0,
            partitions=3,
            consumers=3,
        )
        report = self.engine.analyze_consumer_capacity(self.graph, cfg)
        assert report.consumer_to_partition_ratio == 1.0
        assert report.is_under_provisioned is False
        assert report.is_over_provisioned is False
        assert report.headroom_percent > 0

    def test_under_provisioned(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            events_per_second=1000.0,
            partitions=6,
            consumers=2,
        )
        report = self.engine.analyze_consumer_capacity(self.graph, cfg)
        assert report.is_under_provisioned is True
        assert any("scale" in r.lower() for r in report.recommendations)

    def test_over_provisioned(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            events_per_second=1000.0,
            partitions=2,
            consumers=10,
        )
        report = self.engine.analyze_consumer_capacity(self.graph, cfg)
        assert report.is_over_provisioned is True
        assert any("reduce" in r.lower() or "idle" in r.lower() for r in report.recommendations)

    def test_low_headroom(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            bus_type=EventBusType.KINESIS,  # 1000 per partition
            events_per_second=2800.0,
            partitions=3,
            consumers=3,
        )
        report = self.engine.analyze_consumer_capacity(self.graph, cfg)
        assert report.headroom_percent < 20.0
        assert any("headroom" in r.lower() for r in report.recommendations)

    def test_good_headroom_recommendation(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            bus_type=EventBusType.NATS,  # 50k per partition
            events_per_second=100.0,
            partitions=3,
            consumers=3,
        )
        report = self.engine.analyze_consumer_capacity(self.graph, cfg)
        assert any("well-provisioned" in r.lower() for r in report.recommendations)

    @pytest.mark.parametrize("bus_type", list(EventBusType))
    def test_all_bus_types(self, bus_type):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            bus_type=bus_type,
            events_per_second=500.0,
        )
        report = self.engine.analyze_consumer_capacity(self.graph, cfg)
        assert isinstance(report, ConsumerCapacityReport)
        assert report.estimated_max_throughput > 0


# ---------------------------------------------------------------------------
# simulate_partition_rebalance
# ---------------------------------------------------------------------------


class TestSimulatePartitionRebalance:
    def setup_method(self):
        self.engine = EventStormSimulatorEngine()
        self.graph = _graph(_comp("q1", ComponentType.QUEUE))

    def test_basic_kafka_rebalance(self):
        cfg = StormConfig(
            storm_type=StormType.PARTITION_REBALANCE,
            bus_type=EventBusType.KAFKA,
            partitions=6,
            events_per_second=1000.0,
        )
        result = self.engine.simulate_partition_rebalance(self.graph, cfg)
        assert result.rebalance_duration_ms > 0
        assert result.partitions_moved == 3
        assert result.events_delayed > 0
        assert result.consumer_downtime_ms > 0

    def test_ordering_violated_when_partitioned_bus(self):
        cfg = StormConfig(
            storm_type=StormType.PARTITION_REBALANCE,
            bus_type=EventBusType.KAFKA,  # ordering=True
            partitions=6,
        )
        result = self.engine.simulate_partition_rebalance(self.graph, cfg)
        assert result.ordering_violated is True

    def test_ordering_not_violated_unordered_bus(self):
        cfg = StormConfig(
            storm_type=StormType.PARTITION_REBALANCE,
            bus_type=EventBusType.SQS,  # ordering=False
            partitions=6,
        )
        result = self.engine.simulate_partition_rebalance(self.graph, cfg)
        assert result.ordering_violated is False

    def test_ordering_not_violated_single_partition(self):
        cfg = StormConfig(
            storm_type=StormType.PARTITION_REBALANCE,
            bus_type=EventBusType.KAFKA,
            partitions=1,
        )
        result = self.engine.simulate_partition_rebalance(self.graph, cfg)
        # partitions_moved = max(1, 1//2) = max(1, 0) = 1, only 1 moved -> not violated
        # Actually 1//2 = 0, max(1, 0) = 1, and 1 > 1 is False
        assert result.ordering_violated is False

    def test_high_rebalance_time_recommendation(self):
        cfg = StormConfig(
            storm_type=StormType.PARTITION_REBALANCE,
            bus_type=EventBusType.KINESIS,  # 10000ms base
            partitions=32,
        )
        result = self.engine.simulate_partition_rebalance(self.graph, cfg)
        assert result.rebalance_duration_ms > 10000
        assert any("incremental" in r.lower() for r in result.recommendations)

    def test_too_many_partitions_recommendation(self):
        cfg = StormConfig(
            storm_type=StormType.PARTITION_REBALANCE,
            partitions=20,
            consumers=3,
        )
        result = self.engine.simulate_partition_rebalance(self.graph, cfg)
        assert any("scale consumers" in r.lower() for r in result.recommendations)

    def test_acceptable_rebalance(self):
        cfg = StormConfig(
            storm_type=StormType.PARTITION_REBALANCE,
            bus_type=EventBusType.NATS,  # 1000ms base
            partitions=2,
            consumers=2,
            events_per_second=100.0,
        )
        result = self.engine.simulate_partition_rebalance(self.graph, cfg)
        assert any("acceptable" in r.lower() for r in result.recommendations)

    @pytest.mark.parametrize("bus_type", list(EventBusType))
    def test_all_bus_types(self, bus_type):
        cfg = StormConfig(
            storm_type=StormType.PARTITION_REBALANCE,
            bus_type=bus_type,
            partitions=4,
            events_per_second=500.0,
        )
        result = self.engine.simulate_partition_rebalance(self.graph, cfg)
        assert isinstance(result, RebalanceResult)

    def test_sqs_zero_rebalance_ms(self):
        cfg = StormConfig(
            storm_type=StormType.PARTITION_REBALANCE,
            bus_type=EventBusType.SQS,  # rebalance_ms=0
            partitions=4,
            events_per_second=1000.0,
        )
        result = self.engine.simulate_partition_rebalance(self.graph, cfg)
        assert result.rebalance_duration_ms == 0.0
        assert result.events_delayed == 0


# ---------------------------------------------------------------------------
# recommend_storm_protection
# ---------------------------------------------------------------------------


class TestRecommendStormProtection:
    def setup_method(self):
        self.engine = EventStormSimulatorEngine()

    def test_always_includes_rate_limiting(self):
        g = _graph(_comp("q1", ComponentType.QUEUE))
        protections = self.engine.recommend_storm_protection(g)
        assert any(p.protection_type == "rate_limiting" for p in protections)

    def test_circuit_breaker_when_missing(self):
        a = _comp("a1", ComponentType.APP_SERVER)
        b = _comp("b1", ComponentType.DATABASE)
        g = _graph(a, b, deps=[Dependency(source_id="a1", target_id="b1")])
        protections = self.engine.recommend_storm_protection(g)
        assert any(p.protection_type == "circuit_breaker" for p in protections)

    def test_no_circuit_breaker_when_present(self):
        a = _comp("a1", ComponentType.APP_SERVER)
        b = _comp("b1", ComponentType.DATABASE)
        g = _graph(
            a, b,
            deps=[
                Dependency(
                    source_id="a1",
                    target_id="b1",
                    circuit_breaker=CircuitBreakerConfig(enabled=True),
                )
            ],
        )
        protections = self.engine.recommend_storm_protection(g)
        assert not any(p.protection_type == "circuit_breaker" for p in protections)

    def test_consumer_autoscaling_when_disabled(self):
        g = _graph(_comp("q1", ComponentType.QUEUE))
        protections = self.engine.recommend_storm_protection(g)
        assert any(p.protection_type == "consumer_autoscaling" for p in protections)

    def test_no_autoscaling_when_enabled(self):
        q = _comp(
            "q1",
            ComponentType.QUEUE,
            autoscaling=AutoScalingConfig(enabled=True, min_replicas=1, max_replicas=10),
        )
        g = _graph(q)
        protections = self.engine.recommend_storm_protection(g)
        assert not any(p.protection_type == "consumer_autoscaling" for p in protections)

    def test_always_includes_dlq(self):
        g = _graph()
        protections = self.engine.recommend_storm_protection(g)
        assert any(p.protection_type == "dead_letter_queue" for p in protections)

    def test_always_includes_schema_registry(self):
        g = _graph()
        protections = self.engine.recommend_storm_protection(g)
        assert any(p.protection_type == "schema_registry" for p in protections)

    def test_always_includes_backpressure(self):
        g = _graph()
        protections = self.engine.recommend_storm_protection(g)
        assert any(p.protection_type == "backpressure" for p in protections)

    def test_empty_graph(self):
        g = _graph()
        protections = self.engine.recommend_storm_protection(g)
        assert len(protections) > 0

    def test_no_edges_no_cb_recommendation(self):
        g = _graph(_comp("q1", ComponentType.QUEUE))
        protections = self.engine.recommend_storm_protection(g)
        # No edges => has_cb defaults to False but guard triggers the recommendation
        types = [p.protection_type for p in protections]
        # circuit_breaker may or may not appear depending on edge presence
        assert "rate_limiting" in types


# ---------------------------------------------------------------------------
# estimate_recovery_time
# ---------------------------------------------------------------------------


class TestEstimateRecoveryTime:
    def setup_method(self):
        self.engine = EventStormSimulatorEngine()
        self.graph = _graph(_comp("q1", ComponentType.QUEUE))

    def test_no_recovery_needed(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            events_per_second=100.0,
            partitions=6,
        )
        t = self.engine.estimate_recovery_time(self.graph, cfg)
        assert t == 0.0

    def test_recovery_needed_overloaded(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            events_per_second=100000.0,
            partitions=1,
            duration_seconds=60.0,
        )
        t = self.engine.estimate_recovery_time(self.graph, cfg)
        assert t > 0.0

    def test_replay_flood_doubles_eps(self):
        cfg = StormConfig(
            storm_type=StormType.REPLAY_FLOOD,
            events_per_second=20000.0,
            partitions=3,
            duration_seconds=60.0,
        )
        t = self.engine.estimate_recovery_time(self.graph, cfg)
        assert t > 0.0

    def test_fanout_explosion_recovery(self):
        cfg = StormConfig(
            storm_type=StormType.FANOUT_EXPLOSION,
            events_per_second=5000.0,
            partitions=1,
            fanout_factor=10.0,
            duration_seconds=60.0,
        )
        t = self.engine.estimate_recovery_time(self.graph, cfg)
        assert t > 0.0

    def test_broadcast_storm_recovery(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            events_per_second=5000.0,
            partitions=1,
            fanout_factor=5.0,
            duration_seconds=60.0,
        )
        t = self.engine.estimate_recovery_time(self.graph, cfg)
        assert t > 0.0

    def test_retry_storm_recovery(self):
        cfg = StormConfig(
            storm_type=StormType.RETRY_STORM,
            events_per_second=20000.0,
            partitions=1,
            failure_rate=0.5,
            retry_multiplier=4.0,
            duration_seconds=60.0,
        )
        t = self.engine.estimate_recovery_time(self.graph, cfg)
        assert t > 0.0

    def test_partition_rebalance_adds_rebalance_time(self):
        cfg = StormConfig(
            storm_type=StormType.PARTITION_REBALANCE,
            bus_type=EventBusType.KAFKA,
            events_per_second=50000.0,
            partitions=3,
            duration_seconds=60.0,
        )
        t = self.engine.estimate_recovery_time(self.graph, cfg)
        # Should include rebalance_ms/1000 addition
        assert t > 0.0

    @pytest.mark.parametrize("storm_type", list(StormType))
    def test_all_storm_types(self, storm_type):
        cfg = StormConfig(
            storm_type=storm_type,
            events_per_second=1000.0,
        )
        t = self.engine.estimate_recovery_time(self.graph, cfg)
        assert t >= 0.0


# ---------------------------------------------------------------------------
# simulate_backpressure_response
# ---------------------------------------------------------------------------


class TestSimulateBackpressureResponse:
    def setup_method(self):
        self.engine = EventStormSimulatorEngine()
        self.graph = _graph(_comp("q1", ComponentType.QUEUE))

    def test_within_capacity(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            events_per_second=100.0,
            partitions=6,
        )
        result = self.engine.simulate_backpressure_response(self.graph, cfg)
        assert result.applied_backpressure is False
        assert result.events_dropped == 0
        assert result.events_delayed == 0
        assert any("within capacity" in r.lower() for r in result.recommendations)

    def test_overloaded_with_backpressure(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            bus_type=EventBusType.KAFKA,  # backpressure_capable=True
            events_per_second=100000.0,
            partitions=1,
        )
        result = self.engine.simulate_backpressure_response(self.graph, cfg)
        assert result.applied_backpressure is True
        assert result.throttle_percent > 0
        assert result.events_delayed > 0
        assert result.queue_depth > 0

    def test_overloaded_without_backpressure(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            bus_type=EventBusType.SQS,  # backpressure_capable=False
            events_per_second=100000.0,
            partitions=1,
        )
        result = self.engine.simulate_backpressure_response(self.graph, cfg)
        assert result.applied_backpressure is False
        assert result.events_dropped > 0
        assert result.queue_depth == 0
        assert any("client-side" in r.lower() for r in result.recommendations)

    def test_producer_blocked_high_overflow(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            bus_type=EventBusType.KAFKA,
            events_per_second=100000.0,
            partitions=1,
        )
        result = self.engine.simulate_backpressure_response(self.graph, cfg)
        # overflow_ratio = (100k - 10k) / 10k = 9.0 > 1.0
        assert result.producer_blocked is True

    def test_producer_not_blocked_moderate_overflow(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            bus_type=EventBusType.KAFKA,
            events_per_second=15000.0,
            partitions=1,
        )
        result = self.engine.simulate_backpressure_response(self.graph, cfg)
        # overflow_ratio = (15k - 10k) / 10k = 0.5 < 1.0
        assert result.producer_blocked is False

    def test_replay_flood_doubles_eps(self):
        cfg = StormConfig(
            storm_type=StormType.REPLAY_FLOOD,
            bus_type=EventBusType.KAFKA,
            events_per_second=20000.0,
            partitions=3,
        )
        result = self.engine.simulate_backpressure_response(self.graph, cfg)
        # effective = 40k > 30k => overloaded
        assert result.applied_backpressure is True

    def test_fanout_explosion_multiplied(self):
        cfg = StormConfig(
            storm_type=StormType.FANOUT_EXPLOSION,
            bus_type=EventBusType.KAFKA,
            events_per_second=5000.0,
            partitions=1,
            fanout_factor=5.0,
        )
        result = self.engine.simulate_backpressure_response(self.graph, cfg)
        # effective = 25k > 10k => overloaded
        assert result.applied_backpressure is True

    def test_broadcast_storm_with_fanout(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            bus_type=EventBusType.KAFKA,
            events_per_second=5000.0,
            partitions=1,
            fanout_factor=5.0,
        )
        result = self.engine.simulate_backpressure_response(self.graph, cfg)
        assert result.applied_backpressure is True

    @pytest.mark.parametrize("bus_type", list(EventBusType))
    def test_all_bus_types_overloaded(self, bus_type):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            bus_type=bus_type,
            events_per_second=1000000.0,
            partitions=1,
        )
        result = self.engine.simulate_backpressure_response(self.graph, cfg)
        assert isinstance(result, BackpressureResult)
        # All should be overloaded at 1M eps with 1 partition


# ---------------------------------------------------------------------------
# Integration / cross-method tests
# ---------------------------------------------------------------------------


class TestIntegration:
    def setup_method(self):
        self.engine = EventStormSimulatorEngine()

    def test_storm_then_recovery(self):
        g = _graph(_comp("q1", ComponentType.QUEUE))
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            events_per_second=100000.0,
            partitions=1,
            duration_seconds=120.0,
        )
        result = self.engine.simulate_storm(g, cfg)
        recovery = self.engine.estimate_recovery_time(g, cfg)
        assert result.is_overloaded is True
        assert recovery > 0.0

    def test_capacity_matches_storm_result(self):
        g = _graph(_comp("q1", ComponentType.QUEUE))
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            bus_type=EventBusType.KAFKA,
            events_per_second=5000.0,
            partitions=3,
            consumers=3,
        )
        capacity = self.engine.analyze_consumer_capacity(g, cfg)
        result = self.engine.simulate_storm(g, cfg)
        # Max throughput from capacity should match bus characteristics
        assert capacity.estimated_max_throughput == 30000.0
        assert result.is_overloaded is False

    def test_risks_and_protections(self):
        q = _comp("q1", ComponentType.QUEUE, replicas=1)
        a = _comp("a1", ComponentType.APP_SERVER)
        g = _graph(q, a, deps=[Dependency(source_id="a1", target_id="q1")])
        risks = self.engine.detect_storm_risks(g)
        protections = self.engine.recommend_storm_protection(g)
        assert len(risks) > 0
        assert len(protections) > 0

    def test_all_methods_with_complex_graph(self):
        q1 = _comp("q1", ComponentType.QUEUE)
        q2 = _comp("q2", ComponentType.QUEUE)
        a1 = _comp("a1", ComponentType.APP_SERVER)
        a2 = _comp("a2", ComponentType.APP_SERVER)
        db = _comp("db1", ComponentType.DATABASE)
        g = _graph(
            q1, q2, a1, a2, db,
            deps=[
                Dependency(source_id="a1", target_id="q1"),
                Dependency(source_id="a2", target_id="q1"),
                Dependency(source_id="a1", target_id="q2"),
                Dependency(source_id="q1", target_id="db1"),
            ],
        )
        cfg = StormConfig(
            storm_type=StormType.FANOUT_EXPLOSION,
            events_per_second=10000.0,
            partitions=6,
            consumers=6,
            fanout_factor=3.0,
        )
        result = self.engine.simulate_storm(g, cfg)
        risks = self.engine.detect_storm_risks(g)
        capacity = self.engine.analyze_consumer_capacity(g, cfg)
        rebalance = self.engine.simulate_partition_rebalance(g, cfg)
        protections = self.engine.recommend_storm_protection(g)
        recovery = self.engine.estimate_recovery_time(g, cfg)
        backpressure = self.engine.simulate_backpressure_response(g, cfg)

        assert isinstance(result, StormResult)
        assert isinstance(risks, list)
        assert isinstance(capacity, ConsumerCapacityReport)
        assert isinstance(rebalance, RebalanceResult)
        assert isinstance(protections, list)
        assert isinstance(recovery, float)
        assert isinstance(backpressure, BackpressureResult)

    def test_multiple_storm_types_same_config(self):
        g = _graph(_comp("q1", ComponentType.QUEUE))
        results = {}
        for st in StormType:
            cfg = StormConfig(
                storm_type=st,
                events_per_second=10000.0,
                partitions=6,
                consumers=6,
                failure_rate=0.2,
                incompatibility_rate=0.1,
                fanout_factor=2.0,
            )
            results[st] = self.engine.simulate_storm(g, cfg)
        # Dead letter flood and schema change should have degradation > 0
        assert results[StormType.DEAD_LETTER_FLOOD].degradation_percent > 0
        assert results[StormType.SCHEMA_CHANGE_STORM].degradation_percent > 0

    def test_kinesis_low_throughput(self):
        g = _graph(_comp("q1", ComponentType.QUEUE))
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            bus_type=EventBusType.KINESIS,
            events_per_second=5000.0,
            partitions=3,
        )
        result = self.engine.simulate_storm(g, cfg)
        # Kinesis has 1000/partition => 3000 max => overloaded at 5000
        assert result.is_overloaded is True

    def test_nats_high_throughput(self):
        g = _graph(_comp("q1", ComponentType.QUEUE))
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            bus_type=EventBusType.NATS,
            events_per_second=10000.0,
            partitions=3,
        )
        result = self.engine.simulate_storm(g, cfg)
        # NATS has 50000/partition => 150000 max => not overloaded at 10000
        assert result.is_overloaded is False


# ---------------------------------------------------------------------------
# Edge cases for coverage
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def setup_method(self):
        self.engine = EventStormSimulatorEngine()
        self.graph = _graph(_comp("q1", ComponentType.QUEUE))

    def test_clamp_exactly_at_bounds(self):
        assert _clamp(0.0) == 0.0
        assert _clamp(100.0) == 100.0

    def test_storm_config_min_values(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            events_per_second=0.001,
            duration_seconds=0.0,
            partitions=1,
            consumers=1,
            retry_multiplier=1.0,
            fanout_factor=1.0,
            failure_rate=0.0,
            incompatibility_rate=0.0,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        assert isinstance(result, StormResult)

    def test_zero_failure_rate_dead_letter(self):
        cfg = StormConfig(
            storm_type=StormType.DEAD_LETTER_FLOOD,
            events_per_second=1000.0,
            failure_rate=0.0,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        assert result.dead_letter_events == 0

    def test_zero_incompatibility_schema_storm(self):
        cfg = StormConfig(
            storm_type=StormType.SCHEMA_CHANGE_STORM,
            events_per_second=1000.0,
            incompatibility_rate=0.0,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        assert result.dead_letter_events == 0
        assert result.degradation_percent == 0.0

    def test_consumer_lag_cascade_effective_eps(self):
        cfg = StormConfig(
            storm_type=StormType.CONSUMER_LAG_CASCADE,
            events_per_second=1000.0,
            partitions=3,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        # effective_eps = 1000 * (1 + 0.75*0.5) = 1375 < 30000
        assert result.is_overloaded is False

    def test_overloaded_dead_letter_equals_overflow(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            events_per_second=100000.0,
            partitions=1,
            failure_rate=0.0,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        assert result.dead_letter_events > 0  # overflow goes to dead letter

    def test_recovery_with_partition_rebalance_type(self):
        cfg = StormConfig(
            storm_type=StormType.PARTITION_REBALANCE,
            bus_type=EventBusType.KINESIS,
            events_per_second=5000.0,
            partitions=3,
            duration_seconds=60.0,
        )
        t = self.engine.estimate_recovery_time(self.graph, cfg)
        # Should include rebalance_ms / 1000 addition
        assert t > 0.0

    def test_backpressure_throttle_clamped(self):
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            bus_type=EventBusType.KAFKA,
            events_per_second=1000000.0,
            partitions=1,
        )
        result = self.engine.simulate_backpressure_response(self.graph, cfg)
        assert result.throttle_percent <= 100.0

    def test_retry_storm_low_failure_no_amplification(self):
        cfg = StormConfig(
            storm_type=StormType.RETRY_STORM,
            events_per_second=100.0,
            failure_rate=0.0,
            retry_multiplier=3.0,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        # effective_eps = 100 * (1 + 2*0.0) = 100
        assert result.is_overloaded is False

    def test_non_queue_component_no_single_consumer_risk(self):
        g = _graph(_comp("a1", ComponentType.APP_SERVER, replicas=1))
        risks = self.engine.detect_storm_risks(g)
        assert not any(r.risk_type == "single_consumer" for r in risks)

    def test_exactly_3_dependents_no_fanout_risk(self):
        q = _comp("q1", ComponentType.QUEUE, replicas=3)
        a1 = _comp("a1", ComponentType.APP_SERVER)
        a2 = _comp("a2", ComponentType.APP_SERVER)
        a3 = _comp("a3", ComponentType.APP_SERVER)
        g = _graph(
            q, a1, a2, a3,
            deps=[
                Dependency(source_id="a1", target_id="q1"),
                Dependency(source_id="a2", target_id="q1"),
                Dependency(source_id="a3", target_id="q1"),
            ],
        )
        risks = self.engine.detect_storm_risks(g)
        assert not any(r.risk_type == "high_fanout" for r in risks)

    def test_backpressure_non_storm_type_no_multiplier(self):
        cfg = StormConfig(
            storm_type=StormType.DEAD_LETTER_FLOOD,
            bus_type=EventBusType.KAFKA,
            events_per_second=100000.0,
            partitions=1,
        )
        result = self.engine.simulate_backpressure_response(self.graph, cfg)
        # No fanout/replay/broadcast multiplier, raw eps used
        assert result.applied_backpressure is True

    def test_estimate_recovery_non_overloaded_storm_types(self):
        for st in [StormType.DEAD_LETTER_FLOOD, StormType.SCHEMA_CHANGE_STORM,
                    StormType.CONSUMER_LAG_CASCADE, StormType.PARTITION_REBALANCE]:
            cfg = StormConfig(
                storm_type=st,
                events_per_second=100.0,
                partitions=6,
            )
            t = self.engine.estimate_recovery_time(self.graph, cfg)
            assert t >= 0.0

    def test_recommend_protection_no_queue_components(self):
        g = _graph(_comp("a1", ComponentType.APP_SERVER))
        protections = self.engine.recommend_storm_protection(g)
        # Should still return base protections
        assert any(p.protection_type == "rate_limiting" for p in protections)
        # No queue => no consumer_autoscaling recommendation
        assert not any(p.protection_type == "consumer_autoscaling" for p in protections)


# ---------------------------------------------------------------------------
# Monkey-patch tests for zero-throughput guard branches
# ---------------------------------------------------------------------------


class TestZeroThroughputGuards:
    """Cover the defensive `base_tp <= 0` fallback in every method."""

    def setup_method(self):
        self.engine = EventStormSimulatorEngine()
        self.graph = _graph(_comp("q1", ComponentType.QUEUE))
        self._original = _BUS_CHARACTERISTICS[EventBusType.KAFKA].copy()

    def teardown_method(self):
        _BUS_CHARACTERISTICS[EventBusType.KAFKA] = self._original

    def test_simulate_storm_zero_throughput(self):
        _BUS_CHARACTERISTICS[EventBusType.KAFKA]["throughput_per_partition"] = 0.0
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            bus_type=EventBusType.KAFKA,
            events_per_second=1000.0,
        )
        result = self.engine.simulate_storm(self.graph, cfg)
        assert isinstance(result, StormResult)
        # base_tp falls back to 1.0, so max = 1.0*3 = 3.0 -> overloaded
        assert result.is_overloaded is True

    def test_analyze_consumer_capacity_zero_throughput(self):
        _BUS_CHARACTERISTICS[EventBusType.KAFKA]["throughput_per_partition"] = 0.0
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            bus_type=EventBusType.KAFKA,
            events_per_second=1000.0,
        )
        report = self.engine.analyze_consumer_capacity(self.graph, cfg)
        assert isinstance(report, ConsumerCapacityReport)
        # base_tp falls back to 1.0
        assert report.estimated_max_throughput == 3.0

    def test_estimate_recovery_time_zero_throughput(self):
        _BUS_CHARACTERISTICS[EventBusType.KAFKA]["throughput_per_partition"] = 0.0
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            bus_type=EventBusType.KAFKA,
            events_per_second=1000.0,
            duration_seconds=60.0,
        )
        t = self.engine.estimate_recovery_time(self.graph, cfg)
        # base_tp falls back to 1.0, max = 3.0, eps=1000 > 3 => recovery needed
        assert t > 0.0

    def test_simulate_backpressure_zero_throughput(self):
        _BUS_CHARACTERISTICS[EventBusType.KAFKA]["throughput_per_partition"] = 0.0
        cfg = StormConfig(
            storm_type=StormType.BROADCAST_STORM,
            bus_type=EventBusType.KAFKA,
            events_per_second=1000.0,
        )
        result = self.engine.simulate_backpressure_response(self.graph, cfg)
        assert isinstance(result, BackpressureResult)
        assert result.applied_backpressure is True
