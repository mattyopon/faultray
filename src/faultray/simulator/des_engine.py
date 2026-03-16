"""Discrete Event Simulation engine for infrastructure resilience.

Models infrastructure failures as a sequence of time-stamped events processed
from a priority queue.  Each event (fault, cascade, recovery) triggers
downstream events with realistic propagation delays, producing a full
timeline of how a failure unfolds over time.

Uses ONLY the Python standard library.

Basic usage::

    >>> from faultray.model.graph import InfraGraph
    >>> from faultray.simulator.scenarios import Fault, FaultType
    >>> graph = InfraGraph()
    >>> # ... populate graph ...
    >>> engine = DESEngine(graph)
    >>> fault = Fault(target_component_id="db-1", fault_type=FaultType.COMPONENT_DOWN)
    >>> result = engine.simulate(fault)
    >>> print(result.severity)
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from faultray.model.components import HealthStatus

if TYPE_CHECKING:
    from faultray.model.graph import InfraGraph
    from faultray.simulator.scenarios import Fault


class EventType(str, Enum):
    """Types of events processed by the DES engine."""

    FAULT = "fault"
    CASCADE = "cascade"
    RECOVERY = "recovery"


@dataclass(order=True)
class Event:
    """A single discrete event in the simulation timeline.

    Events are ordered by timestamp so that ``heapq`` processes them
    in chronological order.

    Attributes:
        timestamp: Simulation time in seconds when the event fires.
        component_id: The component affected by this event.
        event_type: Category of the event (fault / cascade / recovery).
        data: Arbitrary metadata (reason strings, severity values, etc.).
    """

    timestamp: float
    component_id: str = field(compare=False)
    event_type: EventType = field(compare=False)
    data: dict[str, Any] = field(default_factory=dict, compare=False)


@dataclass
class DESResult:
    """Complete result of a Discrete Event Simulation run.

    Attributes:
        events_timeline: Chronologically ordered list of all processed events.
        affected_components: Component IDs that ended in a non-HEALTHY state.
        total_duration: Wall-clock simulation time consumed (seconds).
        severity: Overall severity score in ``[0.0, 10.0]``.
        component_states: Final health state per component.
    """

    events_timeline: list[Event] = field(default_factory=list)
    affected_components: list[str] = field(default_factory=list)
    total_duration: float = 0.0
    severity: float = 0.0
    component_states: dict[str, HealthStatus] = field(default_factory=dict)


class DESEngine:
    """Discrete Event Simulation engine for infrastructure resilience.

    Events are inserted into a min-heap keyed by timestamp.  The main loop
    pops the earliest event, applies its effect, and optionally schedules
    follow-on events (cascade propagation, recovery timers).

    Parameters:
        graph: The infrastructure dependency graph.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph
        self._event_queue: list[Event] = []
        self._states: dict[str, HealthStatus] = {}
        self._processed_events: list[Event] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def schedule_event(self, event: Event) -> None:
        """Push an event onto the priority queue."""
        heapq.heappush(self._event_queue, event)

    def simulate(
        self,
        initial_fault: Fault,
        duration: float = 3600.0,
    ) -> DESResult:
        """Run a full DES simulation for *initial_fault*.

        Parameters:
            initial_fault: The fault to inject at ``t=0``.
            duration: Maximum simulation wall-clock time in seconds.

        Returns:
            A ``DESResult`` with the event timeline, affected components,
            total duration and severity score.
        """
        # Reset state
        self._event_queue = []
        self._processed_events = []
        self._states = {
            cid: HealthStatus.HEALTHY for cid in self.graph.components
        }

        # Seed the simulation with the initial fault event
        self.schedule_event(
            Event(
                timestamp=0.0,
                component_id=initial_fault.target_component_id,
                event_type=EventType.FAULT,
                data={
                    "fault_type": initial_fault.fault_type.value,
                    "severity": initial_fault.severity,
                    "reason": f"Injected fault: {initial_fault.fault_type.value}",
                },
            )
        )

        current_time = 0.0

        while self._event_queue:
            event = heapq.heappop(self._event_queue)

            if event.timestamp > duration:
                break

            current_time = event.timestamp
            self._processed_events.append(event)

            if event.event_type == EventType.FAULT:
                self._process_fault_event(event)
            elif event.event_type == EventType.CASCADE:
                self._process_cascade_event(event)
            elif event.event_type == EventType.RECOVERY:
                self._process_recovery_event(event)

        # Build result
        affected = [
            cid
            for cid, state in self._states.items()
            if state != HealthStatus.HEALTHY
        ]

        severity = self._calculate_severity(affected)

        return DESResult(
            events_timeline=list(self._processed_events),
            affected_components=affected,
            total_duration=current_time,
            severity=severity,
            component_states=dict(self._states),
        )

    # ------------------------------------------------------------------
    # Event processors
    # ------------------------------------------------------------------

    def _process_fault_event(self, event: Event) -> None:
        """Handle a fault event: mark the component DOWN and schedule cascades."""
        comp_id = event.component_id
        comp = self.graph.get_component(comp_id)
        if comp is None:
            return

        self._states[comp_id] = HealthStatus.DOWN

        # Schedule cascade events for every component that depends on this one
        dependents = self.graph.get_dependents(comp_id)
        for dep_comp in dependents:
            if self._states.get(dep_comp.id) == HealthStatus.DOWN:
                continue  # already down

            edge = self.graph.get_dependency_edge(dep_comp.id, comp_id)
            dep_type = edge.dependency_type if edge else "requires"
            edge_latency_s = (edge.latency_ms / 1000.0) if edge else 0.5

            # Propagation delay: at least the edge latency + a small timeout
            propagation_delay = max(edge_latency_s, 0.1) + comp.capacity.timeout_seconds * 0.1

            self.schedule_event(
                Event(
                    timestamp=event.timestamp + propagation_delay,
                    component_id=dep_comp.id,
                    event_type=EventType.CASCADE,
                    data={
                        "source_id": comp_id,
                        "dependency_type": dep_type,
                        "reason": (
                            f"Cascade from {comp_id} ({dep_type} dependency)"
                        ),
                    },
                )
            )

        # Schedule a recovery event based on MTTR
        mttr_seconds = comp.operational_profile.mttr_minutes * 60.0
        if mttr_seconds > 0:
            self.schedule_event(
                Event(
                    timestamp=event.timestamp + mttr_seconds,
                    component_id=comp_id,
                    event_type=EventType.RECOVERY,
                    data={"reason": f"MTTR recovery after {mttr_seconds:.0f}s"},
                )
            )

    def _process_cascade_event(self, event: Event) -> None:
        """Handle a cascade event: update health based on dependency type."""
        comp_id = event.component_id
        comp = self.graph.get_component(comp_id)
        if comp is None:
            return

        current = self._states.get(comp_id, HealthStatus.HEALTHY)
        if current == HealthStatus.DOWN:
            return  # already in worst state

        dep_type = event.data.get("dependency_type", "requires")
        source_id = event.data.get("source_id", "")

        if dep_type == "requires":
            # A required dependency is down
            if comp.replicas > 1 and current == HealthStatus.HEALTHY:
                new_state = HealthStatus.DEGRADED
            else:
                new_state = HealthStatus.DOWN
        elif dep_type == "optional":
            new_state = HealthStatus.DEGRADED
        elif dep_type == "async":
            if current == HealthStatus.HEALTHY:
                new_state = HealthStatus.DEGRADED
            else:
                new_state = current
        else:
            new_state = HealthStatus.DEGRADED

        # Only worsen the state, never improve it mid-cascade
        if self._state_severity(new_state) > self._state_severity(current):
            self._states[comp_id] = new_state

        # If the component went DOWN, propagate further
        if self._states[comp_id] == HealthStatus.DOWN:
            dependents = self.graph.get_dependents(comp_id)
            for dep_comp in dependents:
                if self._states.get(dep_comp.id) == HealthStatus.DOWN:
                    continue

                edge = self.graph.get_dependency_edge(dep_comp.id, comp_id)
                d_type = edge.dependency_type if edge else "requires"
                edge_latency_s = (edge.latency_ms / 1000.0) if edge else 0.5
                delay = max(edge_latency_s, 0.1) + 1.0

                self.schedule_event(
                    Event(
                        timestamp=event.timestamp + delay,
                        component_id=dep_comp.id,
                        event_type=EventType.CASCADE,
                        data={
                            "source_id": comp_id,
                            "dependency_type": d_type,
                            "reason": (
                                f"Secondary cascade from {comp_id} "
                                f"(originally triggered by {source_id})"
                            ),
                        },
                    )
                )

            # Schedule recovery
            if comp is not None:
                mttr_seconds = comp.operational_profile.mttr_minutes * 60.0
                if mttr_seconds > 0:
                    self.schedule_event(
                        Event(
                            timestamp=event.timestamp + mttr_seconds,
                            component_id=comp_id,
                            event_type=EventType.RECOVERY,
                            data={
                                "reason": (
                                    f"MTTR recovery after cascade "
                                    f"({mttr_seconds:.0f}s)"
                                ),
                            },
                        )
                    )

    def _process_recovery_event(self, event: Event) -> None:
        """Handle a recovery event: restore component to HEALTHY."""
        comp_id = event.component_id
        self._states[comp_id] = HealthStatus.HEALTHY

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _state_severity(state: HealthStatus) -> int:
        """Numeric severity for health state ordering."""
        return {
            HealthStatus.HEALTHY: 0,
            HealthStatus.DEGRADED: 1,
            HealthStatus.OVERLOADED: 2,
            HealthStatus.DOWN: 3,
        }.get(state, 0)

    def _calculate_severity(self, affected: list[str]) -> float:
        """Compute severity score in ``[0.0, 10.0]``."""
        total = len(self._states)
        if total == 0 or not affected:
            return 0.0

        down = sum(
            1
            for cid in affected
            if self._states.get(cid) == HealthStatus.DOWN
        )
        overloaded = sum(
            1
            for cid in affected
            if self._states.get(cid) == HealthStatus.OVERLOADED
        )
        degraded = sum(
            1
            for cid in affected
            if self._states.get(cid) == HealthStatus.DEGRADED
        )

        affected_count = len(affected)
        impact = (down * 1.0 + overloaded * 0.5 + degraded * 0.25) / affected_count
        spread = affected_count / total
        raw = impact * spread * 10.0

        if affected_count <= 1:
            raw = min(raw, 3.0)
        elif spread < 0.3:
            raw = min(raw, 6.0)

        if down == 0 and overloaded == 0 and degraded > 0:
            raw = min(raw, 4.0)

        return min(10.0, max(0.0, round(raw, 1)))
