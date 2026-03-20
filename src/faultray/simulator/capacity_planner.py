# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Capacity planning engine — forecast resource needs and scaling events.

Predicts when infrastructure components will reach capacity limits
based on current utilization trends, growth patterns, and seasonal
factors. Generates capacity forecasts and scaling recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import ceil, exp, log

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


class GrowthModel(str, Enum):
    """Traffic/resource growth model."""

    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    LOGARITHMIC = "logarithmic"
    PLATEAU = "plateau"


class CapacityRisk(str, Enum):
    """Capacity risk level."""

    SAFE = "safe"
    WATCH = "watch"
    WARNING = "warning"
    CRITICAL = "critical"
    EXCEEDED = "exceeded"


@dataclass
class CapacityForecast:
    """Forecast for a single component's capacity."""

    component_id: str
    component_name: str
    component_type: str
    current_utilization: float  # 0-100
    current_headroom: float  # remaining capacity %
    days_to_80_percent: int | None  # days until 80% utilization
    days_to_100_percent: int | None  # days until capacity exhaustion
    risk: CapacityRisk
    recommended_replicas: int
    current_replicas: int
    scaling_trigger_days: int | None  # when to start scaling
    cost_multiplier: float  # cost increase from scaling
    bottleneck_resource: str  # cpu, memory, connections, disk


@dataclass
class ScalingEvent:
    """A predicted scaling event."""

    component_id: str
    component_name: str
    day: int  # days from now
    action: str  # "scale_up", "scale_out", "add_cache", "optimize"
    from_replicas: int
    to_replicas: int
    reason: str
    estimated_cost_impact: str


@dataclass
class CapacityPlan:
    """Full capacity planning report."""

    forecasts: list[CapacityForecast]
    scaling_events: list[ScalingEvent]
    overall_risk: CapacityRisk
    days_to_first_bottleneck: int | None
    bottleneck_components: list[str]
    total_cost_multiplier: float
    recommendations: list[str]
    growth_model: GrowthModel
    growth_rate_percent: float
    planning_horizon_days: int


# Growth rate multipliers by component type
_TYPE_GROWTH_FACTORS: dict[ComponentType, float] = {
    ComponentType.WEB_SERVER: 1.2,
    ComponentType.APP_SERVER: 1.0,
    ComponentType.DATABASE: 0.8,
    ComponentType.CACHE: 1.1,
    ComponentType.QUEUE: 1.0,
    ComponentType.LOAD_BALANCER: 1.3,
    ComponentType.STORAGE: 0.9,
    ComponentType.DNS: 0.5,
    ComponentType.EXTERNAL_API: 0.3,
    ComponentType.CUSTOM: 1.0,
}


def _project_utilization(
    current: float,
    days: int,
    daily_growth_rate: float,
    model: GrowthModel,
) -> float:
    """Project utilization at a future day given a growth model."""
    if model == GrowthModel.LINEAR:
        return current + (daily_growth_rate * days)
    elif model == GrowthModel.EXPONENTIAL:
        return current * ((1 + daily_growth_rate / 100) ** days)
    elif model == GrowthModel.LOGARITHMIC:
        if days <= 0:
            return current
        return current + daily_growth_rate * log(1 + days)
    elif model == GrowthModel.PLATEAU:
        # Logistic growth approaching 100%
        k = daily_growth_rate / 100
        return 100 / (1 + ((100 - current) / max(current, 1)) * exp(-k * days))
    return current


def _days_to_threshold(
    current: float,
    threshold: float,
    daily_growth_rate: float,
    model: GrowthModel,
    max_days: int = 365,
) -> int | None:
    """Estimate days until utilization reaches a threshold."""
    if current >= threshold:
        return 0
    if daily_growth_rate <= 0:
        return None

    for day in range(1, max_days + 1):
        projected = _project_utilization(current, day, daily_growth_rate, model)
        if projected >= threshold:
            return day
    return None


def _identify_bottleneck(component) -> str:
    """Identify the primary bottleneck resource for a component."""
    metrics = {
        "cpu": component.metrics.cpu_percent,
        "memory": component.metrics.memory_percent,
        "disk": component.metrics.disk_percent,
        "connections": (
            component.metrics.network_connections
            / max(component.capacity.max_connections, 1)
            * 100
        ),
    }
    return max(metrics, key=metrics.get)  # type: ignore[arg-type]


def _classify_risk(
    current_util: float,
    days_to_100: int | None,
) -> CapacityRisk:
    """Classify capacity risk based on utilization and forecast."""
    if current_util >= 95:
        return CapacityRisk.EXCEEDED
    if current_util >= 85 or (days_to_100 is not None and days_to_100 <= 7):
        return CapacityRisk.CRITICAL
    if current_util >= 70 or (days_to_100 is not None and days_to_100 <= 30):
        return CapacityRisk.WARNING
    if current_util >= 50 or (days_to_100 is not None and days_to_100 <= 90):
        return CapacityRisk.WATCH
    return CapacityRisk.SAFE


class CapacityPlanner:
    """Forecast capacity needs and generate scaling plans."""

    def __init__(
        self,
        growth_rate_percent: float = 5.0,
        growth_model: GrowthModel = GrowthModel.LINEAR,
        planning_horizon_days: int = 180,
    ):
        self._growth_rate = growth_rate_percent
        self._model = growth_model
        self._horizon = planning_horizon_days

    def plan(self, graph: InfraGraph) -> CapacityPlan:
        """Generate a full capacity plan for the infrastructure."""
        if not graph.components:
            return CapacityPlan(
                forecasts=[],
                scaling_events=[],
                overall_risk=CapacityRisk.SAFE,
                days_to_first_bottleneck=None,
                bottleneck_components=[],
                total_cost_multiplier=1.0,
                recommendations=[],
                growth_model=self._model,
                growth_rate_percent=self._growth_rate,
                planning_horizon_days=self._horizon,
            )

        forecasts: list[CapacityForecast] = []
        scaling_events: list[ScalingEvent] = []
        bottleneck_days: list[int] = []
        bottleneck_names: list[str] = []

        for comp in graph.components.values():
            forecast = self._forecast_component(comp, graph)
            forecasts.append(forecast)

            if forecast.days_to_100_percent is not None:
                bottleneck_days.append(forecast.days_to_100_percent)
                bottleneck_names.append(comp.name)

            # Generate scaling events
            events = self._plan_scaling_events(comp, forecast)
            scaling_events.extend(events)

        # Sort scaling events by day
        scaling_events.sort(key=lambda e: e.day)

        # Calculate overall risk
        risks = [f.risk for f in forecasts]
        risk_order = [CapacityRisk.SAFE, CapacityRisk.WATCH, CapacityRisk.WARNING,
                      CapacityRisk.CRITICAL, CapacityRisk.EXCEEDED]
        overall_risk = max(risks, key=lambda r: risk_order.index(r))

        # Cost multiplier
        total_cost = sum(f.cost_multiplier for f in forecasts)
        avg_cost = total_cost / len(forecasts) if forecasts else 1.0

        # First bottleneck
        first_bottleneck = min(bottleneck_days) if bottleneck_days else None

        # Recommendations
        recommendations = self._generate_recommendations(forecasts, scaling_events)

        return CapacityPlan(
            forecasts=forecasts,
            scaling_events=scaling_events,
            overall_risk=overall_risk,
            days_to_first_bottleneck=first_bottleneck,
            bottleneck_components=bottleneck_names,
            total_cost_multiplier=round(avg_cost, 2),
            recommendations=recommendations,
            growth_model=self._model,
            growth_rate_percent=self._growth_rate,
            planning_horizon_days=self._horizon,
        )

    def forecast_component(
        self, graph: InfraGraph, component_id: str
    ) -> CapacityForecast | None:
        """Forecast capacity for a single component."""
        comp = graph.get_component(component_id)
        if comp is None:
            return None
        return self._forecast_component(comp, graph)

    def what_if_growth(
        self, graph: InfraGraph, growth_rate: float
    ) -> CapacityPlan:
        """Simulate capacity plan with a different growth rate."""
        original_rate = self._growth_rate
        self._growth_rate = growth_rate
        plan = self.plan(graph)
        self._growth_rate = original_rate
        return plan

    def _forecast_component(
        self, component, graph: InfraGraph
    ) -> CapacityForecast:
        """Forecast capacity for a single component."""
        util = component.utilization()
        headroom = max(0, 100 - util)

        # Adjust growth rate by component type
        type_factor = _TYPE_GROWTH_FACTORS.get(component.type, 1.0)
        effective_growth = self._growth_rate * type_factor

        # Daily growth rate
        daily_growth = effective_growth / 30  # monthly rate → daily

        # Calculate days to thresholds
        days_80 = _days_to_threshold(util, 80, daily_growth, self._model)
        days_100 = _days_to_threshold(util, 100, daily_growth, self._model)

        # Risk classification
        risk = _classify_risk(util, days_100)

        # Recommended replicas
        bottleneck = _identify_bottleneck(component)
        recommended = self._calculate_recommended_replicas(
            component, util, days_100
        )

        # Cost multiplier
        cost_mult = recommended / max(component.replicas, 1)

        # Scaling trigger
        scaling_trigger = None
        if days_80 is not None and days_80 > 0:
            scaling_trigger = max(1, days_80 - 14)  # 2 weeks before 80%

        return CapacityForecast(
            component_id=component.id,
            component_name=component.name,
            component_type=component.type.value,
            current_utilization=round(util, 1),
            current_headroom=round(headroom, 1),
            days_to_80_percent=days_80,
            days_to_100_percent=days_100,
            risk=risk,
            recommended_replicas=recommended,
            current_replicas=component.replicas,
            scaling_trigger_days=scaling_trigger,
            cost_multiplier=round(cost_mult, 2),
            bottleneck_resource=bottleneck,
        )

    def _calculate_recommended_replicas(
        self, component, current_util: float, days_to_100: int | None
    ) -> int:
        """Calculate recommended replica count."""
        current = component.replicas

        # If autoscaling is enabled, trust it
        if component.autoscaling.enabled:
            return max(current, component.autoscaling.min_replicas)

        # If no growth concern, keep current
        if days_to_100 is None or days_to_100 > self._horizon:
            return current

        # Calculate needed replicas to handle projected load
        projected_util = _project_utilization(
            current_util, self._horizon, self._growth_rate / 30, self._model
        )

        # Target 60% utilization after scaling
        if projected_util <= 0:
            return current
        needed_capacity = projected_util / 60.0
        recommended = max(current, ceil(current * needed_capacity))

        # Cap at reasonable limits
        return min(recommended, current * 5, 50)

    def _plan_scaling_events(
        self, component, forecast: CapacityForecast
    ) -> list[ScalingEvent]:
        """Generate scaling events for a component."""
        events: list[ScalingEvent] = []

        if forecast.risk in (CapacityRisk.SAFE, CapacityRisk.WATCH):
            return events

        if forecast.days_to_80_percent is not None:
            trigger_day = max(1, forecast.days_to_80_percent - 14)
            new_replicas = min(
                forecast.current_replicas + 1,
                forecast.recommended_replicas
            )
            if new_replicas > forecast.current_replicas:
                events.append(ScalingEvent(
                    component_id=component.id,
                    component_name=component.name,
                    day=trigger_day,
                    action="scale_out",
                    from_replicas=forecast.current_replicas,
                    to_replicas=new_replicas,
                    reason=f"Projected to reach 80% utilization in {forecast.days_to_80_percent} days",
                    estimated_cost_impact=f"+{((new_replicas / forecast.current_replicas) - 1) * 100:.0f}%",
                ))

        if forecast.risk in (CapacityRisk.CRITICAL, CapacityRisk.EXCEEDED):
            events.append(ScalingEvent(
                component_id=component.id,
                component_name=component.name,
                day=0,
                action="scale_up" if forecast.current_replicas >= 3 else "scale_out",
                from_replicas=forecast.current_replicas,
                to_replicas=forecast.recommended_replicas,
                reason=f"Current utilization at {forecast.current_utilization}% — immediate action needed",
                estimated_cost_impact=f"+{((forecast.recommended_replicas / max(forecast.current_replicas, 1)) - 1) * 100:.0f}%",
            ))

        return events

    def _generate_recommendations(
        self,
        forecasts: list[CapacityForecast],
        events: list[ScalingEvent],
    ) -> list[str]:
        """Generate capacity planning recommendations."""
        recs: list[str] = []

        critical = [f for f in forecasts if f.risk in (CapacityRisk.CRITICAL, CapacityRisk.EXCEEDED)]
        warning = [f for f in forecasts if f.risk == CapacityRisk.WARNING]

        if critical:
            names = ", ".join(f.component_name for f in critical[:3])
            recs.append(f"URGENT: {len(critical)} component(s) at critical capacity: {names}")

        if warning:
            names = ", ".join(f.component_name for f in warning[:3])
            recs.append(f"PLAN: {len(warning)} component(s) approaching capacity limits: {names}")

        # Bottleneck analysis
        bottlenecks: dict[str, int] = {}
        for f in forecasts:
            bottlenecks[f.bottleneck_resource] = bottlenecks.get(f.bottleneck_resource, 0) + 1
        top_bottleneck = max(bottlenecks, key=bottlenecks.get) if bottlenecks else None  # type: ignore[arg-type]
        if top_bottleneck and bottlenecks[top_bottleneck] > 1:
            recs.append(
                f"Common bottleneck: {top_bottleneck} is the limiting resource for "
                f"{bottlenecks[top_bottleneck]} components"
            )

        # Cost impact
        if events:
            total_events = len(events)
            recs.append(f"{total_events} scaling event(s) projected within planning horizon")

        # Autoscaling suggestion
        no_autoscale = [f for f in forecasts if f.risk != CapacityRisk.SAFE
                        and f.cost_multiplier > 1.0]
        if no_autoscale:
            recs.append(
                "Consider enabling autoscaling for components with growing demand"
            )

        return recs
