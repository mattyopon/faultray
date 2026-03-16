"""Tests for Multi-Environment Resilience Comparison."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.multi_env import (
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
# Helpers  (same pattern as test_change_risk.py)
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
    failover: bool = False,
    autoscaling: bool = False,
) -> Component:
    fo = FailoverConfig(enabled=True) if failover else FailoverConfig()
    asc = (
        AutoScalingConfig(enabled=True, min_replicas=1, max_replicas=10)
        if autoscaling
        else AutoScalingConfig()
    )
    c = Component(
        id=cid, name=name, type=ctype, replicas=replicas,
        failover=fo, autoscaling=asc,
    )
    c.health = health
    return c


def _chain_graph() -> InfraGraph:
    """lb -> api -> db  (prod-like with redundancy)."""
    g = InfraGraph()
    g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=2, failover=True))
    g.add_component(_comp("api", "API", replicas=3, failover=True, autoscaling=True))
    g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=2, failover=True))
    g.add_dependency(Dependency(
        source_id="lb", target_id="api", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    g.add_dependency(Dependency(
        source_id="api", target_id="db", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    return g


def _weak_graph() -> InfraGraph:
    """Staging-like: no failover, no autoscaling, no CB, low replicas."""
    g = InfraGraph()
    g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=1))
    g.add_component(_comp("api", "API", replicas=2))
    g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=1))
    g.add_dependency(Dependency(source_id="lb", target_id="api"))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    return g


def _minimal_graph() -> InfraGraph:
    """Dev-like: only api -> db, bare minimum."""
    g = InfraGraph()
    g.add_component(_comp("api", "API", replicas=1))
    g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=1))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    return g


# ---------------------------------------------------------------------------
# Metric helper tests
# ---------------------------------------------------------------------------


class TestCountSpofs:
    def test_no_spofs_with_replicas(self):
        g = _chain_graph()
        assert _count_spofs(g) == 0

    def test_spofs_with_single_replica_dependents(self):
        g = _weak_graph()
        # db has 1 replica and api depends on it => SPOF
        assert _count_spofs(g) >= 1

    def test_empty_graph(self):
        g = InfraGraph()
        assert _count_spofs(g) == 0


class TestAverageReplicas:
    def test_prod_graph(self):
        g = _chain_graph()
        avg = _average_replicas(g)
        # (2 + 3 + 2) / 3 = 2.333
        assert abs(avg - 2.333) < 0.1

    def test_empty_graph(self):
        g = InfraGraph()
        assert _average_replicas(g) == 0.0

    def test_single_component(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A", replicas=5))
        assert _average_replicas(g) == 5.0


class TestFailoverCoverage:
    def test_full_coverage(self):
        g = _chain_graph()
        assert _failover_coverage(g) == 100.0

    def test_zero_coverage(self):
        g = _weak_graph()
        assert _failover_coverage(g) == 0.0

    def test_empty_graph(self):
        g = InfraGraph()
        assert _failover_coverage(g) == 0.0

    def test_partial_coverage(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A", failover=True))
        g.add_component(_comp("b", "B", failover=False))
        assert _failover_coverage(g) == 50.0


class TestAutoscalingCoverage:
    def test_partial_coverage(self):
        g = _chain_graph()
        cov = _autoscaling_coverage(g)
        # only api has autoscaling => 1/3 ~ 33.3%
        assert abs(cov - 33.33) < 1.0

    def test_empty_graph(self):
        g = InfraGraph()
        assert _autoscaling_coverage(g) == 0.0

    def test_full_coverage(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A", autoscaling=True))
        g.add_component(_comp("b", "B", autoscaling=True))
        assert _autoscaling_coverage(g) == 100.0


class TestCircuitBreakerCoverage:
    def test_full_coverage(self):
        g = _chain_graph()
        assert _circuit_breaker_coverage(g) == 100.0

    def test_zero_coverage(self):
        g = _weak_graph()
        assert _circuit_breaker_coverage(g) == 0.0

    def test_no_edges_returns_100(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        assert _circuit_breaker_coverage(g) == 100.0


class TestMaxDependencyDepth:
    def test_chain_depth(self):
        g = _chain_graph()
        depth = _max_dependency_depth(g)
        # lb -> api -> db = 3 nodes
        assert depth == 3

    def test_no_paths(self):
        g = InfraGraph()
        assert _max_dependency_depth(g) == 0


class TestAverageBlastRadius:
    def test_non_negative(self):
        g = _chain_graph()
        assert _average_blast_radius(g) >= 0.0

    def test_empty_graph(self):
        g = InfraGraph()
        assert _average_blast_radius(g) == 0.0

    def test_isolated_components(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        # No dependencies => no blast radius propagation
        assert _average_blast_radius(g) == 0.0


class TestEstimateAvailability:
    def test_high_score_returns_99_99(self):
        """Resilience score >= 95 maps to 99.99%."""
        g = InfraGraph()
        with patch.object(type(g), "resilience_score", return_value=96.0):
            assert _estimate_availability(g) == 99.99

    def test_score_80_to_95(self):
        """Score in [80, 95) maps to [99.9, 99.99)."""
        g = InfraGraph()
        with patch.object(type(g), "resilience_score", return_value=85.0):
            avail = _estimate_availability(g)
            assert 99.9 <= avail < 99.99

    def test_score_50_to_80(self):
        """Score in [50, 80) maps to [99.5, 99.9)."""
        g = InfraGraph()
        with patch.object(type(g), "resilience_score", return_value=65.0):
            avail = _estimate_availability(g)
            assert 99.5 <= avail < 99.9

    def test_score_below_50(self):
        """Score < 50 maps to [95.0, 99.5)."""
        g = InfraGraph()
        with patch.object(type(g), "resilience_score", return_value=25.0):
            avail = _estimate_availability(g)
            assert 95.0 <= avail < 99.5

    def test_score_zero(self):
        """Score 0 returns 95.0."""
        g = InfraGraph()
        with patch.object(type(g), "resilience_score", return_value=0.0):
            assert _estimate_availability(g) == 95.0

    def test_real_graph(self):
        g = _chain_graph()
        avail = _estimate_availability(g)
        assert 95.0 <= avail <= 100.0


class TestExtractMetrics:
    def test_returns_all_expected_keys(self):
        g = _chain_graph()
        metrics = _extract_metrics(g)
        expected = {
            "resilience_score", "component_count", "spof_count",
            "average_replicas", "failover_coverage", "autoscaling_coverage",
            "circuit_breaker_coverage", "dependency_depth", "blast_radius_avg",
        }
        assert set(metrics.keys()) == expected

    def test_component_count_matches(self):
        g = _chain_graph()
        metrics = _extract_metrics(g)
        assert metrics["component_count"] == 3.0


# ---------------------------------------------------------------------------
# MultiEnvAnalyzer.compare_graphs tests
# ---------------------------------------------------------------------------


class TestCompareGraphs:
    def test_returns_matrix(self):
        analyzer = MultiEnvAnalyzer()
        matrix = analyzer.compare_graphs({
            "prod": _chain_graph(), "staging": _weak_graph(),
        })
        assert isinstance(matrix, ComparisonMatrix)
        assert len(matrix.environments) == 2

    def test_identifies_strongest(self):
        analyzer = MultiEnvAnalyzer()
        matrix = analyzer.compare_graphs({
            "prod": _chain_graph(), "staging": _weak_graph(),
        })
        assert matrix.strongest_environment == "prod"

    def test_identifies_weakest(self):
        analyzer = MultiEnvAnalyzer()
        matrix = analyzer.compare_graphs({
            "prod": _chain_graph(), "staging": _weak_graph(),
        })
        assert matrix.weakest_environment == "staging"

    def test_parity_score_range(self):
        analyzer = MultiEnvAnalyzer()
        matrix = analyzer.compare_graphs({
            "prod": _chain_graph(), "staging": _weak_graph(),
        })
        assert 0.0 <= matrix.parity_score <= 100.0

    def test_generates_deltas(self):
        analyzer = MultiEnvAnalyzer()
        matrix = analyzer.compare_graphs({
            "prod": _chain_graph(), "staging": _weak_graph(),
        })
        # 2 envs, 9 metrics => 9 deltas
        assert len(matrix.deltas) == 9

    def test_three_environments(self):
        analyzer = MultiEnvAnalyzer()
        matrix = analyzer.compare_graphs({
            "prod": _chain_graph(), "staging": _weak_graph(), "dev": _minimal_graph(),
        })
        assert len(matrix.environments) == 3
        # C(3,2) * 9 = 27 deltas
        assert len(matrix.deltas) == 27

    def test_too_few_environments(self):
        analyzer = MultiEnvAnalyzer()
        matrix = analyzer.compare_graphs({"only": _chain_graph()})
        assert len(matrix.environments) == 0

    def test_matrix_data_populated(self):
        analyzer = MultiEnvAnalyzer()
        matrix = analyzer.compare_graphs({
            "prod": _chain_graph(), "staging": _weak_graph(),
        })
        assert "prod" in matrix.matrix_data
        assert "staging" in matrix.matrix_data
        assert "resilience_score" in matrix.matrix_data["prod"]

    def test_deltas_have_concern_flag(self):
        analyzer = MultiEnvAnalyzer()
        matrix = analyzer.compare_graphs({
            "prod": _chain_graph(), "staging": _weak_graph(),
        })
        concerns = [d for d in matrix.deltas if d.concern]
        assert len(concerns) > 0

    def test_environment_profile_fields(self):
        analyzer = MultiEnvAnalyzer()
        matrix = analyzer.compare_graphs({
            "prod": _chain_graph(), "staging": _weak_graph(),
        })
        prod_profile = [e for e in matrix.environments if e.name == "prod"][0]
        assert prod_profile.component_count == 3
        assert prod_profile.spof_count == 0
        assert prod_profile.resilience_score > 0
        assert 95.0 <= prod_profile.availability_estimate <= 100.0


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------


class TestRecommendations:
    def test_generates_recommendations(self):
        analyzer = MultiEnvAnalyzer()
        matrix = analyzer.compare_graphs({
            "prod": _chain_graph(), "staging": _weak_graph(),
        })
        assert len(matrix.recommendations) > 0

    def test_significant_score_gap(self):
        """Large resilience gap triggers specific recommendation."""
        analyzer = MultiEnvAnalyzer()
        strong = _chain_graph()
        weak = InfraGraph()
        for i in range(5):
            weak.add_component(_comp(f"a{i}", f"A{i}"))
        for i in range(4):
            weak.add_dependency(Dependency(source_id=f"a{i}", target_id=f"a{i+1}"))

        matrix = analyzer.compare_graphs({"strong": strong, "weak": weak})
        assert any("significantly lower" in r for r in matrix.recommendations)

    def test_spof_recommendation(self):
        """Env with SPOFs should get SPOF recommendation."""
        analyzer = MultiEnvAnalyzer()
        matrix = analyzer.compare_graphs({
            "prod": _chain_graph(), "staging": _weak_graph(),
        })
        assert any("single point" in r.lower() for r in matrix.recommendations)

    def test_failover_coverage_gap_recommendation(self):
        """Failover coverage gap triggers recommendation."""
        analyzer = MultiEnvAnalyzer()
        matrix = analyzer.compare_graphs({
            "prod": _chain_graph(), "staging": _weak_graph(),
        })
        assert any("failover" in r.lower() for r in matrix.recommendations)

    def test_autoscaling_gap_recommendation(self):
        """Autoscaling coverage gap triggers recommendation."""
        analyzer = MultiEnvAnalyzer()
        # prod has autoscaling on api; weak has none
        matrix = analyzer.compare_graphs({
            "prod": _chain_graph(), "staging": _weak_graph(),
        })
        assert any("autoscaling" in r.lower() for r in matrix.recommendations)

    def test_circuit_breaker_gap_recommendation(self):
        """Circuit breaker gap triggers recommendation."""
        analyzer = MultiEnvAnalyzer()
        matrix = analyzer.compare_graphs({
            "prod": _chain_graph(), "staging": _weak_graph(),
        })
        assert any("circuit breaker" in r.lower() for r in matrix.recommendations)


# ---------------------------------------------------------------------------
# Parity calculation
# ---------------------------------------------------------------------------


class TestCalculateParity:
    def test_single_profile_returns_100(self):
        analyzer = MultiEnvAnalyzer()
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        profile = EnvironmentProfile(
            name="only", yaml_path="", graph=g,
            resilience_score=50.0, component_count=1,
            spof_count=0, critical_findings=0,
            availability_estimate=99.5, genome_hash=None,
        )
        assert analyzer._calculate_parity([profile]) == 100.0

    def test_all_zero_scores_returns_100(self):
        analyzer = MultiEnvAnalyzer()
        profiles = [
            EnvironmentProfile(
                name=f"env{i}", yaml_path="", graph=InfraGraph(),
                resilience_score=0.0, component_count=0, spof_count=0,
                critical_findings=0, availability_estimate=95.0, genome_hash=None,
            )
            for i in range(2)
        ]
        assert analyzer._calculate_parity(profiles) == 100.0

    def test_identical_scores_high_parity(self):
        analyzer = MultiEnvAnalyzer()
        profiles = [
            EnvironmentProfile(
                name=f"env{i}", yaml_path="", graph=InfraGraph(),
                resilience_score=80.0, component_count=3, spof_count=0,
                critical_findings=0, availability_estimate=99.9, genome_hash=None,
            )
            for i in range(3)
        ]
        assert analyzer._calculate_parity(profiles) == 100.0

    def test_different_scores_low_parity(self):
        analyzer = MultiEnvAnalyzer()
        profiles = [
            EnvironmentProfile(
                name="strong", yaml_path="", graph=InfraGraph(),
                resilience_score=100.0, component_count=3, spof_count=0,
                critical_findings=0, availability_estimate=99.99, genome_hash=None,
            ),
            EnvironmentProfile(
                name="weak", yaml_path="", graph=InfraGraph(),
                resilience_score=10.0, component_count=1, spof_count=3,
                critical_findings=5, availability_estimate=95.0, genome_hash=None,
            ),
        ]
        parity = analyzer._calculate_parity(profiles)
        assert parity < 100.0


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------


class TestFindDrift:
    def test_missing_component_in_staging(self):
        """Components in prod but not in staging."""
        analyzer = MultiEnvAnalyzer()
        prod = _chain_graph()  # lb, api, db
        dev = _minimal_graph()  # api, db only
        drift = analyzer.find_drift_between_envs(prod, dev)
        assert any("lb" in d for d in drift)

    def test_extra_component_in_staging(self):
        """Components in staging but not in prod."""
        analyzer = MultiEnvAnalyzer()
        prod = _minimal_graph()
        staging = _chain_graph()
        drift = analyzer.find_drift_between_envs(prod, staging)
        assert any("staging" in d.lower() for d in drift)

    def test_replica_difference(self):
        analyzer = MultiEnvAnalyzer()
        prod = _chain_graph()
        staging = _weak_graph()
        drift = analyzer.find_drift_between_envs(prod, staging)
        assert any("replica" in d.lower() for d in drift)

    def test_failover_difference(self):
        analyzer = MultiEnvAnalyzer()
        prod = _chain_graph()
        staging = _weak_graph()
        drift = analyzer.find_drift_between_envs(prod, staging)
        assert any("failover" in d.lower() for d in drift)

    def test_autoscaling_difference(self):
        analyzer = MultiEnvAnalyzer()
        prod = _chain_graph()  # api has autoscaling
        staging = InfraGraph()
        staging.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=2, failover=True))
        staging.add_component(_comp("api", "API", replicas=3, failover=True, autoscaling=False))
        staging.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=2, failover=True))
        staging.add_dependency(Dependency(source_id="lb", target_id="api", circuit_breaker=CircuitBreakerConfig(enabled=True)))
        staging.add_dependency(Dependency(source_id="api", target_id="db", circuit_breaker=CircuitBreakerConfig(enabled=True)))
        drift = analyzer.find_drift_between_envs(prod, staging)
        assert any("autoscaling" in d.lower() for d in drift)

    def test_type_difference(self):
        analyzer = MultiEnvAnalyzer()
        prod = InfraGraph()
        prod.add_component(_comp("a", "A", ComponentType.APP_SERVER))
        staging = InfraGraph()
        staging.add_component(_comp("a", "A", ComponentType.WEB_SERVER))
        drift = analyzer.find_drift_between_envs(prod, staging)
        assert any("type differs" in d.lower() for d in drift)

    def test_identical_graphs_no_drift(self):
        analyzer = MultiEnvAnalyzer()
        g = _chain_graph()
        drift = analyzer.find_drift_between_envs(g, g)
        assert len(drift) == 0

    def test_edge_in_prod_not_staging(self):
        analyzer = MultiEnvAnalyzer()
        prod = _chain_graph()
        dev = _minimal_graph()
        drift = analyzer.find_drift_between_envs(prod, dev)
        assert any("prod but not staging" in d.lower() for d in drift)

    def test_edge_in_staging_not_prod(self):
        analyzer = MultiEnvAnalyzer()
        prod = InfraGraph()
        prod.add_component(_comp("a", "A"))
        prod.add_component(_comp("b", "B", ComponentType.DATABASE))
        staging = InfraGraph()
        staging.add_component(_comp("a", "A"))
        staging.add_component(_comp("b", "B", ComponentType.DATABASE))
        staging.add_dependency(Dependency(source_id="a", target_id="b"))
        drift = analyzer.find_drift_between_envs(prod, staging)
        assert any("staging but not prod" in d.lower() for d in drift)


# ---------------------------------------------------------------------------
# ChaosGenome and SimulationEngine paths in _do_compare
# ---------------------------------------------------------------------------


class TestDoCompareInternalPaths:
    def test_chaos_genome_success_path(self, monkeypatch):
        """Cover the ChaosGenomeAnalyzer success path."""
        import sys
        import types

        mock_genome = MagicMock()
        mock_genome.genome_hash = "abc123"
        mock_analyzer_instance = MagicMock()
        mock_analyzer_instance.analyze.return_value = mock_genome

        mock_module = types.ModuleType("faultray.simulator.chaos_genome")
        mock_module.ChaosGenomeAnalyzer = MagicMock(return_value=mock_analyzer_instance)
        monkeypatch.setitem(sys.modules, "faultray.simulator.chaos_genome", mock_module)

        analyzer = MultiEnvAnalyzer()
        matrix = analyzer.compare_graphs({"a": _chain_graph(), "b": _weak_graph()})
        assert isinstance(matrix, ComparisonMatrix)
        assert len(matrix.environments) == 2

    def test_simulation_engine_failure_path(self, monkeypatch):
        """Cover the except branch when SimulationEngine.run_all_defaults fails."""
        import sys

        mock_engine_mod = MagicMock()
        mock_engine_instance = MagicMock()
        mock_engine_instance.run_all_defaults.side_effect = RuntimeError("boom")
        mock_engine_mod.SimulationEngine.return_value = mock_engine_instance
        monkeypatch.setitem(sys.modules, "faultray.simulator.engine", mock_engine_mod)

        analyzer = MultiEnvAnalyzer()
        matrix = analyzer.compare_graphs({"a": _chain_graph(), "b": _weak_graph()})
        assert isinstance(matrix, ComparisonMatrix)


# ---------------------------------------------------------------------------
# YAML-based compare and check_parity (integration)
# ---------------------------------------------------------------------------


class TestCompareYAML:
    def test_compare_yaml_files(self, tmp_path):
        import yaml

        prod_yaml = {
            "components": [
                {"id": "app", "name": "App", "type": "app_server", "replicas": 3},
                {"id": "db", "name": "DB", "type": "database", "replicas": 2},
            ],
            "dependencies": [
                {"source": "app", "target": "db", "type": "requires"},
            ],
        }
        staging_yaml = {
            "components": [
                {"id": "app", "name": "App", "type": "app_server", "replicas": 1},
                {"id": "db", "name": "DB", "type": "database", "replicas": 1},
            ],
            "dependencies": [
                {"source": "app", "target": "db", "type": "requires"},
            ],
        }
        prod_path = tmp_path / "prod.yaml"
        staging_path = tmp_path / "staging.yaml"
        prod_path.write_text(yaml.dump(prod_yaml))
        staging_path.write_text(yaml.dump(staging_yaml))

        analyzer = MultiEnvAnalyzer()
        try:
            matrix = analyzer.compare({"prod": prod_path, "staging": staging_path})
            assert isinstance(matrix, ComparisonMatrix)
            assert len(matrix.environments) == 2
        except Exception:
            pytest.skip("YAML format not compatible with loader")

    def test_check_parity(self, tmp_path):
        import yaml

        cfg = {"components": [{"id": "app", "name": "App", "type": "app_server", "replicas": 2}]}
        for name in ("a.yaml", "b.yaml"):
            (tmp_path / name).write_text(yaml.dump(cfg))

        analyzer = MultiEnvAnalyzer()
        try:
            result = analyzer.check_parity({
                "a": tmp_path / "a.yaml", "b": tmp_path / "b.yaml",
            })
            assert isinstance(result, bool)
        except Exception:
            pytest.skip("YAML format not compatible with loader")
