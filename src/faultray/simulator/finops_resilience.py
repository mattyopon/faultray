# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""FinOps-Resilience Optimizer — quantifies the tradeoff between
infrastructure cost and resilience.

Answers questions like "if we switch to spot instances, how much
resilience do we lose and how much money do we save?" Generates
Pareto-optimal configurations that minimize cost while meeting
resilience targets.
"""

from __future__ import annotations

import itertools
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class CostTier(str, Enum):
    """Pricing tier for infrastructure resources."""

    ON_DEMAND = "on_demand"
    RESERVED = "reserved"
    SPOT = "spot"
    SERVERLESS = "serverless"


class OptimizationGoal(str, Enum):
    """High-level optimization goal."""

    MINIMIZE_COST = "minimize_cost"
    MAXIMIZE_RESILIENCE = "maximize_resilience"
    BALANCED = "balanced"


# ---------------------------------------------------------------------------
# Cost-tier multipliers (relative to ON_DEMAND = 1.0)
# ---------------------------------------------------------------------------

_TIER_COST_MULTIPLIER: dict[CostTier, float] = {
    CostTier.ON_DEMAND: 1.0,
    CostTier.RESERVED: 0.6,
    CostTier.SPOT: 0.3,
    CostTier.SERVERLESS: 0.8,
}

_TIER_AVAILABILITY: dict[CostTier, float] = {
    CostTier.ON_DEMAND: 99.95,
    CostTier.RESERVED: 99.99,
    CostTier.SPOT: 95.0,
    CostTier.SERVERLESS: 99.9,
}

_TIER_FAILOVER_SECONDS: dict[CostTier, float] = {
    CostTier.ON_DEMAND: 30.0,
    CostTier.RESERVED: 15.0,
    CostTier.SPOT: 120.0,
    CostTier.SERVERLESS: 5.0,
}

# Base monthly cost by component type when no CostProfile is set
_DEFAULT_MONTHLY_COST: dict[ComponentType, float] = {
    ComponentType.LOAD_BALANCER: 25.0,
    ComponentType.WEB_SERVER: 50.0,
    ComponentType.APP_SERVER: 80.0,
    ComponentType.DATABASE: 150.0,
    ComponentType.CACHE: 60.0,
    ComponentType.QUEUE: 40.0,
    ComponentType.STORAGE: 30.0,
    ComponentType.DNS: 10.0,
    ComponentType.EXTERNAL_API: 0.0,
    ComponentType.CUSTOM: 50.0,
}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class InfraOption(BaseModel):
    """A candidate infrastructure option for a single component."""

    component_id: str
    cost_tier: CostTier
    monthly_cost: float
    availability_percent: float = 99.9
    failover_time_seconds: float = 30.0
    replicas: int = 1


class CostResiliencePoint(BaseModel):
    """A single point on the cost-resilience curve."""

    monthly_cost: float
    resilience_score: float
    configuration: dict[str, CostTier] = Field(default_factory=dict)
    tradeoff_description: str = ""


class SLABreachCost(BaseModel):
    """Financial risk of SLA breach for a component."""

    component_id: str
    sla_target: float
    current_availability: float
    annual_breach_probability: float
    annual_expected_penalty: float
    penalty_per_incident: float


class FinOpsRecommendation(BaseModel):
    """A single FinOps recommendation."""

    action: str
    monthly_savings: float
    resilience_impact: float
    risk_description: str
    priority: int


class FinOpsResilienceReport(BaseModel):
    """Full FinOps-resilience analysis report."""

    current_monthly_cost: float
    current_resilience_score: float
    optimal_configurations: list[CostResiliencePoint] = Field(default_factory=list)
    sla_breach_costs: list[SLABreachCost] = Field(default_factory=list)
    recommendations: list[FinOpsRecommendation] = Field(default_factory=list)
    total_potential_savings: float = 0.0
    total_annual_risk_cost: float = 0.0


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class FinOpsResilienceEngine:
    """Core engine that ties FinOps cost analysis to resilience scoring."""

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    # -- public API ----------------------------------------------------------

    def calculate_current_cost(self) -> float:
        """Sum of component cost profiles (hourly_infra_cost * 730h)."""
        total = 0.0
        for comp in self._graph.components.values():
            total += self._component_monthly_cost(comp)
        return round(total, 2)

    def evaluate_option(self, option: InfraOption) -> CostResiliencePoint:
        """Evaluate a single infrastructure option and return its point."""
        score = self._option_resilience_score(option)
        desc = (
            f"{option.component_id}: {option.cost_tier.value} "
            f"at ${option.monthly_cost:.0f}/mo, "
            f"availability {option.availability_percent:.2f}%, "
            f"failover {option.failover_time_seconds:.0f}s, "
            f"{option.replicas} replica(s)"
        )
        return CostResiliencePoint(
            monthly_cost=round(option.monthly_cost, 2),
            resilience_score=round(score, 2),
            configuration={option.component_id: option.cost_tier},
            tradeoff_description=desc,
        )

    def generate_pareto_frontier(
        self,
        options_per_component: dict[str, list[InfraOption]],
    ) -> list[CostResiliencePoint]:
        """Generate Pareto-optimal configurations across all components.

        Enumerates all combinations (one option per component), computes
        total cost/resilience, then filters dominated solutions.
        """
        if not options_per_component:
            return []

        comp_ids = list(options_per_component.keys())
        option_lists = [options_per_component[cid] for cid in comp_ids]

        # Guard against empty option lists
        if any(len(opts) == 0 for opts in option_lists):
            return []

        all_points: list[CostResiliencePoint] = []

        for combo in itertools.product(*option_lists):
            total_cost = sum(opt.monthly_cost for opt in combo)
            scores = [self._option_resilience_score(opt) for opt in combo]
            avg_score = sum(scores) / len(scores) if scores else 0.0
            config = {opt.component_id: opt.cost_tier for opt in combo}
            parts = [
                f"{opt.component_id}={opt.cost_tier.value}" for opt in combo
            ]
            desc = "Config: " + ", ".join(parts)
            all_points.append(
                CostResiliencePoint(
                    monthly_cost=round(total_cost, 2),
                    resilience_score=round(avg_score, 2),
                    configuration=config,
                    tradeoff_description=desc,
                )
            )

        return self._filter_dominated(all_points)

    def assess_sla_breach_cost(
        self, component_id: str, sla_target: float
    ) -> SLABreachCost:
        """Calculate the financial risk of SLA breach for a component."""
        comp = self._graph.get_component(component_id)
        if comp is None:
            return SLABreachCost(
                component_id=component_id,
                sla_target=sla_target,
                current_availability=0.0,
                annual_breach_probability=1.0,
                annual_expected_penalty=0.0,
                penalty_per_incident=0.0,
            )

        availability = self._estimate_availability(comp)
        gap = max(0.0, sla_target - availability)

        # Breach probability: proportional to gap (0 gap => 0 probability)
        if gap <= 0:
            breach_prob = 0.0
        else:
            breach_prob = min(1.0, gap / 5.0)

        monthly_cost = self._component_monthly_cost(comp)
        penalty_per_incident = monthly_cost * (comp.cost_profile.sla_credit_percent / 100.0)
        # Expect ~12 billing periods; breach_prob applies per period
        annual_expected = penalty_per_incident * breach_prob * 12.0

        return SLABreachCost(
            component_id=component_id,
            sla_target=round(sla_target, 4),
            current_availability=round(availability, 4),
            annual_breach_probability=round(breach_prob, 4),
            annual_expected_penalty=round(annual_expected, 2),
            penalty_per_incident=round(penalty_per_incident, 2),
        )

    def recommend_optimizations(self) -> list[FinOpsRecommendation]:
        """Generate automated cost-saving recommendations."""
        recs: list[FinOpsRecommendation] = []
        priority = 0

        for comp in self._graph.components.values():
            monthly = self._component_monthly_cost(comp)

            # Rec 1: over-provisioned replicas
            if comp.replicas >= 3 and comp.failover.enabled:
                savings = monthly * 0.2
                priority += 1
                recs.append(FinOpsRecommendation(
                    action=f"Reduce replicas for '{comp.id}' from {comp.replicas} to {comp.replicas - 1}",
                    monthly_savings=round(savings, 2),
                    resilience_impact=-5.0,
                    risk_description="Slight reduction in capacity headroom",
                    priority=priority,
                ))

            # Rec 2: consider spot/reserved for non-critical
            dependents = self._graph.get_dependents(comp.id)
            if len(dependents) == 0 and monthly > 0:
                savings = monthly * 0.4
                priority += 1
                recs.append(FinOpsRecommendation(
                    action=f"Switch '{comp.id}' to spot/reserved instances",
                    monthly_savings=round(savings, 2),
                    resilience_impact=-10.0,
                    risk_description="Spot instances may be interrupted; reserved requires commitment",
                    priority=priority,
                ))

            # Rec 3: enable autoscaling to reduce idle cost
            if not comp.autoscaling.enabled and comp.replicas >= 2:
                savings = monthly * 0.15
                priority += 1
                recs.append(FinOpsRecommendation(
                    action=f"Enable autoscaling for '{comp.id}' to scale down during low traffic",
                    monthly_savings=round(savings, 2),
                    resilience_impact=5.0,
                    risk_description="Autoscaling adds complexity; may cause brief latency spikes during scale-up",
                    priority=priority,
                ))

            # Rec 4: right-size under-utilized components
            util = comp.utilization()
            if util > 0 and util < 30 and monthly > 0:
                savings = monthly * 0.3
                priority += 1
                recs.append(FinOpsRecommendation(
                    action=f"Right-size '{comp.id}' (current utilization {util:.0f}%)",
                    monthly_savings=round(savings, 2),
                    resilience_impact=-2.0,
                    risk_description="Reduced headroom for traffic spikes",
                    priority=priority,
                ))

        # Sort by monthly_savings descending
        recs.sort(key=lambda r: r.monthly_savings, reverse=True)
        # Re-assign priority after sort
        for i, rec in enumerate(recs):
            rec.priority = i + 1
        return recs

    def generate_report(
        self,
        options: dict[str, list[InfraOption]] | None = None,
    ) -> FinOpsResilienceReport:
        """Generate a full FinOps-resilience report."""
        current_cost = self.calculate_current_cost()
        current_resilience = self._graph.resilience_score()

        # Pareto frontier
        if options:
            optimal = self.generate_pareto_frontier(options)
        else:
            optimal = []

        # SLA breach costs for every component
        breach_costs: list[SLABreachCost] = []
        for comp in self._graph.components.values():
            sla_target = 99.9  # default
            if comp.slo_targets:
                for slo in comp.slo_targets:
                    if slo.metric == "availability":
                        sla_target = slo.target
                        break
            breach_costs.append(self.assess_sla_breach_cost(comp.id, sla_target))

        # Recommendations
        recs = self.recommend_optimizations()

        total_savings = sum(r.monthly_savings for r in recs)
        total_risk = sum(b.annual_expected_penalty for b in breach_costs)

        return FinOpsResilienceReport(
            current_monthly_cost=current_cost,
            current_resilience_score=round(current_resilience, 2),
            optimal_configurations=optimal,
            sla_breach_costs=breach_costs,
            recommendations=recs,
            total_potential_savings=round(total_savings, 2),
            total_annual_risk_cost=round(total_risk, 2),
        )

    # -- internal helpers ----------------------------------------------------

    def _component_monthly_cost(self, comp: Component) -> float:
        """Derive monthly cost for a component."""
        hourly = comp.cost_profile.hourly_infra_cost
        if hourly > 0:
            return hourly * 730.0 * comp.replicas
        return _DEFAULT_MONTHLY_COST.get(comp.type, 50.0) * comp.replicas

    def _option_resilience_score(self, option: InfraOption) -> float:
        """Score an InfraOption on a 0-100 resilience scale."""
        score = 0.0

        # Availability contribution (up to 50 points)
        avail = option.availability_percent
        if avail >= 99.99:
            score += 50.0
        elif avail >= 99.9:
            score += 40.0
        elif avail >= 99.0:
            score += 30.0
        elif avail >= 95.0:
            score += 15.0
        else:
            score += 5.0

        # Replica contribution (up to 30 points)
        if option.replicas >= 3:
            score += 30.0
        elif option.replicas == 2:
            score += 20.0
        else:
            score += 5.0

        # Failover time contribution (up to 20 points)
        ft = option.failover_time_seconds
        if ft <= 5:
            score += 20.0
        elif ft <= 15:
            score += 15.0
        elif ft <= 30:
            score += 10.0
        elif ft <= 60:
            score += 5.0
        else:
            score += 2.0

        return min(100.0, score)

    def _estimate_availability(self, comp: Component) -> float:
        """Estimate current availability percentage for a component."""
        base = 99.0
        if comp.replicas >= 3:
            base += 0.9
        elif comp.replicas >= 2:
            base += 0.5
        if comp.failover.enabled:
            base += 0.09
        if comp.autoscaling.enabled:
            base += 0.05

        if comp.health == HealthStatus.DEGRADED:
            base -= 1.0
        elif comp.health == HealthStatus.OVERLOADED:
            base -= 3.0
        elif comp.health == HealthStatus.DOWN:
            base -= 10.0

        return max(0.0, min(100.0, base))

    @staticmethod
    def _filter_dominated(
        points: list[CostResiliencePoint],
    ) -> list[CostResiliencePoint]:
        """Remove dominated points; keep Pareto-optimal set."""
        if not points:
            return []

        pareto: list[CostResiliencePoint] = []
        for candidate in points:
            dominated = False
            for other in points:
                if other is candidate:
                    continue
                if (
                    other.resilience_score >= candidate.resilience_score
                    and other.monthly_cost <= candidate.monthly_cost
                    and (
                        other.resilience_score > candidate.resilience_score
                        or other.monthly_cost < candidate.monthly_cost
                    )
                ):
                    dominated = True
                    break
            if not dominated:
                pareto.append(candidate)

        pareto.sort(key=lambda p: p.monthly_cost)
        return pareto
