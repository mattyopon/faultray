# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Cost-resilience optimizer — Pareto frontier for cost vs reliability.

Finds the optimal balance between infrastructure cost and resilience.
Shows what you get for each dollar spent on reliability, and identifies
the most cost-effective improvements. Unique to FaultRay — no
competitor offers this analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


class OptimizationStrategy(str, Enum):
    """Optimization strategies."""

    MIN_COST = "min_cost"             # Minimize cost while meeting SLO
    MAX_RESILIENCE = "max_resilience"  # Maximize resilience within budget
    BALANCED = "balanced"             # Balance cost and resilience
    COST_EFFICIENT = "cost_efficient"  # Best resilience per dollar


class ImprovementType(str, Enum):
    """Types of resilience improvements."""

    ADD_REPLICA = "add_replica"
    ENABLE_FAILOVER = "enable_failover"
    ENABLE_AUTOSCALING = "enable_autoscaling"
    ADD_CIRCUIT_BREAKER = "add_circuit_breaker"
    ENABLE_BACKUP = "enable_backup"
    ENABLE_ENCRYPTION = "enable_encryption"
    UPGRADE_INSTANCE = "upgrade_instance"
    ADD_MONITORING = "add_monitoring"
    MULTI_REGION = "multi_region"


# Base monthly costs per component type (USD)
_BASE_COSTS: dict[ComponentType, float] = {
    ComponentType.LOAD_BALANCER: 25.0,
    ComponentType.WEB_SERVER: 50.0,
    ComponentType.APP_SERVER: 80.0,
    ComponentType.DATABASE: 150.0,
    ComponentType.CACHE: 60.0,
    ComponentType.QUEUE: 40.0,
    ComponentType.STORAGE: 30.0,
    ComponentType.DNS: 10.0,
    ComponentType.EXTERNAL_API: 0.0,  # External — no infra cost
    ComponentType.CUSTOM: 50.0,
}

# Improvement costs (monthly USD added)
_IMPROVEMENT_COSTS: dict[ImprovementType, float] = {
    ImprovementType.ADD_REPLICA: 0.0,       # Uses base cost per replica
    ImprovementType.ENABLE_FAILOVER: 20.0,
    ImprovementType.ENABLE_AUTOSCALING: 15.0,
    ImprovementType.ADD_CIRCUIT_BREAKER: 5.0,
    ImprovementType.ENABLE_BACKUP: 25.0,
    ImprovementType.ENABLE_ENCRYPTION: 10.0,
    ImprovementType.UPGRADE_INSTANCE: 50.0,
    ImprovementType.ADD_MONITORING: 30.0,
    ImprovementType.MULTI_REGION: 200.0,
}

# Resilience score improvements (0-100 scale points added)
_IMPROVEMENT_RESILIENCE: dict[ImprovementType, float] = {
    ImprovementType.ADD_REPLICA: 15.0,
    ImprovementType.ENABLE_FAILOVER: 20.0,
    ImprovementType.ENABLE_AUTOSCALING: 10.0,
    ImprovementType.ADD_CIRCUIT_BREAKER: 8.0,
    ImprovementType.ENABLE_BACKUP: 12.0,
    ImprovementType.ENABLE_ENCRYPTION: 5.0,
    ImprovementType.UPGRADE_INSTANCE: 7.0,
    ImprovementType.ADD_MONITORING: 6.0,
    ImprovementType.MULTI_REGION: 25.0,
}


@dataclass
class ImprovementOption:
    """A single improvement option with cost/benefit analysis."""

    component_id: str
    component_name: str
    improvement_type: ImprovementType
    monthly_cost_increase: float
    resilience_score_increase: float
    roi_score: float  # resilience increase per dollar
    description: str
    annual_cost: float
    potential_loss_prevented: float  # Estimated annual loss prevented


@dataclass
class ParetoPoint:
    """A point on the Pareto frontier."""

    total_monthly_cost: float
    resilience_score: float
    improvements_applied: list[str]
    improvement_count: int


@dataclass
class ComponentCostProfile:
    """Cost and resilience profile for a single component."""

    component_id: str
    component_name: str
    component_type: str
    current_monthly_cost: float
    current_resilience_score: float
    available_improvements: list[ImprovementOption]
    max_achievable_resilience: float
    cost_to_max_resilience: float


@dataclass
class OptimizationReport:
    """Full cost-resilience optimization report."""

    component_profiles: list[ComponentCostProfile]
    improvement_options: list[ImprovementOption]
    pareto_frontier: list[ParetoPoint]
    current_total_cost: float
    current_resilience_score: float
    optimal_improvements: list[ImprovementOption]
    strategy: OptimizationStrategy
    total_budget_needed: float
    projected_resilience: float
    cost_efficiency_score: float  # 0-100
    summary: str


class CostResilienceOptimizer:
    """Optimize the cost-resilience tradeoff for infrastructure."""

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    def analyze(
        self,
        strategy: OptimizationStrategy = OptimizationStrategy.BALANCED,
        budget_limit: float | None = None,
        target_resilience: float | None = None,
    ) -> OptimizationReport:
        """Run full cost-resilience optimization analysis."""
        # Build component profiles
        profiles = []
        all_options: list[ImprovementOption] = []

        for comp in self._graph.components.values():
            profile = self._analyze_component(comp)
            profiles.append(profile)
            all_options.extend(profile.available_improvements)

        # Sort by ROI descending (best value first)
        all_options.sort(key=lambda o: o.roi_score, reverse=True)

        current_cost = sum(p.current_monthly_cost for p in profiles)
        current_resilience = self._calculate_infrastructure_resilience()

        # Select optimal improvements based on strategy
        optimal = self._select_improvements(
            all_options, strategy, budget_limit, target_resilience, current_cost
        )

        # Build Pareto frontier
        pareto = self._build_pareto_frontier(all_options, current_cost, current_resilience)

        # Calculate projected state
        total_budget = sum(o.monthly_cost_increase for o in optimal)
        projected_resilience = current_resilience + sum(
            o.resilience_score_increase for o in optimal
        )
        projected_resilience = min(100.0, projected_resilience)

        # Cost efficiency score
        if current_cost > 0:
            efficiency = min(100.0, current_resilience / current_cost * 10)
        else:
            efficiency = 100.0 if current_resilience > 0 else 0.0

        summary = self._generate_summary(
            current_cost,
            current_resilience,
            optimal,
            total_budget,
            projected_resilience,
            strategy,
        )

        return OptimizationReport(
            component_profiles=profiles,
            improvement_options=all_options,
            pareto_frontier=pareto,
            current_total_cost=round(current_cost, 2),
            current_resilience_score=round(current_resilience, 1),
            optimal_improvements=optimal,
            strategy=strategy,
            total_budget_needed=round(total_budget, 2),
            projected_resilience=round(projected_resilience, 1),
            cost_efficiency_score=round(efficiency, 1),
            summary=summary,
        )

    def _analyze_component(self, comp: Component) -> ComponentCostProfile:
        """Analyze cost and resilience for a single component."""
        base_cost = _BASE_COSTS.get(comp.type, 50.0)
        current_cost = base_cost * comp.replicas

        # Calculate current component resilience score (0-100)
        resilience = self._component_resilience_score(comp)

        # Find available improvements
        improvements = self._find_improvements(comp, base_cost)

        max_resilience = resilience + sum(i.resilience_score_increase for i in improvements)
        max_resilience = min(100.0, max_resilience)
        cost_to_max = sum(i.monthly_cost_increase for i in improvements)

        return ComponentCostProfile(
            component_id=comp.id,
            component_name=comp.name,
            component_type=comp.type.value,
            current_monthly_cost=round(current_cost, 2),
            current_resilience_score=round(resilience, 1),
            available_improvements=improvements,
            max_achievable_resilience=round(max_resilience, 1),
            cost_to_max_resilience=round(cost_to_max, 2),
        )

    def _component_resilience_score(self, comp: Component) -> float:
        """Calculate resilience score for a single component (0-100)."""
        score = 0.0

        # Replicas (up to 30 points)
        if comp.replicas >= 3:
            score += 30.0
        elif comp.replicas == 2:
            score += 20.0
        elif comp.replicas == 1:
            score += 5.0

        # Failover (up to 20 points)
        if comp.failover.enabled:
            score += 20.0
            # Fast promotion bonus
            if comp.failover.promotion_time_seconds <= 30:
                score += 5.0

        # Autoscaling (up to 10 points)
        if comp.autoscaling.enabled:
            score += 10.0

        # Security features (up to 15 points)
        if comp.security.encryption_at_rest:
            score += 5.0
        if comp.security.backup_enabled:
            score += 10.0

        # Health penalty
        if comp.health == HealthStatus.DEGRADED:
            score -= 10.0
        elif comp.health == HealthStatus.OVERLOADED:
            score -= 20.0
        elif comp.health == HealthStatus.DOWN:
            score -= 40.0

        # Operational profile bonus
        if comp.operational_profile and comp.operational_profile.mtbf_hours > 0:
            if comp.operational_profile.mtbf_hours >= 2160:  # 90 days
                score += 10.0
            elif comp.operational_profile.mtbf_hours >= 720:  # 30 days
                score += 5.0

        return max(0.0, min(100.0, score))

    def _find_improvements(
        self, comp: Component, base_cost: float
    ) -> list[ImprovementOption]:
        """Find available improvements for a component."""
        improvements: list[ImprovementOption] = []

        # Add replica (if < 3)
        if comp.replicas < 3:
            cost = base_cost  # One replica cost
            resilience_gain = _IMPROVEMENT_RESILIENCE[ImprovementType.ADD_REPLICA]
            if comp.replicas == 2:
                resilience_gain = 10.0  # Less gain for 3rd replica
            roi = resilience_gain / cost if cost > 0 else float("inf")
            loss_prevented = self._estimate_loss_prevented(
                comp, ImprovementType.ADD_REPLICA
            )
            improvements.append(
                ImprovementOption(
                    component_id=comp.id,
                    component_name=comp.name,
                    improvement_type=ImprovementType.ADD_REPLICA,
                    monthly_cost_increase=round(cost, 2),
                    resilience_score_increase=resilience_gain,
                    roi_score=round(roi, 3),
                    description=f"Add replica to {comp.name} ({comp.replicas}→{comp.replicas + 1})",
                    annual_cost=round(cost * 12, 2),
                    potential_loss_prevented=round(loss_prevented, 2),
                )
            )

        # Enable failover
        if not comp.failover.enabled:
            cost = _IMPROVEMENT_COSTS[ImprovementType.ENABLE_FAILOVER]
            resilience_gain = _IMPROVEMENT_RESILIENCE[ImprovementType.ENABLE_FAILOVER]
            roi = resilience_gain / cost if cost > 0 else float("inf")
            loss_prevented = self._estimate_loss_prevented(
                comp, ImprovementType.ENABLE_FAILOVER
            )
            improvements.append(
                ImprovementOption(
                    component_id=comp.id,
                    component_name=comp.name,
                    improvement_type=ImprovementType.ENABLE_FAILOVER,
                    monthly_cost_increase=round(cost, 2),
                    resilience_score_increase=resilience_gain,
                    roi_score=round(roi, 3),
                    description=f"Enable automatic failover for {comp.name}",
                    annual_cost=round(cost * 12, 2),
                    potential_loss_prevented=round(loss_prevented, 2),
                )
            )

        # Enable autoscaling
        if not comp.autoscaling.enabled:
            cost = _IMPROVEMENT_COSTS[ImprovementType.ENABLE_AUTOSCALING]
            resilience_gain = _IMPROVEMENT_RESILIENCE[ImprovementType.ENABLE_AUTOSCALING]
            roi = resilience_gain / cost if cost > 0 else float("inf")
            loss_prevented = self._estimate_loss_prevented(
                comp, ImprovementType.ENABLE_AUTOSCALING
            )
            improvements.append(
                ImprovementOption(
                    component_id=comp.id,
                    component_name=comp.name,
                    improvement_type=ImprovementType.ENABLE_AUTOSCALING,
                    monthly_cost_increase=round(cost, 2),
                    resilience_score_increase=resilience_gain,
                    roi_score=round(roi, 3),
                    description=f"Enable autoscaling for {comp.name}",
                    annual_cost=round(cost * 12, 2),
                    potential_loss_prevented=round(loss_prevented, 2),
                )
            )

        # Enable backup (for data stores)
        if not comp.security.backup_enabled and comp.type in (
            ComponentType.DATABASE,
            ComponentType.STORAGE,
            ComponentType.CACHE,
        ):
            cost = _IMPROVEMENT_COSTS[ImprovementType.ENABLE_BACKUP]
            resilience_gain = _IMPROVEMENT_RESILIENCE[ImprovementType.ENABLE_BACKUP]
            roi = resilience_gain / cost if cost > 0 else float("inf")
            loss_prevented = self._estimate_loss_prevented(
                comp, ImprovementType.ENABLE_BACKUP
            )
            improvements.append(
                ImprovementOption(
                    component_id=comp.id,
                    component_name=comp.name,
                    improvement_type=ImprovementType.ENABLE_BACKUP,
                    monthly_cost_increase=round(cost, 2),
                    resilience_score_increase=resilience_gain,
                    roi_score=round(roi, 3),
                    description=f"Enable automated backups for {comp.name}",
                    annual_cost=round(cost * 12, 2),
                    potential_loss_prevented=round(loss_prevented, 2),
                )
            )

        # Enable encryption
        if not comp.security.encryption_at_rest and comp.type in (
            ComponentType.DATABASE,
            ComponentType.STORAGE,
        ):
            cost = _IMPROVEMENT_COSTS[ImprovementType.ENABLE_ENCRYPTION]
            resilience_gain = _IMPROVEMENT_RESILIENCE[ImprovementType.ENABLE_ENCRYPTION]
            roi = resilience_gain / cost if cost > 0 else float("inf")
            loss_prevented = self._estimate_loss_prevented(
                comp, ImprovementType.ENABLE_ENCRYPTION
            )
            improvements.append(
                ImprovementOption(
                    component_id=comp.id,
                    component_name=comp.name,
                    improvement_type=ImprovementType.ENABLE_ENCRYPTION,
                    monthly_cost_increase=round(cost, 2),
                    resilience_score_increase=resilience_gain,
                    roi_score=round(roi, 3),
                    description=f"Enable encryption at rest for {comp.name}",
                    annual_cost=round(cost * 12, 2),
                    potential_loss_prevented=round(loss_prevented, 2),
                )
            )

        # Add monitoring
        if not comp.security.log_enabled:
            cost = _IMPROVEMENT_COSTS[ImprovementType.ADD_MONITORING]
            resilience_gain = _IMPROVEMENT_RESILIENCE[ImprovementType.ADD_MONITORING]
            roi = resilience_gain / cost if cost > 0 else float("inf")
            loss_prevented = self._estimate_loss_prevented(
                comp, ImprovementType.ADD_MONITORING
            )
            improvements.append(
                ImprovementOption(
                    component_id=comp.id,
                    component_name=comp.name,
                    improvement_type=ImprovementType.ADD_MONITORING,
                    monthly_cost_increase=round(cost, 2),
                    resilience_score_increase=resilience_gain,
                    roi_score=round(roi, 3),
                    description=f"Add monitoring/logging for {comp.name}",
                    annual_cost=round(cost * 12, 2),
                    potential_loss_prevented=round(loss_prevented, 2),
                )
            )

        return improvements

    def _estimate_loss_prevented(
        self, comp: Component, improvement: ImprovementType
    ) -> float:
        """Estimate annual financial loss prevented by an improvement."""
        # Base cost assumptions
        type_revenue_impact: dict[ComponentType, float] = {
            ComponentType.DATABASE: 5000.0,
            ComponentType.LOAD_BALANCER: 3000.0,
            ComponentType.APP_SERVER: 2000.0,
            ComponentType.WEB_SERVER: 1500.0,
            ComponentType.CACHE: 1000.0,
            ComponentType.QUEUE: 800.0,
            ComponentType.STORAGE: 2000.0,
            ComponentType.DNS: 4000.0,
            ComponentType.EXTERNAL_API: 500.0,
            ComponentType.CUSTOM: 1000.0,
        }

        hourly_impact = type_revenue_impact.get(comp.type, 1000.0)

        # Estimate incidents per year without improvement
        incidents_per_year = 4.0  # baseline
        if comp.replicas <= 1:
            incidents_per_year += 3.0
        if not comp.failover.enabled:
            incidents_per_year += 2.0
        if comp.health != HealthStatus.HEALTHY:
            incidents_per_year += 6.0

        # Estimate downtime per incident (hours)
        downtime_hours = 1.0
        if not comp.failover.enabled:
            downtime_hours += 0.5
        if comp.replicas <= 1:
            downtime_hours += 0.5

        # Improvement-specific reduction factors
        reduction_factors: dict[ImprovementType, float] = {
            ImprovementType.ADD_REPLICA: 0.4,
            ImprovementType.ENABLE_FAILOVER: 0.5,
            ImprovementType.ENABLE_AUTOSCALING: 0.2,
            ImprovementType.ADD_CIRCUIT_BREAKER: 0.15,
            ImprovementType.ENABLE_BACKUP: 0.3,
            ImprovementType.ENABLE_ENCRYPTION: 0.05,
            ImprovementType.UPGRADE_INSTANCE: 0.1,
            ImprovementType.ADD_MONITORING: 0.15,
            ImprovementType.MULTI_REGION: 0.6,
        }

        reduction = reduction_factors.get(improvement, 0.1)
        annual_loss = incidents_per_year * downtime_hours * hourly_impact
        return annual_loss * reduction

    def _calculate_infrastructure_resilience(self) -> float:
        """Calculate overall infrastructure resilience score."""
        if not self._graph.components:
            return 0.0

        scores = []
        for comp in self._graph.components.values():
            score = self._component_resilience_score(comp)
            # Weight by number of dependents (more critical = more weight)
            dependents = self._graph.get_dependents(comp.id)
            weight = 1.0 + len(dependents) * 0.5
            scores.append((score, weight))

        if not scores:
            return 0.0

        weighted_sum = sum(s * w for s, w in scores)
        total_weight = sum(w for _, w in scores)
        return weighted_sum / total_weight if total_weight > 0 else 0.0

    def _select_improvements(
        self,
        options: list[ImprovementOption],
        strategy: OptimizationStrategy,
        budget_limit: float | None,
        target_resilience: float | None,
        current_cost: float,
    ) -> list[ImprovementOption]:
        """Select optimal improvements based on strategy."""
        if not options:
            return []

        if strategy == OptimizationStrategy.MIN_COST:
            return self._select_min_cost(options, target_resilience)
        elif strategy == OptimizationStrategy.MAX_RESILIENCE:
            return self._select_max_resilience(options, budget_limit)
        elif strategy == OptimizationStrategy.COST_EFFICIENT:
            return self._select_cost_efficient(options, budget_limit)
        else:  # BALANCED
            return self._select_balanced(options, budget_limit)

    def _select_min_cost(
        self,
        options: list[ImprovementOption],
        target_resilience: float | None,
    ) -> list[ImprovementOption]:
        """Select minimum cost improvements to reach target resilience."""
        if target_resilience is None:
            target_resilience = 70.0  # Default target

        current = self._calculate_infrastructure_resilience()
        needed = target_resilience - current
        if needed <= 0:
            return []  # Already at target

        # Sort by cost ascending, then by resilience descending
        sorted_opts = sorted(options, key=lambda o: (o.monthly_cost_increase, -o.resilience_score_increase))

        selected: list[ImprovementOption] = []
        remaining = needed
        for opt in sorted_opts:
            if remaining <= 0:
                break
            selected.append(opt)
            remaining -= opt.resilience_score_increase

        return selected

    def _select_max_resilience(
        self,
        options: list[ImprovementOption],
        budget_limit: float | None,
    ) -> list[ImprovementOption]:
        """Select improvements that maximize resilience within budget."""
        if budget_limit is None:
            return list(options)  # No budget constraint — take everything

        # Sort by resilience descending
        sorted_opts = sorted(options, key=lambda o: o.resilience_score_increase, reverse=True)

        selected: list[ImprovementOption] = []
        remaining_budget = budget_limit
        for opt in sorted_opts:
            if opt.monthly_cost_increase <= remaining_budget:
                selected.append(opt)
                remaining_budget -= opt.monthly_cost_increase

        return selected

    def _select_cost_efficient(
        self,
        options: list[ImprovementOption],
        budget_limit: float | None,
    ) -> list[ImprovementOption]:
        """Select improvements with best ROI (resilience per dollar)."""
        # Already sorted by ROI descending
        selected: list[ImprovementOption] = []
        remaining_budget = budget_limit if budget_limit is not None else float("inf")

        for opt in options:
            if opt.monthly_cost_increase <= remaining_budget:
                selected.append(opt)
                remaining_budget -= opt.monthly_cost_increase

        return selected

    def _select_balanced(
        self,
        options: list[ImprovementOption],
        budget_limit: float | None,
    ) -> list[ImprovementOption]:
        """Select a balanced set of improvements (top N by ROI)."""
        max_items = min(5, len(options))
        remaining_budget = budget_limit if budget_limit is not None else float("inf")

        selected: list[ImprovementOption] = []
        for opt in options[:max_items]:
            if opt.monthly_cost_increase <= remaining_budget:
                selected.append(opt)
                remaining_budget -= opt.monthly_cost_increase

        return selected

    def _build_pareto_frontier(
        self,
        options: list[ImprovementOption],
        current_cost: float,
        current_resilience: float,
    ) -> list[ParetoPoint]:
        """Build the Pareto frontier of cost vs resilience."""
        # Start with current state
        points: list[ParetoPoint] = [
            ParetoPoint(
                total_monthly_cost=round(current_cost, 2),
                resilience_score=round(current_resilience, 1),
                improvements_applied=[],
                improvement_count=0,
            )
        ]

        # Sort by ROI and add improvements one by one
        sorted_opts = sorted(options, key=lambda o: o.roi_score, reverse=True)

        cumulative_cost = current_cost
        cumulative_resilience = current_resilience
        applied: list[str] = []

        for opt in sorted_opts:
            cumulative_cost += opt.monthly_cost_increase
            cumulative_resilience = min(100.0, cumulative_resilience + opt.resilience_score_increase)
            applied.append(f"{opt.component_name}: {opt.improvement_type.value}")

            # Only add to frontier if resilience increased (Pareto-optimal)
            if cumulative_resilience > points[-1].resilience_score:
                points.append(
                    ParetoPoint(
                        total_monthly_cost=round(cumulative_cost, 2),
                        resilience_score=round(cumulative_resilience, 1),
                        improvements_applied=list(applied),
                        improvement_count=len(applied),
                    )
                )

        return points

    @staticmethod
    def _generate_summary(
        current_cost: float,
        current_resilience: float,
        optimal: list[ImprovementOption],
        total_budget: float,
        projected_resilience: float,
        strategy: OptimizationStrategy,
    ) -> str:
        """Generate a human-readable summary."""
        if not optimal:
            return (
                f"Current state: ${current_cost:.0f}/mo, "
                f"resilience {current_resilience:.0f}/100. "
                f"No improvements needed with {strategy.value} strategy."
            )

        delta_resilience = projected_resilience - current_resilience
        return (
            f"Strategy: {strategy.value}. "
            f"Current: ${current_cost:.0f}/mo, resilience {current_resilience:.0f}/100. "
            f"Recommended: {len(optimal)} improvements (+${total_budget:.0f}/mo) → "
            f"resilience {projected_resilience:.0f}/100 (+{delta_resilience:.0f} points). "
            f"Annual investment: ${total_budget * 12:.0f}. "
            f"Estimated annual loss prevented: "
            f"${sum(o.potential_loss_prevented for o in optimal):.0f}."
        )
