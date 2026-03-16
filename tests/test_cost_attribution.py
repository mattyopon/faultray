"""Tests for Failure Cost Attribution Engine."""

from unittest.mock import patch

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    OperationalProfile,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.cost_attribution import (
    ComponentCostProfile,
    CostAttributionEngine,
    CostAttributionReport,
    CostModel,
    TeamRiskProfile,
    _auto_assign_team,
    _estimate_downtime_hours,
    _estimate_failure_probability,
    _estimate_traffic_fraction,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_test_graph() -> InfraGraph:
    """Build a 4-component graph: lb -> api -> db, api -> cache."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="lb-main", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2, failover=FailoverConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="api-server", name="API Server", type=ComponentType.APP_SERVER,
        replicas=1,
        operational_profile=OperationalProfile(mttr_minutes=30),
    ))
    graph.add_component(Component(
        id="db-primary", name="Primary Database", type=ComponentType.DATABASE,
        replicas=1,
        operational_profile=OperationalProfile(mtbf_hours=4320, mttr_minutes=60),
    ))
    graph.add_component(Component(
        id="redis-cache", name="Redis Cache", type=ComponentType.CACHE,
        replicas=1,
    ))

    graph.add_dependency(Dependency(
        source_id="lb-main", target_id="api-server", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="api-server", target_id="db-primary", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="api-server", target_id="redis-cache", dependency_type="optional",
    ))

    return graph


def _build_redundant_graph() -> InfraGraph:
    """Build a graph with full redundancy."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2, failover=FailoverConfig(enabled=True),
        autoscaling=AutoScalingConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=3, failover=FailoverConfig(enabled=True),
        autoscaling=AutoScalingConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=2, failover=FailoverConfig(enabled=True),
    ))

    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))

    return graph


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

def test_auto_assign_team_api():
    """API-prefixed components should map to backend team."""
    assert _auto_assign_team("api-server") == "backend"
    assert _auto_assign_team("api_gateway") == "backend"
    assert _auto_assign_team("web-frontend") == "backend"


def test_auto_assign_team_data():
    """Database-related components should map to data team."""
    assert _auto_assign_team("db-primary") == "data"
    assert _auto_assign_team("postgres-main") == "data"
    assert _auto_assign_team("redis-cache") == "data"


def test_auto_assign_team_infra():
    """Infrastructure components should map to infra team."""
    assert _auto_assign_team("lb-main") == "infra"
    assert _auto_assign_team("nginx-proxy") == "infra"
    assert _auto_assign_team("cdn-edge") == "infra"


def test_auto_assign_team_default():
    """Unmatched components should map to platform team."""
    assert _auto_assign_team("custom-service") == "platform"
    assert _auto_assign_team("worker") == "platform"


def test_estimate_failure_probability_single():
    """Single instance should have higher failure probability."""
    prob = _estimate_failure_probability(1, False, False)
    assert 0.0 < prob <= 1.0
    assert prob > 0.5  # High probability with default assumptions


def test_estimate_failure_probability_replicas():
    """Multiple replicas should reduce failure probability."""
    single = _estimate_failure_probability(1, False, False)
    multi = _estimate_failure_probability(2, False, False)
    assert multi < single


def test_estimate_failure_probability_failover():
    """Failover should reduce failure probability."""
    no_fo = _estimate_failure_probability(1, False, False)
    with_fo = _estimate_failure_probability(1, True, False)
    assert with_fo < no_fo


def test_estimate_failure_probability_autoscaling():
    """Autoscaling should reduce failure probability."""
    no_as = _estimate_failure_probability(1, False, False)
    with_as = _estimate_failure_probability(1, False, True)
    assert with_as < no_as


def test_estimate_failure_probability_with_mtbf():
    """Custom MTBF should affect failure probability."""
    # High MTBF = lower failure rate
    high_mtbf = _estimate_failure_probability(1, False, False, mtbf_hours=87600)
    low_mtbf = _estimate_failure_probability(1, False, False, mtbf_hours=100)
    assert high_mtbf < low_mtbf


def test_estimate_downtime_single():
    """Single instance downtime should equal full MTTR."""
    downtime = _estimate_downtime_hours(1, False, mttr_minutes=60)
    assert downtime == 1.0  # 60 min = 1 hour


def test_estimate_downtime_with_failover():
    """Failover should reduce downtime."""
    no_fo = _estimate_downtime_hours(1, False, mttr_minutes=60)
    with_fo = _estimate_downtime_hours(1, True, mttr_minutes=60)
    assert with_fo < no_fo


def test_estimate_downtime_with_replicas_and_failover():
    """Replicas + failover should minimize downtime."""
    downtime = _estimate_downtime_hours(2, True, mttr_minutes=60)
    single = _estimate_downtime_hours(1, False, mttr_minutes=60)
    assert downtime < single * 0.2


def test_estimate_traffic_fraction():
    """Traffic fraction should be positive and <= 1.0."""
    graph = _build_test_graph()
    for comp_id in graph.components:
        frac = _estimate_traffic_fraction(graph, comp_id)
        assert 0.0 < frac <= 1.0


# ---------------------------------------------------------------------------
# CostModel tests
# ---------------------------------------------------------------------------

def test_cost_model_defaults():
    """CostModel should have reasonable defaults."""
    model = CostModel(revenue_per_hour=10_000)
    assert model.revenue_per_hour == 10_000
    assert model.cost_per_incident == 50_000
    assert model.currency == "USD"


# ---------------------------------------------------------------------------
# CostAttributionEngine tests
# ---------------------------------------------------------------------------

def test_analyze_returns_report():
    """analyze() should return a CostAttributionReport."""
    graph = _build_test_graph()
    model = CostModel(revenue_per_hour=10_000)
    engine = CostAttributionEngine()

    report = engine.analyze(graph, model)

    assert isinstance(report, CostAttributionReport)


def test_analyze_total_risk_positive():
    """Total annual risk should be positive for graphs with components."""
    graph = _build_test_graph()
    model = CostModel(revenue_per_hour=10_000)
    engine = CostAttributionEngine()

    report = engine.analyze(graph, model)

    assert report.total_annual_risk > 0


def test_analyze_component_profiles():
    """All components should have cost profiles."""
    graph = _build_test_graph()
    model = CostModel(revenue_per_hour=10_000)
    engine = CostAttributionEngine()

    report = engine.analyze(graph, model)

    assert len(report.component_profiles) == len(graph.components)


def test_analyze_component_profiles_sorted():
    """Component profiles should be sorted by annual risk descending."""
    graph = _build_test_graph()
    model = CostModel(revenue_per_hour=10_000)
    engine = CostAttributionEngine()

    report = engine.analyze(graph, model)

    risks = [p.total_annual_risk for p in report.component_profiles]
    assert risks == sorted(risks, reverse=True)


def test_analyze_percentage_sums_to_100():
    """Component risk percentages should approximately sum to 100%."""
    graph = _build_test_graph()
    model = CostModel(revenue_per_hour=10_000)
    engine = CostAttributionEngine()

    report = engine.analyze(graph, model)

    total_pct = sum(p.percentage_of_total_risk for p in report.component_profiles)
    assert abs(total_pct - 100.0) < 1.0  # Allow small rounding error


def test_analyze_team_profiles():
    """Team profiles should be generated."""
    graph = _build_test_graph()
    model = CostModel(revenue_per_hour=10_000)
    engine = CostAttributionEngine()

    report = engine.analyze(graph, model)

    assert len(report.team_profiles) > 0
    # Each team should have owned components
    for tp in report.team_profiles:
        assert len(tp.owned_components) > 0


def test_analyze_custom_team_mapping():
    """Custom team mapping should override auto-assignment."""
    graph = _build_test_graph()
    model = CostModel(revenue_per_hour=10_000)
    engine = CostAttributionEngine()

    team_mapping = {
        "lb-main": "sre",
        "api-server": "sre",
        "db-primary": "dba",
        "redis-cache": "dba",
    }

    report = engine.analyze(graph, model, team_mapping=team_mapping)

    team_names = {tp.team_name for tp in report.team_profiles}
    assert "sre" in team_names
    assert "dba" in team_names


def test_analyze_top_risk_components():
    """Top risk components should contain at most 5 entries."""
    graph = _build_test_graph()
    model = CostModel(revenue_per_hour=10_000)
    engine = CostAttributionEngine()

    report = engine.analyze(graph, model)

    assert len(report.top_risk_components) <= 5
    assert len(report.top_risk_components) > 0


def test_analyze_cost_reduction_opportunities():
    """Opportunities should be found for components without redundancy."""
    graph = _build_test_graph()
    model = CostModel(revenue_per_hour=10_000)
    engine = CostAttributionEngine()

    report = engine.analyze(graph, model)

    # api-server and db-primary have 1 replica, should have improvement opportunities
    assert len(report.cost_reduction_opportunities) > 0


def test_analyze_budget_allocation():
    """Budget allocation should map team names to amounts."""
    graph = _build_test_graph()
    model = CostModel(revenue_per_hour=10_000)
    engine = CostAttributionEngine()

    report = engine.analyze(graph, model)

    assert len(report.budget_allocation) > 0
    for team_name, amount in report.budget_allocation.items():
        assert isinstance(team_name, str)
        assert amount >= 0


def test_analyze_empty_graph():
    """Empty graph should return empty report."""
    graph = InfraGraph()
    model = CostModel(revenue_per_hour=10_000)
    engine = CostAttributionEngine()

    report = engine.analyze(graph, model)

    assert report.total_annual_risk == 0
    assert len(report.component_profiles) == 0


def test_redundant_graph_lower_risk():
    """Redundant graph should have lower total risk than non-redundant."""
    model = CostModel(revenue_per_hour=10_000)
    engine = CostAttributionEngine()

    basic = engine.analyze(_build_test_graph(), model)
    redundant = engine.analyze(_build_redundant_graph(), model)

    assert redundant.total_annual_risk < basic.total_annual_risk


def test_higher_revenue_higher_risk():
    """Higher revenue should increase total risk proportionally."""
    graph = _build_test_graph()
    engine = CostAttributionEngine()

    low_rev = engine.analyze(graph, CostModel(revenue_per_hour=1_000))
    high_rev = engine.analyze(graph, CostModel(revenue_per_hour=100_000))

    assert high_rev.total_annual_risk > low_rev.total_annual_risk


# ---------------------------------------------------------------------------
# calculate_component_cost tests
# ---------------------------------------------------------------------------

def test_calculate_component_cost():
    """Should return a ComponentCostProfile."""
    graph = _build_test_graph()
    model = CostModel(revenue_per_hour=10_000)
    engine = CostAttributionEngine()

    profile = engine.calculate_component_cost(graph, "api-server", model)

    assert isinstance(profile, ComponentCostProfile)
    assert profile.component_id == "api-server"
    assert profile.direct_cost >= 0
    assert profile.cascade_cost >= profile.direct_cost


def test_calculate_component_cost_nonexistent():
    """Non-existent component should return zero-cost profile."""
    graph = _build_test_graph()
    model = CostModel(revenue_per_hour=10_000)
    engine = CostAttributionEngine()

    profile = engine.calculate_component_cost(graph, "nonexistent", model)

    assert profile.total_annual_risk == 0


def test_cascade_cost_higher_than_direct():
    """Cascade cost should be >= direct cost for components with dependents."""
    graph = _build_test_graph()
    model = CostModel(revenue_per_hour=10_000)
    engine = CostAttributionEngine()

    # db-primary has dependents (api-server depends on it)
    profile = engine.calculate_component_cost(graph, "db-primary", model)

    assert profile.cascade_cost >= profile.direct_cost


# ---------------------------------------------------------------------------
# get_roi_ranking tests
# ---------------------------------------------------------------------------

def test_get_roi_ranking():
    """ROI ranking should return sorted tuples."""
    graph = _build_test_graph()
    model = CostModel(revenue_per_hour=10_000)
    engine = CostAttributionEngine()

    ranking = engine.get_roi_ranking(graph, model)

    assert isinstance(ranking, list)
    if len(ranking) > 1:
        # Should be sorted by ROI descending
        rois = [r[1] for r in ranking]
        assert rois == sorted(rois, reverse=True)


# ---------------------------------------------------------------------------
# estimate_improvement_savings tests
# ---------------------------------------------------------------------------

def test_estimate_improvement_savings():
    """Improvement savings should be positive for single-replica components."""
    graph = _build_test_graph()
    model = CostModel(revenue_per_hour=10_000)
    engine = CostAttributionEngine()

    savings = engine.estimate_improvement_savings(
        graph, model, ["api-server", "db-primary"],
    )

    assert savings > 0


def test_estimate_improvement_savings_empty():
    """Empty changes list should return zero savings."""
    graph = _build_test_graph()
    model = CostModel(revenue_per_hour=10_000)
    engine = CostAttributionEngine()

    savings = engine.estimate_improvement_savings(graph, model, [])

    assert savings == 0.0


def test_estimate_improvement_savings_nonexistent():
    """Non-existent component should not contribute savings."""
    graph = _build_test_graph()
    model = CostModel(revenue_per_hour=10_000)
    engine = CostAttributionEngine()

    savings = engine.estimate_improvement_savings(
        graph, model, ["nonexistent"],
    )

    assert savings == 0.0


# ---------------------------------------------------------------------------
# Team risk profile tests
# ---------------------------------------------------------------------------

def test_team_profiles_have_budget():
    """Each team profile should have a recommended budget."""
    graph = _build_test_graph()
    model = CostModel(revenue_per_hour=10_000)
    engine = CostAttributionEngine()

    report = engine.analyze(graph, model)

    for tp in report.team_profiles:
        assert tp.recommended_budget >= 0
        assert tp.highest_risk_component != ""


def test_team_percentage_sums_to_100():
    """Team risk percentages should approximately sum to 100%."""
    graph = _build_test_graph()
    model = CostModel(revenue_per_hour=10_000)
    engine = CostAttributionEngine()

    report = engine.analyze(graph, model)

    total_pct = sum(tp.percentage_of_total_risk for tp in report.team_profiles)
    assert abs(total_pct - 100.0) < 1.0


# ---------------------------------------------------------------------------
# Edge-case tests for full coverage
# ---------------------------------------------------------------------------

def test_estimate_traffic_fraction_empty_graph():
    """Empty graph (0 components) should return 0.0 traffic fraction."""
    graph = InfraGraph()
    # We need the component_id to exist in the graph's networkx structure
    # but the components dict is empty, so total == 0 triggers line 202.
    assert _estimate_traffic_fraction(graph, "anything") == 0.0


def test_estimate_traffic_fraction_isolated_component():
    """Isolated component (no dependents, no dependencies) returns 1/total."""
    graph = InfraGraph()
    # Add two isolated components (no edges between them)
    graph.add_component(Component(
        id="isolated-a", name="Isolated A", type=ComponentType.APP_SERVER,
        replicas=1,
    ))
    graph.add_component(Component(
        id="isolated-b", name="Isolated B", type=ComponentType.APP_SERVER,
        replicas=1,
    ))
    # "isolated-a" has no dependents and no dependencies -> 1.0 / 2 = 0.5
    frac = _estimate_traffic_fraction(graph, "isolated-a")
    assert frac == 1.0 / 2


def test_calculate_component_cost_cascade_with_phantom_affected():
    """Cascade loop should skip affected components not in graph (line 363).

    Uses mock to make get_all_affected return an ID for which
    get_component returns None, triggering the continue branch.
    """
    graph = InfraGraph()
    graph.add_component(Component(
        id="api-server", name="API", type=ComponentType.APP_SERVER,
        replicas=1,
    ))
    model = CostModel(revenue_per_hour=10_000)
    engine = CostAttributionEngine()

    # Patch get_all_affected to return a set including a phantom ID
    with patch.object(graph, "get_all_affected", return_value={"phantom-node"}):
        profile = engine.calculate_component_cost(graph, "api-server", model)

    assert profile.component_id == "api-server"
    # phantom-node is skipped (continue), so cascade_multiplier stays 1.0
    # meaning cascade_cost == direct_cost
    assert profile.cascade_cost == profile.direct_cost


def test_get_component_risk_not_found():
    """_get_component_risk should return 0.0 for unknown component (line 538)."""
    engine = CostAttributionEngine()
    profiles = [
        ComponentCostProfile(
            component_id="known",
            component_name="Known",
            owner_team="platform",
            annual_failure_probability=0.5,
            estimated_downtime_hours=1.0,
            direct_cost=1000.0,
            cascade_cost=2000.0,
            total_annual_risk=5000.0,
            percentage_of_total_risk=100.0,
            improvement_roi=1.0,
        ),
    ]
    assert engine._get_component_risk(profiles, "unknown-comp") == 0.0


def test_find_opportunities_skips_missing_component():
    """_find_opportunities should skip components not in graph (line 555)."""
    engine = CostAttributionEngine()
    graph = InfraGraph()
    model = CostModel(revenue_per_hour=10_000)

    # Create a profile for a component that does NOT exist in the graph
    profiles = [
        ComponentCostProfile(
            component_id="ghost",
            component_name="Ghost",
            owner_team="platform",
            annual_failure_probability=0.9,
            estimated_downtime_hours=2.0,
            direct_cost=5000.0,
            cascade_cost=10000.0,
            total_annual_risk=50000.0,
            percentage_of_total_risk=100.0,
            improvement_roi=5.0,
        ),
    ]
    opportunities = engine._find_opportunities(graph, profiles, model)
    # ghost is not in graph -> continue -> no opportunities generated for it
    assert all(opp[0] != "ghost" for opp in opportunities)


def test_find_opportunities_failover_recommendation():
    """Components with 2+ replicas but no failover should get failover recommendation (line 571)."""
    graph = InfraGraph()
    # Component with 2 replicas but no failover enabled
    graph.add_component(Component(
        id="app-nofailover", name="App No Failover", type=ComponentType.APP_SERVER,
        replicas=2, failover=FailoverConfig(enabled=False),
    ))
    model = CostModel(revenue_per_hour=10_000)
    engine = CostAttributionEngine()

    report = engine.analyze(graph, model)

    # Find the failover recommendation in opportunities
    failover_opps = [
        opp for opp in report.cost_reduction_opportunities
        if "Enable failover" in opp[2]
    ]
    assert len(failover_opps) > 0
    assert failover_opps[0][0] == "app-nofailover"
