# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Predictive failure engine for FaultRay.

Predicts future failures from degradation trends using linear extrapolation
and exponential failure probability (CDF).  Uses ONLY the Python standard
library -- no numpy, scipy, or scikit-learn.

Extended with:
- ComponentReliability: MTBF/MTTR-based failure prediction with Poisson model
- CapacityForecast: Resource exhaustion prediction with threshold alerts
- SLAForecast: SLA achievement probability and error budget projection
- RiskTimelineEvent: Time-ordered risk event timeline generation
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from faultray.model.graph import InfraGraph

# ---------------------------------------------------------------------------
# Default MTBF values (hours) when component has no explicit profile
# ---------------------------------------------------------------------------
_DEFAULT_MTBF: dict[str, float] = {
    "app_server": 2160.0,
    "web_server": 2160.0,
    "database": 4320.0,
    "cache": 1440.0,
    "load_balancer": 8760.0,
    "queue": 2160.0,
    "dns": 43800.0,
    "storage": 8760.0,
}


# ---------------------------------------------------------------------------
# Result dataclasses (original)
# ---------------------------------------------------------------------------


@dataclass
class ResourceExhaustionPrediction:
    """Prediction for when a specific resource will be exhausted."""

    component_id: str
    resource: str  # "memory", "disk", "connections"
    current_usage_percent: float
    growth_rate_per_hour: float
    days_to_exhaustion: float
    exhaustion_date: str  # ISO format
    recommended_action: str


@dataclass
class FailureProbabilityForecast:
    """Failure probability forecast for a component over various horizons."""

    component_id: str
    mtbf_hours: float
    probability_7d: float  # P(failure in 7 days)
    probability_30d: float  # P(failure in 30 days)
    probability_90d: float  # P(failure in 90 days)


@dataclass
class PredictiveReport:
    """Full predictive analysis report."""

    exhaustion_predictions: list[ResourceExhaustionPrediction] = field(
        default_factory=list,
    )
    failure_forecasts: list[FailureProbabilityForecast] = field(
        default_factory=list,
    )
    recommended_maintenance_window: str = ""
    summary: str = ""


# ---------------------------------------------------------------------------
# New dataclasses for Predictive Engine v2
# ---------------------------------------------------------------------------


@dataclass
class ComponentReliability:
    """MTBF/MTTR-based failure prediction for a single component."""

    component_id: str
    mtbf_hours: float  # Mean Time Between Failures
    mttr_hours: float  # Mean Time To Repair
    failure_probability_30d: float  # P(failure in 30 days)
    failure_probability_90d: float  # P(failure in 90 days)
    expected_days_to_failure: float  # MTBF in days
    risk_level: str  # critical/high/medium/low


@dataclass
class CapacityForecast:
    """Resource exhaustion forecast with threshold alerts."""

    resource_type: str  # cpu/memory/storage/network
    current_usage_percent: float
    growth_rate_per_month: float  # percentage points per month
    days_to_80_percent: Optional[float]
    days_to_90_percent: Optional[float]
    days_to_100_percent: Optional[float]
    recommendation: str


@dataclass
class SLAForecast:
    """SLA achievement probability and error budget projection."""

    slo_target: float  # e.g. 99.9
    current_availability: float  # e.g. 99.95
    error_budget_remaining_percent: float  # e.g. 50.0 means 50% left
    days_until_budget_exhaustion: Optional[float]
    monthly_sla_probability: float  # 0.0 to 1.0
    quarterly_sla_probability: float  # 0.0 to 1.0
    trend: str  # improving/stable/degrading


@dataclass
class RiskTimelineEvent:
    """A single risk event on the predicted timeline."""

    days_from_now: float
    event_type: str  # failure/capacity/sla
    severity: str  # critical/high/medium/low
    description: str
    component_or_resource: str


# ---------------------------------------------------------------------------
# Helpers (original)
# ---------------------------------------------------------------------------


def _failure_probability(t_hours: float, mtbf_hours: float) -> float:
    """Compute P(failure within t hours) using exponential CDF.

    P(fail in t) = 1 - exp(-t / MTBF)
    """
    if mtbf_hours <= 0:
        return 1.0
    if t_hours <= 0:
        return 0.0
    return 1.0 - math.exp(-t_hours / mtbf_hours)


def _days_to_exhaust(current_percent: float, rate_per_hour: float) -> float:
    """Linearly extrapolate days until a resource reaches 100%.

    Returns ``float('inf')`` when the rate is zero or negative.
    """
    if rate_per_hour <= 0:
        return float("inf")
    remaining_percent = 100.0 - current_percent
    if remaining_percent <= 0:
        return 0.0
    hours = remaining_percent / rate_per_hour
    return hours / 24.0


def _recommend_action(resource: str, days: float) -> str:
    """Generate a human-readable recommendation based on resource type and TTL."""
    if days <= 1:
        urgency = "CRITICAL"
    elif days <= 7:
        urgency = "HIGH"
    elif days <= 30:
        urgency = "MEDIUM"
    else:
        urgency = "LOW"

    actions: dict[str, str] = {
        "memory": "Investigate memory leak. Consider restarting or increasing memory limit.",
        "disk": "Clean old data/logs or expand disk volume.",
        "connections": "Investigate connection leak. Increase pool size or add connection recycling.",
    }
    base = actions.get(resource, f"Monitor {resource} growth and plan capacity expansion.")
    return f"[{urgency}] {base} Exhaustion in ~{days:.1f} days."


def _suggest_maintenance_window(predictions: list[ResourceExhaustionPrediction]) -> str:
    """Suggest a maintenance window based on the most urgent exhaustion.

    Recommends scheduling maintenance during low-traffic hours (02:00-06:00
    UTC) before the earliest predicted exhaustion.
    """
    if not predictions:
        return "No urgent maintenance needed."

    # Find the soonest exhaustion
    soonest = min(predictions, key=lambda p: p.days_to_exhaustion)
    if soonest.days_to_exhaustion == float("inf"):
        return "No resource exhaustion predicted within the forecast horizon."

    now = datetime.now(timezone.utc)
    target = now + timedelta(days=max(0, soonest.days_to_exhaustion - 1))
    # Snap to next 02:00 UTC
    window_start = target.replace(hour=2, minute=0, second=0, microsecond=0)
    if window_start < now:
        window_start += timedelta(days=1)
    window_end = window_start.replace(hour=6)

    return (
        f"Recommended maintenance window: "
        f"{window_start.strftime('%Y-%m-%d %H:%M')} - "
        f"{window_end.strftime('%Y-%m-%d %H:%M')} UTC "
        f"(before {soonest.component_id}/{soonest.resource} exhaustion "
        f"in ~{soonest.days_to_exhaustion:.1f} days)"
    )


# ---------------------------------------------------------------------------
# New helpers for Predictive Engine v2
# ---------------------------------------------------------------------------


def _poisson_at_least_one(lambda_rate: float, t_days: float) -> float:
    """Compute P(at least one event in t_days) using Poisson distribution.

    P(N >= 1) = 1 - P(N = 0) = 1 - exp(-lambda * t)

    This is mathematically identical to the exponential CDF but framed
    in terms of a Poisson rate (events per day).
    """
    if lambda_rate <= 0:
        return 0.0
    if t_days <= 0:
        return 0.0
    exponent = lambda_rate * t_days
    # Guard against overflow for very large exponents
    if exponent > 700:
        return 1.0
    return 1.0 - math.exp(-exponent)


def _compound_failure_probability(probabilities: list[float]) -> float:
    """Compute P(at least one failure) from independent component failure probabilities.

    P(at least one) = 1 - product(1 - p_i)
    """
    if not probabilities:
        return 0.0
    survival = 1.0
    for p in probabilities:
        survival *= (1.0 - p)
    return 1.0 - survival


def _classify_risk(failure_prob_30d: float) -> str:
    """Classify risk level based on 30-day failure probability.

    Returns one of: critical, high, medium, low.
    """
    if failure_prob_30d >= 0.7:
        return "critical"
    elif failure_prob_30d >= 0.4:
        return "high"
    elif failure_prob_30d >= 0.15:
        return "medium"
    else:
        return "low"


def _days_to_threshold(
    current_percent: float,
    growth_rate_per_month: float,
    threshold: float,
) -> Optional[float]:
    """Calculate days until usage reaches the given threshold percentage.

    Returns None if the threshold is already exceeded or growth rate is
    zero/negative (meaning the threshold will never be reached).
    """
    if current_percent >= threshold:
        return 0.0
    if growth_rate_per_month <= 0:
        return None
    remaining = threshold - current_percent
    # growth_rate_per_month is percentage points per month (30 days)
    days_per_point = 30.0 / growth_rate_per_month
    return remaining * days_per_point


def _capacity_recommendation(
    resource_type: str,
    days_to_80: Optional[float],
    days_to_90: Optional[float],
    days_to_100: Optional[float],
) -> str:
    """Generate a capacity planning recommendation."""
    if days_to_100 is not None and days_to_100 <= 7:
        return (
            f"CRITICAL: {resource_type} exhaustion in {days_to_100:.0f} days. "
            f"Immediate capacity expansion required."
        )
    if days_to_90 is not None and days_to_90 <= 14:
        return (
            f"HIGH: {resource_type} reaching 90% in {days_to_90:.0f} days. "
            f"Plan capacity expansion within 1 week."
        )
    if days_to_80 is not None and days_to_80 <= 30:
        return (
            f"MEDIUM: {resource_type} reaching 80% in {days_to_80:.0f} days. "
            f"Schedule capacity review within 2 weeks."
        )
    if days_to_80 is None and days_to_90 is None and days_to_100 is None:
        return f"OK: {resource_type} usage is stable or decreasing. No action required."
    return (
        f"LOW: {resource_type} growth is within acceptable range. "
        f"Continue monitoring."
    )


def _sla_trend(burn_rate_per_day: float, error_budget_total: float) -> str:
    """Determine SLA trend based on burn rate relative to sustainable rate.

    A sustainable burn rate consumes 100% of the error budget over 30 days.
    """
    if error_budget_total <= 0:
        return "degrading"
    # Sustainable daily burn = budget / 30 days
    sustainable_rate = error_budget_total / 30.0
    ratio = burn_rate_per_day / sustainable_rate if sustainable_rate > 0 else float("inf")
    if ratio <= 0.5:
        return "improving"
    elif ratio <= 1.5:
        return "stable"
    else:
        return "degrading"


def _monthly_sla_probability(
    error_budget_remaining_pct: float,
    burn_rate_per_day: float,
    error_budget_total: float,
    days_remaining_in_period: float = 30.0,
) -> float:
    """Estimate probability of meeting SLA for the period.

    Simple model: if the projected remaining budget at end of period is > 0,
    we consider the SLA met. We add uncertainty via a sigmoid function centered
    at the break-even point.
    """
    if error_budget_total <= 0:
        return 0.0
    # Remaining budget in absolute terms
    remaining_abs = error_budget_remaining_pct / 100.0 * error_budget_total
    # Projected budget at end of period
    projected_remaining = remaining_abs - (burn_rate_per_day * days_remaining_in_period)

    # Normalize: how many days of budget surplus/deficit
    if burn_rate_per_day > 0:
        surplus_days = projected_remaining / burn_rate_per_day
    else:
        # No burn = certain to meet SLA
        return 1.0

    # Sigmoid to convert surplus_days to probability
    # Centered at 0 (break-even), steepness factor of 0.3
    steepness = 0.3
    try:
        prob = 1.0 / (1.0 + math.exp(-steepness * surplus_days))
    except OverflowError:
        prob = 0.0 if surplus_days < 0 else 1.0

    return round(max(0.0, min(1.0, prob)), 6)


# ---------------------------------------------------------------------------
# Engine (original, preserved intact)
# ---------------------------------------------------------------------------


class PredictiveEngine:
    """Predict future failures from degradation trends, MTBF data,
    capacity growth, and SLA error budgets.

    Uses linear extrapolation for resource exhaustion, exponential CDF /
    Poisson model for failure probability, and sigmoid-based SLA projection.
    No external dependencies beyond the Python standard library.
    """

    def __init__(self, graph: InfraGraph | None = None) -> None:
        self._graph = graph

    # ------------------------------------------------------------------
    # Original graph-based API (fully preserved)
    # ------------------------------------------------------------------

    def predict(self, horizon_days: int = 90) -> PredictiveReport:
        """Run predictive analysis over the given horizon.

        Parameters
        ----------
        horizon_days:
            How far ahead to look (default 90 days).

        Returns
        -------
        PredictiveReport
            Resource exhaustion predictions and failure probability forecasts.
        """
        if self._graph is None:
            return PredictiveReport(summary="No graph provided.")

        exhaustion_predictions = self._predict_resource_exhaustion(horizon_days)
        failure_forecasts = self._predict_failure_probabilities()
        maintenance = _suggest_maintenance_window(exhaustion_predictions)
        summary = self._build_summary(exhaustion_predictions, failure_forecasts)

        return PredictiveReport(
            exhaustion_predictions=exhaustion_predictions,
            failure_forecasts=failure_forecasts,
            recommended_maintenance_window=maintenance,
            summary=summary,
        )

    # ------------------------------------------------------------------
    # New standalone API — Failure Prediction
    # ------------------------------------------------------------------

    def predict_failure(
        self,
        component_id: str,
        mtbf_hours: float,
        mttr_hours: float,
    ) -> ComponentReliability:
        """Predict failure probability for a single component.

        Uses exponential/Poisson model to compute:
        - P(failure in 30 days)
        - P(failure in 90 days)
        - Expected days to next failure (= MTBF in days)
        - Risk classification
        """
        if mtbf_hours <= 0:
            return ComponentReliability(
                component_id=component_id,
                mtbf_hours=max(mtbf_hours, 0.0),
                mttr_hours=max(mttr_hours, 0.0),
                failure_probability_30d=1.0,
                failure_probability_90d=1.0,
                expected_days_to_failure=0.0,
                risk_level="critical",
            )

        # Failure rate: lambda = 1 / MTBF (events per hour)
        # Convert to events per day
        lambda_per_day = 24.0 / mtbf_hours

        p_30d = _poisson_at_least_one(lambda_per_day, 30.0)
        p_90d = _poisson_at_least_one(lambda_per_day, 90.0)
        expected_days = mtbf_hours / 24.0

        risk = _classify_risk(p_30d)

        return ComponentReliability(
            component_id=component_id,
            mtbf_hours=mtbf_hours,
            mttr_hours=max(mttr_hours, 0.0),
            failure_probability_30d=round(p_30d, 6),
            failure_probability_90d=round(p_90d, 6),
            expected_days_to_failure=round(expected_days, 2),
            risk_level=risk,
        )

    def predict_failures(
        self,
        components: list[dict[str, float | str]],
    ) -> list[ComponentReliability]:
        """Predict failures for multiple components.

        Parameters
        ----------
        components:
            List of dicts with keys: component_id, mtbf_hours, mttr_hours

        Returns
        -------
        list[ComponentReliability]
            Sorted by risk (highest failure_probability_30d first).
        """
        results: list[ComponentReliability] = []
        for comp in components:
            cid = str(comp.get("component_id", "unknown"))
            mtbf = float(comp.get("mtbf_hours", 0.0))
            mttr = float(comp.get("mttr_hours", 0.0))
            results.append(self.predict_failure(cid, mtbf, mttr))

        # Sort by 30d failure probability descending (highest risk first)
        results.sort(key=lambda r: r.failure_probability_30d, reverse=True)
        return results

    def compound_failure_probability(
        self,
        reliabilities: list[ComponentReliability],
        horizon_days: int = 30,
    ) -> float:
        """Compute probability of at least one component failing within the horizon.

        Parameters
        ----------
        reliabilities:
            ComponentReliability objects from predict_failure/predict_failures.
        horizon_days:
            Time horizon in days (30 or 90 supported directly).

        Returns
        -------
        float
            P(at least one failure in horizon_days).
        """
        probs: list[float] = []
        for r in reliabilities:
            if horizon_days <= 30:
                probs.append(r.failure_probability_30d)
            else:
                probs.append(r.failure_probability_90d)
        return round(_compound_failure_probability(probs), 6)

    # ------------------------------------------------------------------
    # New standalone API — Capacity Forecast
    # ------------------------------------------------------------------

    def forecast_capacity(
        self,
        resource_type: str,
        current_percent: float,
        growth_rate_per_month: float,
    ) -> CapacityForecast:
        """Forecast resource capacity exhaustion.

        Parameters
        ----------
        resource_type:
            Type of resource (cpu, memory, storage, network).
        current_percent:
            Current usage as a percentage (0-100+).
        growth_rate_per_month:
            Growth rate in percentage points per month.

        Returns
        -------
        CapacityForecast
            Forecast with days to threshold alerts and recommendation.
        """
        days_80 = _days_to_threshold(current_percent, growth_rate_per_month, 80.0)
        days_90 = _days_to_threshold(current_percent, growth_rate_per_month, 90.0)
        days_100 = _days_to_threshold(current_percent, growth_rate_per_month, 100.0)

        recommendation = _capacity_recommendation(
            resource_type, days_80, days_90, days_100,
        )

        return CapacityForecast(
            resource_type=resource_type,
            current_usage_percent=round(current_percent, 2),
            growth_rate_per_month=round(growth_rate_per_month, 4),
            days_to_80_percent=round(days_80, 2) if days_80 is not None else None,
            days_to_90_percent=round(days_90, 2) if days_90 is not None else None,
            days_to_100_percent=round(days_100, 2) if days_100 is not None else None,
            recommendation=recommendation,
        )

    # ------------------------------------------------------------------
    # New standalone API — SLA Forecast
    # ------------------------------------------------------------------

    def forecast_sla(
        self,
        slo_target: float,
        current_availability: float,
        error_budget_remaining: float,
        burn_rate_per_day: float,
    ) -> SLAForecast:
        """Forecast SLA achievement probability.

        Parameters
        ----------
        slo_target:
            SLO target as a percentage (e.g. 99.9).
        current_availability:
            Current availability as a percentage (e.g. 99.95).
        error_budget_remaining:
            Remaining error budget as a percentage of total (0-100).
        burn_rate_per_day:
            Error budget consumption rate in absolute units per day.
            The total error budget = 100.0 - slo_target (e.g. 0.1 for 99.9% SLO).

        Returns
        -------
        SLAForecast
            SLA forecast with achievement probabilities and trend.
        """
        # Total error budget in availability percentage points
        error_budget_total = 100.0 - slo_target

        # Days until budget exhaustion
        if burn_rate_per_day > 0 and error_budget_total > 0:
            remaining_abs = (error_budget_remaining / 100.0) * error_budget_total
            if remaining_abs > 0:
                days_to_exhaustion: Optional[float] = remaining_abs / burn_rate_per_day
            else:
                days_to_exhaustion = 0.0
        else:
            days_to_exhaustion = None

        # Trend determination
        trend = _sla_trend(burn_rate_per_day, error_budget_total)

        # Monthly SLA probability (assume 30 days remaining)
        monthly_prob = _monthly_sla_probability(
            error_budget_remaining, burn_rate_per_day, error_budget_total, 30.0,
        )

        # Quarterly SLA probability (assume 90 days remaining)
        quarterly_prob = _monthly_sla_probability(
            error_budget_remaining, burn_rate_per_day, error_budget_total, 90.0,
        )

        return SLAForecast(
            slo_target=slo_target,
            current_availability=round(current_availability, 4),
            error_budget_remaining_percent=round(error_budget_remaining, 2),
            days_until_budget_exhaustion=(
                round(days_to_exhaustion, 2) if days_to_exhaustion is not None else None
            ),
            monthly_sla_probability=monthly_prob,
            quarterly_sla_probability=quarterly_prob,
            trend=trend,
        )

    # ------------------------------------------------------------------
    # New standalone API — Risk Timeline
    # ------------------------------------------------------------------

    def generate_risk_timeline(
        self,
        predictions: list[ComponentReliability] | None = None,
        forecasts: list[CapacityForecast] | None = None,
        sla_forecasts: list[SLAForecast] | None = None,
    ) -> list[RiskTimelineEvent]:
        """Generate a time-ordered list of predicted risk events.

        Merges failure predictions, capacity forecasts, and SLA projections
        into a single timeline sorted by days_from_now (soonest first).
        """
        events: list[RiskTimelineEvent] = []

        # Failure prediction events
        if predictions:
            for pred in predictions:
                if pred.expected_days_to_failure < float("inf"):
                    events.append(RiskTimelineEvent(
                        days_from_now=pred.expected_days_to_failure,
                        event_type="failure",
                        severity=pred.risk_level,
                        description=(
                            f"Expected failure of {pred.component_id} "
                            f"(MTBF={pred.mtbf_hours:.0f}h, "
                            f"P30d={pred.failure_probability_30d:.1%})"
                        ),
                        component_or_resource=pred.component_id,
                    ))

        # Capacity forecast events (one event per threshold reached)
        if forecasts:
            for fc in forecasts:
                thresholds = [
                    (fc.days_to_80_percent, "80%", "medium"),
                    (fc.days_to_90_percent, "90%", "high"),
                    (fc.days_to_100_percent, "100%", "critical"),
                ]
                for days, label, severity in thresholds:
                    if days is not None and days > 0:
                        events.append(RiskTimelineEvent(
                            days_from_now=days,
                            event_type="capacity",
                            severity=severity,
                            description=(
                                f"{fc.resource_type} reaching {label} "
                                f"(current: {fc.current_usage_percent:.1f}%, "
                                f"growth: {fc.growth_rate_per_month:.1f}%/mo)"
                            ),
                            component_or_resource=fc.resource_type,
                        ))
                    elif days is not None and days == 0.0:
                        events.append(RiskTimelineEvent(
                            days_from_now=0.0,
                            event_type="capacity",
                            severity=severity,
                            description=(
                                f"{fc.resource_type} already at or above {label} "
                                f"(current: {fc.current_usage_percent:.1f}%)"
                            ),
                            component_or_resource=fc.resource_type,
                        ))

        # SLA forecast events
        if sla_forecasts:
            for sla in sla_forecasts:
                if sla.days_until_budget_exhaustion is not None:
                    if sla.days_until_budget_exhaustion <= 7:
                        severity = "critical"
                    elif sla.days_until_budget_exhaustion <= 30:
                        severity = "high"
                    else:
                        severity = "medium"
                    events.append(RiskTimelineEvent(
                        days_from_now=sla.days_until_budget_exhaustion,
                        event_type="sla",
                        severity=severity,
                        description=(
                            f"SLO {sla.slo_target}% error budget exhaustion "
                            f"(remaining: {sla.error_budget_remaining_percent:.1f}%, "
                            f"trend: {sla.trend})"
                        ),
                        component_or_resource=f"SLO-{sla.slo_target}",
                    ))

        # Sort by days_from_now ascending (soonest first)
        events.sort(key=lambda e: e.days_from_now)
        return events

    # -- private helpers (original, preserved) -------------------------

    def _predict_resource_exhaustion(
        self,
        horizon_days: int,
    ) -> list[ResourceExhaustionPrediction]:
        predictions: list[ResourceExhaustionPrediction] = []
        now = datetime.now(timezone.utc)

        for comp in self._graph.components.values():
            degradation = comp.operational_profile.degradation

            # Memory leak
            if degradation.memory_leak_mb_per_hour > 0:
                total_mb = comp.capacity.max_memory_mb or 8192.0
                used_mb = comp.metrics.memory_used_mb
                current_pct = (used_mb / total_mb * 100.0) if total_mb > 0 else 0.0
                rate_pct_per_hour = (
                    degradation.memory_leak_mb_per_hour / total_mb * 100.0
                ) if total_mb > 0 else 0.0

                days = _days_to_exhaust(current_pct, rate_pct_per_hour)
                if days <= horizon_days:
                    exhaust_date = now + timedelta(days=days) if days != float("inf") else now
                    predictions.append(ResourceExhaustionPrediction(
                        component_id=comp.id,
                        resource="memory",
                        current_usage_percent=round(current_pct, 2),
                        growth_rate_per_hour=round(rate_pct_per_hour, 4),
                        days_to_exhaustion=round(days, 2),
                        exhaustion_date=exhaust_date.isoformat(),
                        recommended_action=_recommend_action("memory", days),
                    ))

            # Disk fill
            if degradation.disk_fill_gb_per_hour > 0:
                total_gb = comp.capacity.max_disk_gb or 100.0
                used_gb = comp.metrics.disk_used_gb
                current_pct = (used_gb / total_gb * 100.0) if total_gb > 0 else 0.0
                rate_pct_per_hour = (
                    degradation.disk_fill_gb_per_hour / total_gb * 100.0
                ) if total_gb > 0 else 0.0

                days = _days_to_exhaust(current_pct, rate_pct_per_hour)
                if days <= horizon_days:
                    exhaust_date = now + timedelta(days=days) if days != float("inf") else now
                    predictions.append(ResourceExhaustionPrediction(
                        component_id=comp.id,
                        resource="disk",
                        current_usage_percent=round(current_pct, 2),
                        growth_rate_per_hour=round(rate_pct_per_hour, 4),
                        days_to_exhaustion=round(days, 2),
                        exhaustion_date=exhaust_date.isoformat(),
                        recommended_action=_recommend_action("disk", days),
                    ))

            # Connection leak
            if degradation.connection_leak_per_hour > 0:
                max_conns = comp.capacity.max_connections or 1000
                current_conns = comp.metrics.network_connections
                current_pct = (current_conns / max_conns * 100.0) if max_conns > 0 else 0.0
                rate_pct_per_hour = (
                    degradation.connection_leak_per_hour / max_conns * 100.0
                ) if max_conns > 0 else 0.0

                days = _days_to_exhaust(current_pct, rate_pct_per_hour)
                if days <= horizon_days:
                    exhaust_date = now + timedelta(days=days) if days != float("inf") else now
                    predictions.append(ResourceExhaustionPrediction(
                        component_id=comp.id,
                        resource="connections",
                        current_usage_percent=round(current_pct, 2),
                        growth_rate_per_hour=round(rate_pct_per_hour, 4),
                        days_to_exhaustion=round(days, 2),
                        exhaustion_date=exhaust_date.isoformat(),
                        recommended_action=_recommend_action("connections", days),
                    ))

        # Sort by urgency (soonest exhaustion first)
        predictions.sort(key=lambda p: p.days_to_exhaustion)
        return predictions

    def _predict_failure_probabilities(self) -> list[FailureProbabilityForecast]:
        forecasts: list[FailureProbabilityForecast] = []
        for comp in self._graph.components.values():
            mtbf = comp.operational_profile.mtbf_hours
            if mtbf <= 0:
                mtbf = _DEFAULT_MTBF.get(comp.type.value, 2160.0)

            # Effective MTBF accounting for replicas (parallel redundancy)
            # System MTBF for n identical parallel components is roughly
            # MTBF * (1 + 1/2 + 1/3 + ... + 1/n) — harmonic series factor.
            # For simplicity we use the exact formula for single failure:
            # P(all fail in t) = P(single fail)^n
            replicas = max(comp.replicas, 1)

            p_7d_single = _failure_probability(7 * 24, mtbf)
            p_30d_single = _failure_probability(30 * 24, mtbf)
            p_90d_single = _failure_probability(90 * 24, mtbf)

            # All replicas must fail for the component to be unavailable
            p_7d = p_7d_single ** replicas
            p_30d = p_30d_single ** replicas
            p_90d = p_90d_single ** replicas

            forecasts.append(FailureProbabilityForecast(
                component_id=comp.id,
                mtbf_hours=mtbf,
                probability_7d=round(p_7d, 6),
                probability_30d=round(p_30d, 6),
                probability_90d=round(p_90d, 6),
            ))

        # Sort by highest 30d probability first
        forecasts.sort(key=lambda f: f.probability_30d, reverse=True)
        return forecasts

    def _build_summary(
        self,
        exhaustions: list[ResourceExhaustionPrediction],
        forecasts: list[FailureProbabilityForecast],
    ) -> str:
        lines: list[str] = []

        if not exhaustions and not forecasts:
            return "No components to analyze."

        # Resource exhaustion summary
        urgent = [p for p in exhaustions if p.days_to_exhaustion <= 7]
        warning = [p for p in exhaustions if 7 < p.days_to_exhaustion <= 30]
        if urgent:
            lines.append(
                f"CRITICAL: {len(urgent)} resource(s) predicted to exhaust within 7 days."
            )
        if warning:
            lines.append(
                f"WARNING: {len(warning)} resource(s) predicted to exhaust within 30 days."
            )
        if not urgent and not warning:
            lines.append("No resource exhaustion predicted within 30 days.")

        # Failure probability summary
        high_risk = [f for f in forecasts if f.probability_30d > 0.5]
        if high_risk:
            names = ", ".join(f.component_id for f in high_risk[:3])
            lines.append(
                f"High failure risk (>50% in 30d): {names}"
            )
        else:
            lines.append("All components have <50% failure probability in 30 days.")

        return " ".join(lines)
