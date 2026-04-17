# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Infrastructure Pareto Optimizer.

Finds the optimal trade-off between cost and resilience using
multi-objective optimization. Generates a Pareto frontier showing
all non-dominated solutions.

Answers: "What's the cheapest way to achieve 99.99% uptime?"
         "What resilience can I get for $X/month?"
"""

from __future__ import annotations

import copy
import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & Constants
# ---------------------------------------------------------------------------


class OptimizationObjective(str, Enum):
    MAXIMIZE_RESILIENCE = "maximize_resilience"
    MINIMIZE_COST = "minimize_cost"
    MAXIMIZE_AVAILABILITY = "maximize_availability"
    MINIMIZE_SPOF = "minimize_spof"


# Monthly cost per additional replica, by component type
COST_PER_REPLICA: dict[ComponentType, float] = {
    ComponentType.APP_SERVER: 200.0,
    ComponentType.WEB_SERVER: 200.0,
    ComponentType.DATABASE: 500.0,
    ComponentType.CACHE: 150.0,
    ComponentType.QUEUE: 100.0,
    ComponentType.LOAD_BALANCER: 100.0,
    ComponentType.STORAGE: 30.0,
    ComponentType.DNS: 10.0,
    ComponentType.EXTERNAL_API: 0.0,
    ComponentType.CUSTOM: 150.0,
    ComponentType.AI_AGENT: 250.0,
    ComponentType.LLM_ENDPOINT: 500.0,
    ComponentType.TOOL_SERVICE: 150.0,
    ComponentType.AGENT_ORCHESTRATOR: 300.0,
    ComponentType.AUTOMATION: 50.0,
    ComponentType.SERVERLESS: 20.0,
    ComponentType.SCHEDULED_JOB: 30.0,
}

# Monthly cost for enabling features
FAILOVER_COST = 100.0
AUTOSCALING_COST = 50.0
CIRCUIT_BREAKER_COST = 0.0  # Software-only change


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class OptimizationVariable:
    """A single variable that can be tuned during optimization."""

    component_id: str
    parameter: str  # "replicas", "enable_failover", "enable_autoscaling", "enable_circuit_breaker"
    min_value: int | bool
    max_value: int | bool
    current_value: int | bool
    cost_per_unit: float  # Monthly cost impact per unit change


@dataclass
class ParetoSolution:
    """A single solution on (or near) the Pareto frontier."""

    variables: dict[str, dict[str, Any]]  # component_id -> {param: value}
    resilience_score: float
    estimated_monthly_cost: float
    availability_nines: float
    spof_count: int
    is_current: bool = False
    improvements_from_current: list[str] = field(default_factory=list)


@dataclass
class ParetoFrontier:
    """The complete Pareto frontier with metadata."""

    solutions: list[ParetoSolution]
    current_solution: ParetoSolution
    cheapest_solution: ParetoSolution
    most_resilient_solution: ParetoSolution
    best_value_solution: ParetoSolution  # Best resilience/$ ratio
    cost_to_next_nine: float  # How much more to add one nine of availability


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _score_to_nines(score: float) -> float:
    """Convert a resilience score (0-100) to availability nines.

    Uses piecewise linear interpolation with guaranteed monotonicity.
    Mapping:  0 -> 1.0,  40 -> 2.0,  60 -> 2.5,  75 -> 3.0,
             85 -> 3.5,  95 -> 4.0,  99 -> 5.0,  100 -> 5.0
    """
    # Define breakpoints: (score, nines)
    breakpoints = [
        (0.0, 1.0),
        (40.0, 2.0),
        (60.0, 2.5),
        (75.0, 3.0),
        (85.0, 3.5),
        (95.0, 4.0),
        (99.0, 5.0),
    ]

    score = max(0.0, min(100.0, score))

    if score >= 99.0:
        return 5.0

    # Find the two surrounding breakpoints and interpolate
    for i in range(len(breakpoints) - 1):
        s0, n0 = breakpoints[i]
        s1, n1 = breakpoints[i + 1]
        if s0 <= score <= s1:
            fraction = (score - s0) / (s1 - s0)
            return n0 + fraction * (n1 - n0)

    return 1.0


def _count_spofs(graph: InfraGraph) -> int:
    """Count single points of failure in the graph."""
    count = 0
    for comp in graph.components.values():
        if comp.replicas <= 1 and not comp.failover.enabled:
            dependents = graph.get_dependents(comp.id)
            if len(dependents) > 0:
                count += 1
    return count


def _calculate_base_cost(graph: InfraGraph) -> float:
    """Calculate the baseline monthly cost of the current configuration."""
    cost = 0.0
    for comp in graph.components.values():
        comp_type = comp.type
        per_replica = COST_PER_REPLICA.get(comp_type, 150.0)
        cost += comp.replicas * per_replica
        if comp.failover.enabled:
            cost += FAILOVER_COST
        if comp.autoscaling.enabled:
            cost += AUTOSCALING_COST
        # Circuit breaker is free (software change)
    return cost


# ---------------------------------------------------------------------------
# ParetoOptimizer
# ---------------------------------------------------------------------------


class ParetoOptimizer:
    """Multi-objective optimizer for infrastructure cost vs. resilience."""

    def __init__(self) -> None:
        pass

    def _extract_variables(self, graph: InfraGraph) -> list[OptimizationVariable]:
        """Extract all tuneable variables from the graph."""
        variables: list[OptimizationVariable] = []
        for comp in graph.components.values():
            comp_type = comp.type
            per_replica = COST_PER_REPLICA.get(comp_type, 150.0)

            # Replicas: can go from current to 5
            variables.append(OptimizationVariable(
                component_id=comp.id,
                parameter="replicas",
                min_value=1,
                max_value=5,
                current_value=comp.replicas,
                cost_per_unit=per_replica,
            ))

            # Failover toggle
            if not comp.failover.enabled:
                variables.append(OptimizationVariable(
                    component_id=comp.id,
                    parameter="enable_failover",
                    min_value=False,
                    max_value=True,
                    current_value=comp.failover.enabled,
                    cost_per_unit=FAILOVER_COST,
                ))

            # Autoscaling toggle
            if not comp.autoscaling.enabled:
                variables.append(OptimizationVariable(
                    component_id=comp.id,
                    parameter="enable_autoscaling",
                    min_value=False,
                    max_value=True,
                    current_value=comp.autoscaling.enabled,
                    cost_per_unit=AUTOSCALING_COST,
                ))

            # Circuit breaker toggle (on edges targeting this component)
            has_cb = True
            for dep_comp in graph.get_dependents(comp.id):
                edge = graph.get_dependency_edge(dep_comp.id, comp.id)
                if edge and not edge.circuit_breaker.enabled:
                    has_cb = False
                    break

            if not has_cb:
                variables.append(OptimizationVariable(
                    component_id=comp.id,
                    parameter="enable_circuit_breaker",
                    min_value=False,
                    max_value=True,
                    current_value=False,
                    cost_per_unit=CIRCUIT_BREAKER_COST,
                ))

        return variables

    def _apply_changes(
        self,
        graph: InfraGraph,
        changes: dict[str, dict[str, Any]],
    ) -> InfraGraph:
        """Apply a set of changes to a deep copy of the graph and return it."""
        modified = copy.deepcopy(graph)
        for comp_id, params in changes.items():
            comp = modified.get_component(comp_id)
            if not comp:
                continue
            if "replicas" in params:
                comp.replicas = max(1, int(params["replicas"]))
            if "enable_failover" in params and params["enable_failover"]:
                comp.failover.enabled = True
            if "enable_autoscaling" in params and params["enable_autoscaling"]:
                comp.autoscaling.enabled = True
                comp.autoscaling.min_replicas = comp.replicas
                comp.autoscaling.max_replicas = max(comp.replicas * 2, 4)
            if "enable_circuit_breaker" in params and params["enable_circuit_breaker"]:
                # Enable CB on all edges targeting this component
                for u, v, data in modified._graph.edges(data=True):
                    dep = data.get("dependency")
                    if dep and dep.target_id == comp_id:
                        dep.circuit_breaker.enabled = True
        return modified

    def _calculate_cost_of_changes(
        self,
        graph: InfraGraph,
        changes: dict[str, dict[str, Any]],
    ) -> float:
        """Calculate the incremental monthly cost of a set of changes."""
        cost = 0.0
        for comp_id, params in changes.items():
            comp = graph.get_component(comp_id)
            if not comp:
                continue
            comp_type = comp.type
            per_replica = COST_PER_REPLICA.get(comp_type, 150.0)

            if "replicas" in params:
                additional = max(0, int(params["replicas"]) - comp.replicas)
                cost += additional * per_replica
            if "enable_failover" in params and params["enable_failover"] and not comp.failover.enabled:
                cost += FAILOVER_COST
            if "enable_autoscaling" in params and params["enable_autoscaling"] and not comp.autoscaling.enabled:
                cost += AUTOSCALING_COST
            if "enable_circuit_breaker" in params and params["enable_circuit_breaker"]:
                cost += CIRCUIT_BREAKER_COST
        return cost

    def _describe_improvements(
        self,
        graph: InfraGraph,
        changes: dict[str, dict[str, Any]],
    ) -> list[str]:
        """Describe changes from current configuration in human-readable form."""
        improvements: list[str] = []
        for comp_id, params in changes.items():
            comp = graph.get_component(comp_id)
            if not comp:
                continue
            name = comp.name or comp.id
            if "replicas" in params and params["replicas"] != comp.replicas:
                improvements.append(
                    f"{name}: replicas {comp.replicas} -> {params['replicas']}"
                )
            if "enable_failover" in params and params["enable_failover"] and not comp.failover.enabled:
                improvements.append(f"{name}: enable failover")
            if "enable_autoscaling" in params and params["enable_autoscaling"] and not comp.autoscaling.enabled:
                improvements.append(f"{name}: enable autoscaling")
            if "enable_circuit_breaker" in params and params["enable_circuit_breaker"]:
                improvements.append(f"{name}: enable circuit breaker")
        return improvements

    def _build_solution(
        self,
        graph: InfraGraph,
        changes: dict[str, dict[str, Any]],
        base_cost: float,
        is_current: bool = False,
    ) -> ParetoSolution:
        """Build a ParetoSolution from a set of changes."""
        if is_current:
            modified = graph
            incremental_cost = 0.0
        else:
            modified = self._apply_changes(graph, changes)
            incremental_cost = self._calculate_cost_of_changes(graph, changes)

        score = modified.resilience_score()
        total_cost = base_cost + incremental_cost
        nines = _score_to_nines(score)
        spof_count = _count_spofs(modified)
        improvements = self._describe_improvements(graph, changes) if not is_current else []

        return ParetoSolution(
            variables=changes if changes else {},
            resilience_score=round(score, 2),
            estimated_monthly_cost=round(total_cost, 2),
            availability_nines=round(nines, 2),
            spof_count=spof_count,
            is_current=is_current,
            improvements_from_current=improvements,
        )

    def _generate_incremental_changes(
        self,
        graph: InfraGraph,
    ) -> list[dict[str, dict[str, Any]]]:
        """Generate candidate change sets by incrementally adding improvements.

        Strategy: start with cheapest improvements and progressively add more.
        This produces a set of solutions that can then be filtered for Pareto
        optimality.
        """
        candidates: list[dict[str, dict[str, Any]]] = []

        # Collect individual improvements sorted by cost
        individual_changes: list[tuple[float, str, str, Any]] = []  # (cost, comp_id, param, value)

        for comp in graph.components.values():
            comp_type = comp.type
            per_replica = COST_PER_REPLICA.get(comp_type, 150.0)

            # Adding replicas (one at a time)
            for r in range(comp.replicas + 1, 6):
                cost = (r - comp.replicas) * per_replica
                individual_changes.append((cost, comp.id, "replicas", r))

            # Enable failover
            if not comp.failover.enabled:
                individual_changes.append((FAILOVER_COST, comp.id, "enable_failover", True))

            # Enable autoscaling
            if not comp.autoscaling.enabled:
                individual_changes.append((AUTOSCALING_COST, comp.id, "enable_autoscaling", True))

            # Enable circuit breaker
            has_edges = False
            for dep_comp in graph.get_dependents(comp.id):
                edge = graph.get_dependency_edge(dep_comp.id, comp.id)
                if edge and not edge.circuit_breaker.enabled:
                    has_edges = True
                    break
            if has_edges:
                individual_changes.append((CIRCUIT_BREAKER_COST, comp.id, "enable_circuit_breaker", True))

        # Sort by cost (cheapest first)
        individual_changes.sort(key=lambda x: x[0])

        # Generate cumulative change sets
        cumulative: dict[str, dict[str, Any]] = {}
        for cost, comp_id, param, value in individual_changes:
            if comp_id not in cumulative:
                cumulative[comp_id] = {}

            # For replicas, only keep the highest value
            if param == "replicas":
                current_replicas = cumulative[comp_id].get("replicas", graph.get_component(comp_id).replicas)
                if value <= current_replicas:
                    continue

            cumulative[comp_id][param] = value
            # Take a snapshot of current cumulative state
            candidates.append(copy.deepcopy(cumulative))

        # Also generate some targeted solutions:
        # 1. All circuit breakers only (free)
        cb_only: dict[str, dict[str, Any]] = {}
        for cost, comp_id, param, value in individual_changes:
            if param == "enable_circuit_breaker":
                if comp_id not in cb_only:
                    cb_only[comp_id] = {}
                cb_only[comp_id][param] = value
        if cb_only:
            candidates.append(cb_only)

        # 2. All failovers only
        fo_only: dict[str, dict[str, Any]] = {}
        for cost, comp_id, param, value in individual_changes:
            if param == "enable_failover":
                if comp_id not in fo_only:
                    fo_only[comp_id] = {}
                fo_only[comp_id][param] = value
        if fo_only:
            candidates.append(fo_only)

        # 3. Minimum replicas (all to 2)
        rep2_only: dict[str, dict[str, Any]] = {}
        for comp in graph.components.values():
            if comp.replicas < 2:
                rep2_only[comp.id] = {"replicas": 2}
        if rep2_only:
            candidates.append(rep2_only)

        # 4. Everything maxed out
        max_all: dict[str, dict[str, Any]] = {}
        for comp in graph.components.values():
            max_all[comp.id] = {"replicas": 5}
            if not comp.failover.enabled:
                max_all[comp.id]["enable_failover"] = True
            if not comp.autoscaling.enabled:
                max_all[comp.id]["enable_autoscaling"] = True
            for dep_comp in graph.get_dependents(comp.id):
                edge = graph.get_dependency_edge(dep_comp.id, comp.id)
                if edge and not edge.circuit_breaker.enabled:
                    max_all[comp.id]["enable_circuit_breaker"] = True
                    break
        if max_all:
            candidates.append(max_all)

        # 5. Individual changes (each one alone)
        for cost, comp_id, param, value in individual_changes:
            candidates.append({comp_id: {param: value}})

        return candidates

    def _filter_pareto_optimal(
        self, solutions: list[ParetoSolution]
    ) -> list[ParetoSolution]:
        """Filter to Pareto-optimal solutions (no solution dominates another).

        A solution A dominates B if A has equal or better score AND equal or
        lower cost, with at least one strictly better.
        """
        if not solutions:
            return []

        pareto: list[ParetoSolution] = []
        for candidate in solutions:
            dominated = False
            for other in solutions:
                if other is candidate:
                    continue
                # Other dominates candidate if:
                # other has >= score AND <= cost, with at least one strictly better
                if (
                    other.resilience_score >= candidate.resilience_score
                    and other.estimated_monthly_cost <= candidate.estimated_monthly_cost
                    and (
                        other.resilience_score > candidate.resilience_score
                        or other.estimated_monthly_cost < candidate.estimated_monthly_cost
                    )
                ):
                    dominated = True
                    break
            if not dominated:
                pareto.append(candidate)

        # Sort by cost
        pareto.sort(key=lambda s: s.estimated_monthly_cost)
        return pareto

    def generate_frontier(
        self, graph: InfraGraph, steps: int = 20
    ) -> ParetoFrontier:
        """Generate the Pareto frontier of cost vs. resilience solutions."""
        if not graph.components:
            empty_sol = ParetoSolution(
                variables={}, resilience_score=0.0,
                estimated_monthly_cost=0.0, availability_nines=0.0,
                spof_count=0, is_current=True,
            )
            return ParetoFrontier(
                solutions=[empty_sol],
                current_solution=empty_sol,
                cheapest_solution=empty_sol,
                most_resilient_solution=empty_sol,
                best_value_solution=empty_sol,
                cost_to_next_nine=0.0,
            )

        base_cost = _calculate_base_cost(graph)
        current = self._build_solution(graph, {}, base_cost, is_current=True)

        # Generate candidate solutions
        change_sets = self._generate_incremental_changes(graph)
        all_solutions = [current]

        for changes in change_sets:
            sol = self._build_solution(graph, changes, base_cost)
            all_solutions.append(sol)

        # Deduplicate by (score, cost) - keep first occurrence
        seen: set[tuple[float, float]] = set()
        unique: list[ParetoSolution] = []
        for sol in all_solutions:
            key = (round(sol.resilience_score, 1), round(sol.estimated_monthly_cost, 0))
            if key not in seen:
                seen.add(key)
                unique.append(sol)

        # Filter to Pareto-optimal
        pareto = self._filter_pareto_optimal(unique)

        # Ensure current solution is in the list
        current_in_pareto = any(s.is_current for s in pareto)
        if not current_in_pareto:
            pareto.append(current)
            pareto.sort(key=lambda s: s.estimated_monthly_cost)

        # Limit to requested steps
        if len(pareto) > steps:
            # Keep evenly spaced solutions + always keep current, cheapest, and most resilient
            step_size = max(1, len(pareto) // steps)
            sampled = pareto[::step_size]
            # Always include first, last, and current
            if pareto[0] not in sampled:
                sampled.insert(0, pareto[0])
            if pareto[-1] not in sampled:
                sampled.append(pareto[-1])
            current_sol = next((s for s in pareto if s.is_current), None)
            if current_sol and current_sol not in sampled:
                sampled.append(current_sol)
            sampled.sort(key=lambda s: s.estimated_monthly_cost)
            pareto = sampled

        # Identify special solutions
        cheapest = min(pareto, key=lambda s: s.estimated_monthly_cost)
        most_resilient = max(pareto, key=lambda s: s.resilience_score)

        # Best value = highest resilience per dollar (avoid division by zero)
        best_value = max(
            pareto,
            key=lambda s: s.resilience_score / max(s.estimated_monthly_cost, 1.0),
        )

        # Cost to next nine
        current_nines = current.availability_nines
        target_nines = math.floor(current_nines) + 1.0
        solutions_above = [
            s for s in pareto
            if s.availability_nines >= target_nines and not s.is_current
        ]
        if solutions_above:
            cheapest_above = min(solutions_above, key=lambda s: s.estimated_monthly_cost)
            cost_to_next = max(0.0, cheapest_above.estimated_monthly_cost - current.estimated_monthly_cost)
        else:
            cost_to_next = 0.0

        return ParetoFrontier(
            solutions=pareto,
            current_solution=current,
            cheapest_solution=cheapest,
            most_resilient_solution=most_resilient,
            best_value_solution=best_value,
            cost_to_next_nine=round(cost_to_next, 2),
        )

    def optimize(
        self,
        graph: InfraGraph,
        budget: float | None = None,
        target_score: float | None = None,
    ) -> ParetoFrontier:
        """Run optimization with optional budget or target score constraints.

        Args:
            graph: The infrastructure graph to optimize.
            budget: Maximum monthly budget (if set, filters solutions).
            target_score: Target resilience score to achieve.

        Returns:
            ParetoFrontier with all Pareto-optimal solutions.
        """
        frontier = self.generate_frontier(graph)

        if budget is not None:
            frontier.solutions = [
                s for s in frontier.solutions
                if s.estimated_monthly_cost <= budget
            ]
            if not frontier.solutions:
                frontier.solutions = [frontier.current_solution]

        if target_score is not None:
            viable = [
                s for s in frontier.solutions
                if s.resilience_score >= target_score
            ]
            if viable:
                frontier.solutions = viable

        return frontier

    def find_cheapest_for_score(
        self, graph: InfraGraph, target_score: float
    ) -> ParetoSolution:
        """Find the cheapest solution that achieves the target score."""
        frontier = self.generate_frontier(graph, steps=50)
        viable = [
            s for s in frontier.solutions
            if s.resilience_score >= target_score
        ]
        if viable:
            return min(viable, key=lambda s: s.estimated_monthly_cost)
        # If no solution reaches the target, return the most resilient
        return frontier.most_resilient_solution

    def find_best_for_budget(
        self, graph: InfraGraph, budget: float
    ) -> ParetoSolution:
        """Find the best solution within the given budget."""
        frontier = self.generate_frontier(graph, steps=50)
        affordable = [
            s for s in frontier.solutions
            if s.estimated_monthly_cost <= budget
        ]
        if affordable:
            return max(affordable, key=lambda s: s.resilience_score)
        # If nothing is affordable, return the cheapest
        return frontier.cheapest_solution

    def cost_to_improve(
        self, graph: InfraGraph, target_delta: float
    ) -> float:
        """Calculate the cost to improve resilience by target_delta points."""
        frontier = self.generate_frontier(graph)
        current_score = frontier.current_solution.resilience_score
        target_score = current_score + target_delta

        viable = [
            s for s in frontier.solutions
            if s.resilience_score >= target_score and not s.is_current
        ]
        if viable:
            cheapest = min(viable, key=lambda s: s.estimated_monthly_cost)
            return max(
                0.0,
                cheapest.estimated_monthly_cost
                - frontier.current_solution.estimated_monthly_cost,
            )
        return 0.0
