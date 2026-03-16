"""Predictive failure engine for FaultRay.

Predicts future failures from degradation trends using linear extrapolation
and exponential failure probability (CDF).  Uses ONLY the Python standard
library -- no numpy, scipy, or scikit-learn.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

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
# Result dataclasses
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
# Helpers
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
# Engine
# ---------------------------------------------------------------------------


class PredictiveEngine:
    """Predict future failures from degradation trends and MTBF data.

    Uses linear extrapolation for resource exhaustion and exponential CDF
    for failure probability.  No external dependencies.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

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

    # -- private helpers ---------------------------------------------------

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
