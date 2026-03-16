"""Resilience Forecast Engine — predict future resilience scores.

Uses time-series analysis of historical snapshots to answer:
"If we continue our current trajectory, what will our resilience
score be in 30/60/90 days?"

No external ML libraries — implements linear regression with basic math.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from enum import Enum

from pydantic import BaseModel, Field


class ForecastHorizon(int, Enum):
    """Prediction horizon in days."""

    DAYS_7 = 7
    DAYS_30 = 30
    DAYS_60 = 60
    DAYS_90 = 90
    DAYS_180 = 180


class TrendType(str, Enum):
    """Direction of the resilience trend."""

    IMPROVING = "improving"
    STABLE = "stable"
    DEGRADING = "degrading"
    VOLATILE = "volatile"


class RiskLevel(str, Enum):
    """Forecasted risk level."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ── Data Models ──────────────────────────────────────────────


class ResilienceSnapshot(BaseModel):
    """A single point-in-time resilience measurement."""

    timestamp: datetime
    score: float = Field(ge=0, le=100)
    component_count: int = Field(ge=0)
    spof_count: int = Field(ge=0)
    avg_recovery_time_min: float = Field(ge=0)
    change_count: int = Field(ge=0)


class ForecastPoint(BaseModel):
    """One predicted future data-point."""

    timestamp: datetime
    predicted_score: float
    confidence_lower: float
    confidence_upper: float
    confidence_level: float = Field(ge=0, le=1)


class TrendAnalysis(BaseModel):
    """Result of trend analysis on historical snapshots."""

    trend_type: TrendType
    slope: float  # score change per day
    r_squared: float
    volatility: float
    description: str


class RiskForecast(BaseModel):
    """SLO-breach risk assessment."""

    risk_level: RiskLevel
    days_to_threshold: int | None
    breach_probability: float = Field(ge=0, le=1)
    contributing_factors: list[str]


class ResilienceForecastReport(BaseModel):
    """Complete forecast report."""

    current_score: float
    trend: TrendAnalysis
    forecast_points: list[ForecastPoint]
    risk_forecast: RiskForecast
    recommendations: list[str]
    generated_at: datetime


# ── Helpers ──────────────────────────────────────────────────


def _mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _moving_average(vals: list[float], window: int = 5) -> list[float]:
    if len(vals) <= window:
        return vals[:]
    out: list[float] = []
    for i in range(len(vals)):
        lo = max(0, i - window + 1)
        out.append(_mean(vals[lo : i + 1]))
    return out


def _linear_regression(
    xs: list[float], ys: list[float]
) -> tuple[float, float, float]:
    """Return (slope, intercept, r_squared)."""
    n = len(xs)
    if n < 2:
        return 0.0, (ys[0] if ys else 0.0), 0.0
    mx, my = _mean(xs), _mean(ys)
    ss_xy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    ss_xx = sum((x - mx) ** 2 for x in xs)
    if ss_xx == 0:
        return 0.0, my, 0.0
    slope = ss_xy / ss_xx
    intercept = my - slope * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    r_sq = 1 - ss_res / ss_tot if ss_tot > 0 else 1.0
    return slope, intercept, max(0.0, r_sq)


# ── Engine ───────────────────────────────────────────────────


class ResilienceForecastEngine:
    """Predict future resilience scores from historical snapshots."""

    _ANOMALY_Z_THRESHOLD = 2.0

    def __init__(
        self,
        snapshots: list[ResilienceSnapshot],
        slo_threshold: float = 95.0,
    ) -> None:
        self._snapshots = sorted(snapshots, key=lambda s: s.timestamp)
        self._slo = slo_threshold
        if self._snapshots:
            self._origin = self._snapshots[0].timestamp
            self._days = [
                (s.timestamp - self._origin).total_seconds() / 86400
                for s in self._snapshots
            ]
            self._scores = [s.score for s in self._snapshots]
            self._smoothed = _moving_average(self._scores)
        else:
            self._origin = datetime.now(timezone.utc)
            self._days: list[float] = []
            self._scores: list[float] = []
            self._smoothed: list[float] = []

    # ── Public API ───────────────────────────────────────────

    def analyze_trend(self) -> TrendAnalysis:
        if not self._scores:
            return TrendAnalysis(
                trend_type=TrendType.STABLE,
                slope=0.0,
                r_squared=0.0,
                volatility=0.0,
                description="No data available for trend analysis.",
            )

        slope, _, r_sq = _linear_regression(self._days, self._smoothed)
        volatility = self._volatility()
        trend = self._classify_trend(slope, r_sq, volatility)

        descs = {
            TrendType.IMPROVING: f"Resilience is improving at {slope:+.3f} points/day.",
            TrendType.STABLE: "Resilience is holding steady.",
            TrendType.DEGRADING: f"Resilience is declining at {slope:+.3f} points/day.",
            TrendType.VOLATILE: f"Resilience is volatile (std={volatility:.2f}).",
        }
        return TrendAnalysis(
            trend_type=trend,
            slope=round(slope, 6),
            r_squared=round(r_sq, 6),
            volatility=round(volatility, 6),
            description=descs[trend],
        )

    def forecast(self, horizon: ForecastHorizon) -> list[ForecastPoint]:
        if not self._scores:
            return []

        slope, intercept, _ = _linear_regression(self._days, self._smoothed)
        residuals = [
            y - (slope * x + intercept)
            for x, y in zip(self._days, self._smoothed)
        ]
        std_res = self._std(residuals)
        last_day = self._days[-1] if self._days else 0.0
        last_ts = self._snapshots[-1].timestamp

        points: list[ForecastPoint] = []
        n_points = max(2, horizon.value // 7)
        step = horizon.value / n_points

        for i in range(1, n_points + 1):
            d = last_day + step * i
            pred = slope * d + intercept
            days_ahead = step * i
            decay = max(0.3, 1.0 - days_ahead / (horizon.value * 2))
            margin = 1.96 * std_res * math.sqrt(1 + days_ahead / max(len(self._scores), 1))
            points.append(
                ForecastPoint(
                    timestamp=last_ts + timedelta(days=days_ahead),
                    predicted_score=round(max(0, min(100, pred)), 2),
                    confidence_lower=round(max(0, pred - margin), 2),
                    confidence_upper=round(min(100, pred + margin), 2),
                    confidence_level=round(decay, 4),
                )
            )
        return points

    def assess_risk(self, horizon: ForecastHorizon) -> RiskForecast:
        if not self._scores:
            return RiskForecast(
                risk_level=RiskLevel.MEDIUM,
                days_to_threshold=None,
                breach_probability=0.5,
                contributing_factors=["Insufficient data for assessment."],
            )

        slope, intercept, _ = _linear_regression(self._days, self._smoothed)
        last_day = self._days[-1]
        current = self._smoothed[-1]
        factors: list[str] = []

        # Days until score crosses SLO threshold (going down)
        days_to: int | None = None
        if slope < 0 and current > self._slo:
            gap = current - self._slo
            days_to = max(1, int(gap / abs(slope)))
            if days_to > horizon.value:
                days_to = None

        # Breach probability
        future_score = slope * (last_day + horizon.value) + intercept
        vol = self._volatility()
        if vol > 0:
            z = (self._slo - future_score) / vol
            prob = 0.5 * (1 + math.erf(z / math.sqrt(2)))
        else:
            prob = 1.0 if future_score < self._slo else 0.0

        prob = max(0.0, min(1.0, prob))

        if slope < -0.1:
            factors.append("Score is trending downward.")
        if vol > 5:
            factors.append("High score volatility increases risk.")
        if current < self._slo:
            factors.append("Current score already below SLO threshold.")
        spofs = [s for s in self._snapshots if s.spof_count > 0]
        if spofs:
            factors.append(f"SPOFs detected in {len(spofs)} snapshots.")
        recovery = [s for s in self._snapshots if s.avg_recovery_time_min > 15]
        if recovery:
            factors.append("Recovery time exceeds 15 min in some snapshots.")
        if not factors:
            factors.append("No significant risk factors identified.")

        level = self._risk_level(prob, days_to, horizon.value)

        return RiskForecast(
            risk_level=level,
            days_to_threshold=days_to,
            breach_probability=round(prob, 4),
            contributing_factors=factors,
        )

    def detect_anomalies(self) -> list[ResilienceSnapshot]:
        if len(self._scores) < 3:
            return []
        mean = _mean(self._scores)
        std = self._std(self._scores)
        if std == 0:
            return []
        return [
            s
            for s, score in zip(self._snapshots, self._scores)
            if abs(score - mean) / std >= self._ANOMALY_Z_THRESHOLD
        ]

    def generate_report(
        self, horizon: ForecastHorizon
    ) -> ResilienceForecastReport:
        trend = self.analyze_trend()
        forecast_pts = self.forecast(horizon)
        risk = self.assess_risk(horizon)
        recs = self._recommendations(trend, risk)

        return ResilienceForecastReport(
            current_score=self._scores[-1] if self._scores else 0.0,
            trend=trend,
            forecast_points=forecast_pts,
            risk_forecast=risk,
            recommendations=recs,
            generated_at=datetime.now(timezone.utc),
        )

    # ── Private helpers ──────────────────────────────────────

    def _volatility(self) -> float:
        return self._std(self._scores)

    @staticmethod
    def _std(vals: list[float]) -> float:
        if len(vals) < 2:
            return 0.0
        m = _mean(vals)
        var = sum((v - m) ** 2 for v in vals) / (len(vals) - 1)
        return math.sqrt(var)

    @staticmethod
    def _classify_trend(
        slope: float, r_sq: float, volatility: float
    ) -> TrendType:
        if volatility > 10 and r_sq < 0.3:
            return TrendType.VOLATILE
        if abs(slope) < 0.05:
            return TrendType.STABLE
        return TrendType.IMPROVING if slope > 0 else TrendType.DEGRADING

    @staticmethod
    def _risk_level(
        prob: float, days_to: int | None, horizon_days: int
    ) -> RiskLevel:
        if prob >= 0.8 or (days_to is not None and days_to <= 7):
            return RiskLevel.CRITICAL
        if prob >= 0.5 or (days_to is not None and days_to <= 30):
            return RiskLevel.HIGH
        if prob >= 0.2 or (days_to is not None and days_to <= horizon_days):
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    @staticmethod
    def _recommendations(
        trend: TrendAnalysis, risk: RiskForecast
    ) -> list[str]:
        recs: list[str] = []
        if trend.trend_type == TrendType.DEGRADING:
            recs.append(
                "Investigate the root cause of declining resilience scores."
            )
        if trend.trend_type == TrendType.VOLATILE:
            recs.append(
                "Reduce score volatility by stabilising change management."
            )
        if risk.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            recs.append(
                "Immediate action needed to prevent SLO breach."
            )
        if risk.days_to_threshold is not None:
            recs.append(
                f"Score projected to breach SLO in {risk.days_to_threshold} days."
            )
        if any("SPOF" in f for f in risk.contributing_factors):
            recs.append("Eliminate single points of failure.")
        if any("Recovery" in f for f in risk.contributing_factors):
            recs.append("Improve recovery time to under 15 minutes.")
        if not recs:
            recs.append("Continue monitoring — no action required.")
        return recs
