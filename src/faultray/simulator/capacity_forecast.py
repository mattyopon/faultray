# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Capacity forecasting engine for FaultRay.

Predicts future resource needs based on current utilization trends
using simple linear regression when historical data points are available,
or estimates from current utilization otherwise.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ForecastHorizon(Enum):
    """Planning horizon for capacity forecasts."""

    DAYS_7 = 7
    DAYS_30 = 30
    DAYS_90 = 90
    DAYS_180 = 180
    DAYS_365 = 365


class GrowthModel(Enum):
    """Growth model used for trend estimation."""

    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    LOGARITHMIC = "logarithmic"
    SEASONAL = "seasonal"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CapacityDataPoint:
    """A single utilization measurement at a point in time."""

    timestamp: datetime
    utilization: float
    replicas: int


@dataclass
class CapacityForecast:
    """Forecast result for a single component."""

    component_id: str
    component_name: str
    current_utilization: float
    predicted_utilization: float
    days_until_capacity: float
    growth_model: GrowthModel
    growth_rate: float
    recommended_action: str
    confidence: float  # 0.0 – 1.0


@dataclass
class ForecastReport:
    """Aggregated forecast report across all components."""

    forecasts: list[CapacityForecast]
    components_at_risk: list[str]
    total_predicted_cost_increase: float
    planning_horizon_days: int
    recommendations: list[str]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Utilization (%) at which a component is considered at full capacity.
_CAPACITY_THRESHOLD = 100.0

# Utilization (%) above which a component is considered "at risk".
_AT_RISK_THRESHOLD = 75.0

# Default daily growth rate when no historical data is available (0.1%/day).
_DEFAULT_DAILY_GROWTH = 0.001

# Per-replica monthly cost estimate in abstract cost units.
_PER_REPLICA_MONTHLY_COST = 100.0


# ---------------------------------------------------------------------------
# Forecasting engine
# ---------------------------------------------------------------------------


class CapacityForecaster:
    """Predicts future resource needs based on utilization trends."""

    def __init__(self) -> None:
        # component_id -> list of data points (ordered by time)
        self._history: dict[str, list[CapacityDataPoint]] = {}

    # -- public API ----------------------------------------------------------

    def add_data_point(self, component_id: str, data: CapacityDataPoint) -> None:
        """Record a historical utilization measurement for *component_id*."""
        self._history.setdefault(component_id, []).append(data)
        # Keep sorted by timestamp.
        self._history[component_id].sort(key=lambda dp: dp.timestamp)

    def forecast_component(
        self,
        graph: InfraGraph,
        component_id: str,
        horizon: ForecastHorizon,
    ) -> CapacityForecast:
        """Produce a capacity forecast for a single component."""
        comp = graph.get_component(component_id)
        if comp is None:
            raise KeyError(f"Component '{component_id}' not found in graph")

        current_util = comp.utilization()
        data_points = self._history.get(component_id, [])
        horizon_days = horizon.value

        if len(data_points) >= 2:
            growth_rate, confidence = self._linear_regression(data_points)
            growth_model = GrowthModel.LINEAR
        else:
            # No trend data – fall back to a conservative default.
            growth_rate = _DEFAULT_DAILY_GROWTH * current_util if current_util > 0 else 0.0
            confidence = 0.3
            growth_model = GrowthModel.LINEAR

        predicted_util = current_util + growth_rate * horizon_days
        days_until_cap = self._days_until_capacity(current_util, growth_rate)
        action = self._recommend_action(current_util, predicted_util, days_until_cap, horizon_days)

        return CapacityForecast(
            component_id=comp.id,
            component_name=comp.name,
            current_utilization=current_util,
            predicted_utilization=predicted_util,
            days_until_capacity=days_until_cap,
            growth_model=growth_model,
            growth_rate=growth_rate,
            recommended_action=action,
            confidence=min(1.0, max(0.0, confidence)),
        )

    def forecast(
        self,
        graph: InfraGraph,
        horizon: ForecastHorizon = ForecastHorizon.DAYS_30,
    ) -> ForecastReport:
        """Produce a forecast report for every component in *graph*."""
        forecasts: list[CapacityForecast] = []
        components_at_risk: list[str] = []
        recommendations: list[str] = []
        cost_increase = 0.0

        for comp_id in graph.components:
            fc = self.forecast_component(graph, comp_id, horizon)
            forecasts.append(fc)

            if fc.predicted_utilization >= _AT_RISK_THRESHOLD:
                components_at_risk.append(fc.component_id)

            # Estimate cost increase from required additional replicas.
            comp = graph.get_component(comp_id)
            if comp is not None and fc.predicted_utilization > _AT_RISK_THRESHOLD:
                extra_replicas = max(
                    0,
                    math.ceil(fc.predicted_utilization / _AT_RISK_THRESHOLD) - 1,
                )
                cost_increase += extra_replicas * _PER_REPLICA_MONTHLY_COST

            if fc.recommended_action and fc.recommended_action != "No action needed":
                recommendations.append(
                    f"[{fc.component_id}] {fc.recommended_action}"
                )

        return ForecastReport(
            forecasts=forecasts,
            components_at_risk=components_at_risk,
            total_predicted_cost_increase=cost_increase,
            planning_horizon_days=horizon.value,
            recommendations=recommendations,
        )

    # -- private helpers -----------------------------------------------------

    @staticmethod
    def _linear_regression(
        data_points: list[CapacityDataPoint],
    ) -> tuple[float, float]:
        """Return ``(slope_per_day, confidence)`` from data points.

        Uses ordinary least-squares on (elapsed_days, utilization).
        *confidence* is the R-squared value clamped to [0, 1].
        """
        if len(data_points) < 2:
            return 0.0, 0.0

        t0 = data_points[0].timestamp
        xs: list[float] = []
        ys: list[float] = []
        for dp in data_points:
            elapsed = (dp.timestamp - t0).total_seconds() / 86400.0
            xs.append(elapsed)
            ys.append(dp.utilization)

        n = len(xs)
        sum_x = sum(xs)
        sum_y = sum(ys)
        sum_xx = sum(x * x for x in xs)
        sum_xy = sum(x * y for x, y in zip(xs, ys))

        denom = n * sum_xx - sum_x * sum_x
        if denom == 0:
            return 0.0, 0.0

        slope = (n * sum_xy - sum_x * sum_y) / denom
        intercept = (sum_y - slope * sum_x) / n

        # R-squared
        y_mean = sum_y / n
        ss_tot = sum((y - y_mean) ** 2 for y in ys)
        ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))

        if ss_tot == 0:
            r_squared = 1.0  # perfect constant – no variance
        else:
            r_squared = 1.0 - ss_res / ss_tot

        return slope, max(0.0, min(1.0, r_squared))

    @staticmethod
    def _days_until_capacity(current_util: float, daily_growth: float) -> float:
        """Return how many days until utilization reaches *_CAPACITY_THRESHOLD*.

        Returns ``float('inf')`` when growth is zero or negative.
        Returns ``0.0`` when already at or above capacity.
        """
        if current_util >= _CAPACITY_THRESHOLD:
            return 0.0
        if daily_growth <= 0:
            return float("inf")
        return (_CAPACITY_THRESHOLD - current_util) / daily_growth

    @staticmethod
    def _recommend_action(
        current_util: float,
        predicted_util: float,
        days_until_cap: float,
        horizon_days: int,
    ) -> str:
        """Generate a human-readable recommendation."""
        if current_util >= _CAPACITY_THRESHOLD:
            return "CRITICAL: Already at capacity – scale immediately"
        if days_until_cap <= 7:
            return "URGENT: Scale within 7 days to avoid capacity breach"
        if days_until_cap <= 30:
            return "WARNING: Plan scaling within 30 days"
        if predicted_util >= _AT_RISK_THRESHOLD:
            return "PLAN: Predicted to exceed 75% utilization – consider scaling"
        return "No action needed"
