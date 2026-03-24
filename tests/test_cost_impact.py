"""Comprehensive tests for Cost Impact Engine.

Covers: CostProfile defaults, CostBreakdown tier classification, total calculation,
calculate_scenario_cost (single/multi component, SLA, cascade, reputation, recs),
calculate_annual_projection (normal, empty, categories, top-5),
calculate_roi (positive, zero/negative, payback), set/get profile, edge cases.
"""
from __future__ import annotations



from faultray.simulator.cost_impact import (
    AnnualCostProjection,
    CostBreakdown,
    CostCategory,
    CostImpactEngine,
    CostProfile,
    CostTier,
    ROIAnalysis,
)


# ── CostProfile defaults ─────────────────────────────────────────────────

class TestCostProfileDefaults:
    def test_default_revenue_per_hour(self):
        p = CostProfile()
        assert p.revenue_per_hour == 0.0

    def test_default_sla_penalty(self):
        p = CostProfile()
        assert p.sla_penalty_per_violation == 0.0

    def test_default_sla_threshold(self):
        p = CostProfile()
        assert p.sla_threshold_minutes == 43.2

    def test_default_recovery_cost(self):
        p = CostProfile()
        assert p.recovery_cost_per_incident == 500.0

    def test_default_engineer_rate(self):
        p = CostProfile()
        assert p.engineer_hourly_rate == 150.0

    def test_default_affected_users(self):
        p = CostProfile()
        assert p.affected_users == 0

    def test_default_reputation_multiplier(self):
        p = CostProfile()
        assert p.reputation_multiplier == 1.0

    def test_custom_profile(self):
        p = CostProfile(
            revenue_per_hour=100_000,
            sla_penalty_per_violation=50_000,
            sla_threshold_minutes=10.0,
            recovery_cost_per_incident=2000,
            engineer_hourly_rate=250,
            affected_users=1_000_000,
            reputation_multiplier=2.5,
        )
        assert p.revenue_per_hour == 100_000
        assert p.sla_penalty_per_violation == 50_000
        assert p.sla_threshold_minutes == 10.0
        assert p.recovery_cost_per_incident == 2000
        assert p.engineer_hourly_rate == 250
        assert p.affected_users == 1_000_000
        assert p.reputation_multiplier == 2.5


# ── CostBreakdown tier classification ─────────────────────────────────────

class TestCostBreakdownTier:
    def test_tier_low(self):
        """Total cost < $1K/hour -> LOW."""
        bd = CostBreakdown(
            scenario_name="low-cost",
            downtime_minutes=60,
            revenue_loss=100,
        )
        assert bd.cost_tier == CostTier.LOW

    def test_tier_medium(self):
        """Total cost $1K-$10K/hour -> MEDIUM."""
        bd = CostBreakdown(
            scenario_name="medium-cost",
            downtime_minutes=60,
            revenue_loss=5_000,
        )
        assert bd.cost_tier == CostTier.MEDIUM

    def test_tier_high(self):
        """Total cost $10K-$100K/hour -> HIGH."""
        bd = CostBreakdown(
            scenario_name="high-cost",
            downtime_minutes=60,
            revenue_loss=50_000,
        )
        assert bd.cost_tier == CostTier.HIGH

    def test_tier_critical(self):
        """Total cost $100K-$1M/hour -> CRITICAL."""
        bd = CostBreakdown(
            scenario_name="critical-cost",
            downtime_minutes=60,
            revenue_loss=500_000,
        )
        assert bd.cost_tier == CostTier.CRITICAL

    def test_tier_catastrophic(self):
        """Total cost >$1M/hour -> CATASTROPHIC."""
        bd = CostBreakdown(
            scenario_name="catastrophic-cost",
            downtime_minutes=60,
            revenue_loss=2_000_000,
        )
        assert bd.cost_tier == CostTier.CATASTROPHIC


# ── CostBreakdown total calculation ───────────────────────────────────────

class TestCostBreakdownTotal:
    def test_total_sums_all_categories(self):
        bd = CostBreakdown(
            scenario_name="total-test",
            downtime_minutes=60,
            revenue_loss=1000,
            sla_penalty=500,
            recovery_cost=200,
            reputation_cost=300,
            productivity_loss=100,
        )
        assert bd.total_cost == 2100

    def test_total_zero_when_all_zero(self):
        bd = CostBreakdown(scenario_name="zero", downtime_minutes=60)
        assert bd.total_cost == 0.0

    def test_total_with_single_category(self):
        bd = CostBreakdown(
            scenario_name="single",
            downtime_minutes=60,
            sla_penalty=10_000,
        )
        assert bd.total_cost == 10_000


# ── CostBreakdown edge: very small downtime ───────────────────────────────

class TestCostBreakdownEdge:
    def test_very_small_downtime_does_not_divide_by_zero(self):
        """downtime_minutes near zero should not cause division by zero."""
        bd = CostBreakdown(
            scenario_name="micro",
            downtime_minutes=0.001,
            revenue_loss=10,
        )
        # Should still get a tier (computed from hourly rate)
        assert bd.cost_tier is not None

    def test_zero_downtime(self):
        """downtime_minutes=0 -> uses max(0/60, 1/60)."""
        bd = CostBreakdown(
            scenario_name="zero-dt",
            downtime_minutes=0,
            revenue_loss=100,
        )
        # hourly = 100 / (1/60) = 6000 -> MEDIUM ($1K-$10K/hour)
        assert bd.cost_tier == CostTier.MEDIUM


# ── Engine: set_component_profile / get_profile ───────────────────────────

class TestEngineProfiles:
    def test_get_default_profile(self):
        engine = CostImpactEngine()
        p = engine.get_profile("unknown-component")
        assert p.revenue_per_hour == 0.0

    def test_get_custom_default_profile(self):
        default = CostProfile(revenue_per_hour=999)
        engine = CostImpactEngine(default_profile=default)
        p = engine.get_profile("any")
        assert p.revenue_per_hour == 999

    def test_set_and_get_component_profile(self):
        engine = CostImpactEngine()
        custom = CostProfile(revenue_per_hour=50_000)
        engine.set_component_profile("api-server", custom)
        assert engine.get_profile("api-server").revenue_per_hour == 50_000

    def test_component_profile_overrides_default(self):
        default = CostProfile(revenue_per_hour=100)
        engine = CostImpactEngine(default_profile=default)
        custom = CostProfile(revenue_per_hour=99_999)
        engine.set_component_profile("db", custom)
        assert engine.get_profile("db").revenue_per_hour == 99_999
        assert engine.get_profile("other").revenue_per_hour == 100

    def test_set_multiple_profiles(self):
        engine = CostImpactEngine()
        engine.set_component_profile("a", CostProfile(revenue_per_hour=10))
        engine.set_component_profile("b", CostProfile(revenue_per_hour=20))
        engine.set_component_profile("c", CostProfile(revenue_per_hour=30))
        assert engine.get_profile("a").revenue_per_hour == 10
        assert engine.get_profile("b").revenue_per_hour == 20
        assert engine.get_profile("c").revenue_per_hour == 30


# ── calculate_scenario_cost: single component ────────────────────────────

class TestScenarioCostSingle:
    def test_revenue_loss_basic(self):
        engine = CostImpactEngine()
        engine.set_component_profile("api", CostProfile(revenue_per_hour=60_000))
        bd = engine.calculate_scenario_cost("outage", ["api"], downtime_minutes=60)
        assert bd.revenue_loss == 60_000.0

    def test_revenue_loss_fractional_hour(self):
        engine = CostImpactEngine()
        engine.set_component_profile("api", CostProfile(revenue_per_hour=60_000))
        bd = engine.calculate_scenario_cost("outage", ["api"], downtime_minutes=30)
        assert bd.revenue_loss == 30_000.0

    def test_no_sla_penalty_under_threshold(self):
        engine = CostImpactEngine()
        engine.set_component_profile("api", CostProfile(
            sla_penalty_per_violation=10_000,
            sla_threshold_minutes=60,
        ))
        bd = engine.calculate_scenario_cost("short", ["api"], downtime_minutes=30)
        assert bd.sla_penalty == 0.0

    def test_sla_penalty_over_threshold(self):
        engine = CostImpactEngine()
        engine.set_component_profile("api", CostProfile(
            sla_penalty_per_violation=10_000,
            sla_threshold_minutes=30,
        ))
        bd = engine.calculate_scenario_cost("long", ["api"], downtime_minutes=60)
        assert bd.sla_penalty == 10_000.0  # ceil(30/30) = 1 violation

    def test_sla_penalty_multiple_violations(self):
        engine = CostImpactEngine()
        engine.set_component_profile("api", CostProfile(
            sla_penalty_per_violation=5_000,
            sla_threshold_minutes=10,
        ))
        # downtime=40, overage=30, violations=ceil(30/10)=3
        bd = engine.calculate_scenario_cost("many", ["api"], downtime_minutes=40)
        assert bd.sla_penalty == 15_000.0

    def test_recovery_cost_cascade_depth_1(self):
        engine = CostImpactEngine()
        engine.set_component_profile("db", CostProfile(recovery_cost_per_incident=1000))
        bd = engine.calculate_scenario_cost("fail", ["db"], downtime_minutes=10, cascade_depth=1)
        assert bd.recovery_cost == 1000.0

    def test_recovery_cost_cascade_depth_3(self):
        engine = CostImpactEngine()
        engine.set_component_profile("db", CostProfile(recovery_cost_per_incident=1000))
        bd = engine.calculate_scenario_cost("cascade", ["db"], downtime_minutes=10, cascade_depth=3)
        assert bd.recovery_cost == 3000.0

    def test_productivity_loss_minimum(self):
        engine = CostImpactEngine()
        engine.set_component_profile("svc", CostProfile(engineer_hourly_rate=200))
        # downtime=10 -> engineer_hours = max(1, 10/30)*1 = 1
        bd = engine.calculate_scenario_cost("small", ["svc"], downtime_minutes=10)
        assert bd.productivity_loss == 200.0

    def test_productivity_loss_scales_with_downtime(self):
        engine = CostImpactEngine()
        engine.set_component_profile("svc", CostProfile(engineer_hourly_rate=150))
        # downtime=120 -> engineer_hours = max(1, 120/30)*1 = 4
        bd = engine.calculate_scenario_cost("long", ["svc"], downtime_minutes=120)
        assert bd.productivity_loss == 600.0

    def test_productivity_loss_scales_with_cascade(self):
        engine = CostImpactEngine()
        engine.set_component_profile("svc", CostProfile(engineer_hourly_rate=150))
        # downtime=120, cascade=2 -> engineer_hours = 4*2 = 8
        bd = engine.calculate_scenario_cost("cascade", ["svc"], downtime_minutes=120, cascade_depth=2)
        assert bd.productivity_loss == 1200.0


# ── calculate_scenario_cost: multiple components ──────────────────────────

class TestScenarioCostMulti:
    def test_revenue_sums_across_components(self):
        engine = CostImpactEngine()
        engine.set_component_profile("a", CostProfile(revenue_per_hour=10_000))
        engine.set_component_profile("b", CostProfile(revenue_per_hour=20_000))
        bd = engine.calculate_scenario_cost("multi", ["a", "b"], downtime_minutes=60)
        assert bd.revenue_loss == 30_000.0

    def test_affected_components_list(self):
        engine = CostImpactEngine()
        bd = engine.calculate_scenario_cost("test", ["x", "y", "z"], downtime_minutes=10)
        assert bd.affected_components == ["x", "y", "z"]

    def test_scenario_name_preserved(self):
        engine = CostImpactEngine()
        bd = engine.calculate_scenario_cost("my-scenario", ["a"], downtime_minutes=10)
        assert bd.scenario_name == "my-scenario"


# ── calculate_scenario_cost: reputation cost ──────────────────────────────

class TestScenarioCostReputation:
    def test_no_reputation_cost_when_no_users(self):
        engine = CostImpactEngine()
        engine.set_component_profile("backend", CostProfile(affected_users=0))
        bd = engine.calculate_scenario_cost("backend-fail", ["backend"], downtime_minutes=60)
        assert bd.reputation_cost == 0.0

    def test_reputation_cost_with_users(self):
        engine = CostImpactEngine()
        engine.set_component_profile("frontend", CostProfile(
            affected_users=10_000,
            reputation_multiplier=1.0,
        ))
        # hours=1, user_impact = min(10000*0.01*1, 50000) = 100
        bd = engine.calculate_scenario_cost("fe-fail", ["frontend"], downtime_minutes=60)
        assert bd.reputation_cost == 100.0

    def test_reputation_cost_with_multiplier(self):
        engine = CostImpactEngine()
        engine.set_component_profile("frontend", CostProfile(
            affected_users=10_000,
            reputation_multiplier=2.0,
        ))
        # user_impact = 100, reputation = 100 * 2.0 = 200
        bd = engine.calculate_scenario_cost("fe-fail", ["frontend"], downtime_minutes=60)
        assert bd.reputation_cost == 200.0

    def test_reputation_cost_capped_at_50k(self):
        engine = CostImpactEngine()
        engine.set_component_profile("big", CostProfile(
            affected_users=100_000_000,
            reputation_multiplier=1.0,
        ))
        # user_impact = min(100M * 0.01 * 1, 50000) = 50000
        bd = engine.calculate_scenario_cost("mega", ["big"], downtime_minutes=60)
        assert bd.reputation_cost == 50_000.0


# ── calculate_scenario_cost: recommendations ──────────────────────────────

class TestScenarioCostRecommendations:
    def test_critical_recommendation_for_catastrophic(self):
        engine = CostImpactEngine()
        engine.set_component_profile("core", CostProfile(revenue_per_hour=2_000_000))
        bd = engine.calculate_scenario_cost("big", ["core"], downtime_minutes=60)
        assert bd.cost_tier in (CostTier.CATASTROPHIC, CostTier.CRITICAL)
        assert any("CRITICAL" in r for r in bd.recommendations)

    def test_sla_recommendation_when_penalty(self):
        engine = CostImpactEngine()
        engine.set_component_profile("svc", CostProfile(
            sla_penalty_per_violation=10_000,
            sla_threshold_minutes=5,
        ))
        bd = engine.calculate_scenario_cost("sla-breach", ["svc"], downtime_minutes=60)
        assert any("SLA exposure" in r for r in bd.recommendations)

    def test_cascade_recommendation_for_deep_cascade(self):
        engine = CostImpactEngine()
        bd = engine.calculate_scenario_cost("cascade", ["a"], downtime_minutes=60, cascade_depth=5)
        assert any("Cascade depth" in r for r in bd.recommendations)

    def test_no_cascade_recommendation_for_shallow(self):
        engine = CostImpactEngine()
        bd = engine.calculate_scenario_cost("shallow", ["a"], downtime_minutes=60, cascade_depth=1)
        assert not any("Cascade depth" in r for r in bd.recommendations)

    def test_no_sla_recommendation_without_penalty(self):
        engine = CostImpactEngine()
        engine.set_component_profile("svc", CostProfile(sla_penalty_per_violation=0))
        bd = engine.calculate_scenario_cost("clean", ["svc"], downtime_minutes=60)
        assert not any("SLA exposure" in r for r in bd.recommendations)


# ── calculate_annual_projection ───────────────────────────────────────────

class TestAnnualProjection:
    def _make_scenario(self, name: str, total: float) -> CostBreakdown:
        return CostBreakdown(
            scenario_name=name,
            downtime_minutes=60,
            revenue_loss=total,
        )

    def test_empty_scenarios(self):
        engine = CostImpactEngine()
        proj = engine.calculate_annual_projection([])
        assert proj.expected_annual_cost == 0.0
        assert proj.worst_case_annual_cost == 0.0
        assert proj.best_case_annual_cost == 0.0

    def test_single_scenario(self):
        engine = CostImpactEngine()
        s = self._make_scenario("only", 10_000)
        proj = engine.calculate_annual_projection([s], incidents_per_year=12)
        assert proj.expected_annual_cost == 120_000.0
        assert proj.worst_case_annual_cost == 120_000.0
        assert proj.best_case_annual_cost == 120_000.0

    def test_multiple_scenarios_expected_cost(self):
        engine = CostImpactEngine()
        s1 = self._make_scenario("low", 1_000)
        s2 = self._make_scenario("high", 9_000)
        proj = engine.calculate_annual_projection([s1, s2], incidents_per_year=10)
        # avg = (1000+9000)/2 = 5000, annual = 5000*10 = 50000
        assert proj.expected_annual_cost == 50_000.0

    def test_worst_and_best_case(self):
        engine = CostImpactEngine()
        s1 = self._make_scenario("low", 500)
        s2 = self._make_scenario("high", 50_000)
        proj = engine.calculate_annual_projection([s1, s2], incidents_per_year=12)
        assert proj.worst_case_annual_cost == 50_000 * 12
        assert proj.best_case_annual_cost == 500 * 12

    def test_incidents_per_year_stored(self):
        engine = CostImpactEngine()
        s = self._make_scenario("x", 100)
        proj = engine.calculate_annual_projection([s], incidents_per_year=24)
        assert proj.expected_incidents_per_year == 24

    def test_cost_by_category(self):
        engine = CostImpactEngine()
        s = CostBreakdown(
            scenario_name="cat",
            downtime_minutes=60,
            revenue_loss=1000,
            sla_penalty=500,
            recovery_cost=200,
            reputation_cost=100,
            productivity_loss=50,
        )
        proj = engine.calculate_annual_projection([s])
        assert proj.cost_by_category[CostCategory.REVENUE_LOSS.value] == 1000
        assert proj.cost_by_category[CostCategory.SLA_PENALTY.value] == 500
        assert proj.cost_by_category[CostCategory.RECOVERY_COST.value] == 200
        assert proj.cost_by_category[CostCategory.REPUTATION_COST.value] == 100
        assert proj.cost_by_category[CostCategory.PRODUCTIVITY_LOSS.value] == 50

    def test_cost_by_category_sums_across_scenarios(self):
        engine = CostImpactEngine()
        s1 = CostBreakdown(scenario_name="a", downtime_minutes=60, revenue_loss=100)
        s2 = CostBreakdown(scenario_name="b", downtime_minutes=60, revenue_loss=200)
        proj = engine.calculate_annual_projection([s1, s2])
        assert proj.cost_by_category[CostCategory.REVENUE_LOSS.value] == 300

    def test_top_cost_scenarios_sorted(self):
        engine = CostImpactEngine()
        scenarios = [
            self._make_scenario(f"s{i}", (i + 1) * 1000)
            for i in range(10)
        ]
        proj = engine.calculate_annual_projection(scenarios)
        assert len(proj.top_cost_scenarios) == 5
        costs = [s.total_cost for s in proj.top_cost_scenarios]
        assert costs == sorted(costs, reverse=True)

    def test_top_cost_scenarios_max_5(self):
        engine = CostImpactEngine()
        scenarios = [self._make_scenario(f"s{i}", i * 100) for i in range(20)]
        proj = engine.calculate_annual_projection(scenarios)
        assert len(proj.top_cost_scenarios) <= 5

    def test_top_cost_scenarios_fewer_than_5(self):
        engine = CostImpactEngine()
        scenarios = [self._make_scenario("only", 100)]
        proj = engine.calculate_annual_projection(scenarios)
        assert len(proj.top_cost_scenarios) == 1


# ── calculate_roi ─────────────────────────────────────────────────────────

class TestROI:
    def test_positive_roi(self):
        engine = CostImpactEngine()
        roi = engine.calculate_roi(
            improvement_name="add-replica",
            implementation_cost=50_000,
            current_annual_cost=200_000,
            projected_annual_cost=50_000,
        )
        assert roi.annual_cost_reduction == 150_000
        assert roi.five_year_roi_percent > 0
        assert roi.payback_period_months > 0
        assert roi.risk_reduction_percent == 75.0

    def test_zero_savings(self):
        engine = CostImpactEngine()
        roi = engine.calculate_roi(
            improvement_name="no-help",
            implementation_cost=10_000,
            current_annual_cost=100_000,
            projected_annual_cost=100_000,
        )
        assert roi.annual_cost_reduction == 0
        assert roi.payback_period_months == float('inf')
        assert roi.five_year_roi_percent == 0
        assert roi.risk_reduction_percent == 0

    def test_negative_savings(self):
        engine = CostImpactEngine()
        roi = engine.calculate_roi(
            improvement_name="worse",
            implementation_cost=10_000,
            current_annual_cost=50_000,
            projected_annual_cost=60_000,
        )
        assert roi.annual_cost_reduction == 0
        assert roi.payback_period_months == float('inf')

    def test_payback_period_calculation(self):
        engine = CostImpactEngine()
        roi = engine.calculate_roi(
            improvement_name="fast-payback",
            implementation_cost=12_000,
            current_annual_cost=100_000,
            projected_annual_cost=76_000,
        )
        # savings=24000/yr, payback = (12000/24000)*12 = 6 months
        assert roi.payback_period_months == 6.0

    def test_five_year_roi_calculation(self):
        engine = CostImpactEngine()
        roi = engine.calculate_roi(
            improvement_name="good",
            implementation_cost=100_000,
            current_annual_cost=500_000,
            projected_annual_cost=200_000,
        )
        # savings=300K, 5yr net = 300K*5 - 100K = 1.4M, roi = 1.4M/100K*100 = 1400%
        assert roi.five_year_roi_percent == 1400.0

    def test_risk_reduction_calculation(self):
        engine = CostImpactEngine()
        roi = engine.calculate_roi(
            improvement_name="half",
            implementation_cost=50_000,
            current_annual_cost=200_000,
            projected_annual_cost=100_000,
        )
        assert roi.risk_reduction_percent == 50.0

    def test_improvement_name_preserved(self):
        engine = CostImpactEngine()
        roi = engine.calculate_roi("my-improvement", 1, 2, 1)
        assert roi.improvement_name == "my-improvement"

    def test_implementation_cost_preserved(self):
        engine = CostImpactEngine()
        roi = engine.calculate_roi("x", 42_000, 100_000, 50_000)
        assert roi.implementation_cost == 42_000


# ── Edge cases ────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_zero_downtime_scenario(self):
        engine = CostImpactEngine()
        engine.set_component_profile("api", CostProfile(revenue_per_hour=50_000))
        bd = engine.calculate_scenario_cost("zero-dt", ["api"], downtime_minutes=0)
        assert bd.revenue_loss == 0.0
        assert bd.downtime_minutes == 0

    def test_empty_affected_components(self):
        engine = CostImpactEngine()
        bd = engine.calculate_scenario_cost("none", [], downtime_minutes=60)
        assert bd.total_cost == 0.0
        assert bd.affected_components == []

    def test_very_large_downtime(self):
        engine = CostImpactEngine()
        engine.set_component_profile("core", CostProfile(revenue_per_hour=100_000))
        bd = engine.calculate_scenario_cost("long", ["core"], downtime_minutes=14400)  # 10 days
        assert bd.revenue_loss == 100_000 * 240  # 240 hours

    def test_very_small_costs(self):
        engine = CostImpactEngine()
        engine.set_component_profile("tiny", CostProfile(
            revenue_per_hour=0.01,
            recovery_cost_per_incident=0.01,
            engineer_hourly_rate=0.01,
        ))
        bd = engine.calculate_scenario_cost("micro", ["tiny"], downtime_minutes=1)
        assert bd.total_cost >= 0

    def test_engine_with_no_profiles(self):
        engine = CostImpactEngine()
        bd = engine.calculate_scenario_cost("default", ["x", "y"], downtime_minutes=60)
        # All costs from defaults: revenue=0, sla=0, recovery=500*2, reputation=0, productivity=150*2
        assert bd.recovery_cost == 1000.0
        assert bd.productivity_loss == 600.0  # 150*max(1,60/30)*1 = 150*2 = 300, x2 components

    def test_cascade_depth_zero(self):
        """cascade_depth=0 should produce 0 recovery and 0 productivity."""
        engine = CostImpactEngine()
        engine.set_component_profile("svc", CostProfile(
            recovery_cost_per_incident=500,
            engineer_hourly_rate=150,
        ))
        bd = engine.calculate_scenario_cost("zero-cascade", ["svc"], downtime_minutes=60, cascade_depth=0)
        assert bd.recovery_cost == 0.0
        assert bd.productivity_loss == 0.0

    def test_sla_exactly_at_threshold(self):
        """Downtime exactly at SLA threshold -> no penalty."""
        engine = CostImpactEngine()
        engine.set_component_profile("svc", CostProfile(
            sla_penalty_per_violation=10_000,
            sla_threshold_minutes=60,
        ))
        bd = engine.calculate_scenario_cost("edge", ["svc"], downtime_minutes=60)
        assert bd.sla_penalty == 0.0

    def test_sla_just_over_threshold(self):
        """Downtime slightly over SLA threshold -> 1 violation."""
        engine = CostImpactEngine()
        engine.set_component_profile("svc", CostProfile(
            sla_penalty_per_violation=10_000,
            sla_threshold_minutes=60,
        ))
        bd = engine.calculate_scenario_cost("edge", ["svc"], downtime_minutes=61)
        assert bd.sla_penalty == 10_000.0


# ── Enum values ───────────────────────────────────────────────────────────

class TestEnums:
    def test_cost_tier_values(self):
        assert CostTier.CATASTROPHIC.value == "catastrophic"
        assert CostTier.CRITICAL.value == "critical"
        assert CostTier.HIGH.value == "high"
        assert CostTier.MEDIUM.value == "medium"
        assert CostTier.LOW.value == "low"

    def test_cost_category_values(self):
        assert CostCategory.REVENUE_LOSS.value == "revenue_loss"
        assert CostCategory.SLA_PENALTY.value == "sla_penalty"
        assert CostCategory.RECOVERY_COST.value == "recovery_cost"
        assert CostCategory.REPUTATION_COST.value == "reputation_cost"
        assert CostCategory.PRODUCTIVITY_LOSS.value == "productivity_loss"


# ── Dataclass defaults ────────────────────────────────────────────────────

class TestDataclassDefaults:
    def test_annual_projection_defaults(self):
        proj = AnnualCostProjection()
        assert proj.expected_annual_cost == 0.0
        assert proj.worst_case_annual_cost == 0.0
        assert proj.best_case_annual_cost == 0.0
        assert proj.expected_incidents_per_year == 0.0
        assert proj.cost_by_category == {}
        assert proj.top_cost_scenarios == []
        assert proj.roi_of_improvements == []

    def test_roi_analysis_fields(self):
        roi = ROIAnalysis(
            improvement_name="test",
            implementation_cost=1000,
            annual_cost_reduction=500,
            payback_period_months=24,
            five_year_roi_percent=150,
            risk_reduction_percent=25,
        )
        assert roi.improvement_name == "test"
        assert roi.implementation_cost == 1000
        assert roi.annual_cost_reduction == 500
        assert roi.payback_period_months == 24
        assert roi.five_year_roi_percent == 150
        assert roi.risk_reduction_percent == 25


# ── Integration: full pipeline ────────────────────────────────────────────

class TestFullPipeline:
    def test_end_to_end_pipeline(self):
        """Full workflow: profiles -> scenarios -> projection -> ROI."""
        engine = CostImpactEngine(default_profile=CostProfile(
            recovery_cost_per_incident=200,
            engineer_hourly_rate=100,
        ))
        engine.set_component_profile("api", CostProfile(
            revenue_per_hour=50_000,
            sla_penalty_per_violation=25_000,
            sla_threshold_minutes=30,
            recovery_cost_per_incident=1000,
            engineer_hourly_rate=200,
            affected_users=100_000,
            reputation_multiplier=1.5,
        ))
        engine.set_component_profile("db", CostProfile(
            revenue_per_hour=30_000,
            recovery_cost_per_incident=2000,
            engineer_hourly_rate=250,
        ))

        # Scenario 1: API outage
        s1 = engine.calculate_scenario_cost("api-outage", ["api"], downtime_minutes=60)
        assert s1.revenue_loss > 0
        assert s1.total_cost > 0

        # Scenario 2: DB + API cascade
        s2 = engine.calculate_scenario_cost(
            "db-cascade", ["db", "api"], downtime_minutes=120, cascade_depth=3,
        )
        assert s2.total_cost > s1.total_cost

        # Annual projection
        proj = engine.calculate_annual_projection([s1, s2], incidents_per_year=6)
        assert proj.expected_annual_cost > 0
        assert proj.worst_case_annual_cost >= proj.expected_annual_cost

        # ROI calculation
        roi = engine.calculate_roi(
            improvement_name="add-db-replica",
            implementation_cost=50_000,
            current_annual_cost=proj.expected_annual_cost,
            projected_annual_cost=proj.expected_annual_cost * 0.3,
        )
        assert roi.annual_cost_reduction > 0
        assert roi.five_year_roi_percent > 0
        assert roi.payback_period_months < 120  # Less than 10 years
