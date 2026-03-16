"""Capacity planning & saturation predictor.

Predicts when infrastructure components will hit capacity limits
and recommends scaling actions based on current utilization trends,
growth patterns, and seasonal factors.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SaturationMetric(str, Enum):
    """Resource metric that can reach saturation."""

    CPU = "cpu"
    MEMORY = "memory"
    DISK = "disk"
    NETWORK = "network"
    CONNECTIONS = "connections"
    IOPS = "iops"
    BANDWIDTH = "bandwidth"
    QUEUE_DEPTH = "queue_depth"


class GrowthModel(str, Enum):
    """Mathematical model describing resource growth over time."""

    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    LOGARITHMIC = "logarithmic"
    POLYNOMIAL = "polynomial"
    SEASONAL = "seasonal"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class SaturationPrediction(BaseModel):
    """Prediction of when a specific metric will hit 100% on a component."""

    component_id: str
    metric: SaturationMetric
    current_value: float = Field(ge=0.0, le=100.0)
    predicted_saturation_hours: float
    growth_model: GrowthModel
    confidence: float = Field(ge=0.0, le=1.0)
    trend_slope: float
    recommended_action: str
    cost_of_inaction_per_hour: float


class ScalingStep(BaseModel):
    """A single scaling step within a capacity plan."""

    trigger_metric: SaturationMetric
    trigger_threshold: float
    action: str  # scale_up / scale_out / optimize / migrate
    new_capacity: dict[str, float]
    cost_delta: float
    implementation_time_hours: float


class CapacityPlan(BaseModel):
    """Full capacity plan for a component."""

    component_id: str
    current_capacity: dict[str, float]
    recommended_capacity: dict[str, float]
    scaling_steps: list[ScalingStep]
    estimated_monthly_cost_delta: float
    risk_if_no_action: str  # critical / high / medium / low


class BottleneckResult(BaseModel):
    """A component identified as a potential bottleneck."""

    component_id: str
    component_name: str
    metric: SaturationMetric
    current_value: float
    hours_to_saturation: float
    severity: str  # critical / high / medium / low


class TrafficSpikeResult(BaseModel):
    """Result of simulating a traffic spike across the infrastructure."""

    multiplier: float
    total_components: int
    overloaded_components: list[str]
    surviving_components: list[str]
    first_failure_component: str | None
    cascade_risk: str  # critical / high / medium / low / none
    recommended_pre_scaling: dict[str, int]
    timestamp: datetime


class RightSizeRecommendation(BaseModel):
    """Recommendation for right-sizing a component."""

    component_id: str
    component_name: str
    status: str  # over_provisioned / under_provisioned / right_sized
    current_utilization: float
    target_utilization: float
    recommended_replicas: int
    current_replicas: int
    monthly_savings: float
    risk_delta: str  # lower / same / higher


class CostForecast(BaseModel):
    """Projected infrastructure costs over time."""

    months: int
    growth_rate: float
    monthly_costs: list[float]
    total_cost: float
    cost_trend: str  # increasing / stable / decreasing
    scaling_events_count: int
    peak_monthly_cost: float


class SeasonalLoadResult(BaseModel):
    """Result of simulating a seasonal load pattern."""

    peak_multiplier: float
    duration_hours: float
    components_needing_scaling: list[str]
    max_required_replicas: dict[str, int]
    estimated_extra_cost: float
    survival_probability: float
    recommendations: list[str]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _metric_value(comp: Component, metric: SaturationMetric) -> float:
    """Extract current value (0-100) for a given metric from a component."""
    if metric == SaturationMetric.CPU:
        return comp.metrics.cpu_percent
    if metric == SaturationMetric.MEMORY:
        return comp.metrics.memory_percent
    if metric == SaturationMetric.DISK:
        return comp.metrics.disk_percent
    if metric == SaturationMetric.NETWORK:
        return min(
            comp.metrics.network_connections
            / max(comp.capacity.max_connections, 1)
            * 100,
            100.0,
        )
    if metric == SaturationMetric.CONNECTIONS:
        return min(
            comp.metrics.network_connections
            / max(comp.capacity.max_connections, 1)
            * 100,
            100.0,
        )
    # iops, bandwidth, queue_depth - derive from available metrics
    if metric == SaturationMetric.IOPS:
        return comp.metrics.disk_percent * 0.8
    if metric == SaturationMetric.BANDWIDTH:
        return min(
            comp.metrics.network_connections
            / max(comp.capacity.max_connections, 1)
            * 100
            * 0.7,
            100.0,
        )
    # metric == SaturationMetric.QUEUE_DEPTH (last remaining member)
    return comp.metrics.cpu_percent * 0.5


def _project_value(
    current: float,
    hours: float,
    slope: float,
    model: GrowthModel,
) -> float:
    """Project a metric value at *hours* in the future."""
    if hours <= 0:
        return current
    if model == GrowthModel.LINEAR:
        return current + slope * hours
    if model == GrowthModel.EXPONENTIAL:
        return current * math.exp(slope * hours / 100.0)
    if model == GrowthModel.LOGARITHMIC:
        return current + slope * math.log1p(hours)
    if model == GrowthModel.POLYNOMIAL:
        return current + slope * (hours ** 1.5) / 100.0
    # model == GrowthModel.SEASONAL (last remaining member)
    # Sinusoidal overlay on linear growth
    base = current + slope * hours * 0.5
    seasonal = slope * 10.0 * math.sin(2 * math.pi * hours / 168.0)  # weekly
    return base + seasonal


def _hours_to_saturation(
    current: float,
    slope: float,
    model: GrowthModel,
    max_hours: float = 8760.0,
) -> float:
    """Estimate hours until metric reaches 100%.

    Returns *max_hours* if saturation is not predicted.
    """
    if current >= 100.0:
        return 0.0
    if slope <= 0:
        return max_hours

    # Analytical solutions where possible
    if model == GrowthModel.LINEAR:
        return min((100.0 - current) / slope, max_hours)
    if model == GrowthModel.EXPONENTIAL:
        if current <= 0:
            return max_hours
        ratio = 100.0 / current
        return min(math.log(ratio) * 100.0 / slope, max_hours)

    # Numerical search for other models
    lo, hi = 0.0, max_hours
    for _ in range(64):
        mid = (lo + hi) / 2.0
        if _project_value(current, mid, slope, model) >= 100.0:
            hi = mid
        else:
            lo = mid
    return hi if _project_value(current, hi, slope, model) < 100.0 else hi


def _slope_for_component(comp: Component, metric: SaturationMetric) -> float:
    """Derive a synthetic trend slope from the component's configuration."""
    base = 0.0
    if metric == SaturationMetric.CPU:
        base = comp.metrics.cpu_percent * 0.005
    elif metric == SaturationMetric.MEMORY:
        base = comp.metrics.memory_percent * 0.004
        if comp.operational_profile.degradation.memory_leak_mb_per_hour > 0:
            leak = comp.operational_profile.degradation.memory_leak_mb_per_hour
            total = max(comp.capacity.max_memory_mb, 1)
            base += (leak / total) * 100.0
    elif metric == SaturationMetric.DISK:
        base = comp.metrics.disk_percent * 0.003
        if comp.operational_profile.degradation.disk_fill_gb_per_hour > 0:
            fill = comp.operational_profile.degradation.disk_fill_gb_per_hour
            total = max(comp.capacity.max_disk_gb, 1)
            base += (fill / total) * 100.0
    elif metric in (SaturationMetric.NETWORK, SaturationMetric.CONNECTIONS):
        conn_ratio = comp.metrics.network_connections / max(
            comp.capacity.max_connections, 1
        )
        base = conn_ratio * 0.01
        if comp.operational_profile.degradation.connection_leak_per_hour > 0:
            base += (
                comp.operational_profile.degradation.connection_leak_per_hour
                / max(comp.capacity.max_connections, 1)
            )
    elif metric == SaturationMetric.IOPS:
        base = comp.metrics.disk_percent * 0.004
    elif metric == SaturationMetric.BANDWIDTH:
        base = (
            comp.metrics.network_connections
            / max(comp.capacity.max_connections, 1)
            * 0.008
        )
    elif metric == SaturationMetric.QUEUE_DEPTH:
        base = comp.metrics.cpu_percent * 0.003
    return max(base, 0.0)


def _best_growth_model(current: float, slope: float) -> GrowthModel:
    """Select the growth model that best fits current conditions."""
    if slope <= 0:
        return GrowthModel.LINEAR
    if current > 70:
        return GrowthModel.EXPONENTIAL
    if current < 20:
        return GrowthModel.LOGARITHMIC
    return GrowthModel.LINEAR


def _confidence_for_prediction(
    current: float, slope: float, hours: float
) -> float:
    """Compute a confidence score for a saturation prediction."""
    if slope <= 0:
        return 0.3
    # Closer to saturation => more confident
    remaining = max(100.0 - current, 1.0)
    urgency = min(slope * hours / remaining, 1.0)
    base = 0.5 + 0.4 * urgency
    # Penalise very long horizons
    if hours > 720:
        base *= 0.8
    return max(0.0, min(1.0, base))


def _recommend_action(
    metric: SaturationMetric, hours: float, current: float
) -> str:
    """Choose a recommended action string."""
    if current >= 90:
        return "scale_up"
    if hours < 24:
        return "scale_up"
    if hours < 168:
        return "scale_out"
    if current < 30:
        return "optimize"
    return "scale_out"


def _cost_of_inaction(current: float, slope: float) -> float:
    """Estimate cost per hour of doing nothing."""
    if slope <= 0:
        return 0.0
    risk_factor = current / 100.0
    return round(slope * risk_factor * 50.0, 2)


def _risk_label(hours: float, current: float) -> str:
    """Map hours-to-saturation + current value to a risk label."""
    if current >= 90 or hours < 24:
        return "critical"
    if current >= 75 or hours < 168:
        return "high"
    if current >= 50 or hours < 720:
        return "medium"
    return "low"


def _severity_label(hours: float, current: float) -> str:
    """Map to a severity label for bottleneck reporting."""
    return _risk_label(hours, current)


def _current_capacity_dict(comp: Component) -> dict[str, float]:
    """Build current capacity dictionary."""
    return {
        "cpu_percent": comp.metrics.cpu_percent,
        "memory_percent": comp.metrics.memory_percent,
        "disk_percent": comp.metrics.disk_percent,
        "connections": float(comp.metrics.network_connections),
        "max_connections": float(comp.capacity.max_connections),
        "max_rps": float(comp.capacity.max_rps),
        "replicas": float(comp.replicas),
    }


def _recommended_capacity_dict(
    comp: Component, predictions: list[SaturationPrediction]
) -> dict[str, float]:
    """Compute recommended capacity based on saturation predictions."""
    rec = _current_capacity_dict(comp)
    need_scale = False
    for pred in predictions:
        if pred.predicted_saturation_hours < 720:
            need_scale = True
            break
    if need_scale:
        headroom = 1.5
        rec["max_connections"] = rec["max_connections"] * headroom
        rec["max_rps"] = rec["max_rps"] * headroom
        rec["replicas"] = float(max(comp.replicas + 1, math.ceil(comp.replicas * 1.5)))
    return rec


def _monthly_cost_delta(comp: Component, rec: dict[str, float]) -> float:
    """Estimate monthly cost delta from scaling."""
    current_replicas = comp.replicas
    new_replicas = rec.get("replicas", current_replicas)
    delta_replicas = new_replicas - current_replicas
    if delta_replicas <= 0:
        return 0.0
    hourly = comp.cost_profile.hourly_infra_cost or 0.10
    return round(delta_replicas * hourly * 730, 2)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class CapacityPlanningEngine:
    """Stateless capacity planning & saturation predictor."""

    # Metrics to evaluate per component
    _DEFAULT_METRICS = [
        SaturationMetric.CPU,
        SaturationMetric.MEMORY,
        SaturationMetric.DISK,
        SaturationMetric.CONNECTIONS,
    ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict_saturation(
        self,
        graph: InfraGraph,
        component_id: str,
        hours_ahead: float = 720.0,
    ) -> list[SaturationPrediction]:
        """Predict when each metric on *component_id* will reach 100%."""
        comp = graph.get_component(component_id)
        if comp is None:
            return []
        return self._predict_component(comp, hours_ahead)

    def generate_capacity_plan(
        self,
        graph: InfraGraph,
        component_id: str,
    ) -> CapacityPlan:
        """Generate a full capacity plan for *component_id*."""
        comp = graph.get_component(component_id)
        if comp is None:
            return CapacityPlan(
                component_id=component_id,
                current_capacity={},
                recommended_capacity={},
                scaling_steps=[],
                estimated_monthly_cost_delta=0.0,
                risk_if_no_action="low",
            )
        predictions = self._predict_component(comp, 720.0)
        current = _current_capacity_dict(comp)
        recommended = _recommended_capacity_dict(comp, predictions)
        steps = self._build_scaling_steps(comp, predictions)
        cost_delta = _monthly_cost_delta(comp, recommended)
        risk = self._overall_risk(predictions)
        return CapacityPlan(
            component_id=component_id,
            current_capacity=current,
            recommended_capacity=recommended,
            scaling_steps=steps,
            estimated_monthly_cost_delta=cost_delta,
            risk_if_no_action=risk,
        )

    def find_bottlenecks(
        self,
        graph: InfraGraph,
    ) -> list[BottleneckResult]:
        """Identify components closest to capacity limits."""
        results: list[BottleneckResult] = []
        for comp in graph.components.values():
            worst_metric = SaturationMetric.CPU
            worst_hours = float("inf")
            worst_value = 0.0
            for metric in self._DEFAULT_METRICS:
                val = _metric_value(comp, metric)
                slope = _slope_for_component(comp, metric)
                model = _best_growth_model(val, slope)
                hrs = _hours_to_saturation(val, slope, model)
                if hrs < worst_hours:
                    worst_hours = hrs
                    worst_metric = metric
                    worst_value = val
            results.append(
                BottleneckResult(
                    component_id=comp.id,
                    component_name=comp.name,
                    metric=worst_metric,
                    current_value=worst_value,
                    hours_to_saturation=worst_hours,
                    severity=_severity_label(worst_hours, worst_value),
                )
            )
        results.sort(key=lambda b: b.hours_to_saturation)
        return results

    def simulate_traffic_spike(
        self,
        graph: InfraGraph,
        multiplier: float,
    ) -> TrafficSpikeResult:
        """Simulate a traffic multiplier (e.g. 2x, 5x, 10x)."""
        overloaded: list[str] = []
        surviving: list[str] = []
        first_fail: str | None = None
        first_fail_headroom = float("inf")
        recommended_scaling: dict[str, int] = {}

        for comp in graph.components.values():
            cpu = comp.metrics.cpu_percent * multiplier
            mem = comp.metrics.memory_percent * multiplier
            conn = comp.metrics.network_connections * multiplier
            conn_cap = comp.capacity.max_connections

            is_overloaded = (
                cpu > 100 or mem > 100 or conn > conn_cap
            )
            if is_overloaded:
                overloaded.append(comp.id)
                headroom = 100.0 - max(
                    comp.metrics.cpu_percent,
                    comp.metrics.memory_percent,
                )
                if headroom < first_fail_headroom:
                    first_fail_headroom = headroom
                    first_fail = comp.id
                needed = math.ceil(multiplier)
                recommended_scaling[comp.id] = max(
                    needed, comp.replicas + 1
                )
            else:
                surviving.append(comp.id)

        total = len(graph.components)
        if not total:
            cascade = "none"
        elif len(overloaded) == 0:
            cascade = "none"
        elif len(overloaded) / total >= 0.5:
            cascade = "critical"
        elif len(overloaded) / total >= 0.3:
            cascade = "high"
        elif len(overloaded) / total >= 0.1:
            cascade = "medium"
        else:
            cascade = "low"

        return TrafficSpikeResult(
            multiplier=multiplier,
            total_components=total,
            overloaded_components=overloaded,
            surviving_components=surviving,
            first_failure_component=first_fail,
            cascade_risk=cascade,
            recommended_pre_scaling=recommended_scaling,
            timestamp=datetime.now(timezone.utc),
        )

    def recommend_right_sizing(
        self,
        graph: InfraGraph,
    ) -> list[RightSizeRecommendation]:
        """Identify over-provisioned and under-provisioned components."""
        recommendations: list[RightSizeRecommendation] = []
        target = 60.0  # ideal utilization
        for comp in graph.components.values():
            util = comp.utilization()
            if util < 20 and comp.replicas > 1:
                status = "over_provisioned"
                rec_replicas = max(1, comp.replicas // 2)
                savings = (comp.replicas - rec_replicas) * (
                    comp.cost_profile.hourly_infra_cost or 0.10
                ) * 730
                risk_delta = "higher"
            elif util > 80:
                status = "under_provisioned"
                rec_replicas = math.ceil(comp.replicas * (util / target))
                savings = 0.0
                risk_delta = "lower"
            else:
                status = "right_sized"
                rec_replicas = comp.replicas
                savings = 0.0
                risk_delta = "same"
            recommendations.append(
                RightSizeRecommendation(
                    component_id=comp.id,
                    component_name=comp.name,
                    status=status,
                    current_utilization=round(util, 1),
                    target_utilization=target,
                    recommended_replicas=rec_replicas,
                    current_replicas=comp.replicas,
                    monthly_savings=round(savings, 2),
                    risk_delta=risk_delta,
                )
            )
        return recommendations

    def forecast_cost(
        self,
        graph: InfraGraph,
        growth_rate: float,
        months: int,
    ) -> CostForecast:
        """Project infrastructure costs over *months* at *growth_rate* %/month."""
        base_monthly = 0.0
        for comp in graph.components.values():
            hourly = comp.cost_profile.hourly_infra_cost or 0.10
            base_monthly += hourly * 730 * comp.replicas

        monthly_costs: list[float] = []
        scaling_events = 0
        for m in range(months):
            factor = (1.0 + growth_rate / 100.0) ** m
            cost = base_monthly * factor
            # Add scaling event cost when crossing thresholds
            if factor > 1.5 and m > 0:
                scaling_events += 1
                cost *= 1.1  # overhead from scaling
            monthly_costs.append(round(cost, 2))

        total = sum(monthly_costs)
        peak = max(monthly_costs) if monthly_costs else 0.0
        if months > 1 and monthly_costs[-1] > monthly_costs[0] * 1.05:
            trend = "increasing"
        elif months > 1 and monthly_costs[-1] < monthly_costs[0] * 0.95:
            trend = "decreasing"
        else:
            trend = "stable"

        return CostForecast(
            months=months,
            growth_rate=growth_rate,
            monthly_costs=monthly_costs,
            total_cost=round(total, 2),
            cost_trend=trend,
            scaling_events_count=scaling_events,
            peak_monthly_cost=round(peak, 2),
        )

    def simulate_seasonal_load(
        self,
        graph: InfraGraph,
        peak_multiplier: float,
        duration_hours: float,
    ) -> SeasonalLoadResult:
        """Simulate a seasonal load spike (Black Friday, etc.)."""
        needing_scale: list[str] = []
        max_replicas: dict[str, int] = {}
        extra_cost = 0.0
        failures = 0
        total = len(graph.components)
        recs: list[str] = []

        for comp in graph.components.values():
            peak_cpu = comp.metrics.cpu_percent * peak_multiplier
            peak_mem = comp.metrics.memory_percent * peak_multiplier
            peak_conn = comp.metrics.network_connections * peak_multiplier

            needs_scaling = (
                peak_cpu > 80 or peak_mem > 80 or peak_conn > comp.capacity.max_connections
            )
            if needs_scaling:
                needing_scale.append(comp.id)
                needed = max(
                    math.ceil(peak_cpu / 60) * comp.replicas,
                    math.ceil(peak_mem / 60) * comp.replicas,
                    comp.replicas + 1,
                )
                max_replicas[comp.id] = needed
                hourly = comp.cost_profile.hourly_infra_cost or 0.10
                extra = (needed - comp.replicas) * hourly * duration_hours
                extra_cost += extra

                if peak_cpu > 100 or peak_mem > 100:
                    failures += 1

                if comp.autoscaling.enabled:
                    if needed > comp.autoscaling.max_replicas:
                        recs.append(
                            f"Increase max_replicas for {comp.id} to {needed}"
                        )
                else:
                    recs.append(
                        f"Enable autoscaling for {comp.id} with max_replicas={needed}"
                    )
            else:
                max_replicas[comp.id] = comp.replicas

        if total == 0:
            survival = 1.0
        elif failures == 0:
            survival = 1.0
        else:
            survival = max(0.0, 1.0 - failures / total)

        if not recs and needing_scale:
            recs.append("Pre-scale components before peak traffic window")
        if not recs and not needing_scale:
            recs.append("Current capacity is sufficient for the expected peak")

        return SeasonalLoadResult(
            peak_multiplier=peak_multiplier,
            duration_hours=duration_hours,
            components_needing_scaling=needing_scale,
            max_required_replicas=max_replicas,
            estimated_extra_cost=round(extra_cost, 2),
            survival_probability=round(survival, 2),
            recommendations=recs,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _predict_component(
        self,
        comp: Component,
        hours_ahead: float,
    ) -> list[SaturationPrediction]:
        """Generate saturation predictions for all metrics on a component."""
        predictions: list[SaturationPrediction] = []
        for metric in self._DEFAULT_METRICS:
            val = _metric_value(comp, metric)
            slope = _slope_for_component(comp, metric)
            model = _best_growth_model(val, slope)
            hrs = _hours_to_saturation(val, slope, model)
            conf = _confidence_for_prediction(val, slope, hours_ahead)
            action = _recommend_action(metric, hrs, val)
            cost = _cost_of_inaction(val, slope)
            predictions.append(
                SaturationPrediction(
                    component_id=comp.id,
                    metric=metric,
                    current_value=min(val, 100.0),
                    predicted_saturation_hours=round(hrs, 2),
                    growth_model=model,
                    confidence=round(conf, 4),
                    trend_slope=round(slope, 6),
                    recommended_action=action,
                    cost_of_inaction_per_hour=cost,
                )
            )
        return predictions

    def _build_scaling_steps(
        self,
        comp: Component,
        predictions: list[SaturationPrediction],
    ) -> list[ScalingStep]:
        """Build ordered scaling steps from predictions."""
        steps: list[ScalingStep] = []
        for pred in predictions:
            if pred.predicted_saturation_hours >= 8760:
                continue
            threshold = 80.0
            if pred.current_value >= 80:
                threshold = pred.current_value
            action = pred.recommended_action
            current_cap = _current_capacity_dict(comp)
            new_cap = dict(current_cap)
            if action in ("scale_up", "scale_out"):
                new_cap["replicas"] = float(comp.replicas + 1)
                new_cap["max_rps"] = current_cap["max_rps"] * 1.5
            hourly = comp.cost_profile.hourly_infra_cost or 0.10
            cost = hourly * 730
            impl_time = 1.0 if action == "optimize" else 2.0
            steps.append(
                ScalingStep(
                    trigger_metric=pred.metric,
                    trigger_threshold=threshold,
                    action=action,
                    new_capacity=new_cap,
                    cost_delta=round(cost, 2),
                    implementation_time_hours=impl_time,
                )
            )
        return steps

    def _overall_risk(
        self, predictions: list[SaturationPrediction]
    ) -> str:
        """Determine the worst risk from a list of predictions."""
        if not predictions:
            return "low"
        worst = "low"
        order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        for pred in predictions:
            label = _risk_label(
                pred.predicted_saturation_hours, pred.current_value
            )
            if order.get(label, 0) > order.get(worst, 0):
                worst = label
        return worst
