# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Capacity Planning Engine for FaultRay.

Models and predicts infrastructure capacity requirements across multiple
resource dimensions. Supports linear, exponential, seasonal, and
event-driven growth models with headroom analysis, time-to-exhaustion
prediction, cost projection, right-sizing recommendations, peak vs
steady-state modeling, reservation planning, burst capacity analysis,
cross-resource bottleneck identification, and confidence intervals.
"""

from __future__ import annotations

import logging
import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ResourceType(str, Enum):
    """Infrastructure resource dimension."""

    CPU = "cpu"
    MEMORY = "memory"
    DISK = "disk"
    NETWORK_BANDWIDTH = "network_bandwidth"
    IOPS = "iops"
    CONNECTIONS = "connections"


class GrowthModelType(str, Enum):
    """Growth projection model."""

    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    SEASONAL = "seasonal"
    EVENT_DRIVEN = "event_driven"


class SizingVerdict(str, Enum):
    """Component sizing assessment."""

    UNDER_PROVISIONED = "under_provisioned"
    RIGHT_SIZED = "right_sized"
    OVER_PROVISIONED = "over_provisioned"


class CapacityRiskLevel(str, Enum):
    """Capacity risk classification."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class ReservationType(str, Enum):
    """Cloud reservation / savings plan type."""

    ON_DEMAND = "on_demand"
    RESERVED_1Y = "reserved_1y"
    RESERVED_3Y = "reserved_3y"
    SAVINGS_PLAN = "savings_plan"
    SPOT = "spot"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ResourceSnapshot:
    """Current utilization for a single resource type."""

    resource: ResourceType
    current_value: float
    capacity_limit: float
    unit: str = ""

    @property
    def utilization_percent(self) -> float:
        if self.capacity_limit <= 0:
            return 0.0
        return min(100.0, self.current_value / self.capacity_limit * 100.0)

    @property
    def headroom_percent(self) -> float:
        return max(0.0, 100.0 - self.utilization_percent)


@dataclass
class ExhaustionPrediction:
    """Prediction for when a resource will be exhausted."""

    resource: ResourceType
    days_to_exhaustion: float | None
    days_to_warning: float | None  # 80% threshold
    days_to_critical: float | None  # 90% threshold
    confidence_lower: float | None  # lower bound days (confidence interval)
    confidence_upper: float | None  # upper bound days (confidence interval)
    confidence_level: float = 0.90  # e.g. 90% CI


@dataclass
class CostProjection:
    """Cost projection based on growth models."""

    current_monthly_cost: float
    projected_monthly_cost_3m: float
    projected_monthly_cost_6m: float
    projected_monthly_cost_12m: float
    reservation_savings_percent: float
    recommended_reservation: ReservationType


@dataclass
class SizingRecommendation:
    """Right-sizing recommendation for a component."""

    component_id: str
    verdict: SizingVerdict
    current_replicas: int
    recommended_replicas: int
    primary_resource: ResourceType
    utilization_percent: float
    justification: str


@dataclass
class BurstCapacityResult:
    """Burst capacity analysis for a component."""

    component_id: str
    can_handle_2x: bool
    can_handle_3x: bool
    can_handle_5x: bool
    max_burst_multiplier: float
    limiting_resource: ResourceType
    burst_headroom_percent: float


@dataclass
class BottleneckInfo:
    """Cross-resource bottleneck information."""

    component_id: str
    bottleneck_resource: ResourceType
    utilization_percent: float
    secondary_resources: list[tuple[ResourceType, float]]
    cascading_risk: bool


@dataclass
class PeakSteadyAnalysis:
    """Peak vs steady-state capacity comparison."""

    component_id: str
    steady_state_util: float
    peak_util: float
    peak_to_steady_ratio: float
    requires_burst_capacity: bool


@dataclass
class ReservationPlan:
    """Capacity reservation planning output."""

    component_id: str
    recommended_type: ReservationType
    base_capacity_units: float
    reserved_capacity_units: float
    on_demand_buffer_units: float
    estimated_monthly_savings: float
    break_even_months: int


@dataclass
class ComponentCapacityReport:
    """Full capacity report for a single component."""

    component_id: str
    component_type: str
    resources: list[ResourceSnapshot]
    exhaustion_predictions: list[ExhaustionPrediction]
    sizing: SizingRecommendation
    burst: BurstCapacityResult
    peak_steady: PeakSteadyAnalysis
    bottleneck: BottleneckInfo | None
    reservation: ReservationPlan
    risk_level: CapacityRiskLevel


@dataclass
class CapacityPlanningReport:
    """Complete capacity planning report."""

    timestamp: str
    components: list[ComponentCapacityReport]
    cost_projection: CostProjection
    bottlenecks: list[BottleneckInfo]
    overall_risk: CapacityRiskLevel
    days_to_first_exhaustion: float | None
    recommendations: list[str]
    growth_model: GrowthModelType
    growth_rate: float
    planning_horizon_days: int
    confidence_level: float


# ---------------------------------------------------------------------------
# Growth projection helpers
# ---------------------------------------------------------------------------

# Warning / critical thresholds (percent utilization).
_WARNING_THRESHOLD = 80.0
_CRITICAL_THRESHOLD = 90.0

# Type-based growth rate multipliers.
_TYPE_GROWTH_FACTORS: dict[ComponentType, float] = {
    ComponentType.LOAD_BALANCER: 1.3,
    ComponentType.WEB_SERVER: 1.2,
    ComponentType.APP_SERVER: 1.0,
    ComponentType.DATABASE: 0.8,
    ComponentType.CACHE: 1.1,
    ComponentType.QUEUE: 1.0,
    ComponentType.STORAGE: 0.9,
    ComponentType.DNS: 0.5,
    ComponentType.EXTERNAL_API: 0.3,
    ComponentType.CUSTOM: 1.0,
}

# Default resource baselines when metrics are zero.
_DEFAULT_BASELINES: dict[ResourceType, float] = {
    ResourceType.CPU: 35.0,
    ResourceType.MEMORY: 40.0,
    ResourceType.DISK: 20.0,
    ResourceType.NETWORK_BANDWIDTH: 15.0,
    ResourceType.IOPS: 10.0,
    ResourceType.CONNECTIONS: 25.0,
}

# Peak-to-steady multiplier by component type (models diurnal variation).
_PEAK_MULTIPLIERS: dict[ComponentType, float] = {
    ComponentType.LOAD_BALANCER: 2.5,
    ComponentType.WEB_SERVER: 2.2,
    ComponentType.APP_SERVER: 1.8,
    ComponentType.DATABASE: 1.4,
    ComponentType.CACHE: 1.6,
    ComponentType.QUEUE: 2.0,
    ComponentType.STORAGE: 1.1,
    ComponentType.DNS: 1.3,
    ComponentType.EXTERNAL_API: 1.5,
    ComponentType.CUSTOM: 1.5,
}

# Hourly cost rates per replica (rough defaults for cost projections).
_DEFAULT_HOURLY_COST_PER_REPLICA: dict[ComponentType, float] = {
    ComponentType.LOAD_BALANCER: 0.025,
    ComponentType.WEB_SERVER: 0.05,
    ComponentType.APP_SERVER: 0.10,
    ComponentType.DATABASE: 0.25,
    ComponentType.CACHE: 0.08,
    ComponentType.QUEUE: 0.04,
    ComponentType.STORAGE: 0.03,
    ComponentType.DNS: 0.01,
    ComponentType.EXTERNAL_API: 0.0,
    ComponentType.CUSTOM: 0.05,
}


def project_value(
    current: float,
    days: int,
    daily_rate: float,
    model: GrowthModelType,
    seasonal_amplitude: float = 0.0,
    seasonal_period_days: float = 365.0,
    event_spikes: list[tuple[int, float]] | None = None,
) -> float:
    """Project a value forward by *days* under the chosen growth model.

    Parameters
    ----------
    current:
        Current value.
    days:
        Number of days to project.
    daily_rate:
        Daily growth rate (absolute for linear, percentage for exponential).
    model:
        Growth model type.
    seasonal_amplitude:
        Amplitude of seasonal component (fraction of base, 0-1).
    seasonal_period_days:
        Period of the seasonal cycle in days.
    event_spikes:
        List of ``(day, multiplier)`` pairs for event-driven spikes.
    """
    if days <= 0:
        return current

    if model == GrowthModelType.LINEAR:
        base = current + daily_rate * days
    elif model == GrowthModelType.EXPONENTIAL:
        base = current * ((1.0 + daily_rate / 100.0) ** days)
    elif model == GrowthModelType.SEASONAL:
        trend = current + daily_rate * days
        seasonal = seasonal_amplitude * current * math.sin(
            2.0 * math.pi * days / seasonal_period_days
        )
        base = trend + seasonal
    elif model == GrowthModelType.EVENT_DRIVEN:
        base = current + daily_rate * days
        if event_spikes:
            for spike_day, multiplier in event_spikes:
                if days >= spike_day:
                    base *= multiplier
                    break  # apply the most recent spike
    else:
        base = current

    return max(0.0, base)


def days_to_threshold(
    current: float,
    threshold: float,
    daily_rate: float,
    model: GrowthModelType,
    max_days: int = 730,
    seasonal_amplitude: float = 0.0,
) -> float | None:
    """Estimate days until a value reaches *threshold*.

    For linear/exponential models, uses closed-form when possible.
    Falls back to iterative search for seasonal/event models.

    Returns ``None`` if the threshold is not reached within *max_days*.
    """
    if current >= threshold:
        return 0.0
    if daily_rate <= 0:
        return None

    # Closed-form shortcuts
    if model == GrowthModelType.LINEAR:
        d = (threshold - current) / daily_rate
        return d if d <= max_days else None
    if model == GrowthModelType.EXPONENTIAL:
        if daily_rate <= 0:
            return None
        ratio = threshold / current if current > 0 else float("inf")
        if ratio <= 0:
            return None
        d = math.log(ratio) / math.log(1.0 + daily_rate / 100.0)
        return d if d <= max_days else None

    # Iterative fallback for seasonal / event models
    for day in range(1, max_days + 1):
        projected = project_value(
            current, day, daily_rate, model,
            seasonal_amplitude=seasonal_amplitude,
        )
        if projected >= threshold:
            return float(day)
    return None


# ---------------------------------------------------------------------------
# Capacity Planning Engine
# ---------------------------------------------------------------------------


class CapacityPlanningEngine:
    """Models and predicts infrastructure capacity requirements.

    Analyses each component across multiple resource dimensions,
    projects growth, and generates detailed capacity plans with
    right-sizing recommendations and confidence intervals.

    Parameters
    ----------
    graph:
        The infrastructure graph to analyse.
    growth_rate:
        Base daily growth rate (meaning depends on *growth_model*).
    growth_model:
        Growth projection model.
    planning_horizon_days:
        Planning window in days.
    confidence_level:
        Confidence level for prediction intervals (default 0.90).
    peak_multiplier_override:
        If set, overrides the type-based peak-to-steady multiplier.
    """

    def __init__(
        self,
        graph: InfraGraph,
        growth_rate: float = 0.5,
        growth_model: GrowthModelType = GrowthModelType.LINEAR,
        planning_horizon_days: int = 180,
        confidence_level: float = 0.90,
        peak_multiplier_override: float | None = None,
    ) -> None:
        self.graph = graph
        self.growth_rate = growth_rate
        self.growth_model = growth_model
        self.planning_horizon_days = planning_horizon_days
        self.confidence_level = confidence_level
        self.peak_multiplier_override = peak_multiplier_override
        self._now = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self) -> CapacityPlanningReport:
        """Run full capacity planning analysis and return a report."""
        component_reports: list[ComponentCapacityReport] = []
        all_bottlenecks: list[BottleneckInfo] = []
        first_exhaustion: float | None = None
        recommendations: list[str] = []

        for comp_id, comp in self.graph.components.items():
            report = self._analyze_component(comp)
            component_reports.append(report)

            if report.bottleneck is not None:
                all_bottlenecks.append(report.bottleneck)

            for ep in report.exhaustion_predictions:
                if ep.days_to_exhaustion is not None:
                    if first_exhaustion is None or ep.days_to_exhaustion < first_exhaustion:
                        first_exhaustion = ep.days_to_exhaustion

        # Overall risk
        risk_order = [
            CapacityRiskLevel.LOW,
            CapacityRiskLevel.MODERATE,
            CapacityRiskLevel.HIGH,
            CapacityRiskLevel.CRITICAL,
        ]
        overall = CapacityRiskLevel.LOW
        for cr in component_reports:
            if risk_order.index(cr.risk_level) > risk_order.index(overall):
                overall = cr.risk_level

        # Cost projection
        cost_proj = self._build_cost_projection(component_reports)

        # Recommendations
        recommendations = self._build_recommendations(
            component_reports, all_bottlenecks, cost_proj,
        )

        return CapacityPlanningReport(
            timestamp=self._now.isoformat(),
            components=component_reports,
            cost_projection=cost_proj,
            bottlenecks=all_bottlenecks,
            overall_risk=overall,
            days_to_first_exhaustion=first_exhaustion,
            recommendations=recommendations,
            growth_model=self.growth_model,
            growth_rate=self.growth_rate,
            planning_horizon_days=self.planning_horizon_days,
            confidence_level=self.confidence_level,
        )

    def analyze_component(self, component_id: str) -> ComponentCapacityReport | None:
        """Analyse a single component by id."""
        comp = self.graph.get_component(component_id)
        if comp is None:
            return None
        return self._analyze_component(comp)

    def what_if_growth(self, new_rate: float) -> CapacityPlanningReport:
        """Re-run analysis with a different growth rate."""
        original = self.growth_rate
        self.growth_rate = new_rate
        result = self.analyze()
        self.growth_rate = original
        return result

    def burst_test(
        self, component_id: str, multiplier: float = 3.0,
    ) -> BurstCapacityResult | None:
        """Test whether a component can handle a specific traffic burst."""
        comp = self.graph.get_component(component_id)
        if comp is None:
            return None
        return self._burst_analysis(comp)

    # ------------------------------------------------------------------
    # Private: per-component analysis
    # ------------------------------------------------------------------

    def _analyze_component(self, comp: Component) -> ComponentCapacityReport:
        """Run full analysis for a single component."""
        snapshots = self._build_resource_snapshots(comp)
        exhaustion = self._predict_exhaustion(comp, snapshots)
        sizing = self._right_size(comp, snapshots)
        burst = self._burst_analysis(comp)
        peak_steady = self._peak_steady_analysis(comp, snapshots)
        bottleneck = self._detect_bottleneck(comp, snapshots)
        reservation = self._reservation_plan(comp, snapshots)
        risk = self._classify_risk(comp, exhaustion, snapshots)

        return ComponentCapacityReport(
            component_id=comp.id,
            component_type=comp.type.value,
            resources=snapshots,
            exhaustion_predictions=exhaustion,
            sizing=sizing,
            burst=burst,
            peak_steady=peak_steady,
            bottleneck=bottleneck,
            reservation=reservation,
            risk_level=risk,
        )

    # ------------------------------------------------------------------
    # Private: resource snapshots
    # ------------------------------------------------------------------

    def _build_resource_snapshots(self, comp: Component) -> list[ResourceSnapshot]:
        """Extract resource utilization snapshots from a component."""
        snapshots: list[ResourceSnapshot] = []

        # CPU
        cpu_val = comp.metrics.cpu_percent
        if cpu_val <= 0:
            cpu_val = _DEFAULT_BASELINES[ResourceType.CPU]
        snapshots.append(ResourceSnapshot(
            resource=ResourceType.CPU,
            current_value=cpu_val,
            capacity_limit=100.0,
            unit="percent",
        ))

        # Memory
        mem_val = comp.metrics.memory_percent
        if mem_val <= 0:
            mem_val = _DEFAULT_BASELINES[ResourceType.MEMORY]
        snapshots.append(ResourceSnapshot(
            resource=ResourceType.MEMORY,
            current_value=mem_val,
            capacity_limit=100.0,
            unit="percent",
        ))

        # Disk
        disk_val = comp.metrics.disk_percent
        if disk_val <= 0:
            disk_val = _DEFAULT_BASELINES[ResourceType.DISK]
        snapshots.append(ResourceSnapshot(
            resource=ResourceType.DISK,
            current_value=disk_val,
            capacity_limit=100.0,
            unit="percent",
        ))

        # Network / connections
        conn_val = float(comp.metrics.network_connections)
        conn_limit = float(comp.capacity.max_connections)
        if conn_limit <= 0:
            conn_limit = 1000.0
        if conn_val <= 0:
            conn_val = conn_limit * _DEFAULT_BASELINES[ResourceType.CONNECTIONS] / 100.0
        snapshots.append(ResourceSnapshot(
            resource=ResourceType.CONNECTIONS,
            current_value=conn_val,
            capacity_limit=conn_limit,
            unit="connections",
        ))

        # IOPS (derived from disk activity — use disk_percent as proxy)
        iops_proxy = comp.metrics.disk_percent * 0.8
        if iops_proxy <= 0:
            iops_proxy = _DEFAULT_BASELINES[ResourceType.IOPS]
        snapshots.append(ResourceSnapshot(
            resource=ResourceType.IOPS,
            current_value=iops_proxy,
            capacity_limit=100.0,
            unit="percent",
        ))

        # Network bandwidth (use connection ratio as proxy)
        bw_proxy = (conn_val / conn_limit * 100.0) if conn_limit > 0 else 0.0
        if bw_proxy <= 0:
            bw_proxy = _DEFAULT_BASELINES[ResourceType.NETWORK_BANDWIDTH]
        snapshots.append(ResourceSnapshot(
            resource=ResourceType.NETWORK_BANDWIDTH,
            current_value=bw_proxy,
            capacity_limit=100.0,
            unit="percent",
        ))

        return snapshots

    # ------------------------------------------------------------------
    # Private: exhaustion prediction
    # ------------------------------------------------------------------

    def _predict_exhaustion(
        self, comp: Component, snapshots: list[ResourceSnapshot],
    ) -> list[ExhaustionPrediction]:
        """Predict time-to-exhaustion for each resource."""
        type_factor = _TYPE_GROWTH_FACTORS.get(comp.type, 1.0)
        effective_rate = self.growth_rate * type_factor
        predictions: list[ExhaustionPrediction] = []

        for snap in snapshots:
            util = snap.utilization_percent

            d_100 = days_to_threshold(
                util, 100.0, effective_rate, self.growth_model,
                max_days=self.planning_horizon_days * 2,
            )
            d_warning = days_to_threshold(
                util, _WARNING_THRESHOLD, effective_rate, self.growth_model,
                max_days=self.planning_horizon_days * 2,
            )
            d_critical = days_to_threshold(
                util, _CRITICAL_THRESHOLD, effective_rate, self.growth_model,
                max_days=self.planning_horizon_days * 2,
            )

            # Confidence interval: +/- a fraction based on confidence level
            ci_lower: float | None = None
            ci_upper: float | None = None
            if d_100 is not None and d_100 > 0:
                # Width scales with planning horizon uncertainty
                z = 1.645 if self.confidence_level >= 0.90 else 1.0
                spread = d_100 * (1.0 - self.confidence_level) * z
                ci_lower = max(0.0, d_100 - spread)
                ci_upper = d_100 + spread

            predictions.append(ExhaustionPrediction(
                resource=snap.resource,
                days_to_exhaustion=d_100,
                days_to_warning=d_warning,
                days_to_critical=d_critical,
                confidence_lower=ci_lower,
                confidence_upper=ci_upper,
                confidence_level=self.confidence_level,
            ))

        return predictions

    # ------------------------------------------------------------------
    # Private: right-sizing
    # ------------------------------------------------------------------

    def _right_size(
        self, comp: Component, snapshots: list[ResourceSnapshot],
    ) -> SizingRecommendation:
        """Determine if a component is over/under/right-provisioned."""
        # Find the highest-utilization resource
        peak_snap = max(snapshots, key=lambda s: s.utilization_percent)
        util = peak_snap.utilization_percent

        if util >= _WARNING_THRESHOLD:
            verdict = SizingVerdict.UNDER_PROVISIONED
            # Need more replicas to bring utilization down
            target_util = 60.0
            factor = util / target_util
            recommended = max(comp.replicas, math.ceil(comp.replicas * factor))
            justification = (
                f"{peak_snap.resource.value} at {util:.1f}% utilization exceeds "
                f"the {_WARNING_THRESHOLD}% warning threshold. "
                f"Scale from {comp.replicas} to {recommended} replicas."
            )
        elif util < 30.0 and comp.replicas > 1:
            verdict = SizingVerdict.OVER_PROVISIONED
            # Can reduce replicas
            target_util = 50.0
            factor = util / target_util
            recommended = max(1, math.ceil(comp.replicas * factor))
            justification = (
                f"{peak_snap.resource.value} at {util:.1f}% utilization is well below "
                f"the optimal range. Consider scaling from {comp.replicas} to "
                f"{recommended} replicas to reduce costs."
            )
        else:
            verdict = SizingVerdict.RIGHT_SIZED
            recommended = comp.replicas
            justification = (
                f"Peak resource ({peak_snap.resource.value}) at {util:.1f}% "
                f"utilization is within the optimal 30-80% range."
            )

        return SizingRecommendation(
            component_id=comp.id,
            verdict=verdict,
            current_replicas=comp.replicas,
            recommended_replicas=recommended,
            primary_resource=peak_snap.resource,
            utilization_percent=round(util, 2),
            justification=justification,
        )

    # ------------------------------------------------------------------
    # Private: burst analysis
    # ------------------------------------------------------------------

    def _burst_analysis(self, comp: Component) -> BurstCapacityResult:
        """Analyze ability to handle traffic spikes."""
        snapshots = self._build_resource_snapshots(comp)
        peak_snap = max(snapshots, key=lambda s: s.utilization_percent)
        util = peak_snap.utilization_percent

        headroom = 100.0 - util
        if util > 0:
            max_mult = 100.0 / util
        else:
            max_mult = 10.0  # arbitrary safe ceiling

        # Autoscaling bonus: can handle higher bursts
        if comp.autoscaling.enabled:
            scale_factor = comp.autoscaling.max_replicas / max(comp.autoscaling.min_replicas, 1)
            max_mult *= scale_factor

        return BurstCapacityResult(
            component_id=comp.id,
            can_handle_2x=max_mult >= 2.0,
            can_handle_3x=max_mult >= 3.0,
            can_handle_5x=max_mult >= 5.0,
            max_burst_multiplier=round(max_mult, 2),
            limiting_resource=peak_snap.resource,
            burst_headroom_percent=round(headroom, 2),
        )

    # ------------------------------------------------------------------
    # Private: peak vs steady-state
    # ------------------------------------------------------------------

    def _peak_steady_analysis(
        self, comp: Component, snapshots: list[ResourceSnapshot],
    ) -> PeakSteadyAnalysis:
        """Compare peak vs steady-state capacity needs."""
        peak_mult = self.peak_multiplier_override
        if peak_mult is None:
            peak_mult = _PEAK_MULTIPLIERS.get(comp.type, 1.5)

        # Steady-state: average of all resource utilizations
        utils = [s.utilization_percent for s in snapshots]
        steady = statistics.mean(utils) if utils else 0.0
        peak = min(100.0, steady * peak_mult)
        ratio = peak / steady if steady > 0 else 0.0

        return PeakSteadyAnalysis(
            component_id=comp.id,
            steady_state_util=round(steady, 2),
            peak_util=round(peak, 2),
            peak_to_steady_ratio=round(ratio, 2),
            requires_burst_capacity=peak > _WARNING_THRESHOLD,
        )

    # ------------------------------------------------------------------
    # Private: bottleneck detection
    # ------------------------------------------------------------------

    def _detect_bottleneck(
        self, comp: Component, snapshots: list[ResourceSnapshot],
    ) -> BottleneckInfo | None:
        """Identify cross-resource bottlenecks."""
        sorted_snaps = sorted(
            snapshots, key=lambda s: s.utilization_percent, reverse=True,
        )
        if not sorted_snaps:
            return None

        top = sorted_snaps[0]
        if top.utilization_percent < 50.0:
            return None  # no bottleneck at low utilization

        secondary = [
            (s.resource, round(s.utilization_percent, 2))
            for s in sorted_snaps[1:3]
            if s.utilization_percent > 30.0
        ]

        # Cascading risk: high utilization + multiple stressed resources
        cascading = (
            top.utilization_percent >= 70.0
            and len(secondary) >= 1
            and secondary[0][1] >= 50.0
        )

        return BottleneckInfo(
            component_id=comp.id,
            bottleneck_resource=top.resource,
            utilization_percent=round(top.utilization_percent, 2),
            secondary_resources=secondary,
            cascading_risk=cascading,
        )

    # ------------------------------------------------------------------
    # Private: reservation planning
    # ------------------------------------------------------------------

    def _reservation_plan(
        self, comp: Component, snapshots: list[ResourceSnapshot],
    ) -> ReservationPlan:
        """Generate reservation / savings plan recommendation."""
        hourly = _DEFAULT_HOURLY_COST_PER_REPLICA.get(comp.type, 0.05)
        monthly_base = hourly * 730.0 * comp.replicas  # ~730 hours/month

        utils = [s.utilization_percent for s in snapshots]
        avg_util = statistics.mean(utils) if utils else 0.0

        # Steady baseline: portion suitable for reservation
        steady_fraction = min(1.0, avg_util / 100.0 * 0.8)
        reserved_units = comp.replicas * steady_fraction
        on_demand_units = comp.replicas - reserved_units

        # Determine best reservation type based on steady utilization
        if avg_util >= 60.0:
            rec_type = ReservationType.RESERVED_1Y
            savings_pct = 30.0
            break_even = 7
        elif avg_util >= 40.0:
            rec_type = ReservationType.SAVINGS_PLAN
            savings_pct = 20.0
            break_even = 10
        elif avg_util >= 20.0:
            rec_type = ReservationType.RESERVED_1Y
            savings_pct = 15.0
            break_even = 12
        else:
            rec_type = ReservationType.ON_DEMAND
            savings_pct = 0.0
            break_even = 0

        estimated_savings = monthly_base * savings_pct / 100.0

        return ReservationPlan(
            component_id=comp.id,
            recommended_type=rec_type,
            base_capacity_units=float(comp.replicas),
            reserved_capacity_units=round(reserved_units, 2),
            on_demand_buffer_units=round(on_demand_units, 2),
            estimated_monthly_savings=round(estimated_savings, 2),
            break_even_months=break_even,
        )

    # ------------------------------------------------------------------
    # Private: risk classification
    # ------------------------------------------------------------------

    def _classify_risk(
        self,
        comp: Component,
        predictions: list[ExhaustionPrediction],
        snapshots: list[ResourceSnapshot],
    ) -> CapacityRiskLevel:
        """Classify overall capacity risk for a component."""
        # Immediate risk from current utilization
        max_util = max(
            (s.utilization_percent for s in snapshots), default=0.0,
        )

        if max_util >= _CRITICAL_THRESHOLD:
            return CapacityRiskLevel.CRITICAL

        # Check exhaustion timelines
        min_exhaustion: float | None = None
        for pred in predictions:
            if pred.days_to_exhaustion is not None:
                if min_exhaustion is None or pred.days_to_exhaustion < min_exhaustion:
                    min_exhaustion = pred.days_to_exhaustion

        if min_exhaustion is not None and min_exhaustion <= 7:
            return CapacityRiskLevel.CRITICAL
        if max_util >= _WARNING_THRESHOLD or (
            min_exhaustion is not None and min_exhaustion <= 30
        ):
            return CapacityRiskLevel.HIGH
        if max_util >= 50.0 or (
            min_exhaustion is not None and min_exhaustion <= 90
        ):
            return CapacityRiskLevel.MODERATE
        return CapacityRiskLevel.LOW

    # ------------------------------------------------------------------
    # Private: cost projection
    # ------------------------------------------------------------------

    def _build_cost_projection(
        self, reports: list[ComponentCapacityReport],
    ) -> CostProjection:
        """Build aggregate cost projection from component reports."""
        current_monthly = 0.0
        for cr in reports:
            comp = self.graph.get_component(cr.component_id)
            if comp is None:
                continue
            hourly = comp.cost_profile.hourly_infra_cost
            if hourly <= 0:
                hourly = _DEFAULT_HOURLY_COST_PER_REPLICA.get(comp.type, 0.05) * comp.replicas
            current_monthly += hourly * 730.0

        if current_monthly <= 0:
            current_monthly = 1.0  # avoid division by zero in projections

        # Project forward based on growth
        proj_3m = self._project_cost(current_monthly, 90)
        proj_6m = self._project_cost(current_monthly, 180)
        proj_12m = self._project_cost(current_monthly, 365)

        # Average reservation savings across components
        savings_list = [
            cr.reservation.estimated_monthly_savings for cr in reports
        ]
        total_savings = sum(savings_list)
        savings_pct = (total_savings / current_monthly * 100.0) if current_monthly > 0 else 0.0

        # Recommended reservation type = most common among components
        type_counts: dict[ReservationType, int] = {}
        for cr in reports:
            rt = cr.reservation.recommended_type
            type_counts[rt] = type_counts.get(rt, 0) + 1
        recommended = max(type_counts, key=type_counts.get) if type_counts else ReservationType.ON_DEMAND  # type: ignore[arg-type]

        return CostProjection(
            current_monthly_cost=round(current_monthly, 2),
            projected_monthly_cost_3m=round(proj_3m, 2),
            projected_monthly_cost_6m=round(proj_6m, 2),
            projected_monthly_cost_12m=round(proj_12m, 2),
            reservation_savings_percent=round(savings_pct, 2),
            recommended_reservation=recommended,
        )

    def _project_cost(self, current: float, days: int) -> float:
        """Project cost forward using the growth model."""
        return project_value(
            current, days, self.growth_rate, self.growth_model,
        )

    # ------------------------------------------------------------------
    # Private: recommendations
    # ------------------------------------------------------------------

    def _build_recommendations(
        self,
        reports: list[ComponentCapacityReport],
        bottlenecks: list[BottleneckInfo],
        cost: CostProjection,
    ) -> list[str]:
        """Generate actionable recommendations."""
        recs: list[str] = []

        # Critical components
        critical = [r for r in reports if r.risk_level == CapacityRiskLevel.CRITICAL]
        if critical:
            ids = ", ".join(r.component_id for r in critical[:3])
            recs.append(
                f"CRITICAL: {len(critical)} component(s) at critical capacity: {ids}. "
                f"Immediate scaling required."
            )

        # High-risk components
        high = [r for r in reports if r.risk_level == CapacityRiskLevel.HIGH]
        if high:
            ids = ", ".join(r.component_id for r in high[:3])
            recs.append(
                f"HIGH: {len(high)} component(s) approaching capacity limits: {ids}. "
                f"Plan scaling within 30 days."
            )

        # Under-provisioned
        under = [
            r for r in reports
            if r.sizing.verdict == SizingVerdict.UNDER_PROVISIONED
        ]
        if under:
            for u in under[:3]:
                recs.append(
                    f"SCALE UP: {u.component_id} needs {u.sizing.recommended_replicas} "
                    f"replicas (currently {u.sizing.current_replicas})."
                )

        # Over-provisioned
        over = [
            r for r in reports
            if r.sizing.verdict == SizingVerdict.OVER_PROVISIONED
        ]
        if over:
            for o in over[:3]:
                recs.append(
                    f"RIGHT-SIZE: {o.component_id} is over-provisioned. Consider "
                    f"reducing from {o.sizing.current_replicas} to "
                    f"{o.sizing.recommended_replicas} replicas."
                )

        # Burst capacity warnings
        no_burst = [r for r in reports if not r.burst.can_handle_3x]
        if no_burst:
            ids = ", ".join(r.component_id for r in no_burst[:3])
            recs.append(
                f"BURST: {len(no_burst)} component(s) cannot handle 3x traffic "
                f"spikes: {ids}. Consider autoscaling or additional headroom."
            )

        # Cross-resource bottlenecks
        cascading = [b for b in bottlenecks if b.cascading_risk]
        if cascading:
            ids = ", ".join(b.component_id for b in cascading[:3])
            recs.append(
                f"BOTTLENECK: {len(cascading)} component(s) have cascading "
                f"bottleneck risk: {ids}."
            )

        # Cost savings
        if cost.reservation_savings_percent > 5.0:
            recs.append(
                f"COST: Switch to {cost.recommended_reservation.value} to save "
                f"~{cost.reservation_savings_percent:.1f}% on monthly costs."
            )

        if not recs:
            recs.append(
                "All components are within healthy capacity ranges. "
                "No immediate action required."
            )

        return recs
