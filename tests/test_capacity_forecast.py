"""Tests for the capacity forecasting engine."""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    HealthStatus,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.capacity_forecast import (
    CapacityDataPoint,
    CapacityForecast,
    CapacityForecaster,
    ForecastHorizon,
    ForecastReport,
    GrowthModel,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    cpu: float = 0.0,
    memory: float = 0.0,
    disk: float = 0.0,
    health: HealthStatus = HealthStatus.HEALTHY,
) -> Component:
    return Component(
        id=cid,
        name=name,
        type=ctype,
        replicas=replicas,
        metrics=ResourceMetrics(
            cpu_percent=cpu,
            memory_percent=memory,
            disk_percent=disk,
        ),
        health=health,
    )


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


# ---------------------------------------------------------------------------
# Enum value tests
# ---------------------------------------------------------------------------


class TestForecastHorizonEnum:
    def test_days_7(self):
        assert ForecastHorizon.DAYS_7.value == 7

    def test_days_30(self):
        assert ForecastHorizon.DAYS_30.value == 30

    def test_days_90(self):
        assert ForecastHorizon.DAYS_90.value == 90

    def test_days_180(self):
        assert ForecastHorizon.DAYS_180.value == 180

    def test_days_365(self):
        assert ForecastHorizon.DAYS_365.value == 365

    def test_all_members(self):
        members = list(ForecastHorizon)
        assert len(members) == 5


class TestGrowthModelEnum:
    def test_linear(self):
        assert GrowthModel.LINEAR.value == "linear"

    def test_exponential(self):
        assert GrowthModel.EXPONENTIAL.value == "exponential"

    def test_logarithmic(self):
        assert GrowthModel.LOGARITHMIC.value == "logarithmic"

    def test_seasonal(self):
        assert GrowthModel.SEASONAL.value == "seasonal"

    def test_all_members(self):
        members = list(GrowthModel)
        assert len(members) == 4


# ---------------------------------------------------------------------------
# Dataclass construction tests
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_capacity_data_point(self):
        now = datetime.now()
        dp = CapacityDataPoint(timestamp=now, utilization=55.0, replicas=3)
        assert dp.timestamp == now
        assert dp.utilization == 55.0
        assert dp.replicas == 3

    def test_capacity_forecast_fields(self):
        fc = CapacityForecast(
            component_id="web",
            component_name="Web",
            current_utilization=50.0,
            predicted_utilization=70.0,
            days_until_capacity=60.0,
            growth_model=GrowthModel.LINEAR,
            growth_rate=0.5,
            recommended_action="scale",
            confidence=0.85,
        )
        assert fc.component_id == "web"
        assert fc.confidence == 0.85

    def test_forecast_report_fields(self):
        report = ForecastReport(
            forecasts=[],
            components_at_risk=["db"],
            total_predicted_cost_increase=200.0,
            planning_horizon_days=30,
            recommendations=["scale db"],
        )
        assert report.components_at_risk == ["db"]
        assert report.total_predicted_cost_increase == 200.0


# ---------------------------------------------------------------------------
# Forecast with NO data points (uses current utilization only)
# ---------------------------------------------------------------------------


class TestForecastNoData:
    def test_single_component_low_util(self):
        """Low utilization and no history -> no action needed."""
        g = _graph(_comp("app", "App", cpu=10.0))
        fc = CapacityForecaster().forecast_component(
            g, "app", ForecastHorizon.DAYS_30
        )
        assert fc.component_id == "app"
        assert fc.current_utilization == 10.0
        assert fc.recommended_action == "No action needed"

    def test_confidence_low_without_data(self):
        """Confidence should be low when forecasting without history."""
        g = _graph(_comp("app", "App", cpu=40.0))
        fc = CapacityForecaster().forecast_component(
            g, "app", ForecastHorizon.DAYS_30
        )
        assert fc.confidence <= 0.5

    def test_zero_utilization_no_growth(self):
        """Zero utilization -> no growth, infinite days until capacity."""
        g = _graph(_comp("idle", "Idle"))
        fc = CapacityForecaster().forecast_component(
            g, "idle", ForecastHorizon.DAYS_30
        )
        assert fc.current_utilization == 0.0
        assert fc.growth_rate == 0.0
        assert math.isinf(fc.days_until_capacity)

    def test_report_empty_graph(self):
        """Empty graph produces an empty report."""
        g = InfraGraph()
        report = CapacityForecaster().forecast(g)
        assert len(report.forecasts) == 0
        assert report.components_at_risk == []
        assert report.total_predicted_cost_increase == 0.0
        assert report.planning_horizon_days == 30


# ---------------------------------------------------------------------------
# Forecast WITH data points showing growth
# ---------------------------------------------------------------------------


class TestForecastWithData:
    @staticmethod
    def _add_linear_growth(
        forecaster: CapacityForecaster,
        comp_id: str,
        start_util: float = 30.0,
        daily_increase: float = 1.0,
        num_days: int = 10,
    ) -> None:
        """Inject synthetic data points with a linear trend."""
        base = datetime(2025, 1, 1)
        for day in range(num_days):
            forecaster.add_data_point(
                comp_id,
                CapacityDataPoint(
                    timestamp=base + timedelta(days=day),
                    utilization=start_util + daily_increase * day,
                    replicas=2,
                ),
            )

    def test_linear_growth_predicted(self):
        """Data showing steady growth -> predicted utilization rises."""
        g = _graph(_comp("app", "App", cpu=40.0))
        f = CapacityForecaster()
        self._add_linear_growth(f, "app", start_util=30.0, daily_increase=1.0)
        fc = f.forecast_component(g, "app", ForecastHorizon.DAYS_30)
        assert fc.predicted_utilization > fc.current_utilization
        assert fc.growth_rate > 0

    def test_high_confidence_with_clean_data(self):
        """Perfectly linear data -> confidence near 1.0."""
        g = _graph(_comp("app", "App", cpu=40.0))
        f = CapacityForecaster()
        self._add_linear_growth(f, "app", start_util=20.0, daily_increase=2.0, num_days=20)
        fc = f.forecast_component(g, "app", ForecastHorizon.DAYS_30)
        assert fc.confidence >= 0.9

    def test_growth_model_is_linear(self):
        """With data points the engine selects LINEAR growth model."""
        g = _graph(_comp("web", "Web", cpu=30.0))
        f = CapacityForecaster()
        self._add_linear_growth(f, "web")
        fc = f.forecast_component(g, "web", ForecastHorizon.DAYS_30)
        assert fc.growth_model == GrowthModel.LINEAR

    def test_negative_growth_infinite_days(self):
        """Shrinking utilization -> infinite days until capacity."""
        g = _graph(_comp("shrink", "Shrink", cpu=50.0))
        f = CapacityForecaster()
        self._add_linear_growth(f, "shrink", start_util=80.0, daily_increase=-2.0)
        fc = f.forecast_component(g, "shrink", ForecastHorizon.DAYS_90)
        assert math.isinf(fc.days_until_capacity)


# ---------------------------------------------------------------------------
# Days until capacity
# ---------------------------------------------------------------------------


class TestDaysUntilCapacity:
    def test_already_at_100_returns_zero(self):
        g = _graph(_comp("full", "Full", cpu=100.0))
        fc = CapacityForecaster().forecast_component(
            g, "full", ForecastHorizon.DAYS_30
        )
        assert fc.days_until_capacity == 0.0

    def test_exceeds_100_returns_zero(self):
        """Utilization above 100% should still report 0 days."""
        # cpu_percent can technically exceed 100 on multi-core.
        comp = _comp("over", "Over", cpu=120.0)
        g = _graph(comp)
        fc = CapacityForecaster().forecast_component(
            g, "over", ForecastHorizon.DAYS_30
        )
        assert fc.days_until_capacity == 0.0

    def test_zero_growth_infinite(self):
        g = _graph(_comp("static", "Static"))
        fc = CapacityForecaster().forecast_component(
            g, "static", ForecastHorizon.DAYS_30
        )
        assert math.isinf(fc.days_until_capacity)

    def test_positive_growth_finite(self):
        g = _graph(_comp("growing", "Growing", cpu=50.0))
        f = CapacityForecaster()
        TestForecastWithData._add_linear_growth(
            f, "growing", start_util=40.0, daily_increase=1.0, num_days=15
        )
        fc = f.forecast_component(g, "growing", ForecastHorizon.DAYS_90)
        assert 0 < fc.days_until_capacity < float("inf")


# ---------------------------------------------------------------------------
# Components at risk
# ---------------------------------------------------------------------------


class TestComponentsAtRisk:
    def test_high_util_flagged(self):
        """Components with high utilization appear in at-risk list."""
        g = _graph(
            _comp("hot", "Hot", cpu=90.0),
            _comp("cool", "Cool", cpu=10.0),
        )
        report = CapacityForecaster().forecast(g)
        assert "hot" in report.components_at_risk
        assert "cool" not in report.components_at_risk

    def test_all_low_no_risk(self):
        """All components below threshold -> empty at-risk list."""
        g = _graph(
            _comp("a", "A", cpu=10.0),
            _comp("b", "B", cpu=20.0),
        )
        report = CapacityForecaster().forecast(g)
        assert report.components_at_risk == []

    def test_predicted_high_util_flagged(self):
        """A component that is low now but predicted high should be at risk."""
        g = _graph(_comp("rising", "Rising", cpu=50.0))
        f = CapacityForecaster()
        TestForecastWithData._add_linear_growth(
            f, "rising", start_util=40.0, daily_increase=2.0, num_days=20
        )
        report = f.forecast(g, ForecastHorizon.DAYS_30)
        # predicted_util = 50 + 2*30 = ~110 which is >> 75
        assert "rising" in report.components_at_risk


# ---------------------------------------------------------------------------
# Different horizons
# ---------------------------------------------------------------------------


class TestHorizons:
    def test_longer_horizon_higher_predicted(self):
        """Longer horizon should yield higher predicted utilization when growing."""
        g = _graph(_comp("svc", "Svc", cpu=40.0))
        f = CapacityForecaster()
        TestForecastWithData._add_linear_growth(
            f, "svc", start_util=30.0, daily_increase=0.5
        )
        fc7 = f.forecast_component(g, "svc", ForecastHorizon.DAYS_7)
        fc365 = f.forecast_component(g, "svc", ForecastHorizon.DAYS_365)
        assert fc365.predicted_utilization > fc7.predicted_utilization

    def test_default_horizon_is_30(self):
        """Calling forecast() without horizon defaults to 30 days."""
        g = _graph(_comp("x", "X", cpu=20.0))
        report = CapacityForecaster().forecast(g)
        assert report.planning_horizon_days == 30


# ---------------------------------------------------------------------------
# Recommended actions
# ---------------------------------------------------------------------------


class TestRecommendedAction:
    def test_critical_when_at_capacity(self):
        g = _graph(_comp("full", "Full", cpu=100.0))
        fc = CapacityForecaster().forecast_component(
            g, "full", ForecastHorizon.DAYS_30
        )
        assert "CRITICAL" in fc.recommended_action

    def test_no_action_low_util(self):
        g = _graph(_comp("idle", "Idle", cpu=5.0))
        fc = CapacityForecaster().forecast_component(
            g, "idle", ForecastHorizon.DAYS_30
        )
        assert fc.recommended_action == "No action needed"


# ---------------------------------------------------------------------------
# Cost increase estimation
# ---------------------------------------------------------------------------


class TestCostEstimate:
    def test_no_cost_increase_when_low(self):
        g = _graph(_comp("ok", "OK", cpu=20.0))
        report = CapacityForecaster().forecast(g)
        assert report.total_predicted_cost_increase == 0.0

    def test_positive_cost_when_scaling_needed(self):
        g = _graph(_comp("hot", "Hot", cpu=95.0))
        report = CapacityForecaster().forecast(g, ForecastHorizon.DAYS_90)
        assert report.total_predicted_cost_increase > 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_unknown_component_raises(self):
        g = InfraGraph()
        with pytest.raises(KeyError):
            CapacityForecaster().forecast_component(g, "nope", ForecastHorizon.DAYS_30)

    def test_multiple_components_forecast(self):
        g = _graph(
            _comp("a", "A", cpu=30.0),
            _comp("b", "B", cpu=60.0),
            _comp("c", "C", cpu=80.0),
        )
        report = CapacityForecaster().forecast(g)
        assert len(report.forecasts) == 3

    def test_add_data_point_sorts_by_time(self):
        f = CapacityForecaster()
        t1 = datetime(2025, 1, 10)
        t2 = datetime(2025, 1, 1)
        t3 = datetime(2025, 1, 5)
        f.add_data_point("x", CapacityDataPoint(timestamp=t1, utilization=50, replicas=1))
        f.add_data_point("x", CapacityDataPoint(timestamp=t2, utilization=30, replicas=1))
        f.add_data_point("x", CapacityDataPoint(timestamp=t3, utilization=40, replicas=1))
        history = f._history["x"]
        assert history[0].timestamp == t2
        assert history[1].timestamp == t3
        assert history[2].timestamp == t1

    def test_single_data_point_uses_default(self):
        """One data point is not enough for regression -> fallback."""
        g = _graph(_comp("solo", "Solo", cpu=50.0))
        f = CapacityForecaster()
        f.add_data_point(
            "solo",
            CapacityDataPoint(
                timestamp=datetime(2025, 1, 1), utilization=45.0, replicas=1
            ),
        )
        fc = f.forecast_component(g, "solo", ForecastHorizon.DAYS_30)
        # Should use the default fallback, confidence low
        assert fc.confidence <= 0.5

    def test_confidence_clamped_between_0_and_1(self):
        g = _graph(_comp("c", "C", cpu=40.0))
        fc = CapacityForecaster().forecast_component(
            g, "c", ForecastHorizon.DAYS_30
        )
        assert 0.0 <= fc.confidence <= 1.0

    def test_forecast_report_recommendations_populated(self):
        """Components needing action should produce recommendations."""
        g = _graph(_comp("danger", "Danger", cpu=100.0))
        report = CapacityForecaster().forecast(g)
        assert len(report.recommendations) > 0

    def test_all_horizons_produce_valid_report(self):
        g = _graph(_comp("svc", "Svc", cpu=50.0))
        f = CapacityForecaster()
        for horizon in ForecastHorizon:
            report = f.forecast(g, horizon)
            assert report.planning_horizon_days == horizon.value
            assert len(report.forecasts) == 1


# ---------------------------------------------------------------------------
# Coverage gaps — lines 212, 230, 241, 271
# ---------------------------------------------------------------------------


class TestLinearRegressionEdgeCases:
    """Test _linear_regression edge cases directly."""

    def test_empty_data_returns_zero(self):
        """Empty data list -> (0.0, 0.0). [line 212]"""
        slope, confidence = CapacityForecaster._linear_regression([])
        assert slope == 0.0
        assert confidence == 0.0

    def test_single_data_point_returns_zero(self):
        """Single data point -> (0.0, 0.0). [line 212]"""
        dp = CapacityDataPoint(
            timestamp=datetime(2025, 1, 1), utilization=50.0, replicas=1,
        )
        slope, confidence = CapacityForecaster._linear_regression([dp])
        assert slope == 0.0
        assert confidence == 0.0

    def test_same_timestamps_denom_zero(self):
        """All data points at the same timestamp -> denom=0, returns (0, 0). [line 230]"""
        same_time = datetime(2025, 1, 1)
        dps = [
            CapacityDataPoint(timestamp=same_time, utilization=30.0, replicas=1),
            CapacityDataPoint(timestamp=same_time, utilization=60.0, replicas=1),
        ]
        slope, confidence = CapacityForecaster._linear_regression(dps)
        assert slope == 0.0
        assert confidence == 0.0

    def test_constant_utilization_r_squared_one(self):
        """Constant utilization (ss_tot=0) -> r_squared=1.0. [line 241]"""
        base = datetime(2025, 1, 1)
        dps = [
            CapacityDataPoint(
                timestamp=base + timedelta(days=i),
                utilization=50.0,  # constant
                replicas=1,
            )
            for i in range(5)
        ]
        slope, confidence = CapacityForecaster._linear_regression(dps)
        assert slope == 0.0
        assert confidence == 1.0  # r_squared = 1.0 for constant data


class TestRecommendActionFallback:
    """Test the final 'No action needed' return. [line 271]"""

    def test_low_growth_no_risk(self):
        """Low current util, low predicted util, distant capacity ->
        'No action needed'. [line 271]"""
        action = CapacityForecaster._recommend_action(
            current_util=20.0,
            predicted_util=25.0,
            days_until_cap=365.0,
            horizon_days=30,
        )
        assert action == "No action needed"

    def test_well_within_capacity(self):
        """Predicted utilization well below 75% threshold."""
        action = CapacityForecaster._recommend_action(
            current_util=10.0,
            predicted_util=30.0,
            days_until_cap=float("inf"),
            horizon_days=30,
        )
        assert action == "No action needed"

    def test_urgent_when_days_until_cap_within_7(self):
        """days_until_cap <= 7 but not yet at capacity ->
        URGENT recommendation. [line 271]"""
        action = CapacityForecaster._recommend_action(
            current_util=80.0,
            predicted_util=95.0,
            days_until_cap=5.0,
            horizon_days=30,
        )
        assert "URGENT" in action
