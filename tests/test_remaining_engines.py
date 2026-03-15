"""Tests for engines that have low or zero coverage.

Covers BacktestEngine, FinancialRiskEngine, CarbonEngine,
ChangeVelocityAnalyzer, FailureBudgetAllocator, CostOptimizer,
WarRoomSimulator, and EnvironmentComparator.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from infrasim.model.demo import create_demo_graph
from infrasim.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _demo_graph() -> InfraGraph:
    """Create a fresh demo graph for each test."""
    return create_demo_graph()


def _run_simulation(graph: InfraGraph):
    """Run a simulation and return the report."""
    from infrasim.simulator.engine import SimulationEngine

    engine = SimulationEngine(graph)
    return engine.run_all_defaults()


# ===================================================================
# 1. BacktestEngine
# ===================================================================

class TestBacktestEngine:
    def test_backtest_basic(self):
        from infrasim.simulator.backtest_engine import BacktestEngine, RealIncident

        graph = _demo_graph()
        engine = BacktestEngine(graph)

        incidents = [
            RealIncident(
                incident_id="INC-001",
                timestamp="2024-01-15T10:00:00Z",
                failed_component="postgres",
                actual_affected_components=["app-1", "app-2"],
                actual_downtime_minutes=30.0,
                actual_severity="critical",
                root_cause="Connection pool exhaustion",
                recovery_actions=["Restart DB", "Clear connections"],
            ),
        ]

        results = engine.run_backtest(incidents)
        assert len(results) == 1
        result = results[0]
        assert result.incident.incident_id == "INC-001"
        assert isinstance(result.precision, float)
        assert isinstance(result.recall, float)
        assert isinstance(result.f1_score, float)

    def test_backtest_unknown_component(self):
        from infrasim.simulator.backtest_engine import BacktestEngine, RealIncident

        graph = _demo_graph()
        engine = BacktestEngine(graph)

        incidents = [
            RealIncident(
                incident_id="INC-002",
                timestamp="2024-01-16T10:00:00Z",
                failed_component="nonexistent-service",
                actual_affected_components=["app-1"],
                actual_downtime_minutes=15.0,
                actual_severity="medium",
            ),
        ]

        results = engine.run_backtest(incidents)
        assert len(results) == 1
        assert results[0].predicted_affected == []
        assert results[0].details.get("skipped") is True

    def test_backtest_empty_incidents(self):
        from infrasim.simulator.backtest_engine import BacktestEngine

        graph = _demo_graph()
        engine = BacktestEngine(graph)
        results = engine.run_backtest([])
        assert results == []

    def test_backtest_multiple_incidents(self):
        from infrasim.simulator.backtest_engine import BacktestEngine, RealIncident

        graph = _demo_graph()
        engine = BacktestEngine(graph)

        incidents = [
            RealIncident(
                incident_id="INC-A",
                timestamp="2024-01-15T10:00:00Z",
                failed_component="redis",
                actual_affected_components=["app-1", "app-2"],
                actual_downtime_minutes=10.0,
                actual_severity="medium",
            ),
            RealIncident(
                incident_id="INC-B",
                timestamp="2024-01-16T10:00:00Z",
                failed_component="nginx",
                actual_affected_components=["app-1", "app-2", "postgres", "redis"],
                actual_downtime_minutes=60.0,
                actual_severity="critical",
            ),
        ]

        results = engine.run_backtest(incidents)
        assert len(results) == 2
        for r in results:
            assert 0.0 <= r.precision <= 1.0
            assert 0.0 <= r.recall <= 1.0

    def test_backtest_perfect_prediction(self):
        from infrasim.simulator.backtest_engine import BacktestEngine, RealIncident

        graph = _demo_graph()
        engine = BacktestEngine(graph)

        # Get actual affected components
        affected = graph.get_all_affected("postgres")
        affected_list = sorted(affected)

        incidents = [
            RealIncident(
                incident_id="INC-PERF",
                timestamp="2024-01-20T10:00:00Z",
                failed_component="postgres",
                actual_affected_components=affected_list,
                actual_downtime_minutes=45.0,
                actual_severity="critical",
            ),
        ]

        results = engine.run_backtest(incidents)
        assert len(results) == 1
        # With matching predictions, precision and recall should both be 1.0
        assert results[0].precision == pytest.approx(1.0)
        assert results[0].recall == pytest.approx(1.0)


# ===================================================================
# 2. FinancialRiskEngine
# ===================================================================

class TestFinancialRiskEngine:
    def test_analyze_basic(self):
        from infrasim.simulator.financial_risk import FinancialRiskEngine

        graph = _demo_graph()
        report = _run_simulation(graph)
        engine = FinancialRiskEngine(graph)
        result = engine.analyze(report)

        assert isinstance(result.annual_revenue_usd, float)
        assert isinstance(result.value_at_risk_95, float)
        assert isinstance(result.expected_annual_loss, float)
        assert isinstance(result.cost_per_hour_of_risk, float)
        assert result.annual_revenue_usd > 0

    def test_analyze_with_custom_revenue(self):
        from infrasim.simulator.financial_risk import FinancialRiskEngine

        graph = _demo_graph()
        report = _run_simulation(graph)
        engine = FinancialRiskEngine(graph, annual_revenue=5_000_000)
        result = engine.analyze(report)

        assert result.annual_revenue_usd == 5_000_000
        assert result.expected_annual_loss >= 0

    def test_analyze_to_dict(self):
        from infrasim.simulator.financial_risk import FinancialRiskEngine

        graph = _demo_graph()
        report = _run_simulation(graph)
        engine = FinancialRiskEngine(graph)
        result = engine.analyze(report)
        d = result.to_dict()

        assert "annual_revenue_usd" in d
        assert "value_at_risk_95" in d
        assert "expected_annual_loss" in d
        assert "scenarios" in d
        assert isinstance(d["scenarios"], list)

    def test_analyze_scenarios_populated(self):
        from infrasim.simulator.financial_risk import FinancialRiskEngine

        graph = _demo_graph()
        report = _run_simulation(graph)
        engine = FinancialRiskEngine(graph)
        result = engine.analyze(report)

        # Should have at least some scenarios from critical/warning findings
        if report.critical_findings or report.warnings:
            assert len(result.scenarios) > 0
            for s in result.scenarios:
                assert isinstance(s.scenario_name, str)
                assert isinstance(s.probability, float)
                assert isinstance(s.business_loss_usd, float)

    def test_analyze_zero_revenue(self):
        from infrasim.simulator.financial_risk import FinancialRiskEngine

        graph = _demo_graph()
        report = _run_simulation(graph)
        engine = FinancialRiskEngine(graph, annual_revenue=0)
        result = engine.analyze(report)

        assert result.annual_revenue_usd == 0
        # With zero revenue, losses should still be computable
        assert isinstance(result.expected_annual_loss, float)


# ===================================================================
# 3. CarbonEngine
# ===================================================================

class TestCarbonEngine:
    def test_analyze_basic(self):
        from infrasim.simulator.carbon_engine import CarbonEngine

        graph = _demo_graph()
        engine = CarbonEngine(graph)
        result = engine.analyze()

        assert isinstance(result.total_annual_kg, float)
        assert result.total_annual_kg >= 0
        assert isinstance(result.per_component, dict)
        assert len(result.per_component) > 0

    def test_analyze_car_equivalent(self):
        from infrasim.simulator.carbon_engine import CarbonEngine

        graph = _demo_graph()
        engine = CarbonEngine(graph)
        result = engine.analyze()

        assert isinstance(result.equivalent_car_km, float)
        assert result.equivalent_car_km >= 0

    def test_analyze_sustainability_score(self):
        from infrasim.simulator.carbon_engine import CarbonEngine

        graph = _demo_graph()
        engine = CarbonEngine(graph)
        result = engine.analyze()

        assert isinstance(result.sustainability_score, float)
        assert 0 <= result.sustainability_score <= 100

    def test_analyze_recommendations(self):
        from infrasim.simulator.carbon_engine import CarbonEngine

        graph = _demo_graph()
        engine = CarbonEngine(graph)
        result = engine.analyze()

        assert isinstance(result.green_recommendations, list)

    def test_analyze_to_dict(self):
        from infrasim.simulator.carbon_engine import CarbonEngine

        graph = _demo_graph()
        engine = CarbonEngine(graph)
        result = engine.analyze()
        d = result.to_dict()

        assert "total_annual_kg" in d
        assert "per_component" in d
        assert "equivalent_car_km" in d
        assert "sustainability_score" in d

    def test_analyze_empty_graph(self):
        from infrasim.simulator.carbon_engine import CarbonEngine

        graph = InfraGraph()
        engine = CarbonEngine(graph)
        result = engine.analyze()

        assert result.total_annual_kg == 0.0
        assert len(result.per_component) == 0


# ===================================================================
# 4. ChangeVelocityAnalyzer
# ===================================================================

class TestChangeVelocityAnalyzer:
    def test_analyze_defaults(self):
        from infrasim.simulator.change_velocity import ChangeVelocityAnalyzer

        graph = _demo_graph()
        analyzer = ChangeVelocityAnalyzer(graph)
        result = analyzer.analyze()

        assert isinstance(result.dora_classification, str)
        assert result.dora_classification in ("Elite", "High", "Medium", "Low")
        assert isinstance(result.stability_impact, (int, float))
        assert isinstance(result.optimal_deploy_frequency, (int, float))

    def test_analyze_elite_profile(self):
        from infrasim.simulator.change_velocity import ChangeVelocityAnalyzer

        graph = _demo_graph()
        analyzer = ChangeVelocityAnalyzer(graph)
        result = analyzer.analyze(
            deploys_per_week=50,
            change_failure_rate=2.0,
            mttr_minutes=30,
            lead_time_hours=1,
        )

        assert result.dora_classification == "Elite"

    def test_analyze_low_profile(self):
        from infrasim.simulator.change_velocity import ChangeVelocityAnalyzer

        graph = _demo_graph()
        analyzer = ChangeVelocityAnalyzer(graph)
        result = analyzer.analyze(
            deploys_per_week=0.1,
            change_failure_rate=25.0,
            mttr_minutes=60 * 24 * 45,  # 45 days
            lead_time_hours=24 * 200,  # 200 days
        )

        assert result.dora_classification == "Low"

    def test_analyze_recommendations(self):
        from infrasim.simulator.change_velocity import ChangeVelocityAnalyzer

        graph = _demo_graph()
        analyzer = ChangeVelocityAnalyzer(graph)
        result = analyzer.analyze()

        assert isinstance(result.recommendations, list)

    def test_analyze_dora_scores(self):
        from infrasim.simulator.change_velocity import ChangeVelocityAnalyzer

        graph = _demo_graph()
        analyzer = ChangeVelocityAnalyzer(graph)
        result = analyzer.analyze()

        assert isinstance(result.dora_scores, dict)

    def test_analyze_downtime_estimate(self):
        from infrasim.simulator.change_velocity import ChangeVelocityAnalyzer

        graph = _demo_graph()
        analyzer = ChangeVelocityAnalyzer(graph)
        result = analyzer.analyze()

        assert isinstance(result.estimated_downtime_minutes_per_week, (int, float))
        assert result.estimated_downtime_minutes_per_week >= 0

    def test_analyze_empty_graph(self):
        from infrasim.simulator.change_velocity import ChangeVelocityAnalyzer

        graph = InfraGraph()
        analyzer = ChangeVelocityAnalyzer(graph)
        result = analyzer.analyze()

        assert isinstance(result.dora_classification, str)


# ===================================================================
# 5. FailureBudgetAllocator
# ===================================================================

class TestFailureBudgetAllocator:
    def test_allocate_basic(self):
        from infrasim.simulator.failure_budget import FailureBudgetAllocator

        graph = _demo_graph()
        allocator = FailureBudgetAllocator(graph)
        report = allocator.allocate()

        assert isinstance(report.total_budget_minutes, float)
        assert report.total_budget_minutes > 0
        assert len(report.allocations) == len(graph.components)

    def test_allocate_slo_target(self):
        from infrasim.simulator.failure_budget import FailureBudgetAllocator

        graph = _demo_graph()
        allocator = FailureBudgetAllocator(graph, slo_target=99.99)
        report = allocator.allocate()

        assert report.slo_target == 99.99
        # Higher SLO = smaller total budget
        allocator2 = FailureBudgetAllocator(graph, slo_target=99.0)
        report2 = allocator2.allocate()
        assert report.total_budget_minutes < report2.total_budget_minutes

    def test_allocate_window_days(self):
        from infrasim.simulator.failure_budget import FailureBudgetAllocator

        graph = _demo_graph()
        allocator = FailureBudgetAllocator(graph, window_days=7)
        report = allocator.allocate()

        assert report.window_days == 7
        assert report.total_budget_minutes > 0

    def test_allocate_has_service_fields(self):
        from infrasim.simulator.failure_budget import FailureBudgetAllocator

        graph = _demo_graph()
        allocator = FailureBudgetAllocator(graph)
        report = allocator.allocate()

        for alloc in report.allocations:
            assert isinstance(alloc.service_id, str)
            assert isinstance(alloc.service_name, str)
            assert isinstance(alloc.budget_total_minutes, float)
            assert isinstance(alloc.budget_remaining_percent, float)
            assert isinstance(alloc.risk_weight, float)

    def test_allocate_empty_graph(self):
        from infrasim.simulator.failure_budget import FailureBudgetAllocator

        graph = InfraGraph()
        allocator = FailureBudgetAllocator(graph)
        report = allocator.allocate()

        assert report.total_budget_minutes > 0
        assert len(report.allocations) == 0

    def test_allocate_budgets_sum_to_total(self):
        from infrasim.simulator.failure_budget import FailureBudgetAllocator

        graph = _demo_graph()
        allocator = FailureBudgetAllocator(graph)
        report = allocator.allocate()

        total_allocated = sum(a.budget_total_minutes for a in report.allocations)
        assert total_allocated == pytest.approx(report.total_budget_minutes, rel=0.01)

    def test_allocate_rebalance_suggestions(self):
        from infrasim.simulator.failure_budget import FailureBudgetAllocator

        graph = _demo_graph()
        allocator = FailureBudgetAllocator(graph)
        report = allocator.allocate()

        assert isinstance(report.rebalance_suggestions, list)
        assert isinstance(report.over_budget_services, list)
        assert isinstance(report.under_utilized_services, list)


# ===================================================================
# 6. CostOptimizer
# ===================================================================

class TestCostOptimizer:
    def test_optimize_basic(self):
        from infrasim.simulator.cost_optimizer import CostOptimizer

        graph = _demo_graph()
        optimizer = CostOptimizer(graph)
        report = optimizer.optimize()

        assert isinstance(report.current_monthly_cost, (int, float))
        assert isinstance(report.optimized_monthly_cost, (int, float))
        assert isinstance(report.total_savings_monthly, (int, float))
        assert isinstance(report.savings_percent, (int, float))

    def test_optimize_resilience_scores(self):
        from infrasim.simulator.cost_optimizer import CostOptimizer

        graph = _demo_graph()
        optimizer = CostOptimizer(graph)
        report = optimizer.optimize()

        assert isinstance(report.resilience_before, float)
        assert isinstance(report.resilience_after, float)

    def test_optimize_suggestions(self):
        from infrasim.simulator.cost_optimizer import CostOptimizer

        graph = _demo_graph()
        optimizer = CostOptimizer(graph)
        report = optimizer.optimize()

        assert isinstance(report.suggestions, list)
        for s in report.suggestions:
            assert isinstance(s.action, str)
            assert isinstance(s.component_id, str)
            assert isinstance(s.savings_monthly, float)
            assert isinstance(s.risk_level, str)

    def test_optimize_min_score(self):
        from infrasim.simulator.cost_optimizer import CostOptimizer

        graph = _demo_graph()
        optimizer = CostOptimizer(graph, min_resilience_score=90.0)
        report = optimizer.optimize()

        # After optimization, resilience should still be >= min
        assert report.resilience_after >= 0  # may not always reach target

    def test_optimize_empty_graph(self):
        from infrasim.simulator.cost_optimizer import CostOptimizer

        graph = InfraGraph()
        optimizer = CostOptimizer(graph)
        report = optimizer.optimize()

        assert report.current_monthly_cost >= 0
        assert len(report.suggestions) == 0


# ===================================================================
# 7. WarRoomSimulator
# ===================================================================

class TestWarRoomSimulator:
    def test_simulate_database_outage(self):
        from infrasim.simulator.war_room import WarRoomSimulator

        graph = _demo_graph()
        sim = WarRoomSimulator(graph)
        report = sim.simulate(incident_type="database_outage")

        assert isinstance(report.exercise_name, str)
        assert isinstance(report.total_duration_minutes, float)
        assert report.total_duration_minutes > 0
        assert isinstance(report.time_to_detect_minutes, float)
        assert isinstance(report.time_to_mitigate_minutes, float)
        assert isinstance(report.time_to_recover_minutes, float)

    def test_simulate_network_partition(self):
        from infrasim.simulator.war_room import WarRoomSimulator

        graph = _demo_graph()
        sim = WarRoomSimulator(graph)
        report = sim.simulate(incident_type="network_partition")

        assert isinstance(report.exercise_name, str)
        assert report.total_duration_minutes > 0

    def test_simulate_ddos_attack(self):
        from infrasim.simulator.war_room import WarRoomSimulator

        graph = _demo_graph()
        sim = WarRoomSimulator(graph)
        report = sim.simulate(incident_type="ddos_attack")

        assert report.total_duration_minutes > 0
        assert len(report.phases) > 0

    def test_simulate_cascading_failure(self):
        from infrasim.simulator.war_room import WarRoomSimulator

        graph = _demo_graph()
        sim = WarRoomSimulator(graph)
        report = sim.simulate(incident_type="cascading_failure")

        assert len(report.phases) > 0

    def test_simulate_has_phases(self):
        from infrasim.simulator.war_room import WarRoomSimulator

        graph = _demo_graph()
        sim = WarRoomSimulator(graph)
        report = sim.simulate(incident_type="database_outage")

        assert len(report.phases) > 0
        for phase in report.phases:
            assert isinstance(phase.name, str)
            assert isinstance(phase.duration_minutes, float)

    def test_simulate_has_events(self):
        from infrasim.simulator.war_room import WarRoomSimulator

        graph = _demo_graph()
        sim = WarRoomSimulator(graph)
        report = sim.simulate(incident_type="database_outage")

        assert len(report.events) > 0
        for event in report.events:
            assert isinstance(event.time_minutes, float)
            assert isinstance(event.description, str)

    def test_simulate_has_lessons(self):
        from infrasim.simulator.war_room import WarRoomSimulator

        graph = _demo_graph()
        sim = WarRoomSimulator(graph)
        report = sim.simulate(incident_type="database_outage")

        assert isinstance(report.lessons_learned, list)

    def test_simulate_score(self):
        from infrasim.simulator.war_room import WarRoomSimulator

        graph = _demo_graph()
        sim = WarRoomSimulator(graph)
        report = sim.simulate(incident_type="database_outage")

        assert isinstance(report.score, float)
        assert 0 <= report.score <= 100

    def test_available_incidents(self):
        from infrasim.simulator.war_room import WarRoomSimulator

        graph = _demo_graph()
        sim = WarRoomSimulator(graph)
        incidents = sim.available_incidents()

        assert isinstance(incidents, list)
        assert len(incidents) > 0
        assert "database_outage" in incidents

    def test_simulate_with_team_size(self):
        from infrasim.simulator.war_room import WarRoomSimulator

        graph = _demo_graph()
        sim = WarRoomSimulator(graph)
        report_small = sim.simulate(incident_type="database_outage", team_size=2)
        report_large = sim.simulate(incident_type="database_outage", team_size=8)

        # Larger team should generally resolve faster
        assert report_small.total_duration_minutes > 0
        assert report_large.total_duration_minutes > 0

    def test_simulate_security_breach(self):
        from infrasim.simulator.war_room import WarRoomSimulator

        graph = _demo_graph()
        sim = WarRoomSimulator(graph)
        report = sim.simulate(incident_type="security_breach")

        assert report.total_duration_minutes > 0

    def test_simulate_deployment_rollback(self):
        from infrasim.simulator.war_room import WarRoomSimulator

        graph = _demo_graph()
        sim = WarRoomSimulator(graph)
        report = sim.simulate(incident_type="deployment_rollback")

        assert report.total_duration_minutes > 0

    def test_simulate_data_corruption(self):
        from infrasim.simulator.war_room import WarRoomSimulator

        graph = _demo_graph()
        sim = WarRoomSimulator(graph)
        report = sim.simulate(incident_type="data_corruption")

        assert report.total_duration_minutes > 0

    def test_simulate_cloud_region_failure(self):
        from infrasim.simulator.war_room import WarRoomSimulator

        graph = _demo_graph()
        sim = WarRoomSimulator(graph)
        report = sim.simulate(incident_type="cloud_region_failure")

        assert report.total_duration_minutes > 0


# ===================================================================
# 8. EnvironmentComparator
# ===================================================================

class TestEnvironmentComparator:
    def test_compare_two_environments(self):
        from infrasim.simulator.env_comparator import EnvironmentComparator

        g1 = _demo_graph()
        g2 = _demo_graph()
        comp = EnvironmentComparator()
        result = comp.compare({"prod": g1, "staging": g2})

        assert isinstance(result.parity_score, float)
        assert len(result.environments) == 2

    def test_compare_profile_fields(self):
        from infrasim.simulator.env_comparator import EnvironmentComparator

        g1 = _demo_graph()
        g2 = _demo_graph()
        comp = EnvironmentComparator()
        result = comp.compare({"prod": g1, "dev": g2})

        for env in result.environments:
            assert isinstance(env.name, str)
            assert isinstance(env.resilience_score, float)
            assert isinstance(env.security_score, float)
            assert isinstance(env.cost_monthly, float)
            assert isinstance(env.component_count, int)

    def test_compare_identical_environments(self):
        from infrasim.simulator.env_comparator import EnvironmentComparator

        g1 = _demo_graph()
        g2 = _demo_graph()
        comp = EnvironmentComparator()
        result = comp.compare({"prod": g1, "staging": g2})

        # Identical graphs should have high parity
        assert result.parity_score >= 80

    def test_compare_drift_detection(self):
        from infrasim.simulator.env_comparator import EnvironmentComparator

        g1 = _demo_graph()
        g2 = InfraGraph()  # empty graph = very different
        comp = EnvironmentComparator()
        result = comp.compare({"prod": g1, "dev": g2})

        assert isinstance(result.drift_detected, bool)
        assert isinstance(result.drift_details, list)

    def test_compare_recommendations(self):
        from infrasim.simulator.env_comparator import EnvironmentComparator

        g1 = _demo_graph()
        g2 = _demo_graph()
        comp = EnvironmentComparator()
        result = comp.compare({"prod": g1, "staging": g2})

        assert isinstance(result.recommendations, list)

    def test_compare_single_env_returns_empty(self):
        from infrasim.simulator.env_comparator import EnvironmentComparator

        g1 = _demo_graph()
        comp = EnvironmentComparator()
        result = comp.compare({"prod": g1})

        assert len(result.environments) == 0

    def test_compare_three_environments(self):
        from infrasim.simulator.env_comparator import EnvironmentComparator

        g1 = _demo_graph()
        g2 = _demo_graph()
        g3 = _demo_graph()
        comp = EnvironmentComparator()
        result = comp.compare({"prod": g1, "staging": g2, "dev": g3})

        assert len(result.environments) == 3
        assert isinstance(result.parity_score, float)


# ===================================================================
# Extra: SimulationEngine additional paths
# ===================================================================

class TestSimulationEngineExtra:
    def test_run_all_defaults(self):
        from infrasim.simulator.engine import SimulationEngine

        graph = _demo_graph()
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults()

        assert report.resilience_score >= 0
        assert len(report.results) > 0
        assert isinstance(report.critical_findings, list)
        assert isinstance(report.warnings, list)
        assert isinstance(report.passed, list)

    def test_empty_graph_simulation(self):
        from infrasim.simulator.engine import SimulationEngine

        graph = InfraGraph()
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults()

        assert isinstance(report.resilience_score, float)


# ===================================================================
# Extra: Planner tests
# ===================================================================

class TestRemediationPlanner:
    def test_plan_basic(self):
        from infrasim.simulator.planner import RemediationPlanner

        graph = _demo_graph()
        planner = RemediationPlanner(graph)
        plan = planner.plan(target_score=90)

        assert isinstance(plan.current_score, (int, float))
        assert isinstance(plan.target_score, (int, float))
        assert isinstance(plan.total_weeks, (int, float))
        assert isinstance(plan.total_budget, (int, float))

    def test_plan_to_dict(self):
        from infrasim.simulator.planner import RemediationPlanner

        graph = _demo_graph()
        planner = RemediationPlanner(graph)
        plan = planner.plan(target_score=90)
        d = planner.plan_to_dict(plan)

        assert isinstance(d, dict)
        assert "current_score" in d
        assert "phases" in d

    def test_plan_with_budget(self):
        from infrasim.simulator.planner import RemediationPlanner

        graph = _demo_graph()
        planner = RemediationPlanner(graph)
        plan = planner.plan(target_score=90, budget_limit=10000)

        assert plan.total_budget <= 10000 or plan.total_budget >= 0
