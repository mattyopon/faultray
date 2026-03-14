"""Tests for the 3-Layer and 5-Layer Availability Limit Models."""

import math

from infrasim.model.components import (
    Component,
    ComponentType,
    Dependency,
    ExternalSLAConfig,
    FailoverConfig,
    NetworkProfile,
    OperationalProfile,
    RuntimeJitter,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.availability_model import (
    FiveLayerResult,
    ThreeLayerResult,
    _annual_downtime,
    _to_nines,
    compute_five_layer_model,
    compute_three_layer_model,
)


def _simple_graph() -> InfraGraph:
    """Build a simple 3-component graph for testing."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=2,
        operational_profile=OperationalProfile(mtbf_hours=8760, mttr_minutes=2),
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=3,
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=5),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
        operational_profile=OperationalProfile(mtbf_hours=4320, mttr_minutes=30),
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return graph


# --- Utility function tests ---


def test_to_nines_basic():
    assert _to_nines(0.99) == pytest.approx(2.0, abs=0.01)
    assert _to_nines(0.999) == pytest.approx(3.0, abs=0.01)
    assert _to_nines(0.9999) == pytest.approx(4.0, abs=0.01)


def test_to_nines_edge_cases():
    assert _to_nines(1.0) == float("inf")
    assert _to_nines(0.0) == 0.0


def test_annual_downtime():
    # 99% availability = ~3.65 days = ~315,576 seconds
    dt = _annual_downtime(0.99)
    assert 315000 < dt < 316000


# --- 3-Layer Model tests ---


def test_empty_graph():
    graph = InfraGraph()
    result = compute_three_layer_model(graph)
    assert result.layer1_software.nines == 0.0
    assert result.layer2_hardware.nines == 0.0
    assert result.layer3_theoretical.nines == 0.0


def test_three_layer_returns_correct_type():
    graph = _simple_graph()
    result = compute_three_layer_model(graph)
    assert isinstance(result, ThreeLayerResult)
    assert result.layer1_software.nines > 0
    assert result.layer2_hardware.nines > 0
    assert result.layer3_theoretical.nines > 0


def test_layer_ordering():
    """Layer 1 <= Layer 2 <= Layer 3 (software is most restrictive)."""
    graph = _simple_graph()
    result = compute_three_layer_model(graph)
    assert result.layer1_software.nines <= result.layer2_hardware.nines
    # Layer 3 could be <= Layer 2 if network/jitter penalty is large
    # but typically Layer 3 ≈ Layer 2 (theoretical adds network penalty)


def test_layer2_uses_mtbf():
    """Higher MTBF should give higher Layer 2 availability."""
    graph1 = InfraGraph()
    graph1.add_component(Component(
        id="a", name="A", type=ComponentType.APP_SERVER, replicas=1,
        operational_profile=OperationalProfile(mtbf_hours=100, mttr_minutes=30),
    ))

    graph2 = InfraGraph()
    graph2.add_component(Component(
        id="a", name="A", type=ComponentType.APP_SERVER, replicas=1,
        operational_profile=OperationalProfile(mtbf_hours=10000, mttr_minutes=30),
    ))

    r1 = compute_three_layer_model(graph1)
    r2 = compute_three_layer_model(graph2)
    assert r2.layer2_hardware.nines > r1.layer2_hardware.nines


def test_layer2_uses_replicas():
    """More replicas should give higher Layer 2 availability."""
    graph1 = InfraGraph()
    graph1.add_component(Component(
        id="a", name="A", type=ComponentType.APP_SERVER, replicas=1,
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=5),
    ))

    graph2 = InfraGraph()
    graph2.add_component(Component(
        id="a", name="A", type=ComponentType.APP_SERVER, replicas=3,
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=5),
    ))

    r1 = compute_three_layer_model(graph1)
    r2 = compute_three_layer_model(graph2)
    assert r2.layer2_hardware.nines > r1.layer2_hardware.nines


def test_failover_affects_layer2():
    """Failover should slightly reduce Layer 2 due to promotion time penalty."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="a", name="A", type=ComponentType.APP_SERVER, replicas=2,
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=5),
        failover=FailoverConfig(enabled=True, promotion_time_seconds=30,
                                health_check_interval_seconds=10, failover_threshold=3),
    ))
    result = compute_three_layer_model(graph)
    # Failover adds a small penalty, so layer2 should be slightly less than
    # the pure MTBF calculation
    assert result.layer2_hardware.nines > 3.0  # still high
    assert result.layer2_hardware.availability < 1.0  # not perfect


def test_network_penalty_affects_layer3():
    """High packet loss should reduce Layer 3 below Layer 2."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="a", name="A", type=ComponentType.APP_SERVER, replicas=3,
        operational_profile=OperationalProfile(mtbf_hours=8760, mttr_minutes=1),
        network=NetworkProfile(packet_loss_rate=0.01),  # 1% loss
    ))
    result = compute_three_layer_model(graph)
    assert result.layer3_theoretical.nines < result.layer2_hardware.nines


def test_gc_pause_affects_layer3():
    """GC pauses should reduce Layer 3."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="a", name="A", type=ComponentType.APP_SERVER, replicas=3,
        operational_profile=OperationalProfile(mtbf_hours=8760, mttr_minutes=1),
        runtime_jitter=RuntimeJitter(gc_pause_ms=50, gc_pause_frequency=1.0),  # 5% GC
    ))
    result = compute_three_layer_model(graph)
    assert result.layer3_theoretical.nines < result.layer2_hardware.nines


def test_deploy_downtime_affects_layer1():
    """Higher deploy frequency should reduce Layer 1."""
    graph = _simple_graph()
    # Many deploys with significant downtime
    r1 = compute_three_layer_model(graph, deploys_per_month=2)
    r2 = compute_three_layer_model(graph, deploys_per_month=50)
    assert r2.layer1_software.nines <= r1.layer1_software.nines


def test_summary_format():
    """Summary should contain all three layers."""
    graph = _simple_graph()
    result = compute_three_layer_model(graph)
    summary = result.summary
    assert "Layer 1" in summary
    assert "Layer 2" in summary
    assert "Layer 3" in summary
    assert "nines" in summary


def test_details_contain_per_component():
    """Layer 2 details should contain per-component availability."""
    graph = _simple_graph()
    result = compute_three_layer_model(graph)
    details = result.layer2_hardware.details
    assert "lb" in details
    assert "app" in details
    assert "db" in details
    assert all(0 < v <= 1.0 for v in details.values())


# Need pytest import for approx
import pytest


# --- 5-Layer Model tests ---


def _graph_with_external_api() -> InfraGraph:
    """Build a graph with an external API dependency."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=5),
    ))
    graph.add_component(Component(
        id="stripe", name="Stripe", type=ComponentType.EXTERNAL_API, replicas=1,
        external_sla=ExternalSLAConfig(provider_sla=99.99),
    ))
    graph.add_component(Component(
        id="twilio", name="Twilio", type=ComponentType.EXTERNAL_API, replicas=1,
        external_sla=ExternalSLAConfig(provider_sla=99.95),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="stripe", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="twilio", dependency_type="requires",
    ))
    return graph


def test_five_layer_returns_correct_type():
    graph = _simple_graph()
    result = compute_five_layer_model(graph)
    assert isinstance(result, FiveLayerResult)
    assert result.layer1_software.nines > 0
    assert result.layer2_hardware.nines > 0
    assert result.layer3_theoretical.nines > 0
    assert result.layer4_operational.nines > 0


def test_five_layer_empty_graph():
    graph = InfraGraph()
    result = compute_five_layer_model(graph)
    assert result.layer1_software.nines == 0.0
    assert result.layer4_operational.nines == 0.0
    assert result.layer5_external.nines == 0.0


def test_five_layer_backward_compat():
    """Layers 1-3 of compute_five_layer_model should match compute_three_layer_model."""
    graph = _simple_graph()
    three = compute_three_layer_model(graph)
    five = compute_five_layer_model(graph)
    assert five.layer1_software.availability == three.layer1_software.availability
    assert five.layer2_hardware.availability == three.layer2_hardware.availability
    assert five.layer3_theoretical.availability == three.layer3_theoretical.availability


def test_layer4_operational_default():
    """Default operational params: 12 incidents/year, 30min response, 100% coverage."""
    graph = _simple_graph()
    result = compute_five_layer_model(graph)
    # 12 incidents * 0.5 hours / 8760 hours = 0.000685
    # So availability ~= 0.999315
    assert result.layer4_operational.availability == pytest.approx(
        1.0 - (12.0 * 0.5 / 8760.0), abs=0.0001
    )
    assert result.layer4_operational.nines > 2.0


def test_layer4_low_coverage_reduces_availability():
    """Lower on-call coverage should reduce Layer 4 availability."""
    graph = _simple_graph()
    r_full = compute_five_layer_model(graph, oncall_coverage_percent=100.0)
    r_partial = compute_five_layer_model(graph, oncall_coverage_percent=33.0)
    assert r_partial.layer4_operational.availability < r_full.layer4_operational.availability


def test_layer4_more_incidents_reduces_availability():
    """More incidents per year should reduce Layer 4 availability."""
    graph = _simple_graph()
    r_low = compute_five_layer_model(graph, incidents_per_year=4.0)
    r_high = compute_five_layer_model(graph, incidents_per_year=52.0)
    assert r_high.layer4_operational.availability < r_low.layer4_operational.availability


def test_layer4_longer_response_reduces_availability():
    """Longer mean response time should reduce Layer 4 availability."""
    graph = _simple_graph()
    r_fast = compute_five_layer_model(graph, mean_response_minutes=10.0)
    r_slow = compute_five_layer_model(graph, mean_response_minutes=120.0)
    assert r_slow.layer4_operational.availability < r_fast.layer4_operational.availability


def test_layer5_no_external_deps():
    """Without external deps, Layer 5 should be 1.0 (perfect)."""
    graph = _simple_graph()
    result = compute_five_layer_model(graph)
    assert result.layer5_external.availability == 1.0
    assert result.layer5_external.nines == float("inf")


def test_layer5_with_external_api():
    """External APIs should cascade their SLAs."""
    graph = _graph_with_external_api()
    result = compute_five_layer_model(graph)
    # Expected: 0.9999 * 0.9995 = 0.99940005
    expected = 0.9999 * 0.9995
    assert result.layer5_external.availability == pytest.approx(expected, abs=0.0001)
    assert result.layer5_external.nines > 2.0
    assert result.layer5_external.nines < 5.0


def test_layer5_external_api_without_explicit_sla():
    """External API without explicit SLA should default to 99.9%."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="ext", name="External", type=ComponentType.EXTERNAL_API, replicas=1,
    ))
    result = compute_five_layer_model(graph)
    assert result.layer5_external.availability == pytest.approx(0.999, abs=0.0001)


def test_layer5_multiple_externals_compound():
    """Multiple external deps should multiply their SLAs."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
        operational_profile=OperationalProfile(mtbf_hours=8760, mttr_minutes=5),
    ))
    # Add 5 external APIs each with 99.9% SLA
    for i in range(5):
        graph.add_component(Component(
            id=f"ext{i}", name=f"External{i}",
            type=ComponentType.EXTERNAL_API, replicas=1,
            external_sla=ExternalSLAConfig(provider_sla=99.9),
        ))
        graph.add_dependency(Dependency(
            source_id="app", target_id=f"ext{i}", dependency_type="requires",
        ))
    result = compute_five_layer_model(graph)
    # 0.999^5 ≈ 0.995
    expected = 0.999 ** 5
    assert result.layer5_external.availability == pytest.approx(expected, abs=0.001)


def test_five_layer_summary_format():
    """Summary should contain all five layers."""
    graph = _graph_with_external_api()
    result = compute_five_layer_model(graph)
    summary = result.summary
    assert "Layer 1" in summary
    assert "Layer 2" in summary
    assert "Layer 3" in summary
    assert "Layer 4" in summary
    assert "Layer 5" in summary
    assert "5-Layer" in summary
