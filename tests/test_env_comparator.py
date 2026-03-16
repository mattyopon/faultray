"""Tests for Multi-Environment Comparison (env_comparator)."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    Component,
    ComponentType,
    CostProfile,
    Dependency,
    FailoverConfig,
    HealthStatus,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.env_comparator import (
    EnvironmentComparator,
    EnvironmentProfile,
    EnvComparisonResult,
    _cost_monthly,
    _security_score,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
    failover: FailoverConfig | None = None,
    autoscaling: AutoScalingConfig | None = None,
    security: SecurityProfile | None = None,
    cost_profile: CostProfile | None = None,
    capacity: Capacity | None = None,
) -> Component:
    kwargs: dict = dict(id=cid, name=name, type=ctype, replicas=replicas)
    if failover is not None:
        kwargs["failover"] = failover
    if autoscaling is not None:
        kwargs["autoscaling"] = autoscaling
    if security is not None:
        kwargs["security"] = security
    if cost_profile is not None:
        kwargs["cost_profile"] = cost_profile
    if capacity is not None:
        kwargs["capacity"] = capacity
    c = Component(**kwargs)
    c.health = health
    return c


def _chain_graph() -> InfraGraph:
    """Simple 3-node chain: lb -> api -> db."""
    g = InfraGraph()
    g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=2))
    g.add_component(_comp("api", "API", replicas=3))
    g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=2))
    g.add_dependency(Dependency(source_id="lb", target_id="api"))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    return g


def _secured_graph() -> InfraGraph:
    """Graph with full security profile enabled on all components."""
    g = InfraGraph()
    full_sec = SecurityProfile(
        encryption_at_rest=True,
        encryption_in_transit=True,
        waf_protected=True,
        rate_limiting=True,
        auth_required=True,
        network_segmented=True,
        backup_enabled=True,
        log_enabled=True,
        ids_monitored=True,
    )
    g.add_component(_comp(
        "lb", "LB", ComponentType.LOAD_BALANCER, replicas=2,
        security=full_sec,
        failover=FailoverConfig(enabled=True),
        cost_profile=CostProfile(hourly_infra_cost=0.50),
    ))
    g.add_component(_comp(
        "app", "App", ComponentType.APP_SERVER, replicas=3,
        security=full_sec,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
        cost_profile=CostProfile(hourly_infra_cost=1.00),
    ))
    g.add_component(_comp(
        "db", "DB", ComponentType.DATABASE, replicas=2,
        security=full_sec,
        failover=FailoverConfig(enabled=True),
        cost_profile=CostProfile(hourly_infra_cost=2.00),
    ))
    g.add_dependency(Dependency(source_id="lb", target_id="app"))
    g.add_dependency(Dependency(source_id="app", target_id="db"))
    return g


def _minimal_graph() -> InfraGraph:
    """Graph with no security, minimal cost, single replica."""
    g = InfraGraph()
    g.add_component(_comp(
        "lb", "LB", ComponentType.LOAD_BALANCER,
        cost_profile=CostProfile(hourly_infra_cost=0.10),
    ))
    g.add_component(_comp(
        "app", "App", ComponentType.APP_SERVER,
        cost_profile=CostProfile(hourly_infra_cost=0.20),
    ))
    g.add_component(_comp(
        "db", "DB", ComponentType.DATABASE,
        cost_profile=CostProfile(hourly_infra_cost=0.50),
    ))
    g.add_dependency(Dependency(source_id="lb", target_id="app"))
    g.add_dependency(Dependency(source_id="app", target_id="db"))
    return g


@pytest.fixture
def comparator() -> EnvironmentComparator:
    return EnvironmentComparator()


# ---------------------------------------------------------------------------
# Tests: _security_score helper
# ---------------------------------------------------------------------------


class TestSecurityScore:
    def test_empty_graph_returns_zero(self):
        assert _security_score(InfraGraph()) == 0.0

    def test_full_security_returns_100(self):
        """All 9 security checks enabled => score 100."""
        g = InfraGraph()
        g.add_component(_comp("a", "A", security=SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            waf_protected=True,
            rate_limiting=True,
            auth_required=True,
            network_segmented=True,
            backup_enabled=True,
            log_enabled=True,
            ids_monitored=True,
        )))
        assert _security_score(g) == 100.0

    def test_no_security_returns_zero(self):
        """All security checks disabled => score 0."""
        g = InfraGraph()
        g.add_component(_comp("a", "A", security=SecurityProfile()))
        assert _security_score(g) == 0.0

    def test_partial_security(self):
        """Some checks enabled => score between 0 and 100."""
        g = InfraGraph()
        g.add_component(_comp("a", "A", security=SecurityProfile(
            encryption_at_rest=True,
            log_enabled=True,
        )))
        score = _security_score(g)
        assert 0.0 < score < 100.0

    def test_multiple_components_averaged(self):
        """Security score is averaged across multiple components."""
        g = InfraGraph()
        g.add_component(_comp("a", "A", security=SecurityProfile(
            encryption_at_rest=True, encryption_in_transit=True,
            waf_protected=True, rate_limiting=True,
            auth_required=True, network_segmented=True,
            backup_enabled=True, log_enabled=True, ids_monitored=True,
        )))
        g.add_component(_comp("b", "B", security=SecurityProfile()))
        score = _security_score(g)
        # average of 100 and 0 => 50
        assert score == 50.0

    def test_secured_higher_than_minimal(self):
        assert _security_score(_secured_graph()) > _security_score(_minimal_graph())


# ---------------------------------------------------------------------------
# Tests: _cost_monthly helper
# ---------------------------------------------------------------------------


class TestCostMonthly:
    def test_empty_graph_returns_zero(self):
        assert _cost_monthly(InfraGraph()) == 0.0

    def test_hourly_conversion(self):
        """hourly * 730 hours/month."""
        g = InfraGraph()
        g.add_component(_comp("a", "A", cost_profile=CostProfile(hourly_infra_cost=1.0)))
        assert _cost_monthly(g) == 730.0

    def test_monthly_contract_preferred(self):
        """monthly_contract_value takes precedence over hourly."""
        g = InfraGraph()
        g.add_component(_comp("a", "A", cost_profile=CostProfile(
            hourly_infra_cost=1.0, monthly_contract_value=500.0,
        )))
        assert _cost_monthly(g) == 500.0

    def test_zero_cost_component(self):
        """Components with no cost configured contribute 0."""
        g = InfraGraph()
        g.add_component(_comp("a", "A", cost_profile=CostProfile()))
        assert _cost_monthly(g) == 0.0

    def test_multiple_components_summed(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A", cost_profile=CostProfile(hourly_infra_cost=1.0)))
        g.add_component(_comp("b", "B", cost_profile=CostProfile(hourly_infra_cost=2.0)))
        assert _cost_monthly(g) == round((1.0 + 2.0) * 730, 2)

    def test_mixed_hourly_and_contract(self):
        """One component with hourly, another with monthly contract."""
        g = InfraGraph()
        g.add_component(_comp("a", "A", cost_profile=CostProfile(hourly_infra_cost=1.0)))
        g.add_component(_comp("b", "B", cost_profile=CostProfile(monthly_contract_value=200.0)))
        assert _cost_monthly(g) == round(730.0 + 200.0, 2)

    def test_secured_graph_cost_positive(self):
        assert _cost_monthly(_secured_graph()) > 0


# ---------------------------------------------------------------------------
# Tests: EnvironmentComparator.compare - basic
# ---------------------------------------------------------------------------


class TestCompareBasic:
    def test_needs_at_least_two_envs(self, comparator):
        result = comparator.compare({"only": _chain_graph()})
        assert isinstance(result, EnvComparisonResult)
        assert len(result.environments) == 0
        assert result.parity_score == 0.0

    def test_empty_envs(self, comparator):
        result = comparator.compare({})
        assert len(result.environments) == 0

    def test_two_envs_returns_profiles(self, comparator):
        envs = {"prod": _secured_graph(), "dev": _minimal_graph()}
        result = comparator.compare(envs)
        assert len(result.environments) == 2
        names = {ep.name for ep in result.environments}
        assert names == {"prod", "dev"}

    def test_three_envs(self, comparator):
        envs = {
            "prod": _secured_graph(),
            "staging": _chain_graph(),
            "dev": _minimal_graph(),
        }
        result = comparator.compare(envs)
        assert len(result.environments) == 3

    def test_profiles_have_valid_scores(self, comparator):
        envs = {"a": _secured_graph(), "b": _minimal_graph()}
        result = comparator.compare(envs)
        for ep in result.environments:
            assert isinstance(ep, EnvironmentProfile)
            assert ep.resilience_score >= 0
            assert ep.security_score >= 0
            assert ep.cost_monthly >= 0
            assert ep.component_count > 0

    def test_identical_envs_high_parity(self, comparator):
        g = _secured_graph()
        result = comparator.compare({"a": g, "b": g})
        assert result.parity_score >= 95.0
        assert result.drift_detected is False

    def test_different_envs_lower_parity(self, comparator):
        result = comparator.compare({
            "prod": _secured_graph(),
            "dev": _minimal_graph(),
        })
        assert result.parity_score < 100.0

    def test_parity_score_range(self, comparator):
        result = comparator.compare({
            "prod": _secured_graph(),
            "dev": _minimal_graph(),
        })
        assert 0.0 <= result.parity_score <= 100.0


# ---------------------------------------------------------------------------
# Tests: detect_drift
# ---------------------------------------------------------------------------


class TestDetectDrift:
    def test_identical_graphs_no_drift(self, comparator):
        g = _secured_graph()
        drift = comparator.detect_drift(g, g, env_a_name="a", env_b_name="b")
        assert len(drift) == 0

    def test_replica_drift(self, comparator):
        """Different replica counts are detected."""
        a = InfraGraph()
        a.add_component(_comp("svc", "Svc", replicas=3))
        b = InfraGraph()
        b.add_component(_comp("svc", "Svc", replicas=1))
        drift = comparator.detect_drift(a, b, env_a_name="prod", env_b_name="dev")
        replica_drifts = [d for d in drift if d["field"] == "replicas"]
        assert len(replica_drifts) == 1
        assert replica_drifts[0]["prod_value"] == 3
        assert replica_drifts[0]["dev_value"] == 1

    def test_type_drift(self, comparator):
        """Different component types are detected."""
        a = InfraGraph()
        a.add_component(_comp("svc", "Svc", ComponentType.APP_SERVER))
        b = InfraGraph()
        b.add_component(_comp("svc", "Svc", ComponentType.WEB_SERVER))
        drift = comparator.detect_drift(a, b, env_a_name="a", env_b_name="b")
        type_drifts = [d for d in drift if d["field"] == "type"]
        assert len(type_drifts) == 1
        assert type_drifts[0]["a_value"] == ComponentType.APP_SERVER.value
        assert type_drifts[0]["b_value"] == ComponentType.WEB_SERVER.value

    def test_failover_drift(self, comparator):
        """Different failover settings are detected."""
        a = InfraGraph()
        a.add_component(_comp("svc", "Svc", failover=FailoverConfig(enabled=True)))
        b = InfraGraph()
        b.add_component(_comp("svc", "Svc", failover=FailoverConfig(enabled=False)))
        drift = comparator.detect_drift(a, b, env_a_name="a", env_b_name="b")
        fo_drifts = [d for d in drift if d["field"] == "failover"]
        assert len(fo_drifts) == 1
        assert fo_drifts[0]["a_value"] is True
        assert fo_drifts[0]["b_value"] is False

    def test_autoscaling_drift(self, comparator):
        """Different autoscaling settings are detected."""
        a = InfraGraph()
        a.add_component(_comp("svc", "Svc", autoscaling=AutoScalingConfig(enabled=True)))
        b = InfraGraph()
        b.add_component(_comp("svc", "Svc"))
        drift = comparator.detect_drift(a, b, env_a_name="a", env_b_name="b")
        as_drifts = [d for d in drift if d["field"] == "autoscaling"]
        assert len(as_drifts) == 1

    def test_security_field_drift(self, comparator):
        """Differences in individual security profile fields are detected."""
        a = InfraGraph()
        a.add_component(_comp("svc", "Svc", security=SecurityProfile(
            encryption_at_rest=True, encryption_in_transit=True,
            waf_protected=True, rate_limiting=True,
            auth_required=True, network_segmented=True,
            backup_enabled=True,
        )))
        b = InfraGraph()
        b.add_component(_comp("svc", "Svc", security=SecurityProfile()))
        drift = comparator.detect_drift(a, b, env_a_name="prod", env_b_name="dev")
        sec_drifts = [d for d in drift if d["field"].startswith("security.")]
        # All 7 checked security fields should differ
        assert len(sec_drifts) == 7
        fields = {d["field"] for d in sec_drifts}
        for attr in (
            "encryption_at_rest", "encryption_in_transit", "waf_protected",
            "rate_limiting", "auth_required", "network_segmented", "backup_enabled",
        ):
            assert f"security.{attr}" in fields

    def test_capacity_max_rps_drift(self, comparator):
        """Different max_rps values are detected."""
        a = InfraGraph()
        a.add_component(_comp("svc", "Svc", capacity=Capacity(max_rps=10000)))
        b = InfraGraph()
        b.add_component(_comp("svc", "Svc", capacity=Capacity(max_rps=1000)))
        drift = comparator.detect_drift(a, b, env_a_name="a", env_b_name="b")
        cap_drifts = [d for d in drift if d["field"] == "capacity.max_rps"]
        assert len(cap_drifts) == 1
        assert cap_drifts[0]["a_value"] == 10000
        assert cap_drifts[0]["b_value"] == 1000

    def test_missing_component_a_only(self, comparator):
        """Component present in env_a but missing in env_b."""
        a = InfraGraph()
        a.add_component(_comp("svc", "Svc"))
        a.add_component(_comp("extra", "Extra"))
        b = InfraGraph()
        b.add_component(_comp("svc", "Svc"))
        drift = comparator.detect_drift(a, b, env_a_name="a", env_b_name="b")
        exist_drifts = [d for d in drift if d["field"] == "existence"]
        assert len(exist_drifts) == 1
        assert exist_drifts[0]["component"] == "extra"
        assert exist_drifts[0]["a_value"] == "present"
        assert exist_drifts[0]["b_value"] == "missing"

    def test_missing_component_b_only(self, comparator):
        """Component present in env_b but missing in env_a."""
        a = InfraGraph()
        a.add_component(_comp("svc", "Svc"))
        b = InfraGraph()
        b.add_component(_comp("svc", "Svc"))
        b.add_component(_comp("extra", "Extra"))
        drift = comparator.detect_drift(a, b, env_a_name="a", env_b_name="b")
        exist_drifts = [d for d in drift if d["field"] == "existence"]
        assert len(exist_drifts) == 1
        assert exist_drifts[0]["a_value"] == "missing"
        assert exist_drifts[0]["b_value"] == "present"

    def test_default_env_names(self, comparator):
        """Default env names are 'env_a' and 'env_b'."""
        a = InfraGraph()
        a.add_component(_comp("svc", "Svc", replicas=2))
        b = InfraGraph()
        b.add_component(_comp("svc", "Svc", replicas=1))
        drift = comparator.detect_drift(a, b)
        assert any("env_a_value" in d for d in drift)
        assert any("env_b_value" in d for d in drift)

    def test_multiple_drifts_combined(self, comparator):
        """Multiple fields differing on same component produce multiple drift entries."""
        a = InfraGraph()
        a.add_component(_comp("svc", "Svc", replicas=3,
                              failover=FailoverConfig(enabled=True),
                              autoscaling=AutoScalingConfig(enabled=True)))
        b = InfraGraph()
        b.add_component(_comp("svc", "Svc", replicas=1))
        drift = comparator.detect_drift(a, b, env_a_name="a", env_b_name="b")
        fields = {d["field"] for d in drift}
        assert "replicas" in fields
        assert "failover" in fields
        assert "autoscaling" in fields


# ---------------------------------------------------------------------------
# Tests: _calculate_parity
# ---------------------------------------------------------------------------


class TestCalculateParity:
    def test_single_profile_returns_100(self, comparator):
        p = EnvironmentProfile(
            name="only", graph=InfraGraph(),
            resilience_score=80.0, security_score=70.0,
            cost_monthly=100.0, component_count=3,
        )
        assert comparator._calculate_parity([p]) == 100.0

    def test_identical_profiles_return_100(self, comparator):
        p1 = EnvironmentProfile(
            name="a", graph=InfraGraph(),
            resilience_score=80.0, security_score=70.0,
            cost_monthly=100.0, component_count=3,
        )
        p2 = EnvironmentProfile(
            name="b", graph=InfraGraph(),
            resilience_score=80.0, security_score=70.0,
            cost_monthly=100.0, component_count=3,
        )
        assert comparator._calculate_parity([p1, p2]) == 100.0

    def test_zero_scores_returns_100(self, comparator):
        """When max_v=0 for all metrics, spread is 0 => parity 100."""
        p1 = EnvironmentProfile(
            name="a", graph=InfraGraph(),
            resilience_score=0.0, security_score=0.0,
            cost_monthly=0.0, component_count=0,
        )
        p2 = EnvironmentProfile(
            name="b", graph=InfraGraph(),
            resilience_score=0.0, security_score=0.0,
            cost_monthly=0.0, component_count=0,
        )
        assert comparator._calculate_parity([p1, p2]) == 100.0

    def test_spread_reduces_parity(self, comparator):
        p1 = EnvironmentProfile(
            name="a", graph=InfraGraph(),
            resilience_score=100.0, security_score=100.0,
            cost_monthly=100.0, component_count=10,
        )
        p2 = EnvironmentProfile(
            name="b", graph=InfraGraph(),
            resilience_score=0.0, security_score=0.0,
            cost_monthly=0.0, component_count=0,
        )
        parity = comparator._calculate_parity([p1, p2])
        assert parity < 50.0

    def test_parity_non_negative(self, comparator):
        p1 = EnvironmentProfile(
            name="a", graph=InfraGraph(),
            resilience_score=100.0, security_score=100.0,
            cost_monthly=1000.0, component_count=100,
        )
        p2 = EnvironmentProfile(
            name="b", graph=InfraGraph(),
            resilience_score=0.0, security_score=0.0,
            cost_monthly=0.0, component_count=0,
        )
        parity = comparator._calculate_parity([p1, p2])
        assert parity >= 0.0


# ---------------------------------------------------------------------------
# Tests: _generate_recommendations
# ---------------------------------------------------------------------------


class TestGenerateRecommendations:
    def test_no_drift_no_gap_minimal_recs(self, comparator):
        """Identical profiles with no drift => no recommendations."""
        p = EnvironmentProfile(
            name="a", graph=InfraGraph(),
            resilience_score=80.0, security_score=80.0,
            cost_monthly=100.0, component_count=3,
        )
        recs = comparator._generate_recommendations([p, p], [])
        assert isinstance(recs, list)
        assert len(recs) == 0

    def test_resilience_gap_recommendation(self, comparator):
        """Resilience gap > 15 triggers a recommendation."""
        p1 = EnvironmentProfile(
            name="prod", graph=InfraGraph(),
            resilience_score=90.0, security_score=80.0,
            cost_monthly=100.0, component_count=3,
        )
        p2 = EnvironmentProfile(
            name="dev", graph=InfraGraph(),
            resilience_score=50.0, security_score=80.0,
            cost_monthly=50.0, component_count=3,
        )
        recs = comparator._generate_recommendations([p1, p2], [])
        assert any("resilience" in r.lower() for r in recs)
        assert any("dev" in r for r in recs)

    def test_resilience_gap_not_triggered_when_small(self, comparator):
        """Resilience gap <= 15 does not trigger recommendation."""
        p1 = EnvironmentProfile(
            name="a", graph=InfraGraph(),
            resilience_score=80.0, security_score=80.0,
            cost_monthly=100.0, component_count=3,
        )
        p2 = EnvironmentProfile(
            name="b", graph=InfraGraph(),
            resilience_score=70.0, security_score=80.0,
            cost_monthly=100.0, component_count=3,
        )
        recs = comparator._generate_recommendations([p1, p2], [])
        assert not any("resilience" in r.lower() for r in recs)

    def test_security_gap_recommendation(self, comparator):
        """Security gap > 20 triggers a recommendation."""
        p1 = EnvironmentProfile(
            name="prod", graph=InfraGraph(),
            resilience_score=80.0, security_score=90.0,
            cost_monthly=100.0, component_count=3,
        )
        p2 = EnvironmentProfile(
            name="dev", graph=InfraGraph(),
            resilience_score=80.0, security_score=30.0,
            cost_monthly=50.0, component_count=3,
        )
        recs = comparator._generate_recommendations([p1, p2], [])
        assert any("security" in r.lower() for r in recs)

    def test_security_gap_not_triggered_when_small(self, comparator):
        p1 = EnvironmentProfile(
            name="a", graph=InfraGraph(),
            resilience_score=80.0, security_score=80.0,
            cost_monthly=100.0, component_count=3,
        )
        p2 = EnvironmentProfile(
            name="b", graph=InfraGraph(),
            resilience_score=80.0, security_score=70.0,
            cost_monthly=100.0, component_count=3,
        )
        recs = comparator._generate_recommendations([p1, p2], [])
        assert not any("security" in r.lower() for r in recs)

    def test_missing_component_recommendation(self, comparator):
        """Drift with existence field triggers missing-component rec."""
        p = EnvironmentProfile(
            name="a", graph=InfraGraph(),
            resilience_score=80.0, security_score=80.0,
            cost_monthly=100.0, component_count=3,
        )
        drift = [{"component": "svc", "field": "existence", "a_value": "present", "b_value": "missing"}]
        recs = comparator._generate_recommendations([p, p], drift)
        assert any("component" in r.lower() and "exist" in r.lower() for r in recs)

    def test_replica_drift_recommendation(self, comparator):
        """Drift with replicas field triggers replica-drift rec."""
        p = EnvironmentProfile(
            name="a", graph=InfraGraph(),
            resilience_score=80.0, security_score=80.0,
            cost_monthly=100.0, component_count=3,
        )
        drift = [{"component": "svc", "field": "replicas", "a_value": 3, "b_value": 1}]
        recs = comparator._generate_recommendations([p, p], drift)
        assert any("replica" in r.lower() for r in recs)

    def test_security_drift_recommendation(self, comparator):
        """Drift with security.* field triggers security-drift rec."""
        p = EnvironmentProfile(
            name="a", graph=InfraGraph(),
            resilience_score=80.0, security_score=80.0,
            cost_monthly=100.0, component_count=3,
        )
        drift = [{"component": "svc", "field": "security.encryption_at_rest",
                  "a_value": True, "b_value": False}]
        recs = comparator._generate_recommendations([p, p], drift)
        assert any("security" in r.lower() and "parity" in r.lower() for r in recs)

    def test_recommendations_deduplicated(self, comparator):
        """Duplicate recommendations are removed."""
        p1 = EnvironmentProfile(
            name="prod", graph=InfraGraph(),
            resilience_score=90.0, security_score=80.0,
            cost_monthly=100.0, component_count=3,
        )
        p2 = EnvironmentProfile(
            name="dev", graph=InfraGraph(),
            resilience_score=50.0, security_score=80.0,
            cost_monthly=50.0, component_count=3,
        )
        recs = comparator._generate_recommendations([p1, p2], [])
        # Should have no duplicates
        assert len(recs) == len(set(recs))

    def test_all_drift_types_together(self, comparator):
        """Drift details with multiple field types produce multiple recs."""
        p = EnvironmentProfile(
            name="a", graph=InfraGraph(),
            resilience_score=80.0, security_score=80.0,
            cost_monthly=100.0, component_count=3,
        )
        drift = [
            {"component": "svc", "field": "existence", "a_value": "present", "b_value": "missing"},
            {"component": "svc", "field": "replicas", "a_value": 3, "b_value": 1},
            {"component": "svc", "field": "security.waf_protected", "a_value": True, "b_value": False},
        ]
        recs = comparator._generate_recommendations([p, p], drift)
        assert len(recs) >= 3


# ---------------------------------------------------------------------------
# Tests: Full compare integration
# ---------------------------------------------------------------------------


class TestCompareIntegration:
    def test_drift_detected_flag(self, comparator):
        result = comparator.compare({
            "prod": _secured_graph(),
            "dev": _minimal_graph(),
        })
        assert result.drift_detected is True
        assert len(result.drift_details) > 0

    def test_no_drift_identical(self, comparator):
        g = _secured_graph()
        result = comparator.compare({"a": g, "b": g})
        assert result.drift_detected is False
        assert len(result.drift_details) == 0

    def test_recommendations_generated_for_different_envs(self, comparator):
        result = comparator.compare({
            "prod": _secured_graph(),
            "dev": _minimal_graph(),
        })
        assert len(result.recommendations) > 0

    def test_three_env_pairwise_drift(self, comparator):
        """Three environments => 3 pairs checked (ab, ac, bc)."""
        g1 = InfraGraph()
        g1.add_component(_comp("svc", "Svc", replicas=3))
        g2 = InfraGraph()
        g2.add_component(_comp("svc", "Svc", replicas=2))
        g3 = InfraGraph()
        g3.add_component(_comp("svc", "Svc", replicas=1))
        result = comparator.compare({"a": g1, "b": g2, "c": g3})
        # All 3 pairs should have replica drift
        replica_drifts = [d for d in result.drift_details if d["field"] == "replicas"]
        assert len(replica_drifts) == 3

    def test_result_parity_rounded(self, comparator):
        result = comparator.compare({
            "a": _secured_graph(),
            "b": _minimal_graph(),
        })
        # parity_score should be rounded to 1 decimal
        assert result.parity_score == round(result.parity_score, 1)

    def test_environment_profile_component_count(self, comparator):
        result = comparator.compare({
            "a": _secured_graph(),
            "b": _minimal_graph(),
        })
        for ep in result.environments:
            assert ep.component_count == 3
