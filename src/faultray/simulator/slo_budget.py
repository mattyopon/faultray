# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""SLO Budget Simulator -- evaluate how much risk you can take.

Given the remaining SLO error budget, determine which chaos scenarios are
safe to run (i.e., their estimated downtime fits within the budget) and which
would breach the SLO target.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from faultray.model.graph import InfraGraph
from faultray.simulator.engine import ScenarioResult, SimulationEngine, SimulationReport


@dataclass
class BudgetSimulation:
    """Result of an SLO budget simulation."""

    slo_target: float  # e.g., 99.9
    window_days: int
    budget_total_minutes: float
    current_budget_remaining_minutes: float
    scenarios_within_budget: list[str]  # scenario names that are safe
    scenarios_exceeding_budget: list[str]  # scenario names that would breach SLO
    risk_appetite: str  # "conservative", "moderate", "aggressive"
    max_safe_blast_radius: float  # largest blast radius within budget (0.0-1.0)
    scenario_details: list[dict] = field(default_factory=list)


class SLOBudgetSimulator:
    """Simulate how much chaos risk you can take given remaining SLO error budget.

    The error budget is calculated as::

        budget_total = (1 - slo_target / 100) * window_days * 24 * 60  # in minutes

    For example, a 99.9% SLO over 30 days gives::

        budget = (1 - 0.999) * 30 * 24 * 60 = 43.2 minutes

    If 10 minutes have already been consumed, the remaining budget is 33.2
    minutes.  The simulator then estimates the downtime of each scenario
    from the simulation report and classifies scenarios as within-budget or
    exceeding-budget.
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
        self.engine = SimulationEngine(graph)

    def simulate(
        self,
        simulation_report: SimulationReport,
        current_consumed_minutes: float = 0.0,
    ) -> BudgetSimulation:
        """Evaluate which scenarios fit within the remaining error budget.

        Parameters
        ----------
        simulation_report:
            A :class:`SimulationReport` (from ``SimulationEngine.run_all_defaults``
            or ``run_scenarios``).
        current_consumed_minutes:
            Minutes of error budget already consumed in the current window.

        Returns
        -------
        BudgetSimulation
        """
        budget_total = (
            (1 - self.slo_target / 100) * self.window_days * 24 * 60
        )
        budget_remaining = budget_total - current_consumed_minutes

        safe: list[str] = []
        unsafe: list[str] = []
        details: list[dict] = []
        max_safe_blast: float = 0.0

        for result in simulation_report.results:
            estimated_downtime = self._estimate_downtime(result)
            blast_radius = self._estimate_blast_radius(result)

            entry = {
                "scenario_name": result.scenario.name,
                "risk_score": result.risk_score,
                "estimated_downtime_minutes": round(estimated_downtime, 2),
                "blast_radius": round(blast_radius, 3),
                "within_budget": estimated_downtime <= budget_remaining,
            }
            details.append(entry)

            if estimated_downtime <= budget_remaining:
                safe.append(result.scenario.name)
                max_safe_blast = max(max_safe_blast, blast_radius)
            else:
                unsafe.append(result.scenario.name)

        risk_appetite = self._classify_appetite(budget_remaining, budget_total)

        return BudgetSimulation(
            slo_target=self.slo_target,
            window_days=self.window_days,
            budget_total_minutes=round(budget_total, 2),
            current_budget_remaining_minutes=round(budget_remaining, 2),
            scenarios_within_budget=safe,
            scenarios_exceeding_budget=unsafe,
            risk_appetite=risk_appetite,
            max_safe_blast_radius=round(max_safe_blast, 3),
            scenario_details=details,
        )

    def simulate_from_scenarios(
        self,
        scenarios: list,
        current_consumed_minutes: float = 0.0,
    ) -> BudgetSimulation:
        """Convenience method: run scenarios and evaluate budget in one call.

        Parameters
        ----------
        scenarios:
            A list of :class:`Scenario` objects.
        current_consumed_minutes:
            Minutes of error budget already consumed.
        """
        report = self.engine.run_scenarios(scenarios)
        return self.simulate(report, current_consumed_minutes)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _estimate_downtime(self, result: ScenarioResult) -> float:
        """Estimate the downtime (in minutes) that a scenario would cause.

        The estimate is based on:
        - Number of components that go DOWN
        - Their MTTR (mean time to repair)
        - The risk score as a scaling factor
        """
        if not result.cascade.effects:
            return 0.0

        down_effects = [
            e for e in result.cascade.effects if e.health.value == "down"
        ]
        if not down_effects:
            # Degraded-only scenarios cause fractional downtime
            degraded = [
                e
                for e in result.cascade.effects
                if e.health.value in ("degraded", "overloaded")
            ]
            if not degraded:
                return 0.0
            # Each degraded component contributes ~1 min of "effective" downtime
            return len(degraded) * 1.0

        # For each downed component, use its MTTR or a default
        total_downtime_minutes = 0.0
        for effect in down_effects:
            comp = self.graph.get_component(effect.component_id)
            if comp:
                mttr = comp.operational_profile.mttr_minutes
                if mttr > 0:
                    total_downtime_minutes = max(total_downtime_minutes, mttr)
                else:
                    total_downtime_minutes = max(total_downtime_minutes, 30.0)
            else:
                total_downtime_minutes = max(total_downtime_minutes, 30.0)

        # Scale by risk severity -- higher risk means longer actual impact
        severity_factor = min(result.risk_score / 10.0, 1.0)
        return total_downtime_minutes * max(severity_factor, 0.1)

    def _estimate_blast_radius(self, result: ScenarioResult) -> float:
        """Estimate the blast radius as a fraction of total components (0.0 - 1.0)."""
        total = max(len(self.graph.components), 1)
        affected = len(result.cascade.effects)
        return min(affected / total, 1.0)

    def _classify_appetite(
        self, budget_remaining: float, budget_total: float
    ) -> str:
        """Classify risk appetite based on how much budget remains."""
        if budget_total <= 0:
            return "conservative"
        ratio = budget_remaining / budget_total
        if ratio >= 0.7:
            return "aggressive"
        elif ratio >= 0.3:
            return "moderate"
        else:
            return "conservative"

    def _max_safe_blast(self, budget_remaining: float) -> float:
        """Estimate the maximum safe blast radius given the remaining budget.

        This is a rough heuristic: if you have lots of budget, you can
        tolerate more components being affected.
        """
        # Simple mapping: 43 minutes remaining -> ~100% safe blast radius
        # 0 minutes remaining -> 0% safe blast radius
        if budget_remaining <= 0:
            return 0.0
        # Assume a 30-day window at 99.9% => 43.2 minutes total
        total_for_999 = 43.2
        return min(1.0, budget_remaining / total_for_999)
