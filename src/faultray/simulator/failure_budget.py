# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Failure Budget Allocation Engine.

Allocates error budget across teams and services based on criticality,
service type, and dependency graph topology.  Works with existing SLO
data from component definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


@dataclass
class BudgetAllocation:
    """Budget allocation for a single service."""

    service_id: str
    service_name: str
    team: str
    budget_total_minutes: float
    budget_consumed_minutes: float
    budget_remaining_minutes: float
    budget_remaining_percent: float
    risk_weight: float  # higher = more critical service


@dataclass
class BudgetReport:
    """Complete failure budget allocation report."""

    slo_target: float  # e.g., 99.9
    window_days: int
    total_budget_minutes: float
    allocations: list[BudgetAllocation] = field(default_factory=list)
    over_budget_services: list[str] = field(default_factory=list)
    under_utilized_services: list[str] = field(default_factory=list)
    rebalance_suggestions: list[dict] = field(default_factory=list)


# Component types considered "stateful" -- they get smaller error budget
# allocations because failures have higher impact.
_STATEFUL_TYPES = {
    ComponentType.DATABASE,
    ComponentType.CACHE,
    ComponentType.STORAGE,
    ComponentType.QUEUE,
}

# Component types considered "stateless" -- easier to recover, get larger
# budget allocations.
_STATELESS_TYPES = {
    ComponentType.WEB_SERVER,
    ComponentType.APP_SERVER,
    ComponentType.LOAD_BALANCER,
    ComponentType.DNS,
    ComponentType.EXTERNAL_API,
    ComponentType.CUSTOM,
}


class FailureBudgetAllocator:
    """Allocate error budget proportionally across services.

    Allocation strategy:
    - Critical path services get a larger budget share
    - Stateful services (DB/cache) get a smaller budget (less tolerance)
    - Stateless services get a larger budget (easier to recover)
    - Services with more dependents are weighted higher (more critical)

    The total error budget is::

        budget = (1 - slo_target / 100) * window_days * 24 * 60  # minutes

    Each service receives a share proportional to its risk weight.
    """

    def __init__(
        self,
        graph: InfraGraph,
        slo_target: float = 99.9,
        window_days: int = 30,
    ) -> None:
        self.graph = graph
        self.slo_target = slo_target
        self.window_days = window_days

    def allocate(self) -> BudgetReport:
        """Allocate error budget proportionally across services.

        Returns a :class:`BudgetReport` with per-service allocations.
        """
        total_budget = (1 - self.slo_target / 100) * self.window_days * 24 * 60

        if not self.graph.components:
            return BudgetReport(
                slo_target=self.slo_target,
                window_days=self.window_days,
                total_budget_minutes=round(total_budget, 2),
            )

        # Step 1: Calculate risk weight for each component
        weights: dict[str, float] = {}
        for comp in self.graph.components.values():
            weights[comp.id] = self._compute_risk_weight(comp)

        # Step 2: Normalize weights to get budget shares
        total_weight = sum(weights.values())
        if total_weight == 0:
            total_weight = 1.0  # avoid division by zero

        allocations: list[BudgetAllocation] = []
        for comp in self.graph.components.values():
            share = weights[comp.id] / total_weight
            service_budget = total_budget * share

            # Estimate consumed budget from component's MTTR and current health
            consumed = self._estimate_consumed(comp, service_budget)

            remaining = service_budget - consumed
            remaining_pct = (remaining / service_budget * 100) if service_budget > 0 else 100.0

            # Derive team name from component tags or use "default"
            team = self._derive_team(comp)

            allocations.append(BudgetAllocation(
                service_id=comp.id,
                service_name=comp.name,
                team=team,
                budget_total_minutes=round(service_budget, 2),
                budget_consumed_minutes=round(consumed, 2),
                budget_remaining_minutes=round(remaining, 2),
                budget_remaining_percent=round(remaining_pct, 1),
                risk_weight=round(weights[comp.id], 3),
            ))

        # Step 3: Classify services
        over_budget = [a.service_id for a in allocations if a.budget_remaining_minutes < 0]
        under_utilized = [
            a.service_id for a in allocations if a.budget_remaining_percent > 80
        ]

        # Step 4: Generate rebalance suggestions
        suggestions = self._generate_rebalance_suggestions(allocations)

        return BudgetReport(
            slo_target=self.slo_target,
            window_days=self.window_days,
            total_budget_minutes=round(total_budget, 2),
            allocations=allocations,
            over_budget_services=over_budget,
            under_utilized_services=under_utilized,
            rebalance_suggestions=suggestions,
        )

    def simulate_consumption(
        self,
        simulation_report: object,
    ) -> BudgetReport:
        """Simulate budget consumption from chaos test results.

        Takes a :class:`SimulationReport` (from the simulation engine)
        and uses the scenario results to estimate how much error budget
        would be consumed by each affected component.

        Args:
            simulation_report: A SimulationReport with scenario results.

        Returns:
            BudgetReport with consumption estimates based on simulation.
        """
        total_budget = (1 - self.slo_target / 100) * self.window_days * 24 * 60

        if not self.graph.components:
            return BudgetReport(
                slo_target=self.slo_target,
                window_days=self.window_days,
                total_budget_minutes=round(total_budget, 2),
            )

        # Calculate risk weights
        weights: dict[str, float] = {}
        for comp in self.graph.components.values():
            weights[comp.id] = self._compute_risk_weight(comp)

        total_weight = sum(weights.values()) or 1.0

        # Estimate consumption from simulation results
        consumption: dict[str, float] = {cid: 0.0 for cid in self.graph.components}

        results = getattr(simulation_report, "results", [])
        for result in results:
            cascade = getattr(result, "cascade", None)
            if cascade is None:
                continue
            effects = getattr(cascade, "effects", [])
            risk_score = getattr(result, "risk_score", 0.0)

            for effect in effects:
                comp_id = getattr(effect, "component_id", "")
                health = getattr(effect, "health", None)
                if comp_id not in consumption:
                    continue

                # DOWN effects consume more budget than degraded
                health_val = health.value if health else "healthy"
                if health_val == "down":
                    comp = self.graph.get_component(comp_id)
                    mttr = 30.0
                    if comp:
                        mttr = comp.operational_profile.mttr_minutes or 30.0
                    severity = min(risk_score / 10.0, 1.0)
                    consumption[comp_id] += mttr * max(severity, 0.1)
                elif health_val in ("degraded", "overloaded"):
                    consumption[comp_id] += 1.0  # fractional impact

        # Build allocations
        allocations: list[BudgetAllocation] = []
        for comp in self.graph.components.values():
            share = weights[comp.id] / total_weight
            service_budget = total_budget * share
            consumed = consumption.get(comp.id, 0.0)
            remaining = service_budget - consumed
            remaining_pct = (remaining / service_budget * 100) if service_budget > 0 else 100.0

            team = self._derive_team(comp)

            allocations.append(BudgetAllocation(
                service_id=comp.id,
                service_name=comp.name,
                team=team,
                budget_total_minutes=round(service_budget, 2),
                budget_consumed_minutes=round(consumed, 2),
                budget_remaining_minutes=round(remaining, 2),
                budget_remaining_percent=round(remaining_pct, 1),
                risk_weight=round(weights[comp.id], 3),
            ))

        over_budget = [a.service_id for a in allocations if a.budget_remaining_minutes < 0]
        under_utilized = [
            a.service_id for a in allocations if a.budget_remaining_percent > 80
        ]
        suggestions = self._generate_rebalance_suggestions(allocations)

        return BudgetReport(
            slo_target=self.slo_target,
            window_days=self.window_days,
            total_budget_minutes=round(total_budget, 2),
            allocations=allocations,
            over_budget_services=over_budget,
            under_utilized_services=under_utilized,
            rebalance_suggestions=suggestions,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_risk_weight(self, comp: object) -> float:
        """Compute risk weight for a component.

        Higher weight = more critical service = gets larger budget share.

        Factors:
        - Number of dependents (upstream impact)
        - Component type (stateful vs stateless)
        - SLO targets defined on the component
        - Whether it sits on a critical path
        """
        weight = 1.0

        # More dependents = more critical
        dependents = self.graph.get_dependents(comp.id)
        weight += len(dependents) * 0.5

        # Stateful services are more critical (data at risk)
        if comp.type in _STATEFUL_TYPES:
            weight *= 1.5
        elif comp.type in _STATELESS_TYPES:
            weight *= 0.8

        # Components with explicit SLO targets get higher weight
        if comp.slo_targets:
            strictest = min(t.target for t in comp.slo_targets)
            if strictest >= 99.99:
                weight *= 2.0
            elif strictest >= 99.9:
                weight *= 1.5
            elif strictest >= 99.0:
                weight *= 1.2

        # Single-replica components are riskier
        if comp.replicas <= 1 and not comp.failover.enabled:
            weight *= 1.3

        return weight

    def _estimate_consumed(self, comp: object, budget: float) -> float:
        """Estimate consumed budget from current component state.

        Uses component health status and utilization to estimate
        how much budget has already been consumed.
        """
        consumed = 0.0

        # If the component is currently degraded or down, it's consuming budget
        health = comp.health.value if hasattr(comp.health, "value") else str(comp.health)
        if health == "down":
            consumed += comp.operational_profile.mttr_minutes or 30.0
        elif health in ("degraded", "overloaded"):
            consumed += 5.0  # partial impact

        # High utilization suggests potential for budget consumption
        util = comp.utilization()
        if util > 90:
            consumed += budget * 0.1  # 10% budget risk at high utilization

        return consumed

    @staticmethod
    def _derive_team(comp: object) -> str:
        """Derive team name from component tags or use default."""
        for tag in comp.tags:
            if tag.startswith("team:"):
                return tag[5:]
        return "default"

    @staticmethod
    def _generate_rebalance_suggestions(
        allocations: list[BudgetAllocation],
    ) -> list[dict]:
        """Generate suggestions for rebalancing budget allocations."""
        suggestions: list[dict] = []

        over_budget = [a for a in allocations if a.budget_remaining_minutes < 0]
        under_utilized = [a for a in allocations if a.budget_remaining_percent > 80]

        for over in over_budget:
            for under in under_utilized:
                surplus = under.budget_remaining_minutes * 0.2
                suggestions.append({
                    "action": "rebalance",
                    "from_service": under.service_id,
                    "to_service": over.service_id,
                    "suggested_transfer_minutes": round(surplus, 2),
                    "reason": (
                        f"'{over.service_name}' is over budget by "
                        f"{abs(over.budget_remaining_minutes):.1f}min. "
                        f"'{under.service_name}' has {under.budget_remaining_percent:.0f}% "
                        f"budget remaining."
                    ),
                })

        # Suggest adding redundancy for over-budget services without failover
        for over in over_budget:
            suggestions.append({
                "action": "add_redundancy",
                "service": over.service_id,
                "reason": (
                    f"'{over.service_name}' is over budget. "
                    "Consider adding replicas or enabling failover to reduce MTTR."
                ),
            })

        return suggestions
