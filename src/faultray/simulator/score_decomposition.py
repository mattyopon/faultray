# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Resilience Score Decomposition.

Breaks down the resilience score into its constituent parts, showing
exactly why the score is what it is and what would change it.

Like a credit score breakdown:
  Score: 72/100

  SPOF Penalty:        -15 points (3 single points of failure)
  Utilization Penalty:  -5 points (2 components above 80%)
  Chain Depth Penalty:  -3 points (max depth: 4)
  Redundancy Bonus:     +5 points (avg replicas: 2.5)
  Failover Bonus:       +3 points (60% failover coverage)
  Circuit Breaker Bonus: +2 points (40% CB coverage)

  Biggest Improvement: Remove SPOF on postgres -> +8 points
"""

from __future__ import annotations

from dataclasses import dataclass, field

from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ScoreFactor:
    """A single factor contributing to the resilience score."""

    name: str
    category: str  # "penalty", "bonus", "neutral"
    points: float  # negative for penalties, positive for bonuses
    description: str
    affected_components: list[str] = field(default_factory=list)
    remediation: str | None = None


@dataclass
class ScoreImprovement:
    """A potential improvement action with estimated impact."""

    action: str
    component_id: str
    estimated_improvement: float  # points gained
    effort: str  # "low", "medium", "high"
    description: str


@dataclass
class ScoreDecomposition:
    """Complete decomposition of the resilience score."""

    total_score: float
    max_possible_score: float = 100.0
    factors: list[ScoreFactor] = field(default_factory=list)
    penalties_total: float = 0.0
    bonuses_total: float = 0.0
    base_score: float = 100.0
    improvements: list[ScoreImprovement] = field(default_factory=list)
    score_breakdown_text: str = ""
    grade: str = "C"
    percentile_estimate: float = 50.0

    def to_dict(self) -> dict:
        """Serialise the decomposition to a JSON-friendly dictionary."""
        return {
            "total_score": round(self.total_score, 1),
            "max_possible_score": self.max_possible_score,
            "base_score": self.base_score,
            "penalties_total": round(self.penalties_total, 1),
            "bonuses_total": round(self.bonuses_total, 1),
            "grade": self.grade,
            "percentile_estimate": round(self.percentile_estimate, 1),
            "score_breakdown_text": self.score_breakdown_text,
            "factors": [
                {
                    "name": f.name,
                    "category": f.category,
                    "points": round(f.points, 1),
                    "description": f.description,
                    "affected_components": f.affected_components,
                    "remediation": f.remediation,
                }
                for f in self.factors
            ],
            "improvements": [
                {
                    "action": imp.action,
                    "component_id": imp.component_id,
                    "estimated_improvement": round(imp.estimated_improvement, 1),
                    "effort": imp.effort,
                    "description": imp.description,
                }
                for imp in self.improvements
            ],
        }


# ---------------------------------------------------------------------------
# Grade and percentile heuristics
# ---------------------------------------------------------------------------

_GRADE_THRESHOLDS = [
    (95, "A+"),
    (90, "A"),
    (85, "A-"),
    (80, "B+"),
    (75, "B"),
    (70, "B-"),
    (65, "C+"),
    (60, "C"),
    (55, "C-"),
    (50, "D+"),
    (45, "D"),
    (40, "D-"),
    (0, "F"),
]


def _score_to_grade(score: float) -> str:
    for threshold, grade in _GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


def _score_to_percentile(score: float) -> float:
    """Rough estimate of where this score lands relative to typical infra."""
    if score >= 90:
        return 95.0
    elif score >= 80:
        return 85.0
    elif score >= 70:
        return 70.0
    elif score >= 60:
        return 55.0
    elif score >= 50:
        return 40.0
    elif score >= 40:
        return 25.0
    else:
        return 10.0


# ---------------------------------------------------------------------------
# ScoreDecomposer
# ---------------------------------------------------------------------------


class ScoreDecomposer:
    """Decompose the resilience_score() algorithm from InfraGraph into factors."""

    def decompose(self, graph: InfraGraph) -> ScoreDecomposition:
        """Break down the resilience score into penalties and bonuses.

        This replicates the exact logic of InfraGraph.resilience_score() but
        tracks each contributing factor individually.
        """
        if not graph.components:
            return ScoreDecomposition(
                total_score=0.0,
                score_breakdown_text="No components loaded.",
                grade="F",
                percentile_estimate=0.0,
            )

        base_score = 100.0
        factors: list[ScoreFactor] = []
        improvements: list[ScoreImprovement] = []
        running_score = base_score

        # ------------------------------------------------------------------
        # SPOF Penalties (mirrors resilience_score logic exactly)
        # ------------------------------------------------------------------
        total_spof_penalty = 0.0
        spof_components: list[str] = []
        spof_details: dict[str, float] = {}

        for comp in graph.components.values():
            dependents = graph.get_dependents(comp.id)
            if comp.replicas <= 1 and len(dependents) > 0:
                weighted_deps = 0.0
                for dep_comp in dependents:
                    edge = graph.get_dependency_edge(dep_comp.id, comp.id)
                    if edge:
                        dep_type = edge.dependency_type
                        if dep_type == "requires":
                            weighted_deps += 1.0
                        elif dep_type == "optional":
                            weighted_deps += 0.3
                        else:
                            weighted_deps += 0.1
                    else:
                        weighted_deps += 1.0

                penalty = min(20, weighted_deps * 5)

                # Track original penalty before mitigation for improvement estimation
                original_penalty = penalty

                if comp.failover.enabled:
                    penalty *= 0.3
                if comp.autoscaling.enabled:
                    penalty *= 0.5

                if penalty > 0:
                    total_spof_penalty += penalty
                    spof_components.append(comp.id)
                    spof_details[comp.id] = penalty

                    # Calculate what fixing this SPOF would save
                    improvement_points = penalty  # removing the SPOF removes its penalty
                    improvements.append(ScoreImprovement(
                        action="add-replica",
                        component_id=comp.id,
                        estimated_improvement=round(improvement_points, 1),
                        effort="medium",
                        description=(
                            f"Add replicas to '{comp.name}' to eliminate single point of failure. "
                            f"Currently has {len(dependents)} dependent(s)."
                        ),
                    ))

                    # If no failover, suggest that too
                    if not comp.failover.enabled:
                        failover_save = original_penalty - (original_penalty * 0.3)
                        if comp.autoscaling.enabled:
                            failover_save *= 0.5
                        improvements.append(ScoreImprovement(
                            action="enable-failover",
                            component_id=comp.id,
                            estimated_improvement=round(failover_save, 1),
                            effort="medium",
                            description=(
                                f"Enable failover on '{comp.name}' to reduce SPOF risk. "
                                f"Would reduce penalty by ~{failover_save:.1f} points."
                            ),
                        ))

        if total_spof_penalty > 0:
            factors.append(ScoreFactor(
                name="Single Points of Failure",
                category="penalty",
                points=-total_spof_penalty,
                description=(
                    f"{len(spof_components)} component(s) with replicas=1 and dependencies. "
                    f"Weighted by dependency type (requires=1.0, optional=0.3, async=0.1)."
                ),
                affected_components=spof_components,
                remediation="Add replicas, enable failover, or enable autoscaling.",
            ))
            running_score -= total_spof_penalty

        # ------------------------------------------------------------------
        # Utilization Penalties
        # ------------------------------------------------------------------
        total_util_penalty = 0.0
        high_util_comps: list[str] = []

        for comp in graph.components.values():
            util = comp.utilization()
            comp_penalty = 0.0
            if util > 90:
                comp_penalty = 15
            elif util > 80:
                comp_penalty = 8
            elif util > 70:
                comp_penalty = 3

            if comp_penalty > 0:
                total_util_penalty += comp_penalty
                high_util_comps.append(comp.id)

                if not comp.autoscaling.enabled:
                    improvements.append(ScoreImprovement(
                        action="enable-autoscaling",
                        component_id=comp.id,
                        estimated_improvement=round(comp_penalty * 0.5, 1),
                        effort="low",
                        description=(
                            f"Enable autoscaling on '{comp.name}' (utilization: {util:.0f}%). "
                            "Would help handle load spikes."
                        ),
                    ))

        if total_util_penalty > 0:
            factors.append(ScoreFactor(
                name="High Utilization",
                category="penalty",
                points=-total_util_penalty,
                description=(
                    f"{len(high_util_comps)} component(s) above 70% utilization. "
                    f">90%=-15pts, >80%=-8pts, >70%=-3pts per component."
                ),
                affected_components=high_util_comps,
                remediation="Scale up, enable autoscaling, or optimize resource usage.",
            ))
            running_score -= total_util_penalty

        # ------------------------------------------------------------------
        # Dependency Chain Depth Penalty
        # ------------------------------------------------------------------
        critical_paths = graph.get_critical_paths()
        max_depth = len(critical_paths[0]) if critical_paths else 0
        chain_penalty = 0.0
        if max_depth > 5:
            chain_penalty = (max_depth - 5) * 5

        if chain_penalty > 0:
            factors.append(ScoreFactor(
                name="Dependency Chain Depth",
                category="penalty",
                points=-chain_penalty,
                description=(
                    f"Maximum dependency chain depth is {max_depth} (threshold: 5). "
                    f"Each level above 5 costs 5 points."
                ),
                affected_components=[],
                remediation="Reduce dependency chain length by introducing caching or async patterns.",
            ))
            running_score -= chain_penalty

        # ------------------------------------------------------------------
        # Bonuses (these are not in the original resilience_score but show
        # positive aspects of the infrastructure)
        # ------------------------------------------------------------------
        total_comps = len(graph.components)

        # Failover coverage
        failover_count = sum(1 for c in graph.components.values() if c.failover.enabled)
        failover_pct = (failover_count / total_comps * 100) if total_comps else 0
        if failover_count > 0:
            factors.append(ScoreFactor(
                name="Failover Coverage",
                category="bonus",
                points=0,  # Implicit in reduced SPOF penalty
                description=(
                    f"{failover_count}/{total_comps} components ({failover_pct:.0f}%) have failover enabled. "
                    "Failover reduces SPOF penalty by 70%."
                ),
                affected_components=[c.id for c in graph.components.values() if c.failover.enabled],
            ))

        # Autoscaling coverage
        autoscale_count = sum(1 for c in graph.components.values() if c.autoscaling.enabled)
        autoscale_pct = (autoscale_count / total_comps * 100) if total_comps else 0
        if autoscale_count > 0:
            factors.append(ScoreFactor(
                name="Autoscaling Coverage",
                category="bonus",
                points=0,  # Implicit in reduced SPOF penalty
                description=(
                    f"{autoscale_count}/{total_comps} components ({autoscale_pct:.0f}%) have autoscaling. "
                    "Autoscaling reduces SPOF penalty by 50%."
                ),
                affected_components=[c.id for c in graph.components.values() if c.autoscaling.enabled],
            ))

        # Circuit breaker coverage
        all_edges = graph.all_dependency_edges()
        cb_count = sum(1 for e in all_edges if e.circuit_breaker.enabled)
        if all_edges:
            cb_pct = cb_count / len(all_edges) * 100
            factors.append(ScoreFactor(
                name="Circuit Breaker Coverage",
                category="bonus" if cb_count > 0 else "neutral",
                points=0,  # Not directly part of v1 score, but informational
                description=(
                    f"{cb_count}/{len(all_edges)} dependency edges ({cb_pct:.0f}%) "
                    "have circuit breakers enabled."
                ),
                affected_components=[],
            ))

        # Replica diversity
        multi_replica = [c for c in graph.components.values() if c.replicas > 1]
        if multi_replica:
            avg_replicas = sum(c.replicas for c in multi_replica) / len(multi_replica)
            factors.append(ScoreFactor(
                name="Replica Redundancy",
                category="bonus",
                points=0,
                description=(
                    f"{len(multi_replica)}/{total_comps} components have multiple replicas. "
                    f"Average replica count (among multi-replica): {avg_replicas:.1f}."
                ),
                affected_components=[c.id for c in multi_replica],
            ))

        # ------------------------------------------------------------------
        # Final score
        # ------------------------------------------------------------------
        final_score = max(0.0, min(100.0, running_score))
        penalties_total = total_spof_penalty + total_util_penalty + chain_penalty
        bonuses_total = 0.0  # In v1, bonuses are implicit (reduced penalties)

        grade = _score_to_grade(final_score)
        percentile = _score_to_percentile(final_score)

        # Sort improvements by estimated impact (descending)
        improvements.sort(key=lambda x: x.estimated_improvement, reverse=True)

        # Build human-readable breakdown text
        breakdown = self._build_breakdown_text(base_score, final_score, factors, improvements)

        return ScoreDecomposition(
            total_score=final_score,
            max_possible_score=100.0,
            factors=factors,
            penalties_total=penalties_total,
            bonuses_total=bonuses_total,
            base_score=base_score,
            improvements=improvements,
            score_breakdown_text=breakdown,
            grade=grade,
            percentile_estimate=percentile,
        )

    def what_if_fix(self, graph: InfraGraph, component_id: str, fix: str) -> float:
        """Estimate the new score if a specific fix is applied.

        Supported fixes:
        - "add-replica": set replicas to 2
        - "enable-failover": enable failover
        - "enable-autoscaling": enable autoscaling
        - "reduce-utilization": set all metrics to 50%
        """

        comp = graph.get_component(component_id)
        if comp is None:
            return graph.resilience_score()

        # Deep copy the graph to simulate the change
        # We simulate by creating a modified copy
        modified = InfraGraph()
        for c in graph.components.values():
            if c.id == component_id:
                c_dict = c.model_dump()
                if fix == "add-replica":
                    c_dict["replicas"] = max(c_dict["replicas"], 2)
                elif fix == "enable-failover":
                    c_dict["failover"]["enabled"] = True
                elif fix == "enable-autoscaling":
                    c_dict["autoscaling"]["enabled"] = True
                elif fix == "reduce-utilization":
                    c_dict["metrics"]["cpu_percent"] = min(c_dict["metrics"]["cpu_percent"], 50)
                    c_dict["metrics"]["memory_percent"] = min(c_dict["metrics"]["memory_percent"], 50)
                    c_dict["metrics"]["disk_percent"] = min(c_dict["metrics"]["disk_percent"], 50)
                    c_dict["metrics"]["network_connections"] = min(
                        c_dict["metrics"]["network_connections"],
                        int(c_dict["capacity"]["max_connections"] * 0.5),
                    )
                from faultray.model.components import Component
                modified.add_component(Component(**c_dict))
            else:
                modified.add_component(c)

        # Copy dependencies
        from faultray.model.components import Dependency
        for edge in graph.all_dependency_edges():
            modified.add_dependency(Dependency(**edge.model_dump()))

        return modified.resilience_score()

    def explain(self, graph: InfraGraph) -> str:
        """Return a human-readable explanation of the score."""
        decomp = self.decompose(graph)
        return decomp.score_breakdown_text

    def to_waterfall_data(self, decomposition: ScoreDecomposition) -> list[dict]:
        """Convert a decomposition into data suitable for a waterfall chart.

        Each entry has: name, value, running_total, category.
        """
        data: list[dict] = []
        running = decomposition.base_score

        # Start bar
        data.append({
            "name": "Base Score",
            "value": decomposition.base_score,
            "running_total": running,
            "category": "base",
        })

        for factor in decomposition.factors:
            if factor.category == "penalty" and factor.points != 0:
                running += factor.points  # points are already negative
                data.append({
                    "name": factor.name,
                    "value": round(factor.points, 1),
                    "running_total": round(running, 1),
                    "category": "penalty",
                })

        # Final bar
        data.append({
            "name": "Final Score",
            "value": round(decomposition.total_score, 1),
            "running_total": round(decomposition.total_score, 1),
            "category": "total",
        })

        return data

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_breakdown_text(
        base_score: float,
        final_score: float,
        factors: list[ScoreFactor],
        improvements: list[ScoreImprovement],
    ) -> str:
        lines: list[str] = []
        lines.append(f"Resilience Score: {final_score:.0f}/100")
        lines.append(f"Grade: {_score_to_grade(final_score)}")
        lines.append("")
        lines.append(f"Starting from base score: {base_score:.0f}")
        lines.append("")

        penalties = [f for f in factors if f.category == "penalty"]
        bonuses = [f for f in factors if f.category in ("bonus", "neutral")]

        if penalties:
            lines.append("PENALTIES:")
            for f in penalties:
                lines.append(f"  {f.name}: {f.points:+.1f} points")
                lines.append(f"    {f.description}")
                if f.remediation:
                    lines.append(f"    Fix: {f.remediation}")
            lines.append("")

        if bonuses:
            lines.append("POSITIVE FACTORS:")
            for f in bonuses:
                lines.append(f"  {f.name}: {f.description}")
            lines.append("")

        if improvements:
            lines.append("TOP IMPROVEMENTS:")
            for i, imp in enumerate(improvements[:5], 1):
                lines.append(
                    f"  {i}. {imp.action} on {imp.component_id} -> "
                    f"+{imp.estimated_improvement:.1f} points ({imp.effort} effort)"
                )
                lines.append(f"     {imp.description}")

        return "\n".join(lines)
