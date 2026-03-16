"""Tests for the Infrastructure Cost Optimizer."""

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
    OperationalProfile,
    RegionConfig,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.infrastructure_cost_optimizer import (
    COMPUTE_COST_PER_REPLICA,
    IDLE_UTILIZATION_THRESHOLD,
    LICENSING_COST_PER_REPLICA,
    MULTI_AZ_PREMIUM_PERCENT,
    NETWORK_COST_PER_REPLICA,
    OPERATIONAL_COST_PER_COMPONENT,
    RESERVED_1YR_DISCOUNT,
    RESERVED_3YR_DISCOUNT,
    RIGHTSIZE_UTILIZATION_THRESHOLD,
    SPOT_DISCOUNT_RATE,
    STORAGE_COST_PER_REPLICA,
    ComponentCostBreakdown,
    CostAllocation,
    CostAnomalyThreshold,
    CostCategory,
    CostRecommendation,
    IdleResource,
    InfrastructureCostOptimizer,
    InfrastructureCostReport,
    MultiAZCostAnalysis,
    PricingModel,
    RecommendationType,
    RedundancyCostAnalysis,
    ReservedInstanceAnalysis,
    ResilienceChangeCostImpact,
    RiskLevel,
    SavingsPlanRecommendation,
    SpotOpportunity,
    TCOAnalysis,
    compute_component_cost,
    compute_graph_cost,
    _is_stateless,
    _is_stateful,
)


# ---------------------------------------------------------------------------
# Helpers — match the pattern from the spec
# ---------------------------------------------------------------------------


def _comp(cid="c1", ctype=ComponentType.APP_SERVER, **kwargs):
    """Create a Component with sensible defaults."""
    defaults = dict(
        id=cid,
        name=cid,
        type=ctype,
        replicas=kwargs.pop("replicas", 1),
    )
    # Support shorthand for common nested configs
    cpu = kwargs.pop("cpu", 0.0)
    mem = kwargs.pop("mem", 0.0)
    disk = kwargs.pop("disk", 0.0)
    autoscaling = kwargs.pop("autoscaling", False)
    failover = kwargs.pop("failover", False)
    az = kwargs.pop("az", "")
    revenue = kwargs.pop("revenue_per_minute", 0.0)
    mtbf = kwargs.pop("mtbf_hours", 0.0)
    mttr = kwargs.pop("mttr_minutes", 30.0)

    defaults["metrics"] = ResourceMetrics(
        cpu_percent=cpu, memory_percent=mem, disk_percent=disk
    )
    defaults["autoscaling"] = AutoScalingConfig(enabled=autoscaling)
    defaults["failover"] = FailoverConfig(enabled=failover)
    if az:
        defaults["region"] = RegionConfig(availability_zone=az)
    if revenue > 0:
        defaults["cost_profile"] = CostProfile(revenue_per_minute=revenue)
    if mtbf > 0:
        defaults["operational_profile"] = OperationalProfile(
            mtbf_hours=mtbf, mttr_minutes=mttr
        )
    defaults.update(kwargs)
    return Component(**defaults)


def _graph(*comps):
    """Build an InfraGraph from a sequence of Components."""
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


# ---------------------------------------------------------------------------
# Pre-built graph fixtures
# ---------------------------------------------------------------------------


def _simple_graph():
    """lb -> app -> db, basic topology."""
    g = _graph(
        _comp("lb", ComponentType.LOAD_BALANCER, replicas=2),
        _comp("app", ComponentType.APP_SERVER, replicas=3, autoscaling=True),
        _comp("db", ComponentType.DATABASE, replicas=2, failover=True),
    )
    g.add_dependency(Dependency(source_id="lb", target_id="app"))
    g.add_dependency(Dependency(source_id="app", target_id="db"))
    return g


def _idle_graph():
    """Graph with idle components (near-zero utilization)."""
    g = _graph(
        _comp("app", ComponentType.APP_SERVER, replicas=2, cpu=1.0, mem=1.0),
        _comp("orphan", ComponentType.APP_SERVER, replicas=1, cpu=0.0, mem=0.0),
    )
    g.add_dependency(Dependency(source_id="app", target_id="orphan"))
    return g


def _high_util_graph():
    """Graph with high utilization components."""
    return _graph(
        _comp("app", ComponentType.APP_SERVER, replicas=2, cpu=85.0, mem=75.0),
        _comp("db", ComponentType.DATABASE, replicas=2, cpu=70.0, mem=60.0),
    )


# ===========================================================================
# Tests: Enums and constants
# ===========================================================================


class TestEnumsAndConstants:
    def test_cost_category_values(self):
        assert CostCategory.COMPUTE.value == "compute"
        assert CostCategory.STORAGE.value == "storage"
        assert CostCategory.NETWORK.value == "network"
        assert CostCategory.LICENSING.value == "licensing"
        assert CostCategory.OPERATIONAL.value == "operational"

    def test_pricing_model_values(self):
        assert PricingModel.ON_DEMAND.value == "on_demand"
        assert PricingModel.SPOT.value == "spot"
        assert PricingModel.RESERVED_1YR.value == "reserved_1yr"
        assert PricingModel.RESERVED_3YR.value == "reserved_3yr"

    def test_recommendation_type_values(self):
        assert RecommendationType.RIGHT_SIZE.value == "right_size"
        assert RecommendationType.SPOT_OPPORTUNITY.value == "spot_opportunity"
        assert RecommendationType.IDLE_RESOURCE.value == "idle_resource"
        assert RecommendationType.REDUNDANCY_REDUCTION.value == "redundancy_reduction"

    def test_risk_level_values(self):
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"

    def test_compute_cost_per_replica_all_types(self):
        for ct in ComponentType:
            assert ct in COMPUTE_COST_PER_REPLICA

    def test_storage_cost_per_replica_all_types(self):
        for ct in ComponentType:
            assert ct in STORAGE_COST_PER_REPLICA

    def test_network_cost_per_replica_all_types(self):
        for ct in ComponentType:
            assert ct in NETWORK_COST_PER_REPLICA

    def test_licensing_cost_per_replica_all_types(self):
        for ct in ComponentType:
            assert ct in LICENSING_COST_PER_REPLICA


# ===========================================================================
# Tests: Helper functions
# ===========================================================================


class TestHelperFunctions:
    def test_is_stateless_app_server(self):
        assert _is_stateless(ComponentType.APP_SERVER) is True

    def test_is_stateless_web_server(self):
        assert _is_stateless(ComponentType.WEB_SERVER) is True

    def test_is_stateless_load_balancer(self):
        assert _is_stateless(ComponentType.LOAD_BALANCER) is True

    def test_is_stateless_database_false(self):
        assert _is_stateless(ComponentType.DATABASE) is False

    def test_is_stateful_database(self):
        assert _is_stateful(ComponentType.DATABASE) is True

    def test_is_stateful_cache(self):
        assert _is_stateful(ComponentType.CACHE) is True

    def test_is_stateful_storage(self):
        assert _is_stateful(ComponentType.STORAGE) is True

    def test_is_stateful_app_server_false(self):
        assert _is_stateful(ComponentType.APP_SERVER) is False


# ===========================================================================
# Tests: compute_component_cost
# ===========================================================================


class TestComputeComponentCost:
    def test_returns_breakdown(self):
        comp = _comp("app", ComponentType.APP_SERVER, replicas=2)
        b = compute_component_cost(comp)
        assert isinstance(b, ComponentCostBreakdown)

    def test_compute_cost_matches_constant(self):
        comp = _comp("app", ComponentType.APP_SERVER, replicas=3)
        b = compute_component_cost(comp)
        expected = COMPUTE_COST_PER_REPLICA[ComponentType.APP_SERVER] * 3
        assert b.compute_cost == expected

    def test_storage_cost_matches_constant(self):
        comp = _comp("db", ComponentType.DATABASE, replicas=2)
        b = compute_component_cost(comp)
        expected = STORAGE_COST_PER_REPLICA[ComponentType.DATABASE] * 2
        assert b.storage_cost == expected

    def test_network_cost_matches_constant(self):
        comp = _comp("lb", ComponentType.LOAD_BALANCER, replicas=1)
        b = compute_component_cost(comp)
        expected = NETWORK_COST_PER_REPLICA[ComponentType.LOAD_BALANCER] * 1
        assert b.network_cost == expected

    def test_licensing_cost_for_database(self):
        comp = _comp("db", ComponentType.DATABASE, replicas=2)
        b = compute_component_cost(comp)
        expected = LICENSING_COST_PER_REPLICA[ComponentType.DATABASE] * 2
        assert b.licensing_cost == expected

    def test_licensing_cost_zero_for_app_server(self):
        comp = _comp("app", ComponentType.APP_SERVER, replicas=3)
        b = compute_component_cost(comp)
        assert b.licensing_cost == 0.0

    def test_operational_cost_fixed(self):
        comp = _comp("app", ComponentType.APP_SERVER)
        b = compute_component_cost(comp)
        assert b.operational_cost == OPERATIONAL_COST_PER_COMPONENT

    def test_total_is_sum_of_parts(self):
        comp = _comp("db", ComponentType.DATABASE, replicas=2)
        b = compute_component_cost(comp)
        expected = (
            b.compute_cost + b.storage_cost + b.network_cost
            + b.licensing_cost + b.operational_cost
        )
        assert abs(b.total_cost - expected) < 0.01

    def test_utilization_reflected(self):
        comp = _comp("app", ComponentType.APP_SERVER, cpu=75.0)
        b = compute_component_cost(comp)
        assert b.utilization_percent == 75.0

    def test_external_api_zero_cost(self):
        comp = _comp("ext", ComponentType.EXTERNAL_API)
        b = compute_component_cost(comp)
        # Only operational cost should be non-zero
        assert b.compute_cost == 0.0
        assert b.storage_cost == 0.0
        assert b.network_cost == 0.0

    def test_cost_per_request_computed(self):
        comp = _comp("app", ComponentType.APP_SERVER, replicas=2)
        b = compute_component_cost(comp)
        assert b.cost_per_request >= 0.0


# ===========================================================================
# Tests: compute_graph_cost
# ===========================================================================


class TestComputeGraphCost:
    def test_empty_graph(self):
        g = _graph()
        assert compute_graph_cost(g) == 0.0

    def test_single_component(self):
        comp = _comp("app", ComponentType.APP_SERVER)
        g = _graph(comp)
        cost = compute_graph_cost(g)
        expected = compute_component_cost(comp).total_cost
        assert cost == expected

    def test_multi_component_sum(self):
        c1 = _comp("app", ComponentType.APP_SERVER)
        c2 = _comp("db", ComponentType.DATABASE)
        g = _graph(c1, c2)
        cost = compute_graph_cost(g)
        expected = (
            compute_component_cost(c1).total_cost
            + compute_component_cost(c2).total_cost
        )
        assert cost == expected


# ===========================================================================
# Tests: InfrastructureCostOptimizer.analyze()
# ===========================================================================


class TestAnalyze:
    def test_returns_report(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        assert isinstance(report, InfrastructureCostReport)

    def test_generated_at_present(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        assert len(report.generated_at) > 0

    def test_total_monthly_cost_positive(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        assert report.total_monthly_cost > 0

    def test_annual_cost_is_12x_monthly(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        assert abs(report.total_annual_cost - report.total_monthly_cost * 12) < 0.01

    def test_breakdowns_for_all_components(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        cids = {b.component_id for b in report.cost_breakdowns}
        assert cids == {"lb", "app", "db"}

    def test_cost_by_category_has_all_categories(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        for cat in CostCategory:
            assert cat.value in report.cost_by_category

    def test_savings_percent_bounded(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        assert 0 <= report.savings_percent <= 100

    def test_empty_graph_report(self):
        g = _graph()
        report = InfrastructureCostOptimizer(g).analyze()
        assert report.total_monthly_cost == 0.0
        assert report.total_annual_cost == 0.0
        assert len(report.cost_breakdowns) == 0
        assert report.savings_plan is None


# ===========================================================================
# Tests: Cost allocations (per team/service)
# ===========================================================================


class TestCostAllocations:
    def test_no_allocations_without_team_config(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        assert report.cost_allocations == []

    def test_allocations_computed_with_config(self):
        g = _simple_graph()
        teams = {"backend": ["app", "db"], "infra": ["lb"]}
        report = InfrastructureCostOptimizer(g, team_allocations=teams).analyze()
        assert len(report.cost_allocations) == 2

    def test_allocation_percent_sums_to_100(self):
        g = _simple_graph()
        teams = {"backend": ["app", "db"], "infra": ["lb"]}
        report = InfrastructureCostOptimizer(g, team_allocations=teams).analyze()
        total_pct = sum(a.percent_of_total for a in report.cost_allocations)
        assert abs(total_pct - 100.0) < 1.0

    def test_allocation_sorted_by_cost_descending(self):
        g = _simple_graph()
        teams = {"backend": ["app", "db"], "infra": ["lb"]}
        report = InfrastructureCostOptimizer(g, team_allocations=teams).analyze()
        costs = [a.total_cost for a in report.cost_allocations]
        assert costs == sorted(costs, reverse=True)

    def test_allocation_with_unknown_component(self):
        g = _simple_graph()
        teams = {"team_a": ["nonexistent"]}
        report = InfrastructureCostOptimizer(g, team_allocations=teams).analyze()
        assert report.cost_allocations[0].total_cost == 0.0


# ===========================================================================
# Tests: Spot instance opportunities
# ===========================================================================


class TestSpotOpportunities:
    def test_stateless_multi_replica_eligible(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, replicas=3, autoscaling=True))
        report = InfrastructureCostOptimizer(g).analyze()
        assert len(report.spot_opportunities) == 1
        assert report.spot_opportunities[0].is_stateless is True

    def test_stateful_excluded(self):
        g = _graph(_comp("db", ComponentType.DATABASE, replicas=3))
        report = InfrastructureCostOptimizer(g).analyze()
        assert len(report.spot_opportunities) == 0

    def test_single_replica_excluded(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, replicas=1))
        report = InfrastructureCostOptimizer(g).analyze()
        assert len(report.spot_opportunities) == 0

    def test_savings_positive(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, replicas=4))
        report = InfrastructureCostOptimizer(g).analyze()
        for opp in report.spot_opportunities:
            assert opp.monthly_savings > 0

    def test_autoscaling_reduces_risk(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, replicas=3, autoscaling=True))
        report = InfrastructureCostOptimizer(g).analyze()
        assert report.spot_opportunities[0].interruption_risk == "low"

    def test_no_autoscaling_higher_risk(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, replicas=2))
        report = InfrastructureCostOptimizer(g).analyze()
        assert report.spot_opportunities[0].interruption_risk == "high"

    def test_sorted_by_savings(self):
        g = _graph(
            _comp("app1", ComponentType.APP_SERVER, replicas=4),
            _comp("app2", ComponentType.WEB_SERVER, replicas=2),
        )
        report = InfrastructureCostOptimizer(g).analyze()
        savings = [o.monthly_savings for o in report.spot_opportunities]
        assert savings == sorted(savings, reverse=True)


# ===========================================================================
# Tests: Reserved instance analysis
# ===========================================================================


class TestReservedInstanceAnalysis:
    def test_analysis_for_each_component_with_compute(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        assert len(report.reserved_analyses) == 3  # lb, app, db

    def test_reserved_cheaper_than_on_demand(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        for ra in report.reserved_analyses:
            assert ra.reserved_1yr_monthly <= ra.on_demand_monthly
            assert ra.reserved_3yr_monthly <= ra.on_demand_monthly

    def test_3yr_cheaper_than_1yr(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        for ra in report.reserved_analyses:
            assert ra.reserved_3yr_monthly <= ra.reserved_1yr_monthly

    def test_savings_positive(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        for ra in report.reserved_analyses:
            assert ra.savings_1yr_monthly >= 0
            assert ra.savings_3yr_monthly >= 0

    def test_recommendation_on_demand_for_low_util(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, cpu=5.0))
        report = InfrastructureCostOptimizer(g).analyze()
        assert report.reserved_analyses[0].recommendation == "on_demand"

    def test_recommendation_reserved_for_high_util(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, cpu=80.0))
        report = InfrastructureCostOptimizer(g).analyze()
        assert report.reserved_analyses[0].recommendation == "reserved_3yr"

    def test_external_api_excluded(self):
        g = _graph(_comp("ext", ComponentType.EXTERNAL_API))
        report = InfrastructureCostOptimizer(g).analyze()
        # External API has 0 compute cost, so excluded
        assert len(report.reserved_analyses) == 0


# ===========================================================================
# Tests: Redundancy cost analysis
# ===========================================================================


class TestRedundancyCostAnalysis:
    def test_analysis_for_all_components(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        cids = {r.component_id for r in report.redundancy_analyses}
        assert cids == {"lb", "app", "db"}

    def test_single_replica_critical_with_dependents(self):
        g = _graph(
            _comp("db", ComponentType.DATABASE, replicas=1),
            _comp("app", ComponentType.APP_SERVER),
        )
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        report = InfrastructureCostOptimizer(g).analyze()
        db_analysis = [r for r in report.redundancy_analyses if r.component_id == "db"]
        assert db_analysis[0].risk_without_redundancy == "critical"

    def test_single_replica_high_without_dependents(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, replicas=1))
        report = InfrastructureCostOptimizer(g).analyze()
        assert report.redundancy_analyses[0].risk_without_redundancy == "high"

    def test_redundancy_cost_positive(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, replicas=3))
        report = InfrastructureCostOptimizer(g).analyze()
        assert report.redundancy_analyses[0].redundancy_cost > 0

    def test_recommendation_maintain_for_critical(self):
        g = _graph(
            _comp("db", ComponentType.DATABASE, replicas=1),
            _comp("app", ComponentType.APP_SERVER),
        )
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        report = InfrastructureCostOptimizer(g).analyze()
        db_analysis = [r for r in report.redundancy_analyses if r.component_id == "db"]
        assert "maintain" in db_analysis[0].recommendation.lower() or "increase" in db_analysis[0].recommendation.lower()

    def test_recommendation_reduce_for_over_provisioned(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, replicas=5))
        report = InfrastructureCostOptimizer(g).analyze()
        analysis = report.redundancy_analyses[0]
        assert "reduc" in analysis.recommendation.lower() or "appropriate" in analysis.recommendation.lower()


# ===========================================================================
# Tests: Multi-AZ cost analysis
# ===========================================================================


class TestMultiAZAnalysis:
    def test_premium_is_25_percent(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        for ma in report.multi_az_analyses:
            assert ma.premium_percent == MULTI_AZ_PREMIUM_PERCENT

    def test_multi_az_cost_higher(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        for ma in report.multi_az_analyses:
            assert ma.multi_az_cost > ma.single_az_cost

    def test_stateful_high_benefit(self):
        g = _graph(
            _comp("db", ComponentType.DATABASE, replicas=2),
            _comp("app", ComponentType.APP_SERVER),
        )
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        report = InfrastructureCostOptimizer(g).analyze()
        db_analysis = [m for m in report.multi_az_analyses if m.component_id == "db"]
        assert db_analysis[0].availability_benefit == "high"
        assert db_analysis[0].is_stateful is True

    def test_stateless_low_benefit(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER))
        report = InfrastructureCostOptimizer(g).analyze()
        assert report.multi_az_analyses[0].availability_benefit == "low"

    def test_external_api_low_benefit(self):
        g = _graph(_comp("ext", ComponentType.EXTERNAL_API))
        report = InfrastructureCostOptimizer(g).analyze()
        # External API is stateless with no dependents -> low benefit
        ext_analysis = [m for m in report.multi_az_analyses if m.component_id == "ext"]
        if ext_analysis:
            assert ext_analysis[0].availability_benefit == "low"


# ===========================================================================
# Tests: Idle resource detection
# ===========================================================================


class TestIdleResourceDetection:
    def test_idle_detected(self):
        g = _graph(_comp("idle", ComponentType.APP_SERVER, cpu=0.0, mem=0.0))
        report = InfrastructureCostOptimizer(g).analyze()
        assert len(report.idle_resources) == 1
        assert report.idle_resources[0].component_id == "idle"

    def test_active_not_detected(self):
        g = _graph(_comp("active", ComponentType.APP_SERVER, cpu=50.0))
        report = InfrastructureCostOptimizer(g).analyze()
        assert len(report.idle_resources) == 0

    def test_idle_with_history(self):
        g = _graph(_comp("idle", ComponentType.APP_SERVER, cpu=0.0))
        history = [("idle", 1.0), ("idle", 2.0), ("idle", 0.5)]
        report = InfrastructureCostOptimizer(g, utilization_history=history).analyze()
        assert len(report.idle_resources) == 1
        assert "extended" in report.idle_resources[0].idle_since_estimate

    def test_idle_with_mixed_history(self):
        g = _graph(_comp("idle", ComponentType.APP_SERVER, cpu=0.0))
        history = [("idle", 1.0), ("idle", 50.0), ("idle", 0.5)]
        report = InfrastructureCostOptimizer(g, utilization_history=history).analyze()
        assert "recent" in report.idle_resources[0].idle_since_estimate

    def test_idle_sorted_by_cost(self):
        g = _graph(
            _comp("cheap", ComponentType.DNS, cpu=0.0),
            _comp("expensive", ComponentType.DATABASE, cpu=0.0),
        )
        report = InfrastructureCostOptimizer(g).analyze()
        if len(report.idle_resources) >= 2:
            costs = [r.monthly_cost for r in report.idle_resources]
            assert costs == sorted(costs, reverse=True)

    def test_external_api_idle_has_recommendation(self):
        g = _graph(_comp("ext", ComponentType.EXTERNAL_API, cpu=0.0))
        report = InfrastructureCostOptimizer(g).analyze()
        # External API has operational cost, so it appears in idle detection
        idle_ext = [r for r in report.idle_resources if r.component_id == "ext"]
        if idle_ext:
            assert "decommission" in idle_ext[0].recommendation.lower()


# ===========================================================================
# Tests: Cost anomaly thresholds
# ===========================================================================


class TestCostAnomalyThresholds:
    def test_thresholds_for_all_components(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        cids = {t.component_id for t in report.anomaly_thresholds}
        assert cids == {"lb", "app", "db"}

    def test_warning_less_than_critical(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        for t in report.anomaly_thresholds:
            assert t.warning_threshold <= t.critical_threshold

    def test_not_anomalous_at_baseline(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        for t in report.anomaly_thresholds:
            # Without cost history, current cost equals baseline
            assert t.is_anomalous is False

    def test_anomalous_with_history(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, replicas=1))
        # Cost history with much lower values
        history = [("app", 10.0), ("app", 12.0), ("app", 11.0)]
        report = InfrastructureCostOptimizer(g, cost_history=history).analyze()
        app_t = [t for t in report.anomaly_thresholds if t.component_id == "app"]
        assert len(app_t) == 1
        # Current cost is much higher than historical baseline, should be anomalous
        assert app_t[0].is_anomalous is True

    def test_deviation_percent_computed(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        for t in report.anomaly_thresholds:
            assert isinstance(t.deviation_percent, float)


# ===========================================================================
# Tests: Savings plan recommendation
# ===========================================================================


class TestSavingsPlan:
    def test_savings_plan_present(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        assert report.savings_plan is not None

    def test_savings_plan_none_for_empty_graph(self):
        g = _graph()
        report = InfrastructureCostOptimizer(g).analyze()
        assert report.savings_plan is None

    def test_estimated_savings_positive(self):
        g = _graph(
            _comp("app", ComponentType.APP_SERVER, replicas=3, cpu=50.0),
            _comp("db", ComponentType.DATABASE, replicas=2, cpu=60.0),
        )
        report = InfrastructureCostOptimizer(g).analyze()
        assert report.savings_plan is not None
        assert report.savings_plan.estimated_savings >= 0

    def test_coverage_percent_bounded(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        sp = report.savings_plan
        assert sp is not None
        assert 0 <= sp.coverage_percent <= 100

    def test_term_recommendation_3yr_for_high_coverage(self):
        g = _graph(
            _comp("app", ComponentType.APP_SERVER, replicas=3, cpu=80.0),
            _comp("db", ComponentType.DATABASE, replicas=2, cpu=75.0),
        )
        report = InfrastructureCostOptimizer(g).analyze()
        sp = report.savings_plan
        assert sp is not None
        if sp.coverage_percent >= 70:
            assert sp.recommended_term == "3yr"


# ===========================================================================
# Tests: TCO analysis
# ===========================================================================


class TestTCOAnalysis:
    def test_tco_present(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        assert report.tco is not None

    def test_tco_total_includes_all_parts(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        tco = report.tco
        assert tco is not None
        expected = (
            tco.infrastructure_cost + tco.operational_cost
            + tco.licensing_cost + tco.personnel_cost + tco.downtime_cost
        )
        assert abs(tco.total_tco - expected) < 0.01

    def test_annual_tco_is_12x(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        tco = report.tco
        assert tco is not None
        assert abs(tco.annual_tco - tco.total_tco * 12) < 0.01

    def test_tco_per_component(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        tco = report.tco
        assert tco is not None
        expected_per = tco.total_tco / 3  # 3 components
        assert abs(tco.tco_per_component - expected_per) < 0.01

    def test_downtime_cost_with_revenue(self):
        g = _graph(
            _comp(
                "app", ComponentType.APP_SERVER,
                replicas=2, revenue_per_minute=100.0,
                mtbf_hours=720.0, mttr_minutes=30.0,
            )
        )
        report = InfrastructureCostOptimizer(g).analyze()
        tco = report.tco
        assert tco is not None
        assert tco.downtime_cost > 0

    def test_downtime_cost_zero_without_revenue(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        tco = report.tco
        assert tco is not None
        assert tco.downtime_cost == 0.0

    def test_personnel_cost_scales_with_components(self):
        g1 = _graph(_comp("a", ComponentType.APP_SERVER))
        g2 = _graph(
            *[_comp(f"c{i}", ComponentType.APP_SERVER) for i in range(15)]
        )
        r1 = InfrastructureCostOptimizer(g1).analyze()
        r2 = InfrastructureCostOptimizer(g2).analyze()
        assert r2.tco.personnel_cost > r1.tco.personnel_cost


# ===========================================================================
# Tests: Resilience cost impact
# ===========================================================================


class TestResilienceCostImpact:
    def test_impacts_generated(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        assert len(report.resilience_cost_impacts) > 0

    def test_impact_has_cost_delta(self):
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        for impact in report.resilience_cost_impacts:
            assert isinstance(impact.cost_delta, float)

    def test_adding_replica_increases_cost(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, replicas=2))
        opt = InfrastructureCostOptimizer(g)
        impact = opt.estimate_resilience_change_cost("app", additional_replicas=1)
        assert impact is not None
        assert impact.cost_delta > 0

    def test_removing_replica_decreases_cost(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, replicas=3))
        opt = InfrastructureCostOptimizer(g)
        impact = opt.estimate_resilience_change_cost("app", additional_replicas=-1)
        assert impact is not None
        assert impact.cost_delta < 0

    def test_enable_multi_az_increases_cost(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, replicas=2))
        opt = InfrastructureCostOptimizer(g)
        impact = opt.estimate_resilience_change_cost("app", enable_multi_az=True)
        assert impact is not None
        assert impact.cost_delta > 0

    def test_nonexistent_component_returns_none(self):
        g = _simple_graph()
        opt = InfrastructureCostOptimizer(g)
        impact = opt.estimate_resilience_change_cost("ghost", additional_replicas=1)
        assert impact is None

    def test_no_change_zero_delta(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER))
        opt = InfrastructureCostOptimizer(g)
        impact = opt.estimate_resilience_change_cost("app")
        assert impact is not None
        assert impact.cost_delta == 0.0

    def test_cost_per_resilience_point(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, replicas=1))
        opt = InfrastructureCostOptimizer(g)
        impact = opt.estimate_resilience_change_cost("app", additional_replicas=1)
        assert impact is not None
        # cost_per_resilience_point should be computed
        assert isinstance(impact.cost_per_resilience_point, float)

    def test_change_description_format(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, replicas=2))
        opt = InfrastructureCostOptimizer(g)
        impact = opt.estimate_resilience_change_cost(
            "app", additional_replicas=1, enable_failover=True
        )
        assert impact is not None
        assert "app" in impact.change_description
        assert "add" in impact.change_description
        assert "failover" in impact.change_description


# ===========================================================================
# Tests: Recommendations (right-sizing, idle cleanup, redundancy reduction)
# ===========================================================================


class TestRecommendations:
    def test_right_sizing_for_low_util(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, replicas=2, cpu=10.0))
        report = InfrastructureCostOptimizer(g).analyze()
        right_size = [
            r for r in report.recommendations
            if r.recommendation_type == RecommendationType.RIGHT_SIZE.value
        ]
        assert len(right_size) >= 1

    def test_no_right_sizing_for_high_util(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, replicas=2, cpu=80.0))
        report = InfrastructureCostOptimizer(g).analyze()
        right_size = [
            r for r in report.recommendations
            if r.recommendation_type == RecommendationType.RIGHT_SIZE.value
        ]
        assert len(right_size) == 0

    def test_idle_cleanup_for_no_dependents(self):
        g = _graph(_comp("orphan", ComponentType.APP_SERVER, cpu=0.0, mem=0.0))
        report = InfrastructureCostOptimizer(g).analyze()
        idle = [
            r for r in report.recommendations
            if r.recommendation_type == RecommendationType.IDLE_RESOURCE.value
        ]
        assert len(idle) == 1

    def test_no_idle_cleanup_with_dependents(self):
        g = _graph(
            _comp("db", ComponentType.DATABASE, cpu=0.0),
            _comp("app", ComponentType.APP_SERVER),
        )
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        report = InfrastructureCostOptimizer(g).analyze()
        idle = [
            r for r in report.recommendations
            if r.recommendation_type == RecommendationType.IDLE_RESOURCE.value
            and r.component_id == "db"
        ]
        assert len(idle) == 0

    def test_redundancy_reduction_for_multi_replica(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, replicas=4))
        report = InfrastructureCostOptimizer(g).analyze()
        reductions = [
            r for r in report.recommendations
            if r.recommendation_type == RecommendationType.REDUNDANCY_REDUCTION.value
        ]
        assert len(reductions) >= 1

    def test_no_redundancy_reduction_for_2_replicas(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, replicas=2))
        report = InfrastructureCostOptimizer(g).analyze()
        reductions = [
            r for r in report.recommendations
            if r.recommendation_type == RecommendationType.REDUNDANCY_REDUCTION.value
        ]
        assert len(reductions) == 0

    def test_recommendations_sorted_by_savings(self):
        g = _graph(
            _comp("app", ComponentType.APP_SERVER, replicas=5, cpu=5.0),
            _comp("db", ComponentType.DATABASE, replicas=4, cpu=3.0),
        )
        report = InfrastructureCostOptimizer(g).analyze()
        savings = [r.monthly_savings for r in report.recommendations]
        assert savings == sorted(savings, reverse=True)

    def test_annual_savings_is_12x_monthly(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, replicas=4, cpu=10.0))
        report = InfrastructureCostOptimizer(g).analyze()
        for rec in report.recommendations:
            assert abs(rec.annual_savings - rec.monthly_savings * 12) < 0.01

    def test_recommendation_confidence_bounded(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, replicas=3, cpu=5.0))
        report = InfrastructureCostOptimizer(g).analyze()
        for rec in report.recommendations:
            assert 0.0 <= rec.confidence <= 1.0


# ===========================================================================
# Tests: get_cost_breakdown
# ===========================================================================


class TestGetCostBreakdown:
    def test_existing_component(self):
        g = _simple_graph()
        opt = InfrastructureCostOptimizer(g)
        b = opt.get_cost_breakdown("app")
        assert b is not None
        assert b.component_id == "app"

    def test_nonexistent_component(self):
        g = _simple_graph()
        opt = InfrastructureCostOptimizer(g)
        b = opt.get_cost_breakdown("nonexistent")
        assert b is None


# ===========================================================================
# Tests: Edge cases and integration
# ===========================================================================


class TestEdgeCases:
    def test_single_component_graph(self):
        g = _graph(_comp("solo", ComponentType.APP_SERVER))
        report = InfrastructureCostOptimizer(g).analyze()
        assert report.total_monthly_cost > 0
        assert len(report.cost_breakdowns) == 1

    def test_all_component_types(self):
        comps = [
            _comp(ct.value, ct) for ct in ComponentType
        ]
        g = _graph(*comps)
        report = InfrastructureCostOptimizer(g).analyze()
        assert len(report.cost_breakdowns) == len(ComponentType)

    def test_high_replica_count(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, replicas=100))
        report = InfrastructureCostOptimizer(g).analyze()
        assert report.total_monthly_cost > 0

    def test_custom_min_resilience(self):
        g = _simple_graph()
        r_low = InfrastructureCostOptimizer(g, min_resilience_score=0.0).analyze()
        r_high = InfrastructureCostOptimizer(g, min_resilience_score=99.0).analyze()
        # Higher threshold should not produce more savings
        # (some recs may be excluded due to risk)
        assert isinstance(r_low, InfrastructureCostReport)
        assert isinstance(r_high, InfrastructureCostReport)

    def test_resilience_impact_does_not_modify_original(self):
        g = _simple_graph()
        original_replicas = g.get_component("app").replicas
        opt = InfrastructureCostOptimizer(g)
        opt.estimate_resilience_change_cost("app", additional_replicas=5)
        assert g.get_component("app").replicas == original_replicas

    def test_replica_clamp_to_1(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, replicas=2))
        opt = InfrastructureCostOptimizer(g)
        impact = opt.estimate_resilience_change_cost("app", additional_replicas=-10)
        assert impact is not None
        # Should clamp to 1 replica, not go negative
        assert impact.projected_cost > 0

    def test_report_dataclass_fields(self):
        """Verify report has all expected fields."""
        g = _simple_graph()
        report = InfrastructureCostOptimizer(g).analyze()
        assert hasattr(report, "total_monthly_cost")
        assert hasattr(report, "cost_breakdowns")
        assert hasattr(report, "cost_by_category")
        assert hasattr(report, "recommendations")
        assert hasattr(report, "spot_opportunities")
        assert hasattr(report, "reserved_analyses")
        assert hasattr(report, "redundancy_analyses")
        assert hasattr(report, "multi_az_analyses")
        assert hasattr(report, "idle_resources")
        assert hasattr(report, "anomaly_thresholds")
        assert hasattr(report, "savings_plan")
        assert hasattr(report, "tco")
        assert hasattr(report, "resilience_cost_impacts")
        assert hasattr(report, "total_potential_savings")
        assert hasattr(report, "savings_percent")
