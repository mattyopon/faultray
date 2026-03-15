"""Tests for Multi-Environment Comparison (env_comparator)."""

from __future__ import annotations

import pytest

from infrasim.model.components import (
    AutoScalingConfig,
    Capacity,
    Component,
    ComponentType,
    CostProfile,
    Dependency,
    FailoverConfig,
    SecurityProfile,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.env_comparator import (
    EnvironmentComparator,
    EnvironmentProfile,
    EnvComparisonResult,
    _cost_monthly,
    _security_score,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_prod_graph() -> InfraGraph:
    """Build a production-grade graph with redundancy and security."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2, port=443,
        failover=FailoverConfig(enabled=True),
        security=SecurityProfile(
            encryption_in_transit=True, waf_protected=True, rate_limiting=True,
            auth_required=True, network_segmented=True, backup_enabled=True,
            log_enabled=True, ids_monitored=True, encryption_at_rest=True,
        ),
        cost_profile=CostProfile(hourly_infra_cost=0.50),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=3,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
        security=SecurityProfile(
            encryption_in_transit=True, auth_required=True, log_enabled=True,
            encryption_at_rest=True,
        ),
        cost_profile=CostProfile(hourly_infra_cost=1.00),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=2,
        failover=FailoverConfig(enabled=True),
        security=SecurityProfile(
            encryption_at_rest=True, encryption_in_transit=True,
            backup_enabled=True, network_segmented=True, log_enabled=True,
        ),
        cost_profile=CostProfile(hourly_infra_cost=2.00),
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return graph


def _build_staging_graph() -> InfraGraph:
    """Build a staging graph with less redundancy."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=1, port=443,
        security=SecurityProfile(encryption_in_transit=True, log_enabled=True),
        cost_profile=CostProfile(hourly_infra_cost=0.25),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=2,
        security=SecurityProfile(encryption_in_transit=True, log_enabled=True),
        cost_profile=CostProfile(hourly_infra_cost=0.50),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=1,
        security=SecurityProfile(encryption_at_rest=True, log_enabled=True),
        cost_profile=CostProfile(hourly_infra_cost=1.00),
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return graph


def _build_dev_graph() -> InfraGraph:
    """Build a minimal dev graph."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=1, port=8080,
        cost_profile=CostProfile(hourly_infra_cost=0.10),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=1,
        cost_profile=CostProfile(hourly_infra_cost=0.20),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=1,
        cost_profile=CostProfile(hourly_infra_cost=0.50),
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return graph


@pytest.fixture
def comparator() -> EnvironmentComparator:
    return EnvironmentComparator()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEnvironmentComparatorBasic:
    def test_compare_returns_result(self, comparator: EnvironmentComparator):
        envs = {"prod": _build_prod_graph(), "staging": _build_staging_graph()}
        result = comparator.compare(envs)
        assert isinstance(result, EnvComparisonResult)
        assert len(result.environments) == 2

    def test_compare_needs_at_least_two(self, comparator: EnvironmentComparator):
        result = comparator.compare({"prod": _build_prod_graph()})
        assert len(result.environments) == 0

    def test_parity_score_range(self, comparator: EnvironmentComparator):
        envs = {"prod": _build_prod_graph(), "staging": _build_staging_graph(), "dev": _build_dev_graph()}
        result = comparator.compare(envs)
        assert 0 <= result.parity_score <= 100

    def test_identical_environments_high_parity(self, comparator: EnvironmentComparator):
        g = _build_prod_graph()
        result = comparator.compare({"a": g, "b": g})
        assert result.parity_score >= 95.0

    def test_environment_profiles_have_scores(self, comparator: EnvironmentComparator):
        envs = {"prod": _build_prod_graph(), "dev": _build_dev_graph()}
        result = comparator.compare(envs)
        for ep in result.environments:
            assert isinstance(ep, EnvironmentProfile)
            assert ep.resilience_score >= 0
            assert ep.security_score >= 0
            assert ep.component_count > 0


class TestDriftDetection:
    def test_detect_drift_replica_diff(self, comparator: EnvironmentComparator):
        drift = comparator.detect_drift(
            _build_prod_graph(), _build_staging_graph(),
            env_a_name="prod", env_b_name="staging",
        )
        replica_drifts = [d for d in drift if d["field"] == "replicas"]
        assert len(replica_drifts) > 0

    def test_detect_drift_failover_diff(self, comparator: EnvironmentComparator):
        drift = comparator.detect_drift(
            _build_prod_graph(), _build_staging_graph(),
            env_a_name="prod", env_b_name="staging",
        )
        failover_drifts = [d for d in drift if d["field"] == "failover"]
        assert len(failover_drifts) > 0

    def test_detect_drift_security_diff(self, comparator: EnvironmentComparator):
        drift = comparator.detect_drift(
            _build_prod_graph(), _build_dev_graph(),
            env_a_name="prod", env_b_name="dev",
        )
        sec_drifts = [d for d in drift if d["field"].startswith("security.")]
        assert len(sec_drifts) > 0

    def test_detect_drift_missing_component(self, comparator: EnvironmentComparator):
        prod = _build_prod_graph()
        dev = InfraGraph()
        dev.add_component(Component(id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=1))
        drift = comparator.detect_drift(prod, dev, env_a_name="prod", env_b_name="dev")
        existence_drifts = [d for d in drift if d["field"] == "existence"]
        assert len(existence_drifts) > 0

    def test_no_drift_identical(self, comparator: EnvironmentComparator):
        g = _build_prod_graph()
        drift = comparator.detect_drift(g, g, env_a_name="a", env_b_name="b")
        assert len(drift) == 0


class TestScoringHelpers:
    def test_security_score_range(self):
        score = _security_score(_build_prod_graph())
        assert 0 <= score <= 100

    def test_security_score_prod_higher_than_dev(self):
        assert _security_score(_build_prod_graph()) > _security_score(_build_dev_graph())

    def test_cost_monthly_positive(self):
        cost = _cost_monthly(_build_prod_graph())
        assert cost > 0

    def test_cost_monthly_prod_higher_than_dev(self):
        assert _cost_monthly(_build_prod_graph()) > _cost_monthly(_build_dev_graph())

    def test_empty_graph_security_score(self):
        assert _security_score(InfraGraph()) == 0.0

    def test_empty_graph_cost(self):
        assert _cost_monthly(InfraGraph()) == 0.0


class TestRecommendations:
    def test_recommendations_generated(self, comparator: EnvironmentComparator):
        envs = {"prod": _build_prod_graph(), "dev": _build_dev_graph()}
        result = comparator.compare(envs)
        assert len(result.recommendations) > 0

    def test_drift_detected_flag(self, comparator: EnvironmentComparator):
        envs = {"prod": _build_prod_graph(), "staging": _build_staging_graph()}
        result = comparator.compare(envs)
        assert result.drift_detected is True

    def test_no_drift_identical_envs(self, comparator: EnvironmentComparator):
        g = _build_prod_graph()
        result = comparator.compare({"a": g, "b": g})
        assert result.drift_detected is False
