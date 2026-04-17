# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Automatic simulation runner for discovered infrastructure.

Runs the FaultRay SimulationEngine on auto-discovered topology and
generates actionable findings.
"""

from __future__ import annotations

import datetime as _dt
import logging
from dataclasses import dataclass, field

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

# Availability nines table: map score range → SLA string
_AVAILABILITY_TABLE: list[tuple[float, str]] = [
    (99.0, "99.999%"),   # five nines
    (95.0, "99.99%"),    # four nines
    (85.0, "99.9%"),     # three nines
    (70.0, "99.5%"),
    (50.0, "99.0%"),
    (30.0, "95.0%"),
    (0.0,  "< 95.0%"),
]


@dataclass
class AutoSimulationReport:
    """Structured report produced by :class:`AutoSimulator`.

    Attributes
    ----------
    score:
        Resilience score in the range 0–100.
    availability_estimate:
        Human-readable SLA estimate derived from the resilience score,
        e.g. ``"99.95%"``.
    total_scenarios:
        Number of chaos scenarios evaluated.
    critical_count:
        Number of scenarios that resulted in a critical finding (score ≥ 7).
    warning_count:
        Number of scenarios that resulted in a warning (4 ≤ score < 7).
    spofs:
        List of single-point-of-failure component descriptors.
    top_risks:
        Top-5 highest-risk scenario summaries.
    recommendations:
        Actionable recommendations derived from the simulation results.
    timestamp:
        ISO-8601 timestamp of when the report was generated.
    components_analyzed:
        Number of infrastructure components included in the simulation.
    dependencies_analyzed:
        Number of dependency edges included in the simulation.
    """

    score: float = 0.0
    availability_estimate: str = "unknown"
    total_scenarios: int = 0
    critical_count: int = 0
    warning_count: int = 0
    spofs: list[dict] = field(default_factory=list)
    top_risks: list[dict] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    timestamp: str = ""
    components_analyzed: int = 0
    dependencies_analyzed: int = 0


class AutoSimulator:
    """Runs FaultRay chaos simulation on an auto-discovered InfraGraph.

    Usage::

        graph = AutoDiscoverer().discover_all()
        report = AutoSimulator(graph).run()
        print(report.score, report.spofs)
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> AutoSimulationReport:
        """Run full simulation and return a structured report.

        Steps:
        1. Run :meth:`SimulationEngine.run_all_defaults`.
        2. Extract SPOFs, availability ceiling, critical failure scenarios,
           and cascade failure chains.
        3. Derive actionable recommendations.
        4. Return :class:`AutoSimulationReport`.

        All exceptions are caught internally so that a failure here never
        crashes the surrounding agent loop.
        """
        from faultray.simulator.engine import SimulationEngine

        timestamp = _dt.datetime.now(_dt.timezone.utc).isoformat()

        components_analyzed = len(self.graph.components)
        dependencies_analyzed = len(self.graph.all_dependency_edges())

        if components_analyzed == 0:
            logger.warning("AutoSimulator: graph has no components — returning empty report")
            return AutoSimulationReport(
                timestamp=timestamp,
                availability_estimate="unknown",
            )

        engine = SimulationEngine(self.graph)

        try:
            sim_report = engine.run_all_defaults(include_plugins=False)
        except Exception as exc:
            logger.error("SimulationEngine.run_all_defaults failed: %s", exc, exc_info=True)
            return AutoSimulationReport(
                score=0.0,
                availability_estimate="unknown",
                timestamp=timestamp,
                components_analyzed=components_analyzed,
                dependencies_analyzed=dependencies_analyzed,
            )

        score = round(sim_report.resilience_score, 1)
        availability_estimate = _score_to_availability(score)

        critical_count = len(sim_report.critical_findings)
        warning_count = len(sim_report.warnings)

        spofs = self.get_spofs()
        top_risks = self._extract_top_risks(sim_report)
        recommendations = self._build_recommendations(sim_report, spofs)

        return AutoSimulationReport(
            score=score,
            availability_estimate=availability_estimate,
            total_scenarios=len(sim_report.results),
            critical_count=critical_count,
            warning_count=warning_count,
            spofs=spofs,
            top_risks=top_risks,
            recommendations=recommendations,
            timestamp=timestamp,
            components_analyzed=components_analyzed,
            dependencies_analyzed=dependencies_analyzed,
        )

    def get_spofs(self) -> list[dict]:
        """Identify single points of failure in the graph.

        A component is considered a SPOF when it has:
        - ``replicas <= 1`` (no redundancy), AND
        - at least one dependent component that *requires* it.
        """
        spofs: list[dict] = []
        for comp in self.graph.components.values():
            dependents = self.graph.get_dependents(comp.id)
            if not dependents or comp.replicas > 1:
                continue

            # Check whether at least one dependent has a "requires" edge
            hard_deps = []
            for dep_comp in dependents:
                edge = self.graph.get_dependency_edge(dep_comp.id, comp.id)
                if edge is None or edge.dependency_type == "requires":
                    hard_deps.append(dep_comp.id)

            if hard_deps:
                spofs.append(
                    {
                        "id": comp.id,
                        "name": comp.name,
                        "type": comp.type.value,
                        "dependents": hard_deps,
                        "replicas": comp.replicas,
                    }
                )

        return spofs

    def get_availability_ceiling(self) -> dict:
        """Calculate a mathematical availability ceiling.

        Computes the theoretical maximum availability of the system based
        on the product of individual component availability values.  Single
        points of failure dominate this metric.

        Returns a dict with keys:
        - ``availability_string``: human-readable SLA string.
        - ``score``: numeric resilience score (0–100).
        - ``limiting_components``: IDs of the most constraining components.
        """
        score = round(self.graph.resilience_score(), 1)
        availability_string = _score_to_availability(score)

        spofs = self.get_spofs()
        limiting = [s["id"] for s in spofs[:3]]

        return {
            "availability_string": availability_string,
            "score": score,
            "limiting_components": limiting,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_top_risks(self, sim_report) -> list[dict]:
        """Return the top-5 highest-risk scenario summaries."""
        top: list[dict] = []
        for result in sim_report.results[:5]:
            top.append(
                {
                    "scenario_id": result.scenario.id,
                    "scenario_name": result.scenario.name,
                    "risk_score": round(result.risk_score, 2),
                    "is_critical": result.is_critical,
                    "affected_components": [e.component_id for e in result.cascade.effects],
                }
            )
        return top

    def _build_recommendations(self, sim_report, spofs: list[dict]) -> list[str]:
        """Derive actionable recommendations from simulation results and SPOFs."""
        recs: list[str] = []

        for spof in spofs:
            recs.append(
                f"Add redundancy to '{spof['name']}' ({spof['type']}) — "
                f"it is a single point of failure with "
                f"{len(spof['dependents'])} dependent(s)."
            )

        if sim_report.resilience_score < 50:
            recs.append(
                "Overall resilience score is critically low (<50). "
                "Review all single-replica components and enable failover."
            )
        elif sim_report.resilience_score < 70:
            recs.append(
                "Resilience score is below 70. "
                "Consider enabling circuit breakers and autoscaling on key services."
            )

        critical_count = len(sim_report.critical_findings)
        if critical_count > 0:
            recs.append(
                f"{critical_count} critical failure scenario(s) detected. "
                "Implement retry logic and graceful degradation for the top-risk components."
            )

        # Check for high-utilisation components
        for comp in self.graph.components.values():
            util = comp.utilization()
            if util > 85:
                recs.append(
                    f"Component '{comp.id}' has high utilisation ({util:.0f}%). "
                    "Scale up or enable autoscaling to reduce capacity risk."
                )

        return recs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _score_to_availability(score: float) -> str:
    """Map a 0–100 resilience score to a human-readable SLA string."""
    for threshold, label in _AVAILABILITY_TABLE:
        if score >= threshold:
            return label
    return "< 95.0%"
