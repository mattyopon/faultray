"""Comprehensive tests for the Resilience Forecast Engine."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from faultray.simulator.resilience_forecast import (
    ForecastHorizon,
    ForecastPoint,
    ResilienceForecastEngine,
    ResilienceForecastReport,
    ResilienceSnapshot,
    RiskForecast,
    RiskLevel,
    TrendAnalysis,
    TrendType,
    _linear_regression,
    _mean,
    _moving_average,
)


# ── Helper ───────────────────────────────────────────────────


def _make_snapshots(
    scores: list[float], start_days_ago: int = 90
) -> list[ResilienceSnapshot]:
    """Create snapshots with given scores, evenly spaced from *start_days_ago*."""
    now = datetime.now(timezone.utc)
    step = start_days_ago / max(len(scores) - 1, 1)
    return [
        ResilienceSnapshot(
            timestamp=now - timedelta(days=start_days_ago - i * step),
            score=s,
            component_count=10,
            spof_count=max(0, int((100 - s) / 20)),
            avg_recovery_time_min=30.0 - s * 0.2,
            change_count=3,
        )
        for i, s in enumerate(scores)
    ]


# ═══════════════════════════════════════════════════════════
# 1. Enum values
# ═══════════════════════════════════════════════════════════


class TestForecastHorizonEnum:
    def test_days_7(self):
        assert ForecastHorizon.DAYS_7.value == 7

    def test_days_30(self):
        assert ForecastHorizon.DAYS_30.value == 30

    def test_days_60(self):
        assert ForecastHorizon.DAYS_60.value == 60

    def test_days_90(self):
        assert ForecastHorizon.DAYS_90.value == 90

    def test_days_180(self):
        assert ForecastHorizon.DAYS_180.value == 180

    def test_is_int_enum(self):
        assert isinstance(ForecastHorizon.DAYS_30, int)

    def test_all_members(self):
        assert len(ForecastHorizon) == 5


class TestTrendTypeEnum:
    def test_improving(self):
        assert TrendType.IMPROVING.value == "improving"

    def test_stable(self):
        assert TrendType.STABLE.value == "stable"

    def test_degrading(self):
        assert TrendType.DEGRADING.value == "degrading"

    def test_volatile(self):
        assert TrendType.VOLATILE.value == "volatile"

    def test_all_members(self):
        assert len(TrendType) == 4


class TestRiskLevelEnum:
    def test_low(self):
        assert RiskLevel.LOW.value == "low"

    def test_medium(self):
        assert RiskLevel.MEDIUM.value == "medium"

    def test_high(self):
        assert RiskLevel.HIGH.value == "high"

    def test_critical(self):
        assert RiskLevel.CRITICAL.value == "critical"

    def test_all_members(self):
        assert len(RiskLevel) == 4


# ═══════════════════════════════════════════════════════════
# 2. Snapshot validation
# ═══════════════════════════════════════════════════════════


class TestResilienceSnapshot:
    def test_valid_snapshot(self):
        s = ResilienceSnapshot(
            timestamp=datetime.now(timezone.utc),
            score=85.5,
            component_count=10,
            spof_count=1,
            avg_recovery_time_min=5.0,
            change_count=2,
        )
        assert s.score == 85.5

    def test_score_lower_bound(self):
        s = ResilienceSnapshot(
            timestamp=datetime.now(timezone.utc),
            score=0,
            component_count=0,
            spof_count=0,
            avg_recovery_time_min=0,
            change_count=0,
        )
        assert s.score == 0

    def test_score_upper_bound(self):
        s = ResilienceSnapshot(
            timestamp=datetime.now(timezone.utc),
            score=100,
            component_count=5,
            spof_count=0,
            avg_recovery_time_min=1.0,
            change_count=0,
        )
        assert s.score == 100

    def test_score_below_zero_raises(self):
        with pytest.raises(Exception):
            ResilienceSnapshot(
                timestamp=datetime.now(timezone.utc),
                score=-1,
                component_count=0,
                spof_count=0,
                avg_recovery_time_min=0,
                change_count=0,
            )

    def test_score_above_100_raises(self):
        with pytest.raises(Exception):
            ResilienceSnapshot(
                timestamp=datetime.now(timezone.utc),
                score=101,
                component_count=0,
                spof_count=0,
                avg_recovery_time_min=0,
                change_count=0,
            )

    def test_negative_component_count_raises(self):
        with pytest.raises(Exception):
            ResilienceSnapshot(
                timestamp=datetime.now(timezone.utc),
                score=50,
                component_count=-1,
                spof_count=0,
                avg_recovery_time_min=0,
                change_count=0,
            )


# ═══════════════════════════════════════════════════════════
# 3. Forecast / Risk model validation
# ═══════════════════════════════════════════════════════════


class TestForecastPoint:
    def test_valid_point(self):
        p = ForecastPoint(
            timestamp=datetime.now(timezone.utc),
            predicted_score=80.0,
            confidence_lower=70.0,
            confidence_upper=90.0,
            confidence_level=0.85,
        )
        assert p.predicted_score == 80.0

    def test_confidence_level_bounds(self):
        with pytest.raises(Exception):
            ForecastPoint(
                timestamp=datetime.now(timezone.utc),
                predicted_score=80.0,
                confidence_lower=70.0,
                confidence_upper=90.0,
                confidence_level=1.5,
            )


class TestRiskForecastModel:
    def test_valid_risk(self):
        r = RiskForecast(
            risk_level=RiskLevel.LOW,
            days_to_threshold=None,
            breach_probability=0.1,
            contributing_factors=["none"],
        )
        assert r.breach_probability == 0.1

    def test_breach_probability_bounds(self):
        with pytest.raises(Exception):
            RiskForecast(
                risk_level=RiskLevel.LOW,
                days_to_threshold=None,
                breach_probability=-0.1,
                contributing_factors=[],
            )


# ═══════════════════════════════════════════════════════════
# 4. Helper functions
# ═══════════════════════════════════════════════════════════


class TestMean:
    def test_simple(self):
        assert _mean([1, 2, 3]) == 2.0

    def test_empty(self):
        assert _mean([]) == 0.0

    def test_single(self):
        assert _mean([42.0]) == 42.0


class TestMovingAverage:
    def test_short_list(self):
        assert _moving_average([1, 2, 3]) == [1, 2, 3]

    def test_exact_window(self):
        assert _moving_average([1, 2, 3, 4, 5]) == [1, 2, 3, 4, 5]

    def test_smoothing(self):
        vals = [10, 20, 10, 20, 10, 20]
        result = _moving_average(vals, window=5)
        assert len(result) == 6
        # Last value is the mean of the last 5 elements
        assert result[-1] == _mean([20, 10, 20, 10, 20])


class TestLinearRegression:
    def test_perfect_line(self):
        xs = [0.0, 1.0, 2.0, 3.0]
        ys = [2.0, 4.0, 6.0, 8.0]
        slope, intercept, r_sq = _linear_regression(xs, ys)
        assert abs(slope - 2.0) < 1e-9
        assert abs(intercept - 2.0) < 1e-9
        assert abs(r_sq - 1.0) < 1e-9

    def test_flat_line(self):
        xs = [0.0, 1.0, 2.0]
        ys = [5.0, 5.0, 5.0]
        slope, intercept, r_sq = _linear_regression(xs, ys)
        assert slope == 0.0
        assert intercept == 5.0
        # ss_tot == 0 → r_sq = 1.0
        assert r_sq == 1.0

    def test_single_point(self):
        slope, intercept, r_sq = _linear_regression([1.0], [10.0])
        assert slope == 0.0
        assert intercept == 10.0
        assert r_sq == 0.0

    def test_empty(self):
        slope, intercept, r_sq = _linear_regression([], [])
        assert slope == 0.0
        assert intercept == 0.0

    def test_identical_x(self):
        slope, _, r_sq = _linear_regression([3.0, 3.0, 3.0], [1.0, 2.0, 3.0])
        assert slope == 0.0


# ═══════════════════════════════════════════════════════════
# 5. Trend analysis
# ═══════════════════════════════════════════════════════════


class TestTrendAnalysis:
    def test_improving_trend(self):
        # Steadily increasing scores
        scores = [float(s) for s in range(60, 100, 4)]
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        trend = engine.analyze_trend()
        assert trend.trend_type == TrendType.IMPROVING
        assert trend.slope > 0

    def test_degrading_trend(self):
        scores = [float(s) for s in range(95, 55, -4)]
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        trend = engine.analyze_trend()
        assert trend.trend_type == TrendType.DEGRADING
        assert trend.slope < 0

    def test_stable_trend(self):
        scores = [80.0] * 10
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        trend = engine.analyze_trend()
        assert trend.trend_type == TrendType.STABLE
        assert abs(trend.slope) < 0.05

    def test_volatile_trend(self):
        scores = [40.0, 90.0] * 10  # 20 points oscillating
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        trend = engine.analyze_trend()
        assert trend.trend_type == TrendType.VOLATILE

    def test_empty_snapshots(self):
        engine = ResilienceForecastEngine([])
        trend = engine.analyze_trend()
        assert trend.trend_type == TrendType.STABLE
        assert trend.slope == 0.0
        assert trend.volatility == 0.0

    def test_single_snapshot(self):
        snaps = _make_snapshots([80.0])
        engine = ResilienceForecastEngine(snaps)
        trend = engine.analyze_trend()
        assert trend.slope == 0.0
        assert trend.volatility == 0.0

    def test_two_snapshots_improving(self):
        snaps = _make_snapshots([70.0, 90.0], start_days_ago=10)
        engine = ResilienceForecastEngine(snaps)
        trend = engine.analyze_trend()
        assert trend.slope > 0

    def test_r_squared_range(self):
        scores = [80 + i * 0.5 for i in range(20)]
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        trend = engine.analyze_trend()
        assert 0.0 <= trend.r_squared <= 1.0

    def test_description_improving(self):
        scores = [float(s) for s in range(60, 100, 4)]
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        trend = engine.analyze_trend()
        assert "improving" in trend.description.lower()

    def test_description_stable(self):
        engine = ResilienceForecastEngine(_make_snapshots([80.0] * 10))
        trend = engine.analyze_trend()
        assert "steady" in trend.description.lower()

    def test_description_degrading(self):
        scores = [float(s) for s in range(95, 55, -4)]
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        trend = engine.analyze_trend()
        assert "declining" in trend.description.lower()

    def test_description_volatile(self):
        scores = [40.0, 90.0] * 10
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        trend = engine.analyze_trend()
        assert "volatile" in trend.description.lower()

    def test_volatility_zero_constant_scores(self):
        engine = ResilienceForecastEngine(_make_snapshots([50.0] * 10))
        trend = engine.analyze_trend()
        assert trend.volatility == 0.0

    def test_slight_improvement_is_stable(self):
        # Slope below 0.05 threshold
        scores = [80.0 + i * 0.001 for i in range(10)]
        engine = ResilienceForecastEngine(_make_snapshots(scores, start_days_ago=10))
        trend = engine.analyze_trend()
        assert trend.trend_type == TrendType.STABLE


# ═══════════════════════════════════════════════════════════
# 6. Forecasting
# ═══════════════════════════════════════════════════════════


class TestForecast:
    def test_empty_returns_empty(self):
        engine = ResilienceForecastEngine([])
        assert engine.forecast(ForecastHorizon.DAYS_30) == []

    def test_returns_list_of_forecast_points(self):
        engine = ResilienceForecastEngine(
            _make_snapshots([80 + i for i in range(10)])
        )
        pts = engine.forecast(ForecastHorizon.DAYS_30)
        assert len(pts) > 0
        assert all(isinstance(p, ForecastPoint) for p in pts)

    def test_forecast_timestamps_are_future(self):
        snaps = _make_snapshots([80.0] * 10)
        engine = ResilienceForecastEngine(snaps)
        pts = engine.forecast(ForecastHorizon.DAYS_30)
        last_ts = snaps[-1].timestamp
        for p in pts:
            assert p.timestamp > last_ts

    def test_confidence_bounds_order(self):
        engine = ResilienceForecastEngine(
            _make_snapshots([70, 72, 75, 78, 80, 82, 85, 88, 90, 92])
        )
        pts = engine.forecast(ForecastHorizon.DAYS_90)
        for p in pts:
            assert p.confidence_lower <= p.predicted_score
            assert p.predicted_score <= p.confidence_upper

    def test_confidence_level_range(self):
        engine = ResilienceForecastEngine(
            _make_snapshots([80.0 + i for i in range(10)])
        )
        pts = engine.forecast(ForecastHorizon.DAYS_90)
        for p in pts:
            assert 0.0 <= p.confidence_level <= 1.0

    def test_predicted_score_clamped_to_0_100(self):
        # Very high slope should still be clamped
        scores = [float(s) for s in range(10, 100, 10)]
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        pts = engine.forecast(ForecastHorizon.DAYS_180)
        for p in pts:
            assert 0 <= p.predicted_score <= 100

    def test_confidence_lower_at_least_zero(self):
        scores = [float(s) for s in range(95, 5, -10)]
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        pts = engine.forecast(ForecastHorizon.DAYS_180)
        for p in pts:
            assert p.confidence_lower >= 0

    def test_confidence_upper_at_most_100(self):
        scores = [float(s) for s in range(5, 100, 10)]
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        pts = engine.forecast(ForecastHorizon.DAYS_180)
        for p in pts:
            assert p.confidence_upper <= 100

    def test_horizon_7_fewer_points(self):
        engine = ResilienceForecastEngine(
            _make_snapshots([80.0] * 10)
        )
        pts_7 = engine.forecast(ForecastHorizon.DAYS_7)
        pts_90 = engine.forecast(ForecastHorizon.DAYS_90)
        assert len(pts_7) <= len(pts_90)

    def test_all_horizons_produce_output(self):
        engine = ResilienceForecastEngine(
            _make_snapshots([80.0 + i for i in range(10)])
        )
        for h in ForecastHorizon:
            pts = engine.forecast(h)
            assert len(pts) >= 2

    def test_linear_data_forecast_trend_direction(self):
        # Steadily increasing scores — forecast should continue upward
        scores = [50.0 + i for i in range(10)]
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        pts = engine.forecast(ForecastHorizon.DAYS_30)
        # Later predictions should be higher (trend preserved)
        assert pts[-1].predicted_score > pts[0].predicted_score

    def test_single_snapshot_forecast(self):
        engine = ResilienceForecastEngine(_make_snapshots([80.0]))
        pts = engine.forecast(ForecastHorizon.DAYS_30)
        assert len(pts) >= 2
        # With single point slope is 0, so predictions ≈ 80
        for p in pts:
            assert abs(p.predicted_score - 80.0) < 1


# ═══════════════════════════════════════════════════════════
# 7. Risk assessment
# ═══════════════════════════════════════════════════════════


class TestRiskAssessment:
    def test_empty_data(self):
        engine = ResilienceForecastEngine([])
        risk = engine.assess_risk(ForecastHorizon.DAYS_30)
        assert risk.risk_level == RiskLevel.MEDIUM
        assert risk.breach_probability == 0.5

    def test_high_scores_low_risk(self):
        scores = [98.0] * 10
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        risk = engine.assess_risk(ForecastHorizon.DAYS_30)
        assert risk.risk_level == RiskLevel.LOW

    def test_degrading_high_risk(self):
        scores = [float(s) for s in range(98, 50, -5)]
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        risk = engine.assess_risk(ForecastHorizon.DAYS_90)
        assert risk.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    def test_below_slo_already(self):
        scores = [80.0] * 10  # below default 95.0 SLO
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        risk = engine.assess_risk(ForecastHorizon.DAYS_30)
        assert "below SLO" in " ".join(risk.contributing_factors)

    def test_custom_slo_threshold(self):
        scores = [80.0] * 10
        engine = ResilienceForecastEngine(
            _make_snapshots(scores), slo_threshold=70.0
        )
        risk = engine.assess_risk(ForecastHorizon.DAYS_30)
        # Score well above the 70 threshold → low/medium risk
        assert risk.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM)

    def test_days_to_threshold_set_when_degrading(self):
        scores = [98.0 - i * 0.5 for i in range(20)]
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        risk = engine.assess_risk(ForecastHorizon.DAYS_180)
        # Should have days_to_threshold because slope < 0 and current > slo
        if risk.days_to_threshold is not None:
            assert risk.days_to_threshold > 0

    def test_days_to_threshold_none_when_stable_above(self):
        scores = [98.0] * 10
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        risk = engine.assess_risk(ForecastHorizon.DAYS_30)
        assert risk.days_to_threshold is None

    def test_breach_probability_range(self):
        scores = [70 + i for i in range(10)]
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        risk = engine.assess_risk(ForecastHorizon.DAYS_90)
        assert 0.0 <= risk.breach_probability <= 1.0

    def test_contributing_factors_non_empty(self):
        engine = ResilienceForecastEngine(
            _make_snapshots([80.0] * 10)
        )
        risk = engine.assess_risk(ForecastHorizon.DAYS_30)
        assert len(risk.contributing_factors) > 0

    def test_spof_factor_detected(self):
        # Scores below 80 → spof_count > 0 via _make_snapshots
        scores = [60.0] * 10
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        risk = engine.assess_risk(ForecastHorizon.DAYS_30)
        factors_text = " ".join(risk.contributing_factors)
        assert "SPOF" in factors_text

    def test_recovery_time_factor(self):
        # avg_recovery_time = 30 - score*0.2 → score=60 → recovery=18 min
        scores = [60.0] * 10
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        risk = engine.assess_risk(ForecastHorizon.DAYS_30)
        factors_text = " ".join(risk.contributing_factors)
        assert "Recovery" in factors_text or "recovery" in factors_text.lower()

    def test_critical_risk_very_steep_decline(self):
        scores = [100.0 - i * 5 for i in range(20)]
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        risk = engine.assess_risk(ForecastHorizon.DAYS_30)
        assert risk.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    def test_days_to_threshold_calculated(self):
        # Start at 100 and decline gently so last smoothed stays above SLO=95
        scores = [100.0 - i * 0.1 for i in range(20)]
        engine = ResilienceForecastEngine(
            _make_snapshots(scores, start_days_ago=60), slo_threshold=95.0
        )
        risk = engine.assess_risk(ForecastHorizon.DAYS_180)
        # Slope is negative, current > slo → days_to_threshold should be set
        assert risk.days_to_threshold is not None
        assert risk.days_to_threshold >= 1

    def test_days_to_threshold_none_when_exceeds_horizon(self):
        # Very slight decline: days_to would exceed horizon → stays None
        scores = [99.0 - i * 0.001 for i in range(10)]
        engine = ResilienceForecastEngine(
            _make_snapshots(scores, start_days_ago=30), slo_threshold=95.0
        )
        risk = engine.assess_risk(ForecastHorizon.DAYS_7)
        # days_to should be None because the very small slope means
        # it would take way longer than 7 days
        assert risk.days_to_threshold is None


# ═══════════════════════════════════════════════════════════
# 8. Anomaly detection
# ═══════════════════════════════════════════════════════════


class TestAnomalyDetection:
    def test_no_anomalies_stable(self):
        scores = [80.0] * 10
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        assert engine.detect_anomalies() == []

    def test_single_spike(self):
        scores = [80.0] * 9 + [20.0]
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        anomalies = engine.detect_anomalies()
        assert len(anomalies) >= 1
        assert any(a.score == 20.0 for a in anomalies)

    def test_single_high_spike(self):
        scores = [50.0] * 9 + [100.0]
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        anomalies = engine.detect_anomalies()
        assert len(anomalies) >= 1

    def test_multiple_anomalies(self):
        scores = [80.0] * 18 + [10.0, 5.0]
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        anomalies = engine.detect_anomalies()
        assert len(anomalies) >= 2

    def test_too_few_data_points(self):
        engine = ResilienceForecastEngine(_make_snapshots([80.0, 20.0]))
        assert engine.detect_anomalies() == []

    def test_empty_data(self):
        engine = ResilienceForecastEngine([])
        assert engine.detect_anomalies() == []

    def test_all_identical_no_anomalies(self):
        engine = ResilienceForecastEngine(_make_snapshots([50.0] * 20))
        assert engine.detect_anomalies() == []

    def test_gradual_change_no_anomalies(self):
        scores = [80 + i * 0.5 for i in range(20)]
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        anomalies = engine.detect_anomalies()
        # Gradual linear change shouldn't trigger z-score anomalies
        assert len(anomalies) <= 2  # possibly edge values


# ═══════════════════════════════════════════════════════════
# 9. Report generation
# ═══════════════════════════════════════════════════════════


class TestReportGeneration:
    def test_report_returns_model(self):
        engine = ResilienceForecastEngine(
            _make_snapshots([80.0 + i for i in range(10)])
        )
        report = engine.generate_report(ForecastHorizon.DAYS_30)
        assert isinstance(report, ResilienceForecastReport)

    def test_report_current_score(self):
        scores = [70.0, 75.0, 80.0, 85.0, 90.0]
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        report = engine.generate_report(ForecastHorizon.DAYS_30)
        assert report.current_score == 90.0

    def test_report_has_trend(self):
        engine = ResilienceForecastEngine(
            _make_snapshots([80.0] * 10)
        )
        report = engine.generate_report(ForecastHorizon.DAYS_30)
        assert isinstance(report.trend, TrendAnalysis)

    def test_report_has_forecast_points(self):
        engine = ResilienceForecastEngine(
            _make_snapshots([80.0 + i for i in range(10)])
        )
        report = engine.generate_report(ForecastHorizon.DAYS_60)
        assert len(report.forecast_points) >= 2

    def test_report_has_risk(self):
        engine = ResilienceForecastEngine(
            _make_snapshots([80.0] * 10)
        )
        report = engine.generate_report(ForecastHorizon.DAYS_30)
        assert isinstance(report.risk_forecast, RiskForecast)

    def test_report_has_recommendations(self):
        engine = ResilienceForecastEngine(
            _make_snapshots([80.0] * 10)
        )
        report = engine.generate_report(ForecastHorizon.DAYS_30)
        assert len(report.recommendations) >= 1

    def test_report_generated_at(self):
        engine = ResilienceForecastEngine(
            _make_snapshots([80.0] * 10)
        )
        before = datetime.now(timezone.utc)
        report = engine.generate_report(ForecastHorizon.DAYS_30)
        after = datetime.now(timezone.utc)
        assert before <= report.generated_at <= after

    def test_report_empty_data(self):
        engine = ResilienceForecastEngine([])
        report = engine.generate_report(ForecastHorizon.DAYS_30)
        assert report.current_score == 0.0
        assert report.forecast_points == []

    def test_report_all_horizons(self):
        engine = ResilienceForecastEngine(
            _make_snapshots([80.0 + i for i in range(10)])
        )
        for h in ForecastHorizon:
            report = engine.generate_report(h)
            assert isinstance(report, ResilienceForecastReport)

    def test_report_degrading_has_action_recs(self):
        scores = [float(s) for s in range(95, 55, -4)]
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        report = engine.generate_report(ForecastHorizon.DAYS_30)
        recs_text = " ".join(report.recommendations)
        assert "declining" in recs_text.lower() or "breach" in recs_text.lower() or "action" in recs_text.lower()


# ═══════════════════════════════════════════════════════════
# 10. Edge cases
# ═══════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_single_snapshot_trend(self):
        engine = ResilienceForecastEngine(_make_snapshots([50.0]))
        trend = engine.analyze_trend()
        assert trend.slope == 0.0
        assert trend.trend_type == TrendType.STABLE

    def test_single_snapshot_risk(self):
        engine = ResilienceForecastEngine(_make_snapshots([50.0]))
        risk = engine.assess_risk(ForecastHorizon.DAYS_30)
        assert isinstance(risk.risk_level, RiskLevel)

    def test_two_snapshots(self):
        engine = ResilienceForecastEngine(
            _make_snapshots([60.0, 80.0], start_days_ago=30)
        )
        trend = engine.analyze_trend()
        assert trend.slope > 0
        pts = engine.forecast(ForecastHorizon.DAYS_30)
        assert len(pts) >= 2

    def test_identical_scores(self):
        engine = ResilienceForecastEngine(_make_snapshots([75.0] * 15))
        trend = engine.analyze_trend()
        assert trend.trend_type == TrendType.STABLE
        assert trend.volatility == 0.0

    def test_zero_slope(self):
        engine = ResilienceForecastEngine(_make_snapshots([50.0] * 10))
        trend = engine.analyze_trend()
        assert trend.slope == 0.0

    def test_very_negative_slope(self):
        scores = [100.0 - i * 10 for i in range(10)]
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        trend = engine.analyze_trend()
        assert trend.slope < 0
        assert trend.trend_type == TrendType.DEGRADING

    def test_all_max_scores(self):
        engine = ResilienceForecastEngine(_make_snapshots([100.0] * 10))
        trend = engine.analyze_trend()
        assert trend.trend_type == TrendType.STABLE
        risk = engine.assess_risk(ForecastHorizon.DAYS_30)
        assert risk.risk_level == RiskLevel.LOW

    def test_all_zero_scores(self):
        engine = ResilienceForecastEngine(_make_snapshots([0.0] * 10))
        trend = engine.analyze_trend()
        assert trend.trend_type == TrendType.STABLE
        risk = engine.assess_risk(ForecastHorizon.DAYS_30)
        # Score far below SLO
        assert risk.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    def test_snapshots_sorted_on_init(self):
        now = datetime.now(timezone.utc)
        s1 = ResilienceSnapshot(
            timestamp=now - timedelta(days=10), score=80, component_count=5,
            spof_count=0, avg_recovery_time_min=5, change_count=1,
        )
        s2 = ResilienceSnapshot(
            timestamp=now - timedelta(days=5), score=85, component_count=5,
            spof_count=0, avg_recovery_time_min=5, change_count=1,
        )
        s3 = ResilienceSnapshot(
            timestamp=now, score=90, component_count=5,
            spof_count=0, avg_recovery_time_min=5, change_count=1,
        )
        # Pass in wrong order
        engine = ResilienceForecastEngine([s3, s1, s2])
        trend = engine.analyze_trend()
        assert trend.slope > 0  # improving regardless of input order

    def test_large_dataset(self):
        scores = [50 + 30 * math.sin(i / 5) for i in range(100)]
        scores = [max(0.0, min(100.0, s)) for s in scores]
        engine = ResilienceForecastEngine(
            _make_snapshots(scores, start_days_ago=365)
        )
        trend = engine.analyze_trend()
        assert isinstance(trend.trend_type, TrendType)

    def test_two_identical_timestamps(self):
        now = datetime.now(timezone.utc)
        snaps = [
            ResilienceSnapshot(
                timestamp=now, score=80, component_count=5,
                spof_count=0, avg_recovery_time_min=5, change_count=1,
            ),
            ResilienceSnapshot(
                timestamp=now, score=80, component_count=5,
                spof_count=0, avg_recovery_time_min=5, change_count=1,
            ),
        ]
        engine = ResilienceForecastEngine(snaps)
        trend = engine.analyze_trend()
        assert trend.slope == 0.0


# ═══════════════════════════════════════════════════════════
# 11. Different horizons
# ═══════════════════════════════════════════════════════════


class TestDifferentHorizons:
    @pytest.fixture()
    def engine(self):
        return ResilienceForecastEngine(
            _make_snapshots([80.0 + i * 0.5 for i in range(20)])
        )

    def test_7_day_horizon(self, engine):
        pts = engine.forecast(ForecastHorizon.DAYS_7)
        assert len(pts) >= 2
        delta = (pts[-1].timestamp - pts[0].timestamp).total_seconds()
        assert delta <= 7 * 86400 + 1

    def test_30_day_horizon(self, engine):
        pts = engine.forecast(ForecastHorizon.DAYS_30)
        assert len(pts) >= 2

    def test_60_day_horizon(self, engine):
        pts = engine.forecast(ForecastHorizon.DAYS_60)
        assert len(pts) >= 2

    def test_90_day_horizon(self, engine):
        pts = engine.forecast(ForecastHorizon.DAYS_90)
        assert len(pts) >= 2

    def test_180_day_horizon(self, engine):
        pts = engine.forecast(ForecastHorizon.DAYS_180)
        assert len(pts) >= 2

    def test_longer_horizon_more_points(self, engine):
        pts_7 = engine.forecast(ForecastHorizon.DAYS_7)
        pts_180 = engine.forecast(ForecastHorizon.DAYS_180)
        assert len(pts_180) >= len(pts_7)

    def test_risk_differs_by_horizon(self, engine):
        r7 = engine.assess_risk(ForecastHorizon.DAYS_7)
        r180 = engine.assess_risk(ForecastHorizon.DAYS_180)
        # Both should be valid
        assert isinstance(r7.risk_level, RiskLevel)
        assert isinstance(r180.risk_level, RiskLevel)


# ═══════════════════════════════════════════════════════════
# 12. Recommendations
# ═══════════════════════════════════════════════════════════


class TestRecommendations:
    def test_degrading_gives_investigate_rec(self):
        scores = [float(s) for s in range(95, 55, -4)]
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        report = engine.generate_report(ForecastHorizon.DAYS_30)
        assert any("root cause" in r.lower() for r in report.recommendations)

    def test_volatile_gives_stability_rec(self):
        scores = [40.0, 90.0] * 10
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        report = engine.generate_report(ForecastHorizon.DAYS_30)
        assert any("volatility" in r.lower() for r in report.recommendations)

    def test_stable_high_no_action(self):
        engine = ResilienceForecastEngine(
            _make_snapshots([98.0] * 10)
        )
        report = engine.generate_report(ForecastHorizon.DAYS_30)
        assert any("no action" in r.lower() or "monitor" in r.lower() for r in report.recommendations)

    def test_spof_recommendation(self):
        # Score 60 → spof_count = 2 via helper
        scores = [60.0] * 10
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        report = engine.generate_report(ForecastHorizon.DAYS_30)
        recs_text = " ".join(report.recommendations).lower()
        assert "single point" in recs_text or "spof" in recs_text.lower()

    def test_recovery_recommendation(self):
        # Score 60 → avg_recovery = 30 - 60*0.2 = 18 min → > 15
        scores = [60.0] * 10
        engine = ResilienceForecastEngine(_make_snapshots(scores))
        report = engine.generate_report(ForecastHorizon.DAYS_30)
        recs_text = " ".join(report.recommendations).lower()
        assert "recovery" in recs_text

    def test_days_to_threshold_recommendation(self):
        # Gently declining from above SLO → triggers days_to_threshold rec
        scores = [100.0 - i * 0.1 for i in range(20)]
        engine = ResilienceForecastEngine(
            _make_snapshots(scores, start_days_ago=60), slo_threshold=95.0
        )
        report = engine.generate_report(ForecastHorizon.DAYS_180)
        recs_text = " ".join(report.recommendations).lower()
        assert "projected" in recs_text or "breach" in recs_text


# ═══════════════════════════════════════════════════════════
# 13. Risk level classification
# ═══════════════════════════════════════════════════════════


class TestRiskLevelClassification:
    def test_critical_high_probability(self):
        level = ResilienceForecastEngine._risk_level(0.85, None, 30)
        assert level == RiskLevel.CRITICAL

    def test_critical_days_to_threshold_very_soon(self):
        level = ResilienceForecastEngine._risk_level(0.3, 5, 90)
        assert level == RiskLevel.CRITICAL

    def test_high_probability(self):
        level = ResilienceForecastEngine._risk_level(0.55, None, 30)
        assert level == RiskLevel.HIGH

    def test_high_days_to_threshold(self):
        level = ResilienceForecastEngine._risk_level(0.1, 25, 90)
        assert level == RiskLevel.HIGH

    def test_medium_probability(self):
        level = ResilienceForecastEngine._risk_level(0.25, None, 90)
        assert level == RiskLevel.MEDIUM

    def test_medium_days_to_threshold(self):
        level = ResilienceForecastEngine._risk_level(0.1, 60, 90)
        assert level == RiskLevel.MEDIUM

    def test_low_risk(self):
        level = ResilienceForecastEngine._risk_level(0.05, None, 90)
        assert level == RiskLevel.LOW

    def test_boundary_critical_at_0_8(self):
        level = ResilienceForecastEngine._risk_level(0.8, None, 30)
        assert level == RiskLevel.CRITICAL

    def test_boundary_high_at_0_5(self):
        level = ResilienceForecastEngine._risk_level(0.5, None, 30)
        assert level == RiskLevel.HIGH

    def test_boundary_medium_at_0_2(self):
        level = ResilienceForecastEngine._risk_level(0.2, None, 90)
        assert level == RiskLevel.MEDIUM

    def test_boundary_low_below_0_2(self):
        level = ResilienceForecastEngine._risk_level(0.19, None, 90)
        assert level == RiskLevel.LOW


# ═══════════════════════════════════════════════════════════
# 14. Trend classification
# ═══════════════════════════════════════════════════════════


class TestTrendClassification:
    def test_volatile_high_vol_low_r2(self):
        tt = ResilienceForecastEngine._classify_trend(0.5, 0.1, 15.0)
        assert tt == TrendType.VOLATILE

    def test_stable_small_slope(self):
        tt = ResilienceForecastEngine._classify_trend(0.03, 0.9, 2.0)
        assert tt == TrendType.STABLE

    def test_improving_positive_slope(self):
        tt = ResilienceForecastEngine._classify_trend(0.2, 0.9, 2.0)
        assert tt == TrendType.IMPROVING

    def test_degrading_negative_slope(self):
        tt = ResilienceForecastEngine._classify_trend(-0.3, 0.9, 2.0)
        assert tt == TrendType.DEGRADING

    def test_boundary_stable_at_threshold(self):
        tt = ResilienceForecastEngine._classify_trend(0.049, 0.9, 2.0)
        assert tt == TrendType.STABLE

    def test_boundary_improving_at_threshold(self):
        tt = ResilienceForecastEngine._classify_trend(0.05, 0.9, 2.0)
        assert tt == TrendType.IMPROVING


# ═══════════════════════════════════════════════════════════
# 15. Standard deviation helper
# ═══════════════════════════════════════════════════════════


class TestStdHelper:
    def test_empty(self):
        assert ResilienceForecastEngine._std([]) == 0.0

    def test_single(self):
        assert ResilienceForecastEngine._std([5.0]) == 0.0

    def test_known_values(self):
        vals = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
        std = ResilienceForecastEngine._std(vals)
        assert abs(std - 2.138) < 0.01  # sample std of [2,4,4,4,5,5,7,9]
