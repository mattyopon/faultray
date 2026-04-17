# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Infrastructure Cost Optimizer - find cost-efficient architecture meeting resilience targets.

Analyzes each component for cost optimization opportunities (reducing replicas,
downsizing, consolidation, spot instances) while ensuring the overall resilience
score stays above a configurable minimum.

Usage:
    from faultray.simulator.cost_optimizer import CostOptimizer
    optimizer = CostOptimizer(graph, min_resilience_score=70.0)
    report = optimizer.optimize()
    print(f"Savings: ${report.total_savings_monthly:.0f}/mo")

CLI:
    faultray cost-optimize model.yaml --min-score 70 --json
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph
from faultray.simulator.pareto_optimizer import (
    COST_PER_REPLICA,
    _calculate_base_cost,
)

logger = logging.getLogger(__name__)


@dataclass
class OptimizationSuggestion:
    """A single cost optimization suggestion."""

    action: str  # "reduce_replicas", "downsize", "consolidate", "spot_instances"
    component_id: str
    current_cost_monthly: float
    optimized_cost_monthly: float
    savings_monthly: float
    resilience_impact: float  # score change (-5 = drops 5 points)
    risk_level: str  # "safe", "moderate", "risky"
    description: str


@dataclass
class OptimizationReport:
    """Complete cost optimization report."""

    current_monthly_cost: float
    optimized_monthly_cost: float
    total_savings_monthly: float
    savings_percent: float
    resilience_before: float
    resilience_after: float  # after applying all safe suggestions
    suggestions: list[OptimizationSuggestion] = field(default_factory=list)
    pareto_frontier: list[dict] = field(default_factory=list)


class CostOptimizer:
    """Find cost savings while maintaining minimum resilience.

    Analyzes each component for optimization opportunities and calculates
    the resilience impact of each suggestion. Only "safe" suggestions
    (those that keep the score above ``min_resilience_score``) are
    included in the optimized cost.

    Parameters
    ----------
    graph:
        The infrastructure graph to optimize.
    min_resilience_score:
        Minimum acceptable resilience score after optimization.
    """

    def __init__(
        self,
        graph: InfraGraph,
        min_resilience_score: float = 70.0,
    ) -> None:
        self.graph = graph
        self.min_resilience_score = min_resilience_score

    def optimize(self) -> OptimizationReport:
        """Find cost savings while maintaining minimum resilience.

        Evaluates each component for:
        - Reducing replicas without dropping below min score
        - Using spot/preemptible instances for stateless services
        - Disabling unused failover configurations
        - Consolidating low-utilization components

        Returns
        -------
        OptimizationReport
            Report with all suggestions, sorted by savings amount.
        """
        current_cost = _calculate_base_cost(self.graph)
        current_score = self.graph.resilience_score()

        suggestions: list[OptimizationSuggestion] = []

        # Strategy 1: Reduce replicas
        suggestions.extend(self._suggest_reduce_replicas())

        # Strategy 2: Spot instances for stateless services
        suggestions.extend(self._suggest_spot_instances())

        # Strategy 3: Consolidate low-utilization components
        suggestions.extend(self._suggest_consolidation())

        # Strategy 4: Downsize over-provisioned components
        suggestions.extend(self._suggest_downsize())

        # Sort by savings descending
        suggestions.sort(key=lambda s: s.savings_monthly, reverse=True)

        # Calculate optimized cost (only safe suggestions)
        safe_savings = sum(
            s.savings_monthly for s in suggestions if s.risk_level == "safe"
        )
        optimized_cost = max(0.0, current_cost - safe_savings)

        # Calculate resilience after applying safe suggestions
        resilience_after = self._calculate_safe_resilience(suggestions)

        savings_percent = (
            (safe_savings / current_cost * 100.0) if current_cost > 0 else 0.0
        )

        # Generate Pareto frontier
        pareto = self.pareto_analysis()

        return OptimizationReport(
            current_monthly_cost=round(current_cost, 2),
            optimized_monthly_cost=round(optimized_cost, 2),
            total_savings_monthly=round(safe_savings, 2),
            savings_percent=round(savings_percent, 1),
            resilience_before=round(current_score, 1),
            resilience_after=round(resilience_after, 1),
            suggestions=suggestions,
            pareto_frontier=pareto,
        )

    def pareto_analysis(self, budget_steps: int = 10) -> list[dict]:
        """Generate Pareto frontier of cost vs resilience tradeoffs.

        Returns a list of dicts, each with ``cost`` and ``resilience``
        keys, representing non-dominated solutions from zero savings
        to maximum savings.
        """
        current_cost = _calculate_base_cost(self.graph)
        current_score = self.graph.resilience_score()

        # Start with current state
        frontier: list[dict] = [
            {"cost": round(current_cost, 2), "resilience": round(current_score, 1)},
        ]

        # Generate points by progressively applying savings
        suggestions = []
        suggestions.extend(self._suggest_reduce_replicas())
        suggestions.extend(self._suggest_spot_instances())
        suggestions.extend(self._suggest_consolidation())
        suggestions.extend(self._suggest_downsize())

        # Sort by resilience impact (least impact first)
        suggestions.sort(key=lambda s: abs(s.resilience_impact))

        cumulative_savings = 0.0
        cumulative_impact = 0.0
        seen_costs: set[float] = {round(current_cost, 0)}

        for suggestion in suggestions:
            cumulative_savings += suggestion.savings_monthly
            cumulative_impact += suggestion.resilience_impact
            new_cost = max(0.0, current_cost - cumulative_savings)
            new_resilience = max(0.0, current_score + cumulative_impact)

            rounded_cost = round(new_cost, 0)
            if rounded_cost not in seen_costs:
                seen_costs.add(rounded_cost)
                frontier.append({
                    "cost": round(new_cost, 2),
                    "resilience": round(new_resilience, 1),
                })

        # Sort by cost ascending
        frontier.sort(key=lambda p: p["cost"])

        # Limit to budget_steps points
        if len(frontier) > budget_steps:
            step = max(1, len(frontier) // budget_steps)
            sampled = frontier[::step]
            # Always include first and last
            if frontier[0] not in sampled:
                sampled.insert(0, frontier[0])
            if frontier[-1] not in sampled:
                sampled.append(frontier[-1])
            frontier = sampled

        return frontier

    # ------------------------------------------------------------------
    # Suggestion strategies
    # ------------------------------------------------------------------

    def _suggest_reduce_replicas(self) -> list[OptimizationSuggestion]:
        """Suggest reducing replicas where it would not drop resilience below min."""
        suggestions: list[OptimizationSuggestion] = []

        for comp in self.graph.components.values():
            if comp.replicas <= 1:
                continue

            per_replica = COST_PER_REPLICA.get(comp.type, 150.0)
            current_cost = comp.replicas * per_replica

            # Try reducing by 1
            new_replicas = comp.replicas - 1
            new_cost = new_replicas * per_replica
            savings = current_cost - new_cost

            # Calculate resilience impact
            impact = self._score_impact_reduce_replicas(comp.id, new_replicas)

            # Determine risk level
            new_score = self.graph.resilience_score() + impact
            dependents = self.graph.get_dependents(comp.id)
            has_critical_dependents = len(dependents) > 0

            if new_replicas >= 2 and new_score >= self.min_resilience_score:
                risk = "safe"
            elif new_replicas >= 2:
                risk = "moderate"
            elif has_critical_dependents:
                risk = "risky"
            else:
                risk = "moderate"

            suggestions.append(OptimizationSuggestion(
                action="reduce_replicas",
                component_id=comp.id,
                current_cost_monthly=round(current_cost, 2),
                optimized_cost_monthly=round(new_cost, 2),
                savings_monthly=round(savings, 2),
                resilience_impact=round(impact, 1),
                risk_level=risk,
                description=(
                    f"Reduce {comp.name} replicas from {comp.replicas} to "
                    f"{new_replicas} (saves ${savings:.0f}/mo)"
                ),
            ))

        return suggestions

    def _suggest_spot_instances(self) -> list[OptimizationSuggestion]:
        """Suggest spot/preemptible instances for stateless services."""
        suggestions: list[OptimizationSuggestion] = []
        spot_discount = 0.7  # Spot instances are typically 60-70% cheaper

        stateless_types = {
            ComponentType.APP_SERVER,
            ComponentType.WEB_SERVER,
            ComponentType.LOAD_BALANCER,
        }

        for comp in self.graph.components.values():
            if comp.type not in stateless_types:
                continue
            if comp.replicas < 2:
                continue  # Need at least 2 replicas for spot safety

            per_replica = COST_PER_REPLICA.get(comp.type, 150.0)
            current_cost = comp.replicas * per_replica

            # Move a portion of replicas to spot
            spot_replicas = max(1, comp.replicas // 2)
            on_demand_replicas = comp.replicas - spot_replicas
            new_cost = (
                on_demand_replicas * per_replica
                + spot_replicas * per_replica * (1 - spot_discount)
            )
            savings = current_cost - new_cost

            if savings <= 0:
                continue

            # Spot instances add some risk (can be reclaimed)
            impact = -1.0 if comp.autoscaling.enabled else -2.0
            new_score = self.graph.resilience_score() + impact

            if new_score >= self.min_resilience_score and comp.autoscaling.enabled:
                risk = "safe"
            elif new_score >= self.min_resilience_score:
                risk = "moderate"
            else:
                risk = "risky"

            suggestions.append(OptimizationSuggestion(
                action="spot_instances",
                component_id=comp.id,
                current_cost_monthly=round(current_cost, 2),
                optimized_cost_monthly=round(new_cost, 2),
                savings_monthly=round(savings, 2),
                resilience_impact=round(impact, 1),
                risk_level=risk,
                description=(
                    f"Move {spot_replicas} of {comp.replicas} {comp.name} replicas "
                    f"to spot instances (saves ${savings:.0f}/mo)"
                ),
            ))

        return suggestions

    def _suggest_consolidation(self) -> list[OptimizationSuggestion]:
        """Suggest consolidating low-utilization components."""
        suggestions: list[OptimizationSuggestion] = []

        for comp in self.graph.components.values():
            util = comp.utilization()
            if util > 30 or comp.replicas <= 1:
                continue

            # Low utilization with multiple replicas = potential consolidation
            per_replica = COST_PER_REPLICA.get(comp.type, 150.0)
            current_cost = comp.replicas * per_replica

            # Can reduce replicas since utilization is very low
            # Keep at least 2 for redundancy if there are dependents
            dependents = self.graph.get_dependents(comp.id)
            min_replicas = 2 if len(dependents) > 0 else 1
            new_replicas = max(min_replicas, comp.replicas - 1)

            if new_replicas >= comp.replicas:
                continue

            new_cost = new_replicas * per_replica
            savings = current_cost - new_cost

            impact = self._score_impact_reduce_replicas(comp.id, new_replicas)
            new_score = self.graph.resilience_score() + impact

            risk = "safe" if new_score >= self.min_resilience_score else "moderate"

            suggestions.append(OptimizationSuggestion(
                action="consolidate",
                component_id=comp.id,
                current_cost_monthly=round(current_cost, 2),
                optimized_cost_monthly=round(new_cost, 2),
                savings_monthly=round(savings, 2),
                resilience_impact=round(impact, 1),
                risk_level=risk,
                description=(
                    f"Consolidate {comp.name}: utilization at {util:.0f}%, "
                    f"reduce replicas from {comp.replicas} to {new_replicas} "
                    f"(saves ${savings:.0f}/mo)"
                ),
            ))

        return suggestions

    def _suggest_downsize(self) -> list[OptimizationSuggestion]:
        """Suggest downsizing over-provisioned components."""
        suggestions: list[OptimizationSuggestion] = []
        downsize_factor = 0.3  # Assume downsizing saves ~30% per replica

        for comp in self.graph.components.values():
            util = comp.utilization()
            # Only suggest downsizing for very low utilization
            if util > 20:
                continue

            per_replica = COST_PER_REPLICA.get(comp.type, 150.0)
            current_cost = comp.replicas * per_replica
            savings = current_cost * downsize_factor
            new_cost = current_cost - savings

            if savings < 10:
                continue  # Not worth the effort

            # Downsizing has minimal resilience impact if utilization is low
            impact = 0.0
            new_score = self.graph.resilience_score() + impact

            risk = "safe" if new_score >= self.min_resilience_score else "moderate"

            suggestions.append(OptimizationSuggestion(
                action="downsize",
                component_id=comp.id,
                current_cost_monthly=round(current_cost, 2),
                optimized_cost_monthly=round(new_cost, 2),
                savings_monthly=round(savings, 2),
                resilience_impact=round(impact, 1),
                risk_level=risk,
                description=(
                    f"Downsize {comp.name}: utilization at {util:.0f}%, "
                    f"reduce instance size (saves ${savings:.0f}/mo)"
                ),
            ))

        return suggestions

    # ------------------------------------------------------------------
    # Impact calculation helpers
    # ------------------------------------------------------------------

    def _score_impact_reduce_replicas(
        self, component_id: str, new_replicas: int
    ) -> float:
        """Calculate resilience score impact of reducing replicas.

        Returns a negative number (score decrease) or 0.
        """
        # Deep copy the graph and modify
        modified = copy.deepcopy(self.graph)
        comp = modified.get_component(component_id)
        if comp is None:
            return 0.0

        comp.replicas = max(1, new_replicas)
        new_score = modified.resilience_score()
        original_score = self.graph.resilience_score()
        return new_score - original_score

    def _calculate_safe_resilience(
        self, suggestions: list[OptimizationSuggestion]
    ) -> float:
        """Calculate resilience score after applying all safe suggestions."""
        # Build a modified graph applying all safe suggestions
        modified = copy.deepcopy(self.graph)

        for s in suggestions:
            if s.risk_level != "safe":
                continue
            comp = modified.get_component(s.component_id)
            if comp is None:
                continue

            if s.action == "reduce_replicas":
                # Extract new replica count from description
                comp.replicas = max(1, comp.replicas - 1)
            elif s.action == "consolidate":
                comp.replicas = max(1, comp.replicas - 1)
            # spot_instances and downsize don't affect the model's resilience
            # score directly (they affect cost but not graph topology)

        return modified.resilience_score()
