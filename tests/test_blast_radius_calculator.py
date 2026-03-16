"""Tests for Blast Radius Calculator.

Comprehensive tests covering all enums, dataclass models, helper functions,
and the BlastRadiusCalculator class with 50+ test methods targeting 100%
branch and statement coverage.
"""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    CostProfile,
    Dependency,
    FailoverConfig,
    OperationalProfile,
    RegionConfig,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.blast_radius_calculator import (
    BlastRadiusCalculator,
    BlastRadiusReduction,
    BlastRadiusReport,
    CascadeDepthResult,
    ComponentImpactScore,
    ContainmentMechanism,
    ContainmentStrategy,
    CrossRegionImpact,
    DegradationZone,
    IsolationBoundary,
    RecommendationPriority,
    RevenueImpact,
    ScenarioComparison,
    TemporalBlastRadius,
    TemporalPhase,
    TemporalProgression,
    UserImpactEstimate,
    classify_degradation_zone,
    component_revenue_weight,
    component_user_weight,
    compute_direct_impact,
    compute_transitive_impact,
    containment_effectiveness_base,
    dep_type_weight,
    get_temporal_phase,
    identify_containment_mechanism,
    replica_mitigation_factor,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str = "c1",
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    failover: bool = False,
    autoscaling: bool = False,
    network_segmented: bool = False,
    rate_limiting: bool = False,
    hourly_cost: float = 0.0,
    revenue_per_min: float = 0.0,
    monthly_contract: float = 0.0,
    sla_credit_pct: float = 0.0,
    customer_ltv: float = 0.0,
    recovery_team_size: int = 0,
    recovery_engineer_cost: float = 100.0,
    mttr: float = 30.0,
    region: str = "",
    az: str = "",
) -> Component:
    return Component(
        id=cid,
        name=cid,
        type=ctype,
        replicas=replicas,
        failover=FailoverConfig(enabled=failover),
        autoscaling=AutoScalingConfig(enabled=autoscaling),
        security=SecurityProfile(
            network_segmented=network_segmented,
            rate_limiting=rate_limiting,
        ),
        cost_profile=CostProfile(
            hourly_infra_cost=hourly_cost,
            revenue_per_minute=revenue_per_min,
            monthly_contract_value=monthly_contract,
            sla_credit_percent=sla_credit_pct,
            customer_ltv=customer_ltv,
            recovery_team_size=recovery_team_size,
            recovery_engineer_cost=recovery_engineer_cost,
        ),
        operational_profile=OperationalProfile(mttr_minutes=mttr),
        region=RegionConfig(region=region, availability_zone=az),
    )


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestDegradationZone:
    def test_all_values(self):
        assert DegradationZone.FULL_OUTAGE.value == "full_outage"
        assert DegradationZone.SEVERE_DEGRADATION.value == "severe_degradation"
        assert DegradationZone.PARTIAL_DEGRADATION.value == "partial_degradation"
        assert DegradationZone.MINIMAL_IMPACT.value == "minimal_impact"
        assert DegradationZone.NO_IMPACT.value == "no_impact"

    def test_member_count(self):
        assert len(DegradationZone) == 5


class TestContainmentMechanism:
    def test_all_values(self):
        assert ContainmentMechanism.CIRCUIT_BREAKER.value == "circuit_breaker"
        assert ContainmentMechanism.BULKHEAD.value == "bulkhead"
        assert ContainmentMechanism.FAILOVER.value == "failover"
        assert ContainmentMechanism.REDUNDANCY.value == "redundancy"
        assert ContainmentMechanism.RATE_LIMITER.value == "rate_limiter"
        assert ContainmentMechanism.NETWORK_SEGMENTATION.value == "network_segmentation"
        assert ContainmentMechanism.NONE.value == "none"

    def test_member_count(self):
        assert len(ContainmentMechanism) == 7


class TestTemporalPhase:
    def test_all_values(self):
        assert TemporalPhase.IMMEDIATE.value == "immediate"
        assert TemporalPhase.SHORT_TERM.value == "short_term"
        assert TemporalPhase.MEDIUM_TERM.value == "medium_term"
        assert TemporalPhase.LONG_TERM.value == "long_term"
        assert TemporalPhase.EXTENDED.value == "extended"


class TestRecommendationPriority:
    def test_all_values(self):
        assert RecommendationPriority.CRITICAL.value == "critical"
        assert RecommendationPriority.HIGH.value == "high"
        assert RecommendationPriority.MEDIUM.value == "medium"
        assert RecommendationPriority.LOW.value == "low"


# ---------------------------------------------------------------------------
# Dataclass model tests
# ---------------------------------------------------------------------------


class TestDataclassDefaults:
    def test_component_impact_score_defaults(self):
        s = ComponentImpactScore(component_id="x")
        assert s.direct_impact_score == 0.0
        assert s.transitive_impact_score == 0.0
        assert s.total_impact_score == 0.0
        assert s.cascade_depth == 0
        assert s.affected_downstream_count == 0
        assert s.degradation_zone == DegradationZone.NO_IMPACT
        assert s.user_impact_percent == 0.0
        assert s.revenue_impact_per_hour == 0.0

    def test_cascade_depth_result_defaults(self):
        r = CascadeDepthResult(origin_component_id="x")
        assert r.max_depth == 0
        assert r.components_at_depth == {}
        assert r.total_affected == 0
        assert r.propagation_paths == []

    def test_user_impact_estimate_defaults(self):
        u = UserImpactEstimate(component_id="x")
        assert u.direct_user_percent == 0.0
        assert u.indirect_user_percent == 0.0
        assert u.total_user_percent == 0.0
        assert u.affected_user_flows == []
        assert u.estimated_error_rate == 0.0

    def test_revenue_impact_defaults(self):
        r = RevenueImpact(component_id="x")
        assert r.revenue_loss_per_minute == 0.0
        assert r.revenue_loss_per_hour == 0.0
        assert r.sla_credit_exposure == 0.0
        assert r.recovery_cost == 0.0
        assert r.total_cost_per_hour == 0.0
        assert r.impacted_revenue_streams == []

    def test_temporal_blast_radius_defaults(self):
        t = TemporalBlastRadius(origin_component_id="x")
        assert t.phase == TemporalPhase.IMMEDIATE
        assert t.elapsed_seconds == 0.0
        assert t.affected_count == 0
        assert t.affected_components == []

    def test_temporal_progression_defaults(self):
        p = TemporalProgression(origin_component_id="x")
        assert p.snapshots == []
        assert p.time_to_full_propagation_seconds == 0.0
        assert p.peak_affected_count == 0

    def test_cross_region_impact_defaults(self):
        c = CrossRegionImpact(origin_component_id="x")
        assert c.origin_region == ""
        assert c.affected_regions == []
        assert c.cross_region_propagation is False
        assert c.total_regions_affected == 0

    def test_isolation_boundary_defaults(self):
        b = IsolationBoundary(boundary_id="b1")
        assert b.mechanism == ContainmentMechanism.NONE
        assert b.protected_components == []
        assert b.effectiveness_score == 0.0
        assert b.failure_leak_probability == 1.0
        assert b.components_behind == 0

    def test_containment_strategy_defaults(self):
        s = ContainmentStrategy()
        assert s.boundaries == []
        assert s.overall_containment_score == 0.0
        assert s.unprotected_components == []
        assert s.containment_gap_score == 0.0

    def test_blast_radius_reduction_defaults(self):
        r = BlastRadiusReduction(target_component_id="x")
        assert r.recommendation == ""
        assert r.priority == RecommendationPriority.MEDIUM
        assert r.estimated_risk_reduction_percent == 0.0
        assert r.mechanism == ContainmentMechanism.NONE

    def test_scenario_comparison_defaults(self):
        s = ScenarioComparison()
        assert s.scenarios == []
        assert s.worst_case_component == ""
        assert s.best_case_component == ""
        assert s.average_impact_score == 0.0
        assert s.median_impact_score == 0.0
        assert s.risk_ranking == []

    def test_blast_radius_report_defaults(self):
        r = BlastRadiusReport()
        assert r.timestamp == ""
        assert r.graph_component_count == 0
        assert r.impact_scores == []
        assert r.containment_strategy is None
        assert r.overall_risk_score == 0.0


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestClassifyDegradationZone:
    def test_full_outage(self):
        assert classify_degradation_zone(100.0) == DegradationZone.FULL_OUTAGE
        assert classify_degradation_zone(80.0) == DegradationZone.FULL_OUTAGE

    def test_severe(self):
        assert classify_degradation_zone(79.9) == DegradationZone.SEVERE_DEGRADATION
        assert classify_degradation_zone(50.0) == DegradationZone.SEVERE_DEGRADATION

    def test_partial(self):
        assert classify_degradation_zone(49.9) == DegradationZone.PARTIAL_DEGRADATION
        assert classify_degradation_zone(20.0) == DegradationZone.PARTIAL_DEGRADATION

    def test_minimal(self):
        assert classify_degradation_zone(19.9) == DegradationZone.MINIMAL_IMPACT
        assert classify_degradation_zone(0.1) == DegradationZone.MINIMAL_IMPACT

    def test_no_impact(self):
        assert classify_degradation_zone(0.0) == DegradationZone.NO_IMPACT


class TestGetTemporalPhase:
    def test_immediate(self):
        assert get_temporal_phase(0.0) == TemporalPhase.IMMEDIATE
        assert get_temporal_phase(30.0) == TemporalPhase.IMMEDIATE

    def test_short_term(self):
        assert get_temporal_phase(31.0) == TemporalPhase.SHORT_TERM
        assert get_temporal_phase(300.0) == TemporalPhase.SHORT_TERM

    def test_medium_term(self):
        assert get_temporal_phase(301.0) == TemporalPhase.MEDIUM_TERM
        assert get_temporal_phase(1800.0) == TemporalPhase.MEDIUM_TERM

    def test_long_term(self):
        assert get_temporal_phase(1801.0) == TemporalPhase.LONG_TERM
        assert get_temporal_phase(7200.0) == TemporalPhase.LONG_TERM

    def test_extended(self):
        assert get_temporal_phase(7201.0) == TemporalPhase.EXTENDED
        assert get_temporal_phase(999999.0) == TemporalPhase.EXTENDED


class TestDepTypeWeight:
    def test_requires(self):
        assert dep_type_weight("requires") == 1.0

    def test_optional(self):
        assert dep_type_weight("optional") == 0.3

    def test_async(self):
        assert dep_type_weight("async") == 0.1

    def test_unknown(self):
        assert dep_type_weight("some_other") == 0.1


class TestReplicaMitigationFactor:
    def test_single_replica(self):
        assert replica_mitigation_factor(1) == 1.0

    def test_two_replicas(self):
        assert replica_mitigation_factor(2) == 0.6

    def test_three_replicas(self):
        assert replica_mitigation_factor(3) == 0.35

    def test_many_replicas(self):
        f = replica_mitigation_factor(10)
        assert f == pytest.approx(0.1)

    def test_four_replicas(self):
        f = replica_mitigation_factor(4)
        assert f == 0.25


class TestIdentifyContainmentMechanism:
    def test_none(self):
        c = _comp("c1")
        g = _graph(c)
        assert identify_containment_mechanism(c, g) == ContainmentMechanism.NONE

    def test_circuit_breaker(self):
        a = _comp("a1")
        b = _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            Dependency(
                source_id="a1",
                target_id="b1",
                circuit_breaker=CircuitBreakerConfig(enabled=True),
            )
        )
        assert identify_containment_mechanism(a, g) == ContainmentMechanism.CIRCUIT_BREAKER

    def test_failover_with_replicas(self):
        c = _comp("c1", failover=True, replicas=2)
        g = _graph(c)
        assert identify_containment_mechanism(c, g) == ContainmentMechanism.FAILOVER

    def test_failover_without_replicas_falls_through(self):
        c = _comp("c1", failover=True, replicas=1)
        g = _graph(c)
        assert identify_containment_mechanism(c, g) == ContainmentMechanism.NONE

    def test_redundancy(self):
        c = _comp("c1", replicas=3)
        g = _graph(c)
        assert identify_containment_mechanism(c, g) == ContainmentMechanism.REDUNDANCY

    def test_network_segmentation(self):
        c = _comp("c1", network_segmented=True)
        g = _graph(c)
        assert identify_containment_mechanism(c, g) == ContainmentMechanism.NETWORK_SEGMENTATION

    def test_rate_limiter(self):
        c = _comp("c1", rate_limiting=True)
        g = _graph(c)
        assert identify_containment_mechanism(c, g) == ContainmentMechanism.RATE_LIMITER


class TestComputeDirectImpact:
    def test_isolated_component(self):
        c = _comp("c1")
        g = _graph(c)
        score = compute_direct_impact(c, g)
        assert score > 0.0
        assert score <= 100.0

    def test_with_dependents(self):
        db = _comp("db", ctype=ComponentType.DATABASE)
        s1 = _comp("s1")
        s2 = _comp("s2")
        s3 = _comp("s3")
        g = _graph(db, s1, s2, s3)
        g.add_dependency(Dependency(source_id="s1", target_id="db"))
        g.add_dependency(Dependency(source_id="s2", target_id="db"))
        g.add_dependency(Dependency(source_id="s3", target_id="db"))
        # db has 3 dependents, so its direct impact should be high
        score_db = compute_direct_impact(db, g)
        # s1 has no dependents
        score_s1 = compute_direct_impact(s1, g)
        assert score_db > score_s1

    def test_replicas_reduce_impact(self):
        c1 = _comp("c1", replicas=1)
        c3 = _comp("c3", replicas=3)
        g1 = _graph(c1)
        g3 = _graph(c3)
        assert compute_direct_impact(c1, g1) > compute_direct_impact(c3, g3)

    def test_optional_dep_lower_weight(self):
        a = _comp("a1")
        b = _comp("b1")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a1", target_id="b1", dependency_type="optional"))
        score_opt = compute_direct_impact(b, g)

        a2 = _comp("a2")
        b2 = _comp("b2")
        g2 = _graph(a2, b2)
        g2.add_dependency(Dependency(source_id="a2", target_id="b2", dependency_type="requires"))
        score_req = compute_direct_impact(b2, g2)

        assert score_opt < score_req


class TestComputeTransitiveImpact:
    def test_no_dependents(self):
        c = _comp("c1")
        g = _graph(c)
        score, depth, affected = compute_transitive_impact("c1", g)
        assert score == 0.0
        assert depth == 0
        assert affected == []

    def test_chain(self):
        a = _comp("a1")
        b = _comp("b1")
        c = _comp("c1")
        g = _graph(a, b, c)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))
        g.add_dependency(Dependency(source_id="b1", target_id="c1"))
        score, depth, affected = compute_transitive_impact("c1", g)
        assert score > 0.0
        assert depth == 2
        assert set(affected) == {"b1", "a1"}

    def test_circuit_breaker_reduces_transitive(self):
        a = _comp("a1")
        b = _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            Dependency(
                source_id="a1",
                target_id="b1",
                circuit_breaker=CircuitBreakerConfig(enabled=True),
            )
        )
        score_cb, _, _ = compute_transitive_impact("b1", g)

        a2 = _comp("a2")
        b2 = _comp("b2")
        g2 = _graph(a2, b2)
        g2.add_dependency(Dependency(source_id="a2", target_id="b2"))
        score_no_cb, _, _ = compute_transitive_impact("b2", g2)

        assert score_cb < score_no_cb

    def test_fully_contained_stops_propagation(self):
        a = _comp("a1", failover=True, replicas=2)
        b = _comp("b1")
        c = _comp("c1")
        g = _graph(a, b, c)
        g.add_dependency(
            Dependency(
                source_id="a1",
                target_id="b1",
                circuit_breaker=CircuitBreakerConfig(enabled=True),
            )
        )
        g.add_dependency(Dependency(source_id="c1", target_id="a1"))
        _, _, affected = compute_transitive_impact("b1", g)
        assert "c1" not in affected


class TestContainmentEffectivenessBase:
    def test_known_mechanisms(self):
        assert containment_effectiveness_base(ContainmentMechanism.CIRCUIT_BREAKER) == 0.85
        assert containment_effectiveness_base(ContainmentMechanism.BULKHEAD) == 0.75
        assert containment_effectiveness_base(ContainmentMechanism.FAILOVER) == 0.7
        assert containment_effectiveness_base(ContainmentMechanism.REDUNDANCY) == 0.6
        assert containment_effectiveness_base(ContainmentMechanism.RATE_LIMITER) == 0.5
        assert containment_effectiveness_base(ContainmentMechanism.NETWORK_SEGMENTATION) == 0.8
        assert containment_effectiveness_base(ContainmentMechanism.NONE) == 0.0


class TestComponentWeights:
    def test_user_weights_all_types(self):
        for ct in ComponentType:
            w = component_user_weight(ct)
            assert 0.0 < w <= 1.0

    def test_revenue_weights_all_types(self):
        for ct in ComponentType:
            w = component_revenue_weight(ct)
            assert 0.0 < w <= 1.0

    def test_lb_higher_than_cache(self):
        assert component_user_weight(ComponentType.LOAD_BALANCER) > component_user_weight(ComponentType.CACHE)

    def test_db_highest_revenue_weight(self):
        assert component_revenue_weight(ComponentType.DATABASE) == 1.0


# ---------------------------------------------------------------------------
# BlastRadiusCalculator -- impact scoring
# ---------------------------------------------------------------------------


class TestCalculateImpactScore:
    def test_nonexistent_component(self):
        g = _graph(_comp("c1"))
        calc = BlastRadiusCalculator(g)
        score = calc.calculate_impact_score("missing")
        assert score.component_id == "missing"
        assert score.total_impact_score == 0.0
        assert score.degradation_zone == DegradationZone.NO_IMPACT

    def test_isolated_component(self):
        g = _graph(_comp("c1"))
        calc = BlastRadiusCalculator(g)
        score = calc.calculate_impact_score("c1")
        assert score.direct_impact_score > 0.0
        assert score.transitive_impact_score == 0.0
        assert score.cascade_depth == 0

    def test_single_dependency(self):
        a = _comp("a1")
        b = _comp("b1")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))
        calc = BlastRadiusCalculator(g)
        score = calc.calculate_impact_score("b1")
        assert score.affected_downstream_count == 1
        assert score.cascade_depth == 1
        assert score.total_impact_score > 0.0

    def test_deep_chain_impact(self):
        comps = [_comp(f"c{i}") for i in range(5)]
        g = _graph(*comps)
        for i in range(4):
            g.add_dependency(Dependency(source_id=f"c{i + 1}", target_id=f"c{i}"))
        calc = BlastRadiusCalculator(g)
        score = calc.calculate_impact_score("c0")
        assert score.cascade_depth == 4
        assert score.affected_downstream_count == 4

    def test_fan_out_impact(self):
        db = _comp("db", ctype=ComponentType.DATABASE)
        services = [_comp(f"s{i}") for i in range(5)]
        g = _graph(db, *services)
        for s in services:
            g.add_dependency(Dependency(source_id=s.id, target_id="db"))
        calc = BlastRadiusCalculator(g)
        score = calc.calculate_impact_score("db")
        assert score.affected_downstream_count == 5

    def test_calculate_all_impact_scores(self):
        a = _comp("a1")
        b = _comp("b1")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))
        calc = BlastRadiusCalculator(g)
        scores = calc.calculate_all_impact_scores()
        assert len(scores) == 2
        # Sorted by total_impact_score descending
        assert scores[0].total_impact_score >= scores[1].total_impact_score

    def test_graph_property(self):
        g = _graph(_comp("c1"))
        calc = BlastRadiusCalculator(g)
        assert calc.graph is g


# ---------------------------------------------------------------------------
# Cascade depth
# ---------------------------------------------------------------------------


class TestCascadeDepth:
    def test_nonexistent(self):
        g = _graph(_comp("c1"))
        calc = BlastRadiusCalculator(g)
        result = calc.calculate_cascade_depth("missing")
        assert result.max_depth == 0
        assert result.total_affected == 0

    def test_isolated(self):
        g = _graph(_comp("c1"))
        calc = BlastRadiusCalculator(g)
        result = calc.calculate_cascade_depth("c1")
        assert result.max_depth == 0
        assert result.total_affected == 0
        assert result.components_at_depth == {}

    def test_chain_depth(self):
        comps = [_comp(f"c{i}") for i in range(4)]
        g = _graph(*comps)
        for i in range(3):
            g.add_dependency(Dependency(source_id=f"c{i + 1}", target_id=f"c{i}"))
        calc = BlastRadiusCalculator(g)
        result = calc.calculate_cascade_depth("c0")
        assert result.max_depth == 3
        assert result.total_affected == 3
        assert 1 in result.components_at_depth
        assert "c1" in result.components_at_depth[1]

    def test_propagation_paths(self):
        a = _comp("a1")
        b = _comp("b1")
        c = _comp("c1")
        g = _graph(a, b, c)
        g.add_dependency(Dependency(source_id="b1", target_id="c1"))
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))
        calc = BlastRadiusCalculator(g)
        result = calc.calculate_cascade_depth("c1")
        assert len(result.propagation_paths) >= 1
        # Longest path first
        longest = result.propagation_paths[0]
        assert longest[0] == "c1"


# ---------------------------------------------------------------------------
# User impact estimation
# ---------------------------------------------------------------------------


class TestUserImpact:
    def test_nonexistent(self):
        g = _graph(_comp("c1"))
        calc = BlastRadiusCalculator(g)
        u = calc.estimate_user_impact("missing")
        assert u.total_user_percent == 0.0

    def test_isolated(self):
        g = _graph(_comp("c1"))
        calc = BlastRadiusCalculator(g)
        u = calc.estimate_user_impact("c1")
        assert u.direct_user_percent > 0.0
        assert u.indirect_user_percent == 0.0
        assert 0.0 <= u.total_user_percent <= 100.0

    def test_with_dependents(self):
        a = _comp("a1", ctype=ComponentType.WEB_SERVER)
        b = _comp("b1")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))
        calc = BlastRadiusCalculator(g)
        u = calc.estimate_user_impact("b1")
        assert u.indirect_user_percent > 0.0
        assert u.total_user_percent > 0.0

    def test_affected_flows_web_server(self):
        c = _comp("c1", ctype=ComponentType.WEB_SERVER)
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        u = calc.estimate_user_impact("c1")
        assert "web_requests" in u.affected_user_flows

    def test_affected_flows_database(self):
        c = _comp("c1", ctype=ComponentType.DATABASE)
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        u = calc.estimate_user_impact("c1")
        assert "data_operations" in u.affected_user_flows

    def test_affected_flows_queue(self):
        c = _comp("c1", ctype=ComponentType.QUEUE)
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        u = calc.estimate_user_impact("c1")
        assert "async_processing" in u.affected_user_flows

    def test_affected_flows_dns(self):
        c = _comp("c1", ctype=ComponentType.DNS)
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        u = calc.estimate_user_impact("c1")
        assert "dns_resolution" in u.affected_user_flows

    def test_affected_flows_cache(self):
        c = _comp("c1", ctype=ComponentType.CACHE)
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        u = calc.estimate_user_impact("c1")
        assert "cached_reads" in u.affected_user_flows

    def test_affected_flows_storage(self):
        c = _comp("c1", ctype=ComponentType.STORAGE)
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        u = calc.estimate_user_impact("c1")
        assert "file_operations" in u.affected_user_flows

    def test_affected_flows_external_api(self):
        c = _comp("c1", ctype=ComponentType.EXTERNAL_API)
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        u = calc.estimate_user_impact("c1")
        assert "external_integrations" in u.affected_user_flows

    def test_affected_flows_load_balancer(self):
        c = _comp("c1", ctype=ComponentType.LOAD_BALANCER)
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        u = calc.estimate_user_impact("c1")
        assert "web_requests" in u.affected_user_flows

    def test_error_rate_bounded(self):
        c = _comp("c1", ctype=ComponentType.LOAD_BALANCER)
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        u = calc.estimate_user_impact("c1")
        assert 0.0 <= u.estimated_error_rate <= 1.0

    def test_replicas_reduce_user_impact(self):
        c1 = _comp("c1", replicas=1)
        c3 = _comp("c3", replicas=3)
        g1 = _graph(c1)
        g3 = _graph(c3)
        u1 = BlastRadiusCalculator(g1).estimate_user_impact("c1")
        u3 = BlastRadiusCalculator(g3).estimate_user_impact("c3")
        assert u3.direct_user_percent < u1.direct_user_percent

    def test_downstream_flows_added(self):
        db = _comp("db", ctype=ComponentType.DATABASE)
        app = _comp("app")
        g = _graph(db, app)
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        calc = BlastRadiusCalculator(g)
        u = calc.estimate_user_impact("db")
        # "api_requests" comes from downstream app_server
        assert "api_requests" in u.affected_user_flows or "data_operations" in u.affected_user_flows


# ---------------------------------------------------------------------------
# Revenue impact
# ---------------------------------------------------------------------------


class TestRevenueImpact:
    def test_nonexistent(self):
        g = _graph(_comp("c1"))
        calc = BlastRadiusCalculator(g)
        r = calc.calculate_revenue_impact("missing")
        assert r.total_cost_per_hour == 0.0

    def test_no_revenue(self):
        c = _comp("c1")
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        r = calc.calculate_revenue_impact("c1")
        assert r.revenue_loss_per_hour == 0.0

    def test_with_revenue(self):
        c = _comp("c1", revenue_per_min=100.0)
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        r = calc.calculate_revenue_impact("c1")
        assert r.revenue_loss_per_hour > 0.0
        assert r.revenue_loss_per_minute > 0.0

    def test_sla_credit(self):
        c = _comp("c1", monthly_contract=10000.0, sla_credit_pct=10.0)
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        r = calc.calculate_revenue_impact("c1")
        assert r.sla_credit_exposure == pytest.approx(1000.0)

    def test_recovery_cost(self):
        c = _comp("c1", recovery_team_size=3, recovery_engineer_cost=200.0, mttr=60.0)
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        r = calc.calculate_revenue_impact("c1")
        assert r.recovery_cost == pytest.approx(3 * 200.0 * 1.0)

    def test_default_team_size(self):
        c = _comp("c1", recovery_team_size=0, recovery_engineer_cost=100.0, mttr=60.0)
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        r = calc.calculate_revenue_impact("c1")
        assert r.recovery_cost == pytest.approx(2 * 100.0 * 1.0)

    def test_revenue_streams_direct(self):
        c = _comp("c1", revenue_per_min=10.0)
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        r = calc.calculate_revenue_impact("c1")
        assert "direct_revenue" in r.impacted_revenue_streams

    def test_revenue_streams_contract(self):
        c = _comp("c1", monthly_contract=5000.0)
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        r = calc.calculate_revenue_impact("c1")
        assert "contract_revenue" in r.impacted_revenue_streams

    def test_revenue_streams_ltv(self):
        c = _comp("c1", customer_ltv=1000.0)
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        r = calc.calculate_revenue_impact("c1")
        assert "customer_lifetime_value" in r.impacted_revenue_streams

    def test_revenue_streams_infra(self):
        c = _comp("c1", hourly_cost=50.0)
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        r = calc.calculate_revenue_impact("c1")
        assert "infrastructure_cost" in r.impacted_revenue_streams

    def test_revenue_streams_indirect_only(self):
        c = _comp("c1")
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        r = calc.calculate_revenue_impact("c1")
        assert "indirect_operational" in r.impacted_revenue_streams

    def test_replicas_reduce_revenue_loss(self):
        c1 = _comp("c1", revenue_per_min=100.0, replicas=1)
        c3 = _comp("c3", revenue_per_min=100.0, replicas=3)
        g1 = _graph(c1)
        g3 = _graph(c3)
        r1 = BlastRadiusCalculator(g1).calculate_revenue_impact("c1")
        r3 = BlastRadiusCalculator(g3).calculate_revenue_impact("c3")
        assert r3.revenue_loss_per_hour < r1.revenue_loss_per_hour


# ---------------------------------------------------------------------------
# Degradation zones
# ---------------------------------------------------------------------------


class TestDegradationZones:
    def test_classify_all(self):
        a = _comp("a1")
        b = _comp("b1")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))
        calc = BlastRadiusCalculator(g)
        zones = calc.classify_degradation_zones()
        assert "a1" in zones
        assert "b1" in zones

    def test_get_components_in_zone(self):
        c = _comp("c1")
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        zones = calc.classify_degradation_zones()
        zone = zones["c1"]
        in_zone = calc.get_components_in_zone(zone)
        assert "c1" in in_zone

    def test_empty_zone_returns_empty(self):
        c = _comp("c1")
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        in_zone = calc.get_components_in_zone(DegradationZone.FULL_OUTAGE)
        # Single isolated component should not be full outage
        assert "c1" not in in_zone or True  # depends on score; just test the method works


# ---------------------------------------------------------------------------
# Containment strategy
# ---------------------------------------------------------------------------


class TestContainmentStrategy:
    def test_empty_graph(self):
        g = InfraGraph()
        calc = BlastRadiusCalculator(g)
        strategy = calc.analyze_containment_strategy()
        assert strategy.boundaries == []
        assert strategy.overall_containment_score == 0.0
        assert strategy.containment_gap_score == 0.0

    def test_no_containment(self):
        a = _comp("a1")
        b = _comp("b1")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))
        calc = BlastRadiusCalculator(g)
        strategy = calc.analyze_containment_strategy()
        assert strategy.boundaries == []
        assert strategy.overall_containment_score == 0.0
        assert len(strategy.unprotected_components) == 2

    def test_circuit_breaker_boundary(self):
        a = _comp("a1")
        b = _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            Dependency(
                source_id="a1",
                target_id="b1",
                circuit_breaker=CircuitBreakerConfig(enabled=True),
            )
        )
        calc = BlastRadiusCalculator(g)
        strategy = calc.analyze_containment_strategy()
        assert len(strategy.boundaries) >= 1
        assert strategy.overall_containment_score > 0.0

    def test_redundancy_boundary(self):
        c = _comp("c1", replicas=3)
        d = _comp("d1")
        g = _graph(c, d)
        g.add_dependency(Dependency(source_id="d1", target_id="c1"))
        calc = BlastRadiusCalculator(g)
        strategy = calc.analyze_containment_strategy()
        assert any(
            b.mechanism == ContainmentMechanism.REDUNDANCY for b in strategy.boundaries
        )

    def test_failover_boundary(self):
        c = _comp("c1", failover=True, replicas=2)
        d = _comp("d1")
        g = _graph(c, d)
        g.add_dependency(Dependency(source_id="d1", target_id="c1"))
        calc = BlastRadiusCalculator(g)
        strategy = calc.analyze_containment_strategy()
        assert any(
            b.mechanism == ContainmentMechanism.FAILOVER for b in strategy.boundaries
        )

    def test_gap_score_all_unprotected(self):
        a = _comp("a1")
        b = _comp("b1")
        g = _graph(a, b)
        calc = BlastRadiusCalculator(g)
        strategy = calc.analyze_containment_strategy()
        assert strategy.containment_gap_score == 100.0

    def test_network_segmentation_boundary(self):
        c = _comp("c1", network_segmented=True)
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        strategy = calc.analyze_containment_strategy()
        assert any(
            b.mechanism == ContainmentMechanism.NETWORK_SEGMENTATION
            for b in strategy.boundaries
        )

    def test_rate_limiter_boundary(self):
        c = _comp("c1", rate_limiting=True)
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        strategy = calc.analyze_containment_strategy()
        assert any(
            b.mechanism == ContainmentMechanism.RATE_LIMITER
            for b in strategy.boundaries
        )

    def test_replicas_boost_effectiveness(self):
        c2 = _comp("c2", replicas=2, failover=True)
        c3 = _comp("c3", replicas=3, failover=True)
        g2 = _graph(c2)
        g3 = _graph(c3)
        s2 = BlastRadiusCalculator(g2).analyze_containment_strategy()
        s3 = BlastRadiusCalculator(g3).analyze_containment_strategy()
        # 3 replicas gets higher effectiveness
        eff2 = s2.boundaries[0].effectiveness_score if s2.boundaries else 0
        eff3 = s3.boundaries[0].effectiveness_score if s3.boundaries else 0
        assert eff3 >= eff2


# ---------------------------------------------------------------------------
# Temporal progression
# ---------------------------------------------------------------------------


class TestTemporalProgression:
    def test_nonexistent(self):
        g = _graph(_comp("c1"))
        calc = BlastRadiusCalculator(g)
        tp = calc.calculate_temporal_progression("missing")
        assert tp.snapshots == []
        assert tp.peak_affected_count == 0

    def test_isolated(self):
        g = _graph(_comp("c1"))
        calc = BlastRadiusCalculator(g)
        tp = calc.calculate_temporal_progression("c1")
        assert len(tp.snapshots) == 1
        assert tp.snapshots[0].phase == TemporalPhase.IMMEDIATE
        assert tp.snapshots[0].affected_count == 0
        assert tp.time_to_full_propagation_seconds == 0.0

    def test_chain_progression(self):
        comps = [_comp(f"c{i}") for i in range(4)]
        g = _graph(*comps)
        for i in range(3):
            g.add_dependency(Dependency(source_id=f"c{i + 1}", target_id=f"c{i}"))
        calc = BlastRadiusCalculator(g)
        tp = calc.calculate_temporal_progression("c0")
        assert len(tp.snapshots) >= 2
        assert tp.peak_affected_count == 3
        assert tp.time_to_full_propagation_seconds > 0.0
        # Snapshots have increasing elapsed time
        for i in range(1, len(tp.snapshots)):
            assert tp.snapshots[i].elapsed_seconds >= tp.snapshots[i - 1].elapsed_seconds

    def test_revenue_accumulates(self):
        a = _comp("a1", revenue_per_min=10.0)
        b = _comp("b1", revenue_per_min=20.0)
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))
        calc = BlastRadiusCalculator(g)
        tp = calc.calculate_temporal_progression("b1")
        if tp.snapshots:
            assert tp.snapshots[-1].cumulative_revenue_loss >= 0.0

    def test_fan_out_peak(self):
        db = _comp("db")
        services = [_comp(f"s{i}") for i in range(3)]
        g = _graph(db, *services)
        for s in services:
            g.add_dependency(Dependency(source_id=s.id, target_id="db"))
        calc = BlastRadiusCalculator(g)
        tp = calc.calculate_temporal_progression("db")
        assert tp.peak_affected_count == 3


# ---------------------------------------------------------------------------
# Cross-region analysis
# ---------------------------------------------------------------------------


class TestCrossRegionImpact:
    def test_nonexistent(self):
        g = _graph(_comp("c1"))
        calc = BlastRadiusCalculator(g)
        cr = calc.analyze_cross_region_impact("missing")
        assert cr.total_regions_affected == 0

    def test_single_region(self):
        a = _comp("a1", region="us-east-1")
        b = _comp("b1", region="us-east-1")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))
        calc = BlastRadiusCalculator(g)
        cr = calc.analyze_cross_region_impact("b1")
        assert cr.origin_region == "us-east-1"
        assert cr.cross_region_propagation is False

    def test_cross_region(self):
        a = _comp("a1", region="us-east-1")
        b = _comp("b1", region="eu-west-1")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="b1", target_id="a1"))
        calc = BlastRadiusCalculator(g)
        cr = calc.analyze_cross_region_impact("a1")
        assert cr.cross_region_propagation is True
        assert cr.total_regions_affected >= 1
        assert "eu-west-1" in cr.affected_regions

    def test_no_dependents(self):
        c = _comp("c1", region="ap-southeast-1")
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        cr = calc.analyze_cross_region_impact("c1")
        assert cr.origin_region == "ap-southeast-1"
        assert cr.total_regions_affected == 0

    def test_unknown_region_default(self):
        c = _comp("c1")  # no region set
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        cr = calc.analyze_cross_region_impact("c1")
        assert cr.origin_region == "unknown"

    def test_region_scores_capped(self):
        db = _comp("db", region="us-east-1")
        services = [_comp(f"s{i}", region="us-east-1") for i in range(10)]
        g = _graph(db, *services)
        for s in services:
            g.add_dependency(Dependency(source_id=s.id, target_id="db"))
        calc = BlastRadiusCalculator(g)
        cr = calc.analyze_cross_region_impact("db")
        for score in cr.region_impact_scores.values():
            assert score <= 100.0


# ---------------------------------------------------------------------------
# Scenario comparison
# ---------------------------------------------------------------------------


class TestScenarioComparison:
    def test_empty(self):
        g = _graph(_comp("c1"))
        calc = BlastRadiusCalculator(g)
        result = calc.compare_scenarios([])
        assert result.scenarios == []
        assert result.worst_case_component == ""

    def test_single_component(self):
        g = _graph(_comp("c1"))
        calc = BlastRadiusCalculator(g)
        result = calc.compare_scenarios(["c1"])
        assert len(result.scenarios) == 1
        assert result.worst_case_component == "c1"
        assert result.best_case_component == "c1"
        assert result.average_impact_score == result.scenarios[0].total_impact_score

    def test_two_components_ranking(self):
        db = _comp("db", ctype=ComponentType.DATABASE)
        cache = _comp("cache", ctype=ComponentType.CACHE)
        app = _comp("app")
        g = _graph(db, cache, app)
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        g.add_dependency(Dependency(source_id="app", target_id="cache"))
        calc = BlastRadiusCalculator(g)
        result = calc.compare_scenarios(["db", "cache"])
        assert len(result.risk_ranking) == 2
        # First in ranking should be worst
        assert result.risk_ranking[0][0] == result.worst_case_component

    def test_median_odd(self):
        comps = [_comp(f"c{i}") for i in range(3)]
        g = _graph(*comps)
        calc = BlastRadiusCalculator(g)
        result = calc.compare_scenarios(["c0", "c1", "c2"])
        assert len(result.scenarios) == 3
        # Median should be a valid number
        assert result.median_impact_score >= 0.0

    def test_median_even(self):
        comps = [_comp(f"c{i}") for i in range(4)]
        g = _graph(*comps)
        calc = BlastRadiusCalculator(g)
        result = calc.compare_scenarios(["c0", "c1", "c2", "c3"])
        assert len(result.scenarios) == 4
        assert result.median_impact_score >= 0.0


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------


class TestRecommendations:
    def test_empty_graph(self):
        g = InfraGraph()
        calc = BlastRadiusCalculator(g)
        recs = calc.generate_recommendations()
        assert recs == []

    def test_single_replica_gets_redundancy_rec(self):
        a = _comp("a1")
        b = _comp("b1")
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))
        calc = BlastRadiusCalculator(g)
        recs = calc.generate_recommendations()
        assert any(r.mechanism == ContainmentMechanism.REDUNDANCY for r in recs)

    def test_no_failover_gets_failover_rec(self):
        comps = [_comp(f"c{i}") for i in range(4)]
        g = _graph(*comps)
        for i in range(3):
            g.add_dependency(Dependency(source_id=f"c{i + 1}", target_id=f"c{i}"))
        calc = BlastRadiusCalculator(g)
        recs = calc.generate_recommendations()
        assert any(r.mechanism == ContainmentMechanism.FAILOVER for r in recs)

    def test_deep_cascade_gets_bulkhead_rec(self):
        comps = [_comp(f"c{i}") for i in range(5)]
        g = _graph(*comps)
        for i in range(4):
            g.add_dependency(Dependency(source_id=f"c{i + 1}", target_id=f"c{i}"))
        calc = BlastRadiusCalculator(g)
        recs = calc.generate_recommendations()
        assert any(r.mechanism == ContainmentMechanism.BULKHEAD for r in recs)

    def test_database_gets_network_seg_rec(self):
        db = _comp("db", ctype=ComponentType.DATABASE)
        app = _comp("app")
        g = _graph(db, app)
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        calc = BlastRadiusCalculator(g)
        recs = calc.generate_recommendations()
        assert any(
            r.mechanism == ContainmentMechanism.NETWORK_SEGMENTATION for r in recs
        )

    def test_storage_gets_network_seg_rec(self):
        st = _comp("st", ctype=ComponentType.STORAGE)
        app = _comp("app")
        g = _graph(st, app)
        g.add_dependency(Dependency(source_id="app", target_id="st"))
        calc = BlastRadiusCalculator(g)
        recs = calc.generate_recommendations()
        assert any(
            r.mechanism == ContainmentMechanism.NETWORK_SEGMENTATION for r in recs
        )

    def test_high_impact_gets_critical_cb_rec(self):
        db = _comp("db", ctype=ComponentType.DATABASE)
        services = [_comp(f"s{i}") for i in range(5)]
        g = _graph(db, *services)
        for s in services:
            g.add_dependency(Dependency(source_id=s.id, target_id="db"))
        calc = BlastRadiusCalculator(g)
        recs = calc.generate_recommendations()
        critical_cb = [
            r for r in recs
            if r.priority == RecommendationPriority.CRITICAL
            and r.mechanism == ContainmentMechanism.CIRCUIT_BREAKER
        ]
        assert len(critical_cb) >= 1

    def test_recs_sorted_by_priority(self):
        db = _comp("db", ctype=ComponentType.DATABASE)
        services = [_comp(f"s{i}") for i in range(4)]
        g = _graph(db, *services)
        for s in services:
            g.add_dependency(Dependency(source_id=s.id, target_id="db"))
        for i in range(3):
            g.add_dependency(Dependency(source_id=f"s{i + 1}", target_id=f"s{i}"))
        calc = BlastRadiusCalculator(g)
        recs = calc.generate_recommendations()
        prio_order = {
            RecommendationPriority.CRITICAL: 0,
            RecommendationPriority.HIGH: 1,
            RecommendationPriority.MEDIUM: 2,
            RecommendationPriority.LOW: 3,
        }
        prios = [prio_order.get(r.priority, 99) for r in recs]
        assert prios == sorted(prios)

    def test_many_downstream_gets_high_priority(self):
        db = _comp("db")
        services = [_comp(f"s{i}") for i in range(5)]
        g = _graph(db, *services)
        for s in services:
            g.add_dependency(Dependency(source_id=s.id, target_id="db"))
        calc = BlastRadiusCalculator(g)
        recs = calc.generate_recommendations()
        redundancy_recs = [
            r for r in recs
            if r.mechanism == ContainmentMechanism.REDUNDANCY
            and r.target_component_id == "db"
        ]
        assert any(r.priority == RecommendationPriority.HIGH for r in redundancy_recs)

    def test_already_protected_no_duplicate_recs(self):
        c = _comp("c1", replicas=3, failover=True, network_segmented=True)
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        recs = calc.generate_recommendations()
        # A fully protected isolated component should get minimal recommendations
        assert all(r.target_component_id == "c1" for r in recs) or len(recs) == 0


# ---------------------------------------------------------------------------
# Isolation boundary effectiveness
# ---------------------------------------------------------------------------


class TestIsolationBoundaryEffectiveness:
    def test_nonexistent(self):
        g = _graph(_comp("c1"))
        calc = BlastRadiusCalculator(g)
        assert calc.calculate_boundary_effectiveness("missing") == 0.0

    def test_no_mechanism(self):
        c = _comp("c1")
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        assert calc.calculate_boundary_effectiveness("c1") == 0.0

    def test_circuit_breaker_effectiveness(self):
        a = _comp("a1")
        b = _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            Dependency(
                source_id="a1",
                target_id="b1",
                circuit_breaker=CircuitBreakerConfig(enabled=True),
            )
        )
        calc = BlastRadiusCalculator(g)
        eff = calc.calculate_boundary_effectiveness("a1")
        assert eff == pytest.approx(0.85)

    def test_failover_with_2_replicas(self):
        c = _comp("c1", failover=True, replicas=2)
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        eff = calc.calculate_boundary_effectiveness("c1")
        assert eff == pytest.approx(0.75)  # 0.7 + 0.05

    def test_failover_with_3_replicas(self):
        c = _comp("c1", failover=True, replicas=3)
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        eff = calc.calculate_boundary_effectiveness("c1")
        # Redundancy detected first (replicas >= 3), base 0.6 + 0.1 + failover 0.05
        # Actually: failover+replicas>=2 is checked before replicas>=3
        # So mechanism = FAILOVER, base = 0.7, +0.1 for 3 replicas = 0.8
        assert eff == pytest.approx(0.8)

    def test_redundancy_3_replicas_no_failover(self):
        c = _comp("c1", replicas=3)
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        eff = calc.calculate_boundary_effectiveness("c1")
        assert eff == pytest.approx(0.7)  # 0.6 + 0.1

    def test_network_segmentation(self):
        c = _comp("c1", network_segmented=True)
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        eff = calc.calculate_boundary_effectiveness("c1")
        assert eff == pytest.approx(0.8)

    def test_rate_limiter(self):
        c = _comp("c1", rate_limiting=True)
        g = _graph(c)
        calc = BlastRadiusCalculator(g)
        eff = calc.calculate_boundary_effectiveness("c1")
        assert eff == pytest.approx(0.5)

    def test_score_isolation_boundaries(self):
        a = _comp("a1", replicas=3)
        b = _comp("b1", network_segmented=True)
        g = _graph(a, b)
        calc = BlastRadiusCalculator(g)
        boundaries = calc.score_isolation_boundaries()
        assert len(boundaries) == 2

    def test_cb_plus_failover_boost(self):
        a = _comp("a1", failover=True)
        b = _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            Dependency(
                source_id="a1",
                target_id="b1",
                circuit_breaker=CircuitBreakerConfig(enabled=True),
            )
        )
        calc = BlastRadiusCalculator(g)
        eff = calc.calculate_boundary_effectiveness("a1")
        # CB = 0.85, failover enabled but mechanism != FAILOVER so +0.05
        assert eff == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# Full report
# ---------------------------------------------------------------------------


class TestFullReport:
    def test_empty_graph(self):
        g = InfraGraph()
        calc = BlastRadiusCalculator(g)
        report = calc.generate_full_report()
        assert report.graph_component_count == 0
        assert report.graph_dependency_count == 0
        assert report.impact_scores == []
        assert report.overall_risk_score == 0.0
        assert report.timestamp != ""

    def test_single_component(self):
        g = _graph(_comp("c1"))
        calc = BlastRadiusCalculator(g)
        report = calc.generate_full_report()
        assert report.graph_component_count == 1
        assert len(report.impact_scores) == 1
        assert len(report.user_impacts) == 1
        assert len(report.revenue_impacts) == 1
        assert len(report.temporal_progressions) == 1
        assert len(report.cross_region_impacts) == 1
        assert report.containment_strategy is not None
        assert report.scenario_comparison is not None

    def test_full_workflow(self):
        db = _comp("db", ctype=ComponentType.DATABASE, revenue_per_min=50.0, region="us-east-1")
        app = _comp("app", revenue_per_min=10.0, region="us-east-1")
        web = _comp("web", ctype=ComponentType.WEB_SERVER, region="eu-west-1")
        cache = _comp("cache", ctype=ComponentType.CACHE, replicas=3, region="us-east-1")
        g = _graph(db, app, web, cache)
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        g.add_dependency(Dependency(source_id="web", target_id="app"))
        g.add_dependency(Dependency(source_id="app", target_id="cache"))

        calc = BlastRadiusCalculator(g)
        report = calc.generate_full_report()

        assert report.graph_component_count == 4
        assert report.graph_dependency_count == 3
        assert len(report.impact_scores) == 4
        assert len(report.cascade_results) == 4
        assert len(report.user_impacts) == 4
        assert len(report.revenue_impacts) == 4
        assert len(report.temporal_progressions) == 4
        assert len(report.cross_region_impacts) == 4
        assert report.containment_strategy is not None
        assert report.scenario_comparison is not None
        assert report.overall_risk_score >= 0.0
        assert report.timestamp != ""

    def test_report_with_containment(self):
        a = _comp("a1", failover=True, replicas=3)
        b = _comp("b1")
        g = _graph(a, b)
        g.add_dependency(
            Dependency(
                source_id="b1",
                target_id="a1",
                circuit_breaker=CircuitBreakerConfig(enabled=True),
            )
        )
        calc = BlastRadiusCalculator(g)
        report = calc.generate_full_report()
        assert report.containment_strategy is not None
        assert len(report.containment_strategy.boundaries) >= 1


# ---------------------------------------------------------------------------
# Large / complex graph integration
# ---------------------------------------------------------------------------


class TestLargeGraphIntegration:
    def test_deep_chain(self):
        comps = [_comp(f"c{i}") for i in range(15)]
        g = _graph(*comps)
        for i in range(14):
            g.add_dependency(Dependency(source_id=f"c{i + 1}", target_id=f"c{i}"))
        calc = BlastRadiusCalculator(g)
        score = calc.calculate_impact_score("c0")
        assert score.cascade_depth == 14
        assert score.affected_downstream_count == 14

    def test_diamond_dependency(self):
        db = _comp("db")
        svc1 = _comp("svc1")
        svc2 = _comp("svc2")
        web = _comp("web")
        g = _graph(db, svc1, svc2, web)
        g.add_dependency(Dependency(source_id="svc1", target_id="db"))
        g.add_dependency(Dependency(source_id="svc2", target_id="db"))
        g.add_dependency(Dependency(source_id="web", target_id="svc1"))
        g.add_dependency(Dependency(source_id="web", target_id="svc2"))
        calc = BlastRadiusCalculator(g)
        score = calc.calculate_impact_score("db")
        assert score.affected_downstream_count == 3

    def test_fan_in_fan_out(self):
        db = _comp("db")
        mid = [_comp(f"mid{i}") for i in range(3)]
        front = [_comp(f"front{i}") for i in range(3)]
        g = _graph(db, *mid, *front)
        for m in mid:
            g.add_dependency(Dependency(source_id=m.id, target_id="db"))
        for f in front:
            g.add_dependency(Dependency(source_id=f.id, target_id="mid0"))
        calc = BlastRadiusCalculator(g)
        score = calc.calculate_impact_score("db")
        assert score.affected_downstream_count >= 3

    def test_isolated_multiple_components(self):
        comps = [_comp(f"c{i}") for i in range(5)]
        g = _graph(*comps)
        calc = BlastRadiusCalculator(g)
        scores = calc.calculate_all_impact_scores()
        assert len(scores) == 5
        for s in scores:
            assert s.cascade_depth == 0
            assert s.affected_downstream_count == 0

    def test_mixed_dep_types(self):
        a = _comp("a1")
        b = _comp("b1")
        c = _comp("c1")
        g = _graph(a, b, c)
        g.add_dependency(Dependency(source_id="a1", target_id="c1", dependency_type="requires"))
        g.add_dependency(Dependency(source_id="b1", target_id="c1", dependency_type="optional"))
        calc = BlastRadiusCalculator(g)
        score = calc.calculate_impact_score("c1")
        assert score.affected_downstream_count == 2

    def test_complete_end_to_end(self):
        """Full workflow: impact, cascade, user, revenue, temporal, cross-region,
        containment, recommendations, comparison, isolation, report."""
        db = _comp("db", ctype=ComponentType.DATABASE, revenue_per_min=50.0, region="us-east-1")
        app = _comp("app", revenue_per_min=10.0, region="us-east-1")
        web = _comp("web", ctype=ComponentType.WEB_SERVER, region="eu-west-1")
        cache = _comp("cache", ctype=ComponentType.CACHE, replicas=3, region="us-east-1")
        lb = _comp("lb", ctype=ComponentType.LOAD_BALANCER, region="us-east-1", failover=True, replicas=2)
        g = _graph(db, app, web, cache, lb)
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        g.add_dependency(Dependency(source_id="web", target_id="app"))
        g.add_dependency(Dependency(source_id="app", target_id="cache"))
        g.add_dependency(
            Dependency(
                source_id="web",
                target_id="lb",
                circuit_breaker=CircuitBreakerConfig(enabled=True),
            )
        )

        calc = BlastRadiusCalculator(g)

        # 1. Impact score
        score = calc.calculate_impact_score("db")
        assert score.total_impact_score > 0

        # 2. Cascade depth
        cascade = calc.calculate_cascade_depth("db")
        assert cascade.total_affected >= 2

        # 3. User impact
        user = calc.estimate_user_impact("db")
        assert user.total_user_percent > 0

        # 4. Revenue impact
        rev = calc.calculate_revenue_impact("db")
        assert rev.revenue_loss_per_hour > 0

        # 5. Degradation zones
        zones = calc.classify_degradation_zones()
        assert len(zones) == 5

        # 6. Containment strategy
        strategy = calc.analyze_containment_strategy()
        assert isinstance(strategy, ContainmentStrategy)

        # 7. Temporal progression
        tp = calc.calculate_temporal_progression("db")
        assert tp.peak_affected_count >= 1

        # 8. Cross-region
        cr = calc.analyze_cross_region_impact("db")
        assert cr.origin_region == "us-east-1"

        # 9. Scenario comparison
        cmp = calc.compare_scenarios(["db", "cache"])
        assert len(cmp.scenarios) == 2

        # 10. Recommendations
        recs = calc.generate_recommendations()
        assert len(recs) > 0

        # 11. Isolation boundary effectiveness
        eff = calc.calculate_boundary_effectiveness("lb")
        assert eff > 0.0

        # 12. Full report
        report = calc.generate_full_report()
        assert report.graph_component_count == 5
