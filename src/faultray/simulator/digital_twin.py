# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Digital Twin / Live Shadow - continuous shadow simulation predicting failures.

Ingests real-time metrics (or graph defaults) and uses linear trend
extrapolation to forecast resource saturation within a configurable
prediction horizon.  Produces warnings with recommended actions when
predicted metrics cross critical thresholds.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


@dataclass
class PredictionWarning:
    """A single predictive warning about an upcoming resource saturation."""

    component_id: str
    metric: str
    current_value: float
    predicted_value: float
    threshold: float
    time_to_threshold_minutes: float
    severity: str  # "critical", "warning", "info"
    recommended_action: str


@dataclass
class TwinSnapshot:
    """Point-in-time prediction snapshot."""

    timestamp: float
    component_states: dict[str, dict[str, float]]  # {comp_id: {metric: value}}
    warnings: list[PredictionWarning]
    predicted_availability: float


@dataclass
class DigitalTwinReport:
    """Aggregated report from one or more prediction runs."""

    snapshots: list[TwinSnapshot]
    total_warnings: int
    critical_warnings: int
    prediction_horizon_minutes: int
    auto_scale_suggestions: list[dict]


class DigitalTwin:
    """Live shadow simulation predicting failures up to *horizon* minutes ahead.

    Usage::

        twin = DigitalTwin(graph, prediction_horizon_minutes=60)
        twin.ingest_metrics({"web-1": {"cpu_percent": 55, "memory_percent": 40}})
        twin.ingest_metrics({"web-1": {"cpu_percent": 60, "memory_percent": 42}})
        snapshot = twin.predict()
    """

    # Configurable thresholds
    CPU_CRITICAL_THRESHOLD = 90.0
    MEMORY_WARNING_THRESHOLD = 85.0
    DISK_CRITICAL_THRESHOLD = 90.0

    def __init__(
        self,
        graph: InfraGraph,
        prediction_horizon_minutes: int = 60,
    ) -> None:
        self.graph = graph
        self.horizon = prediction_horizon_minutes
        self._history: list[dict] = []
        self._snapshots: list[TwinSnapshot] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest_metrics(self, metrics: dict[str, dict[str, float]]) -> None:
        """Feed real-time metrics from Prometheus / CloudWatch / etc.

        Args:
            metrics: Mapping of *component_id* -> metric dict.
                     Metric dict may contain ``cpu_percent``,
                     ``memory_percent``, ``disk_percent``, etc.
        """
        self._history.append({"timestamp": time.time(), "metrics": metrics})
        # Keep last 60 data points to limit memory
        if len(self._history) > 60:
            self._history = self._history[-60:]

    def predict(self) -> TwinSnapshot:
        """Predict system state for the next *horizon* minutes.

        Returns:
            A :class:`TwinSnapshot` with predicted component states,
            any warnings, and an overall predicted availability.
        """
        warnings: list[PredictionWarning] = []
        states: dict[str, dict[str, float]] = {}

        for comp_id in self.graph.components:
            current = self._get_current_metrics(comp_id)
            trend = self._compute_trend(comp_id)
            predicted = self._extrapolate(current, trend, self.horizon)
            states[comp_id] = predicted

            # --- CPU saturation check ---
            if predicted.get("cpu_percent", 0) > self.CPU_CRITICAL_THRESHOLD:
                warnings.append(PredictionWarning(
                    component_id=comp_id,
                    metric="cpu_percent",
                    current_value=current.get("cpu_percent", 0),
                    predicted_value=predicted["cpu_percent"],
                    threshold=self.CPU_CRITICAL_THRESHOLD,
                    time_to_threshold_minutes=self._time_to_threshold(
                        comp_id, "cpu_percent", self.CPU_CRITICAL_THRESHOLD,
                    ),
                    severity="critical",
                    recommended_action=f"Scale {comp_id} before CPU saturation",
                ))

            # --- Memory check ---
            if predicted.get("memory_percent", 0) > self.MEMORY_WARNING_THRESHOLD:
                warnings.append(PredictionWarning(
                    component_id=comp_id,
                    metric="memory_percent",
                    current_value=current.get("memory_percent", 0),
                    predicted_value=predicted["memory_percent"],
                    threshold=self.MEMORY_WARNING_THRESHOLD,
                    time_to_threshold_minutes=self._time_to_threshold(
                        comp_id, "memory_percent", self.MEMORY_WARNING_THRESHOLD,
                    ),
                    severity="warning",
                    recommended_action=f"Check memory usage on {comp_id}",
                ))

            # --- Disk check ---
            if predicted.get("disk_percent", 0) > self.DISK_CRITICAL_THRESHOLD:
                warnings.append(PredictionWarning(
                    component_id=comp_id,
                    metric="disk_percent",
                    current_value=current.get("disk_percent", 0),
                    predicted_value=predicted["disk_percent"],
                    threshold=self.DISK_CRITICAL_THRESHOLD,
                    time_to_threshold_minutes=self._time_to_threshold(
                        comp_id, "disk_percent", self.DISK_CRITICAL_THRESHOLD,
                    ),
                    severity="critical",
                    recommended_action=f"Expand disk on {comp_id}",
                ))

        snapshot = TwinSnapshot(
            timestamp=time.time(),
            component_states=states,
            warnings=warnings,
            predicted_availability=self._predict_availability(warnings),
        )
        self._snapshots.append(snapshot)
        return snapshot

    def report(self) -> DigitalTwinReport:
        """Build an aggregated report from all snapshots collected so far."""
        total_warnings = sum(len(s.warnings) for s in self._snapshots)
        critical_warnings = sum(
            sum(1 for w in s.warnings if w.severity == "critical")
            for s in self._snapshots
        )

        auto_scale: list[dict] = []
        seen: set[str] = set()
        for snap in self._snapshots:
            for w in snap.warnings:
                if w.severity == "critical" and w.component_id not in seen:
                    comp = self.graph.get_component(w.component_id)
                    if comp and comp.autoscaling.enabled:
                        auto_scale.append({
                            "component_id": w.component_id,
                            "metric": w.metric,
                            "suggestion": f"Pre-scale {w.component_id} by "
                                          f"{comp.autoscaling.scale_up_step} replicas",
                        })
                        seen.add(w.component_id)

        return DigitalTwinReport(
            snapshots=list(self._snapshots),
            total_warnings=total_warnings,
            critical_warnings=critical_warnings,
            prediction_horizon_minutes=self.horizon,
            auto_scale_suggestions=auto_scale,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_current_metrics(self, comp_id: str) -> dict[str, float]:
        """Return the most recent metrics for *comp_id*.

        Falls back to the component's own ``ResourceMetrics`` when no
        external metrics have been ingested.
        """
        if self._history:
            latest = self._history[-1]["metrics"].get(comp_id, {})
            if latest:
                return dict(latest)

        comp = self.graph.get_component(comp_id)
        if comp:
            return {
                "cpu_percent": comp.metrics.cpu_percent,
                "memory_percent": comp.metrics.memory_percent,
                "disk_percent": comp.metrics.disk_percent,
            }
        return {}

    def _compute_trend(self, comp_id: str) -> dict[str, float]:
        """Linear regression (first→last) on historical metrics.

        Returns per-minute change rate for each metric key.
        """
        if len(self._history) < 2:
            return {}

        first_entry = self._history[0]["metrics"].get(comp_id, {})
        last_entry = self._history[-1]["metrics"].get(comp_id, {})
        dt_minutes = (
            self._history[-1]["timestamp"] - self._history[0]["timestamp"]
        ) / 60.0

        if dt_minutes <= 0:
            return {}

        trend: dict[str, float] = {}
        for key in last_entry:
            if key in first_entry:
                trend[key] = (last_entry[key] - first_entry[key]) / dt_minutes
        return trend

    def _extrapolate(
        self,
        current: dict[str, float],
        trend: dict[str, float],
        minutes: int,
    ) -> dict[str, float]:
        """Extrapolate *current* by *trend* over *minutes*.

        Clamps the result to [0, 100] since metrics are percentages.
        """
        result = dict(current)
        for key, rate in trend.items():
            if key in result:
                result[key] = max(0.0, min(100.0, result[key] + rate * minutes))
        return result

    def _time_to_threshold(
        self,
        comp_id: str,
        metric: str,
        threshold: float,
    ) -> float:
        """Estimate how many minutes until *metric* hits *threshold*.

        Returns ``float('inf')`` if the trend is non-positive (the metric
        is stable or decreasing).
        """
        current = self._get_current_metrics(comp_id).get(metric, 0)
        trend_rate = self._compute_trend(comp_id).get(metric, 0)
        if trend_rate <= 0:
            return float("inf")
        return max(0.0, (threshold - current) / trend_rate)

    def _predict_availability(self, warnings: list[PredictionWarning]) -> float:
        """Rough availability estimate based on warning count."""
        critical = sum(1 for w in warnings if w.severity == "critical")
        if critical > 2:
            return 95.0
        if critical > 0:
            return 99.0
        return 99.99
