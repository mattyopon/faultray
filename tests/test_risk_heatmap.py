"""Tests for the Risk Heat Map engine."""

from infrasim.model.components import (
    AutoScalingConfig,
    Capacity,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    ResourceMetrics,
    SecurityProfile,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.risk_heatmap import (
    ComponentRiskProfile,
    HeatMapData,
    RiskDimension,
    RiskHeatMapEngine,
    RiskZone,
    _risk_color,
    _risk_level,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _build_simple_graph() -> InfraGraph:
    """Build a simple 3-component graph for testing."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="lb",
        name="Load Balancer",
        type=ComponentType.LOAD_BALANCER,
        replicas=2,
        capacity=Capacity(max_connections=10000),
    ))
    graph.add_component(Component(
        id="app",
        name="App Server",
        type=ComponentType.APP_SERVER,
        replicas=1,
        capacity=Capacity(max_connections=500, timeout_seconds=30),
        metrics=ResourceMetrics(network_connections=400),
    ))
    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        replicas=1,
        capacity=Capacity(max_connections=100),
        metrics=ResourceMetrics(network_connections=90, disk_percent=72),
    ))

    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))

    return graph


def _build_resilient_graph() -> InfraGraph:
    """Build a graph with high resilience features."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="lb",
        name="Load Balancer",
        type=ComponentType.LOAD_BALANCER,
        replicas=3,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
        failover=FailoverConfig(enabled=True),
        security=SecurityProfile(rate_limiting=True),
    ))
    graph.add_component(Component(
        id="app",
        name="App Server",
        type=ComponentType.APP_SERVER,
        replicas=3,
        autoscaling=AutoScalingConfig(enabled=True),
        failover=FailoverConfig(enabled=True),
        security=SecurityProfile(rate_limiting=True),
    ))
    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        replicas=2,
        failover=FailoverConfig(enabled=True),
        security=SecurityProfile(rate_limiting=True),
    ))

    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))

    return graph


# ---------------------------------------------------------------------------
# Unit tests: color and level mapping
# ---------------------------------------------------------------------------


def test_risk_color_green():
    assert _risk_color(0.0) == "#28a745"
    assert _risk_color(0.24) == "#28a745"


def test_risk_color_yellow():
    assert _risk_color(0.25) == "#ffc107"
    assert _risk_color(0.49) == "#ffc107"


def test_risk_color_orange():
    assert _risk_color(0.5) == "#fd7e14"
    assert _risk_color(0.74) == "#fd7e14"


def test_risk_color_red():
    assert _risk_color(0.75) == "#dc3545"
    assert _risk_color(1.0) == "#dc3545"


def test_risk_level_values():
    assert _risk_level(0.1) == "low"
    assert _risk_level(0.3) == "medium"
    assert _risk_level(0.6) == "high"
    assert _risk_level(0.9) == "critical"


# ---------------------------------------------------------------------------
# Component risk analysis
# ---------------------------------------------------------------------------


def test_get_component_risk_returns_profile():
    graph = _build_simple_graph()
    engine = RiskHeatMapEngine()

    profile = engine.get_component_risk(graph, "db")

    assert isinstance(profile, ComponentRiskProfile)
    assert profile.component_id == "db"
    assert profile.component_name == "Database"
    assert profile.component_type == "database"
    assert 0.0 <= profile.overall_risk <= 1.0
    assert profile.risk_level in ("critical", "high", "medium", "low")
    assert profile.color.startswith("#")


def test_spof_component_has_high_spof_score():
    """A single-replica component with dependents should have SPOF=1.0."""
    graph = _build_simple_graph()
    engine = RiskHeatMapEngine()

    # db has 1 replica and app depends on it
    profile = engine.get_component_risk(graph, "db")
    assert profile.risk_scores[RiskDimension.SPOF] == 1.0


def test_replicated_component_has_zero_spof():
    """A multi-replica component should have SPOF=0.0."""
    graph = _build_simple_graph()
    engine = RiskHeatMapEngine()

    # lb has 2 replicas
    profile = engine.get_component_risk(graph, "lb")
    assert profile.risk_scores[RiskDimension.SPOF] == 0.0


def test_utilization_risk():
    """Components with high utilization should have higher risk."""
    graph = _build_simple_graph()
    engine = RiskHeatMapEngine()

    # db has 90% connection utilization (90/100)
    profile = engine.get_component_risk(graph, "db")
    assert profile.risk_scores[RiskDimension.UTILIZATION] > 0.5


def test_resilient_components_have_low_recovery_risk():
    """Components with failover + autoscaling should have low recovery risk."""
    graph = _build_resilient_graph()
    engine = RiskHeatMapEngine()

    profile = engine.get_component_risk(graph, "app")
    # Has failover, autoscaling, and replicas > 1
    assert profile.risk_scores[RiskDimension.RECOVERY] < 0.3


def test_risk_factors_populated():
    """High-risk components should have explanatory risk factors."""
    graph = _build_simple_graph()
    engine = RiskHeatMapEngine()

    profile = engine.get_component_risk(graph, "db")
    assert len(profile.risk_factors) > 0
    # Should mention SPOF
    assert any("single point" in f.lower() or "spof" in f.lower() for f in profile.risk_factors)


def test_nonexistent_component_returns_default():
    graph = _build_simple_graph()
    engine = RiskHeatMapEngine()

    profile = engine.get_component_risk(graph, "nonexistent")
    assert profile.component_id == "nonexistent"
    assert profile.overall_risk == 0.0


# ---------------------------------------------------------------------------
# Full analysis
# ---------------------------------------------------------------------------


def test_analyze_returns_heatmap_data():
    graph = _build_simple_graph()
    engine = RiskHeatMapEngine()

    data = engine.analyze(graph)

    assert isinstance(data, HeatMapData)
    assert len(data.components) == 3
    assert len(data.hotspots) <= 5
    assert 0.0 <= data.overall_risk_score <= 1.0
    assert "critical" in data.risk_distribution
    assert "high" in data.risk_distribution
    assert "medium" in data.risk_distribution
    assert "low" in data.risk_distribution
    assert sum(data.risk_distribution.values()) == 3


def test_analyze_components_sorted_by_risk():
    graph = _build_simple_graph()
    engine = RiskHeatMapEngine()

    data = engine.analyze(graph)
    scores = [c.overall_risk for c in data.components]
    assert scores == sorted(scores, reverse=True)


def test_analyze_empty_graph():
    graph = InfraGraph()
    engine = RiskHeatMapEngine()

    data = engine.analyze(graph)

    assert len(data.components) == 0
    assert len(data.hotspots) == 0
    assert data.overall_risk_score == 0.0


# ---------------------------------------------------------------------------
# Hotspots
# ---------------------------------------------------------------------------


def test_identify_hotspots_returns_top_n():
    graph = _build_simple_graph()
    engine = RiskHeatMapEngine()

    hotspots = engine.identify_hotspots(graph, top_n=2)
    assert len(hotspots) == 2
    # First should be highest risk
    assert hotspots[0].overall_risk >= hotspots[1].overall_risk


# ---------------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------------


def test_group_by_zones():
    graph = _build_simple_graph()
    engine = RiskHeatMapEngine()

    zones = engine.group_by_zones(graph)

    assert isinstance(zones, list)
    assert all(isinstance(z, RiskZone) for z in zones)

    # Should have zones for each component type present
    zone_names = {z.name for z in zones}
    assert "Database Layer" in zone_names
    assert "Application Layer" in zone_names
    assert "Network Layer" in zone_names

    # Each zone should have components
    for zone in zones:
        assert len(zone.components) > 0
        assert 0.0 <= zone.zone_risk <= 1.0


def test_zones_sorted_by_risk():
    graph = _build_simple_graph()
    engine = RiskHeatMapEngine()

    zones = engine.group_by_zones(graph)
    risks = [z.zone_risk for z in zones]
    assert risks == sorted(risks, reverse=True)


# ---------------------------------------------------------------------------
# Matrix conversion
# ---------------------------------------------------------------------------


def test_to_matrix():
    graph = _build_simple_graph()
    engine = RiskHeatMapEngine()

    data = engine.analyze(graph)
    matrix = engine.to_matrix(data)

    assert len(matrix) == len(data.components)
    assert len(matrix[0]) == len(RiskDimension)

    # All values should be between 0 and 1
    for row in matrix:
        for val in row:
            assert 0.0 <= val <= 1.0


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_to_dict():
    graph = _build_simple_graph()
    engine = RiskHeatMapEngine()

    data = engine.analyze(graph)
    d = data.to_dict()

    assert isinstance(d, dict)
    assert "components" in d
    assert "zones" in d
    assert "hotspots" in d
    assert "overall_risk_score" in d
    assert "risk_distribution" in d
    assert "dimension_weights" in d

    # Check component dict structure
    comp = d["components"][0]
    assert "component_id" in comp
    assert "risk_scores" in comp
    assert "overall_risk" in comp
    assert "risk_level" in comp
    assert "color" in comp


def test_component_profile_to_dict():
    profile = ComponentRiskProfile(
        component_id="test",
        component_name="Test",
        component_type="app_server",
        risk_scores={RiskDimension.SPOF: 1.0, RiskDimension.BLAST_RADIUS: 0.5},
        overall_risk=0.75,
        risk_level="high",
        risk_factors=["SPOF detected"],
        color="#fd7e14",
    )
    d = profile.to_dict()
    assert d["component_id"] == "test"
    assert d["risk_scores"]["spof"] == 1.0
    assert d["overall_risk"] == 0.75


# ---------------------------------------------------------------------------
# Custom weights
# ---------------------------------------------------------------------------


def test_custom_weights():
    """Custom weights should change the overall score."""
    graph = _build_simple_graph()

    # Weight SPOF very heavily
    spof_weights = {dim: 0.0 for dim in RiskDimension}
    spof_weights[RiskDimension.SPOF] = 1.0
    engine_spof = RiskHeatMapEngine(weights=spof_weights)

    # Weight utilization very heavily
    util_weights = {dim: 0.0 for dim in RiskDimension}
    util_weights[RiskDimension.UTILIZATION] = 1.0
    engine_util = RiskHeatMapEngine(weights=util_weights)

    db_spof = engine_spof.get_component_risk(graph, "db")
    db_util = engine_util.get_component_risk(graph, "db")

    # SPOF-weighted should give db a score of 1.0 (it's a SPOF)
    assert db_spof.overall_risk == 1.0

    # Utilization-weighted should reflect utilization
    assert db_util.overall_risk > 0.0
    assert db_util.overall_risk != db_spof.overall_risk


# ---------------------------------------------------------------------------
# Blast radius calculation
# ---------------------------------------------------------------------------


def test_blast_radius_score():
    """Components at the bottom of the chain should have highest blast radius."""
    graph = _build_simple_graph()
    engine = RiskHeatMapEngine()

    db_profile = engine.get_component_risk(graph, "db")
    lb_profile = engine.get_component_risk(graph, "lb")

    # db failure cascades to app and lb
    # lb failure doesn't cascade to anything
    assert db_profile.risk_scores[RiskDimension.BLAST_RADIUS] > lb_profile.risk_scores[RiskDimension.BLAST_RADIUS]
