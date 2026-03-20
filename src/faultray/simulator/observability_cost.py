# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Observability Cost Optimizer.

Analyzes and optimizes the cost of observability infrastructure (logging,
metrics, tracing, profiling, RUM, synthetics).  Provides vendor cost
comparison, sampling recommendations, redundancy detection, retention
policy advice, detection coverage analysis and cost growth projections.
"""

from __future__ import annotations

import math
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ObservabilityPillar(str, Enum):
    """Pillars of observability."""

    METRICS = "metrics"
    LOGS = "logs"
    TRACES = "traces"
    PROFILING = "profiling"
    RUM = "rum"
    SYNTHETICS = "synthetics"


class Vendor(str, Enum):
    """Observability vendor / platform."""

    DATADOG = "datadog"
    NEW_RELIC = "new_relic"
    SPLUNK = "splunk"
    GRAFANA_CLOUD = "grafana_cloud"
    ELASTIC = "elastic"
    AWS_CLOUDWATCH = "aws_cloudwatch"
    PROMETHEUS_SELF_HOSTED = "prometheus_self_hosted"
    CUSTOM = "custom"


# ---------------------------------------------------------------------------
# Vendor cost-per-unit tables (USD)
# ---------------------------------------------------------------------------

# cost per GB/day for logs, per million/day for metrics/traces, per day
# for profiling/rum/synthetics
_VENDOR_COST_PER_UNIT: dict[Vendor, dict[ObservabilityPillar, float]] = {
    Vendor.DATADOG: {
        ObservabilityPillar.METRICS: 8.0,
        ObservabilityPillar.LOGS: 2.50,
        ObservabilityPillar.TRACES: 5.0,
        ObservabilityPillar.PROFILING: 12.0,
        ObservabilityPillar.RUM: 15.0,
        ObservabilityPillar.SYNTHETICS: 10.0,
    },
    Vendor.NEW_RELIC: {
        ObservabilityPillar.METRICS: 7.0,
        ObservabilityPillar.LOGS: 2.0,
        ObservabilityPillar.TRACES: 4.5,
        ObservabilityPillar.PROFILING: 10.0,
        ObservabilityPillar.RUM: 12.0,
        ObservabilityPillar.SYNTHETICS: 8.0,
    },
    Vendor.SPLUNK: {
        ObservabilityPillar.METRICS: 9.0,
        ObservabilityPillar.LOGS: 3.0,
        ObservabilityPillar.TRACES: 6.0,
        ObservabilityPillar.PROFILING: 14.0,
        ObservabilityPillar.RUM: 16.0,
        ObservabilityPillar.SYNTHETICS: 11.0,
    },
    Vendor.GRAFANA_CLOUD: {
        ObservabilityPillar.METRICS: 4.0,
        ObservabilityPillar.LOGS: 1.5,
        ObservabilityPillar.TRACES: 3.0,
        ObservabilityPillar.PROFILING: 6.0,
        ObservabilityPillar.RUM: 8.0,
        ObservabilityPillar.SYNTHETICS: 5.0,
    },
    Vendor.ELASTIC: {
        ObservabilityPillar.METRICS: 5.0,
        ObservabilityPillar.LOGS: 1.8,
        ObservabilityPillar.TRACES: 3.5,
        ObservabilityPillar.PROFILING: 7.0,
        ObservabilityPillar.RUM: 9.0,
        ObservabilityPillar.SYNTHETICS: 6.0,
    },
    Vendor.AWS_CLOUDWATCH: {
        ObservabilityPillar.METRICS: 3.0,
        ObservabilityPillar.LOGS: 1.0,
        ObservabilityPillar.TRACES: 2.5,
        ObservabilityPillar.PROFILING: 5.0,
        ObservabilityPillar.RUM: 7.0,
        ObservabilityPillar.SYNTHETICS: 4.0,
    },
    Vendor.PROMETHEUS_SELF_HOSTED: {
        ObservabilityPillar.METRICS: 1.5,
        ObservabilityPillar.LOGS: 0.8,
        ObservabilityPillar.TRACES: 1.5,
        ObservabilityPillar.PROFILING: 3.0,
        ObservabilityPillar.RUM: 4.0,
        ObservabilityPillar.SYNTHETICS: 2.0,
    },
    Vendor.CUSTOM: {
        ObservabilityPillar.METRICS: 2.0,
        ObservabilityPillar.LOGS: 1.0,
        ObservabilityPillar.TRACES: 2.0,
        ObservabilityPillar.PROFILING: 4.0,
        ObservabilityPillar.RUM: 5.0,
        ObservabilityPillar.SYNTHETICS: 3.0,
    },
}

# Retention cost multiplier — cost factor per 30-day retention window.
# First 30 days = 1.0x, each subsequent 30-day window adds this fraction.
_RETENTION_COST_FACTOR_PER_30D = 0.15

# Default pillar priorities for coverage scoring (higher = more critical).
_PILLAR_DETECTION_WEIGHT: dict[ObservabilityPillar, float] = {
    ObservabilityPillar.METRICS: 1.0,
    ObservabilityPillar.LOGS: 0.9,
    ObservabilityPillar.TRACES: 0.8,
    ObservabilityPillar.PROFILING: 0.5,
    ObservabilityPillar.RUM: 0.4,
    ObservabilityPillar.SYNTHETICS: 0.6,
}

# Ideal minimum retention days per pillar.
_IDEAL_RETENTION: dict[ObservabilityPillar, int] = {
    ObservabilityPillar.METRICS: 90,
    ObservabilityPillar.LOGS: 30,
    ObservabilityPillar.TRACES: 14,
    ObservabilityPillar.PROFILING: 7,
    ObservabilityPillar.RUM: 30,
    ObservabilityPillar.SYNTHETICS: 90,
}

# Maximum recommended retention days per pillar.
_MAX_RECOMMENDED_RETENTION: dict[ObservabilityPillar, int] = {
    ObservabilityPillar.METRICS: 365,
    ObservabilityPillar.LOGS: 90,
    ObservabilityPillar.TRACES: 30,
    ObservabilityPillar.PROFILING: 14,
    ObservabilityPillar.RUM: 90,
    ObservabilityPillar.SYNTHETICS: 365,
}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ObservabilityConfig(BaseModel):
    """Configuration for a single observability data stream."""

    pillar: ObservabilityPillar
    vendor: Vendor
    volume_per_day: float  # GB for logs, millions for metrics/traces
    retention_days: int
    cost_per_unit: float  # USD per unit per day
    sampling_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    compression_ratio: float = Field(default=1.0, gt=0.0)


class OptimizationAction(BaseModel):
    """A single optimization action with expected impact."""

    action: str
    pillar: ObservabilityPillar
    monthly_savings: float
    detection_impact: str  # none / low / medium / high
    implementation_effort: str  # low / medium / high


class CostOptimization(BaseModel):
    """Cost optimization analysis result."""

    current_monthly_cost: float
    optimized_monthly_cost: float
    savings_percent: float
    optimizations: list[OptimizationAction] = Field(default_factory=list)
    risk_of_blind_spots: float  # 0-100
    recommendations: list[str] = Field(default_factory=list)


class SamplingRecommendation(BaseModel):
    """Sampling rate recommendation for a pillar."""

    pillar: ObservabilityPillar
    current_sampling_rate: float
    recommended_sampling_rate: float
    estimated_monthly_savings: float
    detection_impact: str


class RedundancyFinding(BaseModel):
    """A finding of redundant telemetry."""

    pillars: list[ObservabilityPillar]
    vendors: list[Vendor]
    description: str
    monthly_waste: float
    recommendation: str


class VendorCostBreakdown(BaseModel):
    """Cost breakdown for a single vendor."""

    vendor: Vendor
    monthly_cost: float
    per_pillar: dict[str, float] = Field(default_factory=dict)


class VendorCostComparison(BaseModel):
    """Comparison of costs across vendors."""

    current_vendors: list[VendorCostBreakdown] = Field(default_factory=list)
    cheapest_vendor: Vendor | None = None
    cheapest_monthly_cost: float = 0.0
    potential_savings: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class PillarCoverage(BaseModel):
    """Detection coverage for a single pillar."""

    pillar: ObservabilityPillar
    covered: bool
    sampling_rate: float
    retention_days: int
    coverage_score: float  # 0-100


class DetectionCoverage(BaseModel):
    """Detection coverage report."""

    overall_score: float  # 0-100
    per_pillar: list[PillarCoverage] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class RetentionRecommendation(BaseModel):
    """Retention policy recommendation for a pillar."""

    pillar: ObservabilityPillar
    current_retention_days: int
    recommended_retention_days: int
    reason: str
    monthly_savings: float


class CostGrowthDataPoint(BaseModel):
    """A single data point in cost growth projection."""

    month: int
    monthly_cost: float
    cumulative_cost: float


class CostGrowthProjection(BaseModel):
    """Projected cost growth over time."""

    initial_monthly_cost: float
    final_monthly_cost: float
    total_cost: float
    growth_rate: float
    months: int
    data_points: list[CostGrowthDataPoint] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class ObservabilityCostReport(BaseModel):
    """Full observability cost report."""

    total_monthly_cost: float
    per_pillar_cost: dict[str, float] = Field(default_factory=dict)
    per_vendor_cost: dict[str, float] = Field(default_factory=dict)
    optimization: CostOptimization
    component_count: int
    config_count: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _monthly_cost_for_config(cfg: ObservabilityConfig) -> float:
    """Calculate monthly cost for a single observability config.

    Cost = volume_per_day * cost_per_unit * sampling_rate / compression_ratio * 30
         + retention surcharge for days beyond 30.
    """
    effective_volume = cfg.volume_per_day * cfg.sampling_rate / cfg.compression_ratio
    base_daily = effective_volume * cfg.cost_per_unit
    base_monthly = base_daily * 30.0

    # Retention surcharge: each 30-day block beyond the first adds a fraction.
    extra_windows = max(0, (cfg.retention_days - 30)) / 30.0
    retention_multiplier = 1.0 + extra_windows * _RETENTION_COST_FACTOR_PER_30D
    return base_monthly * retention_multiplier


def _detection_impact_for_sampling(current: float, proposed: float) -> str:
    """Classify detection impact when changing sampling rate."""
    if proposed >= current:
        return "none"
    ratio = proposed / current if current > 0 else 1.0
    if ratio >= 0.8:
        return "low"
    if ratio >= 0.5:
        return "medium"
    return "high"


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ObservabilityCostEngine:
    """Stateless engine for observability cost analysis and optimization."""

    # -- analyze_cost -------------------------------------------------------

    def analyze_cost(
        self,
        graph: InfraGraph,
        configs: list[ObservabilityConfig],
    ) -> ObservabilityCostReport:
        """Produce a full cost report for the given configs and infra graph."""
        per_pillar: dict[str, float] = {}
        per_vendor: dict[str, float] = {}

        for cfg in configs:
            cost = _monthly_cost_for_config(cfg)
            pillar_key = cfg.pillar.value
            vendor_key = cfg.vendor.value
            per_pillar[pillar_key] = per_pillar.get(pillar_key, 0.0) + cost
            per_vendor[vendor_key] = per_vendor.get(vendor_key, 0.0) + cost

        total = sum(per_pillar.values())
        optimization = self._build_optimization(configs, total)

        return ObservabilityCostReport(
            total_monthly_cost=round(total, 2),
            per_pillar_cost={k: round(v, 2) for k, v in per_pillar.items()},
            per_vendor_cost={k: round(v, 2) for k, v in per_vendor.items()},
            optimization=optimization,
            component_count=len(graph.components),
            config_count=len(configs),
        )

    # -- optimize_sampling --------------------------------------------------

    def optimize_sampling(
        self,
        configs: list[ObservabilityConfig],
        budget: float,
    ) -> list[SamplingRecommendation]:
        """Recommend per-pillar sampling rates to fit within *budget*."""
        total_cost = sum(_monthly_cost_for_config(c) for c in configs)
        if total_cost <= 0:
            return []

        recs: list[SamplingRecommendation] = []
        if total_cost <= budget:
            # Already within budget — no changes needed.
            for cfg in configs:
                recs.append(
                    SamplingRecommendation(
                        pillar=cfg.pillar,
                        current_sampling_rate=cfg.sampling_rate,
                        recommended_sampling_rate=cfg.sampling_rate,
                        estimated_monthly_savings=0.0,
                        detection_impact="none",
                    )
                )
            return recs

        # Reduce sampling proportionally, prioritising high-weight pillars.
        reduction_ratio = budget / total_cost

        for cfg in configs:
            weight = _PILLAR_DETECTION_WEIGHT.get(cfg.pillar, 0.5)
            # Higher weight pillars get less reduction.
            pillar_ratio = min(1.0, reduction_ratio + (1.0 - reduction_ratio) * weight)
            new_rate = max(0.01, min(1.0, cfg.sampling_rate * pillar_ratio))
            old_cost = _monthly_cost_for_config(cfg)
            new_cfg = cfg.model_copy(update={"sampling_rate": new_rate})
            new_cost = _monthly_cost_for_config(new_cfg)
            savings = old_cost - new_cost

            recs.append(
                SamplingRecommendation(
                    pillar=cfg.pillar,
                    current_sampling_rate=cfg.sampling_rate,
                    recommended_sampling_rate=round(new_rate, 4),
                    estimated_monthly_savings=round(savings, 2),
                    detection_impact=_detection_impact_for_sampling(
                        cfg.sampling_rate, new_rate
                    ),
                )
            )

        return recs

    # -- detect_redundant_telemetry -----------------------------------------

    def detect_redundant_telemetry(
        self,
        configs: list[ObservabilityConfig],
    ) -> list[RedundancyFinding]:
        """Detect configs that overlap on the same pillar across vendors."""
        pillar_map: dict[ObservabilityPillar, list[ObservabilityConfig]] = {}
        for cfg in configs:
            pillar_map.setdefault(cfg.pillar, []).append(cfg)

        findings: list[RedundancyFinding] = []
        for pillar, cfgs in pillar_map.items():
            vendors = list({c.vendor for c in cfgs})
            if len(vendors) > 1:
                costs = [_monthly_cost_for_config(c) for c in cfgs]
                min_cost = min(costs)
                waste = sum(costs) - min_cost
                findings.append(
                    RedundancyFinding(
                        pillars=[pillar],
                        vendors=vendors,
                        description=(
                            f"Multiple vendors ({', '.join(v.value for v in vendors)}) "
                            f"collecting {pillar.value} data"
                        ),
                        monthly_waste=round(waste, 2),
                        recommendation=(
                            f"Consolidate {pillar.value} to a single vendor "
                            f"to save ${round(waste, 2)}/month"
                        ),
                    )
                )
            elif len(cfgs) > 1:
                # Same vendor, same pillar — duplicate streams.
                costs = [_monthly_cost_for_config(c) for c in cfgs]
                total = sum(costs)
                max_cost = max(costs)
                waste = total - max_cost
                if waste > 0:
                    findings.append(
                        RedundancyFinding(
                            pillars=[pillar],
                            vendors=[cfgs[0].vendor],
                            description=(
                                f"Duplicate {pillar.value} streams on "
                                f"{cfgs[0].vendor.value}"
                            ),
                            monthly_waste=round(waste, 2),
                            recommendation=(
                                f"Merge duplicate {pillar.value} streams to eliminate "
                                f"${round(waste, 2)}/month waste"
                            ),
                        )
                    )
        return findings

    # -- estimate_vendor_cost -----------------------------------------------

    def estimate_vendor_cost(
        self,
        configs: list[ObservabilityConfig],
    ) -> VendorCostComparison:
        """Compare current vendor costs and suggest cheapest alternative."""
        # Build current vendor breakdown.
        vendor_map: dict[Vendor, dict[str, float]] = {}
        for cfg in configs:
            cost = _monthly_cost_for_config(cfg)
            if cfg.vendor not in vendor_map:
                vendor_map[cfg.vendor] = {}
            pp = vendor_map[cfg.vendor]
            pp[cfg.pillar.value] = pp.get(cfg.pillar.value, 0.0) + cost

        current_breakdowns: list[VendorCostBreakdown] = []
        for vendor, pp in vendor_map.items():
            current_breakdowns.append(
                VendorCostBreakdown(
                    vendor=vendor,
                    monthly_cost=round(sum(pp.values()), 2),
                    per_pillar=pp,
                )
            )

        current_total = sum(b.monthly_cost for b in current_breakdowns)

        # Estimate cost if everything were on each single vendor.
        best_vendor: Vendor | None = None
        best_cost = math.inf

        for candidate in Vendor:
            vendor_rates = _VENDOR_COST_PER_UNIT.get(candidate, {})
            candidate_cost = 0.0
            for cfg in configs:
                rate = vendor_rates.get(cfg.pillar, cfg.cost_per_unit)
                effective_volume = (
                    cfg.volume_per_day * cfg.sampling_rate / cfg.compression_ratio
                )
                daily = effective_volume * rate
                monthly = daily * 30.0
                extra_windows = max(0, (cfg.retention_days - 30)) / 30.0
                retention_mult = 1.0 + extra_windows * _RETENTION_COST_FACTOR_PER_30D
                candidate_cost += monthly * retention_mult

            if candidate_cost < best_cost:
                best_cost = candidate_cost
                best_vendor = candidate

        potential_savings = max(0.0, current_total - best_cost) if best_vendor else 0.0
        recs: list[str] = []
        if potential_savings > 0 and best_vendor:
            recs.append(
                f"Consolidating to {best_vendor.value} could save "
                f"${round(potential_savings, 2)}/month"
            )
        if len(vendor_map) > 1:
            recs.append(
                "Using multiple vendors increases operational complexity; "
                "consider vendor consolidation"
            )

        return VendorCostComparison(
            current_vendors=current_breakdowns,
            cheapest_vendor=best_vendor,
            cheapest_monthly_cost=round(best_cost, 2) if best_vendor else 0.0,
            potential_savings=round(potential_savings, 2),
            recommendations=recs,
        )

    # -- calculate_detection_coverage ---------------------------------------

    def calculate_detection_coverage(
        self,
        graph: InfraGraph,
        configs: list[ObservabilityConfig],
    ) -> DetectionCoverage:
        """Calculate detection coverage across observability pillars."""
        covered_pillars: dict[ObservabilityPillar, list[ObservabilityConfig]] = {}
        for cfg in configs:
            covered_pillars.setdefault(cfg.pillar, []).append(cfg)

        per_pillar: list[PillarCoverage] = []
        gaps: list[str] = []
        recommendations: list[str] = []

        for pillar in ObservabilityPillar:
            cfgs = covered_pillars.get(pillar, [])
            if not cfgs:
                per_pillar.append(
                    PillarCoverage(
                        pillar=pillar,
                        covered=False,
                        sampling_rate=0.0,
                        retention_days=0,
                        coverage_score=0.0,
                    )
                )
                gaps.append(f"No {pillar.value} collection configured")
                recommendations.append(f"Add {pillar.value} collection")
                continue

            max_rate = max(c.sampling_rate for c in cfgs)
            max_retention = max(c.retention_days for c in cfgs)
            ideal_retention = _IDEAL_RETENTION.get(pillar, 30)

            # Score components: sampling (50%) + retention adequacy (50%)
            sampling_score = max_rate * 50.0
            retention_score = min(1.0, max_retention / ideal_retention) * 50.0
            score = sampling_score + retention_score

            per_pillar.append(
                PillarCoverage(
                    pillar=pillar,
                    covered=True,
                    sampling_rate=max_rate,
                    retention_days=max_retention,
                    coverage_score=round(score, 2),
                )
            )

            if max_rate < 0.5:
                gaps.append(f"{pillar.value} sampling rate is low ({max_rate})")
                recommendations.append(
                    f"Increase {pillar.value} sampling rate to at least 0.5"
                )
            if max_retention < ideal_retention:
                gaps.append(
                    f"{pillar.value} retention ({max_retention}d) is below "
                    f"recommended ({ideal_retention}d)"
                )
                recommendations.append(
                    f"Increase {pillar.value} retention to {ideal_retention} days"
                )

        # Overall score — weighted average.
        total_weight = sum(_PILLAR_DETECTION_WEIGHT.values())
        weighted_sum = 0.0
        for pc in per_pillar:
            w = _PILLAR_DETECTION_WEIGHT.get(pc.pillar, 0.5)
            weighted_sum += pc.coverage_score * w

        overall = weighted_sum / total_weight if total_weight > 0 else 0.0

        return DetectionCoverage(
            overall_score=round(overall, 2),
            per_pillar=per_pillar,
            gaps=gaps,
            recommendations=recommendations,
        )

    # -- recommend_retention_policy ------------------------------------------

    def recommend_retention_policy(
        self,
        configs: list[ObservabilityConfig],
    ) -> list[RetentionRecommendation]:
        """Recommend retention policies per config."""
        recs: list[RetentionRecommendation] = []
        for cfg in configs:
            ideal_min = _IDEAL_RETENTION.get(cfg.pillar, 30)
            ideal_max = _MAX_RECOMMENDED_RETENTION.get(cfg.pillar, 90)

            if cfg.retention_days > ideal_max:
                # Reduce to max recommended.
                old_cost = _monthly_cost_for_config(cfg)
                new_cfg = cfg.model_copy(update={"retention_days": ideal_max})
                new_cost = _monthly_cost_for_config(new_cfg)
                savings = old_cost - new_cost
                recs.append(
                    RetentionRecommendation(
                        pillar=cfg.pillar,
                        current_retention_days=cfg.retention_days,
                        recommended_retention_days=ideal_max,
                        reason=(
                            f"{cfg.pillar.value} retention of {cfg.retention_days}d "
                            f"exceeds recommended maximum of {ideal_max}d"
                        ),
                        monthly_savings=round(savings, 2),
                    )
                )
            elif cfg.retention_days < ideal_min:
                # Increase to minimum recommended — this will cost more.
                old_cost = _monthly_cost_for_config(cfg)
                new_cfg = cfg.model_copy(update={"retention_days": ideal_min})
                new_cost = _monthly_cost_for_config(new_cfg)
                diff = new_cost - old_cost
                recs.append(
                    RetentionRecommendation(
                        pillar=cfg.pillar,
                        current_retention_days=cfg.retention_days,
                        recommended_retention_days=ideal_min,
                        reason=(
                            f"{cfg.pillar.value} retention of {cfg.retention_days}d "
                            f"is below recommended minimum of {ideal_min}d"
                        ),
                        monthly_savings=round(-diff, 2),  # negative savings = extra cost
                    )
                )
            else:
                # Within range — no change.
                recs.append(
                    RetentionRecommendation(
                        pillar=cfg.pillar,
                        current_retention_days=cfg.retention_days,
                        recommended_retention_days=cfg.retention_days,
                        reason=f"{cfg.pillar.value} retention is within recommended range",
                        monthly_savings=0.0,
                    )
                )
        return recs

    # -- simulate_cost_growth ------------------------------------------------

    def simulate_cost_growth(
        self,
        configs: list[ObservabilityConfig],
        growth_rate: float,
        months: int,
    ) -> CostGrowthProjection:
        """Project cost growth assuming volume grows at *growth_rate* per month."""
        initial = sum(_monthly_cost_for_config(c) for c in configs)
        data_points: list[CostGrowthDataPoint] = []
        cumulative = 0.0

        for m in range(1, months + 1):
            factor = (1.0 + growth_rate) ** (m - 1)
            monthly = initial * factor
            cumulative += monthly
            data_points.append(
                CostGrowthDataPoint(
                    month=m,
                    monthly_cost=round(monthly, 2),
                    cumulative_cost=round(cumulative, 2),
                )
            )

        final = data_points[-1].monthly_cost if data_points else initial
        total = data_points[-1].cumulative_cost if data_points else 0.0

        recs: list[str] = []
        if months > 0 and final > initial * 2:
            recs.append(
                "Cost will more than double over the projection period; "
                "consider aggressive sampling and retention optimization"
            )
        if growth_rate > 0.1:
            recs.append(
                f"Growth rate ({growth_rate:.0%}) is high; "
                "implement volume controls and sampling"
            )

        return CostGrowthProjection(
            initial_monthly_cost=round(initial, 2),
            final_monthly_cost=round(final, 2),
            total_cost=round(total, 2),
            growth_rate=growth_rate,
            months=months,
            data_points=data_points,
            recommendations=recs,
        )

    # -- internal helpers ---------------------------------------------------

    def _build_optimization(
        self,
        configs: list[ObservabilityConfig],
        current_total: float,
    ) -> CostOptimization:
        """Build optimization suggestions."""
        actions: list[OptimizationAction] = []
        recommendations: list[str] = []

        for cfg in configs:
            cost = _monthly_cost_for_config(cfg)
            # Suggest sampling reduction for high-volume streams.
            if cfg.sampling_rate > 0.5 and cfg.volume_per_day > 1.0:
                target_rate = max(0.1, cfg.sampling_rate * 0.5)
                new_cfg = cfg.model_copy(update={"sampling_rate": target_rate})
                new_cost = _monthly_cost_for_config(new_cfg)
                savings = cost - new_cost
                if savings > 0:
                    actions.append(
                        OptimizationAction(
                            action=f"Reduce {cfg.pillar.value} sampling to {target_rate:.0%}",
                            pillar=cfg.pillar,
                            monthly_savings=round(savings, 2),
                            detection_impact=_detection_impact_for_sampling(
                                cfg.sampling_rate, target_rate
                            ),
                            implementation_effort="low",
                        )
                    )

            # Suggest retention reduction for overly long retention.
            max_rec = _MAX_RECOMMENDED_RETENTION.get(cfg.pillar, 90)
            if cfg.retention_days > max_rec:
                new_cfg = cfg.model_copy(update={"retention_days": max_rec})
                new_cost = _monthly_cost_for_config(new_cfg)
                savings = cost - new_cost
                if savings > 0:
                    actions.append(
                        OptimizationAction(
                            action=(
                                f"Reduce {cfg.pillar.value} retention from "
                                f"{cfg.retention_days}d to {max_rec}d"
                            ),
                            pillar=cfg.pillar,
                            monthly_savings=round(savings, 2),
                            detection_impact="low",
                            implementation_effort="medium",
                        )
                    )

            # Suggest compression if ratio is 1.0
            if cfg.compression_ratio <= 1.0 and cfg.pillar in (
                ObservabilityPillar.LOGS,
                ObservabilityPillar.TRACES,
            ):
                compressed_cfg = cfg.model_copy(update={"compression_ratio": 3.0})
                compressed_cost = _monthly_cost_for_config(compressed_cfg)
                savings = cost - compressed_cost
                if savings > 0:
                    actions.append(
                        OptimizationAction(
                            action=f"Enable compression for {cfg.pillar.value}",
                            pillar=cfg.pillar,
                            monthly_savings=round(savings, 2),
                            detection_impact="none",
                            implementation_effort="low",
                        )
                    )

        total_savings = sum(a.monthly_savings for a in actions)
        optimized = max(0.0, current_total - total_savings)
        savings_pct = (total_savings / current_total * 100.0) if current_total > 0 else 0.0

        # Blind-spot risk: higher when aggressive sampling reductions are suggested.
        high_impact_count = sum(
            1 for a in actions if a.detection_impact in ("medium", "high")
        )
        blind_risk = min(100.0, high_impact_count * 25.0)

        if len(actions) == 0:
            recommendations.append("Configuration is already cost-efficient")
        else:
            if total_savings > 0:
                recommendations.append(
                    f"Total potential savings: ${round(total_savings, 2)}/month"
                )
            if blind_risk > 50:
                recommendations.append(
                    "Warning: aggressive optimizations may create detection blind spots"
                )

        return CostOptimization(
            current_monthly_cost=round(current_total, 2),
            optimized_monthly_cost=round(optimized, 2),
            savings_percent=round(savings_pct, 2),
            optimizations=actions,
            risk_of_blind_spots=blind_risk,
            recommendations=recommendations,
        )
