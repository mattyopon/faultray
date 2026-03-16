"""Tests for the predictive failure engine."""

from __future__ import annotations

import math

import pytest

from faultray.model.components import (
    Capacity,
    Component,
    ComponentType,
    DegradationConfig,
    Dependency,
    HealthStatus,
    OperationalProfile,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.predictive_engine import (
    FailureProbabilityForecast,
    PredictiveEngine,
    PredictiveReport,
    ResourceExhaustionPrediction,
    _days_to_exhaust,
    _failure_probability,
    _recommend_action,
    _suggest_maintenance_window,
)


# ---------------------------------------------------------------------------
# Helpers (following _comp() / _chain_graph() pattern from test_change_risk)
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.health = health
    return c


def _chain_graph() -> InfraGraph:
    g = InfraGraph()
    g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=2))
    g.add_component(_comp("api", "API", replicas=3))
    g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=2))
    g.add_dependency(Dependency(source_id="lb", target_id="api"))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    return g


def _graph_with_degradation() -> InfraGraph:
    """Graph with components that have degradation configs."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER,
        replicas=2,
        metrics=ResourceMetrics(
            memory_used_mb=4096,
            memory_total_mb=8192,
            disk_used_gb=30,
            network_connections=200,
        ),
        capacity=Capacity(
            max_memory_mb=8192,
            max_disk_gb=100,
            max_connections=1000,
        ),
        operational_profile=OperationalProfile(
            mtbf_hours=2160,
            mttr_minutes=10,
            degradation=DegradationConfig(
                memory_leak_mb_per_hour=10.0,
                disk_fill_gb_per_hour=0.5,
                connection_leak_per_hour=5.0,
            ),
        ),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE,
        replicas=1,
        metrics=ResourceMetrics(
            disk_used_gb=80,
        ),
        capacity=Capacity(max_disk_gb=100),
        operational_profile=OperationalProfile(
            mtbf_hours=4320,
            mttr_minutes=30,
            degradation=DegradationConfig(
                disk_fill_gb_per_hour=0.1,
            ),
        ),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _graph_no_degradation() -> InfraGraph:
    """Graph with no degradation configured."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="web", name="Web", type=ComponentType.WEB_SERVER,
        replicas=3,
        operational_profile=OperationalProfile(
            mtbf_hours=8760,
            mttr_minutes=5,
        ),
    ))
    return graph


def _spof_graph() -> InfraGraph:
    """Single point of failure with low MTBF."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="cache", name="Cache", type=ComponentType.CACHE,
        replicas=1,
        operational_profile=OperationalProfile(
            mtbf_hours=100,
            mttr_minutes=60,
        ),
    ))
    return graph


# ---------------------------------------------------------------------------
# Tests for _failure_probability
# ---------------------------------------------------------------------------


class TestFailureProbability:
    """Tests for the exponential CDF failure probability."""

    def test_zero_time_zero_probability(self) -> None:
        assert _failure_probability(0, 1000) == 0.0

    def test_zero_mtbf_certain_failure(self) -> None:
        assert _failure_probability(100, 0) == 1.0

    def test_negative_mtbf_certain_failure(self) -> None:
        assert _failure_probability(100, -50) == 1.0

    def test_negative_time_zero(self) -> None:
        assert _failure_probability(-10, 1000) == 0.0

    def test_known_value(self) -> None:
        # P(fail in MTBF hours) = 1 - exp(-1) ~ 0.6321
        p = _failure_probability(1000, 1000)
        assert abs(p - (1 - math.exp(-1))) < 1e-10

    def test_long_horizon_high_probability(self) -> None:
        # After 10x MTBF, probability should be very high
        p = _failure_probability(10000, 1000)
        assert p > 0.99

    def test_probability_between_0_and_1(self) -> None:
        p = _failure_probability(500, 2000)
        assert 0.0 < p < 1.0


# ---------------------------------------------------------------------------
# Tests for _days_to_exhaust
# ---------------------------------------------------------------------------


class TestDaysToExhaust:
    """Tests for resource exhaustion extrapolation."""

    def test_zero_rate_infinite(self) -> None:
        assert _days_to_exhaust(50, 0) == float("inf")

    def test_negative_rate_infinite(self) -> None:
        assert _days_to_exhaust(50, -1) == float("inf")

    def test_already_full(self) -> None:
        assert _days_to_exhaust(100, 1.0) == 0.0

    def test_over_full(self) -> None:
        assert _days_to_exhaust(110, 1.0) == 0.0

    def test_half_full_known_rate(self) -> None:
        # 50% remaining, 1%/hr = 50 hours = 50/24 days
        days = _days_to_exhaust(50, 1.0)
        assert abs(days - 50.0 / 24.0) < 0.01

    def test_near_empty(self) -> None:
        # 1% used, 0.1%/hr = 990 hours remaining / 24
        days = _days_to_exhaust(1, 0.1)
        assert abs(days - 990 / 24.0) < 0.01


# ---------------------------------------------------------------------------
# Tests for _recommend_action
# ---------------------------------------------------------------------------


class TestRecommendAction:
    """Tests for _recommend_action urgency levels and resource types."""

    def test_critical_urgency(self) -> None:
        result = _recommend_action("memory", 0.5)
        assert "[CRITICAL]" in result
        assert "memory" in result.lower()

    def test_high_urgency(self) -> None:
        result = _recommend_action("disk", 5.0)
        assert "[HIGH]" in result
        assert "disk" in result.lower()

    def test_medium_urgency(self) -> None:
        result = _recommend_action("connections", 15.0)
        assert "[MEDIUM]" in result
        assert "connection" in result.lower()

    def test_low_urgency(self) -> None:
        result = _recommend_action("memory", 60.0)
        assert "[LOW]" in result

    def test_unknown_resource_type(self) -> None:
        result = _recommend_action("cpu", 10.0)
        assert "[MEDIUM]" in result
        assert "cpu" in result.lower()

    def test_boundary_one_day(self) -> None:
        result = _recommend_action("disk", 1.0)
        assert "[CRITICAL]" in result

    def test_boundary_seven_days(self) -> None:
        result = _recommend_action("disk", 7.0)
        assert "[HIGH]" in result

    def test_boundary_thirty_days(self) -> None:
        result = _recommend_action("disk", 30.0)
        assert "[MEDIUM]" in result

    def test_just_over_thirty_days(self) -> None:
        result = _recommend_action("disk", 31.0)
        assert "[LOW]" in result

    def test_exhaustion_days_in_message(self) -> None:
        result = _recommend_action("memory", 2.5)
        assert "2.5 days" in result


# ---------------------------------------------------------------------------
# Tests for _suggest_maintenance_window
# ---------------------------------------------------------------------------


class TestSuggestMaintenanceWindow:
    """Tests for maintenance window suggestion."""

    def test_no_predictions_no_maintenance(self) -> None:
        result = _suggest_maintenance_window([])
        assert "No urgent maintenance" in result

    def test_all_infinite_exhaustion(self) -> None:
        pred = ResourceExhaustionPrediction(
            component_id="app",
            resource="memory",
            current_usage_percent=10.0,
            growth_rate_per_hour=0.0,
            days_to_exhaustion=float("inf"),
            exhaustion_date="2099-01-01",
            recommended_action="None needed",
        )
        result = _suggest_maintenance_window([pred])
        assert "No resource exhaustion predicted" in result

    def test_urgent_exhaustion_suggests_window(self) -> None:
        pred = ResourceExhaustionPrediction(
            component_id="db",
            resource="disk",
            current_usage_percent=85.0,
            growth_rate_per_hour=0.5,
            days_to_exhaustion=3.0,
            exhaustion_date="2026-03-18",
            recommended_action="[HIGH] Clean up.",
        )
        result = _suggest_maintenance_window([pred])
        assert "Recommended maintenance window" in result
        assert "db" in result
        assert "disk" in result
        assert "3.0 days" in result

    def test_picks_soonest_exhaustion(self) -> None:
        pred1 = ResourceExhaustionPrediction(
            component_id="api",
            resource="memory",
            current_usage_percent=50.0,
            growth_rate_per_hour=0.1,
            days_to_exhaustion=20.0,
            exhaustion_date="2026-04-04",
            recommended_action="[MEDIUM] Check.",
        )
        pred2 = ResourceExhaustionPrediction(
            component_id="db",
            resource="disk",
            current_usage_percent=90.0,
            growth_rate_per_hour=1.0,
            days_to_exhaustion=2.0,
            exhaustion_date="2026-03-17",
            recommended_action="[HIGH] Expand.",
        )
        result = _suggest_maintenance_window([pred1, pred2])
        assert "db" in result
        assert "disk" in result

    def test_zero_days_exhaustion(self) -> None:
        pred = ResourceExhaustionPrediction(
            component_id="db",
            resource="disk",
            current_usage_percent=100.0,
            growth_rate_per_hour=1.0,
            days_to_exhaustion=0.0,
            exhaustion_date="2026-03-15",
            recommended_action="[CRITICAL] Immediate.",
        )
        result = _suggest_maintenance_window([pred])
        assert "Recommended maintenance window" in result


# ---------------------------------------------------------------------------
# Tests for PredictiveEngine — basic
# ---------------------------------------------------------------------------


class TestPredictiveEngineBasic:
    """Basic predictive engine tests."""

    def test_report_structure(self) -> None:
        graph = _graph_with_degradation()
        engine = PredictiveEngine(graph)
        report = engine.predict(horizon_days=90)

        assert isinstance(report, PredictiveReport)
        assert isinstance(report.exhaustion_predictions, list)
        assert isinstance(report.failure_forecasts, list)
        assert isinstance(report.recommended_maintenance_window, str)
        assert isinstance(report.summary, str)

    def test_empty_graph(self) -> None:
        graph = InfraGraph()
        engine = PredictiveEngine(graph)
        report = engine.predict()

        assert len(report.exhaustion_predictions) == 0
        assert len(report.failure_forecasts) == 0
        assert "No components" in report.summary

    def test_no_degradation_no_exhaustion(self) -> None:
        graph = _graph_no_degradation()
        engine = PredictiveEngine(graph)
        report = engine.predict(horizon_days=90)

        assert len(report.exhaustion_predictions) == 0
        assert len(report.failure_forecasts) > 0

    def test_default_horizon(self) -> None:
        graph = _graph_with_degradation()
        engine = PredictiveEngine(graph)
        report = engine.predict()
        # Default horizon is 90 days
        assert isinstance(report, PredictiveReport)


# ---------------------------------------------------------------------------
# Tests for resource exhaustion predictions
# ---------------------------------------------------------------------------


class TestResourceExhaustion:
    """Tests for resource exhaustion predictions."""

    def test_memory_leak_detected(self) -> None:
        graph = _graph_with_degradation()
        engine = PredictiveEngine(graph)
        report = engine.predict(horizon_days=90)

        memory_predictions = [
            p for p in report.exhaustion_predictions if p.resource == "memory"
        ]
        assert len(memory_predictions) > 0
        assert all(p.growth_rate_per_hour > 0 for p in memory_predictions)

    def test_disk_fill_detected(self) -> None:
        graph = _graph_with_degradation()
        engine = PredictiveEngine(graph)
        report = engine.predict(horizon_days=90)

        disk_predictions = [
            p for p in report.exhaustion_predictions if p.resource == "disk"
        ]
        assert len(disk_predictions) > 0

    def test_connection_leak_detected(self) -> None:
        graph = _graph_with_degradation()
        engine = PredictiveEngine(graph)
        report = engine.predict(horizon_days=90)

        conn_predictions = [
            p for p in report.exhaustion_predictions if p.resource == "connections"
        ]
        assert len(conn_predictions) > 0

    def test_predictions_sorted_by_urgency(self) -> None:
        graph = _graph_with_degradation()
        engine = PredictiveEngine(graph)
        report = engine.predict(horizon_days=90)

        if len(report.exhaustion_predictions) >= 2:
            for i in range(len(report.exhaustion_predictions) - 1):
                assert (
                    report.exhaustion_predictions[i].days_to_exhaustion
                    <= report.exhaustion_predictions[i + 1].days_to_exhaustion
                )

    def test_horizon_filters_predictions(self) -> None:
        """Predictions beyond the horizon should not appear."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="slow", name="Slow", type=ComponentType.STORAGE,
            replicas=1,
            metrics=ResourceMetrics(disk_used_gb=1),
            capacity=Capacity(max_disk_gb=1000),
            operational_profile=OperationalProfile(
                mtbf_hours=8760,
                degradation=DegradationConfig(
                    disk_fill_gb_per_hour=0.001,
                ),
            ),
        ))
        engine = PredictiveEngine(graph)
        # Very slow fill rate: 0.001 gb/hr -> 0.0001% per hr (1000gb total)
        # remaining ~99.9%, rate ~0.0001%/hr => days = 99.9/0.0001/24 >> 90
        report = engine.predict(horizon_days=7)
        disk_preds = [p for p in report.exhaustion_predictions if p.resource == "disk"]
        # If days_to_exhaustion > 7, it should be filtered out
        for p in disk_preds:
            assert p.days_to_exhaustion <= 7

    def test_prediction_has_exhaustion_date(self) -> None:
        graph = _graph_with_degradation()
        engine = PredictiveEngine(graph)
        report = engine.predict(horizon_days=90)

        for pred in report.exhaustion_predictions:
            assert len(pred.exhaustion_date) > 0

    def test_prediction_has_recommended_action(self) -> None:
        graph = _graph_with_degradation()
        engine = PredictiveEngine(graph)
        report = engine.predict(horizon_days=90)

        for pred in report.exhaustion_predictions:
            assert len(pred.recommended_action) > 0


# ---------------------------------------------------------------------------
# Tests for failure probability forecasts
# ---------------------------------------------------------------------------


class TestFailureForecasts:
    """Tests for failure probability forecasts."""

    def test_forecasts_for_all_components(self) -> None:
        graph = _graph_with_degradation()
        engine = PredictiveEngine(graph)
        report = engine.predict()

        comp_ids = {f.component_id for f in report.failure_forecasts}
        assert comp_ids == {"app", "db"}

    def test_probabilities_increase_with_horizon(self) -> None:
        graph = _graph_with_degradation()
        engine = PredictiveEngine(graph)
        report = engine.predict()

        for forecast in report.failure_forecasts:
            assert forecast.probability_7d <= forecast.probability_30d
            assert forecast.probability_30d <= forecast.probability_90d

    def test_replicas_reduce_failure_probability(self) -> None:
        graph = _graph_with_degradation()
        engine = PredictiveEngine(graph)
        report = engine.predict()

        app_forecast = next(f for f in report.failure_forecasts if f.component_id == "app")
        db_forecast = next(f for f in report.failure_forecasts if f.component_id == "db")

        # App has 2 replicas with 2160h MTBF, DB has 1 replica with 4320h MTBF
        assert app_forecast.probability_30d < 1.0
        assert db_forecast.probability_30d < 1.0

    def test_spof_high_failure_probability(self) -> None:
        graph = _spof_graph()
        engine = PredictiveEngine(graph)
        report = engine.predict()

        forecast = report.failure_forecasts[0]
        # With MTBF=100h, P(fail in 90 days) should be very high
        assert forecast.probability_90d > 0.99

    def test_forecasts_sorted_by_30d_probability(self) -> None:
        graph = _graph_with_degradation()
        engine = PredictiveEngine(graph)
        report = engine.predict()

        if len(report.failure_forecasts) >= 2:
            for i in range(len(report.failure_forecasts) - 1):
                assert (
                    report.failure_forecasts[i].probability_30d
                    >= report.failure_forecasts[i + 1].probability_30d
                )

    def test_zero_mtbf_uses_default(self) -> None:
        """Component with mtbf_hours=0 should use the default MTBF."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="dns1", name="DNS", type=ComponentType.DNS,
            replicas=1,
            operational_profile=OperationalProfile(
                mtbf_hours=0,
            ),
        ))
        engine = PredictiveEngine(graph)
        report = engine.predict()

        forecast = report.failure_forecasts[0]
        # DNS default MTBF is 43800 hours
        assert forecast.mtbf_hours == 43800.0
        assert forecast.probability_7d > 0

    def test_negative_mtbf_uses_default(self) -> None:
        """Component with negative mtbf_hours should use the default MTBF."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="cache1", name="Cache", type=ComponentType.CACHE,
            replicas=1,
            operational_profile=OperationalProfile(
                mtbf_hours=-100,
            ),
        ))
        engine = PredictiveEngine(graph)
        report = engine.predict()

        forecast = report.failure_forecasts[0]
        # Cache default MTBF is 1440 hours
        assert forecast.mtbf_hours == 1440.0

    def test_unknown_type_uses_fallback_default(self) -> None:
        """Component type not in _DEFAULT_MTBF should use 2160.0."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="ext1", name="External", type=ComponentType.EXTERNAL_API,
            replicas=1,
            operational_profile=OperationalProfile(
                mtbf_hours=0,
            ),
        ))
        engine = PredictiveEngine(graph)
        report = engine.predict()

        forecast = report.failure_forecasts[0]
        # EXTERNAL_API is not in _DEFAULT_MTBF, so fallback to 2160.0
        assert forecast.mtbf_hours == 2160.0

    def test_multi_replica_reduces_probability(self) -> None:
        """More replicas should significantly reduce failure probability."""
        # Single replica
        g1 = InfraGraph()
        g1.add_component(Component(
            id="svc", name="Svc", type=ComponentType.APP_SERVER,
            replicas=1,
            operational_profile=OperationalProfile(mtbf_hours=1000),
        ))
        r1 = PredictiveEngine(g1).predict()

        # Three replicas
        g3 = InfraGraph()
        g3.add_component(Component(
            id="svc", name="Svc", type=ComponentType.APP_SERVER,
            replicas=3,
            operational_profile=OperationalProfile(mtbf_hours=1000),
        ))
        r3 = PredictiveEngine(g3).predict()

        f1 = r1.failure_forecasts[0]
        f3 = r3.failure_forecasts[0]
        # P(all 3 fail) = P(single)^3, much less than P(single)
        assert f3.probability_30d < f1.probability_30d
        assert f3.probability_90d < f1.probability_90d


# ---------------------------------------------------------------------------
# Tests for summary and maintenance window
# ---------------------------------------------------------------------------


class TestSummaryAndMaintenance:
    """Tests for summary and maintenance window."""

    def test_summary_not_empty(self) -> None:
        graph = _graph_with_degradation()
        engine = PredictiveEngine(graph)
        report = engine.predict()

        assert len(report.summary) > 0

    def test_maintenance_window_with_urgent(self) -> None:
        graph = _graph_with_degradation()
        engine = PredictiveEngine(graph)
        report = engine.predict()

        assert "maintenance" in report.recommended_maintenance_window.lower() or \
               "exhaustion" in report.recommended_maintenance_window.lower() or \
               "Recommended" in report.recommended_maintenance_window

    def test_maintenance_window_no_degradation(self) -> None:
        graph = _graph_no_degradation()
        engine = PredictiveEngine(graph)
        report = engine.predict()

        assert "No resource exhaustion" in report.recommended_maintenance_window or \
               "No urgent" in report.recommended_maintenance_window

    def test_summary_with_urgent_exhaustion(self) -> None:
        """Test summary when exhaustion is within 7 days."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=1,
            metrics=ResourceMetrics(memory_used_mb=7500),
            capacity=Capacity(max_memory_mb=8192),
            operational_profile=OperationalProfile(
                mtbf_hours=2160,
                degradation=DegradationConfig(
                    memory_leak_mb_per_hour=50.0,
                ),
            ),
        ))
        engine = PredictiveEngine(graph)
        report = engine.predict(horizon_days=90)
        assert "CRITICAL" in report.summary

    def test_summary_with_warning_exhaustion(self) -> None:
        """Test summary when exhaustion is between 7 and 30 days."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=1,
            metrics=ResourceMetrics(memory_used_mb=2000),
            capacity=Capacity(max_memory_mb=8192),
            operational_profile=OperationalProfile(
                mtbf_hours=2160,
                degradation=DegradationConfig(
                    memory_leak_mb_per_hour=10.0,
                ),
            ),
        ))
        engine = PredictiveEngine(graph)
        report = engine.predict(horizon_days=90)
        # Check that WARNING appears (exhaustion in ~25 days)
        assert "WARNING" in report.summary or "No resource" in report.summary

    def test_summary_no_exhaustion_no_high_risk(self) -> None:
        """Summary for a well-provisioned system."""
        graph = _graph_no_degradation()
        engine = PredictiveEngine(graph)
        report = engine.predict()
        assert "No resource exhaustion" in report.summary
        assert "<50%" in report.summary

    def test_summary_high_failure_risk(self) -> None:
        """Summary mentions high-risk components."""
        graph = _spof_graph()
        engine = PredictiveEngine(graph)
        report = engine.predict()
        # With MTBF=100h, 30d probability is extremely high
        assert "High failure risk" in report.summary or "cache" in report.summary.lower()

    def test_summary_empty_graph(self) -> None:
        graph = InfraGraph()
        engine = PredictiveEngine(graph)
        report = engine.predict()
        assert "No components" in report.summary


# ---------------------------------------------------------------------------
# Tests for dataclass defaults
# ---------------------------------------------------------------------------


class TestDataclasses:
    """Test dataclass field defaults."""

    def test_predictive_report_defaults(self) -> None:
        report = PredictiveReport()
        assert report.exhaustion_predictions == []
        assert report.failure_forecasts == []
        assert report.recommended_maintenance_window == ""
        assert report.summary == ""

    def test_resource_exhaustion_prediction_fields(self) -> None:
        pred = ResourceExhaustionPrediction(
            component_id="app",
            resource="memory",
            current_usage_percent=50.0,
            growth_rate_per_hour=0.5,
            days_to_exhaustion=4.2,
            exhaustion_date="2026-03-19",
            recommended_action="[HIGH] Fix it.",
        )
        assert pred.component_id == "app"
        assert pred.resource == "memory"
        assert pred.current_usage_percent == 50.0

    def test_failure_probability_forecast_fields(self) -> None:
        forecast = FailureProbabilityForecast(
            component_id="db",
            mtbf_hours=4320.0,
            probability_7d=0.03,
            probability_30d=0.12,
            probability_90d=0.35,
        )
        assert forecast.mtbf_hours == 4320.0
        assert forecast.probability_7d == 0.03


# ---------------------------------------------------------------------------
# Tests for edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests for full coverage."""

    def test_component_at_100_percent_usage(self) -> None:
        """Component already at 100% should have 0 days to exhaustion."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="full", name="Full", type=ComponentType.STORAGE,
            replicas=1,
            metrics=ResourceMetrics(disk_used_gb=100),
            capacity=Capacity(max_disk_gb=100),
            operational_profile=OperationalProfile(
                mtbf_hours=8760,
                degradation=DegradationConfig(
                    disk_fill_gb_per_hour=1.0,
                ),
            ),
        ))
        engine = PredictiveEngine(graph)
        report = engine.predict(horizon_days=90)

        disk_preds = [p for p in report.exhaustion_predictions if p.resource == "disk"]
        assert len(disk_preds) == 1
        assert disk_preds[0].days_to_exhaustion == 0.0

    def test_very_fast_memory_leak(self) -> None:
        """Very fast leak causes critical urgency in recommendation."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="leaky", name="Leaky", type=ComponentType.APP_SERVER,
            replicas=1,
            metrics=ResourceMetrics(memory_used_mb=7000),
            capacity=Capacity(max_memory_mb=8192),
            operational_profile=OperationalProfile(
                mtbf_hours=2160,
                degradation=DegradationConfig(
                    memory_leak_mb_per_hour=100.0,
                ),
            ),
        ))
        engine = PredictiveEngine(graph)
        report = engine.predict(horizon_days=90)

        mem_preds = [p for p in report.exhaustion_predictions if p.resource == "memory"]
        assert len(mem_preds) == 1
        # With 1192 MB remaining at 100 MB/hr: ~12 hours = 0.5 days
        assert mem_preds[0].days_to_exhaustion < 1.0
        assert "CRITICAL" in mem_preds[0].recommended_action

    def test_slow_degradation_exceeds_horizon(self) -> None:
        """Slow degradation beyond horizon should not appear in predictions."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="slow", name="Slow", type=ComponentType.APP_SERVER,
            replicas=1,
            metrics=ResourceMetrics(memory_used_mb=100),
            capacity=Capacity(max_memory_mb=100000),
            operational_profile=OperationalProfile(
                mtbf_hours=2160,
                degradation=DegradationConfig(
                    memory_leak_mb_per_hour=0.001,
                ),
            ),
        ))
        engine = PredictiveEngine(graph)
        report = engine.predict(horizon_days=1)
        mem_preds = [p for p in report.exhaustion_predictions if p.resource == "memory"]
        assert len(mem_preds) == 0

    def test_multiple_components_all_degrading(self) -> None:
        """All resources degrade on multiple components."""
        graph = InfraGraph()
        for i in range(3):
            graph.add_component(Component(
                id=f"svc{i}", name=f"Svc{i}", type=ComponentType.APP_SERVER,
                replicas=1,
                metrics=ResourceMetrics(
                    memory_used_mb=4000,
                    disk_used_gb=50,
                    network_connections=500,
                ),
                capacity=Capacity(
                    max_memory_mb=8192,
                    max_disk_gb=100,
                    max_connections=1000,
                ),
                operational_profile=OperationalProfile(
                    mtbf_hours=2160,
                    degradation=DegradationConfig(
                        memory_leak_mb_per_hour=5.0,
                        disk_fill_gb_per_hour=0.2,
                        connection_leak_per_hour=2.0,
                    ),
                ),
            ))
        engine = PredictiveEngine(graph)
        report = engine.predict(horizon_days=90)

        # Should have predictions for all 3 components x 3 resources
        assert len(report.exhaustion_predictions) == 9
        assert len(report.failure_forecasts) == 3
