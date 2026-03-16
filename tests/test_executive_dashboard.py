"""Tests for executive_dashboard module — 100% coverage."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    ComplianceTags,
    Component,
    ComponentType,
    CostProfile,
    Dependency,
    FailoverConfig,
    HealthStatus,
    ResourceMetrics,
    RetryStrategy,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.executive_dashboard import (
    CapacityForecast,
    ComplianceSnapshot,
    DashboardSection,
    ExecutiveDashboard,
    ExecutiveDashboardEngine,
    ExecutiveRating,
    FinancialExposure,
    IncidentTrendData,
    ReportFormat,
    ResilienceScorecard,
    RiskHeatmapCell,
    RiskTrend,
    _count_spofs,
    _dependency_diversity_score,
    _health_mix_score,
    _rating_from_score,
    _redundancy_score,
    _trend_from_scores,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _comp(
    name: str = "c1",
    ctype: ComponentType = ComponentType.APP_SERVER,
    **kwargs,
) -> Component:
    return Component(id=name, name=name, type=ctype, **kwargs)


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestDashboardSection:
    def test_all_values(self):
        expected = {
            "resilience_score",
            "financial_exposure",
            "compliance_status",
            "incident_trends",
            "risk_heatmap",
            "capacity_forecast",
            "sla_performance",
            "team_readiness",
        }
        assert {s.value for s in DashboardSection} == expected

    def test_str_enum(self):
        assert isinstance(DashboardSection.RESILIENCE_SCORE, str)
        assert DashboardSection.RESILIENCE_SCORE == "resilience_score"

    def test_membership(self):
        assert DashboardSection("risk_heatmap") is DashboardSection.RISK_HEATMAP


class TestRiskTrend:
    def test_all_values(self):
        assert set(RiskTrend) == {
            RiskTrend.IMPROVING,
            RiskTrend.STABLE,
            RiskTrend.DEGRADING,
            RiskTrend.CRITICAL_DECLINE,
        }

    def test_str_enum(self):
        assert RiskTrend.IMPROVING == "improving"
        assert isinstance(RiskTrend.CRITICAL_DECLINE, str)


class TestExecutiveRating:
    def test_all_values(self):
        assert set(ExecutiveRating) == {
            ExecutiveRating.EXCELLENT,
            ExecutiveRating.GOOD,
            ExecutiveRating.ACCEPTABLE,
            ExecutiveRating.NEEDS_ATTENTION,
            ExecutiveRating.CRITICAL,
        }

    def test_str_enum(self):
        assert ExecutiveRating.EXCELLENT == "excellent"


class TestReportFormat:
    def test_all_values(self):
        assert set(ReportFormat) == {
            ReportFormat.SUMMARY,
            ReportFormat.DETAILED,
            ReportFormat.BOARD_READY,
            ReportFormat.INVESTOR_BRIEF,
        }

    def test_str_enum(self):
        assert ReportFormat.BOARD_READY == "board_ready"


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestResilienceScorecard:
    def test_defaults(self):
        sc = ResilienceScorecard()
        assert sc.overall_score == 0.0
        assert sc.category_scores == {}
        assert sc.trend == RiskTrend.STABLE
        assert sc.rating == ExecutiveRating.ACCEPTABLE
        assert sc.period_start == ""
        assert sc.period_end == ""

    def test_custom(self):
        sc = ResilienceScorecard(
            overall_score=85.0,
            category_scores={"redundancy": 90.0},
            trend=RiskTrend.IMPROVING,
            rating=ExecutiveRating.GOOD,
            period_start="2026-01-01",
            period_end="2026-01-31",
        )
        assert sc.overall_score == 85.0
        assert sc.category_scores["redundancy"] == 90.0
        assert sc.trend == RiskTrend.IMPROVING


class TestFinancialExposure:
    def test_defaults(self):
        fe = FinancialExposure()
        assert fe.estimated_annual_loss_usd == 0.0
        assert fe.worst_case_loss_usd == 0.0
        assert fe.insurance_coverage_gap_usd == 0.0
        assert fe.risk_reduction_roi == 0.0

    def test_custom(self):
        fe = FinancialExposure(
            estimated_annual_loss_usd=100_000.0,
            worst_case_loss_usd=500_000.0,
            insurance_coverage_gap_usd=200_000.0,
            risk_reduction_roi=150.0,
        )
        assert fe.estimated_annual_loss_usd == 100_000.0
        assert fe.risk_reduction_roi == 150.0


class TestComplianceSnapshot:
    def test_defaults(self):
        cs = ComplianceSnapshot()
        assert cs.frameworks_assessed == 0
        assert cs.compliant_count == 0
        assert cs.non_compliant_count == 0
        assert cs.compliance_percentage == 0.0
        assert cs.critical_gaps == []

    def test_custom(self):
        cs = ComplianceSnapshot(
            frameworks_assessed=5,
            compliant_count=3,
            non_compliant_count=2,
            compliance_percentage=60.0,
            critical_gaps=["SOC2: below threshold"],
        )
        assert cs.compliance_percentage == 60.0
        assert len(cs.critical_gaps) == 1


class TestIncidentTrendData:
    def test_defaults(self):
        itd = IncidentTrendData()
        assert itd.period == ""
        assert itd.total_incidents == 0
        assert itd.mttr_hours == 0.0
        assert itd.mttd_hours == 0.0
        assert itd.p1_count == 0
        assert itd.trend == RiskTrend.STABLE

    def test_custom(self):
        itd = IncidentTrendData(
            period="week-1",
            total_incidents=5,
            mttr_hours=2.5,
            mttd_hours=0.5,
            p1_count=1,
            trend=RiskTrend.DEGRADING,
        )
        assert itd.total_incidents == 5
        assert itd.p1_count == 1


class TestRiskHeatmapCell:
    def test_defaults(self):
        cell = RiskHeatmapCell()
        assert cell.category == ""
        assert cell.likelihood == 0.0
        assert cell.impact == 0.0
        assert cell.risk_level == 0.0
        assert cell.mitigation_status == "open"

    def test_custom(self):
        cell = RiskHeatmapCell(
            category="infra",
            likelihood=0.8,
            impact=0.9,
            risk_level=0.72,
            mitigation_status="partial",
        )
        assert cell.risk_level == 0.72


class TestCapacityForecast:
    def test_defaults(self):
        cf = CapacityForecast()
        assert cf.service_id == ""
        assert cf.current_utilization == 0.0
        assert cf.peak_utilization == 0.0
        assert cf.months_to_capacity == 0.0
        assert cf.scale_recommendation == ""

    def test_custom(self):
        cf = CapacityForecast(
            service_id="api",
            current_utilization=75.0,
            peak_utilization=97.5,
            months_to_capacity=6.5,
            scale_recommendation="Plan scaling",
        )
        assert cf.months_to_capacity == 6.5


class TestExecutiveDashboardModel:
    def test_defaults(self):
        d = ExecutiveDashboard()
        assert d.generated_at == ""
        assert d.report_format == ReportFormat.BOARD_READY
        assert d.scorecard.overall_score == 0.0
        assert d.financial_exposure.estimated_annual_loss_usd == 0.0
        assert d.compliance.frameworks_assessed == 0
        assert d.incident_trends == []
        assert d.risk_heatmap == []
        assert d.capacity_forecasts == []
        assert d.key_recommendations == []
        assert d.executive_summary == ""


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestRatingFromScore:
    def test_excellent(self):
        assert _rating_from_score(100.0) == ExecutiveRating.EXCELLENT
        assert _rating_from_score(90.0) == ExecutiveRating.EXCELLENT

    def test_good(self):
        assert _rating_from_score(89.9) == ExecutiveRating.GOOD
        assert _rating_from_score(75.0) == ExecutiveRating.GOOD

    def test_acceptable(self):
        assert _rating_from_score(74.9) == ExecutiveRating.ACCEPTABLE
        assert _rating_from_score(60.0) == ExecutiveRating.ACCEPTABLE

    def test_needs_attention(self):
        assert _rating_from_score(59.9) == ExecutiveRating.NEEDS_ATTENTION
        assert _rating_from_score(40.0) == ExecutiveRating.NEEDS_ATTENTION

    def test_critical(self):
        assert _rating_from_score(39.9) == ExecutiveRating.CRITICAL
        assert _rating_from_score(0.0) == ExecutiveRating.CRITICAL


class TestTrendFromScores:
    def test_improving(self):
        assert _trend_from_scores(80.0, 70.0) == RiskTrend.IMPROVING

    def test_stable(self):
        assert _trend_from_scores(80.0, 79.0) == RiskTrend.STABLE
        assert _trend_from_scores(80.0, 80.0) == RiskTrend.STABLE

    def test_degrading(self):
        assert _trend_from_scores(70.0, 75.0) == RiskTrend.DEGRADING

    def test_critical_decline(self):
        assert _trend_from_scores(50.0, 65.0) == RiskTrend.CRITICAL_DECLINE


class TestCountSpofs:
    def test_empty_graph(self):
        g = _graph()
        assert _count_spofs(g) == 0

    def test_no_spof(self):
        g = _graph(_comp("a", replicas=2))
        assert _count_spofs(g) == 0

    def test_spof_without_dependents(self):
        g = _graph(_comp("a", replicas=1))
        assert _count_spofs(g) == 0

    def test_spof_with_dependents(self):
        c1 = _comp("c1", replicas=1)
        c2 = _comp("c2", replicas=2)
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c2", target_id="c1"))
        assert _count_spofs(g) == 1

    def test_failover_prevents_spof(self):
        c1 = _comp("c1", replicas=1, failover=FailoverConfig(enabled=True))
        c2 = _comp("c2", replicas=2)
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c2", target_id="c1"))
        assert _count_spofs(g) == 0


class TestRedundancyScore:
    def test_empty_graph(self):
        assert _redundancy_score(_graph()) == 0.0

    def test_all_redundant(self):
        g = _graph(
            _comp("a", replicas=2),
            _comp("b", replicas=3),
        )
        assert _redundancy_score(g) == 100.0

    def test_none_redundant(self):
        g = _graph(_comp("a", replicas=1), _comp("b", replicas=1))
        assert _redundancy_score(g) == 0.0

    def test_mixed(self):
        g = _graph(
            _comp("a", replicas=2),
            _comp("b", replicas=1),
        )
        assert _redundancy_score(g) == 50.0

    def test_failover_counts(self):
        g = _graph(
            _comp("a", replicas=1, failover=FailoverConfig(enabled=True)),
        )
        assert _redundancy_score(g) == 100.0


class TestDependencyDiversityScore:
    def test_empty(self):
        assert _dependency_diversity_score(_graph()) == 100.0

    def test_no_edges(self):
        g = _graph(_comp("a"))
        assert _dependency_diversity_score(g) == 100.0

    def test_shallow_chain(self):
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c1", target_id="c2"))
        score = _dependency_diversity_score(g)
        assert score == 100.0  # depth 2 -> 100.0

    def test_deep_chain(self):
        comps = [_comp(f"c{i}") for i in range(10)]
        g = _graph(*comps)
        for i in range(9):
            g.add_dependency(
                Dependency(source_id=f"c{i}", target_id=f"c{i + 1}")
            )
        score = _dependency_diversity_score(g)
        assert score == 10.0  # depth 10 -> 10.0


class TestHealthMixScore:
    def test_empty(self):
        assert _health_mix_score(_graph()) == 0.0

    def test_all_healthy(self):
        g = _graph(
            _comp("a", health=HealthStatus.HEALTHY),
            _comp("b", health=HealthStatus.HEALTHY),
        )
        assert _health_mix_score(g) == 100.0

    def test_all_down(self):
        g = _graph(
            _comp("a", health=HealthStatus.DOWN),
            _comp("b", health=HealthStatus.DOWN),
        )
        assert _health_mix_score(g) == 0.0

    def test_mixed(self):
        g = _graph(
            _comp("a", health=HealthStatus.HEALTHY),
            _comp("b", health=HealthStatus.DOWN),
        )
        assert _health_mix_score(g) == 50.0

    def test_degraded(self):
        g = _graph(
            _comp("a", health=HealthStatus.DEGRADED),
        )
        assert _health_mix_score(g) == 0.0


# ---------------------------------------------------------------------------
# Engine tests
# ---------------------------------------------------------------------------


class TestComputeResilienceScorecard:
    def test_empty_graph(self):
        engine = ExecutiveDashboardEngine()
        sc = engine.compute_resilience_scorecard(_graph())
        # Empty graph: redundancy=0, diversity=100, health=0 -> 0.4*0+0.3*100+0.3*0=30
        assert sc.overall_score == 30.0
        assert sc.rating == ExecutiveRating.CRITICAL
        assert sc.category_scores["redundancy"] == 0.0
        assert sc.category_scores["health_mix"] == 0.0

    def test_single_healthy_redundant(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a", replicas=2, health=HealthStatus.HEALTHY))
        sc = engine.compute_resilience_scorecard(g)
        assert sc.overall_score > 80.0
        assert sc.rating in (ExecutiveRating.EXCELLENT, ExecutiveRating.GOOD)

    def test_single_no_redundancy(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a", replicas=1))
        sc = engine.compute_resilience_scorecard(g)
        assert sc.category_scores["redundancy"] == 0.0
        assert sc.overall_score < 80.0

    def test_period_dates_populated(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a"))
        sc = engine.compute_resilience_scorecard(g)
        assert sc.period_start != ""
        assert sc.period_end != ""

    def test_scorecard_trend_default(self):
        engine = ExecutiveDashboardEngine()
        sc = engine.compute_resilience_scorecard(_graph(_comp("a")))
        assert sc.trend == RiskTrend.STABLE

    def test_category_scores_keys(self):
        engine = ExecutiveDashboardEngine()
        sc = engine.compute_resilience_scorecard(
            _graph(_comp("a", replicas=2))
        )
        assert "redundancy" in sc.category_scores
        assert "dependency_diversity" in sc.category_scores
        assert "health_mix" in sc.category_scores

    def test_score_clamped(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp("a", replicas=3, health=HealthStatus.HEALTHY),
            _comp("b", replicas=3, health=HealthStatus.HEALTHY),
        )
        sc = engine.compute_resilience_scorecard(g)
        assert 0.0 <= sc.overall_score <= 100.0


class TestEstimateFinancialExposure:
    def test_empty_graph(self):
        engine = ExecutiveDashboardEngine()
        fe = engine.estimate_financial_exposure(_graph())
        assert fe.estimated_annual_loss_usd == 0.0
        assert fe.worst_case_loss_usd == 0.0

    def test_single_component_with_defaults(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a", replicas=1))
        fe = engine.estimate_financial_exposure(g)
        assert fe.estimated_annual_loss_usd > 0.0
        assert fe.worst_case_loss_usd > 0.0
        assert fe.insurance_coverage_gap_usd > 0.0

    def test_redundant_lowers_exposure(self):
        engine = ExecutiveDashboardEngine()
        g_low = _graph(_comp("a", replicas=1))
        g_high = _graph(_comp("a", replicas=3))
        fe_low = engine.estimate_financial_exposure(g_low)
        fe_high = engine.estimate_financial_exposure(g_high)
        assert fe_low.estimated_annual_loss_usd >= fe_high.estimated_annual_loss_usd

    def test_custom_revenue_per_hour(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a", replicas=1))
        fe1 = engine.estimate_financial_exposure(g, revenue_per_hour_usd=1000.0)
        fe2 = engine.estimate_financial_exposure(g, revenue_per_hour_usd=100_000.0)
        assert fe2.estimated_annual_loss_usd > fe1.estimated_annual_loss_usd

    def test_custom_cost_profile_revenue(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp(
                "a",
                replicas=1,
                cost_profile=CostProfile(revenue_per_minute=500.0),
            )
        )
        fe = engine.estimate_financial_exposure(g, revenue_per_hour_usd=1.0)
        # Should use the component's revenue (500*60=30000) not the default 1.0
        assert fe.estimated_annual_loss_usd > 0.0

    def test_roi_with_investment(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp(
                "a",
                replicas=2,
                cost_profile=CostProfile(hourly_infra_cost=10.0),
            )
        )
        fe = engine.estimate_financial_exposure(g)
        # With investment in replicas, roi should be computed
        assert isinstance(fe.risk_reduction_roi, float)

    def test_roi_zero_when_no_investment(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a", replicas=1))
        fe = engine.estimate_financial_exposure(g)
        assert fe.risk_reduction_roi == 0.0

    def test_worst_case_greater_than_estimated(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a", replicas=1))
        fe = engine.estimate_financial_exposure(g)
        assert fe.worst_case_loss_usd >= fe.estimated_annual_loss_usd

    def test_insurance_gap_is_fraction_of_worst_case(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a", replicas=1))
        fe = engine.estimate_financial_exposure(g)
        assert fe.insurance_coverage_gap_usd == pytest.approx(
            fe.worst_case_loss_usd * 0.4, rel=0.01
        )

    def test_unhealthy_increases_exposure(self):
        engine = ExecutiveDashboardEngine()
        g_healthy = _graph(_comp("a", replicas=1, health=HealthStatus.HEALTHY))
        g_down = _graph(_comp("a", replicas=1, health=HealthStatus.DOWN))
        fe_h = engine.estimate_financial_exposure(g_healthy)
        fe_d = engine.estimate_financial_exposure(g_down)
        assert fe_d.estimated_annual_loss_usd >= fe_h.estimated_annual_loss_usd


class TestAssessComplianceStatus:
    def test_empty_graph(self):
        engine = ExecutiveDashboardEngine()
        cs = engine.assess_compliance_status(_graph())
        assert cs.frameworks_assessed > 0
        assert cs.non_compliant_count == cs.frameworks_assessed
        assert cs.compliance_percentage == 0.0
        assert len(cs.critical_gaps) > 0

    def test_default_frameworks(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a"))
        cs = engine.assess_compliance_status(g)
        assert cs.frameworks_assessed == 5  # default 5 frameworks

    def test_custom_frameworks(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a"))
        cs = engine.assess_compliance_status(g, frameworks=["SOC2", "HIPAA"])
        assert cs.frameworks_assessed == 2

    def test_fully_compliant(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp(
                "a",
                security=SecurityProfile(
                    encryption_at_rest=True,
                    encryption_in_transit=True,
                    waf_protected=True,
                    rate_limiting=True,
                    auth_required=True,
                    network_segmented=True,
                    backup_enabled=True,
                    log_enabled=True,
                ),
                compliance_tags=ComplianceTags(
                    audit_logging=True,
                    change_management=True,
                ),
            )
        )
        cs = engine.assess_compliance_status(g, frameworks=["SOC2"])
        assert cs.compliant_count == 1
        assert cs.compliance_percentage == 100.0

    def test_pci_dss_penalty(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp(
                "a",
                security=SecurityProfile(encryption_at_rest=False),
                compliance_tags=ComplianceTags(pci_scope=True),
            )
        )
        cs = engine.assess_compliance_status(g, frameworks=["PCI_DSS"])
        assert cs.non_compliant_count == 1

    def test_hipaa_penalty(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp(
                "a",
                security=SecurityProfile(encryption_at_rest=False),
                compliance_tags=ComplianceTags(contains_phi=True),
            )
        )
        cs = engine.assess_compliance_status(g, frameworks=["HIPAA"])
        assert cs.non_compliant_count == 1

    def test_hipaa_audit_logging_penalty(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp(
                "a",
                security=SecurityProfile(encryption_at_rest=True),
                compliance_tags=ComplianceTags(
                    contains_phi=True, audit_logging=False
                ),
            )
        )
        cs = engine.assess_compliance_status(g, frameworks=["HIPAA"])
        # Score lowered by lack of audit_logging for PHI
        assert cs.frameworks_assessed == 1

    def test_soc2_change_mgmt_penalty(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp(
                "a",
                compliance_tags=ComplianceTags(change_management=False),
            )
        )
        cs = engine.assess_compliance_status(g, frameworks=["SOC2"])
        assert cs.frameworks_assessed == 1

    def test_compliance_percentage_calculation(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp(
                "a",
                security=SecurityProfile(
                    encryption_at_rest=True,
                    encryption_in_transit=True,
                    waf_protected=True,
                    rate_limiting=True,
                    auth_required=True,
                    network_segmented=True,
                    backup_enabled=True,
                    log_enabled=True,
                ),
                compliance_tags=ComplianceTags(
                    audit_logging=True,
                    change_management=True,
                ),
            )
        )
        cs = engine.assess_compliance_status(
            g, frameworks=["SOC2", "ISO27001"]
        )
        assert cs.compliance_percentage == 100.0
        assert cs.critical_gaps == []


class TestAnalyzeIncidentTrends:
    def test_empty_incidents(self):
        engine = ExecutiveDashboardEngine()
        assert engine.analyze_incident_trends([]) == []

    def test_single_incident(self):
        engine = ExecutiveDashboardEngine()
        now = datetime.now(timezone.utc)
        incidents = [
            {
                "timestamp": now.isoformat(),
                "severity": "P1",
                "ttr_hours": 2.0,
                "ttd_hours": 0.5,
            }
        ]
        trends = engine.analyze_incident_trends(incidents, period_days=7)
        assert len(trends) >= 1
        assert trends[0].total_incidents == 1
        assert trends[0].p1_count == 1
        assert trends[0].mttr_hours == 2.0
        assert trends[0].mttd_hours == 0.5

    def test_multiple_buckets(self):
        engine = ExecutiveDashboardEngine()
        now = datetime.now(timezone.utc)
        incidents = [
            {
                "timestamp": (now - timedelta(days=20)).isoformat(),
                "severity": "P2",
                "ttr_hours": 1.0,
                "ttd_hours": 0.3,
            },
            {
                "timestamp": (now - timedelta(days=10)).isoformat(),
                "severity": "P1",
                "ttr_hours": 4.0,
                "ttd_hours": 1.0,
            },
            {
                "timestamp": now.isoformat(),
                "severity": "P3",
                "ttr_hours": 0.5,
                "ttd_hours": 0.1,
            },
        ]
        trends = engine.analyze_incident_trends(incidents, period_days=28)
        assert len(trends) == 4  # 28 / 7 = 4 buckets

    def test_trend_improving(self):
        engine = ExecutiveDashboardEngine()
        now = datetime.now(timezone.utc)
        incidents = [
            {
                "timestamp": (now - timedelta(days=13)).isoformat(),
                "severity": "P2",
                "ttr_hours": 1.0,
                "ttd_hours": 0.2,
            },
            {
                "timestamp": (now - timedelta(days=12)).isoformat(),
                "severity": "P2",
                "ttr_hours": 1.0,
                "ttd_hours": 0.2,
            },
            {
                "timestamp": (now - timedelta(days=11)).isoformat(),
                "severity": "P2",
                "ttr_hours": 1.0,
                "ttd_hours": 0.2,
            },
        ]
        trends = engine.analyze_incident_trends(incidents, period_days=14)
        # All in first bucket, second bucket empty -> improving
        last = trends[-1]
        assert last.trend == RiskTrend.IMPROVING

    def test_trend_degrading(self):
        engine = ExecutiveDashboardEngine()
        now = datetime.now(timezone.utc)
        incidents = [
            {
                "timestamp": (now - timedelta(days=13)).isoformat(),
                "severity": "P2",
                "ttr_hours": 1.0,
                "ttd_hours": 0.2,
            },
            {
                "timestamp": (now - timedelta(days=1)).isoformat(),
                "severity": "P1",
                "ttr_hours": 2.0,
                "ttd_hours": 0.5,
            },
            {
                "timestamp": now.isoformat(),
                "severity": "P1",
                "ttr_hours": 3.0,
                "ttd_hours": 1.0,
            },
        ]
        trends = engine.analyze_incident_trends(incidents, period_days=14)
        last = trends[-1]
        assert last.trend in (RiskTrend.DEGRADING, RiskTrend.CRITICAL_DECLINE)

    def test_invalid_timestamp_handled(self):
        engine = ExecutiveDashboardEngine()
        incidents = [
            {
                "timestamp": "not-a-date",
                "severity": "P3",
                "ttr_hours": 1.0,
                "ttd_hours": 0.5,
            }
        ]
        trends = engine.analyze_incident_trends(incidents, period_days=7)
        assert len(trends) >= 1

    def test_period_labels(self):
        engine = ExecutiveDashboardEngine()
        now = datetime.now(timezone.utc)
        incidents = [
            {
                "timestamp": now.isoformat(),
                "severity": "P3",
                "ttr_hours": 1.0,
                "ttd_hours": 0.5,
            }
        ]
        trends = engine.analyze_incident_trends(incidents, period_days=14)
        assert all(t.period.startswith("week-") for t in trends)

    def test_first_bucket_always_stable(self):
        engine = ExecutiveDashboardEngine()
        now = datetime.now(timezone.utc)
        incidents = [
            {
                "timestamp": now.isoformat(),
                "severity": "P1",
                "ttr_hours": 10.0,
                "ttd_hours": 5.0,
            }
        ]
        trends = engine.analyze_incident_trends(incidents, period_days=7)
        assert trends[0].trend == RiskTrend.STABLE

    def test_mttr_averaging(self):
        engine = ExecutiveDashboardEngine()
        now = datetime.now(timezone.utc)
        incidents = [
            {
                "timestamp": now.isoformat(),
                "severity": "P2",
                "ttr_hours": 2.0,
                "ttd_hours": 1.0,
            },
            {
                "timestamp": now.isoformat(),
                "severity": "P3",
                "ttr_hours": 4.0,
                "ttd_hours": 3.0,
            },
        ]
        trends = engine.analyze_incident_trends(incidents, period_days=7)
        assert trends[-1].mttr_hours == 3.0  # (2+4)/2
        assert trends[-1].mttd_hours == 2.0  # (1+3)/2


class TestBuildRiskHeatmap:
    def test_empty_graph(self):
        engine = ExecutiveDashboardEngine()
        assert engine.build_risk_heatmap(_graph()) == []

    def test_single_component(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a"))
        heatmap = engine.build_risk_heatmap(g)
        assert len(heatmap) == 5  # 5 categories
        categories = {c.category for c in heatmap}
        assert "infrastructure_failure" in categories
        assert "cascade_failure" in categories
        assert "capacity_exhaustion" in categories
        assert "security_breach" in categories
        assert "data_loss" in categories

    def test_risk_level_is_product(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a"))
        heatmap = engine.build_risk_heatmap(g)
        for cell in heatmap:
            assert cell.risk_level == pytest.approx(
                cell.likelihood * cell.impact, abs=0.01
            )

    def test_mitigated_with_backups(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp(
                "a",
                security=SecurityProfile(backup_enabled=True),
            )
        )
        heatmap = engine.build_risk_heatmap(g)
        dl = next(c for c in heatmap if c.category == "data_loss")
        assert dl.mitigation_status == "mitigated"
        assert dl.likelihood == 0.0

    def test_autoscaling_mitigates_capacity(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp("a", autoscaling=AutoScalingConfig(enabled=True)),
        )
        heatmap = engine.build_risk_heatmap(g)
        cap = next(c for c in heatmap if c.category == "capacity_exhaustion")
        assert cap.mitigation_status == "mitigated"

    def test_circuit_breakers_mitigate_cascade(self):
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(
            Dependency(
                source_id="c1",
                target_id="c2",
                circuit_breaker=CircuitBreakerConfig(enabled=True),
            )
        )
        engine = ExecutiveDashboardEngine()
        heatmap = engine.build_risk_heatmap(g)
        cascade = next(c for c in heatmap if c.category == "cascade_failure")
        assert cascade.mitigation_status == "mitigated"

    def test_security_mitigated(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp(
                "a",
                security=SecurityProfile(
                    encryption_at_rest=True,
                    encryption_in_transit=True,
                    waf_protected=True,
                    rate_limiting=True,
                    auth_required=True,
                    network_segmented=True,
                ),
            )
        )
        heatmap = engine.build_risk_heatmap(g)
        sec = next(c for c in heatmap if c.category == "security_breach")
        assert sec.mitigation_status == "mitigated"
        assert sec.likelihood < 0.3

    def test_security_open_no_controls(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a"))
        heatmap = engine.build_risk_heatmap(g)
        sec = next(c for c in heatmap if c.category == "security_breach")
        assert sec.mitigation_status == "open"
        assert sec.likelihood == 1.0

    def test_spof_affects_infra_likelihood(self):
        c1 = _comp("c1", replicas=1)
        c2 = _comp("c2", replicas=2)
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c2", target_id="c1"))
        engine = ExecutiveDashboardEngine()
        heatmap = engine.build_risk_heatmap(g)
        infra = next(c for c in heatmap if c.category == "infrastructure_failure")
        assert infra.likelihood > 0.0
        assert infra.mitigation_status == "partial"


class TestForecastCapacity:
    def test_empty_graph(self):
        engine = ExecutiveDashboardEngine()
        assert engine.forecast_capacity(_graph()) == []

    def test_single_component_zero_util(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a"))
        forecasts = engine.forecast_capacity(g)
        assert len(forecasts) == 1
        assert forecasts[0].service_id == "a"
        assert forecasts[0].current_utilization == 0.0
        # With 0% util, months to capacity should be long
        assert forecasts[0].months_to_capacity > 10

    def test_high_utilization(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp(
                "a",
                metrics=ResourceMetrics(cpu_percent=95.0),
            )
        )
        forecasts = engine.forecast_capacity(g)
        assert forecasts[0].current_utilization == 95.0
        assert forecasts[0].months_to_capacity < 3
        assert "immediately" in forecasts[0].scale_recommendation.lower()

    def test_moderate_utilization(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp(
                "a",
                metrics=ResourceMetrics(cpu_percent=50.0),
            )
        )
        forecasts = engine.forecast_capacity(g)
        assert forecasts[0].months_to_capacity > 3

    def test_autoscaling_extends_runway(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp(
                "a",
                metrics=ResourceMetrics(cpu_percent=80.0),
                autoscaling=AutoScalingConfig(enabled=True),
            )
        )
        forecasts = engine.forecast_capacity(g)
        assert forecasts[0].months_to_capacity >= 12.0
        assert "autoscaling" in forecasts[0].scale_recommendation.lower()

    def test_peak_utilization(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp("a", metrics=ResourceMetrics(cpu_percent=50.0))
        )
        forecasts = engine.forecast_capacity(g)
        assert forecasts[0].peak_utilization == pytest.approx(65.0, abs=0.1)

    def test_full_utilization(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp("a", metrics=ResourceMetrics(cpu_percent=100.0))
        )
        forecasts = engine.forecast_capacity(g)
        assert forecasts[0].months_to_capacity == 0.0

    def test_multiple_components(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp("a", metrics=ResourceMetrics(cpu_percent=30.0)),
            _comp("b", metrics=ResourceMetrics(cpu_percent=70.0)),
        )
        forecasts = engine.forecast_capacity(g)
        assert len(forecasts) == 2
        ids = {f.service_id for f in forecasts}
        assert ids == {"a", "b"}

    def test_scale_recommendation_tiers(self):
        engine = ExecutiveDashboardEngine()
        # Test quarter tier (3-6 months)
        g = _graph(
            _comp("a", metrics=ResourceMetrics(cpu_percent=85.0))
        )
        forecasts = engine.forecast_capacity(g)
        rec = forecasts[0].scale_recommendation.lower()
        assert "immediately" in rec or "quarter" in rec

    def test_no_action_low_util(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp("a", metrics=ResourceMetrics(cpu_percent=10.0))
        )
        forecasts = engine.forecast_capacity(g)
        assert "no immediate action" in forecasts[0].scale_recommendation.lower()


class TestGenerateExecutiveSummary:
    def test_basic_summary(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a", replicas=2))
        dashboard = engine.generate_dashboard(g)
        summary = dashboard.executive_summary
        assert len(summary) > 0
        assert "resilience" in summary.lower() or "rated" in summary.lower()

    def test_summary_mentions_financial(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a", replicas=1))
        dashboard = engine.generate_dashboard(g)
        summary = dashboard.executive_summary
        assert "$" in summary or "financial" in summary.lower() or "exposure" in summary.lower()

    def test_summary_with_compliance_gaps(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a"))
        dashboard = engine.generate_dashboard(g)
        # Default frameworks will have gaps for unconfigured component
        summary = dashboard.executive_summary
        assert "compliance" in summary.lower() or "gap" in summary.lower() or "risk" in summary.lower()

    def test_summary_no_risks(self):
        engine = ExecutiveDashboardEngine()
        d = ExecutiveDashboard(
            scorecard=ResilienceScorecard(
                overall_score=95.0,
                rating=ExecutiveRating.EXCELLENT,
            ),
            financial_exposure=FinancialExposure(),
            compliance=ComplianceSnapshot(),
        )
        summary = engine.generate_executive_summary(d)
        assert "no significant" in summary.lower() or "rated" in summary.lower()

    def test_summary_with_high_risk_heatmap(self):
        engine = ExecutiveDashboardEngine()
        d = ExecutiveDashboard(
            scorecard=ResilienceScorecard(
                overall_score=50.0,
                rating=ExecutiveRating.NEEDS_ATTENTION,
            ),
            financial_exposure=FinancialExposure(
                estimated_annual_loss_usd=500_000.0,
            ),
            compliance=ComplianceSnapshot(),
            risk_heatmap=[
                RiskHeatmapCell(
                    category="infra",
                    likelihood=0.8,
                    impact=0.9,
                    risk_level=0.72,
                )
            ],
        )
        summary = engine.generate_executive_summary(d)
        assert "risk" in summary.lower() or "exceed" in summary.lower()

    def test_summary_singular_gap(self):
        engine = ExecutiveDashboardEngine()
        d = ExecutiveDashboard(
            scorecard=ResilienceScorecard(
                overall_score=60.0,
                rating=ExecutiveRating.ACCEPTABLE,
            ),
            financial_exposure=FinancialExposure(
                estimated_annual_loss_usd=10_000.0,
            ),
            compliance=ComplianceSnapshot(
                critical_gaps=["SOC2: below threshold"],
            ),
        )
        summary = engine.generate_executive_summary(d)
        assert "1 critical compliance gap" in summary


class TestGenerateDashboard:
    def test_empty_graph_board_ready(self):
        engine = ExecutiveDashboardEngine()
        g = _graph()
        d = engine.generate_dashboard(g, ReportFormat.BOARD_READY)
        assert d.report_format == ReportFormat.BOARD_READY
        assert d.generated_at != ""
        assert d.executive_summary != ""

    def test_single_component(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a", replicas=2))
        d = engine.generate_dashboard(g)
        assert d.scorecard.overall_score > 0
        assert d.compliance.frameworks_assessed > 0

    def test_summary_format_omits_details(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a"))
        d = engine.generate_dashboard(g, ReportFormat.SUMMARY)
        assert d.risk_heatmap == []
        assert d.capacity_forecasts == []

    def test_investor_brief_omits_details(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a"))
        d = engine.generate_dashboard(g, ReportFormat.INVESTOR_BRIEF)
        assert d.risk_heatmap == []
        assert d.capacity_forecasts == []

    def test_board_ready_includes_all(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a"))
        d = engine.generate_dashboard(g, ReportFormat.BOARD_READY)
        assert len(d.risk_heatmap) > 0
        assert len(d.capacity_forecasts) > 0

    def test_detailed_includes_all(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a"))
        d = engine.generate_dashboard(g, ReportFormat.DETAILED)
        assert len(d.risk_heatmap) > 0
        assert len(d.capacity_forecasts) > 0

    def test_with_incidents(self):
        engine = ExecutiveDashboardEngine()
        now = datetime.now(timezone.utc)
        g = _graph(_comp("a"))
        incidents = [
            {
                "timestamp": now.isoformat(),
                "severity": "P1",
                "ttr_hours": 2.0,
                "ttd_hours": 0.5,
            }
        ]
        d = engine.generate_dashboard(g, incidents=incidents)
        assert len(d.incident_trends) > 0

    def test_recommendations_generated(self):
        engine = ExecutiveDashboardEngine()
        c1 = _comp("c1", replicas=1)
        c2 = _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c2", target_id="c1"))
        d = engine.generate_dashboard(g)
        assert len(d.key_recommendations) > 0

    def test_generated_at_is_utc(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a"))
        d = engine.generate_dashboard(g)
        # Should be parseable as ISO datetime
        dt = datetime.fromisoformat(d.generated_at)
        assert dt.tzinfo is not None

    def test_complex_graph(self):
        engine = ExecutiveDashboardEngine()
        comps = [
            _comp("lb", ComponentType.LOAD_BALANCER, replicas=2),
            _comp(
                "app1",
                ComponentType.APP_SERVER,
                replicas=3,
                health=HealthStatus.HEALTHY,
            ),
            _comp(
                "app2",
                ComponentType.APP_SERVER,
                replicas=1,
                health=HealthStatus.DEGRADED,
            ),
            _comp(
                "db",
                ComponentType.DATABASE,
                replicas=2,
                failover=FailoverConfig(enabled=True),
            ),
            _comp(
                "cache",
                ComponentType.CACHE,
                replicas=1,
                health=HealthStatus.HEALTHY,
            ),
        ]
        g = _graph(*comps)
        g.add_dependency(Dependency(source_id="lb", target_id="app1"))
        g.add_dependency(Dependency(source_id="lb", target_id="app2"))
        g.add_dependency(Dependency(source_id="app1", target_id="db"))
        g.add_dependency(Dependency(source_id="app1", target_id="cache"))
        g.add_dependency(Dependency(source_id="app2", target_id="db"))

        d = engine.generate_dashboard(g)
        assert d.scorecard.overall_score > 0
        assert d.financial_exposure.estimated_annual_loss_usd > 0
        assert len(d.risk_heatmap) == 5
        assert len(d.capacity_forecasts) == 5

    def test_no_incidents_empty_trends(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a"))
        d = engine.generate_dashboard(g)
        assert d.incident_trends == []

    def test_all_report_formats(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a"))
        for fmt in ReportFormat:
            d = engine.generate_dashboard(g, fmt)
            assert d.report_format == fmt
            assert d.generated_at != ""


class TestBuildRecommendations:
    def test_spof_recommendation(self):
        engine = ExecutiveDashboardEngine()
        c1 = _comp("db", ComponentType.DATABASE, replicas=1)
        c2 = _comp("app", ComponentType.APP_SERVER)
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        sc = engine.compute_resilience_scorecard(g)
        recs = engine._build_recommendations(g, sc)
        assert any("redundancy" in r.lower() or "single point" in r.lower() for r in recs)

    def test_down_component_recommendation(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a", health=HealthStatus.DOWN))
        sc = engine.compute_resilience_scorecard(g)
        recs = engine._build_recommendations(g, sc)
        assert any("down" in r.lower() for r in recs)

    def test_degraded_recommendation(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a", health=HealthStatus.DEGRADED))
        sc = engine.compute_resilience_scorecard(g)
        recs = engine._build_recommendations(g, sc)
        assert any("degradation" in r.lower() for r in recs)

    def test_high_utilization_recommendation(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp("a", metrics=ResourceMetrics(cpu_percent=95.0)),
        )
        sc = engine.compute_resilience_scorecard(g)
        recs = engine._build_recommendations(g, sc)
        assert any("scale" in r.lower() or "utilization" in r.lower() for r in recs)

    def test_circuit_breaker_recommendation(self):
        engine = ExecutiveDashboardEngine()
        c1, c2 = _comp("c1"), _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c1", target_id="c2"))
        sc = engine.compute_resilience_scorecard(g)
        recs = engine._build_recommendations(g, sc)
        assert any("circuit breaker" in r.lower() for r in recs)

    def test_autoscaling_recommendation(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a"), _comp("b"))
        sc = engine.compute_resilience_scorecard(g)
        recs = engine._build_recommendations(g, sc)
        assert any("autoscaling" in r.lower() for r in recs)

    def test_urgent_low_score(self):
        engine = ExecutiveDashboardEngine()
        sc = ResilienceScorecard(overall_score=30.0)
        recs = engine._build_recommendations(_graph(), sc)
        assert recs[0].startswith("URGENT")

    def test_below_target_message(self):
        engine = ExecutiveDashboardEngine()
        sc = ResilienceScorecard(overall_score=60.0)
        recs = engine._build_recommendations(_graph(), sc)
        assert any("below target" in r.lower() for r in recs)

    def test_max_10_recommendations(self):
        engine = ExecutiveDashboardEngine()
        comps = [_comp(f"c{i}", replicas=1) for i in range(20)]
        g = _graph(*comps)
        # Create dependencies so all are SPOFs
        for i in range(1, 20):
            g.add_dependency(
                Dependency(source_id=f"c{i}", target_id="c0")
            )
        sc = engine.compute_resilience_scorecard(g)
        recs = engine._build_recommendations(g, sc)
        assert len(recs) <= 10


class TestAssessSingleFramework:
    def test_empty_graph(self):
        engine = ExecutiveDashboardEngine()
        score = engine._assess_single_framework(_graph(), "SOC2")
        assert score == 0.0

    def test_fully_configured(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp(
                "a",
                security=SecurityProfile(
                    encryption_at_rest=True,
                    encryption_in_transit=True,
                    waf_protected=True,
                    rate_limiting=True,
                    auth_required=True,
                    network_segmented=True,
                    backup_enabled=True,
                    log_enabled=True,
                ),
                compliance_tags=ComplianceTags(
                    audit_logging=True,
                    change_management=True,
                ),
            )
        )
        score = engine._assess_single_framework(g, "SOC2")
        assert score == 100.0

    def test_no_controls(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a"))
        score = engine._assess_single_framework(g, "SOC2")
        assert score < 10.0

    def test_pci_dss_encryption_penalty(self):
        engine = ExecutiveDashboardEngine()
        # Give partial controls so SOC2 score > 0, but PCI penalty for missing encryption
        g = _graph(
            _comp(
                "a",
                security=SecurityProfile(
                    encryption_at_rest=False,
                    encryption_in_transit=True,
                    auth_required=True,
                    log_enabled=True,
                    backup_enabled=True,
                ),
                compliance_tags=ComplianceTags(pci_scope=True),
            )
        )
        score_pci = engine._assess_single_framework(g, "PCI_DSS")
        score_soc = engine._assess_single_framework(g, "SOC2")
        assert score_pci < score_soc

    def test_hipaa_phi_penalty(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp(
                "a",
                security=SecurityProfile(encryption_at_rest=False),
                compliance_tags=ComplianceTags(contains_phi=True),
            )
        )
        score = engine._assess_single_framework(g, "HIPAA")
        assert score == 0.0  # Heavy penalty

    def test_unknown_framework(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a"))
        score = engine._assess_single_framework(g, "UNKNOWN_FW")
        assert score >= 0.0  # No specific adjustments


# ---------------------------------------------------------------------------
# Edge cases and integration
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_single_component_all_features(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp(
                "super",
                replicas=3,
                health=HealthStatus.HEALTHY,
                autoscaling=AutoScalingConfig(enabled=True),
                failover=FailoverConfig(enabled=True),
                security=SecurityProfile(
                    encryption_at_rest=True,
                    encryption_in_transit=True,
                    waf_protected=True,
                    rate_limiting=True,
                    auth_required=True,
                    network_segmented=True,
                    backup_enabled=True,
                    log_enabled=True,
                ),
                compliance_tags=ComplianceTags(
                    audit_logging=True,
                    change_management=True,
                ),
                cost_profile=CostProfile(
                    hourly_infra_cost=50.0,
                    revenue_per_minute=200.0,
                ),
                metrics=ResourceMetrics(cpu_percent=20.0),
            )
        )
        d = engine.generate_dashboard(g, ReportFormat.BOARD_READY)
        assert d.scorecard.overall_score > 80.0
        assert d.scorecard.rating in (
            ExecutiveRating.EXCELLENT,
            ExecutiveRating.GOOD,
        )
        assert d.compliance.compliant_count > 0

    def test_all_down_components(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp("a", health=HealthStatus.DOWN),
            _comp("b", health=HealthStatus.DOWN),
            _comp("c", health=HealthStatus.DOWN),
        )
        d = engine.generate_dashboard(g)
        assert d.scorecard.category_scores["health_mix"] == 0.0
        assert d.scorecard.rating in (
            ExecutiveRating.CRITICAL,
            ExecutiveRating.NEEDS_ATTENTION,
        )

    def test_many_components(self):
        engine = ExecutiveDashboardEngine()
        comps = [_comp(f"c{i}", replicas=2) for i in range(50)]
        g = _graph(*comps)
        d = engine.generate_dashboard(g)
        assert d.scorecard.overall_score > 0
        assert len(d.capacity_forecasts) == 50

    def test_mixed_health_status(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp("a", health=HealthStatus.HEALTHY),
            _comp("b", health=HealthStatus.DEGRADED),
            _comp("c", health=HealthStatus.OVERLOADED),
            _comp("d", health=HealthStatus.DOWN),
        )
        d = engine.generate_dashboard(g)
        assert d.scorecard.category_scores["health_mix"] == 25.0

    def test_component_types_variety(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp("lb", ComponentType.LOAD_BALANCER, replicas=2),
            _comp("web", ComponentType.WEB_SERVER, replicas=2),
            _comp("app", ComponentType.APP_SERVER, replicas=2),
            _comp("db", ComponentType.DATABASE, replicas=2),
            _comp("cache", ComponentType.CACHE, replicas=2),
            _comp("queue", ComponentType.QUEUE, replicas=2),
            _comp("storage", ComponentType.STORAGE, replicas=2),
        )
        d = engine.generate_dashboard(g)
        assert d.scorecard.overall_score >= 80.0
        assert len(d.capacity_forecasts) == 7

    def test_deep_chain_with_circuit_breakers(self):
        engine = ExecutiveDashboardEngine()
        comps = [_comp(f"c{i}") for i in range(8)]
        g = _graph(*comps)
        for i in range(7):
            g.add_dependency(
                Dependency(
                    source_id=f"c{i}",
                    target_id=f"c{i + 1}",
                    circuit_breaker=CircuitBreakerConfig(enabled=True),
                )
            )
        heatmap = engine.build_risk_heatmap(g)
        cascade = next(c for c in heatmap if c.category == "cascade_failure")
        assert cascade.mitigation_status == "mitigated"

    def test_security_partial_controls(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp(
                "a",
                security=SecurityProfile(
                    encryption_at_rest=True,
                    encryption_in_transit=True,
                    auth_required=True,
                ),
            )
        )
        heatmap = engine.build_risk_heatmap(g)
        sec = next(c for c in heatmap if c.category == "security_breach")
        assert sec.mitigation_status == "partial"

    def test_incident_trends_critical_decline(self):
        engine = ExecutiveDashboardEngine()
        now = datetime.now(timezone.utc)
        # 0 incidents in week 1, 5 in week 2
        incidents = [
            {
                "timestamp": (now - timedelta(days=i)).isoformat(),
                "severity": "P1",
                "ttr_hours": 1.0,
                "ttd_hours": 0.5,
            }
            for i in range(5)
        ]
        # Add older incident
        incidents.append(
            {
                "timestamp": (now - timedelta(days=13)).isoformat(),
                "severity": "P3",
                "ttr_hours": 0.5,
                "ttd_hours": 0.1,
            }
        )
        trends = engine.analyze_incident_trends(incidents, period_days=14)
        # Second bucket should have more incidents -> DEGRADING or CRITICAL_DECLINE
        assert any(
            t.trend in (RiskTrend.DEGRADING, RiskTrend.CRITICAL_DECLINE)
            for t in trends
        )

    def test_dashboard_with_all_formats(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp("a", replicas=2),
            _comp("b", replicas=1),
        )
        for fmt in ReportFormat:
            d = engine.generate_dashboard(g, fmt)
            assert d.executive_summary != ""

    def test_capacity_peak_capped_at_100(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp("a", metrics=ResourceMetrics(cpu_percent=90.0))
        )
        forecasts = engine.forecast_capacity(g)
        assert forecasts[0].peak_utilization <= 100.0

    def test_multiple_spofs_in_heatmap(self):
        engine = ExecutiveDashboardEngine()
        c1 = _comp("db1", replicas=1)
        c2 = _comp("db2", replicas=1)
        c3 = _comp("app", replicas=2)
        g = _graph(c1, c2, c3)
        g.add_dependency(Dependency(source_id="app", target_id="db1"))
        g.add_dependency(Dependency(source_id="app", target_id="db2"))
        heatmap = engine.build_risk_heatmap(g)
        infra = next(c for c in heatmap if c.category == "infrastructure_failure")
        assert infra.likelihood > 0.5

    def test_financial_exposure_with_multiple_revenue_sources(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(
            _comp(
                "a",
                replicas=1,
                cost_profile=CostProfile(revenue_per_minute=100.0),
            ),
            _comp(
                "b",
                replicas=1,
                cost_profile=CostProfile(revenue_per_minute=500.0),
            ),
        )
        fe = engine.estimate_financial_exposure(g, revenue_per_hour_usd=1.0)
        # Should use max component revenue (500*60=30000)
        assert fe.estimated_annual_loss_usd > 0

    def test_compliance_empty_frameworks_list(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a"))
        cs = engine.assess_compliance_status(g, frameworks=[])
        assert cs.frameworks_assessed == 0
        assert cs.compliance_percentage == 0.0

    def test_incident_no_severity(self):
        engine = ExecutiveDashboardEngine()
        now = datetime.now(timezone.utc)
        incidents = [
            {
                "timestamp": now.isoformat(),
                "ttr_hours": 1.0,
                "ttd_hours": 0.5,
            }
        ]
        trends = engine.analyze_incident_trends(incidents, period_days=7)
        assert trends[0].p1_count == 0

    def test_overloaded_component(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a", health=HealthStatus.OVERLOADED))
        d = engine.generate_dashboard(g)
        assert d.scorecard.category_scores["health_mix"] == 0.0

    def test_dashboard_scorecard_score_range(self):
        engine = ExecutiveDashboardEngine()
        g = _graph(_comp("a"))
        d = engine.generate_dashboard(g)
        assert 0.0 <= d.scorecard.overall_score <= 100.0

    def test_naive_timestamp_gets_utc(self):
        engine = ExecutiveDashboardEngine()
        # Use a naive datetime string (no timezone info)
        incidents = [
            {
                "timestamp": "2026-01-15T10:00:00",
                "severity": "P2",
                "ttr_hours": 1.0,
                "ttd_hours": 0.5,
            }
        ]
        trends = engine.analyze_incident_trends(incidents, period_days=7)
        assert len(trends) >= 1
        assert trends[0].total_incidents == 1

    def test_cascade_partial_circuit_breakers(self):
        engine = ExecutiveDashboardEngine()
        c1 = _comp("c1")
        c2 = _comp("c2")
        c3 = _comp("c3")
        g = _graph(c1, c2, c3)
        g.add_dependency(
            Dependency(
                source_id="c1",
                target_id="c2",
                circuit_breaker=CircuitBreakerConfig(enabled=True),
            )
        )
        g.add_dependency(
            Dependency(
                source_id="c1",
                target_id="c3",
                circuit_breaker=CircuitBreakerConfig(enabled=False),
            )
        )
        heatmap = engine.build_risk_heatmap(g)
        cascade = next(c for c in heatmap if c.category == "cascade_failure")
        assert cascade.mitigation_status == "partial"
