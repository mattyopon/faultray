# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Capacity planning engine for FaultRay v4.0.

Predicts when infrastructure components will need scaling based on
traffic growth trends, projects error budget consumption, and generates
actionable scaling recommendations.
"""

from __future__ import annotations

import logging
import math

from pydantic import BaseModel, Field

from faultray.errors import ValidationError
from faultray.model.components import Component
from faultray.model.graph import InfraGraph
from faultray.simulator.ops_engine import OpsScenario, OpsSimulationEngine
from faultray.simulator.traffic import create_diurnal_weekly, create_growth_trend

logger = logging.getLogger(__name__)

# Utilization threshold at which a component is considered at capacity.
CAPACITY_THRESHOLD_PERCENT = 80.0
# Target utilization for recommended replica counts (leaves headroom).
TARGET_UTILIZATION_PERCENT = 70.0
# Default base utilization when a component reports zero metrics.
DEFAULT_BASE_UTILIZATION = 30.0

# Per-type baseline utilization estimates for more realistic capacity forecasts.
_DEFAULT_TYPE_UTILIZATION: dict[str, float] = {
    "app_server": 45.0,      # App servers typically run at moderate utilization
    "web_server": 40.0,      # Web servers similar but slightly less
    "database": 55.0,        # Databases typically run hotter
    "cache": 35.0,           # Caches have headroom by design
    "load_balancer": 25.0,   # LBs are over-provisioned for burst handling
    "queue": 30.0,           # Message queues vary widely
    "proxy": 30.0,           # Proxies are lightweight
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class CapacityForecast(BaseModel):
    """Forecast for a single component's capacity needs."""

    component_id: str
    component_type: str
    current_replicas: int
    current_utilization: float = Field(
        description="Current utilization as a percentage (0-100).",
    )
    monthly_growth_rate: float = Field(
        description="Monthly growth rate as a decimal (e.g. 0.10 for 10%).",
    )
    months_to_capacity: float = Field(
        description="Months until utilization reaches the capacity threshold (80%).",
    )
    recommended_replicas_3m: int = Field(
        description="Recommended replica count in 3 months.",
    )
    recommended_replicas_6m: int = Field(
        description="Recommended replica count in 6 months.",
    )
    recommended_replicas_12m: int = Field(
        description="Recommended replica count in 12 months.",
    )
    scaling_urgency: str = Field(
        description='Urgency level: "critical", "warning", or "healthy".',
    )


class ErrorBudgetForecast(BaseModel):
    """Forward-looking error budget projection."""

    slo_target: float = Field(
        description="SLO target percentage (e.g. 99.9).",
    )
    budget_total_minutes: float = Field(
        description="Total error budget in minutes over a 30-day window.",
    )
    budget_consumed_minutes: float = Field(
        description="Budget consumed so far in minutes.",
    )
    budget_consumed_percent: float = Field(
        description="Percentage of total budget consumed.",
    )
    burn_rate_per_day: float = Field(
        description="Minutes of error budget consumed per day.",
    )
    days_to_exhaustion: float | None = Field(
        description="Days until budget is exhausted. None if burn rate is zero.",
    )
    projected_monthly_consumption: float = Field(
        description="Projected percentage of budget consumed over 30 days.",
    )
    status: str = Field(
        description='Budget status: "healthy", "warning", "critical", or "exhausted".',
    )


class CapacityPlanReport(BaseModel):
    """Complete capacity planning report."""

    forecasts: list[CapacityForecast]
    error_budget: ErrorBudgetForecast
    bottleneck_components: list[str] = Field(
        description="Component IDs that hit capacity first (sorted by urgency).",
    )
    scaling_recommendations: list[str] = Field(
        description="Human-readable scaling recommendations.",
    )
    estimated_monthly_cost_increase: float = Field(
        description="Estimated percentage cost increase needed for scaling.",
    )
    summary: str


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class CapacityPlanningEngine:
    """Predicts when infrastructure needs scaling based on growth trends.

    Analyses each component's current utilization, projects forward using
    compound growth, and identifies bottlenecks before they cause incidents.

    Parameters
    ----------
    graph:
        The infrastructure graph to analyse.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def forecast(
        self,
        monthly_growth_rate: float = 0.10,
        slo_target: float = 99.9,
        current_burn_rate: float | None = None,
    ) -> CapacityPlanReport:
        """Generate a capacity plan without running a full ops simulation.

        Parameters
        ----------
        monthly_growth_rate:
            Expected monthly traffic growth as a decimal (e.g. 0.10 = 10%).
        slo_target:
            Availability SLO target percentage.
        current_burn_rate:
            Current error budget burn rate in minutes per day.  If ``None``,
            a conservative estimate is derived from component health states.
        """
        if slo_target <= 0.0 or slo_target > 100.0:
            raise ValidationError(
                f"slo_target must be between 0 (exclusive) and 100 (inclusive), got {slo_target}"
            )

        forecasts = self._build_forecasts(monthly_growth_rate)

        if current_burn_rate is None:
            current_burn_rate = self._estimate_burn_rate(slo_target)

        error_budget = self._build_error_budget_forecast(
            slo_target, current_burn_rate,
        )

        bottlenecks = self._identify_bottlenecks(forecasts)
        recommendations = self._generate_recommendations(
            forecasts, error_budget, bottlenecks,
        )
        cost_increase = self._estimate_cost_increase(forecasts)
        summary = self._build_summary(
            forecasts, error_budget, bottlenecks, cost_increase,
        )

        return CapacityPlanReport(
            forecasts=forecasts,
            error_budget=error_budget,
            bottleneck_components=bottlenecks,
            scaling_recommendations=recommendations,
            estimated_monthly_cost_increase=cost_increase,
            summary=summary,
        )

    def forecast_with_simulation(
        self,
        monthly_growth_rate: float = 0.10,
        slo_target: float = 99.9,
        simulation_days: int = 30,
    ) -> CapacityPlanReport:
        """Generate a capacity plan using an ops simulation for burn rate.

        Runs an :class:`OpsSimulationEngine` with the specified growth rate
        to derive a realistic error budget burn rate, then uses that for
        the capacity forecast.

        Parameters
        ----------
        monthly_growth_rate:
            Expected monthly traffic growth as a decimal.
        slo_target:
            Availability SLO target percentage.
        simulation_days:
            Number of days to simulate.
        """
        scenario = OpsScenario(
            id="capacity-planning-sim",
            name="Capacity Planning Simulation",
            description=(
                f"Simulating {simulation_days} days with "
                f"{monthly_growth_rate:.0%} monthly growth"
            ),
            duration_days=simulation_days,
            traffic_patterns=[
                create_diurnal_weekly(peak=3.0),
                create_growth_trend(
                    monthly_rate=monthly_growth_rate,
                    duration=simulation_days * 86400,
                ),
            ],
            enable_random_failures=True,
            enable_degradation=True,
            enable_maintenance=True,
        )

        engine = OpsSimulationEngine(self.graph)
        result = engine.run_ops_scenario(scenario)

        # Derive burn rate from average availability in SLI timeline.
        # Error budget consumed = (100% - avg_availability%) * observation_time.
        if result.sli_timeline:
            avg_avail = sum(
                p.availability_percent for p in result.sli_timeline
            ) / len(result.sli_timeline)
            # Unavailability fraction
            unavail_fraction = (100.0 - avg_avail) / 100.0
            total_sim_minutes = simulation_days * 24.0 * 60.0
            service_downtime_minutes = unavail_fraction * total_sim_minutes
        else:
            service_downtime_minutes = 0.0
        burn_rate_per_day = (
            service_downtime_minutes / simulation_days
            if simulation_days > 0
            else 0.0
        )

        return self.forecast(
            monthly_growth_rate=monthly_growth_rate,
            slo_target=slo_target,
            current_burn_rate=burn_rate_per_day,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_component_utilization(self, comp: Component) -> float:
        """Get the current utilization for a component.

        When the component reports no utilization data or an
        unrealistically low value (< 10%), falls back to a type-based
        estimate from ``_DEFAULT_TYPE_UTILIZATION`` with a replica-based
        adjustment (single replicas run hotter, highly replicated
        services run cooler).
        """
        util = comp.utilization()
        if util >= 10.0:
            return util

        # Type-based baseline utilization
        base = _DEFAULT_TYPE_UTILIZATION.get(
            comp.type.value, DEFAULT_BASE_UTILIZATION,
        )

        # Replica-based adjustment
        if comp.replicas == 1:
            base += 10.0  # Single point of failure, runs hotter
        elif comp.replicas >= 5:
            base -= 5.0   # Well-distributed load

        return base

    def _build_forecasts(
        self, monthly_growth_rate: float,
    ) -> list[CapacityForecast]:
        """Build per-component capacity forecasts."""
        forecasts: list[CapacityForecast] = []

        for comp_id, comp in self.graph.components.items():
            current_util = self._get_component_utilization(comp)
            months_to_cap = self._months_to_capacity(
                current_util, monthly_growth_rate,
            )
            urgency = self._scaling_urgency(months_to_cap)

            # HA components (failover-enabled, load balancers, DNS) need at
            # least 2 replicas for redundancy regardless of utilization.
            # Cluster components (cache, queue) with 3+ replicas need at
            # least 3 for quorum/consensus (e.g. Redis Cluster, Kafka).
            ha_min = 1
            is_ha = (
                comp.failover.enabled
                or comp.type.value in ("load_balancer", "dns")
            )
            if is_ha:
                ha_min = 2
            if comp.type.value in ("cache", "queue") and comp.replicas >= 3:
                ha_min = max(ha_min, 3)

            rec_3m = max(ha_min, self._replicas_needed(
                comp.replicas, current_util, monthly_growth_rate, 3,
            ))
            rec_6m = max(ha_min, self._replicas_needed(
                comp.replicas, current_util, monthly_growth_rate, 6,
            ))
            rec_12m = max(ha_min, self._replicas_needed(
                comp.replicas, current_util, monthly_growth_rate, 12,
            ))

            forecasts.append(
                CapacityForecast(
                    component_id=comp_id,
                    component_type=comp.type.value,
                    current_replicas=comp.replicas,
                    current_utilization=round(current_util, 2),
                    monthly_growth_rate=monthly_growth_rate,
                    months_to_capacity=round(months_to_cap, 2),
                    recommended_replicas_3m=rec_3m,
                    recommended_replicas_6m=rec_6m,
                    recommended_replicas_12m=rec_12m,
                    scaling_urgency=urgency,
                )
            )

        return forecasts

    @staticmethod
    def _months_to_capacity(
        current_util: float, growth_rate: float,
    ) -> float:
        """Calculate months until utilization reaches the capacity threshold.

        Formula::

            months = log(threshold / current_util) / log(1 + growth_rate)

        Returns ``float('inf')`` when growth rate is zero or current
        utilization already exceeds the threshold.
        """
        if current_util >= CAPACITY_THRESHOLD_PERCENT:
            return 0.0
        if growth_rate <= 0.0:
            return float("inf")
        if current_util <= 0.0:
            return float("inf")

        return (
            math.log(CAPACITY_THRESHOLD_PERCENT / current_util)
            / math.log(1.0 + growth_rate)
        )

    @staticmethod
    def _replicas_needed(
        current_replicas: int,
        current_util: float,
        growth_rate: float,
        months: int,
    ) -> int:
        """Calculate the number of replicas needed at *months* in the future.

        Formula::

            replicas = ceil(
                current_replicas
                * (1 + growth_rate)^months
                * current_util
                / TARGET_UTILIZATION
            )

        The result is always at least 1 (never recommends zero replicas).
        If the component is over-provisioned, fewer replicas than the
        current count may be recommended (right-sizing).
        """
        if current_util <= 0.0:
            return current_replicas

        projected_load = (1.0 + growth_rate) ** months * current_util
        needed = math.ceil(
            current_replicas * projected_load / TARGET_UTILIZATION_PERCENT
        )
        return max(1, needed)

    @staticmethod
    def _scaling_urgency(months_to_capacity: float) -> str:
        """Determine scaling urgency from months-to-capacity.

        Returns
        -------
        str
            ``"critical"`` if < 1 month, ``"warning"`` if < 3 months,
            ``"healthy"`` otherwise.
        """
        if months_to_capacity < 1.0:
            return "critical"
        if months_to_capacity < 3.0:
            return "warning"
        return "healthy"

    def _estimate_burn_rate(self, slo_target: float) -> float:
        """Estimate daily error budget burn rate based on risk factors."""
        daily_burn = 0.0
        for comp in self.graph.components.values():
            # Factor 1: Utilization risk
            util = comp.utilization()
            if util > 80.0:
                daily_burn += 2.0
            elif util > 60.0:
                daily_burn += 0.5
            elif util > 40.0:
                daily_burn += 0.1

            # Factor 2: MTBF/MTTR expected failure downtime
            mtbf_h = comp.operational_profile.mtbf_hours
            if mtbf_h <= 0:
                mtbf_h = 2160.0  # default 90 days
            mttr_min = comp.operational_profile.mttr_minutes
            if mttr_min <= 0:
                mttr_min = 30.0  # default 30 min
            # Expected downtime per day from failures
            failure_downtime = (24.0 / mtbf_h) * mttr_min
            # Multi-replica redundancy: only causes downtime if all replicas fail simultaneously
            # Approximate: discount by 1/replicas (single failure doesn't cause full outage)
            if comp.replicas > 1:
                failure_downtime /= comp.replicas
            daily_burn += failure_downtime

            # Factor 3: SPOF risk (single replica)
            if comp.replicas <= 1:
                daily_burn += 1.0

        # Average across components
        n = len(self.graph.components)
        if n > 0:
            daily_burn /= n

        return daily_burn

    @staticmethod
    def _build_error_budget_forecast(
        slo_target: float,
        burn_rate_per_day: float,
    ) -> ErrorBudgetForecast:
        """Build an error budget forecast from a daily burn rate.

        Parameters
        ----------
        slo_target:
            SLO percentage (e.g. 99.9).
        burn_rate_per_day:
            Minutes of error budget consumed per day.
        """
        budget_total = (1.0 - slo_target / 100.0) * 30.0 * 24.0 * 60.0
        # Assume 7 observation days for consumed calculation
        observation_days = 7.0
        budget_consumed = burn_rate_per_day * observation_days
        budget_consumed_pct = (
            (budget_consumed / budget_total * 100.0) if budget_total > 0 else 0.0
        )

        if burn_rate_per_day > 0:
            remaining = max(0.0, budget_total - budget_consumed)
            days_to_exhaustion = remaining / burn_rate_per_day
        else:
            days_to_exhaustion = None

        projected_monthly = (
            (burn_rate_per_day * 30.0 / budget_total * 100.0)
            if budget_total > 0
            else 0.0
        )

        # Determine status
        if budget_consumed >= budget_total:
            status = "exhausted"
        elif projected_monthly > 100.0:
            status = "critical"
        elif projected_monthly > 50.0:
            status = "warning"
        else:
            status = "healthy"

        return ErrorBudgetForecast(
            slo_target=slo_target,
            budget_total_minutes=round(budget_total, 2),
            budget_consumed_minutes=round(budget_consumed, 2),
            budget_consumed_percent=round(budget_consumed_pct, 2),
            burn_rate_per_day=round(burn_rate_per_day, 4),
            days_to_exhaustion=(
                round(days_to_exhaustion, 2)
                if days_to_exhaustion is not None
                else None
            ),
            projected_monthly_consumption=round(projected_monthly, 2),
            status=status,
        )

    @staticmethod
    def _identify_bottlenecks(
        forecasts: list[CapacityForecast],
    ) -> list[str]:
        """Identify components that will hit capacity first.

        Returns component IDs sorted by ascending ``months_to_capacity``
        (most urgent first), filtering to those that are not infinitely far
        from capacity.
        """
        finite = [
            f for f in forecasts if math.isfinite(f.months_to_capacity)
        ]
        finite.sort(key=lambda f: f.months_to_capacity)
        return [f.component_id for f in finite]

    @staticmethod
    def _generate_recommendations(
        forecasts: list[CapacityForecast],
        error_budget: ErrorBudgetForecast,
        bottleneck_ids: list[str],
    ) -> list[str]:
        """Generate human-readable scaling recommendations."""
        recommendations: list[str] = []

        # Critical components
        critical = [f for f in forecasts if f.scaling_urgency == "critical"]
        for fc in critical:
            recommendations.append(
                f"CRITICAL: {fc.component_id} ({fc.component_type}) will reach "
                f"capacity in {fc.months_to_capacity:.1f} months. Scale from "
                f"{fc.current_replicas} to {fc.recommended_replicas_3m} replicas "
                f"immediately."
            )

        # Warning components
        warning = [f for f in forecasts if f.scaling_urgency == "warning"]
        for fc in warning:
            recommendations.append(
                f"WARNING: {fc.component_id} ({fc.component_type}) will reach "
                f"capacity in {fc.months_to_capacity:.1f} months. Plan to scale "
                f"from {fc.current_replicas} to {fc.recommended_replicas_3m} "
                f"replicas within 3 months."
            )

        # Error budget warnings
        if error_budget.status == "exhausted":
            recommendations.append(
                "CRITICAL: Error budget is exhausted. Halt all non-critical "
                "releases and focus on reliability improvements."
            )
        elif error_budget.status == "critical":
            recommendations.append(
                f"CRITICAL: Error budget projected to exceed 100% this month "
                f"(burn rate: {error_budget.burn_rate_per_day:.2f} min/day). "
                f"Prioritise stability over features."
            )
        elif error_budget.status == "warning":
            recommendations.append(
                f"WARNING: Error budget projected at "
                f"{error_budget.projected_monthly_consumption:.1f}% consumption "
                f"this month. Monitor burn rate closely."
            )

        # Right-sizing opportunities (scale-down recommendations)
        over_provisioned = [
            f for f in forecasts
            if f.recommended_replicas_3m < f.current_replicas
        ]
        for fc in over_provisioned:
            recommendations.append(
                f"RIGHT-SIZE: {fc.component_id} ({fc.component_type}) is "
                f"over-provisioned at {fc.current_utilization:.1f}% utilization. "
                f"Consider scaling from {fc.current_replicas} to "
                f"{fc.recommended_replicas_3m} replicas to reduce costs."
            )

        # Bottleneck summary
        if bottleneck_ids:
            top = bottleneck_ids[:3]
            recommendations.append(
                f"Bottleneck components (first to hit capacity): "
                f"{', '.join(top)}."
            )

        if not recommendations:
            recommendations.append(
                "All components are healthy with sufficient capacity headroom."
            )

        return recommendations

    @staticmethod
    def _estimate_cost_increase(
        forecasts: list[CapacityForecast],
    ) -> float:
        """Estimate the percentage cost increase for scaling over 3 months.

        Uses the ratio of recommended 3-month replicas to current replicas
        as a proxy for cost increase.
        """
        if not forecasts:
            return 0.0

        total_current = sum(f.current_replicas for f in forecasts)
        total_recommended = sum(f.recommended_replicas_3m for f in forecasts)

        if total_current <= 0:
            return 0.0

        increase_ratio = (total_recommended - total_current) / total_current
        return round(increase_ratio * 100.0, 2)

    @staticmethod
    def _build_summary(
        forecasts: list[CapacityForecast],
        error_budget: ErrorBudgetForecast,
        bottleneck_ids: list[str],
        cost_increase: float,
    ) -> str:
        """Build a human-readable summary of the capacity plan."""
        critical_count = sum(
            1 for f in forecasts if f.scaling_urgency == "critical"
        )
        warning_count = sum(
            1 for f in forecasts if f.scaling_urgency == "warning"
        )
        healthy_count = sum(
            1 for f in forecasts if f.scaling_urgency == "healthy"
        )

        lines = [
            f"Capacity Plan: {len(forecasts)} components analysed.",
            f"  Urgency: {critical_count} critical, {warning_count} warning, "
            f"{healthy_count} healthy.",
        ]

        if bottleneck_ids:
            lines.append(
                f"  First bottleneck: {bottleneck_ids[0]}."
            )

        lines.append(
            f"  Error budget ({error_budget.slo_target}% SLO): "
            f"{error_budget.budget_consumed_percent:.1f}% consumed, "
            f"status={error_budget.status}."
        )
        lines.append(
            f"  Estimated 3-month cost increase: {cost_increase:.1f}%."
        )

        return "\n".join(lines)
