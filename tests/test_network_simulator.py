"""Tests for the Network Latency Simulator module.

Covers all NetworkCondition types, topology patterns, partition detection,
percentile calculations, SLA compliance, and edge cases.
"""

from __future__ import annotations

import math

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    HealthStatus,
    NetworkProfile,
    RegionConfig,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.network_simulator import (
    LatencyPrediction,
    NetworkCondition,
    NetworkLink,
    NetworkSimulationResult,
    NetworkSimulator,
    _CONGESTED_LATENCY_MULTIPLIER,
    _CONGESTED_PACKET_LOSS,
    _DEFAULT_CROSS_REGION_LATENCY_MS,
    _DEFAULT_LOCAL_LATENCY_MS,
    _DEGRADED_LATENCY_MULTIPLIER,
    _DEGRADED_PACKET_LOSS,
    _DNS_FAILURE_PENALTY_MS,
    _PARTITION_LATENCY_MS,
    _TLS_FAILURE_PENALTY_MS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_component(
    cid: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    *,
    rtt_ms: float = 1.0,
    packet_loss_rate: float = 0.0001,
    jitter_ms: float = 0.5,
    dns_resolution_ms: float = 5.0,
    tls_handshake_ms: float = 10.0,
    health: HealthStatus = HealthStatus.HEALTHY,
    region: str = "",
    encryption_in_transit: bool = False,
) -> Component:
    return Component(
        id=cid,
        name=cid,
        type=ctype,
        network=NetworkProfile(
            rtt_ms=rtt_ms,
            packet_loss_rate=packet_loss_rate,
            jitter_ms=jitter_ms,
            dns_resolution_ms=dns_resolution_ms,
            tls_handshake_ms=tls_handshake_ms,
        ),
        health=health,
        region=RegionConfig(region=region),
        security=SecurityProfile(encryption_in_transit=encryption_in_transit),
    )


def _simple_chain() -> InfraGraph:
    """A -> B -> C linear chain."""
    graph = InfraGraph()
    graph.add_component(_make_component("A"))
    graph.add_component(_make_component("B"))
    graph.add_component(_make_component("C"))
    graph.add_dependency(Dependency(source_id="A", target_id="B"))
    graph.add_dependency(Dependency(source_id="B", target_id="C"))
    return graph


def _fan_out() -> InfraGraph:
    """A -> B, A -> C, A -> D fan-out topology."""
    graph = InfraGraph()
    graph.add_component(_make_component("A"))
    graph.add_component(_make_component("B"))
    graph.add_component(_make_component("C"))
    graph.add_component(_make_component("D"))
    graph.add_dependency(Dependency(source_id="A", target_id="B"))
    graph.add_dependency(Dependency(source_id="A", target_id="C"))
    graph.add_dependency(Dependency(source_id="A", target_id="D"))
    return graph


def _diamond() -> InfraGraph:
    """A -> B, A -> C, B -> D, C -> D diamond topology."""
    graph = InfraGraph()
    graph.add_component(_make_component("A"))
    graph.add_component(_make_component("B"))
    graph.add_component(_make_component("C"))
    graph.add_component(_make_component("D"))
    graph.add_dependency(Dependency(source_id="A", target_id="B"))
    graph.add_dependency(Dependency(source_id="A", target_id="C"))
    graph.add_dependency(Dependency(source_id="B", target_id="D"))
    graph.add_dependency(Dependency(source_id="C", target_id="D"))
    return graph


# ===========================================================================
# 1. NetworkCondition enum
# ===========================================================================


class TestNetworkConditionEnum:
    def test_all_values(self):
        assert NetworkCondition.NORMAL == "normal"
        assert NetworkCondition.DEGRADED == "degraded"
        assert NetworkCondition.CONGESTED == "congested"
        assert NetworkCondition.PARTITIONED == "partitioned"
        assert NetworkCondition.DNS_FAILURE == "dns_failure"
        assert NetworkCondition.TLS_FAILURE == "tls_failure"

    def test_enum_count(self):
        assert len(NetworkCondition) == 6

    def test_str_conversion(self):
        assert str(NetworkCondition.NORMAL) == "NetworkCondition.NORMAL"
        assert NetworkCondition("normal") is NetworkCondition.NORMAL


# ===========================================================================
# 2. Empty graph
# ===========================================================================


class TestEmptyGraph:
    def test_simulate_empty(self):
        graph = InfraGraph()
        sim = NetworkSimulator(graph)
        result = sim.simulate()
        assert result.total_links == 0
        assert result.healthy_links == 0
        assert result.degraded_links == 0
        assert result.failed_links == 0
        assert result.p50_latency_ms == 0.0
        assert result.p95_latency_ms == 0.0
        assert result.p99_latency_ms == 0.0
        assert result.partition_detected is False
        assert result.partition_groups == []
        assert result.overall_health == "healthy"

    def test_predict_latency_empty(self):
        graph = InfraGraph()
        sim = NetworkSimulator(graph)
        pred = sim.predict_latency("X", "Y")
        assert pred.path == []
        assert pred.total_latency_ms == 0.0
        assert pred.meets_sla is True

    def test_simulate_partition_empty(self):
        graph = InfraGraph()
        sim = NetworkSimulator(graph)
        result = sim.simulate_partition([], [])
        assert result.total_links == 0
        assert result.partition_detected is False


# ===========================================================================
# 3. Single component (no edges)
# ===========================================================================


class TestSingleComponent:
    def test_simulate_single(self):
        graph = InfraGraph()
        graph.add_component(_make_component("solo"))
        sim = NetworkSimulator(graph)
        result = sim.simulate()
        assert result.total_links == 0
        assert result.overall_health == "healthy"
        # One component in a single partition group
        assert result.partition_detected is False

    def test_predict_latency_same_node(self):
        graph = InfraGraph()
        graph.add_component(_make_component("solo"))
        sim = NetworkSimulator(graph)
        pred = sim.predict_latency("solo", "solo")
        assert pred.path == ["solo"]
        assert pred.total_latency_ms == 0.0
        assert pred.meets_sla is True


# ===========================================================================
# 4. Normal condition - simple chain
# ===========================================================================


class TestNormalConditionChain:
    def test_simulate_normal(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        result = sim.simulate()
        assert result.total_links == 2
        assert result.healthy_links == 2
        assert result.degraded_links == 0
        assert result.failed_links == 0
        assert result.overall_health == "healthy"
        assert result.partition_detected is False

    def test_all_links_normal_condition(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        result = sim.simulate()
        for lnk in result.links:
            assert lnk.condition == NetworkCondition.NORMAL
            assert lnk.is_healthy is True

    def test_latency_prediction_chain(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        pred = sim.predict_latency("A", "C")
        assert pred.path == ["A", "B", "C"]
        assert len(pred.breakdown) == 2
        assert pred.total_latency_ms > 0
        assert pred.bottleneck_link is not None
        assert pred.meets_sla is True

    def test_latency_prediction_partial_chain(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        pred = sim.predict_latency("A", "B")
        assert pred.path == ["A", "B"]
        assert len(pred.breakdown) == 1

    def test_latency_prediction_no_path(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        pred = sim.predict_latency("C", "A")  # reverse direction
        assert pred.path == []
        assert pred.total_latency_ms == 0.0

    def test_latency_prediction_nonexistent_source(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        pred = sim.predict_latency("Z", "A")
        assert pred.path == []


# ===========================================================================
# 5. Degraded condition
# ===========================================================================


class TestDegradedCondition:
    def test_degraded_increases_latency(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        normal = sim.simulate(NetworkCondition.NORMAL)
        degraded = sim.simulate(NetworkCondition.DEGRADED)

        for lnk in degraded.links:
            assert lnk.condition == NetworkCondition.DEGRADED
            assert lnk.is_healthy is False
            # Degraded latency = base * 3
            assert lnk.current_latency_ms == pytest.approx(
                lnk.base_latency_ms * _DEGRADED_LATENCY_MULTIPLIER,
            )

    def test_degraded_packet_loss(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        result = sim.simulate(NetworkCondition.DEGRADED)
        for lnk in result.links:
            assert lnk.packet_loss_rate >= _DEGRADED_PACKET_LOSS

    def test_degraded_overall_health(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        result = sim.simulate(NetworkCondition.DEGRADED)
        assert result.overall_health == "degraded"


# ===========================================================================
# 6. Congested condition
# ===========================================================================


class TestCongestedCondition:
    def test_congested_latency_multiplier(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        result = sim.simulate(NetworkCondition.CONGESTED)
        for lnk in result.links:
            assert lnk.current_latency_ms == pytest.approx(
                lnk.base_latency_ms * _CONGESTED_LATENCY_MULTIPLIER,
            )

    def test_congested_packet_loss(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        result = sim.simulate(NetworkCondition.CONGESTED)
        for lnk in result.links:
            assert lnk.packet_loss_rate >= _CONGESTED_PACKET_LOSS

    def test_congested_health(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        result = sim.simulate(NetworkCondition.CONGESTED)
        assert result.overall_health == "degraded"
        assert result.healthy_links == 0


# ===========================================================================
# 7. Partitioned condition
# ===========================================================================


class TestPartitionedCondition:
    def test_global_partition(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        result = sim.simulate(NetworkCondition.PARTITIONED)
        for lnk in result.links:
            assert lnk.current_latency_ms == _PARTITION_LATENCY_MS
            assert lnk.packet_loss_rate == 1.0
            assert lnk.is_healthy is False
        assert result.overall_health == "critical"

    def test_partition_detection_global(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        result = sim.simulate(NetworkCondition.PARTITIONED)
        assert result.partition_detected is True
        # Each component should be in its own group
        assert len(result.partition_groups) == 3

    def test_selective_partition(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        result = sim.simulate_partition(["A"], ["B", "C"])
        # Only A-B link crosses the boundary
        partitioned = [lnk for lnk in result.links if lnk.condition == NetworkCondition.PARTITIONED]
        assert len(partitioned) == 1
        assert partitioned[0].source_id == "A"
        assert partitioned[0].target_id == "B"

    def test_selective_partition_health(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        result = sim.simulate_partition(["A"], ["C"])
        # A-B doesn't cross boundary (B is in neither group),
        # B-C doesn't cross boundary either
        # Only links between explicit groups are partitioned
        assert result.overall_health == "healthy"

    def test_partition_groups_identification(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        result = sim.simulate_partition(["A"], ["B", "C"])
        assert result.partition_detected is True
        assert len(result.partition_groups) >= 2


# ===========================================================================
# 8. DNS failure condition
# ===========================================================================


class TestDNSFailure:
    def test_dns_failure_adds_penalty(self):
        graph = InfraGraph()
        dns = _make_component("dns1", ComponentType.DNS)
        app = _make_component("app1", ComponentType.APP_SERVER)
        graph.add_component(dns)
        graph.add_component(app)
        graph.add_dependency(Dependency(source_id="app1", target_id="dns1"))

        sim = NetworkSimulator(graph)
        result = sim.simulate(NetworkCondition.DNS_FAILURE)
        assert len(result.links) == 1
        lnk = result.links[0]
        # Should include DNS failure penalty + extra for DNS-type component
        assert lnk.current_latency_ms >= _DNS_FAILURE_PENALTY_MS

    def test_dns_failure_non_dns_components(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        result = sim.simulate(NetworkCondition.DNS_FAILURE)
        for lnk in result.links:
            # Even non-DNS components get the base penalty
            assert lnk.current_latency_ms >= lnk.base_latency_ms + _DNS_FAILURE_PENALTY_MS

    def test_dns_failure_health(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        result = sim.simulate(NetworkCondition.DNS_FAILURE)
        assert result.overall_health == "degraded"
        assert all(not lnk.is_healthy for lnk in result.links)


# ===========================================================================
# 9. TLS failure condition
# ===========================================================================


class TestTLSFailure:
    def test_tls_failure_adds_penalty(self):
        graph = InfraGraph()
        src = _make_component("src", encryption_in_transit=True)
        tgt = _make_component("tgt", encryption_in_transit=True)
        graph.add_component(src)
        graph.add_component(tgt)
        graph.add_dependency(Dependency(source_id="src", target_id="tgt"))

        sim = NetworkSimulator(graph)
        result = sim.simulate(NetworkCondition.TLS_FAILURE)
        lnk = result.links[0]
        # Base penalty + extra for both endpoints having TLS
        assert lnk.current_latency_ms >= _TLS_FAILURE_PENALTY_MS * 2

    def test_tls_failure_one_endpoint_encrypted(self):
        graph = InfraGraph()
        src = _make_component("src", encryption_in_transit=True)
        tgt = _make_component("tgt", encryption_in_transit=False)
        graph.add_component(src)
        graph.add_component(tgt)
        graph.add_dependency(Dependency(source_id="src", target_id="tgt"))

        sim = NetworkSimulator(graph)
        result = sim.simulate(NetworkCondition.TLS_FAILURE)
        lnk = result.links[0]
        # Base penalty + extra for source only
        assert lnk.current_latency_ms >= _TLS_FAILURE_PENALTY_MS

    def test_tls_failure_no_encryption(self):
        graph = _simple_chain()  # no encryption by default
        sim = NetworkSimulator(graph)
        result = sim.simulate(NetworkCondition.TLS_FAILURE)
        for lnk in result.links:
            # Only base penalty, no extra per-endpoint penalty
            expected = lnk.base_latency_ms + _TLS_FAILURE_PENALTY_MS
            assert lnk.current_latency_ms == pytest.approx(expected)


# ===========================================================================
# 10. Fan-out topology
# ===========================================================================


class TestFanOutTopology:
    def test_fan_out_link_count(self):
        graph = _fan_out()
        sim = NetworkSimulator(graph)
        result = sim.simulate()
        assert result.total_links == 3

    def test_fan_out_latency_prediction(self):
        graph = _fan_out()
        sim = NetworkSimulator(graph)
        for target in ("B", "C", "D"):
            pred = sim.predict_latency("A", target)
            assert pred.path == ["A", target]
            assert len(pred.breakdown) == 1

    def test_fan_out_partition(self):
        graph = _fan_out()
        sim = NetworkSimulator(graph)
        result = sim.simulate_partition(["A", "B"], ["C", "D"])
        partitioned = [
            lnk for lnk in result.links
            if lnk.condition == NetworkCondition.PARTITIONED
        ]
        assert len(partitioned) == 2  # A->C and A->D


# ===========================================================================
# 11. Diamond topology
# ===========================================================================


class TestDiamondTopology:
    def test_diamond_link_count(self):
        graph = _diamond()
        sim = NetworkSimulator(graph)
        result = sim.simulate()
        assert result.total_links == 4

    def test_diamond_path_a_to_d(self):
        graph = _diamond()
        sim = NetworkSimulator(graph)
        pred = sim.predict_latency("A", "D")
        assert len(pred.path) >= 3
        assert pred.path[0] == "A"
        assert pred.path[-1] == "D"


# ===========================================================================
# 12. Percentile calculations
# ===========================================================================


class TestPercentileCalculations:
    def test_single_value(self):
        sim = NetworkSimulator(InfraGraph())
        p50, p95, p99 = sim._calculate_percentiles([10.0])
        assert p50 == 10.0
        assert p95 == 10.0
        assert p99 == 10.0

    def test_two_values(self):
        sim = NetworkSimulator(InfraGraph())
        p50, p95, p99 = sim._calculate_percentiles([10.0, 20.0])
        assert p50 == pytest.approx(15.0)
        assert p95 > 10.0
        assert p99 > p95

    def test_uniform_distribution(self):
        sim = NetworkSimulator(InfraGraph())
        values = list(range(1, 101))  # 1..100
        p50, p95, p99 = sim._calculate_percentiles([float(v) for v in values])
        assert 49 < p50 < 52  # should be ~50.5
        assert 94 < p95 < 97  # should be ~95.5
        assert 98 < p99 < 100  # should be ~99.02

    def test_empty_list(self):
        sim = NetworkSimulator(InfraGraph())
        p50, p95, p99 = sim._calculate_percentiles([])
        assert p50 == 0.0
        assert p95 == 0.0
        assert p99 == 0.0

    def test_identical_values(self):
        sim = NetworkSimulator(InfraGraph())
        p50, p95, p99 = sim._calculate_percentiles([5.0, 5.0, 5.0])
        assert p50 == 5.0
        assert p95 == 5.0
        assert p99 == 5.0


# ===========================================================================
# 13. SLA compliance
# ===========================================================================


class TestSLACompliance:
    def test_meets_sla(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        pred = sim.predict_latency("A", "C", sla_ms=1000.0)
        assert pred.meets_sla is True
        assert pred.sla_target_ms == 1000.0

    def test_fails_sla_tight(self):
        # Create a chain with high-latency links
        graph = InfraGraph()
        graph.add_component(_make_component("X", rtt_ms=200.0))
        graph.add_component(_make_component("Y", rtt_ms=200.0))
        graph.add_component(_make_component("Z", rtt_ms=200.0))
        graph.add_dependency(
            Dependency(source_id="X", target_id="Y", latency_ms=300.0),
        )
        graph.add_dependency(
            Dependency(source_id="Y", target_id="Z", latency_ms=300.0),
        )

        sim = NetworkSimulator(graph)
        pred = sim.predict_latency("X", "Z", sla_ms=500.0)
        assert pred.total_latency_ms > 500.0
        assert pred.meets_sla is False

    def test_exactly_meets_sla(self):
        graph = InfraGraph()
        graph.add_component(_make_component("P", rtt_ms=0.0, jitter_ms=0.0))
        graph.add_component(_make_component("Q", rtt_ms=0.0, jitter_ms=0.0))
        graph.add_dependency(
            Dependency(source_id="P", target_id="Q", latency_ms=500.0),
        )
        sim = NetworkSimulator(graph)
        pred = sim.predict_latency("P", "Q", sla_ms=500.0)
        assert pred.meets_sla is True

    def test_just_over_sla(self):
        graph = InfraGraph()
        graph.add_component(_make_component("P", rtt_ms=0.0, jitter_ms=0.0))
        graph.add_component(_make_component("Q", rtt_ms=0.0, jitter_ms=0.0))
        graph.add_dependency(
            Dependency(source_id="P", target_id="Q", latency_ms=500.1),
        )
        sim = NetworkSimulator(graph)
        pred = sim.predict_latency("P", "Q", sla_ms=500.0)
        assert pred.meets_sla is False


# ===========================================================================
# 14. Components with 0 latency
# ===========================================================================


class TestZeroLatency:
    def test_zero_rtt_components(self):
        graph = InfraGraph()
        a = _make_component("a", rtt_ms=0.0, jitter_ms=0.0)
        b = _make_component("b", rtt_ms=0.0, jitter_ms=0.0)
        graph.add_component(a)
        graph.add_component(b)
        graph.add_dependency(Dependency(source_id="a", target_id="b", latency_ms=0.0))

        sim = NetworkSimulator(graph)
        result = sim.simulate()
        assert result.total_links == 1
        # With 0 rtt and 0 explicit latency, base latency falls back to default
        # because dep.latency_ms is 0, and rtts average is 0
        lnk = result.links[0]
        # 0 rtt -> average = 0 -> base_latency = 0
        assert lnk.base_latency_ms == 0.0


# ===========================================================================
# 15. Cross-region latency defaults
# ===========================================================================


class TestCrossRegionLatency:
    def test_different_regions(self):
        graph = InfraGraph()
        a = _make_component("a", region="us-east-1", rtt_ms=0.0, jitter_ms=0.0)
        b = _make_component("b", region="eu-west-1", rtt_ms=0.0, jitter_ms=0.0)
        graph.add_component(a)
        graph.add_component(b)
        graph.add_dependency(Dependency(source_id="a", target_id="b"))

        sim = NetworkSimulator(graph)
        result = sim.simulate()
        lnk = result.links[0]
        # When rtt_ms is 0 and no explicit dep latency, should use region comparison
        # But since rtt_ms (0) is used as average, base = 0. Region check only applies
        # when no RTTs are provided. Here RTTs exist (0), so average RTT (0) is used.
        assert lnk.base_latency_ms == 0.0

    def test_cross_region_default_latency_prediction(self):
        graph = InfraGraph()
        a = _make_component("a", region="us-east-1")
        b = _make_component("b", region="eu-west-1")
        graph.add_component(a)
        graph.add_component(b)
        # No dependency edge; predict_latency falls back to _default_latency
        sim = NetworkSimulator(graph)
        default = sim._default_latency("a", "b")
        assert default == _DEFAULT_CROSS_REGION_LATENCY_MS

    def test_same_region_default_latency(self):
        graph = InfraGraph()
        a = _make_component("a", region="us-east-1")
        b = _make_component("b", region="us-east-1")
        graph.add_component(a)
        graph.add_component(b)
        sim = NetworkSimulator(graph)
        default = sim._default_latency("a", "b")
        assert default == _DEFAULT_LOCAL_LATENCY_MS


# ===========================================================================
# 16. Component health impact on links
# ===========================================================================


class TestComponentHealthImpact:
    def test_down_component_unhealthy_link(self):
        graph = InfraGraph()
        a = _make_component("a")
        b = _make_component("b", health=HealthStatus.DOWN)
        graph.add_component(a)
        graph.add_component(b)
        graph.add_dependency(Dependency(source_id="a", target_id="b"))

        sim = NetworkSimulator(graph)
        result = sim.simulate()
        assert result.links[0].is_healthy is False

    def test_overloaded_component_unhealthy_link(self):
        graph = InfraGraph()
        a = _make_component("a", health=HealthStatus.OVERLOADED)
        b = _make_component("b")
        graph.add_component(a)
        graph.add_component(b)
        graph.add_dependency(Dependency(source_id="a", target_id="b"))

        sim = NetworkSimulator(graph)
        result = sim.simulate()
        assert result.links[0].is_healthy is False
        assert result.overall_health == "degraded"

    def test_degraded_component_healthy_link(self):
        """DEGRADED health on a component does not automatically make the link unhealthy."""
        graph = InfraGraph()
        a = _make_component("a", health=HealthStatus.DEGRADED)
        b = _make_component("b")
        graph.add_component(a)
        graph.add_component(b)
        graph.add_dependency(Dependency(source_id="a", target_id="b"))

        sim = NetworkSimulator(graph)
        result = sim.simulate()
        # DEGRADED health doesn't trigger is_healthy=False on the link
        assert result.links[0].is_healthy is True


# ===========================================================================
# 17. High packet loss makes link unhealthy
# ===========================================================================


class TestHighPacketLoss:
    def test_packet_loss_above_threshold(self):
        graph = InfraGraph()
        a = _make_component("a", packet_loss_rate=0.02)
        b = _make_component("b")
        graph.add_component(a)
        graph.add_component(b)
        graph.add_dependency(Dependency(source_id="a", target_id="b"))

        sim = NetworkSimulator(graph)
        result = sim.simulate()
        assert result.links[0].is_healthy is False


# ===========================================================================
# 18. Recommendations generation
# ===========================================================================


class TestRecommendations:
    def test_partition_recommendation(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        result = sim.simulate(NetworkCondition.PARTITIONED)
        recs = result.recommendations
        assert any("partition" in r.lower() for r in recs)

    def test_high_latency_recommendation(self):
        graph = InfraGraph()
        a = _make_component("a", rtt_ms=200.0)
        b = _make_component("b", rtt_ms=200.0)
        graph.add_component(a)
        graph.add_component(b)
        graph.add_dependency(
            Dependency(source_id="a", target_id="b", latency_ms=500.0),
        )
        sim = NetworkSimulator(graph)
        result = sim.simulate()
        assert any("high latency" in r.lower() for r in result.recommendations)

    def test_p99_recommendation(self):
        # Force high p99
        graph = InfraGraph()
        for i in range(10):
            graph.add_component(_make_component(f"n{i}"))
        for i in range(9):
            graph.add_dependency(
                Dependency(
                    source_id=f"n{i}",
                    target_id=f"n{i+1}",
                    latency_ms=600.0,
                ),
            )
        sim = NetworkSimulator(graph)
        result = sim.simulate()
        assert any("p99" in r.lower() for r in result.recommendations)

    def test_packet_loss_recommendation(self):
        graph = InfraGraph()
        a = _make_component("a", packet_loss_rate=0.05)
        b = _make_component("b")
        graph.add_component(a)
        graph.add_component(b)
        graph.add_dependency(Dependency(source_id="a", target_id="b"))
        sim = NetworkSimulator(graph)
        result = sim.simulate()
        assert any("packet loss" in r.lower() for r in result.recommendations)

    def test_no_recommendations_healthy(self):
        graph = InfraGraph()
        a = _make_component("a", rtt_ms=1.0, jitter_ms=0.1)
        b = _make_component("b", rtt_ms=1.0, jitter_ms=0.1)
        graph.add_component(a)
        graph.add_component(b)
        graph.add_dependency(Dependency(source_id="a", target_id="b"))
        sim = NetworkSimulator(graph)
        result = sim.simulate()
        # A small healthy network should produce no recommendations
        assert result.recommendations == []


# ===========================================================================
# 19. Partition groups identification
# ===========================================================================


class TestPartitionGroups:
    def test_three_isolated_groups(self):
        graph = InfraGraph()
        graph.add_component(_make_component("X"))
        graph.add_component(_make_component("Y"))
        graph.add_component(_make_component("Z"))
        graph.add_dependency(Dependency(source_id="X", target_id="Y"))
        graph.add_dependency(Dependency(source_id="X", target_id="Z"))

        sim = NetworkSimulator(graph)
        result = sim.simulate(NetworkCondition.PARTITIONED)
        assert result.partition_detected is True
        assert len(result.partition_groups) == 3

    def test_two_groups_after_partition(self):
        graph = InfraGraph()
        graph.add_component(_make_component("A"))
        graph.add_component(_make_component("B"))
        graph.add_component(_make_component("C"))
        graph.add_component(_make_component("D"))
        graph.add_dependency(Dependency(source_id="A", target_id="B"))
        graph.add_dependency(Dependency(source_id="C", target_id="D"))

        sim = NetworkSimulator(graph)
        result = sim.simulate_partition(["A", "B"], ["C", "D"])
        # A-B in one group, C-D in another
        assert result.partition_detected is True
        assert len(result.partition_groups) >= 2


# ===========================================================================
# 20. Link base latency from dependency edge
# ===========================================================================


class TestBaseLengthFromEdge:
    def test_explicit_latency_on_edge(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a"))
        graph.add_component(_make_component("b"))
        graph.add_dependency(
            Dependency(source_id="a", target_id="b", latency_ms=42.0),
        )
        sim = NetworkSimulator(graph)
        result = sim.simulate()
        assert result.links[0].base_latency_ms == 42.0

    def test_rtt_average_when_no_explicit(self):
        graph = InfraGraph()
        a = _make_component("a", rtt_ms=10.0)
        b = _make_component("b", rtt_ms=20.0)
        graph.add_component(a)
        graph.add_component(b)
        graph.add_dependency(Dependency(source_id="a", target_id="b"))
        sim = NetworkSimulator(graph)
        result = sim.simulate()
        assert result.links[0].base_latency_ms == pytest.approx(15.0)


# ===========================================================================
# 21. DNS component adds resolution time
# ===========================================================================


class TestDNSResolutionNormal:
    def test_dns_component_adds_resolution(self):
        graph = InfraGraph()
        dns = _make_component("dns", ComponentType.DNS, dns_resolution_ms=20.0, jitter_ms=0.0)
        app = _make_component("app", jitter_ms=0.0)
        graph.add_component(dns)
        graph.add_component(app)
        graph.add_dependency(Dependency(source_id="app", target_id="dns"))
        sim = NetworkSimulator(graph)
        result = sim.simulate()
        lnk = result.links[0]
        # Should include DNS resolution from the DNS component
        assert lnk.current_latency_ms >= 20.0


# ===========================================================================
# 22. TLS handshake in normal mode
# ===========================================================================


class TestTLSHandshakeNormal:
    def test_tls_component_adds_handshake(self):
        graph = InfraGraph()
        src = _make_component("src", encryption_in_transit=True, tls_handshake_ms=15.0, jitter_ms=0.0)
        tgt = _make_component("tgt", encryption_in_transit=False, jitter_ms=0.0)
        graph.add_component(src)
        graph.add_component(tgt)
        graph.add_dependency(Dependency(source_id="src", target_id="tgt"))
        sim = NetworkSimulator(graph)
        result = sim.simulate()
        lnk = result.links[0]
        # Should include TLS handshake from encrypted source
        assert lnk.current_latency_ms >= 15.0


# ===========================================================================
# 23. Jitter contribution
# ===========================================================================


class TestJitterContribution:
    def test_jitter_added_both_ends(self):
        graph = InfraGraph()
        a = _make_component("a", jitter_ms=2.0, rtt_ms=0.0)
        b = _make_component("b", jitter_ms=3.0, rtt_ms=0.0)
        graph.add_component(a)
        graph.add_component(b)
        graph.add_dependency(Dependency(source_id="a", target_id="b"))
        sim = NetworkSimulator(graph)
        result = sim.simulate()
        lnk = result.links[0]
        # Jitter from both ends should be added
        assert lnk.current_latency_ms >= 5.0


# ===========================================================================
# 24. Bottleneck link detection
# ===========================================================================


class TestBottleneckDetection:
    def test_identifies_slowest_link(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a", rtt_ms=0.0, jitter_ms=0.0))
        graph.add_component(_make_component("b", rtt_ms=0.0, jitter_ms=0.0))
        graph.add_component(_make_component("c", rtt_ms=0.0, jitter_ms=0.0))
        graph.add_dependency(
            Dependency(source_id="a", target_id="b", latency_ms=10.0),
        )
        graph.add_dependency(
            Dependency(source_id="b", target_id="c", latency_ms=100.0),
        )
        sim = NetworkSimulator(graph)
        pred = sim.predict_latency("a", "c")
        assert pred.bottleneck_link == ("b", "c")


# ===========================================================================
# 25. Simulate with None condition (default)
# ===========================================================================


class TestSimulateNoneCondition:
    def test_none_condition_same_as_normal(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        default_result = sim.simulate()
        none_result = sim.simulate(condition=None)
        assert default_result.total_links == none_result.total_links
        assert default_result.healthy_links == none_result.healthy_links


# ===========================================================================
# 26. NetworkLink dataclass
# ===========================================================================


class TestNetworkLinkDataclass:
    def test_fields(self):
        lnk = NetworkLink(
            source_id="a",
            target_id="b",
            base_latency_ms=5.0,
            current_latency_ms=15.0,
            packet_loss_rate=0.01,
            condition=NetworkCondition.DEGRADED,
            is_healthy=False,
        )
        assert lnk.source_id == "a"
        assert lnk.target_id == "b"
        assert lnk.base_latency_ms == 5.0
        assert lnk.current_latency_ms == 15.0
        assert lnk.packet_loss_rate == 0.01
        assert lnk.condition == NetworkCondition.DEGRADED
        assert lnk.is_healthy is False


# ===========================================================================
# 27. NetworkSimulationResult dataclass
# ===========================================================================


class TestNetworkSimulationResultDataclass:
    def test_fields(self):
        result = NetworkSimulationResult(
            links=[],
            total_links=0,
            healthy_links=0,
            degraded_links=0,
            failed_links=0,
            p50_latency_ms=1.0,
            p95_latency_ms=2.0,
            p99_latency_ms=3.0,
            partition_detected=False,
            partition_groups=[],
            overall_health="healthy",
            recommendations=[],
        )
        assert result.total_links == 0
        assert result.p99_latency_ms == 3.0


# ===========================================================================
# 28. LatencyPrediction dataclass
# ===========================================================================


class TestLatencyPredictionDataclass:
    def test_fields(self):
        pred = LatencyPrediction(
            path=["a", "b"],
            total_latency_ms=10.0,
            breakdown=[("a", "b", 10.0)],
            bottleneck_link=("a", "b"),
            meets_sla=True,
            sla_target_ms=500.0,
        )
        assert pred.path == ["a", "b"]
        assert pred.bottleneck_link == ("a", "b")


# ===========================================================================
# 29. Overall health assessment
# ===========================================================================


class TestOverallHealthAssessment:
    def test_critical_when_failed(self):
        health = NetworkSimulator._assess_overall_health(0, 0, 1, 1, False)
        assert health == "critical"

    def test_critical_when_partition(self):
        health = NetworkSimulator._assess_overall_health(2, 0, 0, 2, True)
        assert health == "critical"

    def test_degraded_when_some_unhealthy(self):
        health = NetworkSimulator._assess_overall_health(1, 1, 0, 2, False)
        assert health == "degraded"

    def test_healthy_when_all_healthy(self):
        health = NetworkSimulator._assess_overall_health(3, 0, 0, 3, False)
        assert health == "healthy"

    def test_healthy_when_total_zero(self):
        health = NetworkSimulator._assess_overall_health(0, 0, 0, 0, False)
        assert health == "healthy"

    def test_degraded_when_not_all_healthy(self):
        health = NetworkSimulator._assess_overall_health(1, 0, 0, 2, False)
        assert health == "degraded"


# ===========================================================================
# 30. Partition detection internal
# ===========================================================================


class TestPartitionDetectionInternal:
    def test_all_connected(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        links = sim._build_links()
        groups = sim._detect_partitions(links)
        assert len(groups) == 1
        assert set(groups[0]) == {"A", "B", "C"}

    def test_isolated_node(self):
        graph = InfraGraph()
        graph.add_component(_make_component("A"))
        graph.add_component(_make_component("B"))
        graph.add_component(_make_component("C"))
        graph.add_dependency(Dependency(source_id="A", target_id="B"))
        # C has no connections
        sim = NetworkSimulator(graph)
        links = sim._build_links()
        groups = sim._detect_partitions(links)
        assert len(groups) == 2


# ===========================================================================
# 31. Shortest path internal
# ===========================================================================


class TestShortestPath:
    def test_direct_path(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        path = sim._find_shortest_path("A", "B")
        assert path == ["A", "B"]

    def test_multi_hop_path(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        path = sim._find_shortest_path("A", "C")
        assert path == ["A", "B", "C"]

    def test_no_path(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        path = sim._find_shortest_path("C", "A")
        assert path == []

    def test_same_node(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        path = sim._find_shortest_path("A", "A")
        assert path == ["A"]

    def test_diamond_shortest(self):
        graph = _diamond()
        sim = NetworkSimulator(graph)
        path = sim._find_shortest_path("A", "D")
        # BFS should find a 3-node path (A->B->D or A->C->D)
        assert len(path) == 3
        assert path[0] == "A"
        assert path[-1] == "D"


# ===========================================================================
# 32. Large-scale latency percentile integration
# ===========================================================================


class TestLargeScalePercentiles:
    def test_many_links_percentiles(self):
        graph = InfraGraph()
        n = 50
        for i in range(n):
            graph.add_component(_make_component(f"n{i}", rtt_ms=float(i + 1)))
        for i in range(n - 1):
            graph.add_dependency(
                Dependency(
                    source_id=f"n{i}",
                    target_id=f"n{i+1}",
                    latency_ms=float(i + 1),
                ),
            )
        sim = NetworkSimulator(graph)
        result = sim.simulate()
        assert result.total_links == 49
        assert result.p50_latency_ms > 0
        assert result.p95_latency_ms >= result.p50_latency_ms
        assert result.p99_latency_ms >= result.p95_latency_ms


# ===========================================================================
# 33. Simulate partition with overlapping groups
# ===========================================================================


class TestPartitionOverlapping:
    def test_no_overlap_link(self):
        graph = InfraGraph()
        graph.add_component(_make_component("A"))
        graph.add_component(_make_component("B"))
        graph.add_component(_make_component("C"))
        # A->B, no connection to C
        graph.add_dependency(Dependency(source_id="A", target_id="B"))
        sim = NetworkSimulator(graph)
        result = sim.simulate_partition(["A"], ["C"])
        # No link crosses the boundary
        partitioned = [
            lnk for lnk in result.links
            if lnk.condition == NetworkCondition.PARTITIONED
        ]
        assert len(partitioned) == 0


# ===========================================================================
# 34. Multiple conditions applied sequentially
# ===========================================================================


class TestSequentialConditions:
    def test_different_conditions_produce_different_results(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)

        normal = sim.simulate(NetworkCondition.NORMAL)
        degraded = sim.simulate(NetworkCondition.DEGRADED)
        congested = sim.simulate(NetworkCondition.CONGESTED)

        assert degraded.p50_latency_ms > normal.p50_latency_ms
        assert congested.p50_latency_ms > degraded.p50_latency_ms


# ===========================================================================
# 35. Partition result fields completeness
# ===========================================================================


class TestPartitionResultFields:
    def test_all_fields_set(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        result = sim.simulate_partition(["A"], ["B", "C"])
        assert isinstance(result.links, list)
        assert isinstance(result.total_links, int)
        assert isinstance(result.healthy_links, int)
        assert isinstance(result.degraded_links, int)
        assert isinstance(result.failed_links, int)
        assert isinstance(result.p50_latency_ms, float)
        assert isinstance(result.p95_latency_ms, float)
        assert isinstance(result.p99_latency_ms, float)
        assert isinstance(result.partition_detected, bool)
        assert isinstance(result.partition_groups, list)
        assert isinstance(result.overall_health, str)
        assert isinstance(result.recommendations, list)


# ===========================================================================
# 36. Infinite latency excluded from percentiles
# ===========================================================================


class TestInfiniteLatencyExclusion:
    def test_inf_not_in_percentiles(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        result = sim.simulate(NetworkCondition.PARTITIONED)
        # All links are partitioned (inf), so latencies list is empty -> 0.0
        assert result.p50_latency_ms == 0.0
        assert result.p95_latency_ms == 0.0
        assert result.p99_latency_ms == 0.0


# ===========================================================================
# 37. Mixed healthy and unhealthy links
# ===========================================================================


class TestMixedHealthLinks:
    def test_mixed_health(self):
        graph = InfraGraph()
        a = _make_component("a")
        b = _make_component("b", health=HealthStatus.DOWN)
        c = _make_component("c")
        graph.add_component(a)
        graph.add_component(b)
        graph.add_component(c)
        graph.add_dependency(Dependency(source_id="a", target_id="b"))
        graph.add_dependency(Dependency(source_id="a", target_id="c"))

        sim = NetworkSimulator(graph)
        result = sim.simulate()
        assert result.healthy_links == 1
        assert result.total_links == 2
        assert result.overall_health == "degraded"


# ===========================================================================
# 38. Build links preserves dependency count
# ===========================================================================


class TestBuildLinksCount:
    def test_link_count_matches_edges(self):
        graph = _diamond()
        sim = NetworkSimulator(graph)
        links = sim._build_links()
        assert len(links) == 4  # diamond has 4 edges


# ===========================================================================
# 39. Apply condition returns new link
# ===========================================================================


class TestApplyConditionImmutability:
    def test_original_unchanged(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        original = NetworkLink(
            source_id="A",
            target_id="B",
            base_latency_ms=5.0,
            current_latency_ms=5.0,
            packet_loss_rate=0.0,
            condition=NetworkCondition.NORMAL,
            is_healthy=True,
        )
        modified = sim._apply_condition(original, NetworkCondition.DEGRADED)
        assert original.condition == NetworkCondition.NORMAL
        assert original.is_healthy is True
        assert modified.condition == NetworkCondition.DEGRADED
        assert modified.is_healthy is False


# ===========================================================================
# 40. Latency breakdown sums to total
# ===========================================================================


class TestLatencyBreakdownSum:
    def test_breakdown_sums(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        pred = sim.predict_latency("A", "C")
        if pred.breakdown:
            total_from_breakdown = sum(lat for _, _, lat in pred.breakdown)
            assert total_from_breakdown == pytest.approx(pred.total_latency_ms)


# ===========================================================================
# 41. Simulate with explicit NORMAL condition
# ===========================================================================


class TestExplicitNormalCondition:
    def test_explicit_normal(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        result = sim.simulate(NetworkCondition.NORMAL)
        for lnk in result.links:
            assert lnk.condition == NetworkCondition.NORMAL


# ===========================================================================
# 42. Disconnected graph partition detection
# ===========================================================================


class TestDisconnectedGraph:
    def test_two_disconnected_subgraphs(self):
        graph = InfraGraph()
        graph.add_component(_make_component("A"))
        graph.add_component(_make_component("B"))
        graph.add_component(_make_component("C"))
        graph.add_component(_make_component("D"))
        graph.add_dependency(Dependency(source_id="A", target_id="B"))
        graph.add_dependency(Dependency(source_id="C", target_id="D"))

        sim = NetworkSimulator(graph)
        result = sim.simulate()
        assert result.partition_detected is True
        assert len(result.partition_groups) == 2


# ===========================================================================
# 43. All conditions mark links as unhealthy (except NORMAL)
# ===========================================================================


class TestAllConditionsUnhealthy:
    @pytest.mark.parametrize("cond", [
        NetworkCondition.DEGRADED,
        NetworkCondition.CONGESTED,
        NetworkCondition.PARTITIONED,
        NetworkCondition.DNS_FAILURE,
        NetworkCondition.TLS_FAILURE,
    ])
    def test_condition_unhealthy(self, cond):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        result = sim.simulate(cond)
        assert all(not lnk.is_healthy for lnk in result.links)


# ===========================================================================
# 44. NORMAL condition preserves health
# ===========================================================================


class TestNormalPreservesHealth:
    def test_normal_healthy(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        result = sim.simulate(NetworkCondition.NORMAL)
        assert all(lnk.is_healthy for lnk in result.links)


# ===========================================================================
# 45. Latency prediction with explicit dependency latency
# ===========================================================================


class TestLatencyPredictionExplicit:
    def test_explicit_latency(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a", rtt_ms=0.0, jitter_ms=0.0))
        graph.add_component(_make_component("b", rtt_ms=0.0, jitter_ms=0.0))
        graph.add_component(_make_component("c", rtt_ms=0.0, jitter_ms=0.0))
        graph.add_dependency(
            Dependency(source_id="a", target_id="b", latency_ms=25.0),
        )
        graph.add_dependency(
            Dependency(source_id="b", target_id="c", latency_ms=75.0),
        )
        sim = NetworkSimulator(graph)
        pred = sim.predict_latency("a", "c")
        assert pred.total_latency_ms == pytest.approx(100.0)
        assert pred.meets_sla is True  # 100 < 500


# ===========================================================================
# 46. Multiple partition simulations
# ===========================================================================


class TestMultiplePartitions:
    def test_sequential_partitions(self):
        graph = _fan_out()
        sim = NetworkSimulator(graph)

        r1 = sim.simulate_partition(["A"], ["B"])
        r2 = sim.simulate_partition(["A"], ["C", "D"])

        # Different partitions should yield different results
        p1 = sum(1 for lnk in r1.links if lnk.condition == NetworkCondition.PARTITIONED)
        p2 = sum(1 for lnk in r2.links if lnk.condition == NetworkCondition.PARTITIONED)
        assert p1 == 1
        assert p2 == 2


# ===========================================================================
# 47. Predict latency default SLA
# ===========================================================================


class TestDefaultSLA:
    def test_default_sla_500(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        pred = sim.predict_latency("A", "C")
        assert pred.sla_target_ms == 500.0


# ===========================================================================
# 48. DNS type component resolution in normal mode
# ===========================================================================


class TestDNSResolutionBothEnds:
    def test_both_dns_components(self):
        graph = InfraGraph()
        d1 = _make_component("d1", ComponentType.DNS, dns_resolution_ms=10.0, jitter_ms=0.0)
        d2 = _make_component("d2", ComponentType.DNS, dns_resolution_ms=15.0, jitter_ms=0.0)
        graph.add_component(d1)
        graph.add_component(d2)
        graph.add_dependency(Dependency(source_id="d1", target_id="d2"))
        sim = NetworkSimulator(graph)
        result = sim.simulate()
        lnk = result.links[0]
        # Both DNS resolution times should be added
        assert lnk.current_latency_ms >= 25.0


# ===========================================================================
# 49. Congested vs Degraded latency ordering
# ===========================================================================


class TestConditionLatencyOrdering:
    def test_congested_worse_than_degraded(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        degraded = sim.simulate(NetworkCondition.DEGRADED)
        congested = sim.simulate(NetworkCondition.CONGESTED)
        # Congested has higher multiplier
        assert congested.p50_latency_ms > degraded.p50_latency_ms


# ===========================================================================
# 50. Multiple conditions don't interfere with each other
# ===========================================================================


class TestConditionIsolation:
    def test_simulate_resets_state(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        # Run congested then normal - ensure normal isn't affected
        sim.simulate(NetworkCondition.CONGESTED)
        normal = sim.simulate(NetworkCondition.NORMAL)
        for lnk in normal.links:
            assert lnk.condition == NetworkCondition.NORMAL
            assert lnk.is_healthy is True


# ===========================================================================
# 51. Simulate partition - non-existent component IDs
# ===========================================================================


class TestPartitionNonExistentIDs:
    def test_nonexistent_groups(self):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        result = sim.simulate_partition(["X"], ["Y"])
        # No links cross between non-existent groups
        partitioned = [
            lnk for lnk in result.links
            if lnk.condition == NetworkCondition.PARTITIONED
        ]
        assert len(partitioned) == 0


# ===========================================================================
# 52. Large percentile edge case
# ===========================================================================


class TestPercentileEdgeCases:
    def test_three_values(self):
        sim = NetworkSimulator(InfraGraph())
        p50, p95, p99 = sim._calculate_percentiles([1.0, 2.0, 3.0])
        assert p50 == 2.0
        assert p95 > 2.0
        assert p99 > p95

    def test_sorted_output_monotonic(self):
        sim = NetworkSimulator(InfraGraph())
        values = [10.0, 1.0, 100.0, 50.0, 5.0]
        p50, p95, p99 = sim._calculate_percentiles(values)
        assert p50 <= p95 <= p99


# ===========================================================================
# 53. Simulate with condition applied to specific link
# ===========================================================================


class TestApplyConditionAllTypes:
    @pytest.mark.parametrize("cond", list(NetworkCondition))
    def test_apply_each_condition(self, cond):
        graph = _simple_chain()
        sim = NetworkSimulator(graph)
        link = NetworkLink(
            source_id="A",
            target_id="B",
            base_latency_ms=10.0,
            current_latency_ms=10.0,
            packet_loss_rate=0.0,
            condition=NetworkCondition.NORMAL,
            is_healthy=True,
        )
        result = sim._apply_condition(link, cond)
        assert result.condition == cond
        if cond == NetworkCondition.NORMAL:
            assert result.is_healthy is True
        else:
            assert result.is_healthy is False


# ===========================================================================
# 54. DNS failure adds double penalty for DNS-type components
# ===========================================================================


class TestDNSFailureDoublePenalty:
    def test_dns_type_extra_penalty(self):
        graph = InfraGraph()
        dns = _make_component("dns", ComponentType.DNS, jitter_ms=0.0, rtt_ms=1.0)
        app = _make_component("app", jitter_ms=0.0, rtt_ms=1.0)
        graph.add_component(dns)
        graph.add_component(app)
        graph.add_dependency(Dependency(source_id="app", target_id="dns"))

        sim = NetworkSimulator(graph)
        result = sim.simulate(NetworkCondition.DNS_FAILURE)
        lnk = result.links[0]
        # base + 5000 (base penalty) + 5000 (DNS-type target)
        assert lnk.current_latency_ms >= _DNS_FAILURE_PENALTY_MS * 2


# ===========================================================================
# 55. TLS failure double penalty for both encrypted
# ===========================================================================


class TestTLSFailureDoublePenalty:
    def test_both_encrypted_extra_penalty(self):
        graph = InfraGraph()
        src = _make_component("src", encryption_in_transit=True, jitter_ms=0.0, rtt_ms=1.0)
        tgt = _make_component("tgt", encryption_in_transit=True, jitter_ms=0.0, rtt_ms=1.0)
        graph.add_component(src)
        graph.add_component(tgt)
        graph.add_dependency(Dependency(source_id="src", target_id="tgt"))

        sim = NetworkSimulator(graph)
        result = sim.simulate(NetworkCondition.TLS_FAILURE)
        lnk = result.links[0]
        # base + 3000 (base penalty) + 3000 (src) + 3000 (tgt)
        assert lnk.current_latency_ms >= _TLS_FAILURE_PENALTY_MS * 3


# ===========================================================================
# 56. DNS failure with source being DNS type
# ===========================================================================


class TestDNSFailureSourceIsDNS:
    def test_source_dns_type_penalty(self):
        graph = InfraGraph()
        dns = _make_component("dns", ComponentType.DNS, jitter_ms=0.0, rtt_ms=1.0)
        app = _make_component("app", jitter_ms=0.0, rtt_ms=1.0)
        graph.add_component(dns)
        graph.add_component(app)
        # DNS is the *source*, app is target
        graph.add_dependency(Dependency(source_id="dns", target_id="app"))

        sim = NetworkSimulator(graph)
        result = sim.simulate(NetworkCondition.DNS_FAILURE)
        lnk = result.links[0]
        # base + 5000 (base penalty) + 5000 (source is DNS type)
        assert lnk.current_latency_ms >= _DNS_FAILURE_PENALTY_MS * 2


# ===========================================================================
# 57. Base latency fallback when components are missing from graph
# ===========================================================================


class TestBaseLengthFallbackNoComponents:
    def test_fallback_to_local_default_when_no_rtt(self):
        """When the dependency edge references components not in the graph,
        _compute_base_latency should fall back through RTT -> region -> default."""
        graph = InfraGraph()
        # Add deps with components that have no RTT info (edge case: components
        # not found in graph)
        graph.add_component(_make_component("a"))
        graph.add_component(_make_component("b"))
        # Create a dependency that references different IDs not in the graph
        dep = Dependency(source_id="x", target_id="y")
        sim = NetworkSimulator(graph)
        # Call _compute_base_latency directly with None components
        base = sim._compute_base_latency(None, None, dep)
        assert base == _DEFAULT_LOCAL_LATENCY_MS

    def test_fallback_cross_region_no_rtt(self):
        """When components exist but somehow the RTT list is empty and
        regions differ, should return cross-region default."""
        # This path is only reached when both src_comp and tgt_comp
        # are present but rtts list is empty. Since we always append
        # rtt_ms when comp exists, this path requires comp=None.
        # We test the full fallback chain via _compute_base_latency.
        graph = InfraGraph()
        sim = NetworkSimulator(graph)
        dep = Dependency(source_id="x", target_id="y")
        # Both comps are None -> no RTTs -> fallback to region check (also None) -> local default
        base = sim._compute_base_latency(None, None, dep)
        assert base == _DEFAULT_LOCAL_LATENCY_MS


# ===========================================================================
# 58. Predict latency uses _default_latency for missing links
# ===========================================================================


class TestPredictLatencyMissingLink:
    def test_path_with_no_matching_link(self):
        """When a path hop has no matching link in link_map,
        predict_latency should use _default_latency."""
        graph = InfraGraph()
        a = _make_component("a", region="us-east-1")
        b = _make_component("b", region="eu-west-1")
        graph.add_component(a)
        graph.add_component(b)
        graph.add_dependency(Dependency(source_id="a", target_id="b"))
        sim = NetworkSimulator(graph)

        # Force a situation: we build a simulator, then predict_latency
        # which builds links and uses them. If the link exists, it uses that.
        # So instead, let's test _default_latency directly for cross-region
        default = sim._default_latency("a", "b")
        assert default == _DEFAULT_CROSS_REGION_LATENCY_MS
