"""Tests for the Financial Risk Engine."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    CostProfile,
    Dependency,
    HealthStatus,
    OperationalProfile,
    OperationalTeamConfig,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.financial_risk import (
    FinancialRiskEngine,
    FinancialRiskReport,
    FinancialRiskResult,
    _DEFAULT_ANNUAL_REVENUE,
    _MINUTES_PER_YEAR,
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
    cpu: float = 0.0,
    mttr: float = 30.0,
    hourly_cost: float = 0.0,
    sla_credit: float = 0.0,
    engineer_cost: float = 100.0,
    team_size: int = 3,
    connections: int = 0,
    autoscaling: bool = False,
    tags: list[str] | None = None,
) -> Component:
    return Component(
        id=cid,
        name=name,
        type=ctype,
        replicas=replicas,
        health=health,
        metrics=ResourceMetrics(cpu_percent=cpu, network_connections=connections),
        operational_profile=OperationalProfile(mttr_minutes=mttr),
        cost_profile=CostProfile(
            hourly_infra_cost=hourly_cost,
            sla_credit_percent=sla_credit,
            recovery_engineer_cost=engineer_cost,
        ),
        team=OperationalTeamConfig(team_size=team_size),
        autoscaling=AutoScalingConfig(enabled=autoscaling),
        tags=tags or [],
    )


def _chain_graph() -> InfraGraph:
    """Build lb -> app -> db chain graph."""
    g = InfraGraph()
    g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=2, hourly_cost=5.0))
    g.add_component(_comp("api", "API", replicas=3, hourly_cost=10.0, sla_credit=10.0))
    g.add_component(
        _comp("db", "DB", ComponentType.DATABASE, replicas=1,
              hourly_cost=20.0, engineer_cost=150.0, mttr=60.0, team_size=2)
    )
    g.add_dependency(Dependency(source_id="lb", target_id="api"))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    return g


# Mock objects for building SimulationReport-like structures without
# importing the real simulation engine (which would add unwanted coupling).

@dataclass
class _MockEffect:
    component_id: str
    health: HealthStatus
    estimated_time_seconds: int = 60


@dataclass
class _MockCascade:
    effects: list[_MockEffect] = field(default_factory=list)
    likelihood: float = 0.5


@dataclass
class _MockScenario:
    name: str = "mock-scenario"


@dataclass
class _MockResult:
    scenario: _MockScenario = field(default_factory=_MockScenario)
    cascade: _MockCascade = field(default_factory=_MockCascade)
    risk_score: float = 8.0

    @property
    def is_critical(self) -> bool:
        return self.risk_score >= 7.0

    @property
    def is_warning(self) -> bool:
        return 4.0 <= self.risk_score < 7.0


@dataclass
class _MockReport:
    results: list[_MockResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Tests: Constructor
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_default_annual_revenue(self):
        g = InfraGraph()
        engine = FinancialRiskEngine(g)
        assert engine.annual_revenue == _DEFAULT_ANNUAL_REVENUE

    def test_custom_annual_revenue(self):
        g = InfraGraph()
        engine = FinancialRiskEngine(g, annual_revenue=5_000_000)
        assert engine.annual_revenue == 5_000_000

    def test_negative_revenue_clamped_to_zero(self):
        g = InfraGraph()
        engine = FinancialRiskEngine(g, annual_revenue=-100)
        assert engine.annual_revenue == 0.0

    def test_revenue_per_minute(self):
        g = InfraGraph()
        engine = FinancialRiskEngine(g, annual_revenue=_MINUTES_PER_YEAR)
        assert abs(engine.revenue_per_minute - 1.0) < 0.001


# ---------------------------------------------------------------------------
# Tests: analyze() with empty / no critical results
# ---------------------------------------------------------------------------


class TestAnalyzeEmpty:
    def test_empty_simulation_report(self):
        """No results => empty report with zero losses."""
        g = _chain_graph()
        engine = FinancialRiskEngine(g)
        report = engine.analyze(_MockReport())
        assert isinstance(report, FinancialRiskReport)
        assert report.expected_annual_loss == 0.0
        assert report.value_at_risk_95 == 0.0
        assert report.cost_per_hour_of_risk == 0.0
        assert report.scenarios == []

    def test_only_passed_results_skipped(self):
        """Results that are neither critical nor warning are skipped."""
        g = _chain_graph()
        engine = FinancialRiskEngine(g)
        # risk_score=2.0 => is_critical=False, is_warning=False
        result = _MockResult(risk_score=2.0)
        report = engine.analyze(_MockReport(results=[result]))
        assert len(report.scenarios) == 0


# ---------------------------------------------------------------------------
# Tests: analyze() with critical / warning scenarios
# ---------------------------------------------------------------------------


class TestAnalyzeScenarios:
    def _make_critical_report(self, graph: InfraGraph) -> _MockReport:
        """Build a report with a critical scenario affecting db (DOWN)."""
        return _MockReport(results=[
            _MockResult(
                scenario=_MockScenario(name="db-failure"),
                cascade=_MockCascade(
                    effects=[
                        _MockEffect("db", HealthStatus.DOWN, estimated_time_seconds=120),
                    ],
                    likelihood=0.3,
                ),
                risk_score=8.0,
            ),
        ])

    def test_returns_financial_risk_report(self):
        g = _chain_graph()
        engine = FinancialRiskEngine(g, annual_revenue=10_000_000)
        report = engine.analyze(self._make_critical_report(g))
        assert isinstance(report, FinancialRiskReport)
        assert report.annual_revenue_usd == 10_000_000

    def test_scenario_populated(self):
        g = _chain_graph()
        engine = FinancialRiskEngine(g, annual_revenue=10_000_000)
        report = engine.analyze(self._make_critical_report(g))
        assert len(report.scenarios) == 1
        s = report.scenarios[0]
        assert s.scenario_name == "db-failure"
        assert s.probability == 0.3
        assert s.recovery_hours > 0
        assert s.business_loss_usd > 0

    def test_expected_annual_loss_positive(self):
        g = _chain_graph()
        engine = FinancialRiskEngine(g, annual_revenue=10_000_000)
        report = engine.analyze(self._make_critical_report(g))
        assert report.expected_annual_loss > 0

    def test_cost_per_hour_calculation(self):
        g = _chain_graph()
        engine = FinancialRiskEngine(g, annual_revenue=10_000_000)
        report = engine.analyze(self._make_critical_report(g))
        expected = report.expected_annual_loss / 8760.0
        assert abs(report.cost_per_hour_of_risk - expected) < 0.01

    def test_warning_scenarios_included(self):
        """Warning-level results (4 <= risk_score < 7) should be included."""
        g = _chain_graph()
        engine = FinancialRiskEngine(g)
        mock = _MockReport(results=[
            _MockResult(
                scenario=_MockScenario(name="warning-scenario"),
                cascade=_MockCascade(
                    effects=[_MockEffect("api", HealthStatus.OVERLOADED, 30)],
                    likelihood=0.5,
                ),
                risk_score=5.0,
            ),
        ])
        report = engine.analyze(mock)
        assert len(report.scenarios) == 1

    def test_scenarios_sorted_by_expected_loss(self):
        g = _chain_graph()
        engine = FinancialRiskEngine(g, annual_revenue=10_000_000)
        mock = _MockReport(results=[
            _MockResult(
                scenario=_MockScenario(name="low-risk"),
                cascade=_MockCascade(
                    effects=[_MockEffect("api", HealthStatus.OVERLOADED, 10)],
                    likelihood=0.1,
                ),
                risk_score=5.0,
            ),
            _MockResult(
                scenario=_MockScenario(name="high-risk"),
                cascade=_MockCascade(
                    effects=[_MockEffect("db", HealthStatus.DOWN, 300)],
                    likelihood=0.9,
                ),
                risk_score=9.0,
            ),
        ])
        report = engine.analyze(mock)
        assert len(report.scenarios) == 2
        expected_losses = [s.probability * s.business_loss_usd for s in report.scenarios]
        for i in range(len(expected_losses) - 1):
            assert expected_losses[i] >= expected_losses[i + 1]

    def test_higher_revenue_means_higher_loss(self):
        g = _chain_graph()
        mock = self._make_critical_report(g)
        engine_low = FinancialRiskEngine(g, annual_revenue=100_000)
        engine_high = FinancialRiskEngine(g, annual_revenue=100_000_000)
        report_low = engine_low.analyze(mock)
        report_high = engine_high.analyze(mock)
        assert report_high.expected_annual_loss > report_low.expected_annual_loss


# ---------------------------------------------------------------------------
# Tests: _estimate_recovery_hours
# ---------------------------------------------------------------------------


class TestEstimateRecoveryHours:
    def test_empty_effects(self):
        g = _chain_graph()
        engine = FinancialRiskEngine(g)
        cascade = _MockCascade(effects=[])
        assert engine._estimate_recovery_hours(cascade) == 0.0

    def test_down_component_uses_full_mttr(self):
        g = _chain_graph()
        engine = FinancialRiskEngine(g)
        cascade = _MockCascade(effects=[
            _MockEffect("db", HealthStatus.DOWN, estimated_time_seconds=0),
        ])
        hours = engine._estimate_recovery_hours(cascade)
        # db has mttr=60 minutes, DOWN uses full MTTR
        # recovery_min = 60 + 0/60 = 60 min, hours = 60/60 = 1.0
        assert abs(hours - 1.0) < 0.01

    def test_overloaded_uses_half_mttr(self):
        g = _chain_graph()
        engine = FinancialRiskEngine(g)
        cascade = _MockCascade(effects=[
            _MockEffect("db", HealthStatus.OVERLOADED, estimated_time_seconds=0),
        ])
        hours = engine._estimate_recovery_hours(cascade)
        # OVERLOADED: mttr * 0.5 = 60 * 0.5 = 30 min, hours = 0.5
        assert abs(hours - 0.5) < 0.01

    def test_degraded_uses_quarter_mttr(self):
        g = _chain_graph()
        engine = FinancialRiskEngine(g)
        cascade = _MockCascade(effects=[
            _MockEffect("db", HealthStatus.DEGRADED, estimated_time_seconds=0),
        ])
        hours = engine._estimate_recovery_hours(cascade)
        # DEGRADED: mttr * 0.25 = 60 * 0.25 = 15 min, hours = 0.25
        assert abs(hours - 0.25) < 0.01

    def test_healthy_uses_quarter_mttr(self):
        g = _chain_graph()
        engine = FinancialRiskEngine(g)
        cascade = _MockCascade(effects=[
            _MockEffect("db", HealthStatus.HEALTHY, estimated_time_seconds=0),
        ])
        hours = engine._estimate_recovery_hours(cascade)
        # HEALTHY falls into else branch: mttr * 0.25 = 15 min, hours = 0.25
        assert abs(hours - 0.25) < 0.01

    def test_estimated_time_added(self):
        g = _chain_graph()
        engine = FinancialRiskEngine(g)
        cascade = _MockCascade(effects=[
            _MockEffect("db", HealthStatus.DOWN, estimated_time_seconds=600),
        ])
        hours = engine._estimate_recovery_hours(cascade)
        # recovery_min = 60 + 600/60 = 60 + 10 = 70 min, hours = 70/60
        assert abs(hours - 70.0 / 60.0) < 0.01

    def test_unknown_component_skipped(self):
        g = _chain_graph()
        engine = FinancialRiskEngine(g)
        cascade = _MockCascade(effects=[
            _MockEffect("nonexistent", HealthStatus.DOWN, estimated_time_seconds=0),
        ])
        hours = engine._estimate_recovery_hours(cascade)
        assert hours == 0.0

    def test_zero_mttr_gets_default(self):
        """When mttr_minutes is 0, default of 30 min should be used."""
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc", mttr=0.0))
        engine = FinancialRiskEngine(g)
        cascade = _MockCascade(effects=[
            _MockEffect("svc", HealthStatus.DOWN, estimated_time_seconds=0),
        ])
        hours = engine._estimate_recovery_hours(cascade)
        # default 30 min for DOWN, hours = 30/60 = 0.5
        assert abs(hours - 0.5) < 0.01

    def test_max_recovery_across_effects(self):
        """Recovery hours should be the maximum across all effects."""
        g = _chain_graph()
        engine = FinancialRiskEngine(g)
        cascade = _MockCascade(effects=[
            _MockEffect("api", HealthStatus.OVERLOADED, estimated_time_seconds=0),  # api mttr=30, * 0.5 = 15 min
            _MockEffect("db", HealthStatus.DOWN, estimated_time_seconds=0),  # db mttr=60, full = 60 min
        ])
        hours = engine._estimate_recovery_hours(cascade)
        assert abs(hours - 1.0) < 0.01  # 60 min / 60 = 1 hr


# ---------------------------------------------------------------------------
# Tests: _estimate_sla_credits
# ---------------------------------------------------------------------------


class TestEstimateSLACredits:
    def test_no_sla_credits(self):
        g = _chain_graph()
        engine = FinancialRiskEngine(g)
        cascade = _MockCascade(effects=[
            _MockEffect("lb", HealthStatus.DOWN),  # lb has sla_credit=0
        ])
        credits = engine._estimate_sla_credits(cascade)
        assert credits == 0.0

    def test_sla_credit_for_down_component(self):
        g = _chain_graph()
        engine = FinancialRiskEngine(g)
        cascade = _MockCascade(effects=[
            _MockEffect("api", HealthStatus.DOWN),  # api has sla_credit=10%
        ])
        credits = engine._estimate_sla_credits(cascade)
        # monthly_cost = 10 * 730 = 7300, credit = 7300 * (10/100) = 730
        assert abs(credits - 730.0) < 0.01

    def test_sla_credit_for_overloaded(self):
        g = _chain_graph()
        engine = FinancialRiskEngine(g)
        cascade = _MockCascade(effects=[
            _MockEffect("api", HealthStatus.OVERLOADED),
        ])
        credits = engine._estimate_sla_credits(cascade)
        assert abs(credits - 730.0) < 0.01

    def test_degraded_no_sla_credit(self):
        """DEGRADED is not in (DOWN, OVERLOADED), no SLA credit."""
        g = _chain_graph()
        engine = FinancialRiskEngine(g)
        cascade = _MockCascade(effects=[
            _MockEffect("api", HealthStatus.DEGRADED),
        ])
        credits = engine._estimate_sla_credits(cascade)
        assert credits == 0.0

    def test_unknown_component_skipped(self):
        g = _chain_graph()
        engine = FinancialRiskEngine(g)
        cascade = _MockCascade(effects=[
            _MockEffect("nonexistent", HealthStatus.DOWN),
        ])
        credits = engine._estimate_sla_credits(cascade)
        assert credits == 0.0


# ---------------------------------------------------------------------------
# Tests: _estimate_recovery_costs
# ---------------------------------------------------------------------------


class TestEstimateRecoveryCosts:
    def test_down_component_incurs_cost(self):
        g = _chain_graph()
        engine = FinancialRiskEngine(g)
        cascade = _MockCascade(effects=[
            _MockEffect("db", HealthStatus.DOWN),
        ])
        cost = engine._estimate_recovery_costs(cascade)
        # engineer_rate=150, mttr_hours=60/60=1, team_size=2, min(2,3)=2
        # cost = 150 * 1 * 2 = 300
        assert abs(cost - 300.0) < 0.01

    def test_overloaded_no_recovery_cost(self):
        """Only DOWN triggers engineer recovery costs."""
        g = _chain_graph()
        engine = FinancialRiskEngine(g)
        cascade = _MockCascade(effects=[
            _MockEffect("db", HealthStatus.OVERLOADED),
        ])
        cost = engine._estimate_recovery_costs(cascade)
        assert cost == 0.0

    def test_degraded_no_recovery_cost(self):
        g = _chain_graph()
        engine = FinancialRiskEngine(g)
        cascade = _MockCascade(effects=[
            _MockEffect("db", HealthStatus.DEGRADED),
        ])
        cost = engine._estimate_recovery_costs(cascade)
        assert cost == 0.0

    def test_unknown_component_skipped(self):
        g = _chain_graph()
        engine = FinancialRiskEngine(g)
        cascade = _MockCascade(effects=[
            _MockEffect("nonexistent", HealthStatus.DOWN),
        ])
        cost = engine._estimate_recovery_costs(cascade)
        assert cost == 0.0

    def test_zero_engineer_rate_uses_default(self):
        """When recovery_engineer_cost <= 0, default of $100/hr is used."""
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc", mttr=60.0, engineer_cost=0.0, team_size=2))
        engine = FinancialRiskEngine(g)
        cascade = _MockCascade(effects=[_MockEffect("svc", HealthStatus.DOWN)])
        cost = engine._estimate_recovery_costs(cascade)
        # rate=100 (default), mttr_hours=1, min(team_size=2, 3)=2
        assert abs(cost - 200.0) < 0.01

    def test_team_size_capped_at_3(self):
        """Team size used for cost is min(team_size, 3)."""
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc", mttr=60.0, engineer_cost=100.0, team_size=10))
        engine = FinancialRiskEngine(g)
        cascade = _MockCascade(effects=[_MockEffect("svc", HealthStatus.DOWN)])
        cost = engine._estimate_recovery_costs(cascade)
        # min(10, 3) = 3, cost = 100 * 1 * 3 = 300
        assert abs(cost - 300.0) < 0.01

    def test_zero_team_size_uses_default(self):
        """When team_size is 0, default of 2 is used."""
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc", mttr=60.0, engineer_cost=100.0, team_size=0))
        engine = FinancialRiskEngine(g)
        cascade = _MockCascade(effects=[_MockEffect("svc", HealthStatus.DOWN)])
        cost = engine._estimate_recovery_costs(cascade)
        # team_size=0 => default 2, min(2, 3)=2, cost = 100 * 1 * 2 = 200
        assert abs(cost - 200.0) < 0.01


# ---------------------------------------------------------------------------
# Tests: _calculate_var95
# ---------------------------------------------------------------------------


class TestCalculateVar95:
    def test_empty_scenarios(self):
        assert FinancialRiskEngine._calculate_var95([]) == 0.0

    def test_single_high_probability_scenario(self):
        """If a single scenario has prob >= 0.95, its loss is the VaR95."""
        scenarios = [
            FinancialRiskResult("s1", probability=1.0, business_loss_usd=5000.0, recovery_hours=1.0),
        ]
        assert FinancialRiskEngine._calculate_var95(scenarios) == 5000.0

    def test_cumulative_exceeds_95(self):
        """VaR95 is the loss at the 95th percentile of cumulative probability."""
        scenarios = [
            FinancialRiskResult("low", probability=0.5, business_loss_usd=100.0, recovery_hours=0.5),
            FinancialRiskResult("high", probability=0.5, business_loss_usd=1000.0, recovery_hours=2.0),
        ]
        # Sorted ascending by loss: low(100, cum=0.5), high(1000, cum=1.0)
        # At high scenario cumulative=1.0 >= 0.95, so VaR95 = 1000
        assert FinancialRiskEngine._calculate_var95(scenarios) == 1000.0

    def test_total_probability_less_than_95(self):
        """If total probability < 0.95, VaR95 is the max loss."""
        scenarios = [
            FinancialRiskResult("a", probability=0.1, business_loss_usd=200.0, recovery_hours=0.5),
            FinancialRiskResult("b", probability=0.2, business_loss_usd=500.0, recovery_hours=1.0),
        ]
        # Total probability = 0.3, never hits 0.95
        # Returns max loss = 500
        assert FinancialRiskEngine._calculate_var95(scenarios) == 500.0

    def test_var95_picks_correct_threshold(self):
        """Multiple scenarios where cumulative first exceeds 0.95."""
        scenarios = [
            FinancialRiskResult("s1", probability=0.6, business_loss_usd=100.0, recovery_hours=0.5),
            FinancialRiskResult("s2", probability=0.3, business_loss_usd=500.0, recovery_hours=1.0),
            FinancialRiskResult("s3", probability=0.1, business_loss_usd=2000.0, recovery_hours=3.0),
        ]
        # Sorted by loss asc: s1(100, cum=0.6), s2(500, cum=0.9), s3(2000, cum=1.0)
        # At s3 cumulative=1.0 >= 0.95, so VaR95 = 2000
        assert FinancialRiskEngine._calculate_var95(scenarios) == 2000.0


# ---------------------------------------------------------------------------
# Tests: _calculate_mitigation_roi
# ---------------------------------------------------------------------------


class TestMitigationROI:
    def test_spof_generates_redundancy_recommendation(self):
        """Single-replica components with dependents should generate SPOF mitigation."""
        g = _chain_graph()
        engine = FinancialRiskEngine(g, annual_revenue=10_000_000)
        scenarios = [
            FinancialRiskResult("db-failure", probability=0.3, business_loss_usd=50000.0, recovery_hours=1.0),
        ]
        roi = engine._calculate_mitigation_roi(scenarios)
        # db has replicas=1 and has dependents (api depends on db)
        redundancy = [m for m in roi if "redundancy" in m["action"].lower()]
        assert len(redundancy) > 0

    def test_spof_related_losses_matched_by_name(self):
        """When scenario name contains comp_id, related_losses is calculated directly."""
        g = _chain_graph()
        engine = FinancialRiskEngine(g, annual_revenue=10_000_000)
        scenarios = [
            FinancialRiskResult("db-failure", probability=0.5, business_loss_usd=10000.0, recovery_hours=1.0),
        ]
        roi = engine._calculate_mitigation_roi(scenarios)
        db_redundancy = [m for m in roi if "DB" in m["action"]]
        assert len(db_redundancy) == 1
        # savings should be 70% of direct related_losses (0.5 * 10000 = 5000) * 0.7 = 3500
        assert abs(db_redundancy[0]["savings"] - 3500.0) < 0.01

    def test_spof_fallback_to_20_percent(self):
        """When scenario name doesn't match comp_id, 20% of total is assumed."""
        g = _chain_graph()
        engine = FinancialRiskEngine(g, annual_revenue=10_000_000)
        scenarios = [
            FinancialRiskResult("unrelated-scenario", probability=0.5, business_loss_usd=10000.0, recovery_hours=1.0),
        ]
        roi = engine._calculate_mitigation_roi(scenarios)
        # db SPOF: scenario name doesn't contain 'db' or 'DB'
        db_redundancy = [m for m in roi if "DB" in m["action"]]
        assert len(db_redundancy) == 1
        # related_losses fallback = total * 0.2 = (0.5*10000)*0.2 = 1000
        # savings = 1000 * 0.7 = 700
        assert abs(db_redundancy[0]["savings"] - 700.0) < 0.01

    def test_spof_zero_cost_gets_default(self):
        """When hourly_infra_cost is 0, default cost of $500 is used."""
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc", replicas=1, hourly_cost=0.0))
        g.add_component(_comp("dep", "Dep", replicas=2))
        g.add_dependency(Dependency(source_id="dep", target_id="svc"))
        engine = FinancialRiskEngine(g)
        scenarios = [FinancialRiskResult("svc", probability=0.5, business_loss_usd=10000.0, recovery_hours=1.0)]
        roi = engine._calculate_mitigation_roi(scenarios)
        svc_roi = [m for m in roi if "Svc" in m["action"]]
        assert len(svc_roi) == 1
        assert svc_roi[0]["cost"] == 500.0

    def test_autoscaling_recommendation(self):
        """High-utilization component without autoscaling gets autoscaling recommendation."""
        g = InfraGraph()
        # utilization > 60 requires cpu_percent > 60
        g.add_component(_comp("svc", "Svc", replicas=2, cpu=75.0, autoscaling=False, hourly_cost=10.0))
        engine = FinancialRiskEngine(g, annual_revenue=1_000_000)
        scenarios = []
        roi = engine._calculate_mitigation_roi(scenarios)
        autoscale = [m for m in roi if "autoscaling" in m["action"].lower()]
        assert len(autoscale) == 1
        assert autoscale[0]["roi_percent"] == 200.0

    def test_no_autoscaling_recommendation_when_enabled(self):
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc", replicas=2, cpu=75.0, autoscaling=True))
        engine = FinancialRiskEngine(g)
        roi = engine._calculate_mitigation_roi([])
        autoscale = [m for m in roi if "autoscaling" in m["action"].lower()]
        assert len(autoscale) == 0

    def test_no_autoscaling_recommendation_low_utilization(self):
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc", replicas=2, cpu=30.0, autoscaling=False))
        engine = FinancialRiskEngine(g)
        roi = engine._calculate_mitigation_roi([])
        autoscale = [m for m in roi if "autoscaling" in m["action"].lower()]
        assert len(autoscale) == 0

    def test_circuit_breaker_recommendation(self):
        """Missing circuit breakers on some (but not all) edges generates recommendation."""
        g = InfraGraph()
        g.add_component(_comp("a", "A", replicas=2))
        g.add_component(_comp("b", "B", replicas=2))
        g.add_component(_comp("c", "C", replicas=2))
        g.add_dependency(Dependency(
            source_id="a", target_id="b",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        g.add_dependency(Dependency(
            source_id="b", target_id="c",
            circuit_breaker=CircuitBreakerConfig(enabled=False),
        ))
        engine = FinancialRiskEngine(g)
        scenarios = [FinancialRiskResult("test", probability=0.5, business_loss_usd=10000.0, recovery_hours=1.0)]
        roi = engine._calculate_mitigation_roi(scenarios)
        cb = [m for m in roi if "circuit breaker" in m["action"].lower()]
        assert len(cb) == 1
        assert cb[0]["cost"] == 0.0
        assert cb[0]["roi_percent"] == float("inf")

    def test_no_circuit_breaker_when_all_enabled(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A", replicas=2))
        g.add_component(_comp("b", "B", replicas=2))
        g.add_dependency(Dependency(
            source_id="a", target_id="b",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        engine = FinancialRiskEngine(g)
        roi = engine._calculate_mitigation_roi([])
        cb = [m for m in roi if "circuit breaker" in m["action"].lower()]
        assert len(cb) == 0

    def test_no_circuit_breaker_when_all_uncovered(self):
        """If ALL edges are uncovered, no recommendation (edge case: uncovered < total is False)."""
        g = InfraGraph()
        g.add_component(_comp("a", "A", replicas=2))
        g.add_component(_comp("b", "B", replicas=2))
        g.add_dependency(Dependency(
            source_id="a", target_id="b",
            circuit_breaker=CircuitBreakerConfig(enabled=False),
        ))
        engine = FinancialRiskEngine(g)
        roi = engine._calculate_mitigation_roi([])
        cb = [m for m in roi if "circuit breaker" in m["action"].lower()]
        # len(uncovered) == len(edges) => condition fails, no recommendation
        assert len(cb) == 0

    def test_roi_sorted_by_roi_percent_descending(self):
        """Mitigations should be sorted by roi_percent descending."""
        g = InfraGraph()
        g.add_component(_comp("a", "A", replicas=1, cpu=75.0, autoscaling=False, hourly_cost=10.0))
        g.add_component(_comp("b", "B", replicas=2))
        g.add_component(_comp("c", "C", replicas=2))
        g.add_dependency(Dependency(source_id="b", target_id="a"))
        g.add_dependency(Dependency(
            source_id="b", target_id="c",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        g.add_dependency(Dependency(
            source_id="c", target_id="a",
            circuit_breaker=CircuitBreakerConfig(enabled=False),
        ))
        engine = FinancialRiskEngine(g, annual_revenue=1_000_000)
        scenarios = [FinancialRiskResult("test", probability=0.5, business_loss_usd=10000.0, recovery_hours=1.0)]
        roi = engine._calculate_mitigation_roi(scenarios)
        if len(roi) >= 2:
            for i in range(len(roi) - 1):
                r1 = roi[i]["roi_percent"] if math.isfinite(roi[i]["roi_percent"]) else 1e9
                r2 = roi[i + 1]["roi_percent"] if math.isfinite(roi[i + 1]["roi_percent"]) else 1e9
                assert r1 >= r2


# ---------------------------------------------------------------------------
# Tests: FinancialRiskReport.to_dict
# ---------------------------------------------------------------------------


class TestToDict:
    def test_to_dict_serializable(self):
        report = FinancialRiskReport(
            annual_revenue_usd=1_000_000,
            value_at_risk_95=5000.0,
            expected_annual_loss=2000.0,
            cost_per_hour_of_risk=0.228,
            scenarios=[
                FinancialRiskResult("s1", probability=0.5, business_loss_usd=4000.0, recovery_hours=1.0),
            ],
            mitigation_roi=[{"action": "test", "cost": 100, "savings": 500, "roi_percent": 400.0}],
        )
        d = report.to_dict()
        serialized = json.dumps(d)
        assert isinstance(serialized, str)

    def test_to_dict_fields(self):
        report = FinancialRiskReport(
            annual_revenue_usd=1_000_000,
            value_at_risk_95=5000.0,
            expected_annual_loss=2000.0,
            cost_per_hour_of_risk=0.228,
            scenarios=[
                FinancialRiskResult("s1", probability=0.5, business_loss_usd=4000.0, recovery_hours=1.0),
            ],
            mitigation_roi=[],
        )
        d = report.to_dict()
        assert "annual_revenue_usd" in d
        assert "value_at_risk_95" in d
        assert "expected_annual_loss" in d
        assert "cost_per_hour_of_risk" in d
        assert "scenarios" in d
        assert "mitigation_roi" in d
        assert len(d["scenarios"]) == 1
        assert d["scenarios"][0]["scenario_name"] == "s1"

    def test_to_dict_rounds_values(self):
        report = FinancialRiskReport(
            annual_revenue_usd=1000.1234,
            value_at_risk_95=500.5678,
            expected_annual_loss=200.9999,
            cost_per_hour_of_risk=0.12345,
            scenarios=[
                FinancialRiskResult("s1", probability=0.12345, business_loss_usd=100.9999, recovery_hours=1.5555),
            ],
        )
        d = report.to_dict()
        assert d["annual_revenue_usd"] == 1000.12
        assert d["scenarios"][0]["probability"] == 0.1235  # rounded to 4 decimal places
        assert d["scenarios"][0]["recovery_hours"] == 1.56


# ---------------------------------------------------------------------------
# Tests: FinancialRiskResult and FinancialRiskReport dataclasses
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_financial_risk_result(self):
        r = FinancialRiskResult("test", probability=0.5, business_loss_usd=1000.0, recovery_hours=2.0)
        assert r.scenario_name == "test"
        assert r.probability == 0.5
        assert r.business_loss_usd == 1000.0
        assert r.recovery_hours == 2.0

    def test_financial_risk_report_defaults(self):
        r = FinancialRiskReport(
            annual_revenue_usd=100.0,
            value_at_risk_95=0.0,
            expected_annual_loss=0.0,
            cost_per_hour_of_risk=0.0,
        )
        assert r.scenarios == []
        assert r.mitigation_roi == []

    def test_default_annual_revenue_constant(self):
        assert _DEFAULT_ANNUAL_REVENUE == 1_000_000.0

    def test_minutes_per_year_constant(self):
        assert _MINUTES_PER_YEAR == 365.25 * 24 * 60


# ---------------------------------------------------------------------------
# Tests: Zero-revenue edge case
# ---------------------------------------------------------------------------


class TestZeroRevenue:
    def test_zero_revenue_analysis(self):
        g = _chain_graph()
        engine = FinancialRiskEngine(g, annual_revenue=0)
        assert engine.revenue_per_minute == 0.0

        mock = _MockReport(results=[
            _MockResult(
                scenario=_MockScenario(name="db-failure"),
                cascade=_MockCascade(
                    effects=[_MockEffect("db", HealthStatus.DOWN, 120)],
                    likelihood=0.3,
                ),
                risk_score=8.0,
            ),
        ])
        report = engine.analyze(mock)
        assert report.annual_revenue_usd == 0
        # Losses should still exist from SLA credits + engineer costs, just no revenue loss
        # SLA credits for db: sla_credit_percent=0 => 0
        # Engineer costs: 150 * 1 * 2 = 300
        assert report.expected_annual_loss >= 0
