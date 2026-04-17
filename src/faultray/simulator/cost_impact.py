# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Cost Impact Engine — Quantify the business cost of infrastructure failures.

Calculates downtime costs, SLA penalty exposure, and recovery costs
for each failure scenario to enable data-driven resilience investment.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CostTier(str, Enum):
    """Business impact tier classification."""
    CATASTROPHIC = "catastrophic"  # >$1M/hour
    CRITICAL = "critical"          # $100K-$1M/hour
    HIGH = "high"                  # $10K-$100K/hour
    MEDIUM = "medium"              # $1K-$10K/hour
    LOW = "low"                    # <$1K/hour


class CostCategory(str, Enum):
    """Categories of downtime cost."""
    REVENUE_LOSS = "revenue_loss"
    SLA_PENALTY = "sla_penalty"
    RECOVERY_COST = "recovery_cost"
    REPUTATION_COST = "reputation_cost"
    PRODUCTIVITY_LOSS = "productivity_loss"


@dataclass
class CostProfile:
    """Cost profile for a component or service."""
    revenue_per_hour: float = 0.0
    sla_penalty_per_violation: float = 0.0
    sla_threshold_minutes: float = 43.2  # 99.9% monthly
    recovery_cost_per_incident: float = 500.0
    engineer_hourly_rate: float = 150.0
    affected_users: int = 0
    reputation_multiplier: float = 1.0  # 1.0=normal, 2.0=high-profile


@dataclass
class CostBreakdown:
    """Detailed cost breakdown for a failure scenario."""
    scenario_name: str
    downtime_minutes: float
    revenue_loss: float = 0.0
    sla_penalty: float = 0.0
    recovery_cost: float = 0.0
    reputation_cost: float = 0.0
    productivity_loss: float = 0.0
    total_cost: float = 0.0
    cost_tier: CostTier = CostTier.LOW
    affected_components: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.total_cost = (
            self.revenue_loss + self.sla_penalty + self.recovery_cost +
            self.reputation_cost + self.productivity_loss
        )
        hourly = self.total_cost / max(self.downtime_minutes / 60, 1/60)
        if hourly > 1_000_000:
            self.cost_tier = CostTier.CATASTROPHIC
        elif hourly > 100_000:
            self.cost_tier = CostTier.CRITICAL
        elif hourly > 10_000:
            self.cost_tier = CostTier.HIGH
        elif hourly > 1_000:
            self.cost_tier = CostTier.MEDIUM
        else:
            self.cost_tier = CostTier.LOW


@dataclass
class AnnualCostProjection:
    """Annual cost projection based on failure probabilities."""
    expected_annual_cost: float = 0.0
    worst_case_annual_cost: float = 0.0
    best_case_annual_cost: float = 0.0
    expected_incidents_per_year: float = 0.0
    cost_by_category: dict[str, float] = field(default_factory=dict)
    top_cost_scenarios: list[CostBreakdown] = field(default_factory=list)
    roi_of_improvements: list[dict] = field(default_factory=list)


@dataclass
class ROIAnalysis:
    """ROI analysis for a resilience improvement."""
    improvement_name: str
    implementation_cost: float
    annual_cost_reduction: float
    payback_period_months: float
    five_year_roi_percent: float
    risk_reduction_percent: float


class CostImpactEngine:
    """Engine to calculate business impact of infrastructure failures."""

    def __init__(self, default_profile: Optional[CostProfile] = None):
        self.default_profile = default_profile or CostProfile()
        self.component_profiles: dict[str, CostProfile] = {}

    def set_component_profile(self, component_id: str, profile: CostProfile) -> None:
        """Set cost profile for a specific component."""
        self.component_profiles[component_id] = profile

    def get_profile(self, component_id: str) -> CostProfile:
        """Get cost profile for a component, falling back to default."""
        return self.component_profiles.get(component_id, self.default_profile)

    def calculate_scenario_cost(
        self,
        scenario_name: str,
        affected_components: list[str],
        downtime_minutes: float,
        cascade_depth: int = 1,
    ) -> CostBreakdown:
        """Calculate cost for a single failure scenario."""
        total_revenue = 0.0
        total_sla = 0.0
        total_recovery = 0.0
        total_reputation = 0.0
        total_productivity = 0.0

        for comp_id in affected_components:
            profile = self.get_profile(comp_id)

            # Revenue loss = hourly rate * downtime hours
            hours = downtime_minutes / 60
            revenue = profile.revenue_per_hour * hours
            total_revenue += revenue

            # SLA penalty if downtime exceeds threshold
            if downtime_minutes > profile.sla_threshold_minutes:
                overage = downtime_minutes - profile.sla_threshold_minutes
                violations = math.ceil(overage / profile.sla_threshold_minutes)
                total_sla += profile.sla_penalty_per_violation * violations

            # Recovery cost (scales with cascade depth)
            total_recovery += profile.recovery_cost_per_incident * cascade_depth

            # Reputation cost (higher for user-facing, scales with cascade)
            if profile.affected_users > 0:
                user_impact = min(profile.affected_users * 0.01 * hours, 50000)
                total_reputation += user_impact * profile.reputation_multiplier

            # Productivity loss (engineering time to investigate + fix)
            engineer_hours = max(1, downtime_minutes / 30) * cascade_depth
            total_productivity += profile.engineer_hourly_rate * engineer_hours

        breakdown = CostBreakdown(
            scenario_name=scenario_name,
            downtime_minutes=downtime_minutes,
            revenue_loss=round(total_revenue, 2),
            sla_penalty=round(total_sla, 2),
            recovery_cost=round(total_recovery, 2),
            reputation_cost=round(total_reputation, 2),
            productivity_loss=round(total_productivity, 2),
            affected_components=affected_components,
        )

        # Generate recommendations based on cost
        if breakdown.cost_tier in (CostTier.CATASTROPHIC, CostTier.CRITICAL):
            breakdown.recommendations.append(
                f"CRITICAL: This scenario costs ${breakdown.total_cost:,.0f}. "
                "Implement redundancy and automated failover immediately."
            )
        if total_sla > 0:
            breakdown.recommendations.append(
                f"SLA exposure: ${total_sla:,.0f} in penalties. "
                "Consider increasing redundancy to meet SLA thresholds."
            )
        if cascade_depth > 2:
            breakdown.recommendations.append(
                f"Cascade depth {cascade_depth} amplifies cost. "
                "Add circuit breakers to limit blast radius."
            )

        return breakdown

    def calculate_annual_projection(
        self,
        scenarios: list[CostBreakdown],
        incidents_per_year: float = 12.0,
    ) -> AnnualCostProjection:
        """Project annual cost exposure from scenario analysis."""
        if not scenarios:
            return AnnualCostProjection()

        total_scenario_cost = sum(s.total_cost for s in scenarios)
        avg_cost = total_scenario_cost / len(scenarios)

        cost_by_cat = {
            CostCategory.REVENUE_LOSS.value: sum(s.revenue_loss for s in scenarios),
            CostCategory.SLA_PENALTY.value: sum(s.sla_penalty for s in scenarios),
            CostCategory.RECOVERY_COST.value: sum(s.recovery_cost for s in scenarios),
            CostCategory.REPUTATION_COST.value: sum(s.reputation_cost for s in scenarios),
            CostCategory.PRODUCTIVITY_LOSS.value: sum(s.productivity_loss for s in scenarios),
        }

        sorted_scenarios = sorted(scenarios, key=lambda s: s.total_cost, reverse=True)

        return AnnualCostProjection(
            expected_annual_cost=round(avg_cost * incidents_per_year, 2),
            worst_case_annual_cost=round(sorted_scenarios[0].total_cost * incidents_per_year, 2),
            best_case_annual_cost=round(sorted_scenarios[-1].total_cost * incidents_per_year, 2),
            expected_incidents_per_year=incidents_per_year,
            cost_by_category=cost_by_cat,
            top_cost_scenarios=sorted_scenarios[:5],
        )

    def calculate_roi(
        self,
        improvement_name: str,
        implementation_cost: float,
        current_annual_cost: float,
        projected_annual_cost: float,
    ) -> ROIAnalysis:
        """Calculate ROI for a resilience improvement."""
        annual_savings = current_annual_cost - projected_annual_cost
        if annual_savings <= 0:
            return ROIAnalysis(
                improvement_name=improvement_name,
                implementation_cost=implementation_cost,
                annual_cost_reduction=0,
                payback_period_months=float('inf'),
                five_year_roi_percent=0,
                risk_reduction_percent=0,
            )

        payback_months = (implementation_cost / annual_savings) * 12
        five_year_net = (annual_savings * 5) - implementation_cost
        five_year_roi = (five_year_net / implementation_cost) * 100
        risk_reduction = (annual_savings / current_annual_cost) * 100

        return ROIAnalysis(
            improvement_name=improvement_name,
            implementation_cost=round(implementation_cost, 2),
            annual_cost_reduction=round(annual_savings, 2),
            payback_period_months=round(payback_months, 1),
            five_year_roi_percent=round(five_year_roi, 1),
            risk_reduction_percent=round(risk_reduction, 1),
        )
