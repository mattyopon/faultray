"""Dependency Impact Scorer for ChaosProof.

Score each dependency edge by "cost if broken" -- quantify the impact of
every single dependency in the infrastructure graph.

Usage:
    from infrasim.simulator.dependency_scorer import DependencyScorer
    scorer = DependencyScorer(graph)
    impacts = scorer.score_all()
    top5 = scorer.most_critical(n=5)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from infrasim.model.components import HealthStatus
from infrasim.model.graph import InfraGraph
from infrasim.simulator.cascade import CascadeEngine
from infrasim.simulator.engine import SimulationEngine
from infrasim.simulator.scenarios import Fault, FaultType, Scenario


@dataclass
class DependencyImpact:
    """Impact assessment for a single dependency edge."""

    source_id: str
    target_id: str
    dependency_type: str
    impact_score: float  # 0-10
    cascade_depth: int
    affected_component_count: int
    estimated_cost_if_broken: float
    criticality: str  # "critical", "high", "medium", "low"
    affected_components: list[str] = field(default_factory=list)
    risk_details: str = ""


class DependencyScorer:
    """Score every dependency edge by impact if broken.

    For each dependency edge (source -> target):
    1. Simulate the target going down
    2. Count cascade effects
    3. Estimate cost from cascade
    4. Score = f(cascade_depth, affected_count, cost)

    This helps identify the most critical dependencies that need
    circuit breakers, failover, or redundancy.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph
        self._cascade_engine = CascadeEngine(graph)
        self._sim_engine = SimulationEngine(graph)

    def score_all(self) -> list[DependencyImpact]:
        """Score every dependency edge by impact if broken.

        Returns:
            List of DependencyImpact, sorted by impact_score descending.
        """
        impacts: list[DependencyImpact] = []
        scored_targets: dict[str, tuple] = {}  # Cache simulation results per target

        for dep in self.graph.all_dependency_edges():
            target_id = dep.target_id
            source_id = dep.source_id

            # Run simulation for target (cache results for same target)
            if target_id not in scored_targets:
                scored_targets[target_id] = self._simulate_target_down(target_id)

            sim_result, affected, cascade_depth, cost = scored_targets[target_id]

            # Calculate impact score
            impact_score = self._calculate_impact_score(
                dep.dependency_type,
                dep.weight,
                cascade_depth,
                len(affected),
                cost,
            )

            # Determine criticality label
            criticality = self._criticality_label(impact_score)

            impacts.append(DependencyImpact(
                source_id=source_id,
                target_id=target_id,
                dependency_type=dep.dependency_type,
                impact_score=round(impact_score, 2),
                cascade_depth=cascade_depth,
                affected_component_count=len(affected),
                estimated_cost_if_broken=round(cost, 2),
                criticality=criticality,
                affected_components=sorted(affected),
                risk_details=self._risk_details(
                    source_id, target_id, dep.dependency_type,
                    cascade_depth, len(affected), cost,
                ),
            ))

        # Sort by impact score descending
        impacts.sort(key=lambda x: x.impact_score, reverse=True)
        return impacts

    def most_critical(self, n: int = 5) -> list[DependencyImpact]:
        """Return the top N most critical dependencies.

        Args:
            n: Number of top dependencies to return.

        Returns:
            List of the N most impactful dependency edges.
        """
        all_impacts = self.score_all()
        return all_impacts[:n]

    def dependency_heatmap_data(self) -> dict:
        """Generate data suitable for visualization as a heatmap.

        Returns:
            Dict with 'edges' list containing source, target, score, and color.
        """
        impacts = self.score_all()
        edges = []
        for impact in impacts:
            color = self._score_to_color(impact.impact_score)
            edges.append({
                "source": impact.source_id,
                "target": impact.target_id,
                "score": impact.impact_score,
                "color": color,
                "criticality": impact.criticality,
                "affected_count": impact.affected_component_count,
                "cascade_depth": impact.cascade_depth,
                "cost": impact.estimated_cost_if_broken,
            })

        return {
            "total_edges": len(edges),
            "edges": edges,
            "summary": {
                "critical": sum(1 for e in edges if e["criticality"] == "critical"),
                "high": sum(1 for e in edges if e["criticality"] == "high"),
                "medium": sum(1 for e in edges if e["criticality"] == "medium"),
                "low": sum(1 for e in edges if e["criticality"] == "low"),
            },
        }

    def _simulate_target_down(
        self, target_id: str,
    ) -> tuple[object, list[str], int, float]:
        """Simulate the target going down and return cascade details.

        Returns:
            Tuple of (scenario_result, affected_ids, cascade_depth, estimated_cost).
        """
        scenario = Scenario(
            id=f"dep-score-{target_id}",
            name=f"Dependency break: {target_id}",
            description=f"Simulate {target_id} going down",
            faults=[
                Fault(
                    target_component_id=target_id,
                    fault_type=FaultType.COMPONENT_DOWN,
                    severity=1.0,
                )
            ],
        )

        result = self._sim_engine.run_scenario(scenario)

        # Extract affected component IDs (excluding the target itself)
        affected = []
        max_depth = 0
        for effect in result.cascade.effects:
            if effect.component_id != target_id:
                affected.append(effect.component_id)
            # Estimate depth from estimated_time_seconds
            if effect.estimated_time_seconds > 0:
                depth = max(1, effect.estimated_time_seconds // 10)
                max_depth = max(max_depth, int(depth))

        # If no time-based depth, use BFS depth from graph
        if max_depth == 0 and affected:
            all_affected = self.graph.get_all_affected(target_id)
            max_depth = min(len(all_affected), 10)

        # Estimate cost
        cost = self._estimate_cost(target_id, affected)

        return result, affected, max_depth, cost

    def _estimate_cost(self, target_id: str, affected_ids: list[str]) -> float:
        """Estimate the cost of a dependency break.

        Cost = sum of (revenue_per_minute * assumed_downtime_minutes) for
        all affected components + the target itself.
        """
        all_ids = [target_id] + affected_ids
        total_cost = 0.0

        for comp_id in all_ids:
            comp = self.graph.get_component(comp_id)
            if comp is None:
                continue

            cost_profile = comp.cost_profile
            # Assume 30 minutes of downtime for cost estimation
            downtime_minutes = 30.0
            revenue_loss = cost_profile.revenue_per_minute * downtime_minutes
            infra_cost = cost_profile.hourly_infra_cost * (downtime_minutes / 60.0)
            engineer_cost = cost_profile.recovery_engineer_cost

            total_cost += revenue_loss + infra_cost + engineer_cost

        return total_cost

    def _calculate_impact_score(
        self,
        dep_type: str,
        weight: float,
        cascade_depth: int,
        affected_count: int,
        cost: float,
    ) -> float:
        """Calculate an impact score from 0-10 for a dependency edge.

        Factors:
        - Dependency type (requires > optional > async)
        - Dependency weight
        - Cascade depth (deeper = more impactful)
        - Number of affected components
        - Estimated cost
        """
        total_components = max(len(self.graph.components), 1)

        # Base score from dependency type (0-3)
        type_scores = {"requires": 3.0, "optional": 1.0, "async": 0.5}
        type_score = type_scores.get(dep_type, 1.5)

        # Spread score: fraction of system affected (0-3)
        spread = affected_count / total_components
        spread_score = min(3.0, spread * 6.0)  # 50% affected = 3.0

        # Depth score (0-2)
        depth_score = min(2.0, cascade_depth * 0.5)

        # Cost score (0-2) -- logarithmic scale
        if cost > 10000:
            cost_score = 2.0
        elif cost > 1000:
            cost_score = 1.5
        elif cost > 100:
            cost_score = 1.0
        elif cost > 0:
            cost_score = 0.5
        else:
            cost_score = 0.0

        raw_score = (type_score + spread_score + depth_score + cost_score) * weight
        return min(10.0, max(0.0, raw_score))

    @staticmethod
    def _criticality_label(score: float) -> str:
        """Convert a numeric score to a criticality label."""
        if score >= 7.0:
            return "critical"
        elif score >= 5.0:
            return "high"
        elif score >= 3.0:
            return "medium"
        else:
            return "low"

    @staticmethod
    def _score_to_color(score: float) -> str:
        """Convert an impact score to a color for visualization."""
        if score >= 7.0:
            return "#ff0000"  # red
        elif score >= 5.0:
            return "#ff8800"  # orange
        elif score >= 3.0:
            return "#ffcc00"  # yellow
        else:
            return "#00cc00"  # green

    @staticmethod
    def _risk_details(
        source_id: str,
        target_id: str,
        dep_type: str,
        cascade_depth: int,
        affected_count: int,
        cost: float,
    ) -> str:
        """Generate a human-readable risk description."""
        parts = [
            f"{source_id} -> {target_id} ({dep_type}): ",
            f"cascade depth={cascade_depth}, ",
            f"affected={affected_count} components, ",
            f"estimated cost=${cost:.2f}",
        ]
        return "".join(parts)
