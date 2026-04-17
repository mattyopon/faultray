# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""SLO Impact Simulator -- calculate SLO violation time from component failures.

This module leverages FaultRay's topology knowledge (InfraGraph) to answer:
"If this component fails, how long until we violate SLO?"

The calculation pipeline:
1. Simulate the component failure via CascadeEngine
2. Estimate MTTR from component type and configuration
3. Calculate Error Budget consumption
4. Derive minutes-to-SLO-violation from remaining budget
"""

from __future__ import annotations

from dataclasses import dataclass

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeChain, CascadeEngine
from faultray.simulator.scenarios import Fault, FaultType

# MTTR estimates by component type (minutes).
# Reduced to 1/3 when failover is enabled, 1/2 when autoscaling is enabled.
# Sources: industry benchmarks used in slo_budget.py and operational_profile defaults.
_MTTR_ESTIMATES: dict[ComponentType, float] = {
    ComponentType.DATABASE: 30.0,
    ComponentType.LOAD_BALANCER: 5.0,
    ComponentType.APP_SERVER: 10.0,
    ComponentType.WEB_SERVER: 10.0,
    ComponentType.CACHE: 15.0,
    ComponentType.QUEUE: 20.0,
    ComponentType.STORAGE: 30.0,
    ComponentType.DNS: 60.0,
    ComponentType.EXTERNAL_API: 20.0,
    ComponentType.CUSTOM: 20.0,
    ComponentType.AI_AGENT: 15.0,
    ComponentType.LLM_ENDPOINT: 10.0,
    ComponentType.TOOL_SERVICE: 10.0,
    ComponentType.AGENT_ORCHESTRATOR: 20.0,
}

_DEFAULT_MTTR: float = 20.0


def _risk_level(minutes_to_violation: float) -> str:
    """Classify risk level from minutes remaining until SLO violation."""
    if minutes_to_violation <= 0.0:
        return "critical"
    elif minutes_to_violation <= 10.0:
        return "high"
    elif minutes_to_violation <= 30.0:
        return "medium"
    else:
        return "low"


def _recommendation(
    component: Component,
    minutes_to_violation: float,
    affected_count: int,
) -> str:
    """Generate a human-readable recommendation based on impact analysis."""
    parts: list[str] = []

    if minutes_to_violation <= 0.0:
        parts.append("IMMEDIATE ACTION REQUIRED: SLO already violated.")
    elif minutes_to_violation <= 10.0:
        parts.append(f"SLO violation in {minutes_to_violation:.1f} min.")

    if not component.failover.enabled:
        parts.append("Enable failover to reduce MTTR by ~3x.")

    if not component.autoscaling.enabled and component.type in (
        ComponentType.APP_SERVER, ComponentType.WEB_SERVER, ComponentType.LOAD_BALANCER
    ):
        parts.append("Enable autoscaling to reduce MTTR by ~2x.")

    if affected_count >= 3:
        parts.append(
            f"This component affects {affected_count} services -- prioritize redundancy."
        )

    if not parts:
        return "No immediate action required."

    return " ".join(parts)


@dataclass
class ErrorBudget:
    """Error Budget computation for a given SLO and window."""

    slo_target: float          # e.g. 99.9
    window_days: int           # e.g. 30
    total_budget_minutes: float
    remaining_budget_minutes: float
    burn_rate: float           # consumed / total (0.0 - 1.0+)


@dataclass
class SLOImpactResult:
    """Result of simulating a single component failure against an SLO target."""

    component_id: str
    component_name: str
    component_type: str
    affected_services: list[str]
    affected_service_count: int
    estimated_mttr_minutes: float
    error_budget_consumption_pct: float   # % of total budget this incident consumes
    minutes_to_slo_violation: float       # remaining budget after this incident
    risk_level: str                       # critical / high / medium / low
    cascade_path: list[str]               # flattened ordered path [trigger -> ... -> leaf]
    recommendation: str


class SLOImpactSimulator:
    """Simulate SLO impact of individual component failures.

    Uses the existing ``CascadeEngine`` to compute blast radius, then maps
    the cascade result to SLO budget consumption.

    Parameters
    ----------
    graph:
        The infrastructure topology.
    slo_target:
        SLO target as a percentage, e.g. ``99.9`` for three nines.
    budget_window_days:
        The SLO measurement window in days (default 30).
    current_consumed_minutes:
        Error budget already consumed in the current window (default 0).
    """

    def __init__(
        self,
        graph: InfraGraph,
        slo_target: float = 99.9,
        budget_window_days: int = 30,
        current_consumed_minutes: float = 0.0,
    ) -> None:
        self.graph = graph
        self.slo_target = slo_target
        self.budget_window_days = budget_window_days
        self.current_consumed_minutes = current_consumed_minutes
        self._cascade_engine = CascadeEngine(graph)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calculate_error_budget(self) -> ErrorBudget:
        """Return the current Error Budget state for this simulator's SLO config."""
        total = (1.0 - self.slo_target / 100.0) * self.budget_window_days * 24.0 * 60.0
        remaining = max(0.0, total - self.current_consumed_minutes)
        burn_rate = self.current_consumed_minutes / total if total > 0 else 0.0
        return ErrorBudget(
            slo_target=self.slo_target,
            window_days=self.budget_window_days,
            total_budget_minutes=round(total, 2),
            remaining_budget_minutes=round(remaining, 2),
            burn_rate=round(burn_rate, 4),
        )

    def simulate_component_failure(self, component_id: str) -> SLOImpactResult:
        """Simulate a single-component failure and compute SLO impact.

        Parameters
        ----------
        component_id:
            The ID of the component to fail (COMPONENT_DOWN fault type).

        Returns
        -------
        SLOImpactResult with full cascade and SLO budget analysis.

        Raises
        ------
        KeyError:
            If ``component_id`` is not found in the graph.
        """
        component = self.graph.get_component(component_id)
        if component is None:
            raise KeyError(f"Component '{component_id}' not found in graph.")

        # Run the cascade simulation
        fault = Fault(
            target_component_id=component_id,
            fault_type=FaultType.COMPONENT_DOWN,
        )
        chain: CascadeChain = self._cascade_engine.simulate_fault(fault)

        # Collect affected service IDs (exclude the failing component itself)
        affected_ids: list[str] = [
            e.component_id
            for e in chain.effects
            if e.component_id != component_id
        ]

        # Estimate MTTR
        mttr = self._estimate_mttr(component)

        # Compute Error Budget consumption
        budget = self.calculate_error_budget()
        consumption_pct: float = (
            (mttr / budget.total_budget_minutes * 100.0)
            if budget.total_budget_minutes > 0
            else float("inf")
        )

        # Minutes remaining until SLO violation after this incident
        minutes_to_violation = budget.remaining_budget_minutes - mttr

        # Build cascade path (trigger -> intermediate -> leaf)
        cascade_path = self._build_cascade_path(component_id, chain)

        return SLOImpactResult(
            component_id=component_id,
            component_name=component.name,
            component_type=component.type.value,
            affected_services=affected_ids,
            affected_service_count=len(affected_ids),
            estimated_mttr_minutes=round(mttr, 1),
            error_budget_consumption_pct=round(consumption_pct, 2),
            minutes_to_slo_violation=round(minutes_to_violation, 1),
            risk_level=_risk_level(minutes_to_violation),
            cascade_path=cascade_path,
            recommendation=_recommendation(component, minutes_to_violation, len(affected_ids)),
        )

    def rank_all_components(self) -> list[SLOImpactResult]:
        """Rank all components by SLO risk (highest risk first).

        Components that would cause SLO violation sooner are ranked first.
        Within the same violation window, components with more affected
        services rank higher.

        Returns
        -------
        List of ``SLOImpactResult`` sorted by ascending ``minutes_to_slo_violation``
        (i.e., most dangerous first).
        """
        results: list[SLOImpactResult] = []
        for comp_id in self.graph.components:
            try:
                result = self.simulate_component_failure(comp_id)
                results.append(result)
            except Exception:
                # Skip components that cannot be simulated
                continue

        # Sort: lowest minutes_to_violation first (most dangerous),
        # then most affected services as tiebreaker.
        results.sort(
            key=lambda r: (r.minutes_to_slo_violation, -r.affected_service_count)
        )
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _estimate_mttr(self, component: Component) -> float:
        """Estimate MTTR in minutes for a component.

        Uses operational_profile.mttr_minutes if set (>0), otherwise
        falls back to type-based estimates.  Failover and autoscaling
        reduce the estimate.
        """
        # Prefer explicitly configured MTTR
        configured = component.operational_profile.mttr_minutes
        if configured > 0:
            base = configured
        else:
            base = _MTTR_ESTIMATES.get(component.type, _DEFAULT_MTTR)

        # Failover reduces MTTR by ~3x (fast promotion)
        if component.failover.enabled:
            base = base / 3.0

        # Autoscaling reduces MTTR by ~2x (additional mitigation)
        if component.autoscaling.enabled:
            base = base / 2.0

        return max(1.0, base)

    def _build_cascade_path(
        self, root_id: str, chain: CascadeChain
    ) -> list[str]:
        """Build an ordered cascade path list from the chain effects.

        Returns a list starting with the root (failed) component and
        followed by affected components in the order they appear in the
        chain effects (which reflects propagation order from CascadeEngine).
        """
        path: list[str] = [root_id]
        seen: set[str] = {root_id}
        for effect in chain.effects:
            if effect.component_id not in seen:
                path.append(effect.component_id)
                seen.add(effect.component_id)
        return path
