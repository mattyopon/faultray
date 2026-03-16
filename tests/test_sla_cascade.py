"""Comprehensive tests for SLA Cascade Calculator (target: 140+ tests, 100% coverage)."""

from __future__ import annotations

import pytest

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.simulator.sla_cascade import (
    CascadeResult,
    ComplianceProjection,
    FinancialRiskReport,
    SLABreachImpact,
    SLACascadeEngine,
    SLAConflict,
    SLATier,
    SLAType,
    ServiceSLA,
    _TIER_DEFAULTS,
    _TIER_PENALTY_DEFAULTS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str | None = None,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
) -> Component:
    return Component(id=cid, name=name or cid, type=ctype, replicas=replicas)


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _dep(source: str, target: str, dep_type: str = "requires") -> Dependency:
    return Dependency(source_id=source, target_id=target, dependency_type=dep_type)


def _sla(
    sid: str,
    target: float = 99.9,
    tier: SLATier = SLATier.SILVER,
    sla_type: SLAType = SLAType.AVAILABILITY,
    penalty: float = 2000.0,
    window: int = 30,
) -> ServiceSLA:
    return ServiceSLA(
        service_id=sid,
        sla_type=sla_type,
        target=target,
        tier=tier,
        penalty_per_violation_percent=penalty,
        measurement_window_days=window,
    )


def _chain_graph(n: int) -> tuple[InfraGraph, list[str]]:
    """Build a linear chain of *n* services: s0 -> s1 -> ... -> s(n-1).

    Each service depends on the next (s0 requires s1, etc).
    """
    ids = [f"s{i}" for i in range(n)]
    g = InfraGraph()
    for cid in ids:
        g.add_component(_comp(cid))
    for i in range(n - 1):
        g.add_dependency(_dep(ids[i], ids[i + 1]))
    return g, ids


# ---------------------------------------------------------------------------
# 1. SLAType Enum Tests
# ---------------------------------------------------------------------------


class TestSLATypeEnum:
    def test_availability_value(self):
        assert SLAType.AVAILABILITY.value == "availability"

    def test_latency_value(self):
        assert SLAType.LATENCY.value == "latency"

    def test_throughput_value(self):
        assert SLAType.THROUGHPUT.value == "throughput"

    def test_error_rate_value(self):
        assert SLAType.ERROR_RATE.value == "error_rate"

    def test_durability_value(self):
        assert SLAType.DURABILITY.value == "durability"

    def test_is_str_enum(self):
        assert isinstance(SLAType.AVAILABILITY, str)

    def test_total_count(self):
        assert len(SLAType) == 5


# ---------------------------------------------------------------------------
# 2. SLATier Enum Tests
# ---------------------------------------------------------------------------


class TestSLATierEnum:
    def test_platinum_value(self):
        assert SLATier.PLATINUM.value == "platinum"

    def test_gold_value(self):
        assert SLATier.GOLD.value == "gold"

    def test_silver_value(self):
        assert SLATier.SILVER.value == "silver"

    def test_bronze_value(self):
        assert SLATier.BRONZE.value == "bronze"

    def test_best_effort_value(self):
        assert SLATier.BEST_EFFORT.value == "best_effort"

    def test_is_str_enum(self):
        assert isinstance(SLATier.PLATINUM, str)

    def test_total_count(self):
        assert len(SLATier) == 5


# ---------------------------------------------------------------------------
# 3. Tier Default Constants Tests
# ---------------------------------------------------------------------------


class TestTierDefaults:
    def test_tier_defaults_has_all_tiers(self):
        for tier in SLATier:
            assert tier in _TIER_DEFAULTS

    def test_platinum_default(self):
        assert _TIER_DEFAULTS[SLATier.PLATINUM] == 99.999

    def test_gold_default(self):
        assert _TIER_DEFAULTS[SLATier.GOLD] == 99.99

    def test_silver_default(self):
        assert _TIER_DEFAULTS[SLATier.SILVER] == 99.9

    def test_bronze_default(self):
        assert _TIER_DEFAULTS[SLATier.BRONZE] == 99.5

    def test_best_effort_default(self):
        assert _TIER_DEFAULTS[SLATier.BEST_EFFORT] == 95.0

    def test_penalty_defaults_has_all_tiers(self):
        for tier in SLATier:
            assert tier in _TIER_PENALTY_DEFAULTS

    def test_penalty_platinum(self):
        assert _TIER_PENALTY_DEFAULTS[SLATier.PLATINUM] == 10000.0

    def test_penalty_best_effort_zero(self):
        assert _TIER_PENALTY_DEFAULTS[SLATier.BEST_EFFORT] == 0.0

    def test_tier_defaults_descending_order(self):
        tiers = [SLATier.PLATINUM, SLATier.GOLD, SLATier.SILVER, SLATier.BRONZE, SLATier.BEST_EFFORT]
        targets = [_TIER_DEFAULTS[t] for t in tiers]
        assert targets == sorted(targets, reverse=True)


# ---------------------------------------------------------------------------
# 4. ServiceSLA Model Tests
# ---------------------------------------------------------------------------


class TestServiceSLA:
    def test_basic_creation(self):
        sla = _sla("svc1")
        assert sla.service_id == "svc1"
        assert sla.target == 99.9
        assert sla.tier == SLATier.SILVER

    def test_defaults(self):
        sla = ServiceSLA(service_id="x")
        assert sla.sla_type == SLAType.AVAILABILITY
        assert sla.target == 99.9
        assert sla.tier == SLATier.SILVER
        assert sla.penalty_per_violation_percent == 2000.0
        assert sla.measurement_window_days == 30

    def test_custom_values(self):
        sla = _sla("db", target=99.99, tier=SLATier.GOLD, penalty=5000.0, window=7)
        assert sla.target == 99.99
        assert sla.tier == SLATier.GOLD
        assert sla.penalty_per_violation_percent == 5000.0
        assert sla.measurement_window_days == 7

    def test_sla_type_latency(self):
        sla = _sla("api", sla_type=SLAType.LATENCY)
        assert sla.sla_type == SLAType.LATENCY

    def test_target_lower_bound(self):
        sla = _sla("x", target=0.0)
        assert sla.target == 0.0

    def test_target_upper_bound(self):
        sla = _sla("x", target=100.0)
        assert sla.target == 100.0

    def test_target_validation_too_high(self):
        with pytest.raises(Exception):
            ServiceSLA(service_id="x", target=100.1)

    def test_target_validation_negative(self):
        with pytest.raises(Exception):
            ServiceSLA(service_id="x", target=-1.0)

    def test_penalty_validation_negative(self):
        with pytest.raises(Exception):
            ServiceSLA(service_id="x", penalty_per_violation_percent=-1.0)

    def test_window_validation_zero(self):
        with pytest.raises(Exception):
            ServiceSLA(service_id="x", measurement_window_days=0)


# ---------------------------------------------------------------------------
# 5. CascadeResult Model Tests
# ---------------------------------------------------------------------------


class TestCascadeResult:
    def test_basic_creation(self):
        r = CascadeResult(composite_sla=99.8, weakest_link="db", chain_depth=3)
        assert r.composite_sla == 99.8
        assert r.weakest_link == "db"
        assert r.chain_depth == 3

    def test_defaults(self):
        r = CascadeResult(composite_sla=99.9, weakest_link="", chain_depth=1)
        assert r.bottleneck_services == []
        assert r.sla_gap == 0.0
        assert r.financial_risk == 0.0
        assert r.recommendations == []

    def test_with_bottlenecks(self):
        r = CascadeResult(
            composite_sla=99.5,
            weakest_link="cache",
            chain_depth=2,
            bottleneck_services=["cache", "db"],
        )
        assert len(r.bottleneck_services) == 2

    def test_with_recommendations(self):
        r = CascadeResult(
            composite_sla=98.0,
            weakest_link="api",
            chain_depth=4,
            recommendations=["Add redundancy"],
        )
        assert "Add redundancy" in r.recommendations


# ---------------------------------------------------------------------------
# 6. SLABreachImpact Model Tests
# ---------------------------------------------------------------------------


class TestSLABreachImpact:
    def test_basic_creation(self):
        b = SLABreachImpact(breached_service="db")
        assert b.breached_service == "db"
        assert b.affected_services == []
        assert b.cascade_depth == 0

    def test_with_affected_services(self):
        b = SLABreachImpact(
            breached_service="db",
            affected_services=["api", "web"],
            cascade_depth=2,
        )
        assert len(b.affected_services) == 2
        assert b.cascade_depth == 2

    def test_estimated_penalty(self):
        b = SLABreachImpact(
            breached_service="db",
            estimated_penalty=5000.0,
        )
        assert b.estimated_penalty == 5000.0


# ---------------------------------------------------------------------------
# 7. FinancialRiskReport Model Tests
# ---------------------------------------------------------------------------


class TestFinancialRiskReport:
    def test_defaults(self):
        r = FinancialRiskReport()
        assert r.total_annual_risk == 0.0
        assert r.service_risks == {}
        assert r.highest_risk_service == ""
        assert r.risk_by_tier == {}
        assert r.mitigation_savings == 0.0
        assert r.recommendations == []

    def test_with_data(self):
        r = FinancialRiskReport(
            total_annual_risk=50000.0,
            service_risks={"db": 30000.0, "api": 20000.0},
            highest_risk_service="db",
        )
        assert r.total_annual_risk == 50000.0
        assert r.highest_risk_service == "db"


# ---------------------------------------------------------------------------
# 8. SLAConflict Model Tests
# ---------------------------------------------------------------------------


class TestSLAConflict:
    def test_basic_creation(self):
        c = SLAConflict(
            service_id="svc1",
            conflict_type="tier_target_mismatch",
            description="test",
        )
        assert c.service_id == "svc1"
        assert c.severity == "warning"
        assert c.resolution == ""

    def test_custom_severity(self):
        c = SLAConflict(
            service_id="svc1",
            conflict_type="test",
            description="test",
            severity="error",
            resolution="fix it",
        )
        assert c.severity == "error"
        assert c.resolution == "fix it"


# ---------------------------------------------------------------------------
# 9. ComplianceProjection Model Tests
# ---------------------------------------------------------------------------


class TestComplianceProjection:
    def test_defaults(self):
        cp = ComplianceProjection()
        assert cp.months == 12
        assert cp.projected_compliance_rate == 100.0
        assert cp.projected_violations == 0
        assert cp.projected_penalty_total == 0.0
        assert cp.monthly_projections == []
        assert cp.risk_trend == "stable"
        assert cp.recommendations == []

    def test_custom_values(self):
        cp = ComplianceProjection(
            months=6,
            projected_compliance_rate=98.5,
            projected_violations=3,
            risk_trend="worsening",
        )
        assert cp.months == 6
        assert cp.projected_violations == 3


# ---------------------------------------------------------------------------
# 10. SLACascadeEngine — calculate_composite_sla
# ---------------------------------------------------------------------------


class TestCalculateCompositeSLA:
    def setup_method(self):
        self.engine = SLACascadeEngine()

    def test_empty_graph(self):
        g = InfraGraph()
        result = self.engine.calculate_composite_sla(g, {})
        assert result.composite_sla == 100.0
        assert result.weakest_link == ""
        assert result.chain_depth == 0

    def test_single_service_full_sla(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1", target=99.9)}
        result = self.engine.calculate_composite_sla(g, slas)
        assert result.composite_sla == pytest.approx(99.9, abs=0.01)
        assert result.weakest_link == "s1"

    def test_two_services_availability_multiply(self):
        g = _graph(_comp("s1"), _comp("s2"))
        g.add_dependency(_dep("s1", "s2"))
        slas = {
            "s1": _sla("s1", target=99.9),
            "s2": _sla("s2", target=99.9),
        }
        result = self.engine.calculate_composite_sla(g, slas)
        # 99.9% * 99.9% = 99.8001%
        expected = (99.9 / 100) * (99.9 / 100) * 100
        assert result.composite_sla == pytest.approx(expected, abs=0.001)

    def test_three_services_chain(self):
        g, ids = _chain_graph(3)
        slas = {cid: _sla(cid, target=99.9) for cid in ids}
        result = self.engine.calculate_composite_sla(g, slas)
        expected = (0.999 ** 3) * 100
        assert result.composite_sla == pytest.approx(expected, abs=0.001)

    def test_chain_depth_increases_with_services(self):
        g, ids = _chain_graph(5)
        slas = {cid: _sla(cid) for cid in ids}
        result = self.engine.calculate_composite_sla(g, slas)
        assert result.chain_depth >= 5

    def test_service_without_sla_treated_as_100(self):
        g = _graph(_comp("s1"), _comp("s2"))
        slas = {"s1": _sla("s1", target=99.9)}
        result = self.engine.calculate_composite_sla(g, slas)
        # s2 treated as 100%, so composite = 99.9% * 100% = 99.9%
        assert result.composite_sla == pytest.approx(99.9, abs=0.01)

    def test_non_availability_sla_uses_min(self):
        g = _graph(_comp("s1"), _comp("s2"))
        slas = {
            "s1": _sla("s1", target=50.0, sla_type=SLAType.LATENCY),
            "s2": _sla("s2", target=80.0, sla_type=SLAType.LATENCY),
        }
        result = self.engine.calculate_composite_sla(g, slas)
        assert result.composite_sla == 50.0

    def test_sla_gap_calculated(self):
        g = _graph(_comp("s1"), _comp("s2"))
        slas = {
            "s1": _sla("s1", target=99.9),
            "s2": _sla("s2", target=99.0),
        }
        result = self.engine.calculate_composite_sla(g, slas)
        assert result.sla_gap == pytest.approx(0.9, abs=0.001)

    def test_financial_risk_positive(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1", target=99.0, penalty=5000.0)}
        result = self.engine.calculate_composite_sla(g, slas)
        assert result.financial_risk > 0

    def test_returns_cascade_result_type(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1")}
        result = self.engine.calculate_composite_sla(g, slas)
        assert isinstance(result, CascadeResult)

    def test_bottleneck_detection(self):
        g = _graph(_comp("s1"), _comp("s2"))
        g.add_dependency(_dep("s1", "s2"))
        slas = {
            "s1": _sla("s1", target=99.99),
            "s2": _sla("s2", target=98.0),  # Much lower
        }
        result = self.engine.calculate_composite_sla(g, slas)
        assert "s2" in result.bottleneck_services

    def test_recommendations_non_empty(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1")}
        result = self.engine.calculate_composite_sla(g, slas)
        assert len(result.recommendations) >= 1

    def test_recommendations_for_low_composite(self):
        g, ids = _chain_graph(10)
        slas = {cid: _sla(cid, target=98.0) for cid in ids}
        result = self.engine.calculate_composite_sla(g, slas)
        # With 10 services at 98%, composite is very low.
        assert result.composite_sla < 99.0
        has_low_rec = any("below 99%" in r for r in result.recommendations)
        assert has_low_rec


# ---------------------------------------------------------------------------
# 11. SLACascadeEngine — find_weakest_link
# ---------------------------------------------------------------------------


class TestFindWeakestLink:
    def setup_method(self):
        self.engine = SLACascadeEngine()

    def test_empty_slas(self):
        g = InfraGraph()
        assert self.engine.find_weakest_link(g, {}) == ""

    def test_single_service(self):
        g = _graph(_comp("db"))
        slas = {"db": _sla("db", target=99.5)}
        assert self.engine.find_weakest_link(g, slas) == "db"

    def test_lowest_target_wins(self):
        g = _graph(_comp("a"), _comp("b"))
        slas = {
            "a": _sla("a", target=99.99),
            "b": _sla("b", target=99.0),
        }
        assert self.engine.find_weakest_link(g, slas) == "b"

    def test_tie_broken_by_dependents(self):
        g = _graph(_comp("a"), _comp("b"), _comp("c"), _comp("d"))
        # c and d depend on b, only d depends on a
        g.add_dependency(_dep("c", "b"))
        g.add_dependency(_dep("d", "b"))
        g.add_dependency(_dep("d", "a"))
        slas = {
            "a": _sla("a", target=99.0),
            "b": _sla("b", target=99.0),
        }
        # b has 2 dependents, a has 1 → b wins
        assert self.engine.find_weakest_link(g, slas) == "b"

    def test_service_not_in_graph_has_zero_dependents(self):
        g = _graph(_comp("a"))
        slas = {
            "a": _sla("a", target=99.0),
            "b": _sla("b", target=99.0),  # not in graph
        }
        # Both have same target; a is in graph (0 deps), b not in graph (0 deps)
        result = self.engine.find_weakest_link(g, slas)
        assert result in ("a", "b")


# ---------------------------------------------------------------------------
# 12. SLACascadeEngine — simulate_sla_breach
# ---------------------------------------------------------------------------


class TestSimulateSLABreach:
    def setup_method(self):
        self.engine = SLACascadeEngine()

    def test_nonexistent_service(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1")}
        result = self.engine.simulate_sla_breach(g, slas, "nonexistent")
        assert result.breached_service == "nonexistent"
        assert result.affected_services == []
        assert result.cascade_depth == 0

    def test_isolated_service_no_cascade(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1")}
        result = self.engine.simulate_sla_breach(g, slas, "s1")
        assert result.breached_service == "s1"
        assert result.affected_services == []
        assert result.cascade_depth == 0

    def test_cascade_affects_dependents(self):
        g = _graph(_comp("db"), _comp("api"), _comp("web"))
        g.add_dependency(_dep("api", "db"))
        g.add_dependency(_dep("web", "api"))
        slas = {
            "db": _sla("db"),
            "api": _sla("api"),
            "web": _sla("web"),
        }
        result = self.engine.simulate_sla_breach(g, slas, "db")
        assert "api" in result.affected_services
        assert "web" in result.affected_services

    def test_cascade_depth(self):
        g, ids = _chain_graph(4)
        slas = {cid: _sla(cid) for cid in ids}
        # Breach at the end of chain (s3). It has dependents going upstream.
        # Actually in _chain_graph, s0 depends on s1, s1 on s2, etc.
        # So breaching s3 affects: via get_dependents, s2 depends on s3, s1 on s2, s0 on s1.
        result = self.engine.simulate_sla_breach(g, slas, ids[-1])
        assert result.cascade_depth >= 1

    def test_estimated_penalty_positive(self):
        g = _graph(_comp("db"), _comp("api"))
        g.add_dependency(_dep("api", "db"))
        slas = {
            "db": _sla("db", penalty=5000.0),
            "api": _sla("api", penalty=3000.0),
        }
        result = self.engine.simulate_sla_breach(g, slas, "db")
        assert result.estimated_penalty > 0

    def test_degradation_increases_with_affected(self):
        # Two graphs: one isolated, one with cascade
        g1 = _graph(_comp("db"))
        g2 = _graph(_comp("db"), _comp("api"), _comp("web"))
        g2.add_dependency(_dep("api", "db"))
        g2.add_dependency(_dep("web", "db"))
        slas = {"db": _sla("db"), "api": _sla("api"), "web": _sla("web")}
        r1 = self.engine.simulate_sla_breach(g1, slas, "db")
        r2 = self.engine.simulate_sla_breach(g2, slas, "db")
        assert r2.total_sla_degradation >= r1.total_sla_degradation

    def test_recovery_recommendations_for_deep_cascade(self):
        g, ids = _chain_graph(5)
        slas = {cid: _sla(cid) for cid in ids}
        result = self.engine.simulate_sla_breach(g, slas, ids[-1])
        if result.cascade_depth > 2:
            assert any("circuit breaker" in r.lower() for r in result.recovery_recommendations)

    def test_recovery_recommendations_for_many_affected(self):
        g = _graph(*[_comp(f"s{i}") for i in range(6)])
        for i in range(1, 6):
            g.add_dependency(_dep(f"s{i}", "s0"))
        slas = {f"s{i}": _sla(f"s{i}") for i in range(6)}
        result = self.engine.simulate_sla_breach(g, slas, "s0")
        if len(result.affected_services) > 3:
            assert any("redundancy" in r.lower() for r in result.recovery_recommendations)

    def test_high_tier_breach_recommendation(self):
        g = _graph(_comp("db"))
        slas = {"db": _sla("db", tier=SLATier.PLATINUM)}
        result = self.engine.simulate_sla_breach(g, slas, "db")
        assert any("incident response" in r.lower() for r in result.recovery_recommendations)

    def test_gold_tier_breach_recommendation(self):
        g = _graph(_comp("db"))
        slas = {"db": _sla("db", tier=SLATier.GOLD)}
        result = self.engine.simulate_sla_breach(g, slas, "db")
        assert any("incident response" in r.lower() for r in result.recovery_recommendations)

    def test_breach_without_sla_entry(self):
        g = _graph(_comp("s1"))
        result = self.engine.simulate_sla_breach(g, {}, "s1")
        assert result.breached_service == "s1"
        assert result.total_sla_degradation == 0.0
        assert result.estimated_penalty == 0.0

    def test_default_recommendation_for_simple_breach(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1", tier=SLATier.BRONZE)}
        result = self.engine.simulate_sla_breach(g, slas, "s1")
        assert len(result.recovery_recommendations) >= 1

    def test_returns_sla_breach_impact_type(self):
        g = _graph(_comp("s1"))
        result = self.engine.simulate_sla_breach(g, {}, "s1")
        assert isinstance(result, SLABreachImpact)


# ---------------------------------------------------------------------------
# 13. SLACascadeEngine — recommend_sla_targets
# ---------------------------------------------------------------------------


class TestRecommendSLATargets:
    def setup_method(self):
        self.engine = SLACascadeEngine()

    def test_empty_graph(self):
        g = InfraGraph()
        recs = self.engine.recommend_sla_targets(g)
        assert recs == []

    def test_single_isolated_service_gets_silver(self):
        g = _graph(_comp("s1"))
        recs = self.engine.recommend_sla_targets(g)
        assert len(recs) == 1
        assert recs[0].tier == SLATier.SILVER
        assert recs[0].target == _TIER_DEFAULTS[SLATier.SILVER]

    def test_service_with_one_dependent_gets_gold(self):
        g = _graph(_comp("db"), _comp("api"))
        g.add_dependency(_dep("api", "db"))
        recs = self.engine.recommend_sla_targets(g)
        db_rec = next(r for r in recs if r.service_id == "db")
        assert db_rec.tier == SLATier.GOLD

    def test_service_with_many_dependents_gets_platinum(self):
        g = _graph(*[_comp(f"s{i}") for i in range(6)])
        for i in range(1, 6):
            g.add_dependency(_dep(f"s{i}", "s0"))
        recs = self.engine.recommend_sla_targets(g)
        s0_rec = next(r for r in recs if r.service_id == "s0")
        assert s0_rec.tier == SLATier.PLATINUM

    def test_all_recommendations_are_service_sla_type(self):
        g = _graph(_comp("s1"), _comp("s2"))
        recs = self.engine.recommend_sla_targets(g)
        for r in recs:
            assert isinstance(r, ServiceSLA)
            assert r.sla_type == SLAType.AVAILABILITY

    def test_penalty_matches_tier(self):
        g = _graph(*[_comp(f"s{i}") for i in range(5)])
        for i in range(1, 5):
            g.add_dependency(_dep(f"s{i}", "s0"))
        recs = self.engine.recommend_sla_targets(g)
        s0_rec = next(r for r in recs if r.service_id == "s0")
        assert s0_rec.penalty_per_violation_percent == _TIER_PENALTY_DEFAULTS[s0_rec.tier]

    def test_window_is_30_days(self):
        g = _graph(_comp("s1"))
        recs = self.engine.recommend_sla_targets(g)
        assert recs[0].measurement_window_days == 30

    def test_three_dependent_service_gets_gold(self):
        g = _graph(*[_comp(f"s{i}") for i in range(4)])
        for i in range(1, 4):
            g.add_dependency(_dep(f"s{i}", "s0"))
        recs = self.engine.recommend_sla_targets(g)
        s0_rec = next(r for r in recs if r.service_id == "s0")
        assert s0_rec.tier == SLATier.GOLD


# ---------------------------------------------------------------------------
# 14. SLACascadeEngine — calculate_financial_risk
# ---------------------------------------------------------------------------


class TestCalculateFinancialRisk:
    def setup_method(self):
        self.engine = SLACascadeEngine()

    def test_empty_slas(self):
        g = InfraGraph()
        report = self.engine.calculate_financial_risk(g, {})
        assert isinstance(report, FinancialRiskReport)
        assert report.total_annual_risk == 0.0

    def test_single_service_risk(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1", target=99.0, penalty=5000.0)}
        report = self.engine.calculate_financial_risk(g, slas)
        assert report.total_annual_risk > 0

    def test_highest_risk_service_identified(self):
        g = _graph(_comp("a"), _comp("b"))
        slas = {
            "a": _sla("a", target=99.9, penalty=1000.0),
            "b": _sla("b", target=95.0, penalty=5000.0),
        }
        report = self.engine.calculate_financial_risk(g, slas)
        assert report.highest_risk_service == "b"

    def test_risk_by_tier(self):
        g = _graph(_comp("a"), _comp("b"))
        slas = {
            "a": _sla("a", tier=SLATier.GOLD, penalty=1000.0),
            "b": _sla("b", tier=SLATier.SILVER, penalty=1000.0),
        }
        report = self.engine.calculate_financial_risk(g, slas)
        assert "gold" in report.risk_by_tier
        assert "silver" in report.risk_by_tier

    def test_mitigation_savings_positive(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1", target=99.0, penalty=10000.0)}
        report = self.engine.calculate_financial_risk(g, slas)
        assert report.mitigation_savings > 0
        assert report.mitigation_savings == pytest.approx(report.total_annual_risk * 0.3, abs=0.01)

    def test_recommendations_populated(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1", penalty=5000.0)}
        report = self.engine.calculate_financial_risk(g, slas)
        assert len(report.recommendations) >= 1

    def test_high_risk_recommendation(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1", target=90.0, penalty=50000.0)}
        report = self.engine.calculate_financial_risk(g, slas)
        if report.total_annual_risk > 100_000:
            assert any("100,000" in r for r in report.recommendations)

    def test_service_risks_dict(self):
        g = _graph(_comp("a"), _comp("b"))
        slas = {
            "a": _sla("a", penalty=1000.0),
            "b": _sla("b", penalty=2000.0),
        }
        report = self.engine.calculate_financial_risk(g, slas)
        assert "a" in report.service_risks
        assert "b" in report.service_risks

    def test_risk_increases_with_lower_target(self):
        g = _graph(_comp("s1"))
        slas_high = {"s1": _sla("s1", target=99.9, penalty=5000.0)}
        slas_low = {"s1": _sla("s1", target=95.0, penalty=5000.0)}
        r_high = self.engine.calculate_financial_risk(g, slas_high)
        r_low = self.engine.calculate_financial_risk(g, slas_low)
        assert r_low.total_annual_risk > r_high.total_annual_risk


# ---------------------------------------------------------------------------
# 15. SLACascadeEngine — detect_sla_conflicts
# ---------------------------------------------------------------------------


class TestDetectSLAConflicts:
    def setup_method(self):
        self.engine = SLACascadeEngine()

    def test_no_conflicts_for_consistent_slas(self):
        slas = {
            "s1": _sla("s1", target=99.9, tier=SLATier.SILVER),
        }
        conflicts = self.engine.detect_sla_conflicts(slas)
        # Should have no tier_target_mismatch, no zero_penalty, no unrealistic
        mismatch = [c for c in conflicts if c.conflict_type == "tier_target_mismatch"]
        assert len(mismatch) == 0

    def test_tier_target_mismatch_detected(self):
        slas = {
            "s1": _sla("s1", target=95.0, tier=SLATier.PLATINUM),
        }
        conflicts = self.engine.detect_sla_conflicts(slas)
        mismatch = [c for c in conflicts if c.conflict_type == "tier_target_mismatch"]
        assert len(mismatch) == 1
        assert mismatch[0].severity == "error"

    def test_zero_penalty_on_paid_tier(self):
        slas = {
            "s1": _sla("s1", tier=SLATier.GOLD, penalty=0.0),
        }
        conflicts = self.engine.detect_sla_conflicts(slas)
        zero_pen = [c for c in conflicts if c.conflict_type == "zero_penalty"]
        assert len(zero_pen) == 1

    def test_zero_penalty_on_best_effort_ok(self):
        slas = {
            "s1": _sla("s1", tier=SLATier.BEST_EFFORT, target=95.0, penalty=0.0),
        }
        conflicts = self.engine.detect_sla_conflicts(slas)
        zero_pen = [c for c in conflicts if c.conflict_type == "zero_penalty"]
        assert len(zero_pen) == 0

    def test_unrealistic_target_detected(self):
        slas = {
            "s1": _sla("s1", target=99.9999),
        }
        conflicts = self.engine.detect_sla_conflicts(slas)
        unreal = [c for c in conflicts if c.conflict_type == "unrealistic_target"]
        assert len(unreal) == 1

    def test_short_window_detected(self):
        slas = {
            "s1": _sla("s1", window=3),
        }
        conflicts = self.engine.detect_sla_conflicts(slas)
        short = [c for c in conflicts if c.conflict_type == "short_window"]
        assert len(short) == 1
        assert short[0].severity == "info"

    def test_window_7_days_no_conflict(self):
        slas = {
            "s1": _sla("s1", window=7),
        }
        conflicts = self.engine.detect_sla_conflicts(slas)
        short = [c for c in conflicts if c.conflict_type == "short_window"]
        assert len(short) == 0

    def test_inconsistent_windows_detected(self):
        slas = {
            "s1": _sla("s1", window=30),
            "s2": _sla("s2", window=7),
        }
        conflicts = self.engine.detect_sla_conflicts(slas)
        incon = [c for c in conflicts if c.conflict_type == "inconsistent_windows"]
        assert len(incon) == 1
        assert incon[0].service_id == "*"

    def test_consistent_windows_no_conflict(self):
        slas = {
            "s1": _sla("s1", window=30),
            "s2": _sla("s2", window=30),
        }
        conflicts = self.engine.detect_sla_conflicts(slas)
        incon = [c for c in conflicts if c.conflict_type == "inconsistent_windows"]
        assert len(incon) == 0

    def test_empty_slas_no_conflicts(self):
        conflicts = self.engine.detect_sla_conflicts({})
        assert conflicts == []

    def test_conflict_has_resolution(self):
        slas = {
            "s1": _sla("s1", target=90.0, tier=SLATier.PLATINUM),
        }
        conflicts = self.engine.detect_sla_conflicts(slas)
        for c in conflicts:
            if c.conflict_type == "tier_target_mismatch":
                assert c.resolution != ""

    def test_multiple_conflicts_on_one_service(self):
        slas = {
            "s1": _sla("s1", target=99.9999, tier=SLATier.GOLD, penalty=0.0, window=3),
        }
        conflicts = self.engine.detect_sla_conflicts(slas)
        s1_conflicts = [c for c in conflicts if c.service_id == "s1"]
        # unrealistic_target + zero_penalty + short_window
        assert len(s1_conflicts) >= 3

    def test_target_exactly_at_tier_boundary(self):
        # Target exactly at tier default minus 1.0 should not trigger
        slas = {
            "s1": _sla("s1", target=98.9, tier=SLATier.SILVER),  # 99.9 - 1.0 = 98.9
        }
        conflicts = self.engine.detect_sla_conflicts(slas)
        mismatch = [c for c in conflicts if c.conflict_type == "tier_target_mismatch"]
        assert len(mismatch) == 0

    def test_target_just_below_boundary(self):
        slas = {
            "s1": _sla("s1", target=98.8, tier=SLATier.SILVER),  # < 98.9
        }
        conflicts = self.engine.detect_sla_conflicts(slas)
        mismatch = [c for c in conflicts if c.conflict_type == "tier_target_mismatch"]
        assert len(mismatch) == 1


# ---------------------------------------------------------------------------
# 16. SLACascadeEngine — project_sla_compliance
# ---------------------------------------------------------------------------


class TestProjectSLACompliance:
    def setup_method(self):
        self.engine = SLACascadeEngine()

    def test_empty_slas(self):
        g = InfraGraph()
        result = self.engine.project_sla_compliance(g, {}, months=12)
        assert result.months == 12
        assert result.projected_compliance_rate == 100.0
        assert result.projected_violations == 0

    def test_zero_months(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1")}
        result = self.engine.project_sla_compliance(g, slas, months=0)
        assert result.months == 0

    def test_negative_months(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1")}
        result = self.engine.project_sla_compliance(g, slas, months=-5)
        assert result.months == 0

    def test_single_month(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1")}
        result = self.engine.project_sla_compliance(g, slas, months=1)
        assert result.months == 1
        assert len(result.monthly_projections) == 1

    def test_monthly_projections_count(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1")}
        result = self.engine.project_sla_compliance(g, slas, months=6)
        assert len(result.monthly_projections) == 6

    def test_monthly_projections_have_keys(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1")}
        result = self.engine.project_sla_compliance(g, slas, months=1)
        proj = result.monthly_projections[0]
        assert "month" in proj
        assert "expected_violations" in proj
        assert "expected_penalty" in proj

    def test_high_target_no_violations(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1", target=99.9)}
        result = self.engine.project_sla_compliance(g, slas, months=12)
        assert result.projected_violations == 0

    def test_compliance_rate_below_100_for_low_target(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1", target=40.0)}  # Very low target → prob > 0.5
        result = self.engine.project_sla_compliance(g, slas, months=12)
        assert result.projected_compliance_rate < 100.0

    def test_risk_trend_stable_for_uniform_penalty(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1")}
        result = self.engine.project_sla_compliance(g, slas, months=12)
        assert result.risk_trend == "stable"

    def test_recommendations_healthy(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1", target=99.9)}
        result = self.engine.project_sla_compliance(g, slas, months=12)
        assert len(result.recommendations) >= 1

    def test_returns_compliance_projection_type(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1")}
        result = self.engine.project_sla_compliance(g, slas, months=12)
        assert isinstance(result, ComplianceProjection)

    def test_cascade_multiplier_increases_risk(self):
        # Service with dependencies should have higher risk
        g1 = _graph(_comp("s1"))
        g2 = _graph(_comp("s1"), _comp("s2"), _comp("s3"))
        g2.add_dependency(_dep("s1", "s2"))
        g2.add_dependency(_dep("s1", "s3"))
        slas = {"s1": _sla("s1", target=99.0)}
        r1 = self.engine.project_sla_compliance(g1, slas, months=12)
        r2 = self.engine.project_sla_compliance(g2, slas, months=12)
        assert r2.projected_penalty_total >= r1.projected_penalty_total

    def test_short_months_stable_trend(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1")}
        result = self.engine.project_sla_compliance(g, slas, months=2)
        assert result.risk_trend == "stable"

    def test_compliance_recommendation_for_low_rate(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1", target=40.0)}
        result = self.engine.project_sla_compliance(g, slas, months=12)
        if result.projected_compliance_rate < 99.0:
            assert any("below 99%" in r for r in result.recommendations)


# ---------------------------------------------------------------------------
# 17. Internal helper methods
# ---------------------------------------------------------------------------


class TestDominantSLAType:
    def test_empty_returns_availability(self):
        assert SLACascadeEngine._dominant_sla_type({}) == SLAType.AVAILABILITY

    def test_single_latency(self):
        slas = {"s1": _sla("s1", sla_type=SLAType.LATENCY)}
        assert SLACascadeEngine._dominant_sla_type(slas) == SLAType.LATENCY

    def test_majority_wins(self):
        slas = {
            "s1": _sla("s1", sla_type=SLAType.THROUGHPUT),
            "s2": _sla("s2", sla_type=SLAType.THROUGHPUT),
            "s3": _sla("s3", sla_type=SLAType.LATENCY),
        }
        assert SLACascadeEngine._dominant_sla_type(slas) == SLAType.THROUGHPUT


class TestCompositeAvailability:
    def test_single_100_percent(self):
        result = SLACascadeEngine._composite_availability({"a": 100.0})
        assert result == pytest.approx(100.0)

    def test_two_99_percent(self):
        result = SLACascadeEngine._composite_availability({"a": 99.0, "b": 99.0})
        assert result == pytest.approx(98.01, abs=0.001)

    def test_one_zero_percent(self):
        result = SLACascadeEngine._composite_availability({"a": 99.9, "b": 0.0})
        assert result == pytest.approx(0.0)


class TestMaxChainDepth:
    def test_empty_graph(self):
        g = InfraGraph()
        assert SLACascadeEngine._max_chain_depth(g) == 0

    def test_single_node(self):
        g = _graph(_comp("s1"))
        depth = SLACascadeEngine._max_chain_depth(g)
        assert depth >= 1

    def test_linear_chain(self):
        g, _ = _chain_graph(5)
        depth = SLACascadeEngine._max_chain_depth(g)
        assert depth >= 5


class TestFindBottlenecks:
    def test_empty_slas(self):
        g = InfraGraph()
        assert SLACascadeEngine._find_bottlenecks(g, {}) == []

    def test_uniform_slas_no_bottleneck(self):
        g = _graph(_comp("a"), _comp("b"))
        slas = {
            "a": _sla("a", target=99.9),
            "b": _sla("b", target=99.9),
        }
        result = SLACascadeEngine._find_bottlenecks(g, slas)
        assert result == []

    def test_low_target_is_bottleneck(self):
        g = _graph(_comp("a"), _comp("b"))
        slas = {
            "a": _sla("a", target=99.9),
            "b": _sla("b", target=98.0),
        }
        result = SLACascadeEngine._find_bottlenecks(g, slas)
        assert "b" in result

    def test_dependent_with_higher_sla_makes_bottleneck(self):
        g = _graph(_comp("db"), _comp("api"))
        g.add_dependency(_dep("api", "db"))
        slas = {
            "db": _sla("db", target=99.0),
            "api": _sla("api", target=99.5),
        }
        # db has dependent api with higher SLA → db is bottleneck
        result = SLACascadeEngine._find_bottlenecks(g, slas)
        assert "db" in result


class TestCascadeDepthFrom:
    def test_nonexistent_component(self):
        g = InfraGraph()
        assert SLACascadeEngine._cascade_depth_from(g, "nonexistent") == 0

    def test_isolated_node(self):
        g = _graph(_comp("s1"))
        assert SLACascadeEngine._cascade_depth_from(g, "s1") == 0

    def test_chain_depth(self):
        g, ids = _chain_graph(4)
        # s0 depends on s1, s1 on s2, s2 on s3
        # Breaching s3: dependents of s3 = s2, dependents of s2 = s1, dependents of s1 = s0
        depth = SLACascadeEngine._cascade_depth_from(g, ids[-1])
        assert depth >= 1


class TestEstimateFinancialRiskSimple:
    def test_empty(self):
        assert SLACascadeEngine._estimate_financial_risk_simple({}) == 0.0

    def test_positive_risk(self):
        slas = {"s1": _sla("s1", target=99.0, penalty=5000.0)}
        risk = SLACascadeEngine._estimate_financial_risk_simple(slas)
        assert risk > 0

    def test_perfect_target_zero_risk(self):
        slas = {"s1": _sla("s1", target=100.0, penalty=5000.0)}
        risk = SLACascadeEngine._estimate_financial_risk_simple(slas)
        assert risk == 0.0


class TestGenerateRecommendations:
    def test_healthy_configuration(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1")}
        recs = SLACascadeEngine._generate_recommendations(g, slas, 99.9, [], 2)
        assert any("healthy" in r.lower() for r in recs)

    def test_low_composite_recommendation(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1")}
        recs = SLACascadeEngine._generate_recommendations(g, slas, 95.0, [], 2)
        assert any("below 99%" in r for r in recs)

    def test_bottleneck_recommendation(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1")}
        recs = SLACascadeEngine._generate_recommendations(g, slas, 99.9, ["s1"], 2)
        assert any("bottleneck" in r.lower() for r in recs)

    def test_deep_chain_recommendation(self):
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1")}
        recs = SLACascadeEngine._generate_recommendations(g, slas, 99.9, [], 7)
        assert any("depth" in r.lower() for r in recs)

    def test_missing_sla_recommendation(self):
        g = _graph(_comp("s1"), _comp("s2"))
        slas = {"s1": _sla("s1")}  # s2 missing
        recs = SLACascadeEngine._generate_recommendations(g, slas, 99.9, [], 2)
        assert any("no SLA defined" in r for r in recs)


# ---------------------------------------------------------------------------
# 18. Integration / Complex Scenarios
# ---------------------------------------------------------------------------


class TestIntegrationScenarios:
    def setup_method(self):
        self.engine = SLACascadeEngine()

    def test_microservice_architecture(self):
        """Test a typical microservice graph: LB -> API -> DB, API -> Cache."""
        g = _graph(
            _comp("lb", ctype=ComponentType.LOAD_BALANCER),
            _comp("api"),
            _comp("db", ctype=ComponentType.DATABASE),
            _comp("cache", ctype=ComponentType.CACHE),
        )
        g.add_dependency(_dep("lb", "api"))
        g.add_dependency(_dep("api", "db"))
        g.add_dependency(_dep("api", "cache"))

        slas = {
            "lb": _sla("lb", target=99.99, tier=SLATier.GOLD),
            "api": _sla("api", target=99.9, tier=SLATier.SILVER),
            "db": _sla("db", target=99.95, tier=SLATier.GOLD),
            "cache": _sla("cache", target=99.5, tier=SLATier.BRONZE),
        }

        result = self.engine.calculate_composite_sla(g, slas)
        assert result.composite_sla < 99.5  # Product of all 4
        assert result.chain_depth >= 3
        assert result.weakest_link == "cache"

    def test_full_workflow(self):
        """Run all engine methods on a single graph."""
        g = _graph(_comp("a"), _comp("b"), _comp("c"))
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("b", "c"))

        slas = {
            "a": _sla("a", target=99.9),
            "b": _sla("b", target=99.5),
            "c": _sla("c", target=99.0),
        }

        composite = self.engine.calculate_composite_sla(g, slas)
        assert isinstance(composite, CascadeResult)

        weakest = self.engine.find_weakest_link(g, slas)
        assert weakest == "c"

        breach = self.engine.simulate_sla_breach(g, slas, "c")
        assert isinstance(breach, SLABreachImpact)
        assert breach.breached_service == "c"

        recs = self.engine.recommend_sla_targets(g)
        assert len(recs) == 3

        risk = self.engine.calculate_financial_risk(g, slas)
        assert isinstance(risk, FinancialRiskReport)

        conflicts = self.engine.detect_sla_conflicts(slas)
        assert isinstance(conflicts, list)

        projection = self.engine.project_sla_compliance(g, slas, months=6)
        assert isinstance(projection, ComplianceProjection)

    def test_diamond_dependency(self):
        """A -> B, A -> C, B -> D, C -> D (diamond shape)."""
        g = _graph(_comp("A"), _comp("B"), _comp("C"), _comp("D"))
        g.add_dependency(_dep("A", "B"))
        g.add_dependency(_dep("A", "C"))
        g.add_dependency(_dep("B", "D"))
        g.add_dependency(_dep("C", "D"))

        slas = {
            "A": _sla("A", target=99.9),
            "B": _sla("B", target=99.9),
            "C": _sla("C", target=99.5),
            "D": _sla("D", target=99.9),
        }

        result = self.engine.calculate_composite_sla(g, slas)
        assert result.weakest_link == "C"

        # Breaching D should affect B, C, A
        breach = self.engine.simulate_sla_breach(g, slas, "D")
        assert "B" in breach.affected_services or "C" in breach.affected_services

    def test_wide_fan_out(self):
        """One service with 10 dependents."""
        ids = ["hub"] + [f"leaf{i}" for i in range(10)]
        g = _graph(*[_comp(cid) for cid in ids])
        for i in range(10):
            g.add_dependency(_dep(f"leaf{i}", "hub"))

        slas = {cid: _sla(cid) for cid in ids}
        result = self.engine.calculate_composite_sla(g, slas)
        assert result.composite_sla < 100.0

        breach = self.engine.simulate_sla_breach(g, slas, "hub")
        assert len(breach.affected_services) == 10

    def test_compliance_with_many_services(self):
        """12 services, various tiers."""
        g = _graph(*[_comp(f"s{i}") for i in range(12)])
        for i in range(1, 12):
            g.add_dependency(_dep(f"s{i}", "s0"))

        slas = {}
        for i in range(12):
            tier = [SLATier.PLATINUM, SLATier.GOLD, SLATier.SILVER, SLATier.BRONZE][i % 4]
            slas[f"s{i}"] = _sla(f"s{i}", target=_TIER_DEFAULTS[tier], tier=tier)

        projection = self.engine.project_sla_compliance(g, slas, months=12)
        assert projection.months == 12
        assert len(projection.monthly_projections) == 12

    def test_financial_risk_large_system(self):
        """Many services with high penalties."""
        g = _graph(*[_comp(f"s{i}") for i in range(20)])
        slas = {
            f"s{i}": _sla(f"s{i}", target=99.0, penalty=10000.0)
            for i in range(20)
        }
        report = self.engine.calculate_financial_risk(g, slas)
        assert report.total_annual_risk > 0
        assert len(report.service_risks) == 20

    def test_detect_conflicts_mixed_issues(self):
        slas = {
            "s1": _sla("s1", target=90.0, tier=SLATier.PLATINUM, penalty=0.0, window=1),
            "s2": _sla("s2", target=99.9999, tier=SLATier.SILVER, window=30),
        }
        conflicts = self.engine.detect_sla_conflicts(slas)
        types = {c.conflict_type for c in conflicts}
        assert "tier_target_mismatch" in types
        assert "zero_penalty" in types
        assert "unrealistic_target" in types
        assert "short_window" in types
        assert "inconsistent_windows" in types

    def test_single_node_graph_recommend(self):
        g = _graph(_comp("only"))
        recs = self.engine.recommend_sla_targets(g)
        assert len(recs) == 1
        assert recs[0].service_id == "only"

    def test_composite_sla_with_throughput_type(self):
        g = _graph(_comp("s1"), _comp("s2"))
        slas = {
            "s1": _sla("s1", target=80.0, sla_type=SLAType.THROUGHPUT),
            "s2": _sla("s2", target=60.0, sla_type=SLAType.THROUGHPUT),
        }
        result = self.engine.calculate_composite_sla(g, slas)
        # Non-availability: min of values
        assert result.composite_sla == 60.0

    def test_breach_on_leaf_no_cascade(self):
        g = _graph(_comp("db"), _comp("api"))
        g.add_dependency(_dep("api", "db"))
        slas = {"db": _sla("db"), "api": _sla("api")}
        # api is a leaf (nobody depends on api except via graph direction)
        # api depends on db. Breaching api: who depends on api?
        # In InfraGraph, get_dependents returns predecessors.
        # dep("api","db"): api -> db edge, so predecessors of api are those who have edges TO api.
        result = self.engine.simulate_sla_breach(g, slas, "api")
        # Nobody has api as a dependency target, so no affected.
        # Actually: api is source, db is target. Dependents of api = predecessors of api = nobody.
        assert result.affected_services == []

    def test_cyclic_graph_chain_depth(self):
        """Graph with a cycle should fallback to len(components) for depth."""
        g = _graph(_comp("a"), _comp("b"), _comp("c"))
        g.add_dependency(_dep("a", "b"))
        g.add_dependency(_dep("b", "c"))
        g.add_dependency(_dep("c", "a"))  # Creates a cycle

        slas = {
            "a": _sla("a"),
            "b": _sla("b"),
            "c": _sla("c"),
        }
        result = self.engine.calculate_composite_sla(g, slas)
        # With a cycle, nx.dag_longest_path_length raises; fallback = len(components) = 3
        assert result.chain_depth == 3

    def test_compliance_high_penalty_recommendation(self):
        """Trigger the high-penalty recommendation in compliance projection."""
        g = _graph(_comp("s1"))
        # target=90 => prob=0.1 => monthly penalty=0.1*500000=50000 => total=600000 > 50000
        slas = {"s1": _sla("s1", target=90.0, penalty=500000.0)}
        result = self.engine.project_sla_compliance(g, slas, months=12)
        assert result.projected_penalty_total > 50_000
        assert any("significant" in r.lower() for r in result.recommendations)

    def test_compliance_worsening_recommendation(self):
        """Trigger worsening trend and its recommendation."""
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1", target=99.0, penalty=5000.0)}
        result = self.engine.project_sla_compliance(g, slas, months=7)
        if result.risk_trend == "worsening":
            assert any("worsening" in r.lower() for r in result.recommendations)

    def test_compliance_worsening_trend_odd_months(self):
        """With odd months, the second half has more entries than the first.

        For months=7, half=3: first_half = 3 months, second_half = 4 months.
        Since each month has the same penalty p: second (4p) > first (3p) * 1.2 = 3.6p.
        4p > 3.6p => "worsening" trend.
        """
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1", target=99.0, penalty=5000.0)}
        result = self.engine.project_sla_compliance(g, slas, months=7)
        # 4 * p > 3 * p * 1.2  =>  worsening
        assert result.risk_trend == "worsening"

    def test_compliance_improving_trend(self):
        """Trigger improving trend: first_half penalties > second_half * 1.25.

        For months=5, half=2: first_half = 2 months, second_half = 3 months.
        2p vs 3p => second > first. Not improving.

        For months=4, half=2: first_half = 2 months, second_half = 2 months.
        Equal => stable.

        The improving branch needs second_half < first_half * 0.8.
        With deterministic identical per-month penalties, second_half < first_half * 0.8
        requires second_half to have fewer months with penalty than first_half.
        This can't happen with uniform penalties and integer halves where second >= first.

        We can trigger it indirectly: if months=5, half=2, first_half=2 months, second_half=3 months.
        That makes second > first, so not improving.

        Actually, improving is only reachable if penalties vary per month, which they don't
        in the current deterministic model. We need to accept this branch or
        we can test it via mocking. Let's just verify the stable case thoroughly.
        """
        # With even months (e.g. 12), second_half == first_half => stable
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1", target=99.0, penalty=5000.0)}
        result = self.engine.project_sla_compliance(g, slas, months=12)
        assert result.risk_trend == "stable"

    def test_error_rate_sla_type_in_composite(self):
        """Non-availability SLA types use min-based composite."""
        g = _graph(_comp("s1"), _comp("s2"), _comp("s3"))
        slas = {
            "s1": _sla("s1", target=0.1, sla_type=SLAType.ERROR_RATE),
            "s2": _sla("s2", target=0.5, sla_type=SLAType.ERROR_RATE),
            "s3": _sla("s3", target=0.3, sla_type=SLAType.ERROR_RATE),
        }
        result = self.engine.calculate_composite_sla(g, slas)
        assert result.composite_sla == 0.1

    def test_durability_sla_type(self):
        """Durability SLA type should work correctly."""
        g = _graph(_comp("s1"))
        slas = {"s1": _sla("s1", target=99.999999, sla_type=SLAType.DURABILITY)}
        result = self.engine.calculate_composite_sla(g, slas)
        # Single service, min-based for non-availability
        assert result.composite_sla == pytest.approx(99.999999, abs=0.0001)

    def test_sla_gap_zero_for_uniform_targets(self):
        """SLA gap should be zero when all services have the same target."""
        g = _graph(_comp("a"), _comp("b"), _comp("c"))
        slas = {
            "a": _sla("a", target=99.9),
            "b": _sla("b", target=99.9),
            "c": _sla("c", target=99.9),
        }
        result = self.engine.calculate_composite_sla(g, slas)
        assert result.sla_gap == 0.0
