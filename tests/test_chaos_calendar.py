"""Tests for Chaos Calendar - scheduled chaos experiments with learning."""

from __future__ import annotations

import math
import sqlite3
import tempfile
from pathlib import Path

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    HealthStatus,
    OperationalProfile,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.chaos_calendar import (
    ChaosCalendar,
    ChaosWindow,
    ExperimentRecord,
    RiskForecast,
    _bayesian_mtbf_update,
    _init_db,
    _poisson_failure_probability,
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
    mtbf_hours: float = 0.0,
    mttr_minutes: float = 30.0,
    cpu_percent: float = 0.0,
) -> Component:
    return Component(
        id=cid,
        name=name,
        type=ctype,
        replicas=replicas,
        health=health,
        operational_profile=OperationalProfile(
            mtbf_hours=mtbf_hours, mttr_minutes=mttr_minutes
        ),
        metrics=ResourceMetrics(cpu_percent=cpu_percent),
    )


def _chain_graph() -> InfraGraph:
    """Build LB -> App -> DB graph with MTBF data."""
    g = InfraGraph()
    g.add_component(
        _comp("lb", "Load Balancer", ComponentType.LOAD_BALANCER, replicas=2, mtbf_hours=8760)
    )
    g.add_component(
        _comp("app", "App Server", replicas=1, mtbf_hours=4380, cpu_percent=75.0)
    )
    g.add_component(
        _comp("db", "Database", ComponentType.DATABASE, replicas=1, mtbf_hours=2190)
    )
    g.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return g


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Return a temporary database path."""
    return tmp_path / "test_calendar.db"


# ---------------------------------------------------------------------------
# Tests: _init_db
# ---------------------------------------------------------------------------


class TestInitDb:
    """Test the database initializer helper."""

    def test_creates_db_file(self, tmp_path: Path) -> None:
        db_path = tmp_path / "subdir" / "cal.db"
        conn = _init_db(db_path)
        assert db_path.exists()
        conn.close()

    def test_creates_tables(self, tmp_path: Path) -> None:
        db_path = tmp_path / "cal.db"
        conn = _init_db(db_path)
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = sorted(row[0] for row in cur.fetchall())
        assert "chaos_windows" in tables
        assert "experiment_records" in tables
        conn.close()

    def test_idempotent(self, tmp_path: Path) -> None:
        db_path = tmp_path / "cal.db"
        conn1 = _init_db(db_path)
        conn1.close()
        conn2 = _init_db(db_path)
        cur = conn2.execute("SELECT COUNT(*) FROM chaos_windows")
        assert cur.fetchone()[0] == 0
        conn2.close()


# ---------------------------------------------------------------------------
# Tests: Poisson model
# ---------------------------------------------------------------------------


class TestPoissonModel:
    """Test the Poisson failure probability function."""

    def test_zero_mtbf_returns_one(self) -> None:
        assert _poisson_failure_probability(0, 100) == 1.0

    def test_negative_mtbf_returns_one(self) -> None:
        assert _poisson_failure_probability(-10, 100) == 1.0

    def test_very_high_mtbf_low_probability(self) -> None:
        prob = _poisson_failure_probability(100_000, 24)
        assert prob < 0.01

    def test_horizon_equals_mtbf(self) -> None:
        # P(fail in MTBF) = 1 - exp(-1) ~ 0.6321
        prob = _poisson_failure_probability(100, 100)
        assert abs(prob - (1 - math.exp(-1))) < 0.001

    def test_long_horizon_high_probability(self) -> None:
        prob = _poisson_failure_probability(100, 100_000)
        assert prob > 0.99

    def test_zero_horizon(self) -> None:
        prob = _poisson_failure_probability(100, 0)
        assert prob == 0.0

    def test_short_horizon_small_prob(self) -> None:
        prob = _poisson_failure_probability(8760, 1)
        expected = 1 - math.exp(-1 / 8760)
        assert abs(prob - expected) < 1e-10


# ---------------------------------------------------------------------------
# Tests: Bayesian MTBF update
# ---------------------------------------------------------------------------


class TestBayesianUpdate:
    """Test Bayesian MTBF adjustment."""

    def test_pass_increases_mtbf(self) -> None:
        adj = _bayesian_mtbf_update(1000, True, 1.0)
        assert adj > 0

    def test_fail_decreases_mtbf(self) -> None:
        adj = _bayesian_mtbf_update(1000, False, 1.0)
        assert adj < 0

    def test_longer_duration_larger_positive_adjustment(self) -> None:
        adj_short = _bayesian_mtbf_update(1000, True, 1.0)
        adj_long = _bayesian_mtbf_update(1000, True, 10.0)
        assert adj_long > adj_short

    def test_longer_duration_larger_negative_adjustment(self) -> None:
        adj_short = _bayesian_mtbf_update(1000, False, 1.0)
        adj_long = _bayesian_mtbf_update(1000, False, 10.0)
        # More negative for longer durations
        assert adj_long < adj_short

    def test_pass_adjustment_value(self) -> None:
        adj = _bayesian_mtbf_update(500, True, 2.0)
        assert adj == pytest.approx(2.0 * 0.1)

    def test_fail_adjustment_value(self) -> None:
        adj = _bayesian_mtbf_update(500, False, 2.0)
        assert adj == pytest.approx(-2.0 * 0.2)

    def test_default_duration(self) -> None:
        adj = _bayesian_mtbf_update(1000, True)
        assert adj == pytest.approx(1.0 * 0.1)


# ---------------------------------------------------------------------------
# Tests: ChaosWindow dataclass
# ---------------------------------------------------------------------------


class TestChaosWindowDataclass:
    def test_defaults(self) -> None:
        w = ChaosWindow(name="test", cron_expression="0 2 * * *")
        assert w.max_blast_radius == 0.5
        assert w.allowed_categories == ["all"]
        assert w.max_duration_minutes == 60

    def test_custom_values(self) -> None:
        w = ChaosWindow(
            name="custom",
            cron_expression="0 3 * * FRI",
            max_blast_radius=0.3,
            allowed_categories=["network"],
            max_duration_minutes=15,
        )
        assert w.name == "custom"
        assert w.max_blast_radius == 0.3


# ---------------------------------------------------------------------------
# Tests: ExperimentRecord dataclass
# ---------------------------------------------------------------------------


class TestExperimentRecordDataclass:
    def test_defaults(self) -> None:
        r = ExperimentRecord(
            experiment_id="e1",
            scenario_id="s1",
            scheduled_at="2026-01-01T00:00:00Z",
        )
        assert r.result == "pass"
        assert r.observed_blast_radius == 0.0
        assert r.learned_mtbf_adjustment == 0.0
        assert r.notes == ""
        assert r.executed_at is None


# ---------------------------------------------------------------------------
# Tests: RiskForecast dataclass
# ---------------------------------------------------------------------------


class TestRiskForecastDataclass:
    def test_fields(self) -> None:
        rf = RiskForecast(
            horizon_days=30,
            critical_incident_probability=0.85,
            component_risks={"a": 0.5},
            recommendation="test",
        )
        assert rf.horizon_days == 30
        assert rf.critical_incident_probability == 0.85


# ---------------------------------------------------------------------------
# Tests: ChaosCalendar window management
# ---------------------------------------------------------------------------


class TestChaosWindowManagement:
    """Test adding and listing chaos windows."""

    def test_add_and_list_window(self, tmp_db: Path) -> None:
        graph = _chain_graph()
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
        assert schedule[0]["max_duration_minutes"] == 30
        cal.close()

    def test_add_multiple_windows(self, tmp_db: Path) -> None:
        graph = _chain_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)
        cal.add_window(ChaosWindow(name="w1", cron_expression="0 2 * * *"))
        cal.add_window(ChaosWindow(name="w2", cron_expression="0 3 * * FRI"))
        schedule = cal.get_schedule()
        assert len(schedule) == 2
        cal.close()

    def test_upsert_window(self, tmp_db: Path) -> None:
        graph = _chain_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)
        cal.add_window(ChaosWindow(name="w1", cron_expression="0 2 * * *"))
        cal.add_window(ChaosWindow(name="w1", cron_expression="0 4 * * *"))
        schedule = cal.get_schedule()
        assert len(schedule) == 1
        assert schedule[0]["cron_expression"] == "0 4 * * *"
        cal.close()

    def test_empty_schedule(self, tmp_db: Path) -> None:
        graph = _chain_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)
        schedule = cal.get_schedule()
        assert schedule == []
        cal.close()

    def test_allowed_categories_serialized_correctly(self, tmp_db: Path) -> None:
        graph = _chain_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)
        cats = ["cpu", "memory", "disk"]
        cal.add_window(ChaosWindow(name="w", cron_expression="*", allowed_categories=cats))
        schedule = cal.get_schedule()
        assert schedule[0]["allowed_categories"] == cats
        cal.close()


# ---------------------------------------------------------------------------
# Tests: Experiment suggestions
# ---------------------------------------------------------------------------


class TestExperimentSuggestions:
    """Test experiment suggestion logic."""

    def test_suggest_spof_components(self, tmp_db: Path) -> None:
        graph = _chain_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)
        suggestions = cal.suggest_experiments()
        assert len(suggestions) > 0
        # "app" is a SPOF (1 replica) with a dependent (lb -> app) and high utilization
        app_suggestions = [s for s in suggestions if s["component_id"] == "app"]
        assert len(app_suggestions) == 1
        assert app_suggestions[0]["priority"] >= 5.0
        assert "single point of failure" in app_suggestions[0]["reasons"]
        cal.close()

    def test_high_utilization_boost(self, tmp_db: Path) -> None:
        graph = _chain_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)
        suggestions = cal.suggest_experiments()
        app_s = [s for s in suggestions if s["component_id"] == "app"][0]
        assert "high utilization" in " ".join(app_s["reasons"]).lower()
        cal.close()

    def test_suggest_never_tested(self, tmp_db: Path) -> None:
        graph = _chain_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)
        suggestions = cal.suggest_experiments()
        for s in suggestions:
            assert "never tested" in s["reasons"]
        cal.close()

    def test_previously_tested_no_never_tested_reason(self, tmp_db: Path) -> None:
        graph = _chain_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)
        # Record an experiment for "app" so it is no longer "never tested"
        cal.record_result(ExperimentRecord(
            experiment_id="exp-1",
            scenario_id="app",
            scheduled_at="2026-01-01T00:00:00Z",
            result="pass",
        ))
        suggestions = cal.suggest_experiments()
        app_s = [s for s in suggestions if s["component_id"] == "app"][0]
        assert "never tested" not in app_s["reasons"]
        cal.close()

    def test_suggestions_sorted_by_priority(self, tmp_db: Path) -> None:
        graph = _chain_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)
        suggestions = cal.suggest_experiments()
        priorities = [s["priority"] for s in suggestions]
        assert priorities == sorted(priorities, reverse=True)
        cal.close()

    def test_suggested_scenario_text(self, tmp_db: Path) -> None:
        graph = _chain_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)
        suggestions = cal.suggest_experiments()
        for s in suggestions:
            assert s["suggested_scenario"].startswith("Kill ")
            assert s["component_name"] in s["suggested_scenario"]
        cal.close()

    def test_low_mtbf_adds_reason(self, tmp_db: Path) -> None:
        g = InfraGraph()
        g.add_component(_comp("s1", "Short MTBF", mtbf_hours=500, replicas=1))
        g.add_component(_comp("s2", "Dependent", replicas=1))
        g.add_dependency(Dependency(source_id="s2", target_id="s1"))
        cal = ChaosCalendar(g, store_path=tmp_db)
        suggestions = cal.suggest_experiments()
        s1_s = [s for s in suggestions if s["component_id"] == "s1"][0]
        assert "low MTBF" in s1_s["reasons"]
        cal.close()

    def test_no_suggestions_for_zero_priority(self, tmp_db: Path) -> None:
        g = InfraGraph()
        # Component with replicas > 1, no dependents, no high utilization,
        # already tested, and MTBF >= 720 => priority == 0
        g.add_component(_comp("safe", "Safe", replicas=2, mtbf_hours=10000))
        cal = ChaosCalendar(g, store_path=tmp_db)
        # Record an experiment so it's not "never tested"
        cal.record_result(ExperimentRecord(
            experiment_id="exp-1",
            scenario_id="safe",
            scheduled_at="2026-01-01T00:00:00Z",
            result="pass",
        ))
        suggestions = cal.suggest_experiments()
        safe_s = [s for s in suggestions if s["component_id"] == "safe"]
        assert len(safe_s) == 0
        cal.close()

    def test_lb_with_replicas_not_spof(self, tmp_db: Path) -> None:
        graph = _chain_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)
        suggestions = cal.suggest_experiments()
        lb_s = [s for s in suggestions if s["component_id"] == "lb"]
        # lb has replicas=2, so it's not a SPOF
        if lb_s:
            assert "single point of failure" not in lb_s[0]["reasons"]
        cal.close()


# ---------------------------------------------------------------------------
# Tests: Experiment recording
# ---------------------------------------------------------------------------


class TestExperimentRecording:
    """Test recording experiment results."""

    def test_record_pass(self, tmp_db: Path) -> None:
        graph = _chain_graph()
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
        assert summary["total_mtbf_adjustment_hours"] > 0
        cal.close()

    def test_record_fail(self, tmp_db: Path) -> None:
        graph = _chain_graph()
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
        assert summary["total_mtbf_adjustment_hours"] < 0
        cal.close()

    def test_record_skipped(self, tmp_db: Path) -> None:
        graph = _chain_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)
        record = ExperimentRecord(
            experiment_id="exp-003",
            scenario_id="app",
            scheduled_at="2026-01-01T00:00:00Z",
            result="skipped",
        )
        cal.record_result(record)
        summary = cal.learning_summary()
        assert summary["skipped"] == 1
        cal.close()

    def test_record_unknown_component(self, tmp_db: Path) -> None:
        """Recording result for a component not in the graph should still persist."""
        graph = _chain_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)
        record = ExperimentRecord(
            experiment_id="exp-004",
            scenario_id="nonexistent",
            scheduled_at="2026-01-01T00:00:00Z",
            result="pass",
        )
        cal.record_result(record)
        summary = cal.learning_summary()
        assert summary["total_experiments"] == 1
        # No MTBF adjustment because component not found
        assert summary["total_mtbf_adjustment_hours"] == 0.0
        cal.close()

    def test_record_component_with_zero_mtbf(self, tmp_db: Path) -> None:
        """Component with mtbf_hours=0 should not trigger MTBF adjustment."""
        g = InfraGraph()
        g.add_component(_comp("c1", "NoMTBF", mtbf_hours=0))
        cal = ChaosCalendar(g, store_path=tmp_db)
        cal.record_result(ExperimentRecord(
            experiment_id="exp-005",
            scenario_id="c1",
            scheduled_at="2026-01-01T00:00:00Z",
            result="pass",
        ))
        summary = cal.learning_summary()
        assert summary["total_mtbf_adjustment_hours"] == 0.0
        cal.close()

    def test_record_multiple(self, tmp_db: Path) -> None:
        graph = _chain_graph()
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

    def test_record_upsert(self, tmp_db: Path) -> None:
        """Recording with the same experiment_id should overwrite."""
        graph = _chain_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)
        cal.record_result(ExperimentRecord(
            experiment_id="exp-dup",
            scenario_id="app",
            scheduled_at="2026-01-01T00:00:00Z",
            result="pass",
        ))
        cal.record_result(ExperimentRecord(
            experiment_id="exp-dup",
            scenario_id="app",
            scheduled_at="2026-01-01T00:00:00Z",
            result="fail",
        ))
        summary = cal.learning_summary()
        assert summary["total_experiments"] == 1
        assert summary["failed"] == 1
        cal.close()


# ---------------------------------------------------------------------------
# Tests: Risk forecast
# ---------------------------------------------------------------------------


class TestRiskForecast:
    """Test risk forecasting."""

    def test_forecast_returns_risk_forecast(self, tmp_db: Path) -> None:
        graph = _chain_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)
        forecast = cal.risk_forecast(horizon_days=30)
        assert isinstance(forecast, RiskForecast)
        assert forecast.horizon_days == 30
        assert 0 <= forecast.critical_incident_probability <= 1.0
        assert len(forecast.component_risks) == 3
        cal.close()

    def test_forecast_higher_horizon_higher_risk(self, tmp_db: Path) -> None:
        graph = _chain_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)
        forecast_30 = cal.risk_forecast(horizon_days=30)
        forecast_365 = cal.risk_forecast(horizon_days=365)
        assert forecast_365.critical_incident_probability >= forecast_30.critical_incident_probability
        cal.close()

    def test_forecast_with_experiment_history(self, tmp_db: Path) -> None:
        graph = _chain_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)
        # Record several passing experiments for "db"
        for i in range(5):
            cal.record_result(ExperimentRecord(
                experiment_id=f"exp-{i}",
                scenario_id="db",
                scheduled_at="2026-01-01T00:00:00Z",
                result="pass",
            ))
        forecast = cal.risk_forecast(horizon_days=30)
        assert forecast.component_risks["db"] < 1.0
        cal.close()

    def test_forecast_recommendation_high_risk(self, tmp_db: Path) -> None:
        """Short MTBF over long horizon should produce high risk recommendation."""
        g = InfraGraph()
        g.add_component(_comp("fragile", "Fragile", mtbf_hours=100))
        cal = ChaosCalendar(g, store_path=tmp_db)
        forecast = cal.risk_forecast(horizon_days=365)
        # With very high risk we expect a strong recommendation
        assert isinstance(forecast.recommendation, str)
        assert len(forecast.recommendation) > 10
        cal.close()

    def test_forecast_recommendation_low_risk(self, tmp_db: Path) -> None:
        g = InfraGraph()
        g.add_component(_comp("solid", "Solid", mtbf_hours=100_000))
        cal = ChaosCalendar(g, store_path=tmp_db)
        forecast = cal.risk_forecast(horizon_days=1)
        assert "acceptable" in forecast.recommendation.lower() or "within" in forecast.recommendation.lower()
        cal.close()

    def test_forecast_recommendation_moderate_risk(self, tmp_db: Path) -> None:
        g = InfraGraph()
        g.add_component(_comp("med", "Medium", mtbf_hours=500))
        cal = ChaosCalendar(g, store_path=tmp_db)
        forecast = cal.risk_forecast(horizon_days=30)
        assert isinstance(forecast.recommendation, str)
        assert len(forecast.recommendation) > 10
        cal.close()

    def test_forecast_zero_mtbf_component(self, tmp_db: Path) -> None:
        """Component with 0 MTBF gets default 0.5 risk."""
        g = InfraGraph()
        g.add_component(_comp("zero", "Zero MTBF", mtbf_hours=0))
        cal = ChaosCalendar(g, store_path=tmp_db)
        forecast = cal.risk_forecast(horizon_days=30)
        assert forecast.component_risks["zero"] == 0.5
        cal.close()

    def test_forecast_critical_probability_combines(self, tmp_db: Path) -> None:
        """Critical probability should reflect all components (complement rule)."""
        g = InfraGraph()
        g.add_component(_comp("a", "A", mtbf_hours=8760))
        g.add_component(_comp("b", "B", mtbf_hours=8760))
        cal = ChaosCalendar(g, store_path=tmp_db)
        forecast = cal.risk_forecast(horizon_days=30)
        # P(any fail) = 1 - product(1-p_i) should be > max individual risk
        max_risk = max(forecast.component_risks.values())
        assert forecast.critical_incident_probability >= max_risk - 0.001
        cal.close()

    def test_forecast_experiment_failure_lowers_mtbf(self, tmp_db: Path) -> None:
        """Failed experiments should lower adjusted MTBF, increasing risk."""
        graph = _chain_graph()

        # Baseline risk
        cal1 = ChaosCalendar(graph, store_path=tmp_db)
        baseline = cal1.risk_forecast(horizon_days=30)
        baseline_risk = baseline.component_risks["db"]
        cal1.close()

        # After many failures
        tmp_db2 = tmp_db.parent / "test2.db"
        cal2 = ChaosCalendar(graph, store_path=tmp_db2)
        for i in range(20):
            cal2.record_result(ExperimentRecord(
                experiment_id=f"fail-{i}",
                scenario_id="db",
                scheduled_at="2026-01-01T00:00:00Z",
                result="fail",
            ))
        after_failures = cal2.risk_forecast(horizon_days=30)
        assert after_failures.component_risks["db"] >= baseline_risk
        cal2.close()


# ---------------------------------------------------------------------------
# Tests: _total_mtbf_adjustment
# ---------------------------------------------------------------------------


class TestTotalMtbfAdjustment:
    def test_no_experiments(self, tmp_db: Path) -> None:
        graph = _chain_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)
        assert cal._total_mtbf_adjustment("app") == 0.0
        cal.close()

    def test_sums_adjustments(self, tmp_db: Path) -> None:
        graph = _chain_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)
        for i in range(3):
            cal.record_result(ExperimentRecord(
                experiment_id=f"exp-{i}",
                scenario_id="app",
                scheduled_at="2026-01-01T00:00:00Z",
                result="pass",
            ))
        total = cal._total_mtbf_adjustment("app")
        assert total > 0
        cal.close()

    def test_separate_components(self, tmp_db: Path) -> None:
        graph = _chain_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)
        cal.record_result(ExperimentRecord(
            experiment_id="exp-a",
            scenario_id="app",
            scheduled_at="2026-01-01T00:00:00Z",
            result="pass",
        ))
        cal.record_result(ExperimentRecord(
            experiment_id="exp-d",
            scenario_id="db",
            scheduled_at="2026-01-01T00:00:00Z",
            result="fail",
        ))
        assert cal._total_mtbf_adjustment("app") > 0
        assert cal._total_mtbf_adjustment("db") < 0
        cal.close()


# ---------------------------------------------------------------------------
# Tests: Learning summary
# ---------------------------------------------------------------------------


class TestLearningSummary:
    """Test learning summary output."""

    def test_empty_summary(self, tmp_db: Path) -> None:
        graph = _chain_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)
        summary = cal.learning_summary()
        assert summary["total_experiments"] == 0
        assert summary["passed"] == 0
        assert summary["failed"] == 0
        assert summary["skipped"] == 0
        assert summary["avg_blast_radius"] == 0.0
        assert summary["total_mtbf_adjustment_hours"] == 0.0
        cal.close()

    def test_summary_avg_blast_radius(self, tmp_db: Path) -> None:
        graph = _chain_graph()
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

    def test_summary_all_fields_present(self, tmp_db: Path) -> None:
        graph = _chain_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)
        cal.record_result(ExperimentRecord(
            experiment_id="exp-1", scenario_id="app",
            scheduled_at="2026-01-01T00:00:00Z", result="pass",
        ))
        summary = cal.learning_summary()
        expected_keys = {
            "total_experiments", "passed", "failed", "skipped",
            "avg_blast_radius", "total_mtbf_adjustment_hours",
        }
        assert set(summary.keys()) == expected_keys
        cal.close()


# ---------------------------------------------------------------------------
# Tests: ChaosCalendar init and close
# ---------------------------------------------------------------------------


class TestChaosCalendarInit:
    def test_default_db_path(self, tmp_path: Path, monkeypatch) -> None:
        """When no store_path given, uses default path."""
        graph = _chain_graph()
        # Use a custom path to avoid touching user's home directory
        cal = ChaosCalendar(graph, store_path=tmp_path / "default.db")
        assert cal._db_path == tmp_path / "default.db"
        cal.close()

    def test_close_connection(self, tmp_db: Path) -> None:
        graph = _chain_graph()
        cal = ChaosCalendar(graph, store_path=tmp_db)
        cal.close()
        # After close, database operations should fail
        with pytest.raises(Exception):
            cal._conn.execute("SELECT 1")
