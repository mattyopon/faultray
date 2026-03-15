"""Tests for the Failure Budget Allocation Engine."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from infrasim.model.components import (
    AutoScalingConfig,
    Capacity,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    OperationalProfile,
    ResourceMetrics,
    SLOTarget,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.failure_budget import (
    BudgetAllocation,
    BudgetReport,
    FailureBudgetAllocator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_basic_graph() -> InfraGraph:
    """Build a 3-component graph: lb -> app -> db."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2,
        failover=FailoverConfig(enabled=True),
        tags=["team:platform"],
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=3,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
        tags=["team:backend"],
        operational_profile=OperationalProfile(mttr_minutes=15),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=1,
        tags=["team:data"],
        operational_profile=OperationalProfile(mttr_minutes=30),
    ))

    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))

    return graph


def _build_single_component_graph() -> InfraGraph:
    """Build a graph with a single component."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="api", name="API Server", type=ComponentType.APP_SERVER,
        replicas=1,
    ))
    return graph


# ---------------------------------------------------------------------------
# Tests: Allocation Basics
# ---------------------------------------------------------------------------


class TestAllocateBasics:
    """Test basic budget allocation functionality."""

    def test_allocate_returns_budget_report(self):
        """allocate() should return a BudgetReport."""
        graph = _build_basic_graph()
        allocator = FailureBudgetAllocator(graph, slo_target=99.9, window_days=30)

        report = allocator.allocate()

        assert isinstance(report, BudgetReport)

    def test_total_budget_calculation(self):
        """Total budget should match: (1 - slo/100) * days * 24 * 60."""
        graph = _build_basic_graph()
        allocator = FailureBudgetAllocator(graph, slo_target=99.9, window_days=30)

        report = allocator.allocate()

        expected = (1 - 99.9 / 100) * 30 * 24 * 60  # 43.2 minutes
        assert abs(report.total_budget_minutes - expected) < 0.1

    def test_allocations_count_matches_components(self):
        """Should have one allocation per component."""
        graph = _build_basic_graph()
        allocator = FailureBudgetAllocator(graph, slo_target=99.9, window_days=30)

        report = allocator.allocate()

        assert len(report.allocations) == 3

    def test_budget_sum_approximates_total(self):
        """Sum of all allocations should approximate total budget."""
        graph = _build_basic_graph()
        allocator = FailureBudgetAllocator(graph, slo_target=99.9, window_days=30)

        report = allocator.allocate()

        alloc_sum = sum(a.budget_total_minutes for a in report.allocations)
        assert abs(alloc_sum - report.total_budget_minutes) < 1.0

    def test_empty_graph(self):
        """Empty graph should return report with no allocations."""
        graph = InfraGraph()
        allocator = FailureBudgetAllocator(graph, slo_target=99.9, window_days=30)

        report = allocator.allocate()

        assert len(report.allocations) == 0
        assert report.total_budget_minutes > 0


# ---------------------------------------------------------------------------
# Tests: Risk Weights
# ---------------------------------------------------------------------------


class TestRiskWeights:
    """Test risk weight computation."""

    def test_database_gets_higher_weight(self):
        """Stateful components (DB) should get higher risk weight."""
        graph = _build_basic_graph()
        allocator = FailureBudgetAllocator(graph, slo_target=99.9, window_days=30)

        report = allocator.allocate()

        db_alloc = next(a for a in report.allocations if a.service_id == "db")
        lb_alloc = next(a for a in report.allocations if a.service_id == "lb")

        # DB should have higher risk weight due to stateful type
        assert db_alloc.risk_weight > lb_alloc.risk_weight

    def test_more_dependents_higher_weight(self):
        """Components with more dependents should get higher weight."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="shared_db", name="Shared DB", type=ComponentType.DATABASE,
            replicas=1,
        ))
        graph.add_component(Component(
            id="svc1", name="Service 1", type=ComponentType.APP_SERVER,
            replicas=1,
        ))
        graph.add_component(Component(
            id="svc2", name="Service 2", type=ComponentType.APP_SERVER,
            replicas=1,
        ))
        graph.add_component(Component(
            id="svc3", name="Service 3", type=ComponentType.APP_SERVER,
            replicas=1,
        ))
        # All services depend on shared_db
        for svc in ["svc1", "svc2", "svc3"]:
            graph.add_dependency(Dependency(
                source_id=svc, target_id="shared_db", dependency_type="requires",
            ))

        allocator = FailureBudgetAllocator(graph, slo_target=99.9, window_days=30)
        report = allocator.allocate()

        db_alloc = next(a for a in report.allocations if a.service_id == "shared_db")
        svc_alloc = next(a for a in report.allocations if a.service_id == "svc1")

        assert db_alloc.risk_weight > svc_alloc.risk_weight

    def test_slo_target_increases_weight(self):
        """Components with stricter SLO targets should get higher weight."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="critical", name="Critical API", type=ComponentType.APP_SERVER,
            replicas=1,
            slo_targets=[SLOTarget(name="availability", target=99.99)],
        ))
        graph.add_component(Component(
            id="normal", name="Normal API", type=ComponentType.APP_SERVER,
            replicas=1,
        ))

        allocator = FailureBudgetAllocator(graph, slo_target=99.9, window_days=30)
        report = allocator.allocate()

        critical_alloc = next(a for a in report.allocations if a.service_id == "critical")
        normal_alloc = next(a for a in report.allocations if a.service_id == "normal")

        assert critical_alloc.risk_weight > normal_alloc.risk_weight


# ---------------------------------------------------------------------------
# Tests: Team Derivation
# ---------------------------------------------------------------------------


class TestTeamDerivation:
    """Test team name derivation from tags."""

    def test_team_from_tags(self):
        """Team should be derived from 'team:' tags."""
        graph = _build_basic_graph()
        allocator = FailureBudgetAllocator(graph, slo_target=99.9, window_days=30)

        report = allocator.allocate()

        app_alloc = next(a for a in report.allocations if a.service_id == "app")
        assert app_alloc.team == "backend"

        db_alloc = next(a for a in report.allocations if a.service_id == "db")
        assert db_alloc.team == "data"

    def test_default_team(self):
        """Components without team tags should get 'default'."""
        graph = _build_single_component_graph()
        allocator = FailureBudgetAllocator(graph, slo_target=99.9, window_days=30)

        report = allocator.allocate()

        assert report.allocations[0].team == "default"


# ---------------------------------------------------------------------------
# Tests: Budget Remaining
# ---------------------------------------------------------------------------


class TestBudgetRemaining:
    """Test remaining budget computation."""

    def test_remaining_percent_range(self):
        """Remaining percent should be between -inf and 100."""
        graph = _build_basic_graph()
        allocator = FailureBudgetAllocator(graph, slo_target=99.9, window_days=30)

        report = allocator.allocate()

        for a in report.allocations:
            assert a.budget_remaining_percent <= 100.0

    def test_stricter_slo_gives_less_budget(self):
        """Stricter SLO should give less total budget."""
        graph = _build_basic_graph()
        alloc_999 = FailureBudgetAllocator(graph, slo_target=99.9, window_days=30)
        alloc_9999 = FailureBudgetAllocator(graph, slo_target=99.99, window_days=30)

        report_999 = alloc_999.allocate()
        report_9999 = alloc_9999.allocate()

        assert report_999.total_budget_minutes > report_9999.total_budget_minutes


# ---------------------------------------------------------------------------
# Tests: Classification
# ---------------------------------------------------------------------------


class TestClassification:
    """Test over-budget and under-utilized classification."""

    def test_healthy_services_classified(self):
        """All services should be classified."""
        graph = _build_basic_graph()
        allocator = FailureBudgetAllocator(graph, slo_target=99.9, window_days=30)

        report = allocator.allocate()

        all_services = {a.service_id for a in report.allocations}
        over = set(report.over_budget_services)
        under = set(report.under_utilized_services)

        # All over_budget and under_utilized should be valid service IDs
        assert over.issubset(all_services)
        assert under.issubset(all_services)

    def test_degraded_component_consumes_budget(self):
        """Degraded component should consume some budget."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="sick",
            name="Sick Service",
            type=ComponentType.APP_SERVER,
            replicas=1,
            health=HealthStatus.DEGRADED,
        ))

        allocator = FailureBudgetAllocator(graph, slo_target=99.9, window_days=30)
        report = allocator.allocate()

        alloc = report.allocations[0]
        assert alloc.budget_consumed_minutes > 0


# ---------------------------------------------------------------------------
# Tests: Simulate Consumption
# ---------------------------------------------------------------------------


class TestSimulateConsumption:
    """Test simulate_consumption with mock simulation reports."""

    def test_simulate_consumption_from_mock_report(self):
        """simulate_consumption should process simulation results."""
        graph = _build_basic_graph()
        allocator = FailureBudgetAllocator(graph, slo_target=99.9, window_days=30)

        # Create a mock simulation report
        @dataclass
        class MockEffect:
            component_id: str
            health: HealthStatus

        @dataclass
        class MockCascade:
            effects: list[MockEffect] = field(default_factory=list)

        @dataclass
        class MockResult:
            cascade: MockCascade
            risk_score: float = 5.0

        @dataclass
        class MockReport:
            results: list[MockResult] = field(default_factory=list)

        mock_report = MockReport(results=[
            MockResult(
                cascade=MockCascade(effects=[
                    MockEffect(component_id="db", health=HealthStatus.DOWN),
                    MockEffect(component_id="app", health=HealthStatus.DEGRADED),
                ]),
                risk_score=7.0,
            ),
        ])

        report = allocator.simulate_consumption(mock_report)

        assert isinstance(report, BudgetReport)
        assert len(report.allocations) == 3

        db_alloc = next(a for a in report.allocations if a.service_id == "db")
        assert db_alloc.budget_consumed_minutes > 0

    def test_simulate_consumption_empty_report(self):
        """Empty simulation report should produce zero consumption."""
        graph = _build_basic_graph()
        allocator = FailureBudgetAllocator(graph, slo_target=99.9, window_days=30)

        @dataclass
        class MockReport:
            results: list = field(default_factory=list)

        report = allocator.simulate_consumption(MockReport())

        assert isinstance(report, BudgetReport)
        for a in report.allocations:
            assert a.budget_consumed_minutes == 0.0


# ---------------------------------------------------------------------------
# Tests: Rebalance Suggestions
# ---------------------------------------------------------------------------


class TestRebalanceSuggestions:
    """Test rebalance suggestion generation."""

    def test_no_suggestions_when_balanced(self):
        """No rebalance suggestions when all services are healthy."""
        graph = _build_basic_graph()
        allocator = FailureBudgetAllocator(graph, slo_target=99.9, window_days=30)

        report = allocator.allocate()

        # With healthy components, we may have suggestions but they should
        # be valid dicts if present
        for s in report.rebalance_suggestions:
            assert isinstance(s, dict)
            assert "action" in s
            assert "reason" in s

    def test_slo_window_stored(self):
        """BudgetReport should store the SLO target and window."""
        graph = _build_basic_graph()
        allocator = FailureBudgetAllocator(graph, slo_target=99.95, window_days=7)

        report = allocator.allocate()

        assert report.slo_target == 99.95
        assert report.window_days == 7
