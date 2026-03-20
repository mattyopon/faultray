# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Infrastructure Replay Engine -- replay past incidents from JSON timelines.

Convert incident timelines (JSON) into simulation scenarios and replay them
against an InfraGraph. This complements the existing ``IncidentReplayEngine``
(which replays known historical cloud outages) by letting users supply their
own incident data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeEngine
from faultray.simulator.engine import ScenarioResult, SimulationEngine
from faultray.simulator.scenarios import Fault, FaultType, Scenario


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class IncidentTimelineEvent:
    """A single event in a user-supplied incident timeline."""

    timestamp_offset_seconds: int
    event_type: str  # "component_down", "traffic_spike", "recovery", "escalation"
    component_id: str
    details: str = ""


@dataclass
class IncidentTimeline:
    """An incident timeline loaded from JSON."""

    incident_id: str
    title: str
    start_time: str
    duration_minutes: float
    events: list[IncidentTimelineEvent]
    root_cause: str = ""
    resolution: str = ""
    severity: float = 5.0  # 0-10 scale from incident data


@dataclass
class CounterfactualResult:
    """A single what-if counterfactual."""

    description: str
    modified_parameter: str
    original_value: str
    modified_value: str
    original_severity: float
    counterfactual_severity: float
    improvement: float  # positive means better


@dataclass
class ReplayResult:
    """Result of replaying an incident timeline."""

    incident_id: str
    simulation_matches_reality: bool
    predicted_severity: float
    actual_severity: float  # from incident data
    divergence_point_seconds: int | None  # where simulation diverged from reality
    lessons: list[str]
    counterfactuals: list[CounterfactualResult]
    scenario_results: list[ScenarioResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ReplayEngine:
    """Replay user-supplied incident timelines against an InfraGraph."""

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph
        self.engine = SimulationEngine(graph)
        self.cascade_engine = CascadeEngine(graph)

    def replay(self, timeline: IncidentTimeline) -> ReplayResult:
        """Replay an incident timeline and compare with the recorded outcome.

        The engine converts each event in the timeline into a simulation
        scenario, runs it, and aggregates the results.
        """
        scenario_results: list[ScenarioResult] = []

        # Build scenario(s) from the timeline events
        scenarios = self._timeline_to_scenarios(timeline)
        for scenario in scenarios:
            result = self.engine.run_scenario(scenario)
            scenario_results.append(result)

        # Aggregate predicted severity
        if scenario_results:
            predicted_severity = max(r.risk_score for r in scenario_results)
        else:
            predicted_severity = 0.0

        actual_severity = timeline.severity

        # Check if simulation matches reality (within 2.0 tolerance)
        matches = abs(predicted_severity - actual_severity) < 2.0

        # Find divergence point
        divergence_point = self._find_divergence_point(
            timeline, scenario_results
        )

        # Generate lessons
        lessons = self._generate_lessons(
            timeline, scenario_results, predicted_severity, actual_severity
        )

        # Generate counterfactuals
        counterfactuals = self.generate_counterfactuals(timeline)

        return ReplayResult(
            incident_id=timeline.incident_id,
            simulation_matches_reality=matches,
            predicted_severity=round(predicted_severity, 1),
            actual_severity=actual_severity,
            divergence_point_seconds=divergence_point,
            lessons=lessons,
            counterfactuals=counterfactuals,
            scenario_results=scenario_results,
        )

    def import_timeline_from_json(self, path: Path) -> IncidentTimeline:
        """Load an incident timeline from a JSON file.

        Expected JSON structure::

            {
                "incident_id": "INC-2024-001",
                "title": "Database primary failover",
                "start_time": "2024-01-15T02:30:00Z",
                "duration_minutes": 45,
                "severity": 7.5,
                "root_cause": "Disk full on primary DB",
                "resolution": "Promoted read-replica, expanded disk",
                "events": [
                    {
                        "timestamp_offset_seconds": 0,
                        "event_type": "component_down",
                        "component_id": "db-primary",
                        "details": "Disk full, writes failing"
                    },
                    ...
                ]
            }
        """
        data = json.loads(path.read_text(encoding="utf-8"))
        events = [
            IncidentTimelineEvent(**ev) for ev in data.get("events", [])
        ]
        return IncidentTimeline(
            incident_id=data["incident_id"],
            title=data.get("title", ""),
            start_time=data.get("start_time", ""),
            duration_minutes=data.get("duration_minutes", 0),
            events=events,
            root_cause=data.get("root_cause", ""),
            resolution=data.get("resolution", ""),
            severity=data.get("severity", 5.0),
        )

    def generate_counterfactuals(
        self, timeline: IncidentTimeline
    ) -> list[CounterfactualResult]:
        """What-if analysis: how would different configs change the outcome?

        Generates counterfactuals such as:
        - "What if we had 2x replicas?"
        - "What if we had circuit breakers?"
        - "What if MTTR was 5min instead of 30min?"
        """
        counterfactuals: list[CounterfactualResult] = []

        # Get the baseline severity
        baseline_scenarios = self._timeline_to_scenarios(timeline)
        if not baseline_scenarios:
            return counterfactuals
        baseline_results = [
            self.engine.run_scenario(s) for s in baseline_scenarios
        ]
        baseline_severity = max(
            (r.risk_score for r in baseline_results), default=0.0
        )

        # Counterfactual 1: What if affected components had 2x replicas?
        affected_ids = set()
        for ev in timeline.events:
            if ev.event_type in ("component_down", "traffic_spike"):
                if ev.component_id in self.graph.components:
                    affected_ids.add(ev.component_id)

        if affected_ids:
            # Estimate the impact with replicas -- we can approximate by
            # noting that components with replicas > 1 tend to degrade rather
            # than go down, cutting severity roughly in half.
            replica_severity = baseline_severity * 0.5
            counterfactuals.append(
                CounterfactualResult(
                    description=(
                        "What if affected components had 2x replicas?"
                    ),
                    modified_parameter="replicas",
                    original_value="1",
                    modified_value="2+",
                    original_severity=baseline_severity,
                    counterfactual_severity=round(replica_severity, 1),
                    improvement=round(
                        baseline_severity - replica_severity, 1
                    ),
                )
            )

        # Counterfactual 2: What if we had circuit breakers on all edges?
        edges = self.graph.all_dependency_edges()
        unprotected = sum(1 for e in edges if not e.circuit_breaker.enabled)
        if unprotected > 0:
            cb_severity = baseline_severity * 0.6
            counterfactuals.append(
                CounterfactualResult(
                    description=(
                        "What if circuit breakers were enabled on all "
                        f"{unprotected} unprotected dependency edges?"
                    ),
                    modified_parameter="circuit_breaker.enabled",
                    original_value="false",
                    modified_value="true",
                    original_severity=baseline_severity,
                    counterfactual_severity=round(cb_severity, 1),
                    improvement=round(baseline_severity - cb_severity, 1),
                )
            )

        # Counterfactual 3: What if MTTR was 5min instead of 30min?
        high_mttr = [
            c
            for c in self.graph.components.values()
            if c.operational_profile.mttr_minutes > 10
        ]
        if high_mttr:
            mttr_severity = baseline_severity * 0.7
            avg_mttr = sum(
                c.operational_profile.mttr_minutes for c in high_mttr
            ) / len(high_mttr)
            counterfactuals.append(
                CounterfactualResult(
                    description=(
                        f"What if MTTR was 5min instead of {avg_mttr:.0f}min?"
                    ),
                    modified_parameter="mttr_minutes",
                    original_value=f"{avg_mttr:.0f}",
                    modified_value="5",
                    original_severity=baseline_severity,
                    counterfactual_severity=round(mttr_severity, 1),
                    improvement=round(baseline_severity - mttr_severity, 1),
                )
            )

        return counterfactuals

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _timeline_to_scenarios(
        self, timeline: IncidentTimeline
    ) -> list[Scenario]:
        """Convert a timeline into one or more Scenario objects."""
        scenarios: list[Scenario] = []
        faults: list[Fault] = []
        traffic_multiplier = 1.0

        for ev in timeline.events:
            comp = self.graph.get_component(ev.component_id)
            if not comp:
                continue

            if ev.event_type == "component_down":
                faults.append(
                    Fault(
                        target_component_id=ev.component_id,
                        fault_type=FaultType.COMPONENT_DOWN,
                        severity=1.0,
                    )
                )
            elif ev.event_type == "traffic_spike":
                traffic_multiplier = max(traffic_multiplier, 3.0)
            elif ev.event_type == "escalation":
                faults.append(
                    Fault(
                        target_component_id=ev.component_id,
                        fault_type=FaultType.LATENCY_SPIKE,
                        severity=0.8,
                    )
                )
            # "recovery" events are skipped (they represent resolution)

        if faults or traffic_multiplier > 1.0:
            scenarios.append(
                Scenario(
                    id=f"replay-{timeline.incident_id}",
                    name=f"Replay: {timeline.title}",
                    description=f"Replayed incident {timeline.incident_id}",
                    faults=faults,
                    traffic_multiplier=traffic_multiplier,
                )
            )

        return scenarios

    def _find_divergence_point(
        self,
        timeline: IncidentTimeline,
        results: list[ScenarioResult],
    ) -> int | None:
        """Find the timestamp (seconds) where simulation diverges from reality.

        A simple heuristic: if the simulation severity differs from the
        recorded severity by more than 2.0, we look at when the first
        "recovery" event occurred but the simulation showed no recovery.
        """
        if not results:
            return None

        predicted = max(r.risk_score for r in results)
        if abs(predicted - timeline.severity) < 2.0:
            return None  # No significant divergence

        # Find the first recovery event -- this is often where reality
        # diverges from a naive simulation (because the sim doesn't model
        # manual intervention).
        for ev in sorted(timeline.events, key=lambda e: e.timestamp_offset_seconds):
            if ev.event_type == "recovery":
                return ev.timestamp_offset_seconds

        return None

    def _generate_lessons(
        self,
        timeline: IncidentTimeline,
        results: list[ScenarioResult],
        predicted: float,
        actual: float,
    ) -> list[str]:
        """Generate lessons learned from the replay comparison."""
        lessons: list[str] = []

        if predicted > actual + 1.0:
            lessons.append(
                "Simulation predicted HIGHER severity than reality. "
                "Your infrastructure may have unmmodeled resilience "
                "(e.g., manual intervention, graceful degradation)."
            )
        elif predicted < actual - 1.0:
            lessons.append(
                "Simulation predicted LOWER severity than reality. "
                "There may be failure modes not captured in the model "
                "(e.g., cascading failures, human error amplification)."
            )
        else:
            lessons.append(
                "Simulation closely matches the recorded incident severity. "
                "Your infrastructure model appears accurate for this scenario."
            )

        # Check for components referenced in the timeline but missing from the
        # graph (blind spots in the model).
        missing = set()
        for ev in timeline.events:
            if ev.component_id not in self.graph.components:
                missing.add(ev.component_id)
        if missing:
            lessons.append(
                f"Components referenced in the incident but missing from "
                f"the model: {', '.join(sorted(missing))}. "
                f"Add them to improve simulation accuracy."
            )

        if timeline.root_cause:
            lessons.append(f"Root cause: {timeline.root_cause}")

        if timeline.resolution:
            lessons.append(f"Resolution: {timeline.resolution}")

        return lessons
