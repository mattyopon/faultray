"""Tests for the Bayesian network failure probability model."""

from __future__ import annotations


from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    HealthStatus,
    OperationalProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.bayesian_model import (
    BayesianEngine,
    BayesianResult,
    _impact_factor,
    _prior_failure_prob,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _simple_chain() -> InfraGraph:
    """LB -> App -> DB dependency chain."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=2,
        operational_profile=OperationalProfile(mtbf_hours=8760, mttr_minutes=2),
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=10),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
        operational_profile=OperationalProfile(mtbf_hours=4320, mttr_minutes=30),
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _mixed_deps() -> InfraGraph:
    """Graph with mixed dependency types: requires, optional, async."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="api", name="API", type=ComponentType.APP_SERVER,
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=10),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        operational_profile=OperationalProfile(mtbf_hours=4320, mttr_minutes=30),
    ))
    graph.add_component(Component(
        id="cache", name="Cache", type=ComponentType.CACHE,
        operational_profile=OperationalProfile(mtbf_hours=1440, mttr_minutes=5),
    ))
    graph.add_component(Component(
        id="queue", name="Queue", type=ComponentType.QUEUE,
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=15),
    ))
    graph.add_dependency(Dependency(
        source_id="api", target_id="db", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="api", target_id="cache", dependency_type="optional",
    ))
    graph.add_dependency(Dependency(
        source_id="api", target_id="queue", dependency_type="async",
    ))
    return graph


def _graph_with_down_component() -> InfraGraph:
    """Graph with a component explicitly marked as DOWN."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=10),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        health=HealthStatus.DOWN,
        operational_profile=OperationalProfile(mtbf_hours=4320, mttr_minutes=30),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


# ---------------------------------------------------------------------------
# Tests for helper functions
# ---------------------------------------------------------------------------


class TestPriorFailureProb:
    """Tests for prior failure probability calculation."""

    def test_basic_calculation(self) -> None:
        # MTBF=2160h, MTTR=30min -> 0.5h -> 0.5 / (2160 + 0.5) = 0.000231
        p = _prior_failure_prob(2160, 30)
        expected = 0.5 / (2160 + 0.5)
        assert abs(p - expected) < 1e-6

    def test_zero_mtbf_certain(self) -> None:
        assert _prior_failure_prob(0, 30) == 1.0

    def test_zero_mttr_zero(self) -> None:
        assert _prior_failure_prob(2160, 0) == 0.0

    def test_both_zero(self) -> None:
        assert _prior_failure_prob(0, 0) == 0.5


class TestImpactFactor:
    """Tests for dependency impact factors."""

    def test_requires_highest(self) -> None:
        assert _impact_factor("requires") == 0.9

    def test_optional_medium(self) -> None:
        assert _impact_factor("optional") == 0.3

    def test_async_lowest(self) -> None:
        assert _impact_factor("async") == 0.1

    def test_unknown_default(self) -> None:
        assert _impact_factor("unknown_type") == 0.5


# ---------------------------------------------------------------------------
# Tests for BayesianEngine.analyze()
# ---------------------------------------------------------------------------


class TestBayesianAnalyze:
    """Tests for the analyze method."""

    def test_results_for_all_components(self) -> None:
        graph = _simple_chain()
        engine = BayesianEngine(graph)
        results = engine.analyze()

        comp_ids = {r.component_id for r in results}
        assert comp_ids == {"lb", "app", "db"}

    def test_result_structure(self) -> None:
        graph = _simple_chain()
        engine = BayesianEngine(graph)
        results = engine.analyze()

        for r in results:
            assert isinstance(r, BayesianResult)
            assert isinstance(r.prior_failure_prob, float)
            assert isinstance(r.posterior_given_deps, float)
            assert isinstance(r.conditional_impacts, dict)
            assert isinstance(r.most_critical_dependency, str)

    def test_prior_between_zero_and_one(self) -> None:
        graph = _simple_chain()
        engine = BayesianEngine(graph)
        results = engine.analyze()

        for r in results:
            assert 0.0 <= r.prior_failure_prob <= 1.0

    def test_posterior_ge_prior(self) -> None:
        """Posterior should be >= prior (dependencies only increase risk)."""
        graph = _simple_chain()
        engine = BayesianEngine(graph)
        results = engine.analyze()

        for r in results:
            assert r.posterior_given_deps >= r.prior_failure_prob - 1e-10

    def test_leaf_no_conditional_impacts(self) -> None:
        """DB is a leaf - it has no dependencies to fail."""
        graph = _simple_chain()
        engine = BayesianEngine(graph)
        results = engine.analyze()

        db_result = next(r for r in results if r.component_id == "db")
        assert len(db_result.conditional_impacts) == 0
        assert db_result.most_critical_dependency == ""

    def test_requires_highest_impact(self) -> None:
        """Requires dependency should create higher conditional probability."""
        graph = _mixed_deps()
        engine = BayesianEngine(graph)
        results = engine.analyze()

        api_result = next(r for r in results if r.component_id == "api")
        # DB (requires) should have higher conditional impact than cache (optional)
        assert api_result.conditional_impacts["db"] > api_result.conditional_impacts["cache"]
        # Cache (optional) should have higher than queue (async)
        assert api_result.conditional_impacts["cache"] > api_result.conditional_impacts["queue"]

    def test_most_critical_dependency(self) -> None:
        graph = _mixed_deps()
        engine = BayesianEngine(graph)
        results = engine.analyze()

        api_result = next(r for r in results if r.component_id == "api")
        assert api_result.most_critical_dependency == "db"

    def test_down_component_increases_posterior(self) -> None:
        """When a dependency is DOWN, the posterior should increase."""
        graph = _graph_with_down_component()
        engine = BayesianEngine(graph)
        results = engine.analyze()

        app_result = next(r for r in results if r.component_id == "app")
        # DB is DOWN, so app's posterior should be significantly higher than prior
        assert app_result.posterior_given_deps > app_result.prior_failure_prob


class TestBayesianAnalyzeEdgeCases:
    """Edge case tests for analyze."""

    def test_empty_graph(self) -> None:
        graph = InfraGraph()
        engine = BayesianEngine(graph)
        results = engine.analyze()
        assert len(results) == 0

    def test_single_component_no_deps(self) -> None:
        graph = InfraGraph()
        graph.add_component(Component(
            id="solo", name="Solo", type=ComponentType.APP_SERVER,
            operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=10),
        ))
        engine = BayesianEngine(graph)
        results = engine.analyze()

        assert len(results) == 1
        assert results[0].posterior_given_deps == results[0].prior_failure_prob

    def test_replicas_reduce_prior(self) -> None:
        """More replicas should reduce prior failure probability."""
        graph1 = InfraGraph()
        graph1.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
            operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=10),
        ))
        graph3 = InfraGraph()
        graph3.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=3,
            operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=10),
        ))

        engine1 = BayesianEngine(graph1)
        engine3 = BayesianEngine(graph3)
        r1 = engine1.analyze()[0]
        r3 = engine3.analyze()[0]

        assert r3.prior_failure_prob < r1.prior_failure_prob


# ---------------------------------------------------------------------------
# Tests for BayesianEngine.query()
# ---------------------------------------------------------------------------


class TestBayesianQuery:
    """Tests for the query method with evidence."""

    def test_down_evidence_increases_dependent(self) -> None:
        graph = _simple_chain()
        engine = BayesianEngine(graph)

        posteriors = engine.query({"db": "down"})
        baseline = engine.query({})

        # App depends on DB; if DB is down, app's posterior should increase
        assert posteriors["app"] > baseline["app"]

    def test_healthy_evidence_reduces_probability(self) -> None:
        graph = _simple_chain()
        engine = BayesianEngine(graph)

        posteriors = engine.query({"db": "healthy"})
        baseline = engine.query({})

        # Knowing DB is healthy should give same or lower probability
        assert posteriors["db"] <= baseline["db"]

    def test_direct_down_evidence(self) -> None:
        graph = _simple_chain()
        engine = BayesianEngine(graph)

        posteriors = engine.query({"db": "down"})
        assert posteriors["db"] == 1.0

    def test_degraded_evidence(self) -> None:
        graph = _simple_chain()
        engine = BayesianEngine(graph)

        posteriors = engine.query({"db": "degraded"})
        baseline = engine.query({})

        # Degraded should increase probability but less than down
        assert posteriors["db"] > baseline["db"]
        assert posteriors["db"] < 1.0

    def test_all_components_in_output(self) -> None:
        graph = _simple_chain()
        engine = BayesianEngine(graph)

        posteriors = engine.query({"db": "down"})
        assert set(posteriors.keys()) == {"lb", "app", "db"}


# ---------------------------------------------------------------------------
# Tests for missing coverage lines (97, 127, 215)
# ---------------------------------------------------------------------------


class TestDefaultMtbfFallback:
    """Line 97: fallback to _DEFAULT_MTBF when mtbf_hours <= 0."""

    def test_zero_mtbf_uses_default(self) -> None:
        """When mtbf_hours is 0 (default), _compute_priors should use _DEFAULT_MTBF."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            operational_profile=OperationalProfile(mtbf_hours=0, mttr_minutes=30),
        ))
        engine = BayesianEngine(graph)
        results = engine.analyze()

        # With mtbf_hours=0, code falls back to _DEFAULT_MTBF["app_server"] = 2160.0
        # Prior = (30/60) / (2160 + 30/60) = 0.5 / 2160.5
        expected = 0.5 / (2160.0 + 0.5)
        assert len(results) == 1
        assert abs(results[0].prior_failure_prob - expected) < 1e-6

    def test_negative_mtbf_uses_default(self) -> None:
        """When mtbf_hours is negative, _compute_priors should use _DEFAULT_MTBF."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            operational_profile=OperationalProfile(mtbf_hours=-10, mttr_minutes=30),
        ))
        engine = BayesianEngine(graph)
        results = engine.analyze()

        # Fallback to _DEFAULT_MTBF["database"] = 4320.0
        expected = 0.5 / (4320.0 + 0.5)
        assert len(results) == 1
        assert abs(results[0].prior_failure_prob - expected) < 1e-6


class TestEdgeNoneContinue:
    """Lines 127 and 215: continue when get_dependency_edge returns None."""

    @staticmethod
    def _graph_with_edgeless_dependency() -> InfraGraph:
        """Create a graph where get_dependencies returns a node but
        get_dependency_edge returns None (edge exists without 'dependency' data)."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=10),
        ))
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE,
            operational_profile=OperationalProfile(mtbf_hours=4320, mttr_minutes=30),
        ))
        # Add edge directly to the networkx graph without 'dependency' metadata.
        # This means get_dependencies("app") returns [db_comp], but
        # get_dependency_edge("app", "db") returns None.
        graph._graph.add_edge("app", "db")
        return graph

    def test_analyze_skips_edge_none(self) -> None:
        """Line 127: analyze() should skip dependencies with no edge data."""
        graph = self._graph_with_edgeless_dependency()
        engine = BayesianEngine(graph)
        results = engine.analyze()

        app_result = next(r for r in results if r.component_id == "app")
        # The dependency edge has no data, so it should be skipped entirely.
        assert len(app_result.conditional_impacts) == 0
        assert app_result.most_critical_dependency == ""
        # Posterior should equal prior since no dependency was processed.
        assert app_result.posterior_given_deps == app_result.prior_failure_prob

    def test_query_skips_edge_none(self) -> None:
        """Line 215: query() should skip dependencies with no edge data."""
        graph = self._graph_with_edgeless_dependency()
        engine = BayesianEngine(graph)

        posteriors = engine.query({"db": "down"})
        # Even though db is "down", app should not be affected because
        # the edge has no dependency metadata and is skipped.
        baseline = engine.query({})
        assert posteriors["app"] == baseline["app"]


# ---------------------------------------------------------------------------
# Regression tests — Codex 2026-04-14 CRITICAL finding (noisy-OR aggregation)
# ---------------------------------------------------------------------------


def test_query_posterior_compounds_multiple_failing_deps_via_noisy_or() -> None:
    """Regression for Codex CRITICAL (bayesian_model.py:138 max aggregation):
    when multiple required dependencies are DOWN simultaneously, the posterior
    must exceed the single-dependency case and approach 1.0. The previous
    ``max`` collapse capped it around the largest single impact factor (~0.9)."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="api", name="API", type=ComponentType.APP_SERVER,
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=10),
    ))
    for dep_id in ("db_a", "db_b", "db_c"):
        graph.add_component(Component(
            id=dep_id, name=dep_id, type=ComponentType.DATABASE,
            operational_profile=OperationalProfile(mtbf_hours=4320, mttr_minutes=30),
        ))
        graph.add_dependency(Dependency(
            source_id="api", target_id=dep_id, dependency_type="requires",
        ))

    engine = BayesianEngine(graph)

    one_down = engine.query({"db_a": "down"})["api"]
    all_down = engine.query({"db_a": "down", "db_b": "down", "db_c": "down"})["api"]

    # More failing dependencies must drive posterior strictly higher.
    assert all_down > one_down, (
        f"noisy-OR must compound; got one_down={one_down}, all_down={all_down}"
    )
    # Three DOWN required deps (factor 0.9 each) → combined effect ≈ 0.999,
    # so posterior should round above 0.99.
    assert all_down > 0.99, (
        f"three DOWN required deps should push posterior above 0.99; "
        f"got {all_down}"
    )


def test_analyze_posterior_compounds_when_multiple_deps_down() -> None:
    """Regression for the same noisy-OR bug in ``analyze()``: setting every
    required dependency's health to DOWN must lift the posterior above the
    0.9 cap that the previous ``max`` aggregation produced."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="api", name="API", type=ComponentType.APP_SERVER,
        operational_profile=OperationalProfile(mtbf_hours=2160, mttr_minutes=10),
    ))
    for dep_id in ("db_a", "db_b", "db_c"):
        graph.add_component(Component(
            id=dep_id, name=dep_id, type=ComponentType.DATABASE,
            operational_profile=OperationalProfile(mtbf_hours=4320, mttr_minutes=30),
            health=HealthStatus.DOWN,
        ))
        graph.add_dependency(Dependency(
            source_id="api", target_id=dep_id, dependency_type="requires",
        ))

    engine = BayesianEngine(graph)
    results = engine.analyze()
    api_result = next(r for r in results if r.component_id == "api")
    assert api_result.posterior_given_deps > 0.99, (
        f"posterior with three DOWN required deps should exceed 0.99, got "
        f"{api_result.posterior_given_deps}"
    )
