"""Tests for Chaos Calendar - scheduled chaos experiments with learning."""

from __future__ import annotations

import math
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from infrasim.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    OperationalProfile,
    ResourceMetrics,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.chaos_calendar import (
    ChaosCalendar,
    ChaosWindow,
    ExperimentRecord,
    RiskForecast,
    _bayesian_mtbf_update,
    _poisson_failure_probability,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _build_graph() -> InfraGraph:
    """Build a simple 3-component graph with MTBF data."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2,
        operational_profile=OperationalProfile(mtbf_hours=8760),  # 1 year
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=75.0),
        operational_profile=OperationalProfile(mtbf_hours=4380),  # 6 months
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=1,
        operational_profile=OperationalProfile(mtbf_hours=2190),  # 3 months
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return graph


@pytest.fixture
def tmp_db(tmp_path):
    """Return a temporary database path."""
    return tmp_path / "test_calendar.db"


# ---------------------------------------------------------------------------
# Tests: Poisson model
# ---------------------------------------------------------------------------

class TestPoissonModel:
    """Test the Poisson failure probability function."""

    def test_zero_mtbf_returns_one(self):
        assert _poisson_failure_probability(0, 100) == 1.0

    def test_very_high_mtbf_low_probability(self):
        # MTBF = 100000h, horizon = 24h => very low probability
        prob = _poisson_failure_probability(100000, 24)
        assert prob < 0.01

    def test_horizon_equals_mtbf(self):
        # P(fail in MTBF) = 1 - exp(-1) ≈ 0.6321
        prob = _poisson_failure_probability(100, 100)
        assert abs(prob - (1 - math.exp(-1))) < 0.001

    def test_long_horizon_high_probability(self):
        # Over a very long horizon, probability approaches 1
        prob = _poisson_failure_probability(100, 100000)
        assert prob > 0.99


class TestBayesianUpdate:
    """Test Bayesian MTBF adjustment."""

    def test_pass_increases_mtbf(self):
        adj = _bayesian_mtbf_update(1000, True, 1.0)
        assert adj > 0

    def test_fail_decreases_mtbf(self):
        adj = _bayesian_mtbf_update(1000, False, 1.0)
        assert adj < 0

    def test_longer_duration_larger_adjustment(self):
        adj_short = _bayesian_mtbf_update(1000, True, 1.0)
        adj_long = _bayesian_mtbf_update(1000, True, 10.0)
        assert adj_long > adj_short


# ---------------------------------------------------------------------------
# Tests: ChaosCalendar
# ---------------------------------------------------------------------------

class TestChaosWindowManagement:
    """Test adding and listing chaos windows."""

    def test_add_and_list_window(self, tmp_db):
        graph = _build_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)

        window = ChaosWindow(
            name="Weekly chaos",
            cron_expression="0 2 * * THU",
            max_blast_radius=0.5,
            allowed_categories=["network", "compute"],
            max_duration_minutes=30,
        )
        cal.add_window(window)

        schedule = cal.get_schedule()
        assert len(schedule) == 1
        assert schedule[0]["name"] == "Weekly chaos"
        assert schedule[0]["cron_expression"] == "0 2 * * THU"
        assert schedule[0]["max_blast_radius"] == 0.5
        assert "network" in schedule[0]["allowed_categories"]
        cal.close()

    def test_add_multiple_windows(self, tmp_db):
        graph = _build_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)

        cal.add_window(ChaosWindow(name="w1", cron_expression="0 2 * * *"))
        cal.add_window(ChaosWindow(name="w2", cron_expression="0 3 * * FRI"))

        schedule = cal.get_schedule()
        assert len(schedule) == 2
        cal.close()

    def test_upsert_window(self, tmp_db):
        graph = _build_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)

        cal.add_window(ChaosWindow(name="w1", cron_expression="0 2 * * *"))
        cal.add_window(ChaosWindow(name="w1", cron_expression="0 4 * * *"))

        schedule = cal.get_schedule()
        assert len(schedule) == 1
        assert schedule[0]["cron_expression"] == "0 4 * * *"
        cal.close()


class TestExperimentSuggestions:
    """Test experiment suggestion logic."""

    def test_suggest_spof_components(self, tmp_db):
        graph = _build_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)

        suggestions = cal.suggest_experiments()
        assert len(suggestions) > 0

        # "app" is a SPOF (1 replica) with a dependent (lb -> app), high utilization
        app_suggestions = [s for s in suggestions if s["component_id"] == "app"]
        assert len(app_suggestions) == 1
        assert app_suggestions[0]["priority"] >= 5.0  # SPOF bonus
        cal.close()

    def test_suggest_never_tested(self, tmp_db):
        graph = _build_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)

        suggestions = cal.suggest_experiments()
        # All components should have "never tested" in their reasons
        for s in suggestions:
            assert "never tested" in s["reasons"]
        cal.close()

    def test_suggestions_sorted_by_priority(self, tmp_db):
        graph = _build_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)

        suggestions = cal.suggest_experiments()
        priorities = [s["priority"] for s in suggestions]
        assert priorities == sorted(priorities, reverse=True)
        cal.close()


class TestExperimentRecording:
    """Test recording experiment results."""

    def test_record_pass(self, tmp_db):
        graph = _build_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)

        record = ExperimentRecord(
            experiment_id="exp-001",
            scenario_id="app",
            scheduled_at="2026-01-01T00:00:00Z",
            executed_at="2026-01-01T02:00:00Z",
            result="pass",
            observed_blast_radius=0.1,
        )
        cal.record_result(record)

        summary = cal.learning_summary()
        assert summary["total_experiments"] == 1
        assert summary["passed"] == 1
        assert summary["total_mtbf_adjustment_hours"] > 0  # pass increases MTBF
        cal.close()

    def test_record_fail(self, tmp_db):
        graph = _build_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)

        record = ExperimentRecord(
            experiment_id="exp-002",
            scenario_id="db",
            scheduled_at="2026-01-01T00:00:00Z",
            executed_at="2026-01-01T02:00:00Z",
            result="fail",
            observed_blast_radius=0.8,
        )
        cal.record_result(record)

        summary = cal.learning_summary()
        assert summary["total_experiments"] == 1
        assert summary["failed"] == 1
        assert summary["total_mtbf_adjustment_hours"] < 0  # fail decreases MTBF
        cal.close()

    def test_record_multiple(self, tmp_db):
        graph = _build_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)

        for i in range(5):
            cal.record_result(ExperimentRecord(
                experiment_id=f"exp-{i:03d}",
                scenario_id="app",
                scheduled_at="2026-01-01T00:00:00Z",
                result="pass" if i % 2 == 0 else "fail",
            ))

        summary = cal.learning_summary()
        assert summary["total_experiments"] == 5
        assert summary["passed"] == 3
        assert summary["failed"] == 2
        cal.close()


class TestRiskForecast:
    """Test risk forecasting."""

    def test_forecast_returns_risk_forecast(self, tmp_db):
        graph = _build_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)

        forecast = cal.risk_forecast(horizon_days=30)
        assert isinstance(forecast, RiskForecast)
        assert forecast.horizon_days == 30
        assert 0 <= forecast.critical_incident_probability <= 1.0
        assert len(forecast.component_risks) == 3
        cal.close()

    def test_forecast_higher_horizon_higher_risk(self, tmp_db):
        graph = _build_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)

        forecast_30 = cal.risk_forecast(horizon_days=30)
        forecast_365 = cal.risk_forecast(horizon_days=365)

        assert forecast_365.critical_incident_probability >= forecast_30.critical_incident_probability
        cal.close()

    def test_forecast_with_experiment_history(self, tmp_db):
        graph = _build_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)

        # Record several passing experiments for "db" (should increase MTBF)
        for i in range(5):
            cal.record_result(ExperimentRecord(
                experiment_id=f"exp-{i}",
                scenario_id="db",
                scheduled_at="2026-01-01T00:00:00Z",
                result="pass",
            ))

        forecast = cal.risk_forecast(horizon_days=30)
        # After passing experiments, db risk should be lower than without
        assert forecast.component_risks["db"] < 1.0
        cal.close()

    def test_forecast_recommendation_text(self, tmp_db):
        graph = _build_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)

        forecast = cal.risk_forecast(horizon_days=30)
        assert isinstance(forecast.recommendation, str)
        assert len(forecast.recommendation) > 10
        cal.close()


class TestLearningSummary:
    """Test learning summary output."""

    def test_empty_summary(self, tmp_db):
        graph = _build_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)

        summary = cal.learning_summary()
        assert summary["total_experiments"] == 0
        assert summary["passed"] == 0
        assert summary["failed"] == 0
        assert summary["skipped"] == 0
        cal.close()

    def test_summary_avg_blast_radius(self, tmp_db):
        graph = _build_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)

        cal.record_result(ExperimentRecord(
            experiment_id="exp-1", scenario_id="app",
            scheduled_at="2026-01-01T00:00:00Z", result="pass",
            observed_blast_radius=0.2,
        ))
        cal.record_result(ExperimentRecord(
            experiment_id="exp-2", scenario_id="db",
            scheduled_at="2026-01-01T00:00:00Z", result="fail",
            observed_blast_radius=0.8,
        ))

        summary = cal.learning_summary()
        assert summary["avg_blast_radius"] == pytest.approx(0.5, abs=0.01)
        cal.close()
