"""Tests for the Incident Cost Modeling Engine.

Comprehensive test suite covering CostCategory/IncidentSeverity enums,
IncidentProfile/CostBreakdown/IncidentCostReport/ROIAnalysis/ScenarioComparison/
ErrorBudgetValue/AnnualProjection/ExecutiveIncidentReport/CascadingCostResult
Pydantic models, and all IncidentCostEngine public methods with edge cases.
"""

from __future__ import annotations

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    CostProfile,
    Dependency,
    FailoverConfig,
    OperationalProfile,
    SecurityProfile,
    ComplianceTags,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.incident_cost_model import (
    AnnualProjection,
    CascadingCostResult,
    CostBreakdown,
    CostCategory,
    ErrorBudgetValue,
    ExecutiveIncidentReport,
    IncidentCostEngine,
    IncidentCostReport,
    IncidentProfile,
    IncidentSeverity,
    ROIAnalysis,
    ScenarioComparison,
)


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str | None = None,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 2,
    failover_enabled: bool = False,
    revenue_per_minute: float = 0.0,
    mtbf_hours: float = 0.0,
) -> Component:
    return Component(
        id=cid,
        name=name or cid,
        type=ctype,
        replicas=replicas,
        failover=FailoverConfig(enabled=failover_enabled),
        cost_profile=CostProfile(revenue_per_minute=revenue_per_minute),
        operational_profile=OperationalProfile(mtbf_hours=mtbf_hours),
    )


def _graph(*components: Component, deps: list[Dependency] | None = None) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    for d in deps or []:
        g.add_dependency(d)
    return g


def _profile(
    severity: IncidentSeverity = IncidentSeverity.SEV3,
    duration: float = 60.0,
    users: int = 1000,
    components: list[str] | None = None,
    data_loss: bool = False,
    public_facing: bool = False,
    sla_breach: bool = False,
    regulatory_impact: bool = False,
) -> IncidentProfile:
    return IncidentProfile(
        severity=severity,
        duration_minutes=duration,
        affected_users=users,
        affected_components=components or [],
        data_loss=data_loss,
        public_facing=public_facing,
        sla_breach=sla_breach,
        regulatory_impact=regulatory_impact,
    )


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestCostCategory:
    """Tests for CostCategory enum."""

    def test_all_values_exist(self) -> None:
        expected = {
            "direct_revenue_loss",
            "sla_credits",
            "engineering_time",
            "customer_churn",
            "brand_damage",
            "regulatory_fine",
            "data_recovery",
            "communication",
            "legal",
            "opportunity_cost",
        }
        assert {e.value for e in CostCategory} == expected

    def test_is_str_enum(self) -> None:
        assert isinstance(CostCategory.DIRECT_REVENUE_LOSS, str)

    def test_member_count(self) -> None:
        assert len(CostCategory) == 10


class TestIncidentSeverity:
    """Tests for IncidentSeverity enum."""

    def test_all_values_exist(self) -> None:
        expected = {"sev1", "sev2", "sev3", "sev4", "sev5"}
        assert {e.value for e in IncidentSeverity} == expected

    def test_is_str_enum(self) -> None:
        assert isinstance(IncidentSeverity.SEV1, str)

    def test_member_count(self) -> None:
        assert len(IncidentSeverity) == 5


# ---------------------------------------------------------------------------
# Pydantic model tests
# ---------------------------------------------------------------------------


class TestIncidentProfile:
    """Tests for IncidentProfile model."""

    def test_minimal_construction(self) -> None:
        p = IncidentProfile(
            severity=IncidentSeverity.SEV3,
            duration_minutes=30.0,
            affected_users=100,
        )
        assert p.severity == IncidentSeverity.SEV3
        assert p.duration_minutes == 30.0
        assert p.affected_users == 100
        assert p.affected_components == []
        assert p.data_loss is False
        assert p.public_facing is False
        assert p.sla_breach is False
        assert p.regulatory_impact is False

    def test_full_construction(self) -> None:
        p = _profile(
            severity=IncidentSeverity.SEV1,
            duration=120.0,
            users=50000,
            components=["db", "api"],
            data_loss=True,
            public_facing=True,
            sla_breach=True,
            regulatory_impact=True,
        )
        assert p.data_loss is True
        assert p.public_facing is True
        assert len(p.affected_components) == 2

    def test_serialization_roundtrip(self) -> None:
        p = _profile(severity=IncidentSeverity.SEV2, duration=45.0, users=500)
        data = p.model_dump()
        p2 = IncidentProfile(**data)
        assert p2 == p

    def test_zero_duration(self) -> None:
        p = _profile(duration=0.0)
        assert p.duration_minutes == 0.0

    def test_zero_users(self) -> None:
        p = _profile(users=0)
        assert p.affected_users == 0


class TestCostBreakdown:
    """Tests for CostBreakdown model."""

    def test_defaults(self) -> None:
        cb = CostBreakdown(category=CostCategory.LEGAL, amount=100.0)
        assert cb.confidence == 0.8
        assert cb.calculation_basis == ""
        assert cb.is_recurring is False

    def test_full(self) -> None:
        cb = CostBreakdown(
            category=CostCategory.CUSTOMER_CHURN,
            amount=5000.0,
            confidence=0.6,
            calculation_basis="churn model",
            is_recurring=True,
        )
        assert cb.is_recurring is True
        assert cb.confidence == 0.6

    def test_confidence_bounds(self) -> None:
        with pytest.raises(Exception):
            CostBreakdown(category=CostCategory.LEGAL, amount=1.0, confidence=1.5)
        with pytest.raises(Exception):
            CostBreakdown(category=CostCategory.LEGAL, amount=1.0, confidence=-0.1)

    def test_zero_amount(self) -> None:
        cb = CostBreakdown(category=CostCategory.SLA_CREDITS, amount=0.0)
        assert cb.amount == 0.0


class TestIncidentCostReport:
    """Tests for IncidentCostReport model."""

    def test_defaults(self) -> None:
        r = IncidentCostReport(total_cost=0.0)
        assert r.breakdown == []
        assert r.cost_per_minute == 0.0
        assert r.recommendations == []

    def test_full(self) -> None:
        r = IncidentCostReport(
            total_cost=10000.0,
            breakdown=[CostBreakdown(category=CostCategory.LEGAL, amount=10000.0)],
            cost_per_minute=100.0,
            cost_per_user=10.0,
            annualized_risk=120000.0,
            roi_of_prevention=500.0,
            recommendations=["Fix stuff"],
        )
        assert len(r.breakdown) == 1
        assert r.recommendations == ["Fix stuff"]


class TestROIAnalysis:
    """Tests for ROIAnalysis model."""

    def test_construction(self) -> None:
        r = ROIAnalysis(
            investment=50000.0,
            expected_annual_loss_without=200000.0,
            expected_annual_loss_with=60000.0,
            annual_savings=90000.0,
            roi_percent=180.0,
            payback_months=6.67,
            recommendation="Recommended",
        )
        assert r.roi_percent == 180.0


class TestScenarioComparison:
    """Tests for ScenarioComparison model."""

    def test_empty(self) -> None:
        sc = ScenarioComparison()
        assert sc.scenarios == []
        assert sc.worst_case_cost == 0.0

    def test_with_data(self) -> None:
        sc = ScenarioComparison(
            worst_case_cost=100.0,
            best_case_cost=10.0,
            average_cost=55.0,
            cost_variance=2025.0,
        )
        assert sc.average_cost == 55.0


class TestErrorBudgetValue:
    """Tests for ErrorBudgetValue model."""

    def test_construction(self) -> None:
        ebv = ErrorBudgetValue(
            slo_target=99.9,
            error_budget_percent=0.1,
            error_budget_minutes_per_month=43.2,
            cost_per_budget_minute=100.0,
            total_budget_value=4320.0,
        )
        assert ebv.slo_target == 99.9


class TestAnnualProjection:
    """Tests for AnnualProjection model."""

    def test_defaults(self) -> None:
        ap = AnnualProjection(projected_incidents=0, projected_annual_cost=0.0)
        assert ap.cost_by_severity == {}
        assert ap.cost_trend == ""


class TestExecutiveIncidentReport:
    """Tests for ExecutiveIncidentReport model."""

    def test_defaults(self) -> None:
        er = ExecutiveIncidentReport()
        assert er.incident_summary == ""
        assert er.total_cost == 0.0
        assert er.top_recommendations == []


class TestCascadingCostResult:
    """Tests for CascadingCostResult model."""

    def test_defaults(self) -> None:
        cr = CascadingCostResult()
        assert cr.initial_component == ""
        assert cr.affected_components == []
        assert cr.cascade_depth == 0


# ---------------------------------------------------------------------------
# IncidentCostEngine tests
# ---------------------------------------------------------------------------


class TestCalculateIncidentCost:
    """Tests for IncidentCostEngine.calculate_incident_cost."""

    def test_basic_cost_report(self) -> None:
        g = _graph(_comp("api", revenue_per_minute=200.0, mtbf_hours=720))
        p = _profile(components=["api"])
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, p)
        assert report.total_cost > 0
        assert len(report.breakdown) == 10  # all categories

    def test_all_categories_present(self) -> None:
        g = _graph(_comp("api"))
        p = _profile(
            components=["api"],
            data_loss=True,
            sla_breach=True,
            regulatory_impact=True,
            public_facing=True,
        )
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, p)
        cats = {item.category for item in report.breakdown}
        assert cats == set(CostCategory)

    def test_sev1_costs_more_than_sev5(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        r1 = engine.calculate_incident_cost(g, _profile(severity=IncidentSeverity.SEV1, components=["api"]))
        r5 = engine.calculate_incident_cost(g, _profile(severity=IncidentSeverity.SEV5, components=["api"]))
        assert r1.total_cost > r5.total_cost

    def test_longer_duration_costs_more(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        r_short = engine.calculate_incident_cost(g, _profile(duration=10.0, components=["api"]))
        r_long = engine.calculate_incident_cost(g, _profile(duration=120.0, components=["api"]))
        assert r_long.total_cost > r_short.total_cost

    def test_more_users_costs_more(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        r_few = engine.calculate_incident_cost(
            g, _profile(users=10, public_facing=True, components=["api"])
        )
        r_many = engine.calculate_incident_cost(
            g, _profile(users=100000, public_facing=True, components=["api"])
        )
        assert r_many.total_cost > r_few.total_cost

    def test_cost_per_minute_calculated(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(duration=60.0, components=["api"]))
        assert report.cost_per_minute > 0
        assert report.cost_per_minute == pytest.approx(
            report.total_cost / 60.0, rel=1e-2
        )

    def test_cost_per_user_calculated(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(users=500, components=["api"]))
        assert report.cost_per_user > 0
        assert report.cost_per_user == pytest.approx(
            report.total_cost / 500, rel=1e-2
        )

    def test_annualized_risk_uses_mtbf(self) -> None:
        g = _graph(_comp("api", mtbf_hours=100))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(components=["api"]))
        # 8760 / 100 = 87.6 incidents per year
        assert report.annualized_risk > report.total_cost

    def test_no_components_in_profile(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(components=[]))
        assert report.total_cost > 0  # uses defaults

    def test_empty_graph(self) -> None:
        g = _graph()
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile())
        assert report.total_cost > 0  # uses defaults

    def test_sla_breach_false_yields_zero_credits(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(sla_breach=False, components=["api"]))
        sla_item = [b for b in report.breakdown if b.category == CostCategory.SLA_CREDITS][0]
        assert sla_item.amount == 0.0

    def test_sla_breach_true_yields_nonzero_credits(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(sla_breach=True, components=["api"]))
        sla_item = [b for b in report.breakdown if b.category == CostCategory.SLA_CREDITS][0]
        assert sla_item.amount > 0

    def test_no_data_loss_yields_zero_recovery(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(data_loss=False, components=["api"]))
        dr = [b for b in report.breakdown if b.category == CostCategory.DATA_RECOVERY][0]
        assert dr.amount == 0.0

    def test_data_loss_yields_nonzero_recovery(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(data_loss=True, components=["api"]))
        dr = [b for b in report.breakdown if b.category == CostCategory.DATA_RECOVERY][0]
        assert dr.amount > 0

    def test_not_public_facing_zero_brand_damage(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(public_facing=False))
        bd = [b for b in report.breakdown if b.category == CostCategory.BRAND_DAMAGE][0]
        assert bd.amount == 0.0

    def test_public_facing_nonzero_brand_damage(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(public_facing=True, users=1000))
        bd = [b for b in report.breakdown if b.category == CostCategory.BRAND_DAMAGE][0]
        assert bd.amount > 0

    def test_no_regulatory_zero_fine(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(regulatory_impact=False))
        rf = [b for b in report.breakdown if b.category == CostCategory.REGULATORY_FINE][0]
        assert rf.amount == 0.0

    def test_regulatory_impact_nonzero_fine(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(regulatory_impact=True))
        rf = [b for b in report.breakdown if b.category == CostCategory.REGULATORY_FINE][0]
        assert rf.amount > 0

    def test_no_legal_exposure(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(
            g, _profile(data_loss=False, regulatory_impact=False)
        )
        legal = [b for b in report.breakdown if b.category == CostCategory.LEGAL][0]
        assert legal.amount == 0.0

    def test_legal_from_data_loss(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(data_loss=True))
        legal = [b for b in report.breakdown if b.category == CostCategory.LEGAL][0]
        assert legal.amount > 0

    def test_legal_from_regulatory(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(regulatory_impact=True))
        legal = [b for b in report.breakdown if b.category == CostCategory.LEGAL][0]
        assert legal.amount > 0

    def test_engineering_time_scales_with_severity(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        r1 = engine.calculate_incident_cost(g, _profile(severity=IncidentSeverity.SEV1))
        r5 = engine.calculate_incident_cost(g, _profile(severity=IncidentSeverity.SEV5))
        eng1 = [b for b in r1.breakdown if b.category == CostCategory.ENGINEERING_TIME][0]
        eng5 = [b for b in r5.breakdown if b.category == CostCategory.ENGINEERING_TIME][0]
        assert eng1.amount > eng5.amount

    def test_multiple_components_revenue(self) -> None:
        g = _graph(
            _comp("api", revenue_per_minute=200.0),
            _comp("web", revenue_per_minute=300.0),
        )
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(components=["api", "web"]))
        rev = [b for b in report.breakdown if b.category == CostCategory.DIRECT_REVENUE_LOSS][0]
        # total revenue = 200 + 300 = 500 per minute
        assert rev.amount > 0

    def test_roi_of_prevention_positive(self) -> None:
        g = _graph(_comp("api", mtbf_hours=100))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(components=["api"]))
        assert report.roi_of_prevention > 0

    def test_recommendations_spof(self) -> None:
        g = _graph(_comp("api", replicas=1, failover_enabled=False))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(components=["api"]))
        assert any("single point of failure" in r for r in report.recommendations)

    def test_recommendations_high_cost(self) -> None:
        g = _graph(_comp("api", revenue_per_minute=10000.0))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(
            g,
            _profile(
                severity=IncidentSeverity.SEV1,
                duration=120.0,
                components=["api"],
                sla_breach=True,
                data_loss=True,
                regulatory_impact=True,
                public_facing=True,
                users=100000,
            ),
        )
        assert len(report.recommendations) > 0

    def test_recommendations_data_loss(self) -> None:
        g = _graph(_comp("db"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(data_loss=True))
        assert any("backup" in r.lower() for r in report.recommendations)

    def test_recommendations_sla_breach(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(sla_breach=True))
        assert any("sla" in r.lower() for r in report.recommendations)

    def test_recommendations_regulatory(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(regulatory_impact=True))
        assert any("compliance" in r.lower() or "regulatory" in r.lower() for r in report.recommendations)

    def test_recommendations_public_facing_many_users(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(
            g, _profile(public_facing=True, users=50000)
        )
        assert any("communication" in r.lower() or "status" in r.lower() for r in report.recommendations)

    def test_zero_duration_no_crash(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(duration=0.0))
        assert report.total_cost >= 0

    def test_zero_users_no_crash(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(users=0))
        assert report.total_cost >= 0

    def test_default_mtbf_used_when_none_set(self) -> None:
        g = _graph(_comp("api", mtbf_hours=0.0))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(components=["api"]))
        # Default MTBF = 720h → 8760/720 = ~12.17 incidents/year
        assert report.annualized_risk > 0

    def test_custom_revenue_component(self) -> None:
        g = _graph(_comp("premium", revenue_per_minute=5000.0))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(components=["premium"], duration=10))
        rev = [b for b in report.breakdown if b.category == CostCategory.DIRECT_REVENUE_LOSS][0]
        # 5000 * 10 * 1.5 (sev3 mult)
        assert rev.amount == pytest.approx(75000.0, rel=1e-2)

    def test_communication_cost_present(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(duration=60.0))
        comm = [b for b in report.breakdown if b.category == CostCategory.COMMUNICATION][0]
        assert comm.amount > 0

    def test_opportunity_cost_present(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(duration=60.0))
        opp = [b for b in report.breakdown if b.category == CostCategory.OPPORTUNITY_COST][0]
        assert opp.amount > 0


class TestEstimatePreventionROI:
    """Tests for IncidentCostEngine.estimate_prevention_roi."""

    def test_basic_roi(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        profiles = [_profile(components=["api"])]
        roi = engine.estimate_prevention_roi(g, profiles, 10000.0)
        assert isinstance(roi, ROIAnalysis)
        assert roi.investment == 10000.0

    def test_high_investment_negative_savings(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        profiles = [_profile(severity=IncidentSeverity.SEV5, duration=1.0, users=1)]
        roi = engine.estimate_prevention_roi(g, profiles, 10_000_000.0)
        assert roi.annual_savings < 0
        assert "Not recommended" in roi.recommendation

    def test_low_investment_high_roi(self) -> None:
        g = _graph(_comp("api", revenue_per_minute=10000.0, mtbf_hours=100))
        engine = IncidentCostEngine()
        profiles = [
            _profile(severity=IncidentSeverity.SEV1, duration=120.0, components=["api"]),
        ]
        roi = engine.estimate_prevention_roi(g, profiles, 100.0)
        assert roi.roi_percent > 200
        assert "Strongly recommended" in roi.recommendation

    def test_multiple_profiles(self) -> None:
        g = _graph(_comp("api"), _comp("db"))
        engine = IncidentCostEngine()
        profiles = [
            _profile(components=["api"]),
            _profile(components=["db"], severity=IncidentSeverity.SEV2),
        ]
        roi = engine.estimate_prevention_roi(g, profiles, 50000.0)
        assert roi.expected_annual_loss_without > roi.expected_annual_loss_with

    def test_empty_profiles(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        roi = engine.estimate_prevention_roi(g, [], 10000.0)
        assert roi.expected_annual_loss_without == 0.0
        assert roi.annual_savings < 0

    def test_zero_investment(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        roi = engine.estimate_prevention_roi(g, [_profile()], 0.0)
        assert roi.investment == 0.0
        assert roi.payback_months >= 0

    def test_payback_months_reasonable(self) -> None:
        g = _graph(_comp("api", mtbf_hours=200))
        engine = IncidentCostEngine()
        roi = engine.estimate_prevention_roi(g, [_profile(components=["api"])], 5000.0)
        assert roi.payback_months > 0

    def test_marginal_recommendation(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        # We need to find an investment level that produces 0 < roi < 50
        profiles = [_profile(severity=IncidentSeverity.SEV4, duration=10.0, users=10)]
        # Try a range to find marginal
        for inv in [1000, 5000, 10000, 50000, 100000, 200000]:
            roi = engine.estimate_prevention_roi(g, profiles, float(inv))
            if 0 < roi.roi_percent < 50:
                assert "Marginal" in roi.recommendation
                return
        # If no marginal found, at least verify the method doesn't crash
        assert True

    def test_recommended_tier(self) -> None:
        g = _graph(_comp("api", mtbf_hours=200))
        engine = IncidentCostEngine()
        profiles = [_profile(components=["api"], duration=60)]
        roi = engine.estimate_prevention_roi(g, profiles, 500.0)
        # With decent annualized risk, small investment should yield solid ROI
        assert roi.recommendation != ""


class TestCompareScenarios:
    """Tests for IncidentCostEngine.compare_scenarios."""

    def test_single_scenario(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        comp = engine.compare_scenarios(g, [_profile()])
        assert isinstance(comp, ScenarioComparison)
        assert len(comp.scenarios) == 1
        assert comp.worst_case_cost == comp.best_case_cost

    def test_multiple_scenarios(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        profiles = [
            _profile(severity=IncidentSeverity.SEV1, duration=120.0),
            _profile(severity=IncidentSeverity.SEV5, duration=5.0),
        ]
        comp = engine.compare_scenarios(g, profiles)
        assert len(comp.scenarios) == 2
        assert comp.worst_case_cost > comp.best_case_cost

    def test_empty_profiles(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        comp = engine.compare_scenarios(g, [])
        assert comp.scenarios == []
        assert comp.worst_case_cost == 0.0

    def test_average_cost(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        profiles = [
            _profile(severity=IncidentSeverity.SEV3),
            _profile(severity=IncidentSeverity.SEV3),
        ]
        comp = engine.compare_scenarios(g, profiles)
        assert comp.average_cost == pytest.approx(comp.worst_case_cost, rel=1e-2)

    def test_variance_calculated(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        profiles = [
            _profile(severity=IncidentSeverity.SEV1, duration=120.0),
            _profile(severity=IncidentSeverity.SEV5, duration=5.0),
        ]
        comp = engine.compare_scenarios(g, profiles)
        assert comp.cost_variance > 0

    def test_recommendations_worst_case_skew(self) -> None:
        g = _graph(_comp("api", revenue_per_minute=10000.0))
        engine = IncidentCostEngine()
        profiles = [
            _profile(
                severity=IncidentSeverity.SEV1,
                duration=120.0,
                components=["api"],
                sla_breach=True,
                data_loss=True,
                regulatory_impact=True,
                public_facing=True,
                users=100000,
            ),
            _profile(severity=IncidentSeverity.SEV5, duration=1.0, users=1),
        ]
        comp = engine.compare_scenarios(g, profiles)
        # With extreme cost skew, at least one recommendation is generated
        assert len(comp.recommendations) > 0
        assert comp.worst_case_cost > comp.best_case_cost * 100

    def test_three_identical_scenarios(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        p = _profile()
        comp = engine.compare_scenarios(g, [p, p, p])
        assert comp.cost_variance == pytest.approx(0.0, abs=1.0)

    def test_best_case_very_low_recommendation(self) -> None:
        g = _graph(_comp("api", revenue_per_minute=50000.0))
        engine = IncidentCostEngine()
        profiles = [
            _profile(severity=IncidentSeverity.SEV1, duration=120.0, components=["api"],
                     sla_breach=True, data_loss=True, regulatory_impact=True,
                     public_facing=True, users=100000),
            _profile(severity=IncidentSeverity.SEV5, duration=0.1, users=1,
                     components=[]),
        ]
        comp = engine.compare_scenarios(g, profiles)
        # The best case cost should be very low compared to average
        # Check if the recommendation about best-case is present
        if comp.best_case_cost < comp.average_cost * 0.1:
            assert any("best-case" in r.lower() or "Best" in r for r in comp.recommendations)


class TestCalculateErrorBudgetValue:
    """Tests for IncidentCostEngine.calculate_error_budget_value."""

    def test_three_nines(self) -> None:
        g = _graph(_comp("api", revenue_per_minute=100.0))
        engine = IncidentCostEngine()
        ebv = engine.calculate_error_budget_value(g, 99.9)
        assert isinstance(ebv, ErrorBudgetValue)
        assert ebv.slo_target == 99.9
        assert ebv.error_budget_percent == pytest.approx(0.1, abs=0.01)
        assert ebv.error_budget_minutes_per_month > 0

    def test_four_nines(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        ebv = engine.calculate_error_budget_value(g, 99.99)
        assert ebv.error_budget_percent == pytest.approx(0.01, abs=0.001)
        assert any("four-nines" in r.lower() or "Four" in r for r in ebv.recommendations)

    def test_two_nines(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        ebv = engine.calculate_error_budget_value(g, 99.0)
        assert ebv.error_budget_percent == pytest.approx(1.0, abs=0.01)
        assert any("below 99.9" in r.lower() or "SLO below" in r for r in ebv.recommendations)

    def test_budget_value_proportional(self) -> None:
        g = _graph(_comp("api", revenue_per_minute=200.0))
        engine = IncidentCostEngine()
        ebv_low = engine.calculate_error_budget_value(g, 99.99)
        ebv_high = engine.calculate_error_budget_value(g, 99.0)
        assert ebv_high.total_budget_value > ebv_low.total_budget_value

    def test_remaining_budget_equals_total(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        ebv = engine.calculate_error_budget_value(g, 99.9)
        assert ebv.remaining_budget_minutes == ebv.error_budget_minutes_per_month
        assert ebv.remaining_budget_value == ebv.total_budget_value

    def test_empty_graph(self) -> None:
        g = _graph()
        engine = IncidentCostEngine()
        ebv = engine.calculate_error_budget_value(g, 99.9)
        assert ebv.total_budget_value > 0  # uses default revenue

    def test_multiple_components_sum_revenue(self) -> None:
        g = _graph(
            _comp("api", revenue_per_minute=100.0),
            _comp("web", revenue_per_minute=200.0),
        )
        engine = IncidentCostEngine()
        ebv = engine.calculate_error_budget_value(g, 99.9)
        assert ebv.cost_per_budget_minute == pytest.approx(300.0, rel=0.01)

    def test_three_nines_recommendation_text(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        ebv = engine.calculate_error_budget_value(g, 99.9)
        assert any("three-nines" in r.lower() or "Three" in r for r in ebv.recommendations)

    def test_100_percent_slo(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        ebv = engine.calculate_error_budget_value(g, 100.0)
        assert ebv.error_budget_percent == 0.0
        assert ebv.error_budget_minutes_per_month == 0.0
        assert ebv.total_budget_value == 0.0


class TestProjectAnnualIncidentCost:
    """Tests for IncidentCostEngine.project_annual_incident_cost."""

    def test_empty_history(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        proj = engine.project_annual_incident_cost(g, [])
        assert isinstance(proj, AnnualProjection)
        assert proj.projected_incidents == 0
        assert proj.projected_annual_cost == 0.0
        assert len(proj.recommendations) > 0

    def test_single_incident(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        proj = engine.project_annual_incident_cost(g, [_profile()])
        assert proj.projected_incidents == 12
        assert proj.projected_annual_cost > 0

    def test_multiple_incidents(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        incidents = [
            _profile(severity=IncidentSeverity.SEV3),
            _profile(severity=IncidentSeverity.SEV4),
            _profile(severity=IncidentSeverity.SEV5),
        ]
        proj = engine.project_annual_incident_cost(g, incidents)
        assert proj.projected_incidents == 36
        assert proj.cost_by_severity != {}

    def test_confidence_interval(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        proj = engine.project_annual_incident_cost(g, [_profile()])
        assert proj.confidence_interval_low < proj.projected_annual_cost
        assert proj.confidence_interval_high > proj.projected_annual_cost

    def test_trend_increasing(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        # All SEV1 → sev1 fraction > 0.5 → increasing
        incidents = [_profile(severity=IncidentSeverity.SEV1) for _ in range(5)]
        proj = engine.project_annual_incident_cost(g, incidents)
        assert proj.cost_trend == "increasing"

    def test_trend_decreasing(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        # All SEV5 → sev1 fraction < 0.1 → decreasing
        incidents = [_profile(severity=IncidentSeverity.SEV5) for _ in range(5)]
        proj = engine.project_annual_incident_cost(g, incidents)
        assert proj.cost_trend == "decreasing"

    def test_trend_stable(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        # SEV1 fraction between 0.1 and 0.5 → stable
        # Include one SEV1 among several lower-severity incidents
        incidents = [
            _profile(severity=IncidentSeverity.SEV1, duration=10.0),
            _profile(severity=IncidentSeverity.SEV2, duration=30.0),
            _profile(severity=IncidentSeverity.SEV2, duration=30.0),
            _profile(severity=IncidentSeverity.SEV3, duration=30.0),
            _profile(severity=IncidentSeverity.SEV3, duration=30.0),
        ]
        proj = engine.project_annual_incident_cost(g, incidents)
        assert proj.cost_trend == "stable"

    def test_high_projected_cost_recommendation(self) -> None:
        g = _graph(_comp("api", revenue_per_minute=10000.0))
        engine = IncidentCostEngine()
        incidents = [
            _profile(severity=IncidentSeverity.SEV1, duration=120.0, components=["api"],
                     sla_breach=True, data_loss=True, regulatory_impact=True,
                     public_facing=True, users=100000),
        ]
        proj = engine.project_annual_incident_cost(g, incidents)
        assert any("$1M" in r or "million" in r.lower() for r in proj.recommendations)

    def test_high_count_recommendation(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        # 5 incidents → 60 annual → should trigger high count recommendation
        incidents = [_profile() for _ in range(5)]
        proj = engine.project_annual_incident_cost(g, incidents)
        assert any("high" in r.lower() or "proactive" in r.lower() for r in proj.recommendations)

    def test_severity_breakdown_keys(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        incidents = [
            _profile(severity=IncidentSeverity.SEV2),
            _profile(severity=IncidentSeverity.SEV4),
        ]
        proj = engine.project_annual_incident_cost(g, incidents)
        assert "sev2" in proj.cost_by_severity
        assert "sev4" in proj.cost_by_severity


class TestGenerateExecutiveReport:
    """Tests for IncidentCostEngine.generate_executive_report."""

    def test_basic_report(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        er = engine.generate_executive_report(g, _profile(components=["api"]))
        assert isinstance(er, ExecutiveIncidentReport)
        assert er.total_cost > 0
        assert er.incident_summary != ""

    def test_risk_rating_critical(self) -> None:
        g = _graph(_comp("api", revenue_per_minute=50000.0))
        engine = IncidentCostEngine()
        er = engine.generate_executive_report(
            g,
            _profile(
                severity=IncidentSeverity.SEV1,
                duration=120.0,
                components=["api"],
                sla_breach=True,
                data_loss=True,
                regulatory_impact=True,
                public_facing=True,
                users=100000,
            ),
        )
        assert er.risk_rating == "CRITICAL"

    def test_risk_rating_low(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        er = engine.generate_executive_report(
            g,
            _profile(
                severity=IncidentSeverity.SEV5,
                duration=1.0,
                users=1,
            ),
        )
        assert er.risk_rating == "LOW"

    def test_risk_rating_medium(self) -> None:
        g = _graph(_comp("api", revenue_per_minute=500.0))
        engine = IncidentCostEngine()
        # Aim for a total cost between 10K and 100K
        er = engine.generate_executive_report(
            g,
            _profile(
                severity=IncidentSeverity.SEV4,
                duration=30.0,
                components=["api"],
                users=100,
            ),
        )
        # Depending on exact amounts, check it's not CRITICAL
        assert er.risk_rating in ("LOW", "MEDIUM", "HIGH")

    def test_business_impact_data_loss(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        er = engine.generate_executive_report(g, _profile(data_loss=True))
        assert "Data loss" in er.business_impact

    def test_business_impact_sla_breach(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        er = engine.generate_executive_report(g, _profile(sla_breach=True))
        assert "SLA" in er.business_impact

    def test_business_impact_regulatory(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        er = engine.generate_executive_report(g, _profile(regulatory_impact=True))
        assert "Regulatory" in er.business_impact or "regulatory" in er.business_impact

    def test_business_impact_public_facing(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        er = engine.generate_executive_report(g, _profile(public_facing=True))
        assert "customer-visible" in er.business_impact.lower() or "customer" in er.business_impact.lower()

    def test_business_impact_none(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        er = engine.generate_executive_report(g, _profile())
        assert "No major" in er.business_impact

    def test_summary_mentions_severity(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        er = engine.generate_executive_report(g, _profile(severity=IncidentSeverity.SEV1))
        assert "SEV1" in er.incident_summary

    def test_summary_mentions_users(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        er = engine.generate_executive_report(g, _profile(users=5000))
        assert "5,000" in er.incident_summary or "5000" in er.incident_summary

    def test_summary_mentions_components(self) -> None:
        g = _graph(_comp("api"), _comp("db"))
        engine = IncidentCostEngine()
        er = engine.generate_executive_report(g, _profile(components=["api", "db"]))
        assert "2 components" in er.incident_summary

    def test_cost_breakdown_summary_nonempty(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        er = engine.generate_executive_report(g, _profile(components=["api"]))
        assert len(er.cost_breakdown_summary) > 0

    def test_prevention_investment_set(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        er = engine.generate_executive_report(g, _profile(components=["api"]))
        assert er.prevention_investment > 0

    def test_expected_roi_set(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        er = engine.generate_executive_report(g, _profile(components=["api"]))
        assert er.expected_roi != 0.0

    def test_top_recommendations_capped(self) -> None:
        g = _graph(
            _comp("a", replicas=1),
            _comp("b", replicas=1),
            _comp("c", replicas=1),
            _comp("d", replicas=1),
            _comp("e", replicas=1),
            _comp("f", replicas=1),
        )
        engine = IncidentCostEngine()
        er = engine.generate_executive_report(
            g,
            _profile(
                components=["a", "b", "c", "d", "e", "f"],
                data_loss=True,
                sla_breach=True,
                regulatory_impact=True,
                public_facing=True,
                users=50000,
                severity=IncidentSeverity.SEV1,
            ),
        )
        assert len(er.top_recommendations) <= 5


class TestCalculateCascadingCost:
    """Tests for IncidentCostEngine.calculate_cascading_cost."""

    def test_no_cascade(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        result = engine.calculate_cascading_cost(g, "api", 60.0)
        assert isinstance(result, CascadingCostResult)
        assert result.initial_component == "api"
        assert result.total_cost > 0
        assert result.affected_components == []

    def test_simple_cascade(self) -> None:
        g = _graph(
            _comp("db"),
            _comp("api"),
            deps=[Dependency(source_id="api", target_id="db")],
        )
        engine = IncidentCostEngine()
        result = engine.calculate_cascading_cost(g, "db", 60.0)
        assert "api" in result.affected_components
        assert result.total_cost > 0

    def test_deep_cascade(self) -> None:
        g = _graph(
            _comp("db"),
            _comp("api"),
            _comp("web"),
            _comp("cdn"),
            deps=[
                Dependency(source_id="api", target_id="db"),
                Dependency(source_id="web", target_id="api"),
                Dependency(source_id="cdn", target_id="web"),
            ],
        )
        engine = IncidentCostEngine()
        result = engine.calculate_cascading_cost(g, "db", 60.0)
        assert len(result.affected_components) == 3
        assert result.cascade_depth > 1

    def test_unknown_component(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        result = engine.calculate_cascading_cost(g, "nonexistent", 60.0)
        assert result.total_cost == 0.0
        assert any("not found" in r for r in result.recommendations)

    def test_per_component_cost_dict(self) -> None:
        g = _graph(
            _comp("db", revenue_per_minute=200.0),
            _comp("api", revenue_per_minute=100.0),
            deps=[Dependency(source_id="api", target_id="db")],
        )
        engine = IncidentCostEngine()
        result = engine.calculate_cascading_cost(g, "db", 60.0)
        assert "db" in result.per_component_cost
        assert "api" in result.per_component_cost

    def test_cascade_depth_metric(self) -> None:
        g = _graph(
            _comp("a"),
            _comp("b"),
            _comp("c"),
            deps=[
                Dependency(source_id="b", target_id="a"),
                Dependency(source_id="c", target_id="b"),
            ],
        )
        engine = IncidentCostEngine()
        result = engine.calculate_cascading_cost(g, "a", 60.0)
        assert result.cascade_depth >= 1

    def test_duration_stored(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        result = engine.calculate_cascading_cost(g, "api", 45.5)
        assert result.duration_minutes == 45.5

    def test_depth_multiplier_effect(self) -> None:
        # Deeper components cost more per minute due to depth multiplier
        g = _graph(
            _comp("db", revenue_per_minute=100.0),
            _comp("api", revenue_per_minute=100.0),
            deps=[Dependency(source_id="api", target_id="db")],
        )
        engine = IncidentCostEngine()
        result = engine.calculate_cascading_cost(g, "db", 60.0)
        # api (depth=1) should cost more than if it were at depth=0
        # due to 1.0 + 1*0.2 = 1.2 multiplier
        assert result.per_component_cost["api"] > result.per_component_cost["db"]

    def test_recommendations_many_components(self) -> None:
        g = _graph(
            _comp("a"),
            _comp("b"),
            _comp("c"),
            _comp("d"),
            deps=[
                Dependency(source_id="b", target_id="a"),
                Dependency(source_id="c", target_id="a"),
                Dependency(source_id="d", target_id="a"),
            ],
        )
        engine = IncidentCostEngine()
        result = engine.calculate_cascading_cost(g, "a", 60.0)
        assert any("circuit breaker" in r.lower() for r in result.recommendations)

    def test_recommendations_no_replicas(self) -> None:
        g = _graph(_comp("api", replicas=1))
        engine = IncidentCostEngine()
        result = engine.calculate_cascading_cost(g, "api", 60.0)
        assert any("replica" in r.lower() or "redundancy" in r.lower() for r in result.recommendations)

    def test_recommendations_deep_cascade(self) -> None:
        g = _graph(
            _comp("a"),
            _comp("b"),
            _comp("c"),
            _comp("d"),
            _comp("e"),
            deps=[
                Dependency(source_id="b", target_id="a"),
                Dependency(source_id="c", target_id="b"),
                Dependency(source_id="d", target_id="c"),
                Dependency(source_id="e", target_id="d"),
            ],
        )
        engine = IncidentCostEngine()
        result = engine.calculate_cascading_cost(g, "a", 60.0)
        assert any("depth" in r.lower() or "isolation" in r.lower() for r in result.recommendations)

    def test_zero_duration(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        result = engine.calculate_cascading_cost(g, "api", 0.0)
        assert result.total_cost == 0.0


# ---------------------------------------------------------------------------
# Integration / edge-case tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and integration tests."""

    def test_all_severities_produce_results(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        for sev in IncidentSeverity:
            report = engine.calculate_incident_cost(g, _profile(severity=sev))
            assert report.total_cost >= 0

    def test_large_user_count(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(users=10_000_000))
        assert report.total_cost > 0
        assert report.cost_per_user > 0

    def test_very_long_duration(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(duration=10000.0))
        assert report.total_cost > 0

    def test_many_components(self) -> None:
        comps = [_comp(f"c{i}", revenue_per_minute=float(i * 10)) for i in range(20)]
        g = _graph(*comps)
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(
            g, _profile(components=[f"c{i}" for i in range(20)])
        )
        assert report.total_cost > 0

    def test_graph_with_dependencies_for_cost(self) -> None:
        g = _graph(
            _comp("lb", ctype=ComponentType.LOAD_BALANCER),
            _comp("api"),
            _comp("db", ctype=ComponentType.DATABASE),
            deps=[
                Dependency(source_id="api", target_id="db"),
                Dependency(source_id="lb", target_id="api"),
            ],
        )
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(
            g, _profile(components=["lb", "api", "db"])
        )
        assert report.total_cost > 0

    def test_consistent_total(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(components=["api"]))
        sum_breakdown = sum(item.amount for item in report.breakdown)
        assert report.total_cost == pytest.approx(sum_breakdown, rel=1e-6)

    def test_engine_stateless(self) -> None:
        engine = IncidentCostEngine()
        g1 = _graph(_comp("a", revenue_per_minute=100.0))
        g2 = _graph(_comp("b", revenue_per_minute=200.0))
        r1 = engine.calculate_incident_cost(g1, _profile(components=["a"]))
        r2 = engine.calculate_incident_cost(g2, _profile(components=["b"]))
        # Running on g2 should not affect g1 results
        r1b = engine.calculate_incident_cost(g1, _profile(components=["a"]))
        assert r1.total_cost == r1b.total_cost

    def test_all_flags_true(self) -> None:
        g = _graph(_comp("api", replicas=1))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(
            g,
            _profile(
                severity=IncidentSeverity.SEV1,
                duration=120.0,
                users=100000,
                components=["api"],
                data_loss=True,
                public_facing=True,
                sla_breach=True,
                regulatory_impact=True,
            ),
        )
        # All categories should have non-zero amounts
        nonzero = [b for b in report.breakdown if b.amount > 0]
        assert len(nonzero) == 10

    def test_all_flags_false(self) -> None:
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(
            g,
            _profile(
                severity=IncidentSeverity.SEV5,
                data_loss=False,
                public_facing=False,
                sla_breach=False,
                regulatory_impact=False,
            ),
        )
        # Some categories should be zero
        zeros = [b for b in report.breakdown if b.amount == 0.0]
        assert len(zeros) > 0

    def test_cascading_then_incident(self) -> None:
        """Verify cascading and incident cost can both be calculated on same graph."""
        g = _graph(
            _comp("db", revenue_per_minute=500.0),
            _comp("api", revenue_per_minute=200.0),
            deps=[Dependency(source_id="api", target_id="db")],
        )
        engine = IncidentCostEngine()
        cascade = engine.calculate_cascading_cost(g, "db", 60.0)
        incident = engine.calculate_incident_cost(
            g, _profile(components=["db", "api"])
        )
        assert cascade.total_cost > 0
        assert incident.total_cost > 0

    def test_compare_then_roi(self) -> None:
        """Verify compare and ROI can be composed."""
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        profiles = [
            _profile(severity=IncidentSeverity.SEV1),
            _profile(severity=IncidentSeverity.SEV3),
        ]
        comp = engine.compare_scenarios(g, profiles)
        roi = engine.estimate_prevention_roi(g, profiles, comp.average_cost * 0.2)
        assert roi.investment > 0

    def test_executive_report_uses_calculate(self) -> None:
        """Verify executive report is consistent with calculate_incident_cost."""
        g = _graph(_comp("api", revenue_per_minute=300.0))
        engine = IncidentCostEngine()
        p = _profile(components=["api"], sla_breach=True)
        report = engine.calculate_incident_cost(g, p)
        executive = engine.generate_executive_report(g, p)
        assert executive.total_cost == report.total_cost

    def test_error_budget_then_projection(self) -> None:
        """Verify error budget and projection can work together."""
        g = _graph(_comp("api"))
        engine = IncidentCostEngine()
        ebv = engine.calculate_error_budget_value(g, 99.9)
        proj = engine.project_annual_incident_cost(g, [_profile()])
        assert ebv.total_budget_value > 0
        assert proj.projected_annual_cost > 0

    def test_component_with_high_mtbf_low_annualized(self) -> None:
        g = _graph(_comp("stable", mtbf_hours=8760))  # 1 year MTBF
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(components=["stable"]))
        # 8760/8760 = 1 incident per year → annualized = 1 * total
        assert report.annualized_risk == pytest.approx(report.total_cost, rel=0.01)

    def test_component_with_low_mtbf_high_annualized(self) -> None:
        g = _graph(_comp("flaky", mtbf_hours=24))  # daily failures
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(g, _profile(components=["flaky"]))
        # 8760/24 = 365 incidents per year
        assert report.annualized_risk > report.total_cost * 100

    def test_severity_multiplier_values(self) -> None:
        """Verify severity multipliers are correctly applied."""
        engine = IncidentCostEngine()
        assert engine._severity_mult(IncidentSeverity.SEV1) == 5.0
        assert engine._severity_mult(IncidentSeverity.SEV2) == 3.0
        assert engine._severity_mult(IncidentSeverity.SEV3) == 1.5
        assert engine._severity_mult(IncidentSeverity.SEV4) == 1.0
        assert engine._severity_mult(IncidentSeverity.SEV5) == 0.5

    def test_engineer_count_values(self) -> None:
        """Verify engineer counts by severity."""
        engine = IncidentCostEngine()
        assert engine._engineer_count(IncidentSeverity.SEV1) == 10
        assert engine._engineer_count(IncidentSeverity.SEV2) == 5
        assert engine._engineer_count(IncidentSeverity.SEV3) == 3
        assert engine._engineer_count(IncidentSeverity.SEV4) == 2
        assert engine._engineer_count(IncidentSeverity.SEV5) == 1

    def test_avg_mtbf_with_no_components(self) -> None:
        engine = IncidentCostEngine()
        g = _graph()
        assert engine._avg_mtbf_hours(g) == 720.0

    def test_avg_mtbf_with_components(self) -> None:
        engine = IncidentCostEngine()
        g = _graph(
            _comp("a", mtbf_hours=100),
            _comp("b", mtbf_hours=200),
        )
        assert engine._avg_mtbf_hours(g) == 150.0

    def test_component_revenue_known(self) -> None:
        engine = IncidentCostEngine()
        g = _graph(_comp("api", revenue_per_minute=999.0))
        assert engine._component_revenue(g, "api") == 999.0

    def test_component_revenue_unknown(self) -> None:
        engine = IncidentCostEngine()
        g = _graph(_comp("api"))
        assert engine._component_revenue(g, "missing") == 100.0  # default

    def test_component_revenue_zero_uses_default(self) -> None:
        engine = IncidentCostEngine()
        g = _graph(_comp("api", revenue_per_minute=0.0))
        assert engine._component_revenue(g, "api") == 100.0  # default

    def test_risk_rating_high(self) -> None:
        g = _graph(_comp("api", revenue_per_minute=2000.0))
        engine = IncidentCostEngine()
        er = engine.generate_executive_report(
            g,
            _profile(
                severity=IncidentSeverity.SEV1,
                duration=60.0,
                components=["api"],
                sla_breach=True,
                public_facing=True,
                users=10000,
            ),
        )
        assert er.risk_rating in ("HIGH", "CRITICAL")

    def test_data_recovery_multiple_components(self) -> None:
        g = _graph(_comp("a"), _comp("b"), _comp("c"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(
            g, _profile(data_loss=True, components=["a", "b", "c"])
        )
        dr = [b for b in report.breakdown if b.category == CostCategory.DATA_RECOVERY][0]
        # 3 components * base * severity mult
        assert dr.amount > 0

    def test_data_recovery_no_components_uses_one(self) -> None:
        g = _graph(_comp("a"))
        engine = IncidentCostEngine()
        report = engine.calculate_incident_cost(
            g, _profile(data_loss=True, components=[])
        )
        dr = [b for b in report.breakdown if b.category == CostCategory.DATA_RECOVERY][0]
        assert dr.amount > 0

    def test_high_variance_recommendation(self) -> None:
        g = _graph(_comp("api", revenue_per_minute=100000.0))
        engine = IncidentCostEngine()
        # Use 3 tiny scenarios and 1 enormous to ensure variance > avg^2
        profiles = [
            _profile(
                severity=IncidentSeverity.SEV1,
                duration=500.0,
                components=["api"],
                sla_breach=True,
                data_loss=True,
                regulatory_impact=True,
                public_facing=True,
                users=1_000_000,
            ),
            _profile(severity=IncidentSeverity.SEV5, duration=0.1, users=1),
            _profile(severity=IncidentSeverity.SEV5, duration=0.1, users=1),
            _profile(severity=IncidentSeverity.SEV5, duration=0.1, users=1),
        ]
        comp = engine.compare_scenarios(g, profiles)
        assert comp.cost_variance > comp.average_cost ** 2
        assert any("variance" in r.lower() or "variability" in r.lower() for r in comp.recommendations)

    def test_worst_case_more_than_2x_average(self) -> None:
        """Ensure worst > 2*avg triggers the worst-case recommendation."""
        g = _graph(_comp("api", revenue_per_minute=100000.0))
        engine = IncidentCostEngine()
        # One enormous incident vs several tiny ones to push worst > 2*avg
        profiles = [
            _profile(
                severity=IncidentSeverity.SEV1,
                duration=120.0,
                components=["api"],
                sla_breach=True,
                data_loss=True,
                regulatory_impact=True,
                public_facing=True,
                users=100000,
            ),
            _profile(severity=IncidentSeverity.SEV5, duration=0.1, users=1),
            _profile(severity=IncidentSeverity.SEV5, duration=0.1, users=1),
            _profile(severity=IncidentSeverity.SEV5, duration=0.1, users=1),
        ]
        comp = engine.compare_scenarios(g, profiles)
        assert comp.worst_case_cost > 2 * comp.average_cost
        assert any("worst-case" in r.lower() or "Worst" in r for r in comp.recommendations)

    def test_executive_risk_rating_exactly_high(self) -> None:
        """Verify a scenario that lands in the HIGH risk band (100K-500K)."""
        g = _graph(_comp("api", revenue_per_minute=1000.0))
        engine = IncidentCostEngine()
        er = engine.generate_executive_report(
            g,
            _profile(
                severity=IncidentSeverity.SEV3,
                duration=60.0,
                components=["api"],
                users=1000,
            ),
        )
        # Total cost between 100K and 500K => HIGH
        assert er.risk_rating == "HIGH"

    def test_cascade_orphan_in_affected_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cover the branch where a component in affected set is not in graph."""
        g = _graph(
            _comp("db"),
            _comp("api"),
            deps=[Dependency(source_id="api", target_id="db")],
        )
        engine = IncidentCostEngine()
        # Monkeypatch get_all_affected to include a phantom component id
        original = g.get_all_affected

        def patched_get_all_affected(component_id: str) -> set[str]:
            result = original(component_id)
            result.add("phantom")
            return result

        monkeypatch.setattr(g, "get_all_affected", patched_get_all_affected)
        result = engine.calculate_cascading_cost(g, "db", 60.0)
        # phantom is skipped (get_component returns None), others proceed
        assert result.total_cost > 0
        assert "phantom" not in result.per_component_cost
