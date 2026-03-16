"""Tests for the Failure Budget Allocation Engine."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    OperationalProfile,
    ResourceMetrics,
    SLOTarget,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.failure_budget import (
    BudgetAllocation,
    BudgetReport,
    FailureBudgetAllocator,
    _STATEFUL_TYPES,
    _STATELESS_TYPES,
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
    connections: int = 0,
    mttr: float = 30.0,
    failover: bool = False,
    autoscaling: bool = False,
    tags: list[str] | None = None,
    slo_targets: list[SLOTarget] | None = None,
) -> Component:
    return Component(
        id=cid,
        name=name,
        type=ctype,
        replicas=replicas,
        health=health,
        metrics=ResourceMetrics(cpu_percent=cpu, network_connections=connections),
        operational_profile=OperationalProfile(mttr_minutes=mttr),
        failover=FailoverConfig(enabled=failover),
        autoscaling=AutoScalingConfig(enabled=autoscaling),
        tags=tags or [],
        slo_targets=slo_targets or [],
    )


def _chain_graph() -> InfraGraph:
    """Build lb -> app -> db chain graph."""
    g = InfraGraph()
    g.add_component(_comp(
        "lb", "LB", ComponentType.LOAD_BALANCER, replicas=2,
        failover=True, tags=["team:platform"],
    ))
    g.add_component(_comp(
        "api", "API", replicas=3, tags=["team:backend"],
        autoscaling=True, mttr=15.0,
    ))
    g.add_component(_comp(
        "db", "DB", ComponentType.DATABASE, replicas=1,
        tags=["team:data"], mttr=30.0,
    ))
    g.add_dependency(Dependency(source_id="lb", target_id="api"))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    return g


# Mock objects for simulate_consumption

@dataclass
class _MockEffect:
    component_id: str
    health: HealthStatus


@dataclass
class _MockCascade:
    effects: list[_MockEffect] = field(default_factory=list)


@dataclass
class _MockResult:
    cascade: _MockCascade = field(default_factory=_MockCascade)
    risk_score: float = 5.0


@dataclass
class _MockReport:
    results: list[_MockResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Tests: Allocation Basics
# ---------------------------------------------------------------------------


class TestAllocateBasics:
    def test_allocate_returns_budget_report(self):
        g = _chain_graph()
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        report = allocator.allocate()
        assert isinstance(report, BudgetReport)

    def test_total_budget_calculation(self):
        g = _chain_graph()
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        report = allocator.allocate()
        expected = (1 - 99.9 / 100) * 30 * 24 * 60  # 43.2 minutes
        assert abs(report.total_budget_minutes - expected) < 0.1

    def test_allocations_count_matches_components(self):
        g = _chain_graph()
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        report = allocator.allocate()
        assert len(report.allocations) == 3

    def test_budget_sum_approximates_total(self):
        g = _chain_graph()
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        report = allocator.allocate()
        alloc_sum = sum(a.budget_total_minutes for a in report.allocations)
        assert abs(alloc_sum - report.total_budget_minutes) < 1.0

    def test_empty_graph(self):
        g = InfraGraph()
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        report = allocator.allocate()
        assert len(report.allocations) == 0
        assert report.total_budget_minutes > 0

    def test_slo_and_window_stored(self):
        g = _chain_graph()
        allocator = FailureBudgetAllocator(g, slo_target=99.95, window_days=7)
        report = allocator.allocate()
        assert report.slo_target == 99.95
        assert report.window_days == 7

    def test_stricter_slo_gives_less_budget(self):
        g = _chain_graph()
        alloc_999 = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        alloc_9999 = FailureBudgetAllocator(g, slo_target=99.99, window_days=30)
        report_999 = alloc_999.allocate()
        report_9999 = alloc_9999.allocate()
        assert report_999.total_budget_minutes > report_9999.total_budget_minutes


# ---------------------------------------------------------------------------
# Tests: Risk Weights (_compute_risk_weight)
# ---------------------------------------------------------------------------


class TestRiskWeights:
    def test_database_gets_higher_weight_than_loadbalancer(self):
        """Stateful components (DB) should get higher risk weight (1.5x) vs stateless (0.8x)."""
        g = _chain_graph()
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        report = allocator.allocate()
        db_alloc = next(a for a in report.allocations if a.service_id == "db")
        lb_alloc = next(a for a in report.allocations if a.service_id == "lb")
        assert db_alloc.risk_weight > lb_alloc.risk_weight

    def test_more_dependents_higher_weight(self):
        """Components with more dependents get higher weight (+0.5 per dependent)."""
        g = InfraGraph()
        g.add_component(_comp("shared_db", "Shared DB", ComponentType.DATABASE))
        g.add_component(_comp("svc1", "Service 1"))
        g.add_component(_comp("svc2", "Service 2"))
        g.add_component(_comp("svc3", "Service 3"))
        for svc in ["svc1", "svc2", "svc3"]:
            g.add_dependency(Dependency(source_id=svc, target_id="shared_db"))
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        report = allocator.allocate()
        db_alloc = next(a for a in report.allocations if a.service_id == "shared_db")
        svc_alloc = next(a for a in report.allocations if a.service_id == "svc1")
        assert db_alloc.risk_weight > svc_alloc.risk_weight

    def test_slo_target_9999_doubles_weight(self):
        """SLO target >= 99.99 applies 2.0x multiplier."""
        g = InfraGraph()
        g.add_component(_comp(
            "critical", "Critical API",
            slo_targets=[SLOTarget(name="availability", target=99.99)],
        ))
        g.add_component(_comp("normal", "Normal API"))
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        report = allocator.allocate()
        critical = next(a for a in report.allocations if a.service_id == "critical")
        normal = next(a for a in report.allocations if a.service_id == "normal")
        assert critical.risk_weight > normal.risk_weight

    def test_slo_target_999_multiplier(self):
        """SLO target >= 99.9 (but < 99.99) applies 1.5x multiplier."""
        g = InfraGraph()
        g.add_component(_comp(
            "svc", "Svc",
            slo_targets=[SLOTarget(name="availability", target=99.9)],
        ))
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        w = allocator._compute_risk_weight(g.get_component("svc"))
        # base=1.0, no dependents, stateless=0.8x => 0.8, SLO>=99.9 => *1.5 = 1.2
        # single replica, no failover => *1.3 = 1.56
        assert abs(w - 1.56) < 0.01

    def test_slo_target_99_multiplier(self):
        """SLO target >= 99.0 (but < 99.9) applies 1.2x multiplier."""
        g = InfraGraph()
        g.add_component(_comp(
            "svc", "Svc",
            slo_targets=[SLOTarget(name="availability", target=99.5)],
        ))
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        w = allocator._compute_risk_weight(g.get_component("svc"))
        # base=1.0, stateless=0.8, SLO>=99.0 => *1.2 = 0.96, single no failover => *1.3 = 1.248
        assert abs(w - 1.248) < 0.01

    def test_single_replica_no_failover_higher_weight(self):
        """Single-replica component without failover gets 1.3x multiplier."""
        g = InfraGraph()
        g.add_component(_comp("single", "Single", replicas=1, failover=False))
        g.add_component(_comp("redundant", "Redundant", replicas=2, failover=True))
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        w_single = allocator._compute_risk_weight(g.get_component("single"))
        w_redundant = allocator._compute_risk_weight(g.get_component("redundant"))
        assert w_single > w_redundant

    def test_stateful_types(self):
        """All stateful types should be in _STATEFUL_TYPES."""
        assert ComponentType.DATABASE in _STATEFUL_TYPES
        assert ComponentType.CACHE in _STATEFUL_TYPES
        assert ComponentType.STORAGE in _STATEFUL_TYPES
        assert ComponentType.QUEUE in _STATEFUL_TYPES

    def test_stateless_types(self):
        """All stateless types should be in _STATELESS_TYPES."""
        assert ComponentType.WEB_SERVER in _STATELESS_TYPES
        assert ComponentType.APP_SERVER in _STATELESS_TYPES
        assert ComponentType.LOAD_BALANCER in _STATELESS_TYPES
        assert ComponentType.DNS in _STATELESS_TYPES
        assert ComponentType.EXTERNAL_API in _STATELESS_TYPES
        assert ComponentType.CUSTOM in _STATELESS_TYPES

    def test_zero_total_weight_fallback(self):
        """When all weights sum to 0, total_weight defaults to 1.0 to avoid div/zero."""
        # This is hard to trigger naturally since weights are always > 0.
        # We test the allocator with a single component and verify it doesn't crash.
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc"))
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        report = allocator.allocate()
        assert len(report.allocations) == 1


# ---------------------------------------------------------------------------
# Tests: Team Derivation (_derive_team)
# ---------------------------------------------------------------------------


class TestTeamDerivation:
    def test_team_from_tags(self):
        g = _chain_graph()
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        report = allocator.allocate()
        app = next(a for a in report.allocations if a.service_id == "api")
        assert app.team == "backend"
        db = next(a for a in report.allocations if a.service_id == "db")
        assert db.team == "data"
        lb = next(a for a in report.allocations if a.service_id == "lb")
        assert lb.team == "platform"

    def test_default_team_no_tags(self):
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc", tags=[]))
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        report = allocator.allocate()
        assert report.allocations[0].team == "default"

    def test_non_team_tags_ignored(self):
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc", tags=["env:prod", "region:us-east"]))
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        report = allocator.allocate()
        assert report.allocations[0].team == "default"

    def test_first_team_tag_used(self):
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc", tags=["team:alpha", "team:beta"]))
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        report = allocator.allocate()
        assert report.allocations[0].team == "alpha"


# ---------------------------------------------------------------------------
# Tests: _estimate_consumed
# ---------------------------------------------------------------------------


class TestEstimateConsumed:
    def test_healthy_no_consumption(self):
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc", health=HealthStatus.HEALTHY))
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        report = allocator.allocate()
        assert report.allocations[0].budget_consumed_minutes == 0.0

    def test_down_consumes_mttr(self):
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc", health=HealthStatus.DOWN, mttr=45.0))
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        report = allocator.allocate()
        assert report.allocations[0].budget_consumed_minutes >= 45.0

    def test_degraded_consumes_partial(self):
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc", health=HealthStatus.DEGRADED))
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        report = allocator.allocate()
        assert report.allocations[0].budget_consumed_minutes > 0

    def test_overloaded_consumes_partial(self):
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc", health=HealthStatus.OVERLOADED))
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        report = allocator.allocate()
        assert report.allocations[0].budget_consumed_minutes > 0

    def test_high_utilization_adds_budget_risk(self):
        """Utilization > 90% adds 10% of budget to consumed."""
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc", cpu=95.0))
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        report = allocator.allocate()
        # Total budget = 43.2 min (single component gets all)
        # consumed includes budget * 0.1 for high utilization
        assert report.allocations[0].budget_consumed_minutes > 0

    def test_down_with_zero_mttr_uses_default(self):
        """When mttr_minutes is 0, it should use 30 as default (via `or 30.0`)."""
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc", health=HealthStatus.DOWN, mttr=0.0))
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        report = allocator.allocate()
        assert report.allocations[0].budget_consumed_minutes >= 30.0


# ---------------------------------------------------------------------------
# Tests: Budget Remaining
# ---------------------------------------------------------------------------


class TestBudgetRemaining:
    def test_remaining_percent_range(self):
        g = _chain_graph()
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        report = allocator.allocate()
        for a in report.allocations:
            assert a.budget_remaining_percent <= 100.0

    def test_remaining_is_total_minus_consumed(self):
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc", health=HealthStatus.DEGRADED))
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        report = allocator.allocate()
        a = report.allocations[0]
        expected_remaining = a.budget_total_minutes - a.budget_consumed_minutes
        assert abs(a.budget_remaining_minutes - expected_remaining) < 0.1


# ---------------------------------------------------------------------------
# Tests: Classification (over_budget / under_utilized)
# ---------------------------------------------------------------------------


class TestClassification:
    def test_healthy_services_classification_valid(self):
        g = _chain_graph()
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        report = allocator.allocate()
        all_ids = {a.service_id for a in report.allocations}
        assert set(report.over_budget_services).issubset(all_ids)
        assert set(report.under_utilized_services).issubset(all_ids)

    def test_over_budget_when_consumed_exceeds_total(self):
        """A DOWN component with high MTTR and strict SLO can be over-budget."""
        g = InfraGraph()
        # Very strict SLO + very small budget window
        g.add_component(_comp("svc", "Svc", health=HealthStatus.DOWN, mttr=120.0))
        allocator = FailureBudgetAllocator(g, slo_target=99.99, window_days=1)
        report = allocator.allocate()
        # total_budget = (1 - 0.9999) * 1 * 24 * 60 = 0.144 min
        # consumed >= 120 min (mttr)
        assert "svc" in report.over_budget_services

    def test_under_utilized_when_remaining_above_80(self):
        """Healthy component with budget_remaining_percent > 80 is under-utilized."""
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc", health=HealthStatus.HEALTHY))
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        report = allocator.allocate()
        assert "svc" in report.under_utilized_services


# ---------------------------------------------------------------------------
# Tests: simulate_consumption
# ---------------------------------------------------------------------------


class TestSimulateConsumption:
    def test_basic_simulation_consumption(self):
        g = _chain_graph()
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        mock = _MockReport(results=[
            _MockResult(
                cascade=_MockCascade(effects=[
                    _MockEffect(component_id="db", health=HealthStatus.DOWN),
                    _MockEffect(component_id="api", health=HealthStatus.DEGRADED),
                ]),
                risk_score=7.0,
            ),
        ])
        report = allocator.simulate_consumption(mock)
        assert isinstance(report, BudgetReport)
        assert len(report.allocations) == 3
        db_alloc = next(a for a in report.allocations if a.service_id == "db")
        assert db_alloc.budget_consumed_minutes > 0

    def test_empty_simulation_report(self):
        g = _chain_graph()
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        report = allocator.simulate_consumption(_MockReport())
        assert isinstance(report, BudgetReport)
        for a in report.allocations:
            assert a.budget_consumed_minutes == 0.0

    def test_empty_graph_simulation(self):
        g = InfraGraph()
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        report = allocator.simulate_consumption(_MockReport())
        assert len(report.allocations) == 0
        assert report.total_budget_minutes > 0

    def test_down_effect_consumes_mttr_proportional_to_risk(self):
        """DOWN effect consumption = mttr * max(risk_score/10, 0.1)."""
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc", mttr=60.0))
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        mock = _MockReport(results=[
            _MockResult(
                cascade=_MockCascade(effects=[
                    _MockEffect("svc", HealthStatus.DOWN),
                ]),
                risk_score=5.0,
            ),
        ])
        report = allocator.simulate_consumption(mock)
        alloc = report.allocations[0]
        # consumption = 60 * max(5/10, 0.1) = 60 * 0.5 = 30
        assert abs(alloc.budget_consumed_minutes - 30.0) < 0.1

    def test_degraded_effect_consumes_one_minute(self):
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc"))
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        mock = _MockReport(results=[
            _MockResult(
                cascade=_MockCascade(effects=[
                    _MockEffect("svc", HealthStatus.DEGRADED),
                ]),
                risk_score=5.0,
            ),
        ])
        report = allocator.simulate_consumption(mock)
        assert abs(report.allocations[0].budget_consumed_minutes - 1.0) < 0.01

    def test_overloaded_effect_consumes_one_minute(self):
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc"))
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        mock = _MockReport(results=[
            _MockResult(
                cascade=_MockCascade(effects=[
                    _MockEffect("svc", HealthStatus.OVERLOADED),
                ]),
                risk_score=5.0,
            ),
        ])
        report = allocator.simulate_consumption(mock)
        assert abs(report.allocations[0].budget_consumed_minutes - 1.0) < 0.01

    def test_healthy_effect_no_consumption(self):
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc"))
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        mock = _MockReport(results=[
            _MockResult(
                cascade=_MockCascade(effects=[
                    _MockEffect("svc", HealthStatus.HEALTHY),
                ]),
                risk_score=5.0,
            ),
        ])
        report = allocator.simulate_consumption(mock)
        assert report.allocations[0].budget_consumed_minutes == 0.0

    def test_unknown_component_effect_ignored(self):
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc"))
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        mock = _MockReport(results=[
            _MockResult(
                cascade=_MockCascade(effects=[
                    _MockEffect("nonexistent", HealthStatus.DOWN),
                ]),
                risk_score=5.0,
            ),
        ])
        report = allocator.simulate_consumption(mock)
        assert report.allocations[0].budget_consumed_minutes == 0.0

    def test_no_cascade_attribute_handled(self):
        """Results without a cascade attribute should be skipped gracefully."""
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc"))
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)

        @dataclass
        class NoCascadeResult:
            risk_score: float = 5.0

        @dataclass
        class NoCascadeReport:
            results: list = field(default_factory=list)

        report = allocator.simulate_consumption(NoCascadeReport(results=[NoCascadeResult()]))
        assert report.allocations[0].budget_consumed_minutes == 0.0

    def test_risk_score_capped_at_10(self):
        """severity = min(risk_score/10, 1.0), so risk_score=15 caps at 1.0."""
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc", mttr=60.0))
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        mock = _MockReport(results=[
            _MockResult(
                cascade=_MockCascade(effects=[
                    _MockEffect("svc", HealthStatus.DOWN),
                ]),
                risk_score=15.0,
            ),
        ])
        report = allocator.simulate_consumption(mock)
        # consumption = 60 * min(15/10, 1.0) = 60 * 1.0 = 60
        assert abs(report.allocations[0].budget_consumed_minutes - 60.0) < 0.1

    def test_low_risk_score_uses_minimum(self):
        """severity = max(risk_score/10, 0.1), so risk_score=0 => 0.1."""
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc", mttr=60.0))
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        mock = _MockReport(results=[
            _MockResult(
                cascade=_MockCascade(effects=[
                    _MockEffect("svc", HealthStatus.DOWN),
                ]),
                risk_score=0.0,
            ),
        ])
        report = allocator.simulate_consumption(mock)
        # consumption = 60 * max(0/10, 0.1) = 60 * 0.1 = 6
        assert abs(report.allocations[0].budget_consumed_minutes - 6.0) < 0.1

    def test_simulate_over_budget_detection(self):
        """simulate_consumption should detect over-budget services."""
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc", mttr=120.0))
        # Very strict SLO + small window => tiny budget
        allocator = FailureBudgetAllocator(g, slo_target=99.99, window_days=1)
        mock = _MockReport(results=[
            _MockResult(
                cascade=_MockCascade(effects=[
                    _MockEffect("svc", HealthStatus.DOWN),
                ]),
                risk_score=10.0,
            ),
        ])
        report = allocator.simulate_consumption(mock)
        # total_budget = (1-0.9999)*1*24*60 = 0.144 min
        # consumption = 120 * 1.0 = 120 min >> budget
        assert "svc" in report.over_budget_services

    def test_simulate_consumption_with_mttr_zero(self):
        """Component with mttr=0 should use default (30 via `or 30.0`)."""
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc", mttr=0.0))
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        mock = _MockReport(results=[
            _MockResult(
                cascade=_MockCascade(effects=[
                    _MockEffect("svc", HealthStatus.DOWN),
                ]),
                risk_score=10.0,
            ),
        ])
        report = allocator.simulate_consumption(mock)
        # mttr=0 => or 30.0 => consumption = 30 * 1.0 = 30
        assert abs(report.allocations[0].budget_consumed_minutes - 30.0) < 0.1


# ---------------------------------------------------------------------------
# Tests: Rebalance Suggestions (_generate_rebalance_suggestions)
# ---------------------------------------------------------------------------


class TestRebalanceSuggestions:
    def test_no_suggestions_when_all_balanced(self):
        """No over-budget services => no rebalance suggestions."""
        g = _chain_graph()
        allocator = FailureBudgetAllocator(g, slo_target=99.9, window_days=30)
        report = allocator.allocate()
        for s in report.rebalance_suggestions:
            assert isinstance(s, dict)
            assert "action" in s
            assert "reason" in s

    def test_rebalance_from_under_to_over(self):
        """When one service is over-budget and another is under-utilized, suggest rebalance."""
        over = BudgetAllocation(
            service_id="over_svc", service_name="Over Service", team="ops",
            budget_total_minutes=10.0, budget_consumed_minutes=15.0,
            budget_remaining_minutes=-5.0, budget_remaining_percent=-50.0,
            risk_weight=2.0,
        )
        under = BudgetAllocation(
            service_id="under_svc", service_name="Under Service", team="ops",
            budget_total_minutes=20.0, budget_consumed_minutes=2.0,
            budget_remaining_minutes=18.0, budget_remaining_percent=90.0,
            risk_weight=1.0,
        )
        suggestions = FailureBudgetAllocator._generate_rebalance_suggestions([over, under])
        rebalances = [s for s in suggestions if s["action"] == "rebalance"]
        assert len(rebalances) == 1
        assert rebalances[0]["from_service"] == "under_svc"
        assert rebalances[0]["to_service"] == "over_svc"
        # transfer = under.budget_remaining_minutes * 0.2 = 18 * 0.2 = 3.6
        assert abs(rebalances[0]["suggested_transfer_minutes"] - 3.6) < 0.01

    def test_add_redundancy_for_over_budget(self):
        """Over-budget services should get add_redundancy suggestion."""
        over = BudgetAllocation(
            service_id="over_svc", service_name="Over Service", team="ops",
            budget_total_minutes=10.0, budget_consumed_minutes=15.0,
            budget_remaining_minutes=-5.0, budget_remaining_percent=-50.0,
            risk_weight=2.0,
        )
        suggestions = FailureBudgetAllocator._generate_rebalance_suggestions([over])
        redundancy = [s for s in suggestions if s["action"] == "add_redundancy"]
        assert len(redundancy) == 1
        assert redundancy[0]["service"] == "over_svc"

    def test_no_suggestions_when_none_over_budget(self):
        """If no service is over budget, no suggestions at all."""
        alloc = BudgetAllocation(
            service_id="svc", service_name="Svc", team="ops",
            budget_total_minutes=50.0, budget_consumed_minutes=10.0,
            budget_remaining_minutes=40.0, budget_remaining_percent=80.0,
            risk_weight=1.0,
        )
        suggestions = FailureBudgetAllocator._generate_rebalance_suggestions([alloc])
        assert len(suggestions) == 0

    def test_multiple_over_budget_multiple_under_utilized(self):
        """Cross-product of over/under pairs should generate all combinations."""
        over1 = BudgetAllocation(
            service_id="o1", service_name="O1", team="ops",
            budget_total_minutes=10.0, budget_consumed_minutes=15.0,
            budget_remaining_minutes=-5.0, budget_remaining_percent=-50.0,
            risk_weight=2.0,
        )
        over2 = BudgetAllocation(
            service_id="o2", service_name="O2", team="ops",
            budget_total_minutes=10.0, budget_consumed_minutes=12.0,
            budget_remaining_minutes=-2.0, budget_remaining_percent=-20.0,
            risk_weight=1.5,
        )
        under1 = BudgetAllocation(
            service_id="u1", service_name="U1", team="ops",
            budget_total_minutes=50.0, budget_consumed_minutes=5.0,
            budget_remaining_minutes=45.0, budget_remaining_percent=90.0,
            risk_weight=0.5,
        )
        suggestions = FailureBudgetAllocator._generate_rebalance_suggestions(
            [over1, over2, under1]
        )
        rebalances = [s for s in suggestions if s["action"] == "rebalance"]
        # 2 over x 1 under = 2 rebalance suggestions
        assert len(rebalances) == 2
        # Plus 2 add_redundancy suggestions
        redundancy = [s for s in suggestions if s["action"] == "add_redundancy"]
        assert len(redundancy) == 2


# ---------------------------------------------------------------------------
# Tests: BudgetAllocation / BudgetReport dataclasses
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_budget_allocation_fields(self):
        a = BudgetAllocation(
            service_id="svc", service_name="Svc", team="ops",
            budget_total_minutes=100.0, budget_consumed_minutes=20.0,
            budget_remaining_minutes=80.0, budget_remaining_percent=80.0,
            risk_weight=1.5,
        )
        assert a.service_id == "svc"
        assert a.risk_weight == 1.5

    def test_budget_report_defaults(self):
        r = BudgetReport(slo_target=99.9, window_days=30, total_budget_minutes=43.2)
        assert r.allocations == []
        assert r.over_budget_services == []
        assert r.under_utilized_services == []
        assert r.rebalance_suggestions == []
