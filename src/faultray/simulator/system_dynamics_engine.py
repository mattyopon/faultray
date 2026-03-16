"""System Dynamics (Stock-and-Flow) engine for infrastructure resilience.

Models component health as continuous stocks with degradation/recovery flows.
Unlike ABM (discrete agents) or DES (discrete events), this captures
continuous degradation dynamics via differential equations.

Key Concepts:
  - **Stock**: A continuously valued quantity that accumulates over time.
    Here each component's health level (0.0–1.0) is a stock.
  - **Flow**: The rate of change of a stock. Three flows govern each stock:
      * recovery_rate – how quickly a healthy component self-heals
      * degradation_rate – background wear or load-induced degradation
      * cascade_impact – additional drain caused by unhealthy neighbours
  - **Euler integration**: dHealth/dt = recovery_rate - degradation_rate
    - cascade_impact is approximated at discrete time-steps of width *dt*.

Comparison with other engines in FaultRay:
  - ABM (abm_engine.py): models components as discrete autonomous agents
    with rule-based behaviour – good for emergent phenomena but poor at
    capturing smooth, continuous degradation curves.
  - DES (des_engine.py): event-driven; state changes only when discrete
    events occur – misses gradual trends between events.
  - Cellular Automata (cellular_automata_engine.py): grid-based discrete
    state transitions – captures spatial propagation patterns but not
    continuous health levels.
  - This engine fills the gap by treating health as a *continuous* variable
    governed by ordinary differential equations (ODEs), enabling analysis
    of degradation velocity, tipping-point thresholds, and recovery
    trajectories that are invisible to discrete-state models.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from faultray.model.components import Component, HealthStatus
from faultray.model.graph import InfraGraph


@dataclass
class SDResult:
    """Result of a System Dynamics simulation run.

    Attributes:
        time_series: Mapping from component_id to a list of health values
            sampled at each time-step.  ``time_series[cid][i]`` is the health
            of component *cid* at time ``i * dt``.
        failed_components: Component IDs whose health dropped to 0.0 during
            the simulation.
        severity: Overall severity score (0.0–10.0) based on the fraction
            and depth of degradation across all components.
        duration: Total simulated time.
        dt: Time-step width used for Euler integration.
    """

    time_series: dict[str, list[float]] = field(default_factory=dict)
    failed_components: list[str] = field(default_factory=list)
    severity: float = 0.0
    duration: float = 0.0
    dt: float = 0.1


class SystemDynamicsEngine:
    """Stock-and-Flow simulation engine for infrastructure health dynamics.

    Each component is modelled as a *stock* whose value (health, 0.0–1.0)
    evolves according to three *flows*:

    .. math::

        \\frac{dH_i}{dt} = r_i - d_i - \\sum_{j \\in \\text{deps}(i)} c_{ji}

    where *r_i* is the recovery rate, *d_i* is the intrinsic degradation
    rate, and *c_ji* is the cascade impact from each dependency *j* that
    component *i* relies on.

    Parameters:
        graph: The infrastructure dependency graph.
        dt: Euler integration time-step (smaller ⇒ more accurate but slower).
    """

    def __init__(self, graph: InfraGraph, dt: float = 0.1) -> None:
        self.graph = graph
        self.dt = max(0.001, dt)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def simulate(
        self,
        fault_component: str,
        duration: float = 100.0,
        degradation_rate: float = 0.05,
        recovery_rate: float = 0.01,
        cascade_weight: float = 0.3,
    ) -> SDResult:
        """Run a System Dynamics simulation starting from *fault_component*.

        The faulted component's health is set to 0.0 at *t=0* and is
        prevented from recovering (modelling a hard failure).  All other
        components start at 1.0 and evolve under the ODE.

        Args:
            fault_component: ID of the component that fails initially.
            duration: Total simulated time (arbitrary units).
            degradation_rate: Base degradation flow per unit time.
            recovery_rate: Base recovery flow per unit time.
            cascade_weight: Multiplier for cascade impact from unhealthy
                neighbours.

        Returns:
            An :class:`SDResult` containing full time-series and summary
            statistics.
        """
        components = self.graph.components
        if not components or fault_component not in components:
            return SDResult(dt=self.dt, duration=duration)

        # Initialise stocks – all healthy except the fault target
        health: dict[str, float] = {}
        for cid in components:
            health[cid] = 0.0 if cid == fault_component else 1.0

        # Pre-compute dependency map: for each component, which components
        # does it depend on?  (i.e. successors in the directed graph)
        dep_map: dict[str, list[str]] = {}
        for cid in components:
            deps = self.graph.get_dependencies(cid)
            dep_map[cid] = [d.id for d in deps]

        steps = max(1, int(duration / self.dt))
        time_series: dict[str, list[float]] = {cid: [health[cid]] for cid in components}

        for _ in range(steps):
            new_health: dict[str, float] = {}
            for cid in components:
                if cid == fault_component:
                    # Faulted component stays down
                    new_health[cid] = 0.0
                    continue

                h = health[cid]

                # Compute cascade impact from dependencies
                cascade_impact = 0.0
                for dep_id in dep_map.get(cid, []):
                    dep_health = health.get(dep_id, 1.0)
                    # Impact grows as dependency health decreases
                    cascade_impact += cascade_weight * (1.0 - dep_health)

                    # Weight by dependency type
                    edge = self.graph.get_dependency_edge(cid, dep_id)
                    if edge:
                        if edge.dependency_type == "optional":
                            cascade_impact *= 0.3
                        elif edge.dependency_type == "async":
                            cascade_impact *= 0.1

                # ODE: dH/dt = recovery - degradation - cascade
                dh_dt = recovery_rate - degradation_rate - cascade_impact

                # Euler step
                h_new = h + dh_dt * self.dt
                new_health[cid] = max(0.0, min(1.0, h_new))

            health = new_health
            for cid in components:
                time_series[cid].append(health[cid])

        # Determine failed components (health reached 0.0 at any point)
        failed: list[str] = []
        for cid, series in time_series.items():
            if any(v <= 0.0 for v in series):
                failed.append(cid)

        severity = self._compute_severity(time_series, len(components))

        return SDResult(
            time_series=time_series,
            failed_components=failed,
            severity=severity,
            duration=duration,
            dt=self.dt,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_severity(
        time_series: dict[str, list[float]], total_components: int
    ) -> float:
        """Compute an overall severity score (0.0–10.0).

        The score reflects both the *depth* of degradation (how low health
        drops) and *breadth* (how many components are affected).
        """
        if not time_series or total_components == 0:
            return 0.0

        min_healths = [min(series) for series in time_series.values()]

        # Average degradation depth across all components
        avg_degradation = sum(1.0 - h for h in min_healths) / total_components

        # Fraction of components that experienced significant degradation
        degraded_count = sum(1 for h in min_healths if h < 0.5)
        spread = degraded_count / total_components

        raw = (avg_degradation * 0.6 + spread * 0.4) * 10.0
        return round(max(0.0, min(10.0, raw)), 1)
