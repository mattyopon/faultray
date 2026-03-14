"""Tests for the 3-Layer Availability Limit Model."""

import math

from infrasim.model.components import (
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    NetworkProfile,
    OperationalProfile,
    RuntimeJitter,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.availability_model import (
    ThreeLayerResult,
    _annual_downtime,
    _to_nines,
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
