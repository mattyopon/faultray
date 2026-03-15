"""Tests for Multi-Environment Resilience Comparison."""

from infrasim.model.components import (
    AutoScalingConfig,
    Capacity,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    ResourceMetrics,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.multi_env import (
    ComparisonMatrix,
    EnvironmentDelta,
    EnvironmentProfile,
    MultiEnvAnalyzer,
    _average_blast_radius,
    _average_replicas,
    _autoscaling_coverage,
    _circuit_breaker_coverage,
    _count_spofs,
    _estimate_availability,
    _extract_metrics,
    _failover_coverage,
    _max_dependency_depth,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_prod_graph() -> InfraGraph:
    """Build a production-like graph with redundancy."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2, failover=FailoverConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=3, autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
        failover=FailoverConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=2, failover=FailoverConfig(enabled=True),
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


def _build_staging_graph() -> InfraGraph:
    """Build a staging graph with less redundancy."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=1,
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=2,
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=1,
    ))

    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))

    return graph


def _build_dev_graph() -> InfraGraph:
    """Build a minimal dev graph."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=1,
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=1,
    ))

    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))

    return graph


# ---------------------------------------------------------------------------
# Metric helper tests
# ---------------------------------------------------------------------------

def test_count_spofs_no_spofs():
    """All components with replicas >= 2 should have zero SPOFs."""
    graph = _build_prod_graph()
    assert _count_spofs(graph) == 0


def test_count_spofs_with_spofs():
    """Staging graph should have SPOFs (single replica with dependents)."""
    graph = _build_staging_graph()
    spofs = _count_spofs(graph)
    # lb has 1 replica but app depends on... actually lb has no dependents
    # (lb depends on app via edge, so app has lb as dependent)
    # db has 1 replica and app depends on it => SPOF
    assert spofs >= 1


def test_average_replicas():
    """Average replicas should reflect the graph configuration."""
    graph = _build_prod_graph()
    avg = _average_replicas(graph)
    # (2 + 3 + 2) / 3 = 2.33
    assert abs(avg - 2.333) < 0.1


def test_failover_coverage():
    """Failover coverage should be 100% for prod graph."""
    graph = _build_prod_graph()
    coverage = _failover_coverage(graph)
    assert coverage == 100.0


def test_failover_coverage_zero():
    """Staging has no failover enabled."""
    graph = _build_staging_graph()
    coverage = _failover_coverage(graph)
    assert coverage == 0.0


def test_autoscaling_coverage():
    """Only app in prod has autoscaling."""
    graph = _build_prod_graph()
    coverage = _autoscaling_coverage(graph)
    # 1 out of 3
    assert abs(coverage - 33.33) < 1.0


def test_circuit_breaker_coverage():
    """Prod graph has circuit breakers on all edges."""
    graph = _build_prod_graph()
    coverage = _circuit_breaker_coverage(graph)
    assert coverage == 100.0


def test_circuit_breaker_coverage_none():
    """Staging has no circuit breakers."""
    graph = _build_staging_graph()
    coverage = _circuit_breaker_coverage(graph)
    assert coverage == 0.0


def test_max_dependency_depth():
    """Prod graph has depth 3 (lb -> app -> db)."""
    graph = _build_prod_graph()
    depth = _max_dependency_depth(graph)
    assert depth == 3


def test_estimate_availability():
    """Availability estimate should be between 95 and 100."""
    graph = _build_prod_graph()
    avail = _estimate_availability(graph)
    assert 95.0 <= avail <= 100.0


def test_extract_metrics_returns_all_keys():
    """Metrics dict should contain all expected keys."""
    graph = _build_prod_graph()
    metrics = _extract_metrics(graph)
    expected_keys = {
        "resilience_score", "component_count", "spof_count",
        "average_replicas", "failover_coverage", "autoscaling_coverage",
        "circuit_breaker_coverage", "dependency_depth", "blast_radius_avg",
    }
    assert set(metrics.keys()) == expected_keys


def test_average_blast_radius():
    """Average blast radius should be non-negative."""
    graph = _build_prod_graph()
    radius = _average_blast_radius(graph)
    assert radius >= 0.0


# ---------------------------------------------------------------------------
# MultiEnvAnalyzer tests
# ---------------------------------------------------------------------------

def test_compare_graphs_returns_matrix():
    """compare_graphs should return a ComparisonMatrix."""
    analyzer = MultiEnvAnalyzer()
    envs = {
        "production": _build_prod_graph(),
        "staging": _build_staging_graph(),
    }
    matrix = analyzer.compare_graphs(envs)
    assert isinstance(matrix, ComparisonMatrix)
    assert len(matrix.environments) == 2


def test_compare_graphs_identifies_strongest():
    """Production should be identified as the strongest environment."""
    analyzer = MultiEnvAnalyzer()
    envs = {
        "production": _build_prod_graph(),
        "staging": _build_staging_graph(),
    }
    matrix = analyzer.compare_graphs(envs)
    assert matrix.strongest_environment == "production"


def test_compare_graphs_identifies_weakest():
    """Staging should be identified as the weakest environment."""
    analyzer = MultiEnvAnalyzer()
    envs = {
        "production": _build_prod_graph(),
        "staging": _build_staging_graph(),
    }
    matrix = analyzer.compare_graphs(envs)
    assert matrix.weakest_environment == "staging"


def test_compare_graphs_parity_score():
    """Parity score should be between 0 and 100."""
    analyzer = MultiEnvAnalyzer()
    envs = {
        "production": _build_prod_graph(),
        "staging": _build_staging_graph(),
    }
    matrix = analyzer.compare_graphs(envs)
    assert 0.0 <= matrix.parity_score <= 100.0


def test_compare_graphs_generates_deltas():
    """Deltas should be generated for each metric pair."""
    analyzer = MultiEnvAnalyzer()
    envs = {
        "production": _build_prod_graph(),
        "staging": _build_staging_graph(),
    }
    matrix = analyzer.compare_graphs(envs)
    assert len(matrix.deltas) > 0
    # With 2 environments and 9 metrics, should have 9 deltas
    assert len(matrix.deltas) == 9


def test_compare_three_environments():
    """Comparison should work with 3 environments."""
    analyzer = MultiEnvAnalyzer()
    envs = {
        "production": _build_prod_graph(),
        "staging": _build_staging_graph(),
        "dev": _build_dev_graph(),
    }
    matrix = analyzer.compare_graphs(envs)
    assert len(matrix.environments) == 3
    # With 3 environments and 9 metrics: C(3,2) * 9 = 27 deltas
    assert len(matrix.deltas) == 27


def test_compare_generates_recommendations():
    """Recommendations should be generated when environments differ."""
    analyzer = MultiEnvAnalyzer()
    envs = {
        "production": _build_prod_graph(),
        "staging": _build_staging_graph(),
    }
    matrix = analyzer.compare_graphs(envs)
    assert len(matrix.recommendations) > 0


def test_compare_matrix_data():
    """Matrix data should contain metrics for each environment."""
    analyzer = MultiEnvAnalyzer()
    envs = {
        "production": _build_prod_graph(),
        "staging": _build_staging_graph(),
    }
    matrix = analyzer.compare_graphs(envs)
    assert "production" in matrix.matrix_data
    assert "staging" in matrix.matrix_data
    assert "resilience_score" in matrix.matrix_data["production"]


def test_compare_too_few_environments():
    """Comparison with less than 2 environments should return empty matrix."""
    analyzer = MultiEnvAnalyzer()
    envs = {"production": _build_prod_graph()}
    matrix = analyzer.compare_graphs(envs)
    assert len(matrix.environments) == 0


def test_environment_profile_fields():
    """EnvironmentProfile should have correct field values."""
    analyzer = MultiEnvAnalyzer()
    envs = {
        "production": _build_prod_graph(),
        "staging": _build_staging_graph(),
    }
    matrix = analyzer.compare_graphs(envs)

    prod_profile = [e for e in matrix.environments if e.name == "production"][0]
    assert prod_profile.component_count == 3
    assert prod_profile.spof_count == 0
    assert prod_profile.resilience_score > 0


def test_deltas_have_concern_flag():
    """Significant deltas should be flagged as concerns."""
    analyzer = MultiEnvAnalyzer()
    envs = {
        "production": _build_prod_graph(),
        "staging": _build_staging_graph(),
    }
    matrix = analyzer.compare_graphs(envs)
    concerns = [d for d in matrix.deltas if d.concern]
    # There should be at least some concerns (failover, circuit breakers differ)
    assert len(concerns) > 0


# ---------------------------------------------------------------------------
# Drift detection tests
# ---------------------------------------------------------------------------

def test_find_drift_missing_components():
    """Should detect components that exist in one env but not the other."""
    analyzer = MultiEnvAnalyzer()
    prod = _build_prod_graph()
    dev = _build_dev_graph()
    drift = analyzer.find_drift_between_envs(prod, dev)
    # prod has lb which dev does not
    assert any("lb" in d for d in drift)


def test_find_drift_replica_difference():
    """Should detect replica count differences."""
    analyzer = MultiEnvAnalyzer()
    prod = _build_prod_graph()
    staging = _build_staging_graph()
    drift = analyzer.find_drift_between_envs(prod, staging)
    # prod has 3 replicas for app, staging has 2
    assert any("replica" in d.lower() for d in drift)


def test_find_drift_failover_difference():
    """Should detect failover configuration differences."""
    analyzer = MultiEnvAnalyzer()
    prod = _build_prod_graph()
    staging = _build_staging_graph()
    drift = analyzer.find_drift_between_envs(prod, staging)
    assert any("failover" in d.lower() for d in drift)


def test_find_drift_identical():
    """Identical graphs should have no drift."""
    analyzer = MultiEnvAnalyzer()
    prod = _build_prod_graph()
    drift = analyzer.find_drift_between_envs(prod, prod)
    assert len(drift) == 0


def test_find_drift_edge_difference():
    """Should detect dependency edge differences."""
    analyzer = MultiEnvAnalyzer()
    prod = _build_prod_graph()
    dev = _build_dev_graph()
    drift = analyzer.find_drift_between_envs(prod, dev)
    # prod has lb->app edge which dev doesn't (lb doesn't exist in dev)
    assert any("Dependency" in d or "missing" in d.lower() for d in drift)
