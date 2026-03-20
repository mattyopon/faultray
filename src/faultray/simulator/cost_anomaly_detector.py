# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Infrastructure cost anomaly detector using statistical methods.

Detects anomalous cost spikes in infrastructure spending by analyzing cost
time-series data with z-score, IQR, and moving average methods.  Classifies
anomaly root causes (auto-scaling events, resource leaks, pricing changes,
over-provisioning) and generates cost optimization recommendations.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AnomalyType(str, Enum):
    """Classification of detected cost anomalies."""

    SPIKE = "spike"
    DROP = "drop"
    TREND_CHANGE = "trend_change"
    SEASONAL_DEVIATION = "seasonal_deviation"
    RESOURCE_LEAK = "resource_leak"
    PRICING_CHANGE = "pricing_change"
    OVER_PROVISIONING = "over_provisioning"
    ORPHANED_RESOURCE = "orphaned_resource"


class AnomalySeverity(str, Enum):
    """Severity level assigned to a cost anomaly."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DetectionMethod(str, Enum):
    """Statistical method used to flag an anomaly."""

    Z_SCORE = "z_score"
    IQR = "iqr"
    MOVING_AVERAGE = "moving_average"
    PERCENTAGE_CHANGE = "percentage_change"
    FORECAST_DEVIATION = "forecast_deviation"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class CostDataPoint(BaseModel):
    """A single cost observation."""

    timestamp: str
    cost_usd: float
    component_id: str
    category: str = "general"


class CostAnomaly(BaseModel):
    """A detected cost anomaly with diagnosis information."""

    anomaly_type: AnomalyType
    severity: AnomalySeverity
    detection_method: DetectionMethod
    component_id: str
    expected_cost: float
    actual_cost: float
    deviation_percent: float
    description: str = ""
    recommendation: str = ""


class CostBaseline(BaseModel):
    """Statistical baseline for a single component's costs."""

    component_id: str
    avg_daily_cost: float
    std_dev: float
    p95_cost: float
    min_cost: float
    max_cost: float


class CostOptimization(BaseModel):
    """A concrete optimisation opportunity."""

    component_id: str
    current_monthly_cost: float
    optimized_monthly_cost: float
    savings_percent: float
    recommendation: str = ""
    confidence: float = 0.0


class CostAnomalyReport(BaseModel):
    """Aggregated anomaly detection report."""

    anomalies: list[CostAnomaly] = Field(default_factory=list)
    baselines: list[CostBaseline] = Field(default_factory=list)
    total_spend: float = 0.0
    anomaly_spend: float = 0.0
    optimization_potential_usd: float = 0.0
    optimizations: list[CostOptimization] = Field(default_factory=list)
    timestamp: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_Z_THRESHOLD = 2.0
_DEFAULT_MA_WINDOW = 3
_IQR_MULTIPLIER = 1.5


def _severity_from_deviation(deviation: float) -> AnomalySeverity:
    """Map absolute deviation percentage to a severity level."""
    abs_dev = abs(deviation)
    if abs_dev >= 200.0:
        return AnomalySeverity.CRITICAL
    if abs_dev >= 100.0:
        return AnomalySeverity.HIGH
    if abs_dev >= 50.0:
        return AnomalySeverity.MEDIUM
    if abs_dev >= 20.0:
        return AnomalySeverity.LOW
    return AnomalySeverity.INFO


def _compute_deviation(actual: float, expected: float) -> float:
    """Return percentage deviation of *actual* from *expected*."""
    if expected == 0.0:
        return 0.0 if actual == 0.0 else 100.0
    return ((actual - expected) / expected) * 100.0


def _quantile(sorted_vals: list[float], q: float) -> float:
    """Compute quantile *q* (0-1) from an already-sorted list."""
    if not sorted_vals:
        return 0.0
    idx = q * (len(sorted_vals) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac


# ---------------------------------------------------------------------------
# Base monthly cost lookup
# ---------------------------------------------------------------------------

_BASE_MONTHLY_COST: dict[ComponentType, float] = {
    ComponentType.DATABASE: 500.0,
    ComponentType.APP_SERVER: 200.0,
    ComponentType.CACHE: 150.0,
    ComponentType.LOAD_BALANCER: 100.0,
    ComponentType.WEB_SERVER: 180.0,
    ComponentType.QUEUE: 120.0,
    ComponentType.STORAGE: 80.0,
    ComponentType.DNS: 50.0,
    ComponentType.EXTERNAL_API: 0.0,
    ComponentType.CUSTOM: 100.0,
}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class CostAnomalyDetectorEngine:
    """Stateless engine that analyses cost data for anomalies and optimisations."""

    # -- public API ---------------------------------------------------------

    def detect_anomalies(
        self,
        graph: InfraGraph,
        cost_data: list[CostDataPoint],
        sensitivity: float = 1.0,
    ) -> CostAnomalyReport:
        """Run full anomaly detection pipeline.

        Parameters
        ----------
        graph:
            The current infrastructure graph for context.
        cost_data:
            Time-ordered list of cost data points.
        sensitivity:
            Multiplier applied to detection thresholds.  Lower values
            produce *more* alerts; higher values produce fewer.  The
            default ``1.0`` uses standard thresholds.
        """
        if not cost_data:
            return CostAnomalyReport(
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        threshold = _DEFAULT_Z_THRESHOLD * sensitivity

        baselines = self.compute_baselines(cost_data)

        anomalies: list[CostAnomaly] = []
        anomalies.extend(self.detect_by_zscore(cost_data, threshold=threshold))
        anomalies.extend(self.detect_by_iqr(cost_data))
        anomalies.extend(
            self.detect_by_moving_average(
                cost_data, window=_DEFAULT_MA_WINDOW
            )
        )

        # Deduplicate by (component_id, anomaly_type)
        seen: set[tuple[str, str]] = set()
        unique: list[CostAnomaly] = []
        for a in anomalies:
            key = (a.component_id, a.anomaly_type.value)
            if key not in seen:
                seen.add(key)
                # Classify root cause (may update anomaly_type)
                root = self.classify_anomaly_root_cause(a, graph)
                a = a.model_copy(update={"description": root})
                unique.append(a)
        anomalies = unique

        optimizations = self.identify_optimizations(graph, baselines)

        total_spend = sum(dp.cost_usd for dp in cost_data)
        anomaly_cids = {a.component_id for a in anomalies}
        anomaly_spend = sum(
            dp.cost_usd for dp in cost_data if dp.component_id in anomaly_cids
        )
        opt_savings = sum(
            o.current_monthly_cost - o.optimized_monthly_cost
            for o in optimizations
        )

        return CostAnomalyReport(
            anomalies=anomalies,
            baselines=baselines,
            total_spend=round(total_spend, 2),
            anomaly_spend=round(anomaly_spend, 2),
            optimization_potential_usd=round(opt_savings, 2),
            optimizations=optimizations,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # -- baselines ----------------------------------------------------------

    def compute_baselines(
        self, cost_data: list[CostDataPoint]
    ) -> list[CostBaseline]:
        """Compute per-component statistical baselines."""
        grouped: dict[str, list[float]] = {}
        for dp in cost_data:
            grouped.setdefault(dp.component_id, []).append(dp.cost_usd)

        baselines: list[CostBaseline] = []
        for cid, costs in grouped.items():
            if len(costs) < 2:
                avg = costs[0] if costs else 0.0
                baselines.append(
                    CostBaseline(
                        component_id=cid,
                        avg_daily_cost=round(avg, 2),
                        std_dev=0.0,
                        p95_cost=round(avg, 2),
                        min_cost=round(avg, 2),
                        max_cost=round(avg, 2),
                    )
                )
                continue

            avg = statistics.mean(costs)
            sd = statistics.stdev(costs)
            sorted_c = sorted(costs)
            p95 = _quantile(sorted_c, 0.95)
            baselines.append(
                CostBaseline(
                    component_id=cid,
                    avg_daily_cost=round(avg, 2),
                    std_dev=round(sd, 2),
                    p95_cost=round(p95, 2),
                    min_cost=round(min(costs), 2),
                    max_cost=round(max(costs), 2),
                )
            )
        return baselines

    # -- z-score detection --------------------------------------------------

    def detect_by_zscore(
        self,
        cost_data: list[CostDataPoint],
        threshold: float = _DEFAULT_Z_THRESHOLD,
    ) -> list[CostAnomaly]:
        """Flag data points whose cost deviates beyond *threshold* z-scores."""
        grouped: dict[str, list[CostDataPoint]] = {}
        for dp in cost_data:
            grouped.setdefault(dp.component_id, []).append(dp)

        anomalies: list[CostAnomaly] = []
        for cid, points in grouped.items():
            costs = [p.cost_usd for p in points]
            if len(costs) < 2:
                continue
            avg = statistics.mean(costs)
            sd = statistics.stdev(costs)
            if sd == 0.0:
                continue
            for pt in points:
                z = (pt.cost_usd - avg) / sd
                if abs(z) > threshold:
                    dev = _compute_deviation(pt.cost_usd, avg)
                    sev = _severity_from_deviation(dev)
                    atype = AnomalyType.SPIKE if z > 0 else AnomalyType.DROP
                    anomalies.append(
                        CostAnomaly(
                            anomaly_type=atype,
                            severity=sev,
                            detection_method=DetectionMethod.Z_SCORE,
                            component_id=cid,
                            expected_cost=round(avg, 2),
                            actual_cost=round(pt.cost_usd, 2),
                            deviation_percent=round(dev, 2),
                            description=f"Z-score {z:.2f} exceeds threshold {threshold}",
                            recommendation=(
                                "Investigate cost spike"
                                if z > 0
                                else "Verify expected cost reduction"
                            ),
                        )
                    )
        return anomalies

    # -- IQR detection ------------------------------------------------------

    def detect_by_iqr(
        self, cost_data: list[CostDataPoint]
    ) -> list[CostAnomaly]:
        """Flag outliers using the inter-quartile range method."""
        grouped: dict[str, list[CostDataPoint]] = {}
        for dp in cost_data:
            grouped.setdefault(dp.component_id, []).append(dp)

        anomalies: list[CostAnomaly] = []
        for cid, points in grouped.items():
            costs = sorted(p.cost_usd for p in points)
            if len(costs) < 4:
                continue
            q1 = _quantile(costs, 0.25)
            q3 = _quantile(costs, 0.75)
            iqr = q3 - q1
            if iqr == 0.0:
                continue
            lower = q1 - _IQR_MULTIPLIER * iqr
            upper = q3 + _IQR_MULTIPLIER * iqr
            median_cost = _quantile(costs, 0.5)

            for pt in points:
                if pt.cost_usd < lower or pt.cost_usd > upper:
                    dev = _compute_deviation(pt.cost_usd, median_cost)
                    sev = _severity_from_deviation(dev)
                    atype = (
                        AnomalyType.SPIKE
                        if pt.cost_usd > upper
                        else AnomalyType.DROP
                    )
                    anomalies.append(
                        CostAnomaly(
                            anomaly_type=atype,
                            severity=sev,
                            detection_method=DetectionMethod.IQR,
                            component_id=cid,
                            expected_cost=round(median_cost, 2),
                            actual_cost=round(pt.cost_usd, 2),
                            deviation_percent=round(dev, 2),
                            description=(
                                f"Cost outside IQR bounds "
                                f"[{lower:.2f}, {upper:.2f}]"
                            ),
                            recommendation="Review resource allocation",
                        )
                    )
        return anomalies

    # -- moving average detection -------------------------------------------

    def detect_by_moving_average(
        self,
        cost_data: list[CostDataPoint],
        window: int = _DEFAULT_MA_WINDOW,
    ) -> list[CostAnomaly]:
        """Compare each point against its trailing moving average."""
        if window < 1:
            window = 1

        grouped: dict[str, list[CostDataPoint]] = {}
        for dp in cost_data:
            grouped.setdefault(dp.component_id, []).append(dp)

        anomalies: list[CostAnomaly] = []
        for cid, points in grouped.items():
            if len(points) <= window:
                continue
            costs = [p.cost_usd for p in points]
            for i in range(window, len(costs)):
                ma = statistics.mean(costs[i - window : i])
                if ma == 0.0:
                    continue
                dev = _compute_deviation(costs[i], ma)
                if abs(dev) > 50.0:
                    sev = _severity_from_deviation(dev)
                    atype = (
                        AnomalyType.SPIKE if dev > 0 else AnomalyType.DROP
                    )
                    anomalies.append(
                        CostAnomaly(
                            anomaly_type=atype,
                            severity=sev,
                            detection_method=DetectionMethod.MOVING_AVERAGE,
                            component_id=cid,
                            expected_cost=round(ma, 2),
                            actual_cost=round(costs[i], 2),
                            deviation_percent=round(dev, 2),
                            description=(
                                f"Cost deviates {dev:.1f}% from "
                                f"{window}-period moving average"
                            ),
                            recommendation="Check for sudden workload changes",
                        )
                    )
        return anomalies

    # -- optimizations ------------------------------------------------------

    def identify_optimizations(
        self,
        graph: InfraGraph,
        baselines: list[CostBaseline],
    ) -> list[CostOptimization]:
        """Suggest cost optimisations based on the graph and baselines."""
        baseline_map: dict[str, CostBaseline] = {
            b.component_id: b for b in baselines
        }
        optimizations: list[CostOptimization] = []

        for cid, comp in graph.components.items():
            base = _BASE_MONTHLY_COST.get(comp.type, 100.0)
            monthly = base * comp.replicas

            # Over-provisioned replicas
            if comp.replicas > 2:
                dependents = graph.get_dependents(cid)
                needed = max(2, len(dependents))
                if comp.replicas > needed:
                    opt_monthly = base * needed
                    savings = _compute_deviation(opt_monthly, monthly)
                    optimizations.append(
                        CostOptimization(
                            component_id=cid,
                            current_monthly_cost=round(monthly, 2),
                            optimized_monthly_cost=round(opt_monthly, 2),
                            savings_percent=round(abs(savings), 2),
                            recommendation=(
                                f"Reduce replicas from {comp.replicas} "
                                f"to {needed}"
                            ),
                            confidence=0.8,
                        )
                    )

            # Under-utilised component
            util = comp.utilization()
            if util < 10.0 and monthly > 0 and comp.type != ComponentType.EXTERNAL_API:
                opt_monthly = monthly * 0.5
                savings_pct = 50.0
                optimizations.append(
                    CostOptimization(
                        component_id=cid,
                        current_monthly_cost=round(monthly, 2),
                        optimized_monthly_cost=round(opt_monthly, 2),
                        savings_percent=savings_pct,
                        recommendation="Right-size or consolidate under-utilised resource",
                        confidence=0.6,
                    )
                )

            # Enable autoscaling suggestion
            if (
                not comp.autoscaling.enabled
                and comp.replicas >= 2
                and comp.type
                in (
                    ComponentType.APP_SERVER,
                    ComponentType.WEB_SERVER,
                    ComponentType.CACHE,
                )
            ):
                opt_monthly = monthly * 0.7
                optimizations.append(
                    CostOptimization(
                        component_id=cid,
                        current_monthly_cost=round(monthly, 2),
                        optimized_monthly_cost=round(opt_monthly, 2),
                        savings_percent=30.0,
                        recommendation="Enable autoscaling to reduce idle capacity cost",
                        confidence=0.7,
                    )
                )

            # High baseline std_dev suggests variable workload – spot / preemptible
            bl = baseline_map.get(cid)
            if bl and bl.std_dev > 0 and bl.avg_daily_cost > 0:
                cv = bl.std_dev / bl.avg_daily_cost  # coefficient of variation
                if cv > 0.5 and comp.type in (
                    ComponentType.APP_SERVER,
                    ComponentType.WEB_SERVER,
                ):
                    opt_monthly = monthly * 0.6
                    optimizations.append(
                        CostOptimization(
                            component_id=cid,
                            current_monthly_cost=round(monthly, 2),
                            optimized_monthly_cost=round(opt_monthly, 2),
                            savings_percent=40.0,
                            recommendation=(
                                "High cost variance detected — consider "
                                "spot/preemptible instances for burst capacity"
                            ),
                            confidence=0.5,
                        )
                    )

            # Orphaned resource: no dependents and no dependencies
            deps = graph.get_dependencies(cid)
            dependents = graph.get_dependents(cid)
            if not deps and not dependents and len(graph.components) > 1:
                optimizations.append(
                    CostOptimization(
                        component_id=cid,
                        current_monthly_cost=round(monthly, 2),
                        optimized_monthly_cost=0.0,
                        savings_percent=100.0,
                        recommendation="Orphaned resource with no connections — consider decommissioning",
                        confidence=0.9,
                    )
                )

        return optimizations

    # -- root cause classification ------------------------------------------

    def classify_anomaly_root_cause(
        self, anomaly: CostAnomaly, graph: InfraGraph
    ) -> str:
        """Return a human-readable root-cause description for an anomaly."""
        comp = graph.get_component(anomaly.component_id)
        if comp is None:
            return f"Unknown component {anomaly.component_id}"

        # Autoscaling event
        if comp.autoscaling.enabled and anomaly.anomaly_type == AnomalyType.SPIKE:
            return (
                f"Auto-scaling event on '{comp.name}': cost spike likely "
                f"caused by replica scale-up (max_replicas={comp.autoscaling.max_replicas})"
            )

        # Over-provisioning
        if comp.replicas > 3 and anomaly.deviation_percent > 50.0:
            return (
                f"Over-provisioned '{comp.name}' with {comp.replicas} replicas "
                f"contributing to elevated cost"
            )

        # Resource leak indicator — steady upward trend
        if anomaly.anomaly_type == AnomalyType.SPIKE and anomaly.deviation_percent > 100.0:
            op = comp.operational_profile
            if (
                op.degradation.memory_leak_mb_per_hour > 0
                or op.degradation.connection_leak_per_hour > 0
                or op.degradation.disk_fill_gb_per_hour > 0
            ):
                return (
                    f"Possible resource leak in '{comp.name}' — "
                    f"degradation config shows active leak parameters"
                )

        # Pricing change — external APIs
        if comp.type == ComponentType.EXTERNAL_API:
            return (
                f"Cost anomaly on external API '{comp.name}' — "
                f"may indicate upstream pricing change"
            )

        # Orphaned resource — no connections
        deps = graph.get_dependencies(anomaly.component_id)
        dependents = graph.get_dependents(anomaly.component_id)
        if not deps and not dependents and len(graph.components) > 1:
            return (
                f"Orphaned resource '{comp.name}' — not connected to "
                f"any other component"
            )

        # Generic classification based on anomaly type
        labels: dict[AnomalyType, str] = {
            AnomalyType.SPIKE: f"Unexpected cost spike on '{comp.name}'",
            AnomalyType.DROP: f"Unexpected cost drop on '{comp.name}'",
            AnomalyType.TREND_CHANGE: f"Cost trend change for '{comp.name}'",
            AnomalyType.SEASONAL_DEVIATION: f"Seasonal deviation for '{comp.name}'",
            AnomalyType.RESOURCE_LEAK: f"Resource leak suspected for '{comp.name}'",
            AnomalyType.PRICING_CHANGE: f"Pricing change for '{comp.name}'",
            AnomalyType.OVER_PROVISIONING: f"Over-provisioned '{comp.name}'",
            AnomalyType.ORPHANED_RESOURCE: f"Orphaned resource '{comp.name}'",
        }
        return labels.get(
            anomaly.anomaly_type,
            f"Cost anomaly on '{comp.name}'",
        )
